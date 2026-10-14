# FX and OFZ-IN bond lifecycle — experimental research ledger

**Status: SYNTHETIC_ONLY / UNVERIFIED_LEGAL_EDITION. Not operational bank tax accounting.**

This module extends the original RUB ordinary coupon-bond ledger without changing its
validated synthetic scope. It introduces `scripts/advanced_bond_ledger.py` with two
**strictly separate modes**: `FX` and `OFZ_IN`. Neither mode produces final tax payable.

## Run

```bash
python scripts/advanced_bond_ledger.py examples/fx_lifecycle_synthetic.json
python scripts/advanced_bond_ledger.py examples/ofz_in_lifecycle_synthetic.json
python -m unittest discover -s tests -v
```

Python `Decimal` is used throughout; all event amounts are supplied as strings.
All events are strictly chronological and identified by unique `id` values. One run
means **one issue and one tax lot, disposed entirely**. Other shapes fail closed.

## FX mode — RUB translation, separate interest receivable

Supported: Russian-law **foreign-currency denominated and settled** ordinary coupon
bonds of **Russian corporate issuers**, with accrual-based coupons, one purchased tax lot and complete sale/redemption.
This does not include foreign issuers, special cash-receipt recognition under NK RF
271(4)(14.6), RUB settlement of FX nominal, withholding-agent determinations or
sale of part of a lot.

Events: `BUY`, `ACCRUE`, `COUPON`, `SELL`, `REDEEM`.

- The acquisition price (clean) is translated at the **historical RUB/FX rate** and is
  not revalued periodically merely because the currency rate moves. The disposition
  price uses its own applicable event rate. See NK RF art. 280(2)–(4).
- Coupon interest earned during the holding period is separated from purchased NKD.
  Its candidate ruble recognition is per-event accrued **increment in FX × rate**;
  separately calculated exchange differences on **already accrued currency coupon
  receivables** are shown as candidate FX items. This is not a claim that all coupon
  receivables are taxable on that date: verify applicable issue terms and NK RF arts.
  250, 265, 271–272, 328.
- The currency change in **purchased NKD** between acquisition and recovery is kept
  as `PURCHASED_NKD_FX_DIFFERENCE_UNCLASSIFIED`: it balances the synthetic cash flow,
  but is **not** included in any candidate taxable base until its legal character is
  independently established. The example deliberately contains one such item.
- There is no routine monthly tax revaluation of the bond principal (art. 280(4)).
  Revaluation of a separate accrued coupon receivable is not the same thing.
- **All FX rates in examples are invented for arithmetic illustration**. For a real
  bank trade obtain date-specific official rates, accounting dates and confirmations.

### Synthetic FX trace

| Component | RUB |
| --- | ---: |
| Coupon accrued while held | +3,770 |
| Candidate FX difference on coupon receivable | +30 |
| FX difference on purchased NKD — **UNCLASSIFIED** | +100 |
| Clean-price disposal result in RUB | +12,000 |
| Cash-flow total | **15,900** |

The `+100` must **not** be assigned automatically to taxable income, expense, or a
particular rate. A balanced cash ledger is only an arithmetic control.

## OFZ-IN mode — positive nominal indexation, no duplicate recognition

Supported: synthetic **Russian RUB OFZ with indexed nominal** under documented
issue terms, positive or unchanged nominal indexation only, fixed coupon and one
complete purchase-to-disposal lot.

Events: `BUY`, `INDEX`, `ACCRUE`, `COUPON`, `SELL`, `REDEEM`.

- Each `INDEX` event records the positive incremental nominal amount as a **candidate
  interest component**, relying on the subject-specific interpretation in Minfin
  14.07.2015 № 03-03-10/40395; confirm the effective edition and issue terms.
- The previously captured indexation amount is subtracted from candidate clean-price
  disposition result to guard against **double counting** the same nominal growth.
  This is a simplified synthetic reconciliation, not a substitute for statutory
  rules governing the tax cost of a real indexed issue.
- **Negative indexation immediately blocks** with
  `NEGATIVE_OFZ_INDEXATION_REVIEW`: see Minfin 13.12.2022 № 03-03-06/2/122113
  and any superseding positions. Do not simply post a negative expense.
- Index history is supplied by the user; the module does not independently fetch
  official daily/monthly indexed nominal data.

### Synthetic OFZ-IN trace

| Component | RUB |
| --- | ---: |
| Coupon | +20 |
| Indexed nominal income candidate | +20 |
| Disposition result after preventing double count | 0 |
| Cash-flow total | **40** |

## Hard legal gates and escalation

Before treating the output as a tax conclusion, independently verify the effective
edition of NK RF on **each event date**, amendments, transition clauses, rates and
issue terms. If full controlling text or the actual issue documentation cannot be
verified, request DOCX or searchable PDF copies from the user (e.g. ConsultantPlus)
and return `UNVERIFIED_LEGAL_EDITION` / `BLOCKED`. The researcher **must not** claim
that no changes exist merely because an online search found none.

Primary law: NK RF arts. 250, 265, 271–272, 280–281, 284, 328–329:
https://www.consultant.ru/document/cons_doc_LAW_28165/

Official legal publication: https://pravo.gov.ru/

Interpretative leads (NOT binding normative acts):
- Minfin 14.07.2015 № 03-03-10/40395 (OFZ-IN indexation)
- Minfin 13.12.2022 № 03-03-06/2/122113 (negative indexed nominal)
- Minfin 13.01.2025 № 03-03-06/2/975 (banks and FX differences)

No licensed full legal text or confidential bank transactions are committed.