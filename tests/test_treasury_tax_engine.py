"""Integration contracts for the unified treasury tax orchestrator.

Uses the real multi-lot implementation locally; single-lot adapters are integration-
tested when their modules are present (e.g., GitHub Actions checkout).
"""
import copy
import importlib.util
import json
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from treasury_tax_engine import (EngineBlocked, _input_profile, _normalize,
                                 load_catalog, run_unified, safe_run)


def mini_catalog():
    ids = ('BND-NKD-LEDGER', 'BND-INDEXED-OFZ', 'BND-CLEAN-PRICE-RESULT',
           'BND-FX-NO-REVALUE', 'BND-OFZ-INT-20', 'BND-GEN-25')
    entries = []
    for rid in ids:
        rate = 20 if rid == 'BND-OFZ-INT-20' else (25 if rid == 'BND-GEN-25' else None)
        entries.append({'id': rid, 'as_of': '2026-10-14', 'valid_from': '2025-01-01'
                        if rate is not None else None, 'valid_to': None,
                        'rate_percent': rate, 'required_conditions': ['actual_legal_text',
                        'issue_terms'], 'primary_provision': 'НК РФ ст.280, 284, 328',
                        'sources': ['NK-RU-280', 'NK-RU-284'],
                        'readiness': 'normative_framework'})
    return {'rules': entries, 'legal_snapshot_date': '2026-10-14'}


def fixture(name):
    return json.loads((ROOT / 'examples' / name).read_text(encoding='utf-8'))


def rub_payload():
    return {'events': [
        {'id': 'B1', 'date': '2026-01-10', 'type': 'BUY', 'security_id': 'RUB1',
         'lot_id': 'L1', 'currency': 'RUB', 'principal_unit': '1000',
         'quantity': '1', 'clean_price_unit': '980', 'nkd_unit': '0',
         'coupon_rule_id': 'BND-OFZ-INT-20', 'traded_market_status': 'TRADED'},
        {'id':'R1', 'date': '2026-03-01', 'type': 'REDEEM', 'security_id':'RUB1'}]}


