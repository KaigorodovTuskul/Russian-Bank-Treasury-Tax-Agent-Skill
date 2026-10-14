import copy
import json
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from advanced_bond_ledger import LegalEvidenceRequired, run_advanced


def fx_buy(**changes):
    x={'id':'BUY','date':'2026-01-10','type':'BUY','security_id':'SYNTH-RU-USD-01',
       'lot_id':'LOT-1','quantity':'1','clean_price_unit':'1000',
       'nkd_unit':'20','fees_rub':'0','nominal_unit':'1000','rub_per_nominal_currency':'90',
       'nominal_currency':'USD','settlement_currency':'USD',
       'issuer_law':'RU','issuer_class':'RU_CORPORATE','coupon_recognition_method':'ACCRUAL','coupon_period':'C1'}
    x.update(changes)
    return x


def fx_sample():
    return [fx_buy(),
            {'id':'MONTH','date':'2026-01-31','type':'ACCRUE','security_id':'SYNTH-RU-USD-01',
             'coupon_period':'C1','nkd_unit':'30','rub_per_nominal_currency':'92'},
            {'id':'COUP','date':'2026-02-15','type':'COUPON','security_id':'SYNTH-RU-USD-01',
             'coupon_period':'C1','coupon_unit':'60','rub_per_nominal_currency':'95'},
            {'id':'SELL','date':'2026-03-15','type':'SELL','security_id':'SYNTH-RU-USD-01',
             'quantity':'1','clean_price_unit':'1020','nkd_unit':'0','rub_per_nominal_currency':'100'}]


def indexed_sample():
    return [{'id':'BUY','date':'2026-01-10','type':'BUY','security_id':'SYNTH-OFZIN',
            'lot_id':'LOT-1','quantity':'1','clean_price_unit':'1000','nkd_unit':'0',
            'nominal_unit':'1000','nominal_currency':'RUB','security_kind':'OFZ_IN'},
            {'id':'INDEX1','date':'2026-01-31','type':'INDEX','security_id':'SYNTH-OFZIN',
             'indexed_nominal_unit':'1010'},
            {'id':'COUP','date':'2026-02-15','type':'COUPON','security_id':'SYNTH-OFZIN',
             'coupon_period':'C1','coupon_unit':'20'},
            {'id':'INDEX2','date':'2026-02-28','type':'INDEX','security_id':'SYNTH-OFZIN',
             'indexed_nominal_unit':'1020'},
            {'id':'REDEEM','date':'2026-03-01','type':'REDEEM','security_id':'SYNTH-OFZIN'}]


def sums(report):
    return {k:D(v) for k,v in report['candidate_base_totals_rub'].items()}


