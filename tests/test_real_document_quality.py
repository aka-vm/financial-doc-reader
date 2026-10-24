import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from pypdf import PdfWriter
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
from financial_brief.engine import read_sources,clean_metadata,supported_fact,obj
from financial_brief.selection import select_figures
from reader.convert import pdf_page_text

class RealDocumentQualityTests(unittest.TestCase):
    def test_layout_falls_back_when_numeric_token_is_split(self):
        page=Mock()
        page.extract_text.side_effect=lambda **kwargs:'Group revenue 1,071, 174 crore' if kwargs else 'Group revenue 1,071,174 crore'
        text=pdf_page_text(page)
        self.assertIn('1,071,174',text)
        self.assertNotIn('1,071, 174',text)

    def test_permission_restricted_pdf_with_empty_reading_password_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'annual-report.pdf';writer=PdfWriter();page=writer.add_blank_page(width=595,height=842)
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})})})
            content=DecodedStreamObject();content.set_data(b'BT /F1 12 Tf 40 700 Td (Annual revenue USD 100 million.) Tj ET');page[NameObject('/Contents')]=writer._add_object(content)
            writer.encrypt(user_password='',owner_password='owner-secret');writer.write(path)
            sources,warnings=read_sources([path]);self.assertIn('USD 100 million',sources[0]['text'])

    def test_header_context_can_support_units_but_must_occur_in_source(self):
        source={'text':'Consolidated results FY25 (₹ in crore)\nRevenue was 100'}
        fact={'label':'Consolidated revenue','value':'100','period':'FY25','unit':'INR crore','quote':'Revenue was 100','context_quote':'Consolidated results FY25 (₹ in crore)'}
        cleaned=clean_metadata(fact);self.assertEqual(cleaned['unit'],'INR crore');self.assertEqual(cleaned['period'],'FY25');self.assertTrue(supported_fact(cleaned,source))
        self.assertFalse(supported_fact(fact|{'context_quote':'Invented header FY25 (INR crore)'},source))

    def test_cards_prioritize_material_group_metrics_over_filing_identifiers(self):
        facts=[{'id':'F1','file':'report','label':'Scrip code','value':'500325','period':''},
               {'id':'F2','file':'report','label':'O2C quarterly revenue','value':'164,613','period':'FY25'},
               {'id':'F3','file':'report','label':'Consolidated group annual revenue','value':'1,071,174','period':'2025'},
               {'id':'F4','file':'report','label':'Consolidated EBITDA','value':'183,422','period':'2025'},
               {'id':'F5','file':'report','label':'Capital expenditure','value':'131,107','period':'2025'}]
        selected=select_figures(facts);self.assertEqual(selected[0]['id'],'F3');self.assertNotIn('F1',[f['id'] for f in selected])

    def test_review_schema_requires_every_requested_fact_and_claim(self):
        from reader.backends import closed_schema
        schema=obj({'verdicts':obj({key:obj({'supported':{'type':'boolean'},'reason':{'type':'string'}}) for key in ['C1','F1','F2']})})
        self.assertEqual(set(schema['properties']['verdicts']['required']),{'C1','F1','F2'});self.assertTrue(closed_schema(schema))

    def test_cards_exclude_auditor_scope_and_unmaterial_line_items(self):
        facts=[{'id':'F1','label':'Subsidiary revenue','value':'220','quote':'whose financial results reflect total revenues of INR 220 crores'},
               {'id':'F2','label':'Retail depreciation','value':'5996'},
               {'id':'F3','label':'Consolidated revenue','value':'20243'}]
        self.assertEqual([f['id'] for f in select_figures(facts)],['F3'])

    def test_table_does_not_treat_digits_in_a_name_as_a_numeric_metric(self):
        from financial_brief.visuals import build_views
        facts=[{'id':'F1','label':'Revenue driver','value':'higher volumes of KGD6 and CBM','file':'report'}]
        self.assertEqual(build_views(facts)['rows'],[])

    def test_header_fragments_restore_intervening_source_without_guessing(self):
        from financial_brief.engine import restore_context_span
        source={'text':'Consolidated Jio Platforms\nQuarterly revenue commentary\nFY25 FY24 (INR crore)\nRevenue 150,270 128,521'}
        fact={'label':'Revenue','value':'150,270','period':'FY25','unit':'INR crore',
              'quote':'Revenue 150,270 128,521','context_quote':'Consolidated Jio Platforms\nFY25 FY24 (INR crore)'}
        restored=restore_context_span(fact,source)
        self.assertIn('Quarterly revenue commentary',restored['context_quote'])
        self.assertTrue(supported_fact(restored,source))
        invented=fact|{'context_quote':'Consolidated Jio Platforms\nFY26 FY24 (INR crore)'}
        self.assertEqual(restore_context_span(invented,source),invented)
        self.assertFalse(supported_fact(invented,source))

    def test_claim_period_can_be_grounded_in_verified_table_header(self):
        from financial_brief.engine import valid_claim
        facts=[{'id':'F1','quote':'Revenue 150,270 128,521','context_quote':'FY25 FY24 (INR crore)'}]
        self.assertTrue(valid_claim({'text':'FY25 revenue was INR 150,270 crore.','evidence':['F1']},facts))
        self.assertFalse(valid_claim({'text':'FY26 revenue was INR 150,270 crore.','evidence':['F1']},facts))
