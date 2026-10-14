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
