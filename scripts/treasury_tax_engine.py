#!/usr/bin/env python3
"""Unified, conservative bond-tax RESEARCH orchestrator.

Routes one-security event streams into existing audited *synthetic* calculators.
Does NOT independently verify Russian law or approve tax payable.

This is a router and reporting facade, NOT a replacement for dated legal research.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

CATALOG = Path(__file__).resolve().parents[1] / (
    'skills/russian-bank-treasury-tax/data/bond_tax_rules_2026.json'
)
SNAPSHOT_DATE = '2026-10-14'


class EngineBlocked(ValueError):
    """Requested route or source cannot be established safely."""

    def __init__(self, code: str, documents: tuple[str, ...] = ()):  # noqa: D107
        self.code = code
        self.documents = tuple(documents)
        super().__init__(f'{code}: {"; ".join(self.documents)}')


def _number(value: Any) -> Decimal:
    if value is None or isinstance(value, (bool, float)):
        raise ValueError('Monetary values must be exact strings or integers, not floats/bools')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Invalid monetary value') from exc
    if not result.is_finite():
        raise ValueError('Non-finite monetary value')
    return result


def _decimal_str(value: Any) -> str:
    return format(_number(value), 'f')


def _reject_floats(value: Any):
    if isinstance(value, float):
        raise ValueError('JSON floating-point amounts are not accepted; use decimal strings')
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    if isinstance(value, list):
        for item in value:
            _reject_floats(item)


def load_catalog(path: Path = CATALOG) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    rules = data.get('rules')
    if not isinstance(rules, list) or not rules:
        raise EngineBlocked('INVALID_RULE_CATALOG', ('Original, versioned tax rule catalog',))
    keys = [r['id'] for r in rules]
    if len(keys) != len(set(keys)):
        raise EngineBlocked('DUPLICATE_RULE_IDS', ('Corrected tax rule catalog',))
    return data


def _input_profile(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('Payload must be an object')
    _reject_floats(payload)
    events = payload.get('events')
    if not isinstance(events, list) or not events:
        raise ValueError('events must be a nonempty list')
    if not all(isinstance(e, dict) for e in events):
        raise ValueError('Each event must be a JSON object')
    purchases = [e for e in events if e.get('type') == 'BUY']
    if not purchases or events[0].get('type') != 'BUY':
        raise EngineBlocked('MISSING_INITIAL_PURCHASE', ('First BUY event and issue terms',))
    initial = purchases[0]
    ids = [e.get('id') for e in events]
    if any(not isinstance(v, str) or not v.strip() for v in ids) or len(ids) != len(set(ids)):
        raise ValueError('Event ids must be nonempty and unique')
    issue = initial.get('security_id')
    if not isinstance(issue, str) or not issue.strip():
        raise ValueError('security_id required on BUY')
    if any(e.get('security_id') != issue for e in events):
        raise EngineBlocked('MULTIPLE_SECURITIES', ('Run one ISIN / security per request',))
    previous: date | None = None
    for e in events:
        if not isinstance(e.get('date'), str):
            raise ValueError('Each event requires a date')
        dt = date.fromisoformat(e['date'])
        if previous and dt < previous:
            raise ValueError('Events must be chronological; same-day order is material')
        previous = dt

    def identify_buy(e: dict[str, Any]) -> str:
        if e.get('security_kind') == 'OFZ_IN':
            if e.get('nominal_currency') != 'RUB':
                raise EngineBlocked('CONFLICTING_INSTRUMENT_METADATA', ('OFZ-IN RUB issue terms',))
            return 'OFZ_IN'
        nominal_ccy = e.get('nominal_currency')
        if isinstance(nominal_ccy, str) and nominal_ccy and nominal_ccy != 'RUB':
            if e.get('security_kind') not in (None, 'CORPORATE_BOND'):
                raise EngineBlocked('CONFLICTING_INSTRUMENT_METADATA', ('Issue type / FX denomination',))
            return 'FX'
        if e.get('currency') == 'RUB' and e.get('principal_unit') is not None:
            if e.get('security_kind') not in (None, 'STANDARD_BOND'):
                raise EngineBlocked('CONFLICTING_INSTRUMENT_METADATA', ('Instrument classification',))
            return 'RUB'
        raise EngineBlocked('INSTRUMENT_CLASSIFICATION_REQUIRED',
                            ('Issuer terms with instrument kind, currency, nominal and coupon details',))

    kinds = {identify_buy(e) for e in purchases}
    if len(kinds) != 1:
        raise EngineBlocked('MIXED_INSTRUMENT_KINDS', ('One security with consistent issue metadata',))
    kind = kinds.pop()
    requested_kind = payload.get('kind')
    if requested_kind is not None and requested_kind != kind:
        raise EngineBlocked('DECLARED_KIND_MISMATCH',
                            (f'Declared {requested_kind}; derived {kind}', 'Issuer issue terms',))

    # Avoid using a single-lot engine when partial disposal or multiple lots exist.
    quantity = Decimal('0')
    partial_disposal = False
    for event in events:
        typ = event.get('type')
        if typ == 'BUY':
            quantity += _number(event['quantity'])
        elif typ == 'SELL':
            n = _number(event['quantity'])
            if n < quantity:
                partial_disposal = True
            quantity -= n
        elif typ == 'REDEEM':
            n = _number(event.get('quantity', quantity))
            if n < quantity:
                partial_disposal = True
            quantity -= n
        if quantity < 0:
            raise ValueError('Disposal exceeds holdings')
    requires_multilot = len(purchases) > 1 or partial_disposal
    preferred = payload.get('calculation_mode', 'auto')
    if preferred not in ('auto', 'single', 'multi'):
        raise ValueError('calculation_mode must be auto, single or multi')
    if preferred == 'single' and requires_multilot:
        raise EngineBlocked('SINGLE_LOT_ROUTE_UNSAFE',
                            ('Several acquisition lots or partial disposal detected',))
    if kind == 'RUB':
        if preferred == 'single' and requires_multilot:
            raise EngineBlocked('SINGLE_LOT_ROUTE_UNSAFE', ('RUB portfolio has multiple lots',))
        backend = 'bond_ledger'
    elif preferred == 'multi' or requires_multilot:
        backend = 'multilot_bond_ledger'
    else:
        backend = 'advanced_bond_ledger'
    return {
        'kind': kind, 'backend': backend, 'security_id': issue,
        'events': events, 'purchase_count': len(purchases),
        'partial_disposal': partial_disposal,
        'route_reason': (
            'RUB traded coupon engine supports lot-level FIFO and amortization'
            if kind == 'RUB' else
            'Multiple acquisition lots / partial disposal or explicit multi mode'
            if backend == 'multilot_bond_ledger' else
            'One purchase with no partial disposals'),
    }


def _calculate(profile: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    name = profile['backend']
    if name == 'bond_ledger':
        from bond_ledger import run_ledger
        return run_ledger(profile['events'], catalog=catalog)
    if name == 'advanced_bond_ledger':
        from advanced_bond_ledger import run_advanced
        return run_advanced(profile['events'], profile['kind'])
    if name == 'multilot_bond_ledger':
        from multilot_bond_ledger import run_multilot
        return run_multilot(profile['events'], profile['kind'])
    raise AssertionError('Unknown backend')


def _normalize(profile: dict[str, Any], native: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    index = {r['id']: r for r in catalog['rules']}
    rows = native.get('tax_entries', [])
    if not isinstance(rows, list):
        raise EngineBlocked('INVALID_BACKEND_ROWS', ('Raw event computation and logs',))
    normalized = []
    buckets: dict[str, Decimal] = {}
    component_total = Decimal('0')
    for row in rows:
        rid = row.get('rule_id')
        if rid not in index:
            raise EngineBlocked('UNMAPPED_RULE_REFERENCE', (str(rid), 'Rule catalog amendments'))
        rule = index[rid]
        if rule.get('readiness') == 'hard_stop':
            raise EngineBlocked('HARD_STOP_RULE_USED', (rid, 'Case-specific legal validation'))
        when = row['date']
        historical = bool((rule.get('valid_from') and when < rule['valid_from']) or
                          (rule.get('valid_to') and when > rule['valid_to']))
        if historical:
            raise EngineBlocked('RULE_DATE_OUTSIDE_VALIDITY',
                                (f'{rid} on {when}', 'Dated controlling legal edition and transition rules'))
        value = _number(row['amount_rub'])
        base = row.get('candidate_tax_base', row.get('tax_base_candidate'))
        base = {
            'general_profit': 'GENERAL_PROFIT_CANDIDATE',
            'separate_interest': 'SPECIAL_INTEREST_CANDIDATE',
        }.get(base, base)
        base = base if isinstance(base, str) and base else 'UNCLASSIFIED_NOT_TAX_BASE'
        buckets[base] = buckets.get(base, Decimal('0')) + value
        component_total += value
        normalized.append({
            'event_id': row['event_id'], 'event_date': when,
            'security_id': row.get('security_id', profile['security_id']),
            'lot_id': row.get('lot_id'), 'component': row['component'],
            'amount_rub': _decimal_str(value), 'candidate_tax_base': base,
            'rule_id': rid, 'legal_pinpoint': rule.get('primary_provision'),
            'primary_source_ids': rule.get('sources', []),
            'interpretation_note': row.get('source_reference'),
            'rate_percent_snapshot': (None if rule.get('rate_percent') is None
                                      else str(rule['rate_percent'])),
            'required_applicability_conditions': rule.get('required_conditions', []),
            'legal_status': ('UNCLASSIFIED_REQUIRES_DOCUMENTS'
                             if base == 'UNCLASSIFIED_NOT_TAX_BASE'
                             else 'UNVERIFIED_LEGAL_EDITION'),
            'approved_tax_amount_rub': None,
        })
    cash_rows = native.get('cash_flows', [])
    cash_total = sum((_number(x.get('cash_flow_rub', x.get('synthetic_cash_rub')))
                      for x in cash_rows), Decimal('0'))
    positions = native.get('positions', [])
    if not isinstance(positions, list):
        raise EngineBlocked('INVALID_POSITION_ROWS', ('Raw positions',))
    closed = bool(native.get('closed_position_reconciled'))
    if closed and component_total != cash_total:
        raise EngineBlocked('UNIFIED_RECONCILIATION_FAILED',
                            (f'Components={component_total}', f'Cash={cash_total}',
                             'Complete trade, NKD and coupon cash evidence'))
    rule_info = [{
        'rule_id': rid, 'source_pinpoint': index[rid]['primary_provision'],
        'source_ids': index[rid].get('sources', []),
        'rate_percent_snapshot': index[rid].get('rate_percent'),
        'required_conditions': index[rid].get('required_conditions', []),
        'catalog_readiness': index[rid].get('readiness'),
        'snapshot_date': index[rid]['as_of'],
    } for rid in sorted({r['rule_id'] for r in normalized})]
    unclassified = any(row['candidate_tax_base'] == 'UNCLASSIFIED_NOT_TAX_BASE'
                       for row in normalized)
    required_docs = [
        'Full historical/current applicable NK RF editions for all events',
        'Official amendment laws, effective dates and transitional provisions',
        'Full issuer terms, coupon calendar and any indexed nominal schedule',
        'Trade/depository records, purchased and disposed NKD, bank tax-accounting policy',
        'Official historical currency rates and tax treatment of receivables where FX',
        'Evidence of traded status and eligibility for any special rate',
    ]
    if unclassified:
        required_docs.append('Legal tax classification of purchased-NKD FX differences')
    return {
        'schema_version': '0.3.0',
        'engine': 'treasury_tax_engine',
        'status': 'UNVERIFIED_LEGAL_EDITION',
        'research_only': True,
        'instrument': {'security_id': profile['security_id'], 'kind': profile['kind'],
                       'event_count': len(profile['events']),
                       'purchase_count': profile['purchase_count']},
        'route': {'backend': profile['backend'], 'reason': profile['route_reason'],
                  'partial_disposals': profile['partial_disposal']},
        'accounting': {
            'tax_components': normalized,
            'candidate_tax_base_totals_rub': {k: _decimal_str(v) for k, v in sorted(buckets.items())},
            'component_total_rub': _decimal_str(component_total),
            'net_cash_flow_rub': _decimal_str(cash_total),
            'closed_position_reconciled': closed,
            'open_lots': positions,
            'cash_flows': cash_rows,
        },
        'legal_validation': {
            'status': 'UNVERIFIED_LEGAL_EDITION',
            'rule_catalog_snapshot': catalog.get('legal_snapshot_date', SNAPSHOT_DATE),
            'amendment_check_performed': False,
            'authoritative_texts_checked': False,
            'tax_rate_predicates_checked': False,
            'unclassified_components_present': unclassified,
            'required_documents_if_sources_unavailable': required_docs,
            'instruction': (
                'Verify the edition applicable to each event, intervening amendments and '
                'transitional rules; if full controlling documents are unavailable, '
                'request the texts from the user. Do not issue a definitive conclusion.'),
            'rules_used': rule_info,
        },
        'tax_outcome': {
            'approved_tax_amount_rub': None,
            'indicative_total_tax_rub': None,
            'explanation': 'Only component arithmetic is computed; no legal validation or tax-base netting.',
        },
    }


def run_unified(payload: dict[str, Any], *, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Raises on invalid input / blocked legal events. No definitive tax amount."""
    profile = _input_profile(payload)
    rules = load_catalog() if catalog is None else catalog
    native = _calculate(profile, rules)
    return _normalize(profile, native, rules)


