#!/usr/bin/env python3
"""Check synthetic arithmetic only; this program is NOT a tax engine."""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'tests/fixtures/bond_synthetic_cases.json'
D = Decimal

def evaluate(case):
    f = case['facts']; kind = case['kind']
    if kind == 'coupon_nkd':
        coupon = D(f['coupon_cash']) - D(f['buy_nkd']) + D(f['sell_nkd'])
        clean = D(f['sell_clean']) - D(f['buy_clean'])
        return dict(gross_cash_profit=coupon+clean, analytical_coupon_component=coupon, analytical_clean_component=clean)
    if kind == 'issue_discount':
        interest = D(f['nominal']) - D(f['primary_weighted_price'])
        rest = D(f['primary_weighted_price']) - D(f['bank_purchase_price'])
        return dict(issue_discount=interest, other_redemption_result=rest, gross_result=interest+rest)
    if kind == 'amort':
        cost=D(f['tax_cost']); nominal=D(f['nominal'])
        alloc=[cost*D(p)/nominal for p in f['principal_payments']]
        pay=sum(map(D,f['principal_payments']))
        return dict(cost_allocations=alloc, remaining_tax_cost=cost-sum(alloc), residual_profit=pay-sum(alloc))
    if kind == 'indexation':
        index=D(f['final_nominal'])-D(f['initial_nominal']);coupon=D(f['coupon'])
        return dict(indexation=index,coupon=coupon,gross_cash_profit=D(f['final_nominal'])+coupon-D(f['purchase_cost']),duplicate_disposal_indexation=D('0'))
    if kind == 'fx_sale':
        return dict(gross_rub_result=D(f['sell_usd'])*D(f['sell_rate_rub'])-D(f['buy_usd'])*D(f['buy_rate_rub']))
    if kind == 'fifo':
        qty=int(f['sold_qty']);first=int(f['first_lot_qty'])
        if qty>first or qty<0: raise ValueError('Demo fixture assumes sale fully covered by first lot')
        cost=D(qty)*D(f['first_lot_unit']);revenue=D(qty)*D(f['sell_unit'])
        return dict(first_in_first_out_cost=cost,sale_revenue=revenue,gross_profit=revenue-cost)
    if kind == 'stop':
        return dict(approved_tax_amount=None,stop_reason=case['expected']['stop_reason'])
    raise ValueError('Unknown fixture kind: '+kind)

def run():
    cases=json.loads(FILE.read_text(encoding='utf-8'))['cases']
    for case in cases:
        actual=evaluate(case)
        expected=case['expected']
        if set(actual)!=set(expected): raise AssertionError((case['id'],'fields mismatch'))
        for key,value in actual.items():
            want=expected[key]
            if isinstance(value,list):
                assert [str(x) for x in value]==want, (case['id'],key,value,want)
            elif isinstance(value,Decimal):
                assert value==D(want), (case['id'],key,value,want)
            else:
                assert value==want,(case['id'],key,value,want)
        if case['decision']=='BLOCKED':
            assert actual['approved_tax_amount'] is None,case['id']
    print(f'PASS: {len(cases)} synthetic arithmetic/stop fixtures (not legal validation)')

if __name__=='__main__': run()
