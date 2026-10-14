import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from check_calculations import evaluate
from validate import validate

DATA=json.loads((ROOT/'tests/fixtures/bond_synthetic_cases.json').read_text(encoding='utf-8'))
CASES={x['id']:x for x in DATA['cases']}

class FixtureSmokeTests(unittest.TestCase):
    def test_skill_structure(self): validate()
    def test_all_fixtures_are_non_authoritative(self):
        for c in CASES.values(): self.assertNotEqual(c['legal_status'],'VERIFIED')
    def test_ofz_cash_reconciliation(self): self.assertEqual(evaluate(CASES['T01'])['gross_cash_profit'],Decimal('52'))
    def test_issue_discount_split(self):
        r=evaluate(CASES['T06']);self.assertEqual(r['issue_discount'],Decimal('80'));self.assertEqual(r['other_redemption_result'],Decimal('20'))
    def test_amort_cost_conservation(self):
        r=evaluate(CASES['T08']);self.assertEqual(sum(r['cost_allocations']),Decimal('960'));self.assertEqual(r['remaining_tax_cost'],0)
    def test_indexation_double_count_guard(self):
        r=evaluate(CASES['T09']);self.assertEqual(r['gross_cash_profit'],Decimal('40'));self.assertEqual(r['duplicate_disposal_indexation'],0)
    def test_fx_result(self): self.assertEqual(evaluate(CASES['T10'])['gross_rub_result'],Decimal('10000'))
    def test_fifo(self): self.assertEqual(evaluate(CASES['T12'])['gross_profit'],Decimal('300'))
    def test_stop_gates(self):
        for k in ('T14','T15','T16'):
            self.assertIsNone(evaluate(CASES[k])['approved_tax_amount'])

if __name__=='__main__':unittest.main()
