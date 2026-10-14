# Event-sourced bond tax research ledger (v0.2 draft)

The experimental [`bond_ledger.py`](../scripts/bond_ledger.py) accepts a **chronological list of one security's events** and produces audit-friendly, provisional tax-component rows, FIFO lot balances, cash flows and a reconciliation for fully closed positions. It uses **exact `Decimal` arithmetic**, the dated hard-coded rule catalog and explicit source IDs. It is **not** an authoritative tax register and cannot determine the bank's actual tax payable.

## Supported subset (intentionally narrow)

- One **RUB-denominated, RUB-settled, traded** ordinary coupon bond per invocation. The `TRADED` field is an input assertion, **not verified market evidence**.
- Bank holds the security in its **own** book. Purchase lots and FIFO sales are supported. The bank's tax accounting policy **must independently confirm FIFO** before using these calculations operationally.
- `BUY`: clean price, acquired NKD, allowable purchase fees, initial remaining nominal, issue coupon-period ID and candidate coupon rule ID.
- `ACCRUE`: new **cumulative NKD per unit** in the specified period, typically at month-end; adds only the increment since the previous observation for each active lot.
- `COUPON`: actual cash coupon per unit and corresponding period; recognises only previously unrecognised interest, resets cumulative NKD tracking and prevents duplicate payment for a period.
- `AMORTIZE`: partial principal **cash** repayment; proportionally releases remaining tax cost by lot, adjusting remaining nominal.
- `SELL`: FIFO partial/full sale, clean price, seller NKD, selling fee; separates incremental interest from clean-price result, preserves remaining lots.
- `REDEEM`: ordinary final principal repayment **after** any accrued coupon has been fully processed; releases remaining lot costs.

Unsupported events or complicated terms — FX issues, indexed principal, structural payments, replacement, write-down, subordination-driven loss, cancelled coupons, non-traded paper, nonresident withholding, nonstandard call premium — **STOP** with required documents. See [`source-workflow.md`](../skills/russian-bank-treasury-tax/references/source-workflow.md).

## Run an example

```bash
python scripts/bond_ledger.py examples/bond_lifecycle_t01.json
python -m unittest discover -s tests -v
```

The synthetic T01 case produces:

| Income component | Amount (RUB) | Candidate tax treatment |
| --- | ---: | --- |
| January accrued interest | 15 | OФЗ interest, candidate 20% |
| Interest at coupon payment | 15 | OФЗ interest, candidate 20% |
| February accrued interest | 10 | OФЗ interest, candidate 20% |
| Interest at sale | 2 | OФЗ interest, candidate 20% |
| Clean-price gain at sale | 10 | General income, candidate 25% |
| **Total** | **52** | **Not a final tax calculation** |

Cash reconciliation: `−1,010 (BUY) + 60 (COUPON) + 1,002 (SELL) = 52 RUB`. No double recognition of acquired NKD or previously accrued coupon. All rate interpretations remain provisional pending legal edition and rule-eligibility verification.

## Input and output controls

- Input: UTF-8 JSON with `events` list, ISO-8601 `date`, unique `id`, one `security_id`, and decimal amounts encoded as strings. No floats are required.
- Event time ordering matters for events with the same date. The engine **does not sort** and rejects decreasing dates.
- Each event carries an audit ID, tax component and amount; each tax row carries `rule_id`, `primary_provision` and `legal_status=UNVERIFIED_LEGAL_EDITION`.
- The result always sets `approved_tax_amount_rub=null`; negative gains are **not** credited against current tax without independent loss-base analysis.
- A fully closed position checks `net_cash_flow_rub == recognized_result_rub`. An open position does **not** assert economic reconciliation, because cash, remaining principal tax cost and accrued interest are unsettled.
- The engine **does not generate missing monthly accrual events**, source-check external NKD, prove market status, determine actual issuer eligibility, validate tax-basis/loss offset, calculate tax penalties, confirm statutory rate history, or independently access ConsultantPlus/GARANT.
- For any actual case, **first** verify the complete legal edition effective on each event date (including amending acts and transition rules). If the text is inaccessible, request it from the user. A rule in the catalog is only a dated research hypothesis until that source check is complete.

## Change management

Add a new instrument subtype by writing explicit versioned source-backed rules, deterministic unit tests and lifecycle events. Do not bypass the `BLOCKED` status with a user-provided boolean such as `all_legal_conditions_satisfied=true`. Store proof metadata and have a qualified reviewer approve its application before generating operational tax outputs.