def safe_run(payload: dict[str, Any], *, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a uniform BLOCKED/INVALID_INPUT object for CLI/agent workflows."""
    try:
        return run_unified(payload, catalog=catalog)
    except EngineBlocked as exc:
        code, docs, status = exc.code, list(exc.documents), 'BLOCKED'
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        # Known evidence-dependent exceptions from the three adapters.
        if hasattr(exc, 'code') and (hasattr(exc, 'documents') or hasattr(exc, 'needed')):
            code = exc.code
            docs = list(getattr(exc, 'documents', getattr(exc, 'needed', ())))
            status = 'BLOCKED'
        else:
            code, docs, status = 'INVALID_INPUT', [str(exc)], 'INVALID_INPUT'
    return {
        'schema_version': '0.3.0', 'engine': 'treasury_tax_engine',
        'status': status, 'reason_code': code,
        'required_documents': docs, 'approved_tax_amount_rub': None,
        'legal_validation': {'status': 'UNVERIFIED_LEGAL_EDITION',
                             'amendment_check_performed': False},
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_json', type=Path)
    p.add_argument('--output', type=Path, help='Write unified report to this file')
    args = p.parse_args()
    payload = json.loads(args.input_json.read_text(encoding='utf-8'))
    result = safe_run(payload)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(serialized, encoding='utf-8')
    else:
        print(serialized, end='')
    raise SystemExit(0 if result['status'] == 'UNVERIFIED_LEGAL_EDITION' else 2)


if __name__ == '__main__':
    main()