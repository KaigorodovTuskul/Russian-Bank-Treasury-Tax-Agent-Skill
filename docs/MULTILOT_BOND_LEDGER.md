# Multi-lot FX and OFZ-IN bond ledger — research preview

**Status:** `SYNTHETIC_ONLY / UNVERIFIED_LEGAL_EDITION`. This module computes reproducible candidate RUB components but **never an approved tax amount**. The final Legal Judge Test and human tax-expert review have been deferred. Do not post tax entries, determine actual withholding, file returns or trade on this output.

## Purpose and supported scope

[`scripts/multilot_bond_ledger.py`](../scripts/multilot_bond_ledger.py) processes **one synthetic security per invocation**, including an arbitrary number of acquisition lots in FIFO order. It extends, but does not silently replace, the existing conservative single-lot [`advanced_bond_ledger.py`](../scripts/advanced_bond_ledger.py).

| Feature | FX mode | OFZ_IN mode |
| --- | --- | --- |
| Multiple acquisition lots; different unit prices and purchased NKD | Yes | Yes |
| Multiple buy dates; FIFO partial sales across lots | Yes | Yes |
| Historical acquisition exchange rate per lot | Yes | N/A (RUB) |
| Per-lot interest/NKD accrual and purchased-NKD FX differences | Yes | Per-lot RUB NKD |
| Per-lot accrued-interest receivable exchange differences | Candidate only | N/A |
| Positive indexed nominal, second purchase after index increase | N/A | Yes |
| Exclude previously recognized indexation from realized price result | N/A | Candidate only |
| Coupon cash and full remaining-balance maturity redemption | Yes | Yes |
| Partial *issuer* principal amortization / call premium | **BLOCKED** | **BLOCKED** |
| Negative OFZ-IN indexation / foreign issuer / RUB settlement of FX nominal | **BLOCKED** | **BLOCKED** |
| Accounting for tax-agent withholding, treaties, special cash-interest recognition | **NOT IMPLEMENTED** | **NOT IMPLEMENTED** |
| Automatic verification of legal editions or download of official rates/ISIN terms | **NOT IMPLEMENTED** | **NOT IMPLEMENTED** |

The FX mode is restricted to **ordinary FX-settled, Russian-law, Russian corporate issuer bonds with hypothetical accrual-based coupon recognition**. This intentionally excludes foreign issuer debt, offshore eurobonds and special timing rules that might otherwise invalidate the model.

## How to run

From repository root, Python 3.10+ (no third-party packages):

```bash
python scripts/multilot_bond_ledger.py examples/fx_multilot_synthetic.json
python scripts/multilot_bond_ledger.py examples/ofz_in_multilot_synthetic.json
python -m unittest discover -s tests -v
```

The input must be a JSON object containing `kind: "FX" | "OFZ_IN"` and a chronological `events` array with **unique** event IDs. Use **decimal strings** for monetary quantities and exchange rates, not floats. `security_id` must remain constant across all events. Events can share a date; their input order then determines processing sequence.

### Common event schema

| Event | Required fields (in addition to `id`, `date`, `type`, `security_id`) | Treatment |
| --- | --- | --- |
| `BUY` | `lot_id`, `quantity`, `clean_price_unit`, `nkd_unit`, `nominal_unit`, instrument descriptors, FX rate if applicable | Append a new FIFO lot with historical RUB clean-cost basis and bought NKD |
| `ACCRUE` | `coupon_period`, `nkd_unit`, FX rate if applicable | Recognize changes in accrued income *separately for each open lot* and FX receivable changes (FX only) |
| `COUPON` | `coupon_period`, `coupon_unit`, FX rate if applicable | Receive coupon on remaining positions, settle accrued coupon and purchased NKD, reset period state |
| `SELL` | `coupon_period`, `quantity`, `clean_price_unit`, `nkd_unit`, optional `fees_rub`, FX rate if applicable | Accrue interest for outstanding lots, consume FIFO tax lots, recognize realized price components |
| `INDEX` (OFZ-IN only) | `indexed_nominal_unit` | Increase indexed principal for open holdings and candidate interest; negative indexation hard-stops |
| `REDEEM` | FX rate if applicable | Redeem **all remaining units** at stated principal and remove candidate previously recognized indexation |

FX buys additionally require `nominal_currency`, matching `settlement_currency`, `issuer_law: "RU"`, `issuer_class: "RU_CORPORATE"`, `coupon_recognition_method: "ACCRUAL"`. OFZ-IN buys require `nominal_currency: "RUB"` and `security_kind: "OFZ_IN"`. For a buy **after** a previous `INDEX`, set `nominal_unit` to the then-current indexed nominal, not the original face value.

## Formulas — mathematical only, not legal conclusions

