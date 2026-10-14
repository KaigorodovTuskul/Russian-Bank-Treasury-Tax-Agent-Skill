# Agent contributor guide

This repository is a **research-preview high-stakes legal/tax Agent Skill**.

Before editing:

1. Read `skills/russian-bank-treasury-tax/SKILL.md`, `docs/RESEARCH_STATUS.md` and relevant `references/`.
2. Preserve frontmatter compatibility, the `PROVISIONAL`/`BLOCKED` evidence gates, and the distinction between synthetic arithmetic and legal validity.
3. Do not introduce tax rates as unqualified facts or mark draft fixtures as expert-approved. Require exact effective legal version and event-date support.
4. Do not commit licensed documents, credentials, confidential bank data or copyrighted proprietary reference texts.
5. Update `CHANGELOG.md`, research status and tests when behavior changes.
6. Run `python scripts/validate.py`, `python scripts/check_calculations.py`, `python -m unittest discover -s tests -v`.

Change requests must state what is confirmed, what remains disputed and what sources support every material legal claim. Prefer simple, reviewable changes to broad unverified tax-policy expansions.
