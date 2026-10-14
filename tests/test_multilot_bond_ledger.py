"""Golden calculations & fail-closed invariants for multi-lot research ledger."""
import copy
import json
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from multilot_bond_ledger import LedgerEvidenceRequired, MultiLotBondLedger, run_multilot


def fixture(name):
    return json.loads((ROOT / 'examples' / (name + '.json')).read_text(encoding='utf-8'))


def total(result, base):
    return D(result['candidate_base_totals_rub'].get(base, '0'))


def fail(events, kind, expected_code):
    with unittest.TestCase().assertRaises(LedgerEvidenceRequired) as caught:
        run_multilot(events,kind)
    assert caught.exception.code == expected_code, (caught.exception.code,expected_code)


class MultiLotBondTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixture('fx_multilot_synthetic')['events']
        self.ofz = fixture('ofz_in_multilot_synthetic')['events']

    def test_fx_two_lots_fifo_cross_lot_sale_full_reconciliation(self):
        r=run_multilot(self.fx,'FX')
        self.assertTrue(r['closed_position_reconciled'])
        self.assertEqual(D(r['net_cash_flow_rub']),D('46125'))
        self.assertEqual(D(r['candidate_component_total_rub']),D('46125'))
        self.assertIsNone(r['final_tax_amount_rub'])
        self.assertEqual(r['status'],'UNVERIFIED_LEGAL_EDITION')

    def test_fx_four_distinct_bases(self):
        r=run_multilot(self.fx,'FX')
        self.assertEqual(total(r,'GENERAL_INTEREST_CANDIDATE'),D('9910'))
        self.assertEqual(total(r,'GENERAL_FX_CANDIDATE'),D('135'))
        self.assertEqual(total(r,'GENERAL_PROFIT_CANDIDATE'),D('35530'))
        self.assertEqual(total(r,'UNCLASSIFIED_NOT_TAX_BASE'),D('550'))
        self.assertTrue(r['unclassified_components_present'])

    def test_fx_fifo_sale_lot_details(self):
        r=run_multilot(self.fx,'FX')
        rows=[x for x in r['tax_entries'] if x['event_id']=='S1'
              and x['component']=='PRICE_REALIZATION_CANDIDATE']
        self.assertEqual([(x['lot_id'], D(x['amount_rub'])) for x in rows],
                         [('L1',D('11900')),('L2',D('11720'))])

    def test_fx_first_partial_sale_retains_lot_cost(self):
        r=run_multilot(self.fx[:4],'FX')
        self.assertFalse(r['closed_position_reconciled'])
        self.assertEqual([(p['lot_id'],p['units']) for p in r['positions']],[('L2','1')])
        self.assertEqual(D(r['positions'][0]['remaining_tax_cost_rub']),D('90090'))
        self.assertEqual(D(r['positions'][0]['last_nkd_unit']),D('40'))

    def test_fx_coupon_only_remaining_units(self):
        r=run_multilot(self.fx[:5],'FX')
        couponflows=[x for x in r['cash_flows'] if x['event_id']=='C1']
        self.assertEqual(D(couponflows[0]['cash_flow_rub']),D('5820'))

    def test_fx_purchased_nkd_fx_diff_segregated_by_lot(self):
        r=run_multilot(self.fx,'FX')
        rows=[x for x in r['tax_entries'] if x['component']=='PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED']
        self.assertEqual(sum((D(x['amount_rub']) for x in rows),D('0')),D('550'))
        self.assertTrue(all(x['candidate_tax_base'] is None for x in rows))
        self.assertTrue(all(x['approved_tax_amount_rub'] is None for x in rows))

    def test_fx_purchase_later_lot_after_accrual(self):
        data=copy.deepcopy(self.fx)
        data[1]['date']='2026-02-01'
        data[1]['nkd_unit']='35'
        # chronology: must reorder and permit purchase during open coupon period.
        events=[data[0],data[2],data[1],data[3],data[4],data[5]]
        r=run_multilot(events,'FX')
        self.assertTrue(r['closed_position_reconciled'])

    def test_fx_zero_purchased_nkd_has_no_unclassified_component(self):
        events=copy.deepcopy(self.fx)
        events[0]['nkd_unit']='0'
        events[1]['nkd_unit']='0'
        r=run_multilot(events,'FX')
        self.assertTrue(r['closed_position_reconciled'])
        self.assertFalse(r['unclassified_components_present'])

    def test_fx_sale_fee_allocated_by_fifo_quantity(self):
        events=copy.deepcopy(self.fx)
        events[3]['fees_rub']='40'
        r=run_multilot(events,'FX')
        self.assertEqual(total(r,'GENERAL_PROFIT_CANDIDATE'),D('35490'))
        self.assertEqual(D(r['net_cash_flow_rub']),D('46085'))
        self.assertEqual(D(r['candidate_component_total_rub']),D('46085'))
        fees=[x for x in r['tax_entries'] if x['component']=='PRICE_REALIZATION_CANDIDATE' and x['event_id']=='S1']
        self.assertEqual([D(x['amount_rub']) for x in fees],[D('11880'),D('11700')])

    def test_fx_partial_fractional_lot_quantity(self):
        events=copy.deepcopy(self.fx)
        events[3]['quantity']='2.5'
        events[5]['quantity']='2.5'
        r=run_multilot(events,'FX')
        self.assertTrue(r['closed_position_reconciled'])
        self.assertEqual([(x['lot_id'],D(x['amount_rub'])) for x in r['tax_entries']
                          if x['event_id']=='S1' and x['component']=='PRICE_REALIZATION_CANDIDATE'],
                         [('L1',D('11900')),('L2',D('2930'))])

    def test_fx_buy_fee_in_tax_cost(self):
        events=copy.deepcopy(self.fx)
        events[0]['fees_rub']='10'
        r=run_multilot(events,'FX')
        self.assertTrue(r['closed_position_reconciled'])
        self.assertEqual(D(r['net_cash_flow_rub']),D('46115'))
        self.assertEqual(total(r,'GENERAL_PROFIT_CANDIDATE'),D('35520'))

    def test_fx_multi_currency_denied(self):
        e=copy.deepcopy(self.fx)
        e[1]['nominal_currency']='EUR';e[1]['settlement_currency']='EUR'
        fail(e,'FX','ISSUE_CURRENCY_MISMATCH')

    def test_fx_foreign_issuer_denied(self):
        e=copy.deepcopy(self.fx)
        e[0]['issuer_class']='FOREIGN'
        fail(e,'FX','FX_INSTRUMENT_NOT_SUPPORTED')

    def test_fx_cash_settlement_rub_denied(self):
        e=copy.deepcopy(self.fx)
        e[0]['settlement_currency']='RUB'
        fail(e,'FX','FX_INSTRUMENT_NOT_SUPPORTED')

    def test_fx_rate_zero_denied(self):
        e=copy.deepcopy(self.fx)
        e[2]['rub_per_nominal_currency']='0'
        with self.assertRaises(ValueError): run_multilot(e,'FX')

    def test_fx_index_event_denied(self):
        e=copy.deepcopy(self.fx)
        e.insert(2,{'id':'I1','date':'2026-01-25','type':'INDEX','security_id':'SYNTH-RU-USD-MULTI','indexed_nominal_unit':'1010'})
        fail(e,'FX','UNSUPPORTED_INSTRUMENT_OR_EVENT')

    def test_ofz_index_after_first_lot_not_second(self):
        r=run_multilot(self.ofz,'OFZ_IN')
        entries=[x for x in r['tax_entries'] if x['component']=='INDEXATION_INTEREST_CANDIDATE']
        self.assertEqual([(x['event_id'],x['lot_id'],D(x['amount_rub'])) for x in entries],
                         [('I1','L1',D('20')),('I2','L2',D('20'))])

    def test_ofz_lifecycle_cash_reconciles(self):
        r=run_multilot(self.ofz,'OFZ_IN')
        self.assertTrue(r['closed_position_reconciled'])
        self.assertEqual(D(r['net_cash_flow_rub']),D('113'))
        self.assertEqual(D(r['candidate_component_total_rub']),D('113'))
        self.assertEqual(total(r,'SPECIAL_INTEREST_CANDIDATE'),D('104'))
        self.assertEqual(total(r,'GENERAL_PROFIT_CANDIDATE'),D('9'))
        self.assertFalse(r['unclassified_components_present'])

    def test_ofz_sale_removes_first_lot_and_part_of_second(self):
        r=run_multilot(self.ofz[:5],'OFZ_IN')
        self.assertFalse(r['closed_position_reconciled'])
        self.assertEqual([(p['lot_id'],p['units']) for p in r['positions']],[('L2','2')])
        self.assertEqual(D(r['positions'][0]['recognized_indexation_unit']),D('0'))

    def test_ofz_buy_after_index_must_use_indexed_nominal(self):
        e=copy.deepcopy(self.ofz)
        e[2]['nominal_unit']='1000'
        fail(e,'OFZ_IN','NOMINAL_AT_PURCHASE_MISMATCH')

    def test_ofz_negative_indexation_hard_stop(self):
        e=copy.deepcopy(self.ofz)
        e[6]['indexed_nominal_unit']='1005'
        fail(e,'OFZ_IN','NEGATIVE_INDEXATION_REVIEW')

    def test_ofz_price_result_excludes_already_recognized_index(self):
        r=run_multilot(self.ofz,'OFZ_IN')
        rows=[x for x in r['tax_entries'] if x['component']=='PRICE_REALIZATION_CANDIDATE']
        self.assertEqual([(x['event_id'],x['lot_id'],D(x['amount_rub'])) for x in rows],
                         [('S1','L1',D('10')),('S1','L2',D('3')),('R1','L2',D('-4'))])

    def test_ofz_coupon_only_remaining_units_after_sale(self):
        r=run_multilot(self.ofz[:6],'OFZ_IN')
        row=next(x for x in r['cash_flows'] if x['event_id']=='C1')
        self.assertEqual(D(row['cash_flow_rub']),D('40'))

    def test_ofz_redeem_with_unpaid_coupon_blocks(self):
        e=copy.deepcopy(self.ofz)
        e.pop(5)
        fail(e,'OFZ_IN','FINAL_COUPON_NOT_SETTLED')

    def test_ofz_partial_redemption_blocks(self):
        e=copy.deepcopy(self.ofz)
        e[-1]['quantity']='1'
        fail(e,'OFZ_IN','PARTIAL_REDEMPTION_UNSUPPORTED')

    def test_ofz_no_index_before_purchase(self):
        e=copy.deepcopy(self.ofz)
        e[1]['date']='2026-01-09'
        with self.assertRaises(ValueError):run_multilot(e,'OFZ_IN')

    def test_ofz_second_coupon_same_period_blocks(self):
        e=copy.deepcopy(self.ofz)
        clone=copy.deepcopy(e[5]);clone['id']='C1-again';clone['date']='2026-02-16'
        e.insert(6,clone)
        fail(e,'OFZ_IN','COUPON_PERIOD_ALREADY_CLOSED')

    def test_ofz_buy_after_redemption_blocks(self):
        e=copy.deepcopy(self.ofz)
        clone=copy.deepcopy(e[2]);clone['id']='B3';clone['lot_id']='L3';clone['date']='2026-03-05';clone['nominal_unit']='1020'
        e.append(clone)
        fail(e,'OFZ_IN','ISSUE_ALREADY_REDEEMED')

    def test_duplicate_lot_ids_across_closed_lots_denied(self):
        e=copy.deepcopy(self.ofz)
        e[2]['lot_id']='L1'
        with self.assertRaises(ValueError):run_multilot(e,'OFZ_IN')

    def test_insufficient_fifo_inventory_denied(self):
        e=copy.deepcopy(self.fx)
        e[3]['quantity']='6'
        with self.assertRaises(ValueError):run_multilot(e,'FX')

    def test_multi_issue_mixed_issuer_denied(self):
        e=copy.deepcopy(self.fx)
        e[1]['security_id']='SECOND-ISIN'
        fail(e,'FX','MULTIPLE_SECURITIES_NOT_SUPPORTED')

    def test_chronological_order_enforced(self):
        e=copy.deepcopy(self.fx)
        e[2]['date']='2026-01-01'
        with self.assertRaises(ValueError):run_multilot(e,'FX')

    def test_duplicate_event_id_enforced(self):
        e=copy.deepcopy(self.fx)
        e[3]['id']='A1'
        with self.assertRaises(ValueError):run_multilot(e,'FX')

    def test_atomic_failed_event_does_not_corrupt_open_position(self):
        ledger=MultiLotBondLedger('FX')
        for event in self.fx[:3]:ledger.apply(event)
        before=ledger.report()
        bad=copy.deepcopy(self.fx[3]);bad['nkd_unit']='10'
        with self.assertRaises(LedgerEvidenceRequired):ledger.apply(bad)
        after=ledger.report()
        self.assertEqual(after,before)
        ledger.apply(self.fx[3])
        self.assertEqual(len(ledger.applied_ids),4)

    def test_negative_and_float_inputs_denied(self):
        e=copy.deepcopy(self.fx)
        e[0]['quantity']=-2
        with self.assertRaises(ValueError):run_multilot(e,'FX')
        e=copy.deepcopy(self.fx)
        e[0]['clean_price_unit']=1000.0
        with self.assertRaises(ValueError):run_multilot(e,'FX')

    def test_open_partial_holdings_not_reported_as_closed(self):
        r=run_multilot(self.fx[:2],'FX')
        self.assertFalse(r['closed_position_reconciled'])
        self.assertEqual(len(r['positions']),2)
        self.assertEqual(r['final_tax_amount_rub'],None)

    def test_backwards_compatible_fx_single_lot_fixture(self):
        buy=copy.deepcopy(self.fx[0]);buy['quantity']='1'
        buy['id']='B'
        accr={'id':'A','date':'2026-01-31','type':'ACCRUE','security_id':buy['security_id'],
              'coupon_period':'C1','nkd_unit':'30','rub_per_nominal_currency':'92'}
        cp={'id':'C','date':'2026-02-15','type':'COUPON','security_id':buy['security_id'],
            'coupon_period':'C1','coupon_unit':'60','rub_per_nominal_currency':'95'}
        sale={'id':'S','date':'2026-03-15','type':'SELL','security_id':buy['security_id'],
              'coupon_period':'C2','quantity':'1','clean_price_unit':'1020',
              'nkd_unit':'0','rub_per_nominal_currency':'100'}
        r=run_multilot([buy,accr,cp,sale],'FX')
        self.assertEqual(D(r['net_cash_flow_rub']),D('15900'))
        self.assertEqual(D(r['candidate_component_total_rub']),D('15900'))

    def test_backwards_compatible_ofz_single_lot_fixture(self):
        buy=copy.deepcopy(self.ofz[0]);buy['quantity']='1'
        idx1={'id':'I1','date':'2026-01-31','type':'INDEX','security_id':buy['security_id'],
              'indexed_nominal_unit':'1010'}
        cp={'id':'C','date':'2026-02-15','type':'COUPON','security_id':buy['security_id'],
            'coupon_period':'C1','coupon_unit':'20'}
        idx2={'id':'I2','date':'2026-02-28','type':'INDEX','security_id':buy['security_id'],
              'indexed_nominal_unit':'1020'}
        red={'id':'R','date':'2026-03-01','type':'REDEEM','security_id':buy['security_id']}
        r=run_multilot([buy,idx1,cp,idx2,red],'OFZ_IN')
        self.assertEqual(D(r['net_cash_flow_rub']),D('40'))
        self.assertEqual(D(r['candidate_component_total_rub']),D('40'))

    def test_unverified_flag_per_tax_entry(self):
        r=run_multilot(self.ofz,'OFZ_IN')
        self.assertTrue(all(x['approved_tax_amount_rub'] is None for x in r['tax_entries']))
        self.assertTrue(all(x['verification_status']!='VERIFIED' for x in r['tax_entries']))
        self.assertTrue(all(x['rule_id'] and x['source_reference'] for x in r['tax_entries']))


if __name__=='__main__': unittest.main()
