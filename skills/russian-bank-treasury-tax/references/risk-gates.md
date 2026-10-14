# Stop gates and escalation

Never convert a synthetic calculation into an approved banking tax position without evidence and review.

| Gate | When triggered | Required response |
| --- | --- | --- |
| LAW_VERSION | Controlling legal article/amendment not checked as of event date | `BLOCKED`, request dated full text |
| ISSUE_TERMS | Coupon cancellation, write-down, amortization, indexed principal, conversion or structured payout without official terms | `BLOCKED`, request terms and event documents |
| LICENSE | Loss-offset inference depends on professional-securities license not evidenced | `BLOCKED` for offset conclusion |
| WITHHOLDING | Cross-border coupon/NKD/beneficial owner/treaty status not known | `BLOCKED` for withholding conclusion |
| REPLACEMENT | Missing statutory eligibility, exchange scope, cost or cap data | `BLOCKED` for transfer of basis conclusion |
| DOUBLE_COUNT | Accrued income seems counted again in sale/redemption | Halt and reconcile tax ledger |
| COURT_CONFLICT | Adverse case law or revision mismatch unresolved | `PROVISIONAL`/`BLOCKED`, identify case history |
| NOT_IMPLEMENTED | REPO, derivatives, FX dealing, interbank loans or other non-bond detailed tax rules requested | Issue spotting only; explicitly label no approved rule |

Taxpayer-visible result statuses:

- `VERIFIED`: sourced primary law, effective revision, all material facts and conditions have evidence, calculation reconciled; **still requires expert approval for implementation**.
- `PROVISIONAL`: partial support or hypothetical assumptions; not operational.
- `BLOCKED`: material predicate missing/contradictory; do not produce a definitive tax number or filing instruction.

Do not silently assume 20% coupon eligibility, professional licenses, treaty relief, deductibility or disposal timing. Never treat a Minfin letter about an **issuer** as an automatically symmetric rule for an **investor**.
