import tempfile
import unittest
from pathlib import Path
from financial_brief.visuals import build_views, measurement
from financial_brief.server import create_app


def fact(year, value, unit='USD million', label='Revenue', file='statement.txt', source='S1'):
    return {'id': 'F'+str(year)+value, 'label': label, 'value': value, 'period': str(year), 'unit': unit, 'file': file, 'source': source}


class VisualTests(unittest.TestCase):
    def test_same_metric_and_unit_charts_preserve_original_values_and_citations(self):
        facts=[fact(2025,'USD 120 million'),fact(2024,'USD 100 million')]
        views=build_views(facts)
        self.assertEqual(len(views['charts']),1)
        points=views['charts'][0]['points']
        self.assertEqual([p['period'] for p in points],['2024','2025'])
        self.assertEqual([p['number'] for p in points],[100,120])
        self.assertEqual(points[0]['value'],'USD 100 million')
        self.assertEqual(points[0]['evidence'],[facts[1]['id']])

    def test_ambiguity_units_sources_and_conflicting_periods_do_not_chart(self):
        pairs=[
            [fact(2024,'USD 100 million'),fact(2025,'EUR 120 million','EUR million')],
            [fact(2024,'USD 100 million'),fact(2025,'USD 120 thousand','USD thousand')],
            [fact(2024,'USD 100 million'),fact(2025,'USD 120 million',file='other.txt')],
            [fact(2024,'USD 100 million'),fact(2025,'USD 120 million',source='S2')],
            [fact(2024,'USD 100 million'),fact(2025,'USD 120 million'),fact(2025,'USD 125 million')],
            [fact(2024,'10–20','USD million'),fact(2025,'25','USD million')],
            [fact('2024-12-31','USD 100 million'),fact('2025-12-31','USD 120 million')],
        ]
        for facts in pairs:
            with self.subTest(facts=facts):self.assertEqual(build_views(facts)['charts'],[])
        self.assertIsNone(measurement(fact(2025,'USD 2 million','EUR million')))

    def test_negative_values_zero_and_percentages(self):
        self.assertEqual(measurement(fact(2025,'(2)','USD million')),(-2,'USD million'))
        self.assertEqual(measurement(fact(2025,'0','USD million')),(0,'USD million'))
        self.assertEqual(measurement(fact(2025,'12.6%','%')),(12.6,'%'))
        self.assertEqual(len(build_views([fact(2024,'1'),fact(2025,'-2')])['charts']),1)

    def test_fiscal_periods_remain_fiscal_and_unknown_review_is_not_charted(self):
        facts=[fact('FY24','Rs. 100 crores','Rs crore'),fact('FY25','Rs. 120 crores','Rs crore')]
        views=build_views(facts)
        self.assertEqual(len(views['charts']),1)
        self.assertEqual(views['charts'][0]['unit'],'Rs crore')
        self.assertEqual([p['period'] for p in views['charts'][0]['points']],['FY24','FY25'])
        self.assertEqual(build_views([facts[0],fact(2025,'Rs. 120 crores','Rs crore')])['charts'],[])
        self.assertEqual(build_views([facts[0],facts[1]|{'context_reviewed':False}])['charts'],[])

    def test_qualitative_and_flagged_facts_remain_uncharted(self):
        facts=[fact(2024,'USD 100 million'),fact(2025,'USD 120 million')|{'context_problem':'wrong metric'}]
        views=build_views(facts)
        self.assertEqual(len(views['rows']),1)
        self.assertEqual(views['charts'],[])
        self.assertEqual(build_views([fact(2025,'The waiver is conditional')])['rows'],[])

    def test_catalog_has_diverse_downloadable_examples(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'DATA_DIR':directory,'BACKEND':'link','SECRET_KEY':'test'})
            client=app.test_client()
            catalog=client.get('/api/examples').json
            self.assertGreaterEqual(len(catalog),6)
            self.assertGreaterEqual(len({item['category'] for item in catalog}),5)
            self.assertTrue(all(not item['fictional'] for item in catalog))
            self.assertTrue({'zomato','zerodha','americredit'} <= {item['id'] for item in catalog})
            for item in catalog:
                response=client.get(item['url'])
                self.assertEqual(response.status_code,200,item['url'])
                self.assertGreater(len(response.data),100)
                response.close()
            self.assertEqual(client.get('/examples/catalog.json').status_code,404)
