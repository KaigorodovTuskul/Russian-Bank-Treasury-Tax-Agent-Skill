#!/usr/bin/env python3
"""Event-sourced RUB bond TAX RESEARCH ledger (synthetic, not a tax return).

Supported: traded, non-structured RUB coupon bonds with ordinary redemption;
BUY, ACCRUE, COUPON, AMORTIZE, SELL, REDEEM. Each amount uses Decimal.
Legally uncertain cases and unavailable legal editions fail closed.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

D = Decimal
CATALOG = Path(__file__).resolve().parents[1] / 'skills/russian-bank-treasury-tax/data/bond_tax_rules_2026.json'
COMPLEX_EVENTS = {'REPLACE', 'WRITE_DOWN', 'CONVERT', 'CANCEL_COUPON',
                  'STRUCTURED_PAY', 'NONRESIDENT_WITHHOLDING', 'INDEX', 'FX_SETTLE'}
ALLOWED = {'BUY', 'ACCRUE', 'COUPON', 'AMORTIZE', 'SELL', 'REDEEM'}


class LedgerBlocked(ValueError):
    """The requested ledger cannot be trusted without additional evidence."""
    def __init__(self, code: str, needed: tuple[str, ...]):
        self.code, self.needed = code, needed
        super().__init__(f'{code}: {"; ".join(needed)}')


def decimal(value: Any) -> D:
    if isinstance(value, bool) or value is None:
        raise ValueError('Missing or invalid decimal value')
    try:
        out = D(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f'Invalid numeric value: {value!r}') from exc
    if not out.is_finite():
        raise ValueError('Non-finite amount')
    return out


def positive(value: Any) -> D:
    d = decimal(value)
    if d <= 0:
        raise ValueError('Expected strictly positive amount')
    return d


def nonnegative(value: Any) -> D:
    d = decimal(value)
    if d < 0:
        raise ValueError('Expected nonnegative amount')
    return d


@dataclass
class Lot:
    id: str
    quantity: D
    cost_unit: D
    principal_unit: D
    last_nkd_unit: D
    period: str | None


class BondLedger:
    def __init__(self, catalog: dict[str, Any] | None = None):
        if catalog is None:
            catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        self.rules = {x['id']: x for x in catalog['rules']}
        self.lots: list[Lot] = []
        self.rows: list[dict[str, str | None]] = []
        self.cash: list[dict[str, str]] = []
        self.issue: str | None = None
        self.coupon_rule: str | None = None
        self.last_date: date | None = None
        self.ids: set[str] = set()
        self.closed_periods: set[str] = set()

    def _source(self, rule_id: str, event_date: str) -> dict[str, Any]:
        rule = self.rules.get(rule_id)
        if not rule:
            raise LedgerBlocked('RULE_MISSING', (f'Versioned rule: {rule_id}',))
        if rule.get('readiness') == 'hard_stop':
            raise LedgerBlocked('COMPLEX_RULE', (f'Case-specific legal research: {rule_id}',))
        if (rule.get('valid_from') and event_date < rule['valid_from']) or (
            rule.get('valid_to') and event_date > rule['valid_to']
        ):
            raise LedgerBlocked('HISTORICAL_EDITION_REQUIRED',
                                (f'Effective law for {event_date}', f'Rule: {rule_id}'))
        return rule

    def _post(self, event: dict, lot: Lot, component: str, amount: D, rule_id: str):
        if not amount:
            return
        r = self._source(rule_id, event['date'])
        self.rows.append({
            'event_id': event['id'], 'date': event['date'], 'security_id': self.issue,
            'lot_id': lot.id, 'component': component, 'amount_rub': str(amount),
            'tax_base_candidate': r['tax_base'], 'indicative_rate_percent': (
                str(r['rate_percent']) if r['rate_percent'] is not None else None),
            'rule_id': rule_id, 'primary_provision': r['primary_provision'],
            'legal_status': 'UNVERIFIED_LEGAL_EDITION',
            'approved_tax_amount_rub': None,
        })

    def _cash(self, event: dict, flow: D):
        self.cash.append({'event_id': event['id'], 'date': event['date'],
                          'cash_flow_rub': str(flow)})

    def _period(self, lot: Lot, event: dict):
        name = event.get('coupon_period')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('coupon_period is required for coupon/NKD operations')
        if name in self.closed_periods:
            raise LedgerBlocked('COUPON_PERIOD_ALREADY_PAID',
                                (f'Coupon period {name} previously closed',))
        if lot.period is None:
            lot.period = name
        elif lot.period != name:
            raise LedgerBlocked('COUPON_PERIOD_MISMATCH',
                                (f'Previous coupon period: {lot.period}',
                                 f'Event coupon period: {name}', 'Issue coupon schedule'))

    def apply(self, event: dict[str, Any]):
        if not isinstance(event, dict):
            raise ValueError('Event must be an object')
        kind, event_id, event_date = event.get('type'), event.get('id'), event.get('date')
        if not isinstance(event_id, str) or not event_id.strip() or event_id in self.ids:
            raise ValueError('Event id missing or repeated')
        if not isinstance(event_date, str):
            raise ValueError('Event date is required')
        dt = date.fromisoformat(event_date)
        if self.last_date and dt < self.last_date:
            raise ValueError('Events must be chronological; same-day input order is significant')
        if kind in COMPLEX_EVENTS or kind not in ALLOWED:
            raise LedgerBlocked('UNSUPPORTED_EVENT',
                                (f'Full issue terms for {kind}',
                                 'Applicable dated Tax Code, amendments and interpretation'))
        issue = event.get('security_id')
        if not isinstance(issue, str) or not issue.strip():
            raise ValueError('security_id required')
        if self.issue is not None and self.issue != issue:
            raise LedgerBlocked('MULTI_ISSUE_INPUT', ('One security per ledger invocation',))
        self.issue = issue
        if kind != 'BUY' and not self.lots:
            raise ValueError('No remaining position')
        handler = getattr(self, '_'+kind.lower())
        handler(event)
        self.ids.add(event_id)
        self.last_date = dt

    def _buy(self, e: dict):
        if e.get('currency') != 'RUB' or e.get('traded_market_status') != 'TRADED':
            raise LedgerBlocked('ISSUE_NOT_SUPPORTED',
                                ('RUB denomination and settlement',
                                 'Evidence of traded tax-market status',
                                 'Separate special-case handling if absent'))
        lot_id = e.get('lot_id')
        if not isinstance(lot_id, str) or not lot_id or any(x.id == lot_id for x in self.lots):
            raise ValueError('Unique lot_id required')
        qty, clean, nkd, fees, principal = (
            positive(e['quantity']), nonnegative(e['clean_price_unit']),
            nonnegative(e['nkd_unit']), nonnegative(e.get('fees_rub', 0)),
            positive(e['principal_unit']))
        period = e.get('coupon_period')
        if nkd and (not isinstance(period, str) or not period):
            raise ValueError('coupon_period required when purchased NKD > 0')
        coupon_rule = e.get('coupon_rule_id')
        rule = self._source(coupon_rule, e['date'])
        if rule.get('rate_percent') is None:
            raise ValueError('Coupon rule requires a numeric research-snapshot rate')
        if self.coupon_rule and self.coupon_rule != coupon_rule:
            raise LedgerBlocked('CONFLICTING_COUPON_TREATMENT',
                                ('Coupon tax classification per acquisition lot',))
        if self.lots and any(l.principal_unit != principal for l in self.lots):
            raise LedgerBlocked('PRINCIPAL_BALANCE_MISMATCH',
                                ('Per-issue principal balance on acquisition date',
                                 'Complete issuer amortization history'))
        self.coupon_rule = coupon_rule
        self._source('BND-GEN-25', e['date'])
        self.lots.append(Lot(lot_id, qty, clean + fees/qty, principal, nkd, period))
        self._cash(e, -(qty*(clean+nkd) + fees))

    def _accrue(self, e: dict):
        nkd = nonnegative(e['nkd_unit'])
        for lot in self.lots:
            self._period(lot, e)
            if nkd < lot.last_nkd_unit:
                raise LedgerBlocked('NKD_DECREASE_WITHOUT_COUPON',
                                    ('Coupon payment confirmation', 'Coupon period schedule'))
            self._post(e, lot, 'INTEREST_ACCRUAL', lot.quantity*(nkd-lot.last_nkd_unit),
                       self.coupon_rule)
            lot.last_nkd_unit = nkd
        self._cash(e, D('0'))

    def _coupon(self, e: dict):
        coupon = nonnegative(e['coupon_unit'])
        for lot in self.lots:
            self._period(lot, e)
            if coupon < lot.last_nkd_unit:
                raise LedgerBlocked('COUPON_LESS_THAN_ACCRUED_NKD',
                                    ('Coupon calculation and payment document',))
            self._post(e, lot, 'INTEREST_ACCRUAL', lot.quantity*(coupon-lot.last_nkd_unit),
                       self.coupon_rule)
            lot.last_nkd_unit = D('0')
            lot.period = None
        self._cash(e, coupon*sum(l.quantity for l in self.lots))
        self.closed_periods.add(e['coupon_period'])

    def _amortize(self, e: dict):
        amount = positive(e['principal_paid_unit'])
        total = D('0')
        for lot in self.lots:
            if amount >= lot.principal_unit:
                raise LedgerBlocked('FULL_REDEMPTION_REQUIRED',
                                    ('Use REDEEM for complete principal repayment',))
            cost_alloc = lot.cost_unit*amount/lot.principal_unit
            self._post(e, lot, 'PRINCIPAL_PRICE_RESULT',
                       lot.quantity*(amount-cost_alloc), 'BND-GEN-25')
            lot.principal_unit -= amount
            lot.cost_unit -= cost_alloc
            total += lot.quantity*amount
        self._cash(e, total)

    def _sell(self, e: dict):
        qty = positive(e['quantity'])
        clean, nkd, fees = (nonnegative(e['clean_price_unit']),
                            nonnegative(e['nkd_unit']),
                            nonnegative(e.get('fees_rub',0)))
        if qty > sum(l.quantity for l in self.lots):
            raise ValueError('Insufficient position for sale')
        sold = D('0')
        for lot in list(self.lots):
            take = min(qty-sold, lot.quantity)
            if take == 0:
                break
            self._period(lot, e)
            if nkd < lot.last_nkd_unit:
                raise LedgerBlocked('SALE_NKD_BELOW_ACCRUED',
                                    ('Coupon schedule and payment confirmations',))
            self._post(e, lot, 'INTEREST_ACCRUAL',
                       take*(nkd-lot.last_nkd_unit), self.coupon_rule)
            self._post(e, lot, 'SALE_PRICE_RESULT',
                       take*(clean-lot.cost_unit)-fees*take/qty, 'BND-GEN-25')
            lot.quantity -= take
            sold += take
            if lot.quantity == 0:
                self.lots.remove(lot)
        self._cash(e, qty*(clean+nkd)-fees)

    def _redeem(self, e: dict):
        if 'redemption_cash_unit' in e:
            raise LedgerBlocked('NONSTANDARD_REDEMPTION',
                                ('Issue terms for call premiums or discounts',
                                 'Applicable tax classification'))
        if any(l.last_nkd_unit for l in self.lots):
            raise LedgerBlocked('UNSETTLED_INTEREST_ON_REDEMPTION',
                                ('Final coupon payment / accrued interest evidence',))
        total = D('0')
        for lot in self.lots:
            self._post(e, lot, 'PRINCIPAL_PRICE_RESULT',
                       lot.quantity*(lot.principal_unit-lot.cost_unit), 'BND-GEN-25')
            total += lot.quantity*lot.principal_unit
        self._cash(e,total)
        self.lots.clear()

    def report(self) -> dict[str, Any]:
        income = sum((D(r['amount_rub']) for r in self.rows), D('0'))
        cash = sum((D(x['cash_flow_rub']) for x in self.cash),D('0'))
        positions = [dict(lot_id=l.id, quantity=str(l.quantity),
                          remaining_tax_cost_rub=str(l.cost_unit*l.quantity),
                          principal_unit_rub=str(l.principal_unit),
                          last_nkd_unit_rub=str(l.last_nkd_unit),
                          coupon_period=l.period) for l in self.lots]
        # Closed-position reconciliation only: accrued interest is then fully settled.
        closed = not self.lots
        if closed and self.cash and cash != income:
            raise LedgerBlocked('CLOSED_LEDGER_RECONCILIATION_FAILED',
                                ('Cash flows, NKD and fee treatment',
                                 f'Cash={cash}; recognized={income}'))
        bases: dict[str, D] = {}
        for r in self.rows:
            name=r['tax_base_candidate']
            bases[name] = bases.get(name,D('0'))+D(r['amount_rub'])
        return {
            'security_id': self.issue, 'status': 'UNVERIFIED_LEGAL_EDITION',
            'legal_snapshot': '2026-10-14', 'approved_tax_amount_rub': None,
            'event_count':len(self.ids), 'tax_entries': self.rows,
            'cash_flows': self.cash, 'positions': positions,
            'tax_base_candidate_totals_rub':{k:str(v) for k,v in bases.items()},
            'recognized_result_rub':str(income), 'net_cash_flow_rub':str(cash),
            'closed_position_reconciled': closed,
            'periodization_warning': 'Completeness of month-end ACCRUE events is not automatically verified',
            'required_sources': ['Full Tax Code edition effective on each event date',
                                 'Amending acts and transitional provisions',
                                 'Issue terms / coupon dates / bank tax policy',
                                 'Market-status evidence and trade confirmations'],
            'disclaimer':'Research-only synthetic output; rates are not approved for filing.'}


def run_ledger(events: list[dict[str, Any]], catalog: dict | None = None) -> dict[str, Any]:
    ledger = BondLedger(catalog=catalog)
    if not events:
        raise ValueError('At least one event required')
    for event in events:
        ledger.apply(event)
    return ledger.report()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path,help='JSON document with events array')
    args=parser.parse_args()
    data=json.loads(args.file.read_text(encoding='utf-8'))
    try:
        result = run_ledger(data['events'])
    except LedgerBlocked as exc:
        result = {'status':'BLOCKED', 'reason_code':exc.code,
                  'required_documents':list(exc.needed), 'approved_tax_amount_rub':None}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(2) from None
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()