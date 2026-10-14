#!/usr/bin/env python3
"""Pure Decimal bond calculations plus conservative tax-rule evidence gate.

Synthetic arithmetic only. Executing this file never approves a tax position.
"""
from __future__ import annotations
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

D = Decimal
RULE_FILE = (Path(__file__).resolve().parents[1] /
             'skills/russian-bank-treasury-tax/data/bond_tax_rules_2026.json')


class EvidenceRequired(ValueError):
    def __init__(self, code: str, documents: Iterable[str]):
        self.code = code
        self.documents = tuple(documents)
        super().__init__(f'{code}: {", ".join(self.documents)}')


def dec(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError('Boolean is not a monetary value')
    try:
        out = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('Invalid decimal value') from exc
    if not out.is_finite():
        raise ValueError('Non-finite decimal value')
    return out


def rate_effect(base: Any, percent: Any, *, loss_usable: bool = False) -> Decimal:
    """Incremental illustrative tax effect, NOT payable tax or an approved benefit."""
    b, r = dec(base), dec(percent)
    if not 0 <= r <= 100:
        raise ValueError('Rate outside 0..100')
    if b < 0 and not loss_usable:
        raise EvidenceRequired('LOSS_OFFSET_UNVERIFIED',
                               ('tax base', 'loss-offset eligibility', 'tax register'))
    return b * r / D('100')


def coupon_nkd(coupon_cash: Any, purchased_nkd: Any, sold_nkd: Any = 0) -> Decimal:
    """Simplified interest = one coupon payment - purchased NKD + sold NKD."""
    coupon, purchased, sold = map(dec, (coupon_cash, purchased_nkd, sold_nkd))
    if min(coupon, purchased, sold) < 0 or purchased > coupon:
        raise ValueError('Inconsistent NKD/coupon for this simplified scenario')
    return coupon - purchased + sold


def clean_price_result(buy_clean: Any, sell_clean: Any,
                       allowable_costs: Any = 0) -> Decimal:
    buy, sell, costs = map(dec, (buy_clean, sell_clean, allowable_costs))
    if min(buy, sell, costs) < 0:
        raise ValueError('Negative price/cost')
    return sell - buy - costs


def split_issue_discount(nominal: Any, weighted_primary_price: Any,
                         actual_bank_cost: Any) -> Dict[str, Decimal]:
    nom, primary, cost = map(dec, (nominal, weighted_primary_price, actual_bank_cost))
    if nom <= 0 or primary <= 0 or cost <= 0 or primary > nom:
        raise ValueError('Invalid simplified zero-coupon issue assumptions')
    return {'issue_interest': nom-primary,
            'other_redemption_result': primary-cost,
            'total_economic_result': nom-cost}


def amortization_allocations(tax_cost: Any, principal_remaining_at_purchase: Any,
                             principal_received: Iterable[Any]) -> Dict[str, Any]:
    cost, remaining = dec(tax_cost), dec(principal_remaining_at_purchase)
    payments = [dec(p) for p in principal_received]
    if cost < 0 or remaining <= 0 or not payments or any(p <= 0 for p in payments):
        raise ValueError('Invalid amortization inputs')
    if sum(payments) > remaining:
        raise ValueError('Principal payments exceed remaining post-acquisition principal')
    allocations = [cost*p/remaining for p in payments]
    return {'cost_allocations': allocations,
            'realized_gains': [p-a for p, a in zip(payments, allocations)],
            'remaining_cost': cost-sum(allocations)}


def fx_sale_result(buy_fx_amount: Any, buy_rub_fx: Any,
                   sell_fx_amount: Any, sell_rub_fx: Any) -> Dict[str, Decimal]:
    buy, rate_buy, sell, rate_sell = map(
        dec, (buy_fx_amount, buy_rub_fx, sell_fx_amount, sell_rub_fx))
    if min(buy, rate_buy, sell, rate_sell) < 0:
        raise ValueError('Negative amount or exchange rate')
    cost, proceeds = buy*rate_buy, sell*rate_sell
    return {'purchase_rub': cost, 'proceeds_rub': proceeds,
            'realized_result_rub': proceeds-cost,
            'monthly_bond_fx_revaluation_rub': D('0')}


def fifo_disposal(lots: Iterable[Tuple[Any, Any]], quantity: Any,
                  sale_price: Any) -> Dict[str, Decimal]:
    qty, price = dec(quantity), dec(sale_price)
    if qty <= 0 or price < 0:
        raise ValueError('Invalid sale')
    remaining, cost = qty, D('0')
    for raw_units, raw_price in lots:
        units, unit_price = dec(raw_units), dec(raw_price)
        if units <= 0 or unit_price < 0:
            raise ValueError('Invalid lot')
        taken = min(remaining, units)
        cost += taken*unit_price
        remaining -= taken
        if remaining == 0:
            break
    if remaining:
        raise ValueError('Insufficient lot quantity')
    proceeds = qty*price
    return {'cost': cost, 'proceeds': proceeds, 'gain': proceeds-cost}


def indexed_principal(principal_start: Any, principal_end: Any, coupon: Any,
                      tax_purchase_cost: Any, redemption_cash: Any,
                      previously_recognized_indexation: Any) -> Dict[str, Decimal]:
    start, end, cp, cost, cash, prior = map(dec, (
        principal_start, principal_end, coupon, tax_purchase_cost,
        redemption_cash, previously_recognized_indexation))
    if end < start:
        raise EvidenceRequired('NEGATIVE_INDEXATION_REVIEW',
                               ('applicable OFZ-IN issue terms',
                                'Minfin interpretations', 'dated NK RF'))
    if start <= 0 or cp < 0 or cost < 0 or prior != end-start:
        raise ValueError('Indexation ledger does not reconcile')
    interest = cp+prior
    cash_profit = cash+cp-cost
    price_gain_after_exclusion = cash-cost-prior
    if interest+price_gain_after_exclusion != cash_profit:
        raise ValueError('Double recognition of indexed principal')
    return {'indexation_interest': prior, 'coupon_interest': cp,
            'total_interest': interest, 'taxable_price_gain': price_gain_after_exclusion,
            'economic_profit': cash_profit}


def rule_gate(rule_id: str, event_date: str, *, source_edition_verified: bool = False,
              predicates_verified: bool = False) -> Dict[str, Any]:
    """A flag never verifies documents. External legal review is still required."""
    date.fromisoformat(event_date)
    data = json.loads(RULE_FILE.read_text(encoding='utf-8'))
    rule = next((r for r in data['rules'] if r['id'] == rule_id), None)
    if rule is None:
        raise KeyError(rule_id)
    if rule['readiness'] == 'hard_stop':
        status = 'BLOCKED_COMPLEX_LEGAL_EVENT'
    elif rule['valid_from'] and event_date < rule['valid_from']:
        status = 'HISTORICAL_EDITION_REQUIRED'
    elif not source_edition_verified:
        status = 'UNVERIFIED_LEGAL_EDITION'
    elif not predicates_verified:
        status = 'MISSING_ELIGIBILITY_EVIDENCE'
    else:
        status = 'PROVISIONAL_PENDING_HUMAN_REVIEW'
    return {'rule_id': rule_id, 'event_date': event_date,
            'snapshot_date': rule['as_of'], 'status': status,
            'rate_percent': rule['rate_percent'], 'source': rule['primary_provision'],
            'missing_documents': [] if status == 'PROVISIONAL_PENDING_HUMAN_REVIEW'
            else ['full applicable Tax Code edition and amendment acts',
                  'issuer issue terms / bank tax registers as applicable'],
            'approved_tax_amount': None}


def refuse_complex_event(event_type: str) -> None:
    documents = {
        'replacement': ('original and replacement terms', 'exchange confirmations',
                        'applicable articles 251, 270, 280 and amending act'),
        'nontraded_loss': ('professional securities licence',
                           'market-status evidence', 'tax bases and carryforwards'),
        'cancelled_coupon': ('issue terms', 'issuer coupon cancellation decision',
                             'prior interest tax ledger'),
        'subordinated_write_down': ('issue terms',
                                    'legally effective write-down document',
                                    'market status and tax cost ledger'),
        'cross_border_nkd': ('counterparty residence and income recipient',
                             'applicable treaty/suspensions', 'articles 309-312'),
    }
    if event_type not in documents:
        raise ValueError('Unknown complex event')
    raise EvidenceRequired('LEGAL_REVIEW_REQUIRED_' + event_type.upper(),
                           documents[event_type])
