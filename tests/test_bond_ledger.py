import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from bond_ledger import run_ledger, LedgerBlocked

CATALOG={'rules':[
    {'id':'BND-OFZ-INT-20', 'rate_percent':20, 'tax_base':'separate_interest',
     'readiness':'normative_checked', 'valid_from':'2025-01-01', 'valid_to':None,
     'primary_provision':'НК РФ ст. 284 п. 4'},
    {'id':'BND-GEN-25', 'rate_percent':25, 'tax_base':'general_profit',
     'readiness':'normative_checked', 'valid_from':'2025-01-01', 'valid_to':None,
     'primary_provision':'НК РФ ст. 284 п. 1'},
    {'id':'BND-SPECIAL-STOP', 'rate_percent':None, 'tax_base':'unresolved',
     'readiness':'hard_stop', 'valid_from':None, 'valid_to':None,
     'primary_provision':'Requires verification'}]}


def e(id, day, type, **kwargs):
    return {'id':id, 'date':day, 'type':type, 'security_id':'BOND001', **kwargs}


def buy(id, day, qty='1', clean='980', nkd='30', principal='1000', fees='0', period='C1'):
    return e(id,day,'BUY',lot_id=id,quantity=qty,clean_price_unit=clean,
             nkd_unit=nkd,principal_unit=principal,fees_rub=fees,
             coupon_period=period,currency='RUB',traded_market_status='TRADED',
             coupon_rule_id='BND-OFZ-INT-20')