class UnifiedEngineTests(unittest.TestCase):
    def setUp(self):
        self.catalog = mini_catalog()
        self.fx = fixture('fx_multilot_synthetic.json')
        self.indexed = fixture('ofz_in_multilot_synthetic.json')

    def test_multi_fx_routes_and_reconciles(self):
        r = run_unified(self.fx, catalog=self.catalog)
        self.assertEqual(r['route']['backend'], 'multilot_bond_ledger')
        self.assertEqual(r['instrument']['kind'], 'FX')
        self.assertEqual(r['accounting']['net_cash_flow_rub'], '46125')
        self.assertEqual(r['accounting']['component_total_rub'], '46125')
        self.assertTrue(r['accounting']['closed_position_reconciled'])
        self.assertEqual(r['accounting']['candidate_tax_base_totals_rub']['GENERAL_PROFIT_CANDIDATE'], '35530')
        self.assertIsNone(r['tax_outcome']['approved_tax_amount_rub'])
        self.assertIsNone(r['tax_outcome']['indicative_total_tax_rub'])

    def test_multi_ofz_routes_and_reconciles(self):
        r = run_unified(self.indexed, catalog=self.catalog)
        self.assertEqual(r['route']['backend'], 'multilot_bond_ledger')
        self.assertEqual(r['instrument']['kind'], 'OFZ_IN')
        self.assertEqual(r['accounting']['component_total_rub'], '113')
        self.assertEqual(r['accounting']['candidate_tax_base_totals_rub']['SPECIAL_INTEREST_CANDIDATE'], '104')
        self.assertEqual(r['accounting']['candidate_tax_base_totals_rub']['GENERAL_PROFIT_CANDIDATE'], '9')

    def test_tax_rows_have_pinpoint_conditions_and_date(self):
        r = run_unified(self.indexed, catalog=self.catalog)
        for item in r['accounting']['tax_components']:
            self.assertTrue(item['legal_pinpoint'])
            self.assertTrue(item['rule_id'])
            self.assertTrue(item['required_applicability_conditions'])
            self.assertEqual(item['legal_status'], 'UNVERIFIED_LEGAL_EDITION')
            self.assertIsNone(item['approved_tax_amount_rub'])
            self.assertEqual(item['event_date'][:4], '2026')

    def test_purchased_nkd_revaluation_unclassified(self):
        r = run_unified(self.fx, catalog=self.catalog)
        x = [x for x in r['accounting']['tax_components']
             if x['component'] == 'PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED']
        self.assertTrue(x)
        self.assertTrue(all(z['candidate_tax_base'] == 'UNCLASSIFIED_NOT_TAX_BASE' for z in x))
        self.assertTrue(r['legal_validation']['unclassified_components_present'])
        self.assertIn('Legal tax classification of purchased-NKD FX differences',
                      r['legal_validation']['required_documents_if_sources_unavailable'])

    def test_law_never_marked_verified_by_calculation(self):
        r = run_unified(self.indexed, catalog=self.catalog)
        self.assertFalse(r['legal_validation']['amendment_check_performed'])
        self.assertFalse(r['legal_validation']['authoritative_texts_checked'])
        self.assertEqual(r['status'], 'UNVERIFIED_LEGAL_EDITION')
        self.assertEqual(r['tax_outcome']['approved_tax_amount_rub'], None)

    def test_single_fx_routes_to_advanced_backend(self):
        b = copy.deepcopy(self.fx['events'][0]);b['quantity'] = '1'
        r = {'kind':'FX','events':[b,{'id':'S','date':'2026-02-01','type':'SELL',
                                     'security_id':b['security_id'],'quantity':'1',
                                     'clean_price_unit':'1100','nkd_unit':'0',
                                     'rub_per_nominal_currency':'95'}]}
        self.assertEqual(_input_profile(r)['backend'], 'advanced_bond_ledger')

    def test_single_ofz_routes_to_advanced_backend(self):
        b=copy.deepcopy(self.indexed['events'][0]);b['quantity']='1'
        events=[b,{'id':'R','date':'2026-04-01','type':'REDEEM',
                   'security_id':b['security_id']}]
        self.assertEqual(_input_profile({'events':events})['backend'], 'advanced_bond_ledger')

    def test_rub_routes_to_rub_ledger(self):
        self.assertEqual(_input_profile(rub_payload())['backend'], 'bond_ledger')

    def test_requested_multi_for_single_fx(self):
        b=copy.deepcopy(self.fx['events'][0]);b['quantity']='1'
        events=[b,{'id':'S','date':'2026-03-01','type':'SELL','security_id':b['security_id'],
                   'quantity':'1','clean_price_unit':'1000','nkd_unit':'0',
                   'rub_per_nominal_currency':'95','coupon_period':'C1'}]
        self.assertEqual(_input_profile({'calculation_mode':'multi', 'events':events})['backend'],
                         'multilot_bond_ledger')

    def test_single_override_cannot_bypass_multilot(self):
        x=copy.deepcopy(self.fx);x['calculation_mode']='single'
        r=safe_run(x,catalog=self.catalog)
        self.assertEqual(r['status'],'BLOCKED')
        self.assertEqual(r['reason_code'],'SINGLE_LOT_ROUTE_UNSAFE')

    def test_declared_kind_mismatch_is_blocked(self):
        x=copy.deepcopy(self.fx);x['kind']='OFZ_IN'
        self.assertEqual(safe_run(x,catalog=self.catalog)['reason_code'],
                         'DECLARED_KIND_MISMATCH')

    def test_mixed_buy_instrument_kinds_blocked(self):
        x=copy.deepcopy(self.fx);x['events'][1]['nominal_currency']='RUB'
        x['events'][1]['currency']='RUB';x['events'][1]['principal_unit']='1000'
        self.assertEqual(safe_run(x,catalog=self.catalog)['reason_code'],
                         'MIXED_INSTRUMENT_KINDS')

    def test_mixed_security_ids_blocked(self):
        x=copy.deepcopy(self.fx);x['events'][2]['security_id']='other'
        self.assertEqual(safe_run(x,catalog=self.catalog)['reason_code'],
                         'MULTIPLE_SECURITIES')

    def test_unknown_instrument_is_blocked(self):
        x=copy.deepcopy(self.fx);x['events'][0]['nominal_currency']='RUB'
        self.assertEqual(safe_run(x,catalog=self.catalog)['reason_code'],
                         'INSTRUMENT_CLASSIFICATION_REQUIRED')

    def test_bad_event_duplicate_id(self):
        x=copy.deepcopy(self.fx);x['events'][2]['id']=x['events'][1]['id']
        self.assertEqual(safe_run(x,catalog=self.catalog)['status'],'INVALID_INPUT')

    def test_out_of_order_rejected(self):
        x=copy.deepcopy(self.fx);x['events'][2]['date']='2026-01-01'
        self.assertEqual(safe_run(x,catalog=self.catalog)['status'],'INVALID_INPUT')

    def test_reject_float_input(self):
        x=copy.deepcopy(self.fx);x['events'][0]['clean_price_unit']=1000.01
        self.assertEqual(safe_run(x,catalog=self.catalog)['status'],'INVALID_INPUT')

    def test_reject_disposal_exceeding_position(self):
        x=copy.deepcopy(self.fx);x['events'][3]['quantity']='1000'
        self.assertEqual(safe_run(x,catalog=self.catalog)['status'],'INVALID_INPUT')

    def test_negative_indexation_blocks(self):
        x=copy.deepcopy(self.indexed);x['events'][6]['indexed_nominal_unit']='1005'
        result=safe_run(x,catalog=self.catalog)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['reason_code'],'NEGATIVE_INDEXATION_REVIEW')

    def test_required_rule_absent_blocks(self):
        catalog=mini_catalog()
        catalog['rules']=[r for r in catalog['rules'] if r['id']!='BND-INDEXED-OFZ']
        r=safe_run(self.indexed,catalog=catalog)
        self.assertEqual(r['reason_code'],'UNMAPPED_RULE_REFERENCE')

    def test_legal_snapshot_time_gate(self):
        catalog=mini_catalog()
        r=next(r for r in catalog['rules'] if r['id']=='BND-INDEXED-OFZ')
        r['valid_from']='2027-01-01'
        output=safe_run(self.indexed,catalog=catalog)
        self.assertEqual(output['reason_code'],'RULE_DATE_OUTSIDE_VALIDITY')

    def test_schema_version_and_no_approval_when_blocked(self):
        x=copy.deepcopy(self.indexed);x['events'][0]['nominal_currency']='USD'
        r=safe_run(x,catalog=self.catalog)
        self.assertEqual(r['schema_version'],'0.3.0')
        self.assertIsNone(r['approved_tax_amount_rub'])
        self.assertFalse(r['legal_validation']['amendment_check_performed'])

    def test_rub_adapter_normalization_with_stub(self):
        raw={'tax_entries':[{'event_id':'A','date':'2026-02-15','lot_id':'L1',
                             'security_id':'RUB1','component':'INTEREST_ACCRUAL',
                             'amount_rub':'10','tax_base_candidate':'separate_interest',
                             'rule_id':'BND-OFZ-INT-20'}],
             'cash_flows':[{'event_id':'A','cash_flow_rub':'10'}],
             'positions':[],'closed_position_reconciled':True}
        fake=types.ModuleType('bond_ledger')
        fake.run_ledger=lambda events,catalog=None: raw
        with patch.dict(sys.modules,{'bond_ledger':fake}):
            r=run_unified(rub_payload(),catalog=self.catalog)
        self.assertEqual(r['route']['backend'],'bond_ledger')
        self.assertEqual(r['accounting']['candidate_tax_base_totals_rub'],
                         {'SPECIAL_INTEREST_CANDIDATE':'10'})
        self.assertEqual(r['accounting']['net_cash_flow_rub'],'10')

    def test_real_multilot_produces_no_approved_tax(self):
        for source in (self.fx,self.indexed):
            r=run_unified(source,catalog=self.catalog)
            self.assertIsNone(r['tax_outcome']['approved_tax_amount_rub'])
            self.assertTrue(all(z['approved_tax_amount_rub'] is None
                                for z in r['accounting']['tax_components']))

    def test_single_backend_real_if_available(self):
        if importlib.util.find_spec('advanced_bond_ledger') is None:
            self.skipTest('Advanced single-lot backend not present in isolated local fixture')
        b=copy.deepcopy(self.fx['events'][0]);b['quantity']='1'
        events=[b,{'id':'A','date':'2026-01-31','type':'ACCRUE',
                   'security_id':b['security_id'],'coupon_period':'C1',
                   'nkd_unit':'30','rub_per_nominal_currency':'92'},
                {'id':'C','date':'2026-02-15','type':'COUPON',
                   'security_id':b['security_id'],'coupon_period':'C1',
                   'coupon_unit':'60','rub_per_nominal_currency':'95'},
                {'id':'S','date':'2026-03-15','type':'SELL',
                   'security_id':b['security_id'],'quantity':'1',
                   'clean_price_unit':'1020','nkd_unit':'0',
                   'rub_per_nominal_currency':'100'}]
        r=run_unified({'events':events},catalog=self.catalog)
        self.assertEqual(r['route']['backend'],'advanced_bond_ledger')
        self.assertEqual(r['accounting']['net_cash_flow_rub'],'15900')

    def test_rub_backend_real_if_available(self):
        if importlib.util.find_spec('bond_ledger') is None:
            self.skipTest('RUB backend not present in isolated local fixture')
        f = ROOT / 'examples' / 'bond_lifecycle_t01.json'
        if not f.exists():
            self.skipTest('Existing RUB fixture not in isolated local fixture')
        r=run_unified(json.loads(f.read_text(encoding='utf-8')),catalog=self.catalog)
        self.assertEqual(r['route']['backend'],'bond_ledger')
        self.assertEqual(r['accounting']['net_cash_flow_rub'],'52')


if __name__=='__main__':
    unittest.main()