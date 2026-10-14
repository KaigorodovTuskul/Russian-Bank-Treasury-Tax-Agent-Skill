#!/usr/bin/env python3
"""Research-only multi-lot event ledger for simple FX bonds and positive-index OFZ-IN.

No tax positions are approved. Every row is an arithmetic candidate tied to
an unverified legal interpretation; users must validate dated primary law.

Scope: one ISIN per run; purchase / accrual / coupon / INDEX (OFZ-IN) /
partial FIFO SELL / full REDEEM; Decimal amounts, no daily accrual inference.
"""
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

D = Decimal


class LedgerEvidenceRequired(ValueError):
    """A hard safety gate: data or law requires case-specific validation."""
    def __init__(self, code: str, needed: tuple[str, ...]):
        self.code, self.needed = code, needed
        super().__init__(f'{code}: {"; ".join(needed)}')


def number(value: Any, *, strictly_positive: bool = False) -> D:
    if value is None or isinstance(value, (bool, float)):
        raise ValueError('Use finite nonnegative decimal strings (not float/bool)')
    try:
        result = D(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f'Invalid decimal amount {value!r}') from exc
    if not result.is_finite() or result < 0 or (strictly_positive and result == 0):
        raise ValueError('Expected finite nonnegative amount' + (' > 0' if strictly_positive else ''))
    return result


def str_amount(v: D) -> str:
    return format(v, 'f')


@dataclass
class Lot:
    id: str
    units: D
    cost_unit_rub: D
    principal_unit: D
    acquired_nkd_unit: D
    acquired_fx_rate: D
    last_nkd_unit: D
    accrued_receivable_unit: D
    receivable_fx_rate: D
    coupon_period: str | None
    recognized_index_unit: D = D('0')


