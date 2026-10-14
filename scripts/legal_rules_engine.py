#!/usr/bin/env python3
"""Conservative, offline legal-evidence gate for synthetic bond tax ledgers.

This software DOES NOT retrieve, authenticate or validate Russian legislation.
It records hard-coded rule provenance, evidence gaps, amendment signals and
precise document requests. No supplied metadata can approve tax liability.
"""
from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

SCHEMA = '0.4.0'
KNOWN_BASES = {
    'SPECIAL_INTEREST_CANDIDATE': 'separate_interest',
    'GENERAL_PROFIT_CANDIDATE': 'general_profit',
    'GENERAL_INTEREST_CANDIDATE': 'general_profit',
    'GENERAL_FX_CANDIDATE': 'general_profit',
}
GENERAL_RATE_IDS = {'BND-GEN-25'}
RATE_CLASSES = {
    'SPECIAL_INTEREST_CANDIDATE': 'special_interest',
    'GENERAL_PROFIT_CANDIDATE': 'general_profit',
    'GENERAL_INTEREST_CANDIDATE': 'general_profit',
    'GENERAL_FX_CANDIDATE': 'general_profit',
}
CONDITION_HINTS: dict[str, str] = {
    'bank_russian_taxpayer': 'Bank tax registration and taxpayer classification',
    'no_special_rate_applicable': 'Applicable tax regime, exception review and tax accounting policy',
    'qualifying_state_debt': 'Government bond issuance decision and instrument classification',
    'issue_terms_specify_interest': 'Official issue prospectus / terms establishing interest',
    'not_excluded_foreign_placement': 'Place and method of original issue/placement',
    'no_284_8_exclusion': 'Applicability review of NK RF article 284(8)',
    'issuer_municipality': 'Issuer charter / municipal registration and issue decision',
    'issuer_subject_rf': 'Issuer status of constituent entity of Russian Federation',
    'no_legacy_9_or_0': 'Issue date, original terms and grandfathering exceptions',
    'no_historical_exception': 'Issue date and relevant historical exception review',
    'issuer_russian_organization_not_foreign_resident': 'Issuer legal registry extract and residence',
    'ruble_denominated_nominal': 'Official ruble nominal denomination in issue terms',
    'issue_date_on_or_after_2017_01_01': 'Official placement/issuance date',
    'tax_traded_status_on_EACH_interest_recognition_date': (
        'Tax-market traded-status evidence on EACH recognition date, not only listing'),
    'mortgage_covered_bond': 'Registration of mortgage-backed issue and issue terms',
    'issued_after_2007_01_01': 'Verified issue date after 2007-01-01',
    'municipal_bond': 'Municipal issue terms and issuer identity',
    'issued_before_2007_01_01': 'Official issuance date before 2007-01-01',
    'original_issue_term_at_least_3_years': 'Original issue maturity schedule',
    'state_or_municipal_bond': 'Issue type and public issuer identity',
    'issue_date_on_or_before_1997_01_20': 'Official issuance date on/before 1997-01-20',
    'full_issue_terms': 'Complete issue terms including coupon and redemption rights',
}


