import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from financial_brief import engine
from financial_brief.server import create_app


class EvidenceTests(unittest.TestCase):
    def test_generated_currency_scale_and_negative_amount_cases(self):
        count = 0
        for currency in ("USD", "EUR", "INR", "GBP", "AUD"):
            for unit in ("million", "thousand", "crore"):
                for amount in ("12", "1,234.50", "(620)", "0.25"):
                    quote = f"The 2025 cash balance was {currency} {amount} {unit}."
                    fact = {"label": "Cash", "value": f"{currency} {amount} {unit}",
                            "period": "2025", "unit": f"{currency} {unit}", "quote": quote}
                    with self.subTest(currency=currency, unit=unit, amount=amount):
                        self.assertTrue(engine.supported_fact(fact, {"text": quote}))
                        self.assertFalse(engine.supported_fact(fact | {"value": f"{currency} 999999 {unit}"}, {"text": quote}))
                        self.assertFalse(engine.supported_fact(fact | {"period": "2039"}, {"text": quote}))
                    count += 1
        self.assertEqual(count, 60)

    def test_isolated_decoder_success_and_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "statement.txt"
            path.write_text("Cash was USD 10 million.")
            sources, warnings = engine.read_isolated([path])
            self.assertIn("USD 10 million", sources[0]["text"])
            self.assertEqual(warnings, [])
            path.write_text("")
            with self.assertRaisesRegex(ValueError, "no readable text"):
                engine.read_isolated([path])

    def test_pdf_pages_and_unsupported_pdf_failures(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "statement.pdf"
            writer = PdfWriter()
            for text in ("Revenue was USD 120 million.", "Cash was USD 9 million."):
                page = writer.add_blank_page(width=595, height=842)
                page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
                    NameObject('/F1'): DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})})})
                content = DecodedStreamObject()
                content.set_data(f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode())
                page[NameObject('/Contents')] = writer._add_object(content)
            writer.write(path)
            sources, warnings = engine.read_isolated([path])
            self.assertEqual(sources[0]["page"], "1–2")
            self.assertIn("USD 9 million", sources[0]["text"])
            self.assertFalse(warnings)
            writer.encrypt("secret")
            writer.write(path)
            with self.assertRaisesRegex(ValueError, "encrypted"):
                engine.read_isolated([path])
            blank = PdfWriter()
            blank.add_blank_page(width=595, height=842)
            blank.write(path)
            with self.assertRaisesRegex(ValueError, "no readable text"):
                engine.read_isolated([path])

    def test_multi_file_sources_keep_entity_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.txt", Path(directory) / "b.txt"
            a.write_text("A Ltd cash was USD 10 million.")
            b.write_text("B Ltd cash was USD 90 million.")
            sources, _ = engine.read_isolated([a, b])
            self.assertEqual([s['file'] for s in sources], ['a.txt', 'b.txt'])
            self.assertFalse(engine.supported_fact({'label': 'Cash', 'value': 'USD 90 million',
                'period': '', 'unit': 'USD', 'quote': b.read_text()}, sources[0]))

    def test_values_periods_and_units_must_be_in_quote(self):
        source = {"text": "Revenue was USD 120 million in 2025."}
        fact = {"label": "Revenue", "value": "USD 120 million", "period": "2025",
                "unit": "USD million", "quote": source["text"]}
        self.assertTrue(engine.supported_fact(fact, source))
        self.assertFalse(engine.supported_fact(fact | {"value": "USD 121 million"}, source))
        self.assertFalse(engine.supported_fact(fact | {"period": "2024"}, source))
        self.assertFalse(engine.supported_fact(fact | {"quote": "Revenue was USD 121 million in 2025."}, source))

    def test_writer_cannot_invent_ids_or_numbers(self):
        facts = [{"id": "F1", "quote": "Cash was 10 million."}]
        self.assertTrue(engine.valid_claim({"text": "Cash was 10 million.", "evidence": ["F1"]}, facts))
        self.assertFalse(engine.valid_claim({"text": "Cash was 20 million.", "evidence": ["F1"]}, facts))
        self.assertFalse(engine.valid_claim({"text": "Cash fell.", "evidence": ["F2"]}, facts))

    def test_inline_citations_are_not_financial_numbers(self):
        facts = [{"id": "F13", "quote": "Revenue was 120 million."}]
        self.assertTrue(engine.valid_claim({"text": "Revenue was 120 million (F13).", "evidence": ["F13"]}, facts))
        self.assertFalse(engine.valid_claim({"text": "Revenue was 120 million (F99).", "evidence": ["F13"]}, facts))
        claim = {"text": "Revenue was 120 million (F13).", "evidence": []}
        self.assertEqual(engine.complete_citations(claim)["evidence"], ["F13"])
        self.assertTrue(engine.valid_claim(claim, facts))

    def test_ungrounded_metadata_is_removed_without_losing_source_value(self):
        fact = {"label": "Cash", "value": "EUR (620) thousand", "period": "2025",
                "unit": "EUR thousands", "quote": "Cash was EUR (620) thousand."}
        cleaned = engine.clean_metadata(fact)
        self.assertEqual(cleaned["period"], "")
        self.assertEqual(cleaned["unit"], "EUR thousands")
        self.assertTrue(engine.supported_fact(cleaned, {"text": fact["quote"]}))

    def test_all_text_is_covered_and_oversized_documents_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "statement.txt"
            text = "A" * 23000 + "END OF DOCUMENT"
            path.write_text(text)
            sources, warnings = engine.read_sources([path])
            self.assertEqual(len(sources), 3)
            self.assertTrue(sources[-1]["text"].rstrip().endswith("END OF DOCUMENT"))
            self.assertFalse(warnings)
            path.write_text("x" * (engine.MAX_CHARS + 1))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                engine.read_sources([path])

    def test_pipeline_withholds_unsupported_extractions_and_claims(self):
        quote = "Revenue was USD 120 million in 2025."
        fact = {"label": "Revenue", "value": "120 million", "period": "2025", "unit": "USD", "quote": quote}
        responses = iter([
            {"facts": [fact, fact | {"value": "invented"}]},
            {"title": "Statement", "subtitle": "Financial brief",
             "overview": [{"text": "Revenue was USD 120 million in 2025.", "evidence": ["F1"]}],
             "highlights": [{"text": "Revenue grew 30%.", "evidence": ["F1"]}],
             "risks": [], "questions": ["What drove revenue?"]},
            {"verdicts": [{"id": "C1", "supported": True, "reason": "Explicit in source"},
                          {"id": "F1", "supported": True, "reason": "Explicit in source"}]}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "statement.txt"
            path.write_text(quote)
            report = engine.build([path], "test", "http://test", ask=lambda *a, **kw: next(responses))
        self.assertEqual(len(report["facts"]), 1)
        self.assertEqual(report["rejected"], 2)
        self.assertEqual(report["highlights"], [])

    def test_unanswerable_question_does_not_pass_through_model_assertions(self):
        result = engine.answer("What will it earn?", {"facts": []}, "test", "http://test",
                               ask=lambda *a, **k: {"answer": "It will earn a billion.", "evidence": []})
        self.assertIn("insufficient", result["answer"])

    def test_answer_repair_is_bounded_and_keeps_the_same_source_checks(self):
        report = {"facts": [{"id": "F1", "label": "Cash", "quote": "Cash was USD 10 million."}]}
        responses = iter([{"answer": "Cash was USD 20 million.", "evidence": ["F1"]},
                          {"answer": "Cash was USD 10 million.", "evidence": ["F1"]}])
        result = engine.answer("How much cash?", report, "test", "http://test", ask=lambda *a, **kw: next(responses))
        self.assertTrue(result["repaired"])
        self.assertIn("10 million", result["answer"])
        calls = []
        def bad(*args, **kwargs):
            calls.append(True)
            return {"answer": "Cash was USD 20 million.", "evidence": ["F1"]}
        result = engine.answer("How much cash?", report, "test", "http://test", ask=bad)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["evidence"], [])

    def test_context_review_catches_wrong_metric_despite_matching_numbers(self):
        quote = "The loan pool weighted average coupon was 11.54%."
        responses = iter([
            {"facts": [{"label": "Pool coupon", "value": "11.54%", "period": "", "unit": "%", "quote": quote}]},
            {"title": "Statement", "subtitle": "Brief", "overview": [
                {"text": "The notes pay 11.54% interest.", "evidence": ["F1"]}],
                "highlights": [], "risks": [], "questions": []},
            {"verdicts": [{"id": "C1", "supported": False, "reason": "Pool yield is not the note rate."},
                          {"id": "F1", "supported": True, "reason": "Pool coupon is explicit."}]}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pool.txt"
            path.write_text(quote)
            report = engine.build([path], "test", "http://test", ask=lambda *a, **k: next(responses))
        self.assertEqual(report["context_review"]["claims_withheld"], 1)
        self.assertEqual(report["overview"][0]["text"], "Source excerpt: " + quote)
        self.assertTrue(report["warnings"])

    def test_follow_up_can_retrieve_original_period_not_in_headline_facts(self):
        report = {"facts": [{"id": "F1", "label": "SOFR", "quote": "Accrual ends 8/16/2026."}],
                  "_sources": [{"id": "S1", "file": "report.txt", "page": None, "section": 1,
                                 "text": "Collection Period | 07/01/26-07/31/26\nAccrual ends 8/16/2026."}]}
        def ask(backend, model, prompt, *args, **kwargs):
            self.assertIn("Collection Period", prompt)
            return {"answer": "The collection period is 07/01/26-07/31/26 (S1).", "evidence": ["S1"]}
        result = engine.answer("Which reporting period is covered?", report, "test", "http://test", ask=ask)
        self.assertEqual(result["evidence"], ["S1"])
        self.assertEqual(result["evidence_details"][0]["file"], "report.txt")


class WebTests(unittest.TestCase):
    def test_default_session_survives_restart_and_does_not_share_other_app_cookie(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"TESTING": True, "DATA_DIR": directory, "BACKEND": "link"}
            first = create_app(config)
            client = first.test_client()
            client.get('/').close()
            cookie = client.get_cookie('ledger_session')
            with client.session_transaction() as browser_session:
                owner = browser_session['owner']
            jid = 'b' * 32
            (Path(directory) / f'{jid}.json').write_text(json.dumps({
                'owner': owner, 'created': time.time(), 'status': 'done', 'report': {'title': 'Saved brief'}}))
            restarted = create_app(config)
            resumed = restarted.test_client()
            resumed.set_cookie('ledger_session', cookie.value)
            resumed.set_cookie('session', 'another-app-cookie')
            self.assertEqual(resumed.get(f'/api/briefs/{jid}').status_code, 200)
            self.assertEqual(first.secret_key, restarted.secret_key)
            self.assertEqual((Path(directory) / '.session-secret').stat().st_mode & 0o777, 0o600)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATA_DIR": self.directory.name, "SECRET_KEY": "test-secret", "BACKEND": "link", "CONCURRENCY": 1})
        self.client = self.app.test_client()
        self.client.get("/").close()
        self.headers = {"X-Brief-Request": "1"}

    def tearDown(self):
        self.directory.cleanup()

    def test_submission_boundary_and_limits(self):
        self.assertEqual(self.client.post("/api/briefs").status_code, 403)
        self.assertEqual(self.client.post("/api/briefs", headers=self.headers).status_code, 400)
        response = self.client.post("/api/briefs", headers=self.headers,
                                    data={"files": (io.BytesIO(b"bad"), "script.exe")})
        self.assertEqual(response.status_code, 400)
        # Failed admissions must release the inference slot.
        self.assertEqual(self.client.post("/api/briefs", headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post("/api/briefs", headers=self.headers,
                                         environ_overrides={"CONTENT_LENGTH": str(17 << 20)}).status_code, 413)
        self.assertEqual(self.client.post("/api/briefs", headers={**self.headers, "Origin": "https://evil.test"}).status_code, 403)

    def test_job_isolation_deletion_and_upload_cleanup(self):
        done = threading.Event()

        def build(*args, **kwargs):
            return {"title": "Test", "facts": [], "_sources": [{"text": "Internal retrieval corpus"}]}

        with patch("financial_brief.server.engine.build", side_effect=build):
            response = self.client.post("/api/briefs", headers=self.headers,
                                        data={"files": (io.BytesIO(b"Cash was 10 million."), "cash.txt")})
            self.assertEqual(response.status_code, 202)
            jid = response.json["id"]
            # Wait for asynchronous snapshot completion without arbitrary sleeps.
            for _ in range(100):
                job = self.client.get(f"/api/briefs/{jid}").json
                if job["status"] == "done":
                    break
                done.wait(.01)
            self.assertEqual(job["status"], "done")
            self.assertNotIn("owner", job)
            self.assertNotIn("_sources", job["report"])
            other = self.app.test_client()
            other.get("/").close()
            self.assertEqual(other.get(f"/api/briefs/{jid}").status_code, 404)
            self.assertEqual(self.client.get("/api/briefs/../../secret").status_code, 404)
            self.assertFalse(list(Path(self.directory.name).glob("upload-*")))
            self.assertEqual(self.client.delete(f"/api/briefs/{jid}", headers=self.headers).status_code, 200)
            self.assertEqual(self.client.get(f"/api/briefs/{jid}").status_code, 404)

    def test_follow_up_returns_before_model_and_preserves_access_boundary(self):
        with self.client.session_transaction() as browser:
            owner = browser["owner"]
        jid = "c" * 32
        (Path(self.directory.name) / f"{jid}.json").write_text(json.dumps({
            "owner": owner, "created": time.time(), "status": "done", "report": {}}))
        release = threading.Event()
        def answer(*args, **kwargs):
            release.wait(5)
            return {"answer": "Cash was 10.", "evidence": []}
        with patch("financial_brief.server.engine.answer", side_effect=answer):
            try:
                response = self.client.post(f"/api/briefs/{jid}/ask", headers=self.headers,
                                            json={"question": "How much cash?"})
                self.assertEqual(response.status_code, 202)
                url = f"/api/briefs/{jid}/answers/{response.json['id']}"
                self.assertEqual(self.client.get(url).json["status"], "running")
                other = self.app.test_client()
                other.get("/").close()
                self.assertEqual(other.get(url).status_code, 404)
                self.assertEqual(self.client.delete(f"/api/briefs/{jid}", headers=self.headers).status_code, 409)
                self.assertEqual(self.client.post(f"/api/briefs/{jid}/ask", headers=self.headers,
                                 json={"question": "Another question?"}).status_code, 429)
            finally:
                release.set()
            for _ in range(100):
                result = self.client.get(url).json
                if result["status"] != "running":
                    break
                threading.Event().wait(.01)
            self.assertEqual(result["status"], "done")
            self.assertEqual(result["result"]["answer"], "Cash was 10.")

    def test_second_upload_waits_in_queue_and_starts_automatically(self):
        release, entered = threading.Event(), threading.Event()
        count = []
        def build(*args, **kwargs):
            count.append(1)
            entered.set()
            release.wait(5)
            return {"title": "Test", "facts": [], "warnings": []}
        with patch("financial_brief.server.engine.build", side_effect=build):
            try:
                first = self.client.post('/api/briefs', headers=self.headers,
                    data={'files': (io.BytesIO(b'first'), 'first.txt')})
                self.assertEqual(first.status_code, 202)
                self.assertTrue(entered.wait(2))
                second = self.client.post('/api/briefs', headers=self.headers,
                    data={'files': (io.BytesIO(b'second'), 'second.txt')})
                self.assertEqual(second.status_code, 202)
                jid = second.json['id']
                self.assertEqual(self.client.get(f'/api/briefs/{jid}').json['status'], 'queued')
                self.assertEqual(len(count), 1)
                self.assertEqual(self.client.delete(f'/api/briefs/{jid}', headers=self.headers).status_code, 409)
            finally:
                release.set()
            for _ in range(100):
                state = self.client.get(f'/api/briefs/{jid}').json
                if state['status'] not in {'queued', 'running'}: break
                threading.Event().wait(.01)
            self.assertEqual(state['status'], 'done')
            self.assertEqual(len(count), 2)

    def test_two_reports_can_process_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({"TESTING": True, "DATA_DIR": directory, "BACKEND": "link", "CONCURRENCY": 2, "SECRET_KEY": "test"})
            client=app.test_client();client.get('/').close()
            release, both_started=threading.Event(),threading.Event()
            entered=[];mutex=threading.Lock()
            def build(*args, **kwargs):
                with mutex:
                    entered.append(1)
                    if len(entered)==2:both_started.set()
                release.wait(5)
                return {"title":"Test","facts":[],"warnings":[]}
            with patch('financial_brief.server.engine.build',side_effect=build):
                ids=[]
                try:
                    for i in range(2):
                        result=client.post('/api/briefs',headers=self.headers,data={'files':(io.BytesIO(b'test'),f'{i}.txt')})
                        self.assertEqual(result.status_code,202);ids.append(result.json['id'])
                    self.assertTrue(both_started.wait(2))
                finally:release.set()
                for jid in ids:
                    for _ in range(100):
                        state=client.get(f'/api/briefs/{jid}').json
                        if state['status'] not in {'queued','running'}:break
                        threading.Event().wait(.01)
                    self.assertEqual(state['status'],'done')

    def test_expired_job_is_not_accessible(self):
        with self.client.session_transaction() as session:
            owner = session["owner"]
        jid = "a" * 32
        (Path(self.directory.name) / f"{jid}.json").write_text(json.dumps({"owner": owner, "created": 0}))
        self.assertEqual(self.client.get(f"/api/briefs/{jid}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
