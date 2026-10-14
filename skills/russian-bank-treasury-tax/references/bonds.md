# Bond issue and tax-event map (research preview)

**No hard-coded tax rate is authoritative.** Determine effective law on each date and document conditions for any special rate.

## Identify the security

- Issuer: Russian Federation / subject / municipality / resident company or bank / nonresident.
- Currency of legal nominal, settlement currency, exchange-rate/indexation terms.
- Issue date, program, legal jurisdiction, identifier (ISIN), issue-document versions.
- Listed/traded status **under the tax definition**, including relevant quote history and recognition dates; a boolean `is_listed` is insufficient.
- Senior, subordinated, perpetual, callable, puttable, convertible, structured or replacement.
- Fixed/floating/conditional/zero coupon; original-issue discount vs **secondary-market discount**.
- Full or partial amortization schedule, nominal indexation, write-down/cancelled coupon trigger.

## Event split

| Event | Separate tax issue to check | First-look statutory pointers (not conclusions) |
| --- | --- | --- |
| Buy at clean price + NKD | Tax cost, acquired coupon, fees | Tax Code Arts. 280, 328–329 |
| Coupon accrued / paid | Date of recognition, interest base and applicable rate | Arts. 271, 281, 284, 328 |
| Market price appreciation/decline | Disposal proceeds and tax cost; avoid coupon double count | Arts. 280, 329 |
| Original-issue zero-coupon discount | Issue terms and for relevant public debt weighted-average placement price | Arts. 43, 281, 328 |
| Secondary-market discount/premium | Distinguish trading result from issue-terms interest | Arts. 280, 328 |
| Partial principal redemption | Allocation of remaining cost, coupon separately | Art. 280(6) |
| Nominal indexed to inflation | Interest classification, negative indexation, no repeat recognition at redemption | Arts. 280–281, 328; verify official interpretations |
| Currency-denominated security | Historic tax cost, FX rate at disposal, interest receivable vs security | Arts. 271–272, 280 |
| Replacement instrument | Eligibility, what is exchanged, limits and carryover cost | Arts. 251, 270, 280; check operative changes |
| Subordinated write-down | Legal trigger, amount actually extinguished, separate tax base | Art. 280; Banking Law 395-1 Art. 25.1 |
| Cancelled perpetual coupon | Was a right to receive income ever established? Prior tax accrual? | Issue conditions; Arts. 271, 328; research only |
| Structured redemption/conversion | Classify contractual amounts, capital returned and tax cost | Securities Law 39-FZ; Arts. 43, 280 |
| Nonresident counterparty | Tax-agent obligations and beneficial ownership | Arts. 309–312 plus treaties/suspensions |

## Tax base and loss restrictions

Keep applicable special-rate interest and ordinary result of disposal apart. Investigate whether transactions with non-traded bonds and derivatives fall in a separate base and whether any relevant professional-securities license exists; being a bank with a universal banking license is not by itself proof of that status. Examine Arts. 280 and 329 independently.

## Expected evidence for a real ISIN

Official terms and amendments; registrar/depository holdings; trades with clean/dirty prices and NKD; cash-flow confirmations; original placement data (for qualifying discounts); applicable market quote history; published amendments and operative law; accounting/tax policy; professional license (if needed); tax-agent and treaty documentation for cross-border operations.
