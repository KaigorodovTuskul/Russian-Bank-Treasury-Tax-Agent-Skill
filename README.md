# Russian Bank Treasury Tax — Agent Skill

**Traceable tax research for Russian bank treasury operations.**

[Quick start](#quick-start) · [How it works](#how-it-works) · [Coverage](#coverage) · [Русский](docs/README.ru.md) · [Research status](docs/RESEARCH_STATUS.md)

A portable [Agent Skill](https://agentskills.io/specification) that guides AI agents through Russian bank treasury tax analysis: classify financial instruments, locate effective-law sources, calculate reproducible scenarios, challenge conclusions, and explicitly stop when evidence is incomplete.

> [!IMPORTANT]
> **Research preview — not legally validated for production.** This repository contains a workflow and synthetic test fixtures, **not** an authoritative tax calculation engine. Final Legal Judge Test and human tax-expert review have **not** been completed. Do not use its outputs to post tax entries, prepare returns, determine withholding, or execute trades without independent professional approval.

## Why this skill?

Treasury tax questions mix multiple instruments, legal characterizations, dates, accounting treatments and tax bases. A fluent but unsupported answer is especially dangerous. This skill forces evidence-first reasoning, decision-level traceability and refusal to guess when a missing issue term or historical legal revision would change the result.

## Coverage

| Topic | Current status |
| --- | --- |
| Russian bank as principal (joint-stock commercial bank with universal banking license) | In scope; licensing facts must still be verified |
| Bonds: OFZ, municipal, corporate, fixed/floating coupon | Research workflow + provisional reference notes |
| Bonds: accrued coupon income (НКД), discount, amortization, disposal | Synthetic arithmetic fixtures; legal review pending |
| Bonds: FX, replacement, indexed principal | Provisional; extra source and transaction checks required |
| Bonds: subordinated, perpetual, structured | High-risk; stop gates for write-down and cancelled coupon |
| REPO, interbank loans/deposits, equities, FX, derivatives | Roadmap only — **not implemented as tax rules** |
| Tax-agent / cross-border withholding | Issue spotting only; specialist review required |

## Quick start

Install with a compatible [Agent Skills](https://agentskills.io/) client:

```bash
npx skills add KaigorodovTuskul/Russian-Bank-Treasury-Tax-Agent-Skill --skill russian-bank-treasury-tax
```

Or copy the complete `skills/russian-bank-treasury-tax/` directory into your agent's project/user skills directory. Keep the `references/` and `assets/` folders next to `SKILL.md`.

**Example request:**

> Use russian-bank-treasury-tax. Review the tax consequences for a Russian joint-stock bank purchasing an OFZ on the secondary market, receiving coupons and disposing of the bond. Separate НКД, price result, taxable events and the source evidence for the relevant tax year. If facts or current legal text are missing, mark the conclusion provisional.

No external legal database, MCP or subscription is bundled. The agent must obtain access to applicable primary texts and check the legal revision valid for the event date.

## How it works

1. **Scope** — identify bank/entity status, own vs client transactions, tax and event dates, licenses and tax accounting policy.
2. **Qualify** — map instrument terms and each event to a legal/tax characterization; do not infer it solely from the instrument name.
3. **Source** — retrieve the relevant effective provisions of the Tax Code and verify the edition, amendments and transitional provisions.
4. **Compute** — separate coupon, НКД, price result, principal, FX and special-event components. Preserve an auditable calculation trace.
5. **Challenge** — test counterexamples, source conflict, applicable tax base, uncertain facts and agent obligations.
6. **Release or block** — produce a provisional source-linked memo; stop where missing evidence changes the conclusion. Human sign-off is required for tax implementation.

The executable skill is deliberately short; deeper instructions are read only when needed.

## Repository layout

```text
skills/russian-bank-treasury-tax/
  SKILL.md                     Portable agent instructions
  references/                  Source workflow, bond decision map, stop gates, output rules
  assets/                      Ready-to-fill analysis and review templates
scripts/validate.py            Offline structure + fixture validator
scripts/check_calculations.py  Deterministic synthetic arithmetic checks
tests/                      Local smoke/unit tests and provisional fixtures
examples/                   Synthetic research examples (not legal opinions)
docs/                       Russian quickstart, methodology, status and roadmap
.github/workflows/          Validation on pull requests and pushes
```

## Validate

Requires Python 3.9+; no third-party Python packages are required.

```bash
python scripts/validate.py
python scripts/check_calculations.py
python -m unittest discover -s tests -v
```

These checks establish file consistency, stop behavior and simple arithmetic only. They do **not** prove correctness of legal classifications, court holdings, market-status tests, tax rates or real ISIN behavior.

## Evidence and licensed materials

Preferred hierarchy: effective Russian legal text; binding judicial guidance and pertinent case law; official Finance Ministry/FNS/Bank of Russia materials; licensed commentary as research support. Check official publication and effective-date status. `consultant.ru` / `garant.ru` are valuable research sources but full licensed texts are **not** redistributed here.

See [legal evidence protocol](skills/russian-bank-treasury-tax/references/source-workflow.md) and [research limitations](docs/RESEARCH_STATUS.md).

## Contributing / security / license

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [MIT License](LICENSE)

The project is inspired by the organizational clarity of [Pareto Forge](https://github.com/KaigorodovTuskul/pareto-forge), without reusing its skill text. No affiliation with providers of commercial legal databases is implied.