class AdvancedBondLedgerTests(unittest.TestCase):
    def test_fx_full_lifecycle_and_unclassified_nkd(self):
        x=run_advanced(fx_sample(),'FX')
        self.assertTrue(x['closed_position_reconciled'])
        self.assertTrue(x['unclassified_components_present'])
        self.assertEqual(D(x['synthetic_cash_total_rub']),D('15900'))
        self.assertEqual(D(x['synthetic_component_total_rub']),D('15900'))
        self.assertEqual(sums(x)['GENERAL_PROFIT_CANDIDATE'],D('12000'))
        self.assertEqual(sums(x)['GENERAL_INTEREST_CANDIDATE'],D('3770'))
        self.assertEqual(sums(x)['GENERAL_FX_CANDIDATE'],D('30'))
        self.assertEqual(sums(x)['UNCLASSIFIED_NOT_TAX_BASE'],D('100'))
        self.assertIsNone(x['final_tax_amount_rub'])

    def test_fx_zero_purchased_nkd_reconcile(self):
        events=fx_sample()
        events[0]['nkd_unit']='0'
        events[1]['nkd_unit']='10'
        events[2]['coupon_unit']='40'
        x=run_advanced(events,'FX')
        self.assertFalse(x['unclassified_components_present'])
        self.assertEqual(D(x['synthetic_cash_total_rub']), D('15800'))
        self.assertEqual(sums(x)['GENERAL_INTEREST_CANDIDATE'],D('3770'))
        self.assertEqual(sums(x)['GENERAL_FX_CANDIDATE'],D('30'))

    def test_fx_no_monthly_revaluation_of_bond_price(self):
        rows=run_advanced(fx_sample(),'FX')['tax_entries']
        self.assertNotIn('FX_BOND_MARK_TO_MARKET', [r['component'] for r in rows])
        self.assertEqual([r['amount_rub'] for r in rows if r['component']=='PRICE_REALIZATION_CANDIDATE'],['12000'])

    def test_fx_redeem_after_coupon(self):
        events=fx_sample()
        events[3]={'id':'REDEEM','date':'2026-03-15','type':'REDEEM',
                   'security_id':'SYNTH-RU-USD-01','rub_per_nominal_currency':'100'}
        x=run_advanced(events,'FX')
        self.assertTrue(x['closed_position_reconciled'])
        self.assertEqual(D(x['synthetic_cash_total_rub']),D('13900'))

    def test_fx_month_end_revalue_only_on_receivable(self):
        events=fx_sample()
        events.insert(2,{'id':'MONTH2','date':'2026-02-01','type':'ACCRUE',
                         'security_id':'SYNTH-RU-USD-01','coupon_period':'C1',
                         'nkd_unit':'30','rub_per_nominal_currency':'93'})
        x=run_advanced(events,'FX')
        self.assertEqual(sums(x)['GENERAL_FX_CANDIDATE'],D('30'))
        self.assertTrue(x['closed_position_reconciled'])

    def test_fx_sale_before_coupon_with_purchased_nkd(self):
        events=fx_sample()[:2]+[{'id':'SELL','date':'2026-02-10','type':'SELL',
                'security_id':'SYNTH-RU-USD-01','quantity':'1','clean_price_unit':'1010',
                'nkd_unit':'40','rub_per_nominal_currency':'94','coupon_period':'C1'}]
        x=run_advanced(events,'FX')
        self.assertTrue(x['closed_position_reconciled'])
        self.assertEqual(D(x['synthetic_cash_total_rub']), D('6900'))
        self.assertTrue(x['unclassified_components_present'])

    def test_fx_unsupported_foreign_issuer(self):
        with self.assertRaisesRegex(LegalEvidenceRequired,'FX_INSTRUMENT_NOT_SUPPORTED'):
            run_advanced([fx_buy(issuer_law='US')],'FX')

    def test_fx_unsupported_ruble_settlement(self):
        with self.assertRaisesRegex(LegalEvidenceRequired,'FX_INSTRUMENT_NOT_SUPPORTED'):
            run_advanced([fx_buy(settlement_currency='RUB')],'FX')

    def test_fx_unsupported_special_recognition_method(self):
        with self.assertRaises(LegalEvidenceRequired):
            run_advanced([fx_buy(coupon_recognition_method='CASH')],'FX')

    def test_fx_bad_rate(self):
        with self.assertRaises(ValueError):
            run_advanced([fx_buy(rub_per_nominal_currency='NaN')],'FX')
        with self.assertRaises(ValueError):
            run_advanced([fx_buy(rub_per_nominal_currency='0')],'FX')

    def test_indexed_full_lifecycle_no_double_count(self):
        x=run_advanced(indexed_sample(),'OFZ_IN')
        self.assertTrue(x['closed_position_reconciled'])
        self.assertEqual(D(x['synthetic_cash_total_rub']),D('40'))
        self.assertEqual(sums(x)['SPECIAL_INTEREST_CANDIDATE'],D('40'))
        self.assertNotIn('GENERAL_PROFIT_CANDIDATE',sums(x))
        self.assertIsNone(x['final_tax_amount_rub'])

    def test_indexed_discount_remains_price_result(self):
        events=indexed_sample()
        events[0]['clean_price_unit']='950'
        x=run_advanced(events,'OFZ_IN')
        self.assertTrue(x['closed_position_reconciled'])
        self.assertEqual(sums(x)['GENERAL_PROFIT_CANDIDATE'],D('50'))
        self.assertEqual(D(x['synthetic_cash_total_rub']),D('90'))

    def test_indexed_sale_higher_clean_price(self):
        events=indexed_sample()
        events[-1]={'id':'SELL','date':'2026-03-01','type':'SELL',
                    'security_id':'SYNTH-OFZIN','quantity':'1',
                    'clean_price_unit':'1040','nkd_unit':'0'}
        x=run_advanced(events,'OFZ_IN')
        self.assertEqual(sums(x)['GENERAL_PROFIT_CANDIDATE'],D('20'))
        self.assertTrue(x['closed_position_reconciled'])

    def test_indexed_negative_indexation_blocks(self):
        events=indexed_sample()
        events[1]['indexed_nominal_unit']='995'
        with self.assertRaisesRegex(LegalEvidenceRequired,'NEGATIVE_OFZ_INDEXATION_REVIEW'):
            run_advanced(events,'OFZ_IN')

    def test_indexed_invalid_instrument(self):
        events=indexed_sample();events[0]['security_kind']='CORPORATE'
        with self.assertRaises(LegalEvidenceRequired):
            run_advanced(events,'OFZ_IN')

    def test_duplicate_event_id_rejected(self):
        events=indexed_sample();events[1]['id']='BUY'
        with self.assertRaises(ValueError):run_advanced(events,'OFZ_IN')

    def test_dates_monotonic(self):
        events=indexed_sample();events[1]['date']='2026-01-01'
        with self.assertRaises(ValueError):run_advanced(events,'OFZ_IN')

    def test_partial_sale_blocked(self):
        events=fx_sample();events[-1]['quantity']='0.5'
        with self.assertRaises(LegalEvidenceRequired):run_advanced(events,'FX')

    def test_two_lots_blocked(self):
        events=indexed_sample(); events.insert(1,dict(events[0],id='BUY2',lot_id='LOT2',date='2026-01-11'))
        with self.assertRaises(LegalEvidenceRequired):run_advanced(events,'OFZ_IN')

    def test_missing_coupon_nkd_on_sale_blocks(self):
        events=fx_sample()
        events=events[:2]+[{'id':'SELL','date':'2026-02-10','type':'SELL',
                'security_id':'SYNTH-RU-USD-01','quantity':'1','clean_price_unit':'1010',
                'rub_per_nominal_currency':'94','coupon_period':'C1'}]
        with self.assertRaisesRegex(LegalEvidenceRequired,'NKD_OMITTED_ON_DISPOSAL'):
            run_advanced(events,'FX')

    def test_unsettled_coupon_at_redemption_blocks(self):
        events=fx_sample()[:2]+[{'id':'REDEEM','date':'2026-03-01','type':'REDEEM',
                'security_id':'SYNTH-RU-USD-01','rub_per_nominal_currency':'100'}]
        with self.assertRaises(LegalEvidenceRequired):run_advanced(events,'FX')

    def test_unknown_complex_event_blocks(self):
        events=indexed_sample()
        events[1]['type']='WRITE_DOWN'
        with self.assertRaises(LegalEvidenceRequired):run_advanced(events,'OFZ_IN')

    def test_open_position_never_assumes_reconciliation(self):
        x=run_advanced(indexed_sample()[:3],'OFZ_IN')
        self.assertFalse(x['closed_position_reconciled'])
        self.assertEqual(x['open_quantity'],'1')

    def test_input_sequence_required(self):
        with self.assertRaises(ValueError):run_advanced([], 'FX')
        with self.assertRaises(ValueError):run_advanced([{'type':'BUY','date':'2026-01-01','id':'1'}],'INVALID')


if __name__=='__main__':unittest.main()