class BondLifecycleTests(unittest.TestCase):
    def test_T01_purchase_month_end_coupon_sale(self):
        events=[buy('b','2026-01-10'),
                e('a1','2026-01-31','ACCRUE',nkd_unit='45',coupon_period='C1'),
                e('c','2026-02-15','COUPON',coupon_unit='60',coupon_period='C1'),
                e('a2','2026-02-28','ACCRUE',nkd_unit='10',coupon_period='C2'),
                e('s','2026-03-02','SELL',quantity='1',clean_price_unit='990',
                  nkd_unit='12',coupon_period='C2',fees_rub='0')]
        r=run_ledger(events,CATALOG)
        self.assertEqual([D(v['amount_rub']) for v in r['tax_entries']],
                         [D('15'),D('15'),D('10'),D('2'),D('10')])
        self.assertEqual(r['recognized_result_rub'],'52')
        self.assertEqual(r['net_cash_flow_rub'],'52')
        self.assertTrue(r['closed_position_reconciled'])
        self.assertEqual(r['tax_base_candidate_totals_rub'],
                         {'separate_interest':'42','general_profit':'10'})
        self.assertIsNone(r['approved_tax_amount_rub'])
        self.assertEqual({x['legal_status'] for x in r['tax_entries']},
                         {'UNVERIFIED_LEGAL_EDITION'})

    def test_T08_amortization_and_redemption(self):
        r=run_ledger([buy('b','2026-01-10',qty='10',clean='960',nkd='0'),
          e('p1','2026-02-01','AMORTIZE',principal_paid_unit='400'),
          e('p2','2026-03-01','REDEEM')],CATALOG)
        self.assertEqual([D(x['amount_rub']) for x in r['tax_entries']],
                         [D('160'),D('240')])
        self.assertEqual(r['recognized_result_rub'],'400')
        self.assertEqual(r['net_cash_flow_rub'],'400')
        self.assertEqual(r['positions'],[])

    def test_T12_fifo_two_lots(self):
        r=run_ledger([buy('b1','2026-01-10',qty='10',clean='940',nkd='0'),
                      buy('b2','2026-01-11',qty='10',clean='980',nkd='0'),
          e('s1','2026-02-01','SELL',quantity='10',clean_price_unit='970',
            nkd_unit='0',coupon_period='C1')],CATALOG)
        self.assertEqual(r['recognized_result_rub'],'300')
        self.assertEqual(r['positions'][0]['lot_id'],'b2')
        self.assertEqual(r['positions'][0]['remaining_tax_cost_rub'],'9800')
        self.assertFalse(r['closed_position_reconciled'])

    def test_partial_sale_and_remaining_accrual(self):
        r=run_ledger([buy('b','2026-01-10',qty='2',clean='1000',nkd='10'),
          e('a','2026-01-31','ACCRUE',nkd_unit='20',coupon_period='C1'),
          e('s1','2026-02-01','SELL',quantity='1',clean_price_unit='1010',
            nkd_unit='25',coupon_period='C1'),
          e('c','2026-02-15','COUPON',coupon_unit='40',coupon_period='C1'),
          e('s2','2026-03-01','SELL',quantity='1',clean_price_unit='1000',
            nkd_unit='0',coupon_period='C2')],CATALOG)
        self.assertEqual(r['recognized_result_rub'],'55')
        self.assertEqual(r['net_cash_flow_rub'],'55')
        # earned interest 15 on sold lot, 30 on retained lot; clean gain 10
        self.assertEqual(r['tax_base_candidate_totals_rub']['separate_interest'],'45')
        self.assertEqual(r['tax_base_candidate_totals_rub']['general_profit'],'10')

    def test_buy_fee_then_sale_fee_reconcile(self):
        r=run_ledger([buy('b','2026-01-01',qty='2',clean='100',nkd='0',fees='2'),
          e('s','2026-02-01','SELL',quantity='2',clean_price_unit='110',
            nkd_unit='0',coupon_period='C1',fees_rub='4')],CATALOG)
        self.assertEqual(r['recognized_result_rub'],'14')
        self.assertEqual(r['net_cash_flow_rub'],'14')

    def test_negative_result_is_never_approved_tax_benefit(self):
        r=run_ledger([buy('b','2026-01-01',qty='1',clean='1000',nkd='0'),
          e('s','2026-02-01','SELL',quantity='1',clean_price_unit='900',
            nkd_unit='0',coupon_period='C1')],CATALOG)
        self.assertEqual(r['recognized_result_rub'],'-100')
        self.assertIsNone(r['approved_tax_amount_rub'])

    def test_guard_unrecognized_event(self):
        with self.assertRaises(LedgerBlocked):
            run_ledger([buy('b','2026-01-01'),
                        e('wd','2026-02-01','WRITE_DOWN')],CATALOG)

    def test_guard_issue_status(self):
        b=buy('b','2026-01-01'); b['traded_market_status']='UNKNOWN'
        with self.assertRaises(LedgerBlocked):run_ledger([b],CATALOG)

    def test_guard_currency(self):
        b=buy('b','2026-01-01'); b['currency']='USD'
        with self.assertRaises(LedgerBlocked):run_ledger([b],CATALOG)

    def test_guard_historical_edition(self):
        with self.assertRaises(LedgerBlocked):run_ledger([buy('b','2024-01-01')],CATALOG)

    def test_guard_negative_nkd(self):
        with self.assertRaises(LedgerBlocked):run_ledger([buy('b','2026-01-01'),
           e('a','2026-01-31','ACCRUE',nkd_unit='5',coupon_period='C1')],CATALOG)

    def test_guard_double_coupon_same_period(self):
        with self.assertRaises(LedgerBlocked):run_ledger([buy('b','2026-01-01',nkd='0'),
          e('c1','2026-02-01','COUPON',coupon_unit='40',coupon_period='C1'),
          e('c2','2026-02-02','COUPON',coupon_unit='40',coupon_period='C1')],CATALOG)

    def test_guard_excess_sale(self):
        with self.assertRaises(ValueError):run_ledger([buy('b','2026-01-01'),
          e('s','2026-02-01','SELL',quantity='2',clean_price_unit='1000',
            nkd_unit='40',coupon_period='C1')],CATALOG)

    def test_guard_out_of_order(self):
        with self.assertRaises(ValueError):run_ledger([buy('b','2026-02-01'),
          e('a','2026-01-31','ACCRUE',nkd_unit='35',coupon_period='C1')],CATALOG)

    def test_guard_redeem_with_unsettled_coupon(self):
        with self.assertRaises(LedgerBlocked):run_ledger([buy('b','2026-01-01',nkd='30'),
          e('r','2026-02-01','REDEEM')],CATALOG)

    def test_guard_duplicate_id(self):
        with self.assertRaises(ValueError):run_ledger([buy('b','2026-01-01'),
          e('b','2026-02-01','ACCRUE',nkd_unit='40',coupon_period='C1')],CATALOG)

    def test_guard_different_issue(self):
        b=buy('b','2026-01-01'); s=e('s','2026-02-01','REDEEM')
        s['security_id']='DIFFERENT'
        with self.assertRaises(LedgerBlocked):run_ledger([b,s],CATALOG)

    def test_guard_principal_mismatch_between_lots(self):
        with self.assertRaises(LedgerBlocked):
            run_ledger([buy('b1','2026-01-01',principal='1000'),
                        buy('b2','2026-01-02',principal='900')], CATALOG)

    def test_unknown_coupon_rule_rejected(self):
        b=buy('b','2026-01-01');b['coupon_rule_id']='INVENTED'
        with self.assertRaises(LedgerBlocked):run_ledger([b],CATALOG)

    def test_complex_rule_forbidden(self):
        b=buy('b','2026-01-01');b['coupon_rule_id']='BND-SPECIAL-STOP'
        with self.assertRaises(LedgerBlocked):run_ledger([b],CATALOG)

    def test_missing_fee_and_empty_events(self):
        with self.assertRaises(ValueError):run_ledger([],CATALOG)
        b=buy('b','2026-01-01');b['fees_rub']='NaN'
        with self.assertRaises(ValueError):run_ledger([b],CATALOG)


if __name__=='__main__': unittest.main()