class MultiLotBondLedger:
    SUPPORTED = {
        'FX': {'BUY', 'ACCRUE', 'COUPON', 'SELL', 'REDEEM'},
        'OFZ_IN': {'BUY', 'INDEX', 'ACCRUE', 'COUPON', 'SELL', 'REDEEM'},
    }
    SOURCE = {
        'INTEREST_ACCRUAL_CANDIDATE': ('BND-NKD-LEDGER', 'НК РФ ст.271, 281, 284, 328'),
        'INDEXATION_INTEREST_CANDIDATE': ('BND-INDEXED-OFZ', 'НК РФ ст.281, 328; Минфин 14.07.2015 № 03-03-10/40395'),
        'PRICE_REALIZATION_CANDIDATE': ('BND-CLEAN-PRICE-RESULT', 'НК РФ ст.280, 281, 329'),
        'FX_INTEREST_RECEIVABLE_REVALUATION_CANDIDATE': ('BND-FX-NO-REVALUE', 'НК РФ ст.250, 265, 271–272, 280; specific receivable'),
        'PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED': ('BND-NKD-LEDGER', 'НК РФ ст.280, 328; additional classification required'),
    }

    def __init__(self, kind: str):
        if kind not in self.SUPPORTED:
            raise ValueError('kind must be FX or OFZ_IN')
        self.kind = kind
        self.security_id: str | None = None
        self.currency: str | None = None
        self.principal_unit: D | None = None
        self.lots: list[Lot] = []
        self.all_lot_ids: set[str] = set()
        self.closed_coupon_periods: set[str] = set()
        self.active_coupon_period: str | None = None
        self.rows: list[dict[str, Any]] = []
        self.cash: list[dict[str, str]] = []
        self.applied_ids: set[str] = set()
        self.last_date: date | None = None
        self.last_event_type: str | None = None
        self.maturity_redeemed = False

    def _amount_at_event_rate(self, e: dict[str, Any]) -> D:
        return number(e['rub_per_nominal_currency'], strictly_positive=True) if self.kind == 'FX' else D('1')

    def _record(self, e: dict[str, Any], lot: Lot, component: str, value: D,
                candidate_base: str | None) -> None:
        if value == 0:
            return
        rule, provision = self.SOURCE[component]
        if component == 'INTEREST_ACCRUAL_CANDIDATE' and self.kind == 'OFZ_IN':
            rule = 'BND-OFZ-INT-20'
        if component == 'PRICE_REALIZATION_CANDIDATE' and self.kind == 'FX':
            rule = 'BND-FX-NO-REVALUE'
        self.rows.append({
            'event_id':e['id'], 'date':e['date'], 'security_id':self.security_id,
            'lot_id':lot.id, 'component':component,
            'amount_rub':str_amount(value), 'candidate_tax_base':candidate_base,
            'rule_id':rule, 'source_reference':provision,
            'verification_status':('UNCLASSIFIED_REQUIRES_DOCUMENTS' if candidate_base is None
                                   else 'UNVERIFIED_LEGAL_EDITION'),
            'approved_tax_amount_rub':None,
        })

    def _cash(self, e: dict, value: D) -> None:
        self.cash.append({'event_id':e['id'], 'date':e['date'],
                          'cash_flow_rub':str_amount(value)})

    def _period(self, e: dict) -> str:
        period = e.get('coupon_period')
        if not isinstance(period,str) or not period.strip():
            raise ValueError('coupon_period is required')
        if period in self.closed_coupon_periods:
            raise LedgerEvidenceRequired('COUPON_PERIOD_ALREADY_CLOSED',
                                         ('Complete coupon payment schedule',))
        if self.active_coupon_period is None:
            self.active_coupon_period = period
        if period != self.active_coupon_period:
            raise LedgerEvidenceRequired('COUPON_PERIOD_MISMATCH',
                                         (f'Expected {self.active_coupon_period}', 'Issue coupon schedule'))
        return period

    def _accrue_lot(self, e: dict, lot: Lot, target_nkd: D, rate: D) -> None:
        if target_nkd < lot.last_nkd_unit:
            raise LedgerEvidenceRequired('NKD_DECREASE_WITHOUT_COUPON',
                                         ('Coupon calendar', 'Accrued interest confirmations'))
        if self.kind == 'FX' and lot.accrued_receivable_unit:
            fx_change = lot.units*lot.accrued_receivable_unit*(rate-lot.receivable_fx_rate)
            self._record(e,lot,'FX_INTEREST_RECEIVABLE_REVALUATION_CANDIDATE',
                         fx_change,'GENERAL_FX_CANDIDATE')
        incremental = target_nkd-lot.last_nkd_unit
        self._record(e,lot,'INTEREST_ACCRUAL_CANDIDATE',lot.units*incremental*rate,
                     'GENERAL_INTEREST_CANDIDATE' if self.kind == 'FX'
                     else 'SPECIAL_INTEREST_CANDIDATE')
        lot.accrued_receivable_unit += incremental
        lot.receivable_fx_rate = rate
        lot.last_nkd_unit = target_nkd

    def _validate_buy(self, e: dict, nominal: D) -> str:
        if self.kind == 'FX':
            c = e.get('nominal_currency')
            if (not isinstance(c,str) or len(c) != 3 or not c.isalpha() or not c.isupper()
                or c == 'RUB' or e.get('settlement_currency') != c
                or e.get('issuer_law') != 'RU' or e.get('issuer_class') != 'RU_CORPORATE'
                or e.get('coupon_recognition_method') != 'ACCRUAL'):
                raise LedgerEvidenceRequired('FX_INSTRUMENT_NOT_SUPPORTED',
                    ('Russian corporate issue terms', 'FX-settlement evidence',
                     'Accrual-based coupon treatment under effective law'))
            currency = c
        else:
            if e.get('nominal_currency') != 'RUB' or e.get('security_kind') != 'OFZ_IN':
                raise LedgerEvidenceRequired('OFZ_IN_ISSUE_NOT_ESTABLISHED',
                                             ('Official indexed government bond terms',))
            currency = 'RUB'
        if self.currency is not None and currency != self.currency:
            raise LedgerEvidenceRequired('ISSUE_CURRENCY_MISMATCH', ('Single-issue currency specification',))
        if self.principal_unit is not None and self.principal_unit != nominal:
            raise LedgerEvidenceRequired('NOMINAL_AT_PURCHASE_MISMATCH',
                ('Historical nominal index schedule on purchase date',
                 'Principal amount per security at settlement'))
        return currency

    def _buy(self,e:dict) -> None:
        lot_id=e.get('lot_id')
        if not isinstance(lot_id,str) or not lot_id.strip() or lot_id in self.all_lot_ids:
            raise ValueError('Unique nonempty lot_id required across entire input')
        units=number(e['quantity'],strictly_positive=True)
        clean,nkd,nominal,fees=(number(e['clean_price_unit']),number(e['nkd_unit']),
                                 number(e['nominal_unit'],strictly_positive=True),
                                 number(e.get('fees_rub','0')))
        currency=self._validate_buy(e,nominal)
        rate=self._amount_at_event_rate(e)
        if self.active_coupon_period is not None and e.get('coupon_period') != self.active_coupon_period:
            raise LedgerEvidenceRequired('COUPON_PERIOD_MISMATCH', ('Uniform coupon period per issue',))
        if nkd:
            self._period(e)
        elif e.get('coupon_period') and e['coupon_period'] in self.closed_coupon_periods:
            raise LedgerEvidenceRequired('COUPON_PERIOD_ALREADY_CLOSED',('Coupon schedule',))
        self.currency=currency
        if self.principal_unit is None:
            self.principal_unit=nominal
        lot=Lot(lot_id,units,clean*rate+fees/units,nominal,nkd,rate,nkd,D('0'),rate,
                e.get('coupon_period'))
        self.lots.append(lot)
        self.all_lot_ids.add(lot_id)
        self._cash(e,-(units*(clean+nkd)*rate+fees))

    def _accrue(self,e:dict) -> None:
        self._period(e)
        target=number(e['nkd_unit'])
        rate=self._amount_at_event_rate(e)
        for lot in self.lots:
            self._accrue_lot(e,lot,target,rate)
            lot.coupon_period=self.active_coupon_period
        self._cash(e,D('0'))

    def _coupon(self,e:dict) -> None:
        period=self._period(e)
        coupon=number(e['coupon_unit'])
        rate=self._amount_at_event_rate(e)
        cash=D('0')
        for lot in self.lots:
            if coupon < lot.last_nkd_unit:
                raise LedgerEvidenceRequired('COUPON_BELOW_RECORDED_NKD',
                    ('Coupon entitlement records','Issuer payment schedule'))
            self._accrue_lot(e,lot,coupon,rate)
            if self.kind == 'FX' and lot.acquired_nkd_unit:
                unclassified=lot.units*lot.acquired_nkd_unit*(rate-lot.acquired_fx_rate)
                self._record(e,lot,'PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED',
                             unclassified,None)
            cash += lot.units*coupon*rate
            lot.last_nkd_unit=D('0')
            lot.acquired_nkd_unit=D('0')
            lot.accrued_receivable_unit=D('0')
            lot.receivable_fx_rate=rate
            lot.coupon_period=None
        self._cash(e,cash)
        self.closed_coupon_periods.add(period)
        self.active_coupon_period=None

    def _index(self,e:dict) -> None:
        new_nominal=number(e['indexed_nominal_unit'],strictly_positive=True)
        if new_nominal < self.principal_unit:
            raise LedgerEvidenceRequired('NEGATIVE_INDEXATION_REVIEW',
                ('Complete OFZ-IN terms','Minfin 13.12.2022 №03-03-06/2/122113',
                 'Effective applicable Tax Code edition'))
        delta=new_nominal-self.principal_unit
        for lot in self.lots:
            self._record(e,lot,'INDEXATION_INTEREST_CANDIDATE',lot.units*delta,
                         'SPECIAL_INTEREST_CANDIDATE')
            lot.recognized_index_unit+=delta
            lot.principal_unit=new_nominal
        self.principal_unit=new_nominal
        self._cash(e,D('0'))

    def _sell(self,e:dict) -> None:
        units=number(e['quantity'],strictly_positive=True)
        if units > sum((lot.units for lot in self.lots),D('0')):
            raise ValueError('Insufficient holdings for FIFO disposal')
        clean,nkd,fees=(number(e['clean_price_unit']),number(e['nkd_unit']),
                        number(e.get('fees_rub','0')))
        rate=self._amount_at_event_rate(e)
        # All active holdings experience the same issuer NKD curve, including lots
        # that remain open after this sale; recognize their month/event accrual too.
        self._period(e)
        for lot in self.lots:
            self._accrue_lot(e,lot,nkd,rate)
        sold=D('0')
        for lot in list(self.lots):
            take=min(units-sold,lot.units)
            if take == 0:
                break
            offset=lot.recognized_index_unit if self.kind == 'OFZ_IN' else D('0')
            price_gain=take*(clean*rate-lot.cost_unit_rub-offset)-fees*take/units
            self._record(e,lot,'PRICE_REALIZATION_CANDIDATE',price_gain,
                         'GENERAL_PROFIT_CANDIDATE')
            if self.kind == 'FX' and lot.acquired_nkd_unit:
                currency_diff=take*lot.acquired_nkd_unit*(rate-lot.acquired_fx_rate)
                self._record(e,lot,'PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED',
                             currency_diff,None)
            lot.units-=take
            sold+=take
            if lot.units == 0:
                self.lots.remove(lot)
        self._cash(e,units*(clean+nkd)*rate-fees)
        if not self.lots:
            self.active_coupon_period=None

    def _redeem(self,e:dict) -> None:
        if 'quantity' in e and number(e['quantity'],strictly_positive=True) != sum((x.units for x in self.lots),D('0')):
            raise LedgerEvidenceRequired('PARTIAL_REDEMPTION_UNSUPPORTED',
                                         ('Issue principal amortization terms',))
        if any(lot.last_nkd_unit or lot.accrued_receivable_unit for lot in self.lots):
            raise LedgerEvidenceRequired('FINAL_COUPON_NOT_SETTLED',
                                         ('Final coupon/NKD cash confirmations',))
        if 'redemption_cash_unit' in e:
            raise LedgerEvidenceRequired('NONSTANDARD_REDEMPTION_UNSUPPORTED',
                                         ('Call/put premium and issue terms',))
        rate=self._amount_at_event_rate(e)
        cash=D('0')
        for lot in self.lots:
            nominal=lot.principal_unit
            offset=lot.recognized_index_unit if self.kind == 'OFZ_IN' else D('0')
            self._record(e,lot,'PRICE_REALIZATION_CANDIDATE',
                         lot.units*(nominal*rate-lot.cost_unit_rub-offset),
                         'GENERAL_PROFIT_CANDIDATE')
            cash+=lot.units*nominal*rate
        self._cash(e,cash)
        self.lots.clear()
        self.active_coupon_period=None
        self.maturity_redeemed=True

    def _apply_unchecked(self,e:dict[str,Any]) -> None:
        if not isinstance(e,dict):
            raise ValueError('Event must be an object')
        eid,typ,dt_s=e.get('id'),e.get('type'),e.get('date')
        if not isinstance(eid,str) or not eid.strip() or eid in self.applied_ids:
            raise ValueError('Nonempty unique event ID required')
        if not isinstance(dt_s,str):
            raise ValueError('Date required')
        dt=date.fromisoformat(dt_s)
        if self.last_date and dt < self.last_date:
            raise ValueError('Events must be chronological')
        if typ not in self.SUPPORTED[self.kind]:
            raise LedgerEvidenceRequired('UNSUPPORTED_INSTRUMENT_OR_EVENT',
                    (f'Issue terms/event {typ}', 'Tax Code effective on event date'))
        issue=e.get('security_id')
        if not isinstance(issue,str) or not issue.strip():
            raise ValueError('security_id required')
        if self.security_id and self.security_id != issue:
            raise LedgerEvidenceRequired('MULTIPLE_SECURITIES_NOT_SUPPORTED',
                                         ('One ISIN per ledger; invoke separately',))
        if self.maturity_redeemed:
            raise LedgerEvidenceRequired('ISSUE_ALREADY_REDEEMED',('Maturity schedule',))
        if typ != 'BUY' and not self.lots:
            raise ValueError('No holding for this event')
        if self.security_id is None:
            self.security_id=issue
        handler=getattr(self,'_'+typ.lower())
        handler(e)
        self.applied_ids.add(eid)
        self.last_date=dt
        self.last_event_type=typ

    def apply(self,e:dict[str,Any]) -> None:
        """Transactional event application: invalid events cannot corrupt position state."""
        original=copy.deepcopy(self.__dict__)
        try:
            self._apply_unchecked(e)
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(original)
            raise

    def report(self) -> dict[str,Any]:
        total_candidate=sum((D(r['amount_rub']) for r in self.rows),D('0'))
        cash_total=sum((D(r['cash_flow_rub']) for r in self.cash),D('0'))
        closed=bool(self.applied_ids) and not self.lots
        if closed and total_candidate != cash_total:
            raise LedgerEvidenceRequired('LIFECYCLE_RECONCILIATION_FAILED',
                (f'cash={str_amount(cash_total)}; components={str_amount(total_candidate)}',
                 'Per-lot NKD, historical FX rates, indexed nominal, cash statements'))
        candidate_bases:dict[str,D]={}
        for r in self.rows:
            category=r['candidate_tax_base'] or 'UNCLASSIFIED_NOT_TAX_BASE'
            candidate_bases[category]=candidate_bases.get(category,D('0'))+D(r['amount_rub'])
        positions=[{'lot_id':lot.id,'units':str_amount(lot.units),
                    'cost_unit_rub':str_amount(lot.cost_unit_rub),
                    'remaining_tax_cost_rub':str_amount(lot.units*lot.cost_unit_rub),
                    'principal_unit':str_amount(lot.principal_unit),
                    'purchased_nkd_unit':str_amount(lot.acquired_nkd_unit),
                    'last_nkd_unit':str_amount(lot.last_nkd_unit),
                    'recognized_indexation_unit':str_amount(lot.recognized_index_unit)}
                   for lot in self.lots]
        return {'kind':self.kind,'security_id':self.security_id,
                'status':'UNVERIFIED_LEGAL_EDITION','final_tax_amount_rub':None,
                'as_of_snapshot':'2026-10-14','event_count':len(self.applied_ids),
                'tax_entries':self.rows,'cash_flows':self.cash,
                'candidate_base_totals_rub':{k:str_amount(v) for k,v in candidate_bases.items()},
                'candidate_component_total_rub':str_amount(total_candidate),
                'net_cash_flow_rub':str_amount(cash_total),
                'closed_position_reconciled':closed,
                'positions':positions,
                'unclassified_components_present':any(r['candidate_tax_base'] is None for r in self.rows),
                'missing_documents':[
                    'Full dated NK RF edition and amending/transitional provisions',
                    'Full bond issue/coupon/indexation terms and trade confirmations',
                    'Official FX rates and tax accounting policy where applicable',
                    'OFZ-IN nominal index chronology and Minfin clarifications where applicable'],
                'note':'Synthetic FIFO arithmetic only. No approved tax; real-world event rights and rates must be verified.'}


def run_multilot(events:list[dict[str,Any]],kind:str) -> dict[str,Any]:
    if not isinstance(events,list) or not events:
        raise ValueError('Nonempty list of events required')
    ledger=MultiLotBondLedger(kind)
    for event in events:
        ledger.apply(event)
    return ledger.report()


def main() -> None:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('json_file',type=Path)
    ns=cli.parse_args()
    data=json.loads(ns.json_file.read_text(encoding='utf-8'))
    try:
        result=run_multilot(data['events'],data['kind'])
    except LedgerEvidenceRequired as exc:
        result={'status':'BLOCKED','reason_code':exc.code,
                'missing_documents':list(exc.needed),'final_tax_amount_rub':None}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(2) from None
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
