# Dated legal evidence protocol

## Source hierarchy (for research, not a universal ranking of legal authority)

1. The controlling **effective** Russian legal text and implementing regulations, with publication, amendment and entry-into-force dates. Start with the Tax Code of the Russian Federation, especially Chapters 21 and 25; add securities/banking laws as relevant.
2. Judicial decisions with court, case number, date, **later-instance history and legal period**. Distinguish binding guidance from fact-specific holdings.
3. Official FNS/Minfin/Bank of Russia communications, with number, date, scope and applicability; such letters are not themselves generally binding legislation.
4. Licensed КонсультантПлюс / ГАРАНТ analysis, guides and commentaries for discovery, cross-checks and jurisprudence navigation; do not replace primary evidence with commentary.

Useful public starting points: https://pravo.gov.ru/ ; https://www.nalog.gov.ru/ ; https://www.cbr.ru/ . Official publications and tax-code revisions must be verified for each event.

## Workflow

1. Write the exact taxable event and date; do not assume today's edition governs historical events.
2. Identify a controlling article/paragraph, amendment law, effective date, transitions and special exclusions. Save identifiers and revision date.
3. Read adjacent cross-referenced provisions, including tax base, moment of recognition, rates and banking-specific rules.
4. Search for the **opposite** interpretation and controlling court decisions; check appeals and subsequent amendments.
5. Register each source with `source_type`, `title`, `identifier`, `edition_date`, `effective_from`, `effective_to` (if known), `url_or_file`, `pinpoint`, `accessed_at`, `notes`, `verification_status`.
6. Link **each material conclusion** to the precise applicable primary-law provision. If the primary text cannot be checked, set `PROVISIONAL` or `BLOCKED`.

## Copyright and privacy

Do not commit licensed full-text ConsultantPlus/GARANT documents, bank contracts, client personal data, internal account statements, subscription credentials or leaked legal databases. Store only legally shareable citations/metadata and original commentary. If given proprietary materials, use them only within permitted scope; do not redistribute.


## Mandatory change-detection and user-document escalation (v0.2)

Hard-coded rules in `data/bond_tax_rules_2026.json` are a **dated 2026 research snapshot**, not permanently applicable law. On **every tax query**, before using a stored rate, interpretation, formula or exception as an operative legal conclusion:

1. Determine **each taxable event date** and whether historical editions or new law govern. Do not assume today's latest text applies retroactively.
2. Check the rule's primary provisions, effective edition and validity interval against current, authoritative text; search for **subsequent amendments**, entry-into-force provisions, transitional measures, repeal, and material changes in official interpretations or precedent.
3. If changes exist, re-read the affected complete text and cross-referenced articles; recalculate impacted cases; record the new source identifier, official publication, effective dates and verification timestamp. A patch is a **new reviewed rule version**, not silent mutation of 2026 historical facts.
4. If the agent has **no live legal-access tool**, cannot reach full authoritative text, a commercial source is behind login, or new law/current revision **cannot be verified**, the agent must stop before a definitive tax conclusion. Clearly state **UNVERIFIED_LEGAL_EDITION** and ask the user to provide the **full relevant edition(s)** of the statute and amendments (preferably DOCX or text-searchable PDF), plus issue terms or other documents where needed.
5. Even if no changes are discovered via public search, do not treat `no search result` as proof of no changes. Explicitly disclose completeness of checks and mark `PROVISIONAL` if authoritative source access was insufficient.
6. Never hard-code unknown values or infer the missing legal text from an old commentary; do not bypass evidence or stop gates simply to supply a number.

User-facing escalation example (Russian):

> Для применения правила на дату операции требуется подтвердить действующую редакцию НК РФ, ст. 280 и 284, включая изменения и переходные положения. Доступного полного текста проверенной редакции у меня нет. Загрузите, пожалуйста, соответствующие статьи/полную редакцию НК РФ и тексты законов о внесённых изменениях из КонсультантПлюс или другого надёжного источника. До проверки расчёт имеет статус PROVISIONAL и не должен использоваться как окончательное налоговое заключение.

Required audit fields: `rule_id`, `rule_version`, `event_date`, `law_effective_date`, `checked_at`, `source_publication_id`, `source_pinpoint`, `change_checked`, `change_status`, `supporting_file`, `verification_status`, `missing_evidence`. Public GitHub sources must contain only legally redistributable material, not licensed legal documents.
