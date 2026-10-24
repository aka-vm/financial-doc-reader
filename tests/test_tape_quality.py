import csv
import tempfile
import unittest
from pathlib import Path
from reader.tape import summary, against_report, BAL, RATE, FICO, TERM
from reader.deal import to_markdown


class TapeQualityTests(unittest.TestCase):
    def make_tape(self, directory, rows):
        path=Path(directory)/'tape.csv'
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=[BAL,RATE,FICO,TERM,'reportingPeriodEndingDate','currentDelinquencyStatus'])
            writer.writeheader()
            for balance,delinquency in rows:
                writer.writerow({BAL:balance,RATE:'0.1',FICO:'700',TERM:'36','reportingPeriodEndingDate':'08-31-2026','currentDelinquencyStatus':delinquency})
        return str(path)

    def test_missing_status_is_unknown_without_changing_balance_or_active_count(self):
        with tempfile.TemporaryDirectory() as directory:
            got=summary(self.make_tape(directory,[(100,0),(50,''),(20,45),(10,'not reported'),(0,''),(-5,'')]))
        self.assertEqual(got['total_assets'],6)
        self.assertEqual(got['loans'],4)
        self.assertEqual(got['excluded_nonpositive_assets'],2)
        self.assertEqual(got['balance'],180)
        self.assertEqual(got['delinquency_balance'],{'30-59':20,'current':100,'unknown':60})
        self.assertEqual(got['missing_delinquency_assets'],2)
        self.assertEqual(got['missing_delinquency_balance'],60)
        self.assertEqual(got['wa_rate_pct'],10)
        self.assertEqual(against_report(got,{'pool_balance_ending':180})['status'],'match')

    def test_nonfinite_and_negative_status_values_are_not_current(self):
        with tempfile.TemporaryDirectory() as directory:
            got=summary(self.make_tape(directory,[(10,'nan'),(20,'inf'),(30,-1),(40,90)]))
        self.assertEqual(got['delinquency_balance'],{'90+':40,'unknown':60})
        self.assertEqual(got['missing_delinquency_assets'],3)

    def test_human_report_distinguishes_active_count_unknown_status_and_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            tape=summary(self.make_tape(directory,[(100,0),(50,''),(0,'')]))
        tape['file']='tape.csv';tape['check']=against_report(tape,{'pool_balance_ending':150.1})
        report={'documents':[{'name':'tape.csv','kind':'loan_tape'}], 'months':[], 'tapes':[tape], 'waterfall':None,'read':[],'notes':[]}
        text=to_markdown(report)
        self.assertIn('2 active loans with positive ending balance (3 total tape rows)',text)
        self.assertIn('unknown for 1 active loans',text)
        self.assertIn('| Unknown / not reported | 50 |',text)
        self.assertIn('within the comparison tolerance',text)
        self.assertNotIn('matches to the cent',text)
