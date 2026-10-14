# Legal Rules Engine — v0.4 (research preview)

The code in `scripts/legal_rules_engine.py` attaches a **non-authoritative documentary evidence gate** to each calculated bond tax component. It is called automatically by `scripts/treasury_tax_engine.py` after deterministic ledger calculations. It intentionally **does not access websites, parse legal texts, infer substantive legal amendments or certify current tax law**. Only the invoking AI agent can collect and substantively assess full legal documents and actual issue terms using legally accessible tools.

## Exact function and safeguards

- Read the catalog (`skills/russian-bank-treasury-tax/data/bond_tax_rules_2026.json`), identify each tax row's rule ID and event date, apply `valid_from` / `valid_to` constraints, and expose the rule's **dated snapshot rate** when its candidate base matches.
- For each *source ID and event date* require metadata for the full applicable legal edition and amendment-check result. A no-change assertion with no source evidence is insufficient.
- For each *rule / event date / applicability predicate* request supporting issue documents, issuer/trading status and taxpayer evidence; an evidence record for an earlier date does not prove traded status on a later coupon date.
- A **new/changed law signal** yields `REVALIDATION_REQUIRED`. The stored rule must be reviewed against the amending law and transitional provisions and replaced by a **new dated version**, not silently overridden.
- An **unknown/unreachable legal text** yields a concrete `MISSING_DATED_LAW_TEXT` document request, with a source identifier and event date. If the agent cannot obtain the full controlling text or the user has no permission for a commercial source, ask the user to upload the applicable laws, amendments and issue documents.
- A **rate-less computation rule** (such as `BND-NKD-LEDGER`) does not inherit 20% or 25% from a label. A separate `rate_rule_id` may be nominated in `legal_review.rate_selections`; the tax-base class must match, and all conditions for BOTH rules must be evidenced. The selection is a **hypothesis**, not an approved rate.
- A **negative component** does not create automatic tax savings: no conditional tax effect is produced without a loss-offset review. `UNCLASSIFIED_NOT_TAX_BASE` (for example FX differences on purchased NKD) is never silently assigned an income tax category.
- Even when all **externally supplied** documentary metadata passes structural checks, the best status is `DOCUMENTS_SUPPLIED_REVIEW_REQUIRED`. **The code has not read, authenticated or substantively reviewed the legal text.** Tax payable remains `null`.

## Data flow

```
JSON event stream
   → treasury_tax_engine.py (classification & specialized arithmetic)
      → legal_rules_engine.assess_report(...)
         → legal_rules.evaluations[] (one per tax row)
         → legal_rules.document_requests[] (deduplicated requests)
         → legal_validation.legal_rules_status
         → tax_outcome.approved_tax_amount_rub = null
```

### Explicit source and evidence input (optional)

Top-level `legal_review` is an **untrusted list of source claims** that the reviewer must open, inspect and confirm separately. Example:

```json
{
  "legal_review": {
    "law_documents": [{
      "source_id": "NK-RU-284",
      "effective_from": "2025-01-01",
      "effective_to": null,
      "document_locator": "user-upload://dated-tax-code-2026.pdf",
      "full_text_available": true,
      "official_publication_id": "official-law-publication-id",
      "pinpoint": "ст. 284, п. 4",
      "checked_at": "2026-10-14"
    }],
    "amendment_checks": [{
      "source_id": "NK-RU-284",
      "event_date": "2026-02-15",
      "change_status": "unknown",
      "checked_at": "2026-10-14",
      "reviewed_through": "2026-10-14",
      "supporting_document": ""
    }],
    "condition_evidence": [{
      "rule_id": "BND-OFZ-INT-20",
      "event_date": "2026-02-15",
      "condition": "qualifying_state_debt",
      "supporting_document": "user-upload://terms-of-issue.pdf"
    }],
    "rate_selections": [{
      "row_key": "C1|L1|INTEREST_ACCRUAL_CANDIDATE",
      "rate_rule_id": "BND-GEN-25"
    }]
  }
}
```

**Important:** the sample contains *independent illustrative fragments*, not a complete and mutually consistent evidence package. `rate_selections` must match the tax-base class of the actual computation row and may not override an explicit rate rule.

Source IDs and article leads are recorded in `references/legal-source-registry.md`. `document_locator` is only a user-supplied pointer; **it is not retrieved or authenticated** by Python. Do not add licensed full texts, private bank positions or personal data to a public GitHub repository. The conditions (including exchange/listing market-status data) are checked by the human or externally equipped agent, not by presence of a filename.

## Legal amendment workflow for the invoking AI agent

1. Resolve the **tax event date**, issue-specific facts and affected rule IDs.
2. Find each **complete controlling legal edition**, the laws that amended it, effective dates, retroactivity/grandfathering/transitional provisions and relevant cross-references, using accessible reliable sources (e.g. `pravo.gov.ru`, `nalog.gov.ru`, law publishers when licensed).
3. Compare actual provisions with the dated cached rule, including tax rates, base classification, recognition dates, loss restrictions and withholding obligations. Independently check any subsequent interpretations that alter risk.
4. If a change affects the rule, **do not apply the old cached result**. Acquire the actual amending text; prepare a new version of the rule, explain the before/after, update tests and source pinpoints, and only then re-run the arithmetic and legal assessment.
5. If no complete authoritative text, amendment history or actual issue terms are available, **ask the user** for exactly the missing editions (DOCX/searchable PDF from КонсультантПлюс/ГАРАНТ if available), relevant amending laws, issuer terms, trade/NKD extracts, bank license and tax policy as applicable. Report `UNVERIFIED_LEGAL_EDITION` or `BLOCKED` and **do not issue a final tax amount**.
6. All real-world tax implementation requires a designated expert review. Synthetic unit tests validate code mechanics only.

### Suggested Russian user message

> Для операции от **{event_date}** не удалось подтвердить полную редакцию **{source_id}, {precise_article}** и связанные изменения/переходные положения. Загрузите, пожалуйста, действовавший на дату операции текст указанных статей НК РФ, тексты законов об их изменении и (если требуется) условия выпуска облигации / реестр НКД. Без этих материалов расчёт остаётся предварительным; окончательная сумма налога не определена.

## Run & test

```bash
python scripts/treasury_tax_engine.py examples/fx_multilot_synthetic.json
python -m unittest discover -s tests -v
```

The result now includes `legal_rules.status`, `legal_rules.evaluations`, `legal_rules.document_requests`, `law_checked_live_by_code: false` and `approved_tax_amount_rub: null`. Each row may expose a `conditional_arithmetic_tax_effect_rub` **only for a nonnegative base and a matching stored rate**. This does **not** mean the rule is legally applicable or the number is a payable tax. Never sum such amounts into tax payable.