def _when(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value or len(value) != 10:
        raise ValueError(f'{field} must be YYYY-MM-DD')
    return date.fromisoformat(value)


def _money(value: Any) -> Decimal:
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError('Amounts must be finite Decimal strings/integers, not floats')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Invalid amount') from exc
    if not result.is_finite():
        raise ValueError('Non-finite amount')
    return result


def _iso_interval_contains(item: dict[str, Any], target: date) -> bool:
    start = item.get('effective_from')
    end = item.get('effective_to')
    if not start:
        return False
    try:
        return _when(start, 'effective_from') <= target and (
            end in (None, '') or target <= _when(end, 'effective_to'))
    except (ValueError, TypeError):
        return False


def _row_key(row: dict[str, Any]) -> str:
    return '|'.join([str(row.get('event_id','')), str(row.get('lot_id') or ''),
                     str(row.get('component',''))])


def _hint(condition: str) -> str:
    return CONDITION_HINTS.get(condition, 'Supporting issue/tax document for: '+condition)


def _class_of(rate_rule: dict[str, Any]) -> str | None:
    return ('special_interest' if rate_rule.get('tax_base') == 'separate_interest'
            else 'general_profit' if rate_rule.get('tax_base') == 'general_profit'
            else None)


def _unique_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        shared_codes = {'MISSING_DATED_LAW_TEXT','MISSING_AMENDMENT_CHECK',
                        'MISSING_APPLICABILITY_CONDITION','RULE_REVALIDATION_REQUIRED',
                        'AMENDMENT_STATUS_UNKNOWN','AMENDMENT_PROVENANCE_MISSING',
                        'LAW_PROVENANCE_INCOMPLETE','SOURCE_REGISTRY_GAP'}
        key = (item['code'],item.get('rule_id'),item.get('source_id'),
               item.get('event_date'),item.get('condition'),
               None if item['code'] in shared_codes else item.get('row_key'))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def assess_report(report: dict[str, Any], catalog: dict[str, Any],
                  review: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append rule-by-rule evidence assessment to an existing normalized report.

    'review' is UNTRUSTED evidence metadata, not proof of external verification.
    Assertions of unchanged law and provided documents never yield VERIFIED/approved.
    """
    if not isinstance(report, dict) or not isinstance(catalog, dict):
        raise ValueError('Expected normalized report and catalog')
    if review is None:
        review = {}
    if not isinstance(review, dict):
        raise ValueError('legal_review must be an object')
    rules = catalog.get('rules')
    if not isinstance(rules, list):
        raise ValueError('Missing tax rules')
    index = {r['id']:r for r in rules}
    if len(index) != len(rules):
        raise ValueError('Duplicate tax rules')
    rows = report.get('accounting', {}).get('tax_components')
    if not isinstance(rows, list):
        raise ValueError('Report missing accounting.tax_components')
    for key in ('law_documents','amendment_checks','condition_evidence','rate_selections'):
        if not isinstance(review.get(key,[]),list):
            raise ValueError(f'legal_review.{key} must be an array')
    laws = review.get('law_documents',[])
    changes = review.get('amendment_checks',[])
    conditions = review.get('condition_evidence',[])
    selections = review.get('rate_selections',[])
    result = copy.deepcopy(report)
    evaluated = []
    requests: list[dict[str, Any]] = []
    found_changes = False
    for row in rows:
        rule_id = row.get('rule_id')
        rule = index.get(rule_id)
        if rule is None:
            raise ValueError(f'Unknown tax rule: {rule_id}')
        row_date = row.get('event_date')
        dt = _when(row_date, 'row.event_date')
        event_id = row.get('event_id')
        key = _row_key(row)
        base = row.get('candidate_tax_base')
        # Numeric shape must be validated even when no legal rate is available.
        _money(row.get('amount_rub'))
        rate_rule = rule
        selection = [x for x in selections if x.get('row_key') == key]
        warnings = []
        missing = []

        def need(code: str, description: str, *, source: str | None = None,
                 condition: str | None = None):
            item={'code':code,'rule_id':rule_id,'event_date':row_date,
                  'row_key':key,'request':description}
            if source:
                item['source_id']=source
            if condition:
                item['condition']=condition
            missing.append(code)
            requests.append(item)

        if len(selection) > 1:
            raise ValueError('Duplicate rate selections for row '+key)
        if selection:
            chosen = selection[0].get('rate_rule_id')
            rate_rule = index.get(chosen)
            if not rate_rule or rate_rule.get('rate_percent') is None:
                need('INVALID_RATE_SELECTION', 'Choose a numeric rate rule in the dated catalog; '+str(chosen))
                rate_rule = rule
            elif RATE_CLASSES.get(base) != _class_of(rate_rule):
                need('RATE_BASE_CONFLICT','Chosen rate does not correspond to candidate tax base; reclassify using the Tax Code')
                rate_rule = rule
            elif rule.get('rate_percent') is not None and rule_id != chosen:
                need('CONFLICTING_DIRECT_RATE', 'Original explicit rate rule cannot be overwritten by selection')
                rate_rule = rule
            elif rule_id != chosen:
                warnings.append('Selected rate is a separate legal hypothesis, not proved by event accounting')
        applied_rate_id = rate_rule['id'] if rate_rule.get('rate_percent') is not None else None
        applicable_rules = [rule] if applied_rate_id in (None,rule_id) else [rule,rate_rule]
        if base not in KNOWN_BASES:
            need('UNCLASSIFIED_COMPONENT',
                 'Provide legal tax-base classification of this exact component, with full dated provisions')
        if rate_rule.get('rate_percent') is None and base in KNOWN_BASES:
            need('RATE_RULE_REQUIRED',
                 'Identify a separate dated rate rule with issuer/market/tax-base evidence; do not infer 20%/25%')
        if applied_rate_id and RATE_CLASSES.get(base) != _class_of(rate_rule):
            # A direct rate rule cannot be used for the wrong taxable base.
            need('RATE_BASE_CONFLICT','Rule rate and component tax base conflict; provide a proper statutory rule')
            applied_rate_id = None

        statuses = set()
        for current in applicable_rules:
            cid = current['id']
            if current.get('readiness') == 'hard_stop':
                statuses.add('HARD_STOP')
                need('HARD_STOP_RULE','Provide case-specific legal opinion and complete issue/transaction terms')
            if current.get('valid_from') and dt < _when(current['valid_from'],'rule.valid_from'):
                statuses.add('HISTORICAL_REVISION')
                need('HISTORICAL_EDITION_REQUIRED',f'Provide controlling historical tax law for {row_date}')
            if current.get('valid_to') and dt > _when(current['valid_to'],'rule.valid_to'):
                statuses.add('HISTORICAL_REVISION')
                need('HISTORICAL_EDITION_REQUIRED',f'Stored rule has expired; provide replacement legal edition for {row_date}')
            ids = current.get('sources',[])
            if not ids:
                need('SOURCE_REGISTRY_GAP','Link the rule to an authoritative statutory source ID and exact paragraph')
            for source_id in ids:
                matching = [doc for doc in laws if doc.get('source_id') == source_id
                            and _iso_interval_contains(doc,dt)
                            and isinstance(doc.get('document_locator'),str)
                            and doc['document_locator'].strip()
                            and doc.get('full_text_available') is True]
                if not matching:
                    need('MISSING_DATED_LAW_TEXT',
                         'Provide full effective legal text for '+source_id+' on '+row_date+
                         ' (DOCX/searchable PDF plus official publication and amendments)',source=source_id)
                else:
                    if not any(all(isinstance(doc.get(field),str) and doc[field].strip()
                                   for field in ('official_publication_id','pinpoint','checked_at'))
                               for doc in matching):
                        need('LAW_PROVENANCE_INCOMPLETE',
                             'Provide official publication ID, exact article/pinpoint and check date for '+source_id,
                             source=source_id)
                    warnings.append('Law document metadata supplied but primary text has NOT been read/authenticated by this engine')
                checks = [a for a in changes if a.get('source_id') == source_id
                          and a.get('event_date') == row_date]
                if not checks:
                    need('MISSING_AMENDMENT_CHECK',
                         'Check and document amendments, effective dates and transitions for '+source_id+' on '+row_date,
                         source=source_id)
                else:
                    if len(checks)>1:
                        raise ValueError('Duplicate amendment evidence for source/date')
                    amendment=checks[0]
                    signal=amendment.get('change_status','unknown')
                    if signal not in ('unchanged','changed','unknown'):
                        raise ValueError('Bad amendment change_status')
                    if signal == 'changed':
                        found_changes=True
                        statuses.add('REVALIDATE')
                        need('RULE_REVALIDATION_REQUIRED',
                             'Changes reported for '+source_id+'; provide amending acts and issue a NEW catalog rule revision',source=source_id)
                    elif signal == 'unknown':
                        need('AMENDMENT_STATUS_UNKNOWN',
                             'Determine amendment status for '+source_id+' on '+row_date,source=source_id)
                    else:
                        reviewed_through = amendment.get('reviewed_through')
                        current_enough = False
                        if reviewed_through:
                            try:
                                current_enough = _when(reviewed_through, 'reviewed_through') >= dt
                            except ValueError:
                                current_enough = False
                        if not (amendment.get('supporting_document') and amendment.get('checked_at')
                                and current_enough):
                            need('AMENDMENT_PROVENANCE_MISSING',
                                 'Provide source, checked_at, and reviewed_through >= event date for no-change review of '+source_id,
                                 source=source_id)
                        else:
                            warnings.append('Unchanged-law assertion is externally supplied; not independently verified')
            for condition in current.get('required_conditions',[]):
                found = [x for x in conditions
                         if x.get('rule_id') == cid and x.get('event_date') == row_date
                         and x.get('condition') == condition
                         and isinstance(x.get('supporting_document'),str)
                         and x['supporting_document'].strip()]
                if not found:
                    need('MISSING_APPLICABILITY_CONDITION',_hint(condition),condition=condition)
                else:
                    warnings.append('Condition '+condition+' requires actual substantive document review')

        numeric = None
        if applied_rate_id is not None and not statuses and 'RATE_BASE_CONFLICT' not in missing:
            tax_base = _money(row.get('amount_rub'))
            rate = _money(rate_rule['rate_percent'])
            if tax_base < 0:
                need('LOSS_UTILIZATION_NOT_VERIFIED',
                     'Document applicable tax base, offset limitations, current profits and carry-forward history')
            elif 0 <= rate <= 100:
                numeric = format(tax_base*rate/Decimal('100'),'f')
            else:
                need('INVALID_SNAPSHOT_RATE','Correct invalid numeric rate rule')
        if 'REVALIDATE' in statuses:
            status='REVALIDATION_REQUIRED'
        elif 'HARD_STOP' in statuses:
            status='BLOCKED_HIGH_RISK'
        elif 'HISTORICAL_REVISION' in statuses:
            status='HISTORICAL_EDITION_REQUIRED'
        elif 'UNCLASSIFIED_COMPONENT' in missing:
            status='UNCLASSIFIED_REQUIRES_DOCUMENTS'
        elif missing:
            status='MISSING_EVIDENCE'
        else:
            status='DOCUMENTS_SUPPLIED_REVIEW_REQUIRED'
        evaluated.append({
            'row_key':key,'event_id':event_id,'event_date':row_date,
            'original_rule_id':rule_id,'rate_rule_id':applied_rate_id,
            'source_rule_ids':sorted({s['id'] for s in applicable_rules}),
            'candidate_tax_base':base,'stored_snapshot_rate_percent':(
                None if applied_rate_id is None else str(rate_rule['rate_percent'])),
            'conditional_arithmetic_tax_effect_rub':numeric,
            'status':status,'missing_evidence_codes':sorted(set(missing)),
            'warnings':sorted(set(warnings)),
            'legally_validated':False,'approved_tax_amount_rub':None,
        })

    needs=_unique_requests(requests)
    status = ('REVALIDATION_REQUIRED' if found_changes else
              'MISSING_EVIDENCE' if needs else 'DOCUMENTS_SUPPLIED_REVIEW_REQUIRED')
    result['legal_rules']={
        'schema_version':SCHEMA, 'status':status,
        'snapshot_date':catalog.get('legal_snapshot_date'),
        'law_checked_live_by_code':False,
        'current_law_confirmed':False,
        'external_metadata_not_verification':True,
        'evaluations':evaluated,
        'document_requests':needs,
        'next_step':('Obtain authoritative full controlling editions, amendment/transition texts '
                     'and issue evidence; review their substance before editing dated rules. '
                     'If unavailable, request the exact items listed from the user.'),
        'approved_tax_amount_rub':None,
        'conditional_tax_amounts_are_not_tax_payable':True,
    }
    result.setdefault('legal_validation',{})['legal_rules_status']=status
    result['legal_validation']['amendment_check_performed']=False
    result['legal_validation']['authoritative_texts_checked']=False
    result.setdefault('tax_outcome',{})['approved_tax_amount_rub']=None
    result['tax_outcome']['indicative_total_tax_rub']=None
    return result