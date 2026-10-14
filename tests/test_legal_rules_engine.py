"""Offline legal rules engine: documentary gates, dates, conditions and rate discipline.

These tests DO NOT assert that the NК РФ texts are legally correct or current.
"""
import copy
import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from legal_rules_engine import assess_report
from treasury_tax_engine import run_unified, safe_run, load_catalog


def fixture(name):
    return json.loads((ROOT/'examples'/name).read_text(encoding='utf-8'))


def example_row(rule_id='BND-OFZ-INT-20',base='SPECIAL_INTEREST_CANDIDATE',
                amount='42',day='2026-02-15',kind='INTEREST_ACCRUAL'):
    return {'event_id':'C1','event_date':day,'lot_id':'L1','rule_id':rule_id,
            'component':kind,'candidate_tax_base':base,'amount_rub':amount}


def review_report(row):
    return {'accounting':{'tax_components':[row]},'legal_validation':{},'tax_outcome':{}}


class LegalRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=load_catalog()
        cls.catalog_index={r['id']:r for r in cls.catalog['rules']}

    def assess(self,row,review=None):
        return assess_report(review_report(row), self.catalog, review)

    def test_no_evidence_produces_legal_document_requests(self):
        r=self.assess(example_row())
        self.assertEqual(r['legal_rules']['status'],'MISSING_EVIDENCE')
        codes={x['code'] for x in r['legal_rules']['document_requests']}
        self.assertIn('MISSING_DATED_LAW_TEXT',codes)
        self.assertIn('MISSING_AMENDMENT_CHECK',codes)
        self.assertIn('MISSING_APPLICABILITY_CONDITION',codes)
        self.assertFalse(r['legal_rules']['law_checked_live_by_code'])
        self.assertIsNone(r['tax_outcome']['approved_tax_amount_rub'])

    def test_conditions_are_specific_not_generic(self):
        r=self.assess(example_row('BND-CORP-RUB-INT-20'))
        texts=[x['request'] for x in r['legal_rules']['document_requests']]
        self.assertTrue(any('EACH recognition date' in t for t in texts))
        self.assertTrue(any('ruble nominal' in t.lower() for t in texts))

    def test_hardcoded_20_percent_and_conditional_example(self):
        a=self.assess(example_row())['legal_rules']['evaluations'][0]
        self.assertEqual(a['stored_snapshot_rate_percent'],'20')
        self.assertEqual(a['conditional_arithmetic_tax_effect_rub'],'8.4')
        self.assertFalse(a['legally_validated'])
        self.assertIsNone(a['approved_tax_amount_rub'])

    def test_hardcoded_25_percent_on_price_candidate(self):
        row=example_row('BND-GEN-25','GENERAL_PROFIT_CANDIDATE','100',kind='PRICE_REALIZATION')
        a=self.assess(row)['legal_rules']['evaluations'][0]
        self.assertEqual(a['conditional_arithmetic_tax_effect_rub'],'25')

    def test_rate_is_never_inferred_from_interest_accounting_rule(self):
        row=example_row('BND-NKD-LEDGER','GENERAL_INTEREST_CANDIDATE','300')
        r=self.assess(row)
        a=r['legal_rules']['evaluations'][0]
        self.assertIsNone(a['rate_rule_id'])
        self.assertIsNone(a['conditional_arithmetic_tax_effect_rub'])
        self.assertIn('RATE_RULE_REQUIRED',a['missing_evidence_codes'])

    def test_explicit_rate_selection_still_provisional(self):
        row=example_row('BND-NKD-LEDGER','GENERAL_INTEREST_CANDIDATE','300')
        review={'rate_selections':[{'row_key':'C1|L1|INTEREST_ACCRUAL',
                                    'rate_rule_id':'BND-GEN-25'}]}
        r=self.assess(row,review)
        a=r['legal_rules']['evaluations'][0]
        self.assertEqual(a['rate_rule_id'],'BND-GEN-25')
        self.assertEqual(a['conditional_arithmetic_tax_effect_rub'],'75')
        self.assertEqual(a['status'],'MISSING_EVIDENCE')
        self.assertTrue(any(x['rule_id']=='BND-NKD-LEDGER' for x in r['legal_rules']['document_requests']))

    def test_rate_selection_wrong_tax_base_is_blocked(self):
        row=example_row('BND-NKD-LEDGER','SPECIAL_INTEREST_CANDIDATE','100')
        r=self.assess(row,{'rate_selections':[{'row_key':'C1|L1|INTEREST_ACCRUAL',
                                               'rate_rule_id':'BND-GEN-25'}]})
        a=r['legal_rules']['evaluations'][0]
        self.assertIsNone(a['rate_rule_id'])
        self.assertIn('RATE_BASE_CONFLICT',a['missing_evidence_codes'])

    def test_explicit_rate_selection_cannot_override_direct_rate(self):
        row=example_row()
        r=self.assess(row,{'rate_selections':[{'row_key':'C1|L1|INTEREST_ACCRUAL',
                                               'rate_rule_id':'BND-CORP-RUB-INT-20'}]})
        a=r['legal_rules']['evaluations'][0]
        self.assertIn('CONFLICTING_DIRECT_RATE',a['missing_evidence_codes'])

    def test_loss_never_generates_automatic_tax_benefit(self):
        row=example_row('BND-GEN-25','GENERAL_PROFIT_CANDIDATE','-50')
        a=self.assess(row)['legal_rules']['evaluations'][0]
        self.assertIsNone(a['conditional_arithmetic_tax_effect_rub'])
        self.assertIn('LOSS_UTILIZATION_NOT_VERIFIED',a['missing_evidence_codes'])

    def test_unclassified_fx_nkd_unrated(self):
        row=example_row('BND-NKD-LEDGER','UNCLASSIFIED_NOT_TAX_BASE','100')
        a=self.assess(row)['legal_rules']['evaluations'][0]
        self.assertEqual(a['status'],'UNCLASSIFIED_REQUIRES_DOCUMENTS')
        self.assertIsNone(a['conditional_arithmetic_tax_effect_rub'])

    def test_historical_rate_2024_is_not_applied(self):
        row=example_row(day='2024-01-10')
        a=self.assess(row)['legal_rules']['evaluations'][0]
        self.assertEqual(a['status'],'HISTORICAL_EDITION_REQUIRED')
        self.assertIsNone(a['conditional_arithmetic_tax_effect_rub'])

    def test_future_edition_expiration_flag(self):
        cat=copy.deepcopy(self.catalog)
        rule=next(r for r in cat['rules'] if r['id']=='BND-OFZ-INT-20')
        rule['valid_to']='2026-02-01'
        r=assess_report(review_report(example_row()),cat)
        self.assertEqual(r['legal_rules']['evaluations'][0]['status'],'HISTORICAL_EDITION_REQUIRED')

    def test_amendment_signal_blocks_outdated_rule(self):
        review={'amendment_checks':[{'source_id':'NK-RU-284', 'event_date':'2026-02-15',
                                     'change_status':'changed',
                                     'supporting_document':'Amendment № X'}]}
        r=self.assess(example_row(),review)
        self.assertEqual(r['legal_rules']['status'],'REVALIDATION_REQUIRED')
        self.assertEqual(r['legal_rules']['evaluations'][0]['status'],'REVALIDATION_REQUIRED')
        self.assertIn('RULE_REVALIDATION_REQUIRED',
                      r['legal_rules']['evaluations'][0]['missing_evidence_codes'])

    def test_unchanged_claim_is_not_accepted_without_provenance(self):
        review={'amendment_checks':[{'source_id':'NK-RU-284', 'event_date':'2026-02-15',
                                     'change_status':'unchanged'}]}
        a=self.assess(example_row(),review)['legal_rules']['evaluations'][0]
        self.assertIn('AMENDMENT_PROVENANCE_MISSING',a['missing_evidence_codes'])

    def test_law_document_wrong_date_not_counted(self):
        review={'law_documents':[{'source_id':'NK-RU-284','effective_from':'2026-03-01',
                                  'document_locator':'source.pdf','full_text_available':True}]}
        a=self.assess(example_row(),review)['legal_rules']['evaluations'][0]
        self.assertIn('MISSING_DATED_LAW_TEXT',a['missing_evidence_codes'])

    def test_even_all_declared_evidence_does_not_verify_law(self):
        row=example_row()
        source=self.catalog_index['BND-OFZ-INT-20']
        conditions=[{'rule_id':source['id'],'event_date':row['event_date'],
                     'condition':p,'supporting_document':'user-note.pdf'}
                    for p in source['required_conditions']]
        review={
          'law_documents':[{'source_id':'NK-RU-284','effective_from':'2025-01-01',
                            'document_locator':'law.pdf','full_text_available':True,
                            'official_publication_id':'synthetic-test-ref','pinpoint':'ст.284 п.4',
                            'checked_at':'2026-10-14'}],
          'amendment_checks':[{'source_id':'NK-RU-284','event_date':'2026-02-15',
                               'change_status':'unchanged','supporting_document':'audit.pdf',
                               'checked_at':'2026-10-14','reviewed_through':'2026-10-14'}],
          'condition_evidence':conditions}
        r=self.assess(row,review)
        self.assertEqual(r['legal_rules']['status'],'DOCUMENTS_SUPPLIED_REVIEW_REQUIRED')
        self.assertFalse(r['legal_rules']['current_law_confirmed'])
        self.assertEqual(r['legal_rules']['evaluations'][0]['status'],
                         'DOCUMENTS_SUPPLIED_REVIEW_REQUIRED')
        self.assertEqual(r['legal_rules']['document_requests'],[])
        self.assertIsNone(r['tax_outcome']['approved_tax_amount_rub'])

    def test_amendment_checks_wrong_event_date_do_not_count(self):
        review={'amendment_checks':[{'source_id':'NK-RU-284','event_date':'2026-02-14',
                                     'change_status':'unchanged','supporting_document':'audit.pdf'}]}
        a=self.assess(example_row(),review)['legal_rules']['evaluations'][0]
        self.assertIn('MISSING_AMENDMENT_CHECK',a['missing_evidence_codes'])

    def test_conditions_do_not_transfer_across_events(self):
        rule=self.catalog_index['BND-OFZ-INT-20']
        review={'condition_evidence':[{'rule_id':rule['id'],'event_date':'2026-02-14',
                                       'condition':name,'supporting_document':'data.pdf'}
                                      for name in rule['required_conditions']]}
        a=self.assess(example_row(),review)['legal_rules']['evaluations'][0]
        self.assertIn('MISSING_APPLICABILITY_CONDITION',a['missing_evidence_codes'])

    def test_hard_stop_rule_rejection(self):
        row=example_row('BND-REPLACEMENT','GENERAL_PROFIT_CANDIDATE')
        a=self.assess(row)['legal_rules']['evaluations'][0]
        self.assertEqual(a['status'],'BLOCKED_HIGH_RISK')

    def test_missing_source_registry_rejected(self):
        row=example_row('BND-WITHHOLDING-NONRESIDENT','UNCLASSIFIED_NOT_TAX_BASE')
        a=self.assess(row)['legal_rules']['evaluations'][0]
        self.assertIn('SOURCE_REGISTRY_GAP',a['missing_evidence_codes'])

    def test_duplicate_selection_invalid(self):
        row=example_row('BND-NKD-LEDGER','GENERAL_INTEREST_CANDIDATE')
        item={'row_key':'C1|L1|INTEREST_ACCRUAL','rate_rule_id':'BND-GEN-25'}
        with self.assertRaises(ValueError):
            self.assess(row,{'rate_selections':[item,item]})

    def test_non_json_floats_denied_in_tax_ledger_rows(self):
        row=example_row(amount=0.1)
        with self.assertRaises(ValueError):self.assess(row)

    def test_full_fx_pipeline_with_document_checklist(self):
        r=run_unified(fixture('fx_multilot_synthetic.json'))
        self.assertEqual(r['accounting']['component_total_rub'],'46125')
        self.assertIn('legal_rules',r)
        self.assertEqual(r['legal_rules']['status'],'MISSING_EVIDENCE')
        self.assertTrue(any(x['code']=='UNCLASSIFIED_COMPONENT' for x in r['legal_rules']['document_requests']))
        self.assertIsNone(r['tax_outcome']['approved_tax_amount_rub'])
        self.assertFalse(r['legal_rules']['law_checked_live_by_code'])

    def test_full_ofzin_pipeline_with_specific_index_sources(self):
        r=run_unified(fixture('ofz_in_multilot_synthetic.json'))
        self.assertEqual(r['accounting']['component_total_rub'],'113')
        self.assertTrue(any(x['original_rule_id']=='BND-INDEXED-OFZ' for x in r['legal_rules']['evaluations']))
        self.assertIsNone(r['tax_outcome']['indicative_total_tax_rub'])

    def test_unified_report_preserves_raw_row_sources(self):
        r=run_unified(fixture('fx_multilot_synthetic.json'))
        row=r['accounting']['tax_components'][0]
        self.assertIn('legal_pinpoint',row)
        self.assertIn('required_applicability_conditions',row)

    def test_safe_run_invalid_evidence_is_invalid_input(self):
        input=fixture('fx_multilot_synthetic.json')
        input['legal_review']={'law_documents':{}}
        r=safe_run(input)
        self.assertEqual(r['status'],'INVALID_INPUT')
        self.assertIsNone(r['approved_tax_amount_rub'])

    def test_duplicate_rule_catalog_is_invalid(self):
        cat=copy.deepcopy(self.catalog)
        cat['rules'].append(copy.deepcopy(cat['rules'][0]))
        with self.assertRaises(ValueError): assess_report(review_report(example_row()),cat)


if __name__=='__main__':unittest.main()