Let `q` be the number of securities in one lot; `P` the clean unit purchase price in original currency; `r_b` the RUB/FX rate on purchase; `f_b` the allocated RUB commission; `N_b` purchased NKD; `N_t` later NKD; `r_t` a dated RUB/FX rate.

- **Historical clean tax-cost candidate:** `C_lot_unit = P × r_b + f_b / q` (in RUB). It is *not* revalued merely because FX rates change.
- **Interest accrual candidate:** `q_current × (N_t − N_prior) × r_t`. An already recognized FX coupon receivable is revalued separately: `q_current × R_prior × (r_t − r_prior)`.
- **Bought NKD FX difference:** `q_disposed × N_b × (r_disposal − r_b)` or, for a coupon receipt, `q_current × N_b × (r_coupon − r_b)`. This is **UNCLASSIFIED_NOT_TAX_BASE** until actual legal qualification is verified.
- **Clean-price FIFO result (FX):** `q_disposed × (P_sale × r_sale − C_lot_unit) − allocated_sale_fee_rub`.
- **OFZ-IN indexation:** `q_current × (N_nominal_new − N_nominal_old)`, strictly when nonnegative. A lot purchased after some indexation begins recognizing future indexation **only** from its own acquisition date.
- **OFZ-IN realized candidate:** `q_disposed × (P_sale − C_lot_unit − indexation_recognized_since_lot_buy) − allocated_fee`.
- **Partial FIFO:** oldest lot units are depleted first; unsold units retain their per-unit historical cost, acquired NKD and indexed nominal histories.

**Critical assumptions:** accrued NKD curves are supplied; coupon rights, ex-coupon dates, traded-market status, recognition method, tax bases and historic law are *not independently verified*. An `ACCRUE` event must be supplied for each required reporting boundary; the engine does not infer accrual calendar automatically.

## Synthetic calculation A — FX, two lots, cross-lot sale

Two USD lots (2 units bought for `1000` at `90`, NKD `20`; 3 units bought for `990` at `91`, NKD `25`). After accrual, sell **4 units across both lots** (2 from the first, 2 from the second), collect a later coupon on the remaining unit and sell it. All FX rates below are **invented**.

| Component | RUB | Interpretive status |
| --- | ---: | --- |
| Interest accrual while held | 9,910 | Candidate |
| Currency differences on interest receivable | 135 | Candidate, legal applicability unverified |
| FIFO clean-price realization | 35,530 | Candidate |
| Currency differences on *purchased NKD* | 550 | **UNCLASSIFIED** |
| **Total components** | **46,125** | Mathematical total only |
| **Net RUB cash flows** | **46,125** | Reconciled |

The `550` RUB **must not be automatically included** in a profit tax base or assigned a tax rate.

## Synthetic calculation B — OFZ-IN, two lots purchased at different nominal levels

Buy 2 securities at indexed nominal 1000; index to 1010; buy 3 more securities at indexed nominal 1010. Later sell 3 FIFO units, collect a coupon on 2 remaining units, index nominal to 1020 and redeem those 2 units.

| Component | RUB | Interpretive status |
| --- | ---: | --- |
| Indexation accrued while each lot held | 40 | Candidate interest |
| Coupon/NKD attributable to holdings | 64 | Candidate interest |
| Realized clean-price result after excluding prior indexation | 9 | Candidate |
| **Total components** | **113** | Mathematical total only |
| **Net cash flows** | **113** | Reconciled |

The second lot gets **no** candidate income for the first `1000 → 1010` index move: it was not yet held. Recognized indexation is deducted from the later sale or redemption *candidate* to prevent arithmetic duplication.

## Mandatory source freshness and escalation

Every tax report must check the controlling Tax Code edition for **each** transaction event (not merely the snapshot date), amendments, transition dates, relevant letters and issue documentation. If the full current or historical text is inaccessible, ask the user for source documents (e.g., export of exact effective articles and amending laws from КонсультантПлюс/ГАРАНТ) and mark `UNVERIFIED_LEGAL_EDITION` or `BLOCKED`. Search returning no amendments is not affirmative proof of no changes.

Statutory anchors requiring full-text verification: **НК РФ ст. 250, 265, 271, 272, 280, 281, 284, 328–329**; banking-specific foreign-exchange recognition may also depend on other provisions and underlying asset classification. Consult https://pravo.gov.ru/ and https://www.consultant.ru/document/cons_doc_LAW_28165/ for source discovery.

Official-interpretation research leads: Минфин 14.07.2015 № 03-03-10/40395 (indexed OFZ nominal); Минфин 13.12.2022 № 03-03-06/2/122113 (negative indexation). Letters are nonnormative explanations and **not** guarantees of present-day application.

**Do not commit licensed legal databases, bank client records or proprietary issuer/trade documents** to this public project. Validate legal rights and access before using documents, data or APIs.
