#!/usr/bin/env python3
"""Research-only event ledger for FX-denominated ordinary bonds and positive-index OFZ-IN.

This program computes auditable candidate components, NOT approved tax amounts.
It deliberately blocks legally unresolved special coupon recognition, negative nominal
indexation, complex redemptions, multi-lot accounting, and nonstandard FX settlement.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

D = Decimal


class LegalEvidenceRequired(ValueError):
    def __init__(self, code: str, documents: tuple[str, ...]):
        self.code = code
        self.documents = documents
        super().__init__(f'{code}: {"; ".join(documents)}')


def amount(value: Any, *, positive: bool = False) -> D:
    if isinstance(value, bool) or value is None:
        raise ValueError('Decimal amount required')
    try:
        v = D(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Invalid Decimal amount') from exc
    if not v.is_finite() or v < 0 or (positive and v == 0):
        raise ValueError('Amount must be finite and nonnegative' + (' and nonzero' if positive else ''))
    return v


class AdvancedBondLedger:
    """Intentionally limited to a single homogeneous, fully disposed lot.

    This disallows partial sale, acquired-bond special methods and netting multiple
    coupon entitlements before their legal qualification has been validated.
    """

    TYPE_EVENTS = {
        'FX': {'BUY', 'ACCRUE', 'COUPON', 'SELL', 'REDEEM'},
        'OFZ_IN': {'BUY', 'INDEX', 'ACCRUE', 'COUPON', 'SELL', 'REDEEM'},
    }

    def __init__(self, kind: str):
        if kind not in self.TYPE_EVENTS:
            raise ValueError('kind must be FX or OFZ_IN')
        self.kind = kind
        self.security_id: str | None = None
        self.lot_id: str | None = None
        self.quantity = D('0')
        self.cost_unit_rub = D('0')
        self.currency: str | None = None
        self.original_nominal_unit = D('0')
        self.nominal_unit = D('0')
        self.buy_rate = D('0')
        self.last_nkd_unit = D('0')
        self.purchased_nkd_unit = D('0')
        self.coupon_receivable_unit = D('0')
        self.receivable_last_rate = D('0')
        self.period: str | None = None
        self.closed_periods: set[str] = set()
        self.indexation_recognized_unit = D('0')
        self.tax_rows: list[dict[str, Any]] = []
        self.cash_rows: list[dict[str, str]] = []
        self.ids: set[str] = set()
        self.last_date: date | None = None
        self.closed = False

    def _rule_id(self, component: str) -> str:
        if component == 'INTEREST_ACCRUAL_CANDIDATE':
            return 'BND-OFZ-INT-20' if self.kind == 'OFZ_IN' else 'BND-NKD-LEDGER'
        if component == 'INDEXATION_INTEREST_CANDIDATE':
            return 'BND-INDEXED-OFZ'
        if component == 'PRICE_REALIZATION_CANDIDATE':
            return 'BND-FX-NO-REVALUE' if self.kind == 'FX' else 'BND-CLEAN-PRICE-RESULT'
        return 'BND-NKD-LEDGER'

    def _record(self, e: dict, component: str, value: D, source: str,
                *, candidate_base: str | None):
        if not value:
            return
        self.tax_rows.append({
            'event_id': e['id'], 'date': e['date'], 'security_id': self.security_id,
            'component': component, 'amount_rub': str(value),
            'rule_id': self._rule_id(component),
            'candidate_tax_base': candidate_base, 'source_reference': source,
            'verification_status': ('UNCLASSIFIED_REQUIRES_DOCUMENTS'
                                    if candidate_base is None else 'PROVISIONAL'),
            'approved_tax_amount_rub': None,
        })

    def _cash(self, e: dict, value: D):
        self.cash_rows.append({'event_id': e['id'], 'date': e['date'],
                               'synthetic_cash_rub': str(value)})

    def _rate(self, e: dict) -> D:
        return amount(e['rub_per_nominal_currency'], positive=True)

    def _coupon_period(self, e: dict):
        period = e.get('coupon_period')
        if not isinstance(period, str) or not period.strip():
            raise ValueError('coupon_period required')
        if period in self.closed_periods:
            raise LegalEvidenceRequired('COUPON_ALREADY_PAID', ('Coupon history',))
        if self.period is None:
            self.period = period
        elif self.period != period:
            raise LegalEvidenceRequired('COUPON_PERIOD_MISMATCH',
                                        ('Complete coupon schedule',))

    def _recognize_nkd(self, e: dict, new_nkd: D, rate: D):
        self._coupon_period(e)
        if new_nkd < self.last_nkd_unit:
            raise LegalEvidenceRequired('NKD_FELL_WITHOUT_COUPON',
                                        ('Coupon calendar and broker statements',))
        if self.kind == 'FX' and self.coupon_receivable_unit:
            reval = self.coupon_receivable_unit * (rate-self.receivable_last_rate)
            self._record(e, 'FX_INTEREST_RECEIVABLE_REVALUATION_CANDIDATE', reval,
                         'НК РФ ст.250, 265, 271–272; bank-specific applicability',
                         candidate_base='GENERAL_FX_CANDIDATE')
        incremental = new_nkd-self.last_nkd_unit
        self._record(e, 'INTEREST_ACCRUAL_CANDIDATE', self.quantity*incremental*rate,
                     'НК РФ ст.271, 281, 284, 328',
                     candidate_base=('GENERAL_INTEREST_CANDIDATE' if self.kind == 'FX'
                                     else 'SPECIAL_INTEREST_CANDIDATE'))
        if self.kind == 'FX':
            self.coupon_receivable_unit += self.quantity*incremental
            self.receivable_last_rate = rate
        self.last_nkd_unit = new_nkd

    def _buy(self, e: dict):
        if self.security_id is not None:
            raise LegalEvidenceRequired('MULTI_LOT_UNSUPPORTED',
                                        ('Per-lot tax-cost and coupon attribution',))
        qty = amount(e['quantity'], positive=True)
        clean = amount(e['clean_price_unit'])
        nkd = amount(e['nkd_unit'])
        fees = amount(e.get('fees_rub', '0'))
        nominal = amount(e['nominal_unit'], positive=True)
        rate = self._rate(e) if self.kind == 'FX' else D('1')
        if self.kind == 'FX':
            currency = e.get('nominal_currency')
            if (not isinstance(currency, str) or len(currency) != 3 or
                    not currency.isalpha() or not currency.isupper() or currency == 'RUB' or
                    e.get('settlement_currency') != currency or
                    e.get('issuer_law') != 'RU' or
                    e.get('issuer_class') != 'RU_CORPORATE' or
                    e.get('coupon_recognition_method') != 'ACCRUAL'):
                raise LegalEvidenceRequired('FX_INSTRUMENT_NOT_SUPPORTED',
                    ('Russian-law issue terms', 'Coupon recognition legal grounds',
                     'Settlement currency and matching cash confirmation'))
        else:
            if e.get('nominal_currency') != 'RUB' or e.get('security_kind') != 'OFZ_IN':
                raise LegalEvidenceRequired('OFZ_IN_ISSUE_NOT_ESTABLISHED',
                                            ('Actual terms of indexed government issue',))
            currency = 'RUB'
        self.security_id, self.lot_id = e['security_id'], e['lot_id']
        self.quantity, self.currency = qty, currency
        self.original_nominal_unit = self.nominal_unit = nominal
        self.cost_unit_rub = clean*rate + fees/qty
        self.buy_rate = rate
        self.purchased_nkd_unit = nkd
        self.last_nkd_unit = nkd
        self.receivable_last_rate = rate
        if nkd:
            self._coupon_period(e)
        self._cash(e, -(qty*(clean+nkd)*rate+fees))

    def _accrue(self, e: dict):
        self._recognize_nkd(e, amount(e['nkd_unit']),
                            self._rate(e) if self.kind == 'FX' else D('1'))
        self._cash(e, D('0'))

    def _coupon(self, e: dict):
        coupon = amount(e['coupon_unit'])
        rate = self._rate(e) if self.kind == 'FX' else D('1')
        self._recognize_nkd(e, coupon, rate)
        if self.kind == 'FX' and self.purchased_nkd_unit:
            # The tax character of the FX difference on *purchased* NKD is NOT
            # decided by this research arithmetic model.
            diff = self.quantity * self.purchased_nkd_unit * (rate-self.buy_rate)
            self._record(e, 'PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED', diff,
                         'НК РФ ст.280, 328; require FX NKD legal analysis',
                         candidate_base=None)
        self._cash(e, self.quantity*coupon*rate)
        self.closed_periods.add(self.period)
        self.period = None
        self.last_nkd_unit = D('0')
        self.purchased_nkd_unit = D('0')
        self.coupon_receivable_unit = D('0')
        self.receivable_last_rate = rate

    def _index(self, e: dict):
        new_nominal = amount(e['indexed_nominal_unit'], positive=True)
        if new_nominal < self.nominal_unit:
            raise LegalEvidenceRequired('NEGATIVE_OFZ_INDEXATION_REVIEW',
                ('Full issue terms', 'Minfin 13.12.2022 № 03-03-06/2/122113',
                 'Relevant 2026 Tax Code edition and transitional rules'))
        delta = new_nominal-self.nominal_unit
        self._record(e, 'INDEXATION_INTEREST_CANDIDATE', self.quantity*delta,
                     'НК РФ ст.281, 328; Минфин 14.07.2015 № 03-03-10/40395',
                     candidate_base='SPECIAL_INTEREST_CANDIDATE')
        self.indexation_recognized_unit += delta
        self.nominal_unit = new_nominal
        self._cash(e, D('0'))

    def _dispose(self, e: dict, *, redeem: bool):
        if amount(e.get('quantity', self.quantity), positive=True) != self.quantity:
            raise LegalEvidenceRequired('PARTIAL_DISPOSAL_UNSUPPORTED',
                                        ('Per-lot FIFO/tax-cost allocation',))
        if redeem and (self.last_nkd_unit or self.coupon_receivable_unit):
            raise LegalEvidenceRequired('UNSETTLED_COUPON_AT_REDEMPTION',
                                        ('Final coupon and NKD payment confirmation',))
        rate = self._rate(e) if self.kind == 'FX' else D('1')
        if redeem:
            if self.kind == 'OFZ_IN':
                proceeds = self.nominal_unit
            else:
                proceeds = self.original_nominal_unit
            nkd = D('0')
        else:
            proceeds = amount(e['clean_price_unit'])
            nkd = amount(e.get('nkd_unit', '0'))
            if nkd:
                self._recognize_nkd(e, nkd, rate)
            elif self.last_nkd_unit:
                raise LegalEvidenceRequired('NKD_OMITTED_ON_DISPOSAL',
                                            ('Trade NKD and accrued income ledger',))
        fee = amount(e.get('fees_rub', '0'))
        # Positive OFZ-IN indexation already posted as interest must not be
        # duplicated as a price gain upon disposal. Case-specific law check remains.
        offset = self.indexation_recognized_unit if self.kind == 'OFZ_IN' else D('0')
        gain = self.quantity*(proceeds*rate-self.cost_unit_rub-offset) - fee
        self._record(e, 'PRICE_REALIZATION_CANDIDATE', gain,
                     'НК РФ ст.280 п.2–4, 281; exclude previously accrued indexation',
                     candidate_base='GENERAL_PROFIT_CANDIDATE')
        if self.kind == 'FX' and nkd and self.purchased_nkd_unit:
            diff = self.quantity*self.purchased_nkd_unit*(rate-self.buy_rate)
            self._record(e, 'PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED', diff,
                         'НК РФ ст.280, 328; require FX NKD legal analysis',
                         candidate_base=None)
        cash_received = self.quantity*(proceeds+nkd)*rate-fee
        self._cash(e, cash_received)
        self.quantity = D('0')
        self.closed = True

    def apply(self, e: dict[str, Any]):
        if not isinstance(e, dict) or not isinstance(e.get('id'), str) or not e['id']:
            raise ValueError('Unique nonempty event id required')
        if e['id'] in self.ids:
            raise ValueError('Duplicate event id')
        dt = date.fromisoformat(e['date'])
        if self.last_date and dt < self.last_date:
            raise ValueError('Events must be chronological')
        kind = e.get('type')
        if kind not in self.TYPE_EVENTS[self.kind]:
            raise LegalEvidenceRequired('UNSUPPORTED_COMPLEX_EVENT',
                                        ('Issue terms and applicable legal treatment',))
        if self.closed:
            raise LegalEvidenceRequired('ALREADY_DISPOSED', ('Trade confirmations',))
        if kind != 'BUY' and self.security_id is None:
            raise ValueError('Buy must be first')
        if self.security_id and e.get('security_id') != self.security_id:
            raise LegalEvidenceRequired('MULTI_ISSUE_UNSUPPORTED', ('Single ISIN per run',))
        if kind == 'BUY': self._buy(e)
        elif kind == 'ACCRUE': self._accrue(e)
        elif kind == 'COUPON': self._coupon(e)
        elif kind == 'INDEX': self._index(e)
        else: self._dispose(e, redeem=(kind == 'REDEEM'))
        self.last_date = dt
        self.ids.add(e['id'])

    def report(self) -> dict[str, Any]:
        candidates = sum((D(x['amount_rub']) for x in self.tax_rows), D('0'))
        cash = sum((D(x['synthetic_cash_rub']) for x in self.cash_rows), D('0'))
        if self.closed and candidates != cash:
            raise LegalEvidenceRequired('CLOSED_POSITION_RECONCILIATION_FAILED',
                (f'Candidate sum={candidates}; cash={cash}', 'Coupons, NKD, FX rates and documentation'))
        bases: dict[str, D] = {}
        for row in self.tax_rows:
            key = row['candidate_tax_base'] or 'UNCLASSIFIED_NOT_TAX_BASE'
            bases[key] = bases.get(key, D('0'))+D(row['amount_rub'])
        return {
            'security_id': self.security_id, 'kind': self.kind,
            'status': 'UNVERIFIED_LEGAL_EDITION',
            'final_tax_amount_rub': None,
            'legal_snapshot_date': '2026-10-14',
            'tax_entries': self.tax_rows, 'cash_flows': self.cash_rows,
            'candidate_base_totals_rub': {k:str(v) for k,v in bases.items()},
            'synthetic_cash_total_rub':str(cash),
            'synthetic_component_total_rub':str(candidates),
            'closed_position_reconciled':self.closed,
            'open_quantity':str(self.quantity),
            'unclassified_components_present':any(r['candidate_tax_base'] is None
                                                 for r in self.tax_rows),
            'required_documents':[
                'Full applicable Tax Code edition (arts. 250, 265, 271-272, 280-281, 284, 328), amendments',
                'Official issuer issue terms, coupon schedules and tax-accounting policy',
                'Official FX history and executed trade/cash statements if FX',
                'Historical indexed-nominal schedule and Minfin interpretations if OFZ-IN',
            ],
            'warning':'Cash reconciliation is not approval of tax classification or rates.'
        }


def run_advanced(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    if not isinstance(events, list) or not events:
        raise ValueError('Nonempty event list required')
    ledger = AdvancedBondLedger(kind)
    for event in events:
        ledger.apply(event)
    return ledger.report()


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('json_file', type=Path)
    args=cli.parse_args()
    payload=json.loads(args.json_file.read_text(encoding='utf-8'))
    try:
        print(json.dumps(run_advanced(payload['events'], payload['kind']), ensure_ascii=False, indent=2))
    except LegalEvidenceRequired as exc:
        print(json.dumps({'status':'BLOCKED','code':exc.code,
                          'required_documents':list(exc.documents),
                          'final_tax_amount_rub':None},ensure_ascii=False,indent=2))
        raise SystemExit(2) from None


if __name__ == '__main__': main()