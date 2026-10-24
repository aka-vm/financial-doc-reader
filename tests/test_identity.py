import unittest
from financial_brief.identity import identify

class IdentityTests(unittest.TestCase):
    def source(self,text,file='report.pdf'):
        return {'text':text,'file':file,'id':'S1','page':'1','section':1}

    def test_stock_research_subject_is_the_company_not_publisher_or_peer(self):
        source=self.source('Peer: Other Bank\nReliance Industries Limited is engaged in refining.\nRELIANCE INDUSTRIES (RELIANCE-IN)\nReport by Thomson Reuters')
        subjects=identify([source]);self.assertEqual(subjects[0]['name'],'Reliance Industries Limited')
        self.assertEqual(subjects[0]['ticker'],'RELIANCE-IN')
        self.assertIn(subjects[0]['quote'],source['text'])

    def test_model_subject_requires_exact_name_and_quote_and_does_not_guess(self):
        source=self.source('A report about Northstar Manufacturing. Revenue was USD 120 million.')
        valid={'name':'Northstar Manufacturing','ticker':'','quote':'A report about Northstar Manufacturing.'}
        self.assertEqual(identify([source],{'S1':valid})[0]['name'],'Northstar Manufacturing')
        self.assertEqual(identify([source],{'S1':dict(valid,name='Invented Industries')}),[])
        self.assertEqual(identify([self.source('Unidentified company snapshot')]),[])

    def test_one_subject_per_file_and_multiple_files_remain_separate(self):
        first=self.source('FIRST COMPANY (FIRST-IN)')
        second=self.source('SECOND COMPANY (SECOND-IN)','second.pdf')
        self.assertEqual(len(identify([first,first,second])),2)
