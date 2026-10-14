# Research output contract

Return a concise memo with these sections:

1. **Question and scope**: taxpayer/role, instrument, dates, jurisdiction and tax period.
2. **Facts and missing evidence**: exact facts; distinguish documented vs assumed.
3. **Event ledger**: buy, accrued coupon/NKD, payments, disposal, amortization, FX and exceptional events, each date-stamped.
4. **Tax characterization matrix**: event → rule/predicates → rate (if verified) → tax base → recognition date → evidence.
5. **Calculation**: arithmetic with intermediate values and cash-flow reconciliation; handle other bank income/eligible offsets separately from transaction-level results.
6. **Sources**: precise article/paragraph and edition/effective dates; positions from letters and decisions marked by authority and period.
7. **Alternative interpretations / adverse evidence**: what could invalidate this view.
8. **Decision**: `VERIFIED`, `PROVISIONAL` or `BLOCKED`; exactly which documents/approvals unblock it.

Do not label a number as "tax payable" when it is merely a transaction-level marginal effect dependent on other income, loss limitations or distinct tax bases.

Suggested fields for machine-readable systems: `taxpayer_role`, `instrument_id`, `event_id`, `event_date`, `tax_period`, `facts`, `unknowns`, `tax_components`, `tax_base`, `rate_basis`, `source_ids`, `effective_law_date`, `calculation_trace`, `decision`, `required_reviews`.
