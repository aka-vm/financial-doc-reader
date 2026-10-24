import copy
import unittest
from unittest.mock import patch
from reader import contract


def valid_spec():
    return {'terms': {}, 'definitions': {'servicing_fee': 'pool_begin * 0.01 / 12'},
            'steps': [{'id':'i','pay':'servicer','kind':'fee','amount':'servicing_fee'},
                      {'id':'ii','pay':'certificateholder','kind':'residual','amount':'available_funds'}],
            'principal_order':[['A']]}


class ContractStructureTests(unittest.TestCase):
    def test_nested_model_spec_triggers_repair_before_month_run(self):
        good=valid_spec()
        malformed={'terms':{'note_rates_pct':{'A':5},'definitions':good['definitions'],
                            'steps':good['steps'],'principal_order':good['principal_order']}}
        self.assertTrue(all('top-level' in issue for issue in contract.problems(malformed,['A'])))
        with patch.object(contract,'find_payments',return_value=('sale.htm','5.7','Distributions')), \
             patch.object(contract,'build_pack',return_value=('Source contract excerpt',[])), \
             patch.object(contract,'call',side_effect=[malformed,good]) as model:
            result=contract.write_spec({'sale.htm':'source'},['A'],'openai','gpt-5-mini',log=lambda *args:None)
        self.assertEqual(model.call_count,2)
        self.assertIn("move 'steps' out of 'terms'",model.call_args.args[2])
        self.assertFalse(result['problems'])
        self.assertEqual(result['spec']['steps'],good['steps'])

    def test_empty_missing_and_wrong_type_specs_are_not_valid(self):
        bad=[{}, {'terms':{}}, {'definitions':{},'steps':[],'principal_order':[]},
             {'definitions':[],'steps':{},'principal_order':'A'}, None, []]
        for spec in bad:
            with self.subTest(spec=spec):
                self.assertTrue(contract.problems(spec,['A']))
                self.assertEqual(contract.close_parens(spec),[])

    def test_malformed_rows_and_formulas_do_not_crash_the_validator(self):
        replacements=[('definitions',{'fee':None}),('steps',[None]),
                      ('steps',[{'id':'i','pay':'A','kind':'interest'}]),
                      ('principal_order',['A']),('principal_order',[[]])]
        for key,value in replacements:
            spec=valid_spec();spec[key]=value
            with self.subTest(key=key,value=value):self.assertTrue(contract.problems(spec,['A']))
        duplicate=valid_spec();duplicate['principal_order']=[['A'],['A']]
        self.assertTrue(any('repeats class' in issue for issue in contract.problems(duplicate,['A'])))

    def test_repaired_structure_exposes_invalid_formulas_instead_of_accepting_them(self):
        spec=valid_spec();spec['definitions']['int_A']='(x ? 1 : 0)'
        self.assertTrue(any('not a valid expression' in issue for issue in contract.problems(spec,['A'])))
        spec['definitions']['int_A']='unknown_input * bal_A'
        self.assertTrue(any('unknown_input' in issue for issue in contract.problems(spec,['A'])))
        self.assertFalse(contract.problems(valid_spec(),['A']))
