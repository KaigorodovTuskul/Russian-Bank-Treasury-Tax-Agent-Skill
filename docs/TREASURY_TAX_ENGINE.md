# Treasury Tax Engine — unified research orchestrator (v0.3.0)

**Scope:** event-based tax **research** for a Russian commercial bank's own bond portfolio, with an explicit dated-legal-evidence gate. **Status:** `RESEARCH_PREVIEW / UNVERIFIED_LEGAL_EDITION`. This software does **not** validate Russian legislation, issuer terms, a professional-participant licence, or market-status eligibility, and does **not** produce final payable tax.

## Why one entry point?

`treasury_tax_engine.py` is a deterministic facade over existing specialized modules. It avoids multiplying duplicate tax formulas: the underlying engines remain the source of calculated components; this facade supplies **validated routing, one report contract, and hard-coded catalogue attribution**.

| Instrument evidence from the first BUY | Conditions | Selected backend |
| --- | --- | --- |
| Ordinary RUB bond (`currency=RUB`, `principal_unit`) | Any lot count, including partial sales and amortization | `bond_ledger.py` |
| Foreign-currency-denominated **Russian corporate issue** (`nominal_currency=USD` etc.) | One purchase and no partial disposals | `advanced_bond_ledger.py` |
| FX Russian corporate issue | Multiple purchases, partial sale, or `calculation_mode=multi` | `multilot_bond_ledger.py` |
| RUB indexed sovereign OFZ (`security_kind=OFZ_IN`, `nominal_currency=RUB`) | One purchase and no partial disposals | `advanced_bond_ledger.py` |
| OFZ-IN | Multiple purchases, partial sale, or `calculation_mode=multi` | `multilot_bond_ledger.py` |
| Missing/conflicting issue classification, other instruments | — | **BLOCKED** |

**Instrument routing must not be inferred from an ISIN-like string alone.** The issuer/nominal/settlement fields are input claims until verified against issue documents. The additional specialized adapters themselves enforce the relevant restrictions.

## Quick start

Requires Python 3.9+, standard library only. From the repository root:

```bash
python scripts/treasury_tax_engine.py examples/bond_lifecycle_t01.json
python scripts/treasury_tax_engine.py examples/fx_lifecycle_synthetic.json
python scripts/treasury_tax_engine.py examples/fx_multilot_synthetic.json --output /tmp/unified_fx_report.json
python scripts/treasury_tax_engine.py examples/ofz_in_multilot_synthetic.json
python -m unittest discover -s tests -v
```

`kind` in the input may be supplied as a cross-check; it never overrides the classification inferred from the first BUY. For FX and OFZ-IN, `calculation_mode` can be `auto` (default), `single`, or `multi`. A forced `single` with multiple lots/partial disposal is blocked. Input money, prices, quantities and rates should be **JSON decimal strings**; JSON floating-point numbers are rejected.

Input skeleton:

```json
{
  "kind": "FX",
  "calculation_mode": "auto",
  "events": [
    {
      "id": "BUY-1", "date": "2026-01-10", "type": "BUY",
      "security_id": "SYNTH-RU-CORP-USD", "lot_id": "LOT-1",
      "quantity": "1", "clean_price_unit": "1000", "nkd_unit": "20",
      "nominal_unit": "1000", "rub_per_nominal_currency": "90",
      "nominal_currency": "USD", "settlement_currency": "USD",
      "issuer_law": "RU", "issuer_class": "RU_CORPORATE",
      "coupon_recognition_method": "ACCRUAL", "coupon_period": "C1"
    }
  ]
}
```

Single-input examples are intentionally synthetic and must not be used to post bank tax entries. An open position does not have to reconcile to lifetime net cash profit because its carrying value remains invested. A **closed** position is reconciled to the component sum by the underlying engine and again by the facade.

## Normalized output

Top-level:

- `schema_version`: `0.3.0`; `engine`: `treasury_tax_engine`.
- `instrument`: `security_id`, `kind`, `event_count`, `purchase_count`.
- `route`: selected backend, reason and partial-disposal flag.
- `accounting`: `tax_components`, `candidate_tax_base_totals_rub`, component total, net cash, outstanding lots and cash-flow register.
- `legal_validation`: catalog snapshot date, rule-specific legal references/conditions, **false** live-law verification flags, and user-document checklist.
- `tax_outcome`: **`approved_tax_amount_rub: null`**, **`indicative_total_tax_rub: null`**. No naive multiplication of a component by a stored rate is final tax; separate tax bases and loss restrictions must be verified at bank level.

Each tax component contains event date, lot ID when available, precise `rule_id`, a catalog `legal_pinpoint`, `primary_source_ids`, stored rate *if any*, required eligibility conditions, research status and original source interpretation note. A row whose tax character is unresolved uses `UNCLASSIFIED_NOT_TAX_BASE` and may **never** be silently offset against another base.

For `BLOCKED` or `INVALID_INPUT` the facade returns a common rejection object with `reason_code`, document needs and **no tax amount**. The CLI exits nonzero for rejections. `UNVERIFIED_LEGAL_EDITION` is still **not** authorization for tax filing.

## Dated law checking — mandatory outside the calculator

The catalog is a research snapshot dated **2026-10-14**. The Python program cannot retrieve live legislation. The invoking AI agent **must** do the following for every real-world question:

1. Establish each event date and the legally controlling tax period. Retrieve official or reliable **full dated** text of every cited НК РФ paragraph and its cross-references; check amendments, entry-into-force provisions, grandfathering, repeal and relevant official clarifications or judgments.
2. Confirm issue conditions, market/traded status on *each* recognition date, bank tax accounting policy, and separate tax-base rules. Do not treat the presence of a stored rate in the catalog as proof of eligibility.
3. Compare the controlling text with stored `rule_id` and conditions. A change requires an appropriately sourced **new rule version**, impact assessment, and regression tests; old historical versions must not be overwritten silently.
4. If the agent lacks full applicable legal text (for example, access to a subscription database fails), explicitly report **`UNVERIFIED_LEGAL_EDITION` / `BLOCKED`** and request the relevant full versions of the **Tax Code and amending laws** from the user, e.g. a DOCX or searchable PDF exported from КонсультантПлюс. Also request the bond issue terms, tax registers and deal evidence as needed.
5. Never infer “the law has not changed” from an unsuccessful public web search. Never say that the code has independently validated the law.

Source starting points: [official Russian legal publication](https://pravo.gov.ru/), [ФНС](https://www.nalog.gov.ru/), [НК РФ, часть II](https://www.consultant.ru/document/cons_doc_LAW_28165/). Consult the repository's `references/legal-source-registry.md` for exact provisions. Licensed full text is **not** committed to GitHub.

## Known exclusions

- Securities outside supported RUB ordinary bonds, Russian corporate foreign-currency bonds and positive-index OFZ-IN.
- Nominal FX bond with settlement in RUB, foreign-law/issuer special regimes, coupon recognition on receipt, nonresident withholding, complex replacement/structured/subordinated events.
- Negative indexed nominal, foreign-currency amortization, heterogeneous instruments in one call, true portfolio aggregation, real-world rate/FX retrieval.
- Full bank-level tax base and loss offsets, treaty checks, automated current-legislation validation and final human approval.

A numerical cash-flow reconciliation is **only an arithmetic invariant**, not proof that all tax components, timing or historical legal rules are valid.