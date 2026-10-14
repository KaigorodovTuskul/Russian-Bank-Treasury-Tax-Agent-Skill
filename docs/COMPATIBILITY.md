# Compatibility

Uses the [Agent Skills](https://agentskills.io/specification) directory/frontmatter convention. A compatible client must discover `skills/russian-bank-treasury-tax/SKILL.md` or the copied skill directory and read linked `references/` as needed.

- CLI install: `npx skills add KaigorodovTuskul/Russian-Bank-Treasury-Tax-Agent-Skill --skill russian-bank-treasury-tax` (requires npm/npx and a working network connection).
- Manual install: copy `skills/russian-bank-treasury-tax/` into the skill directory used by your client. Avoid moving `SKILL.md` away from its references.
- Python 3.9+ is needed **only** for repository scripts/tests; no Python runtime is required just to read the skill.
- The skill does not require, bundle or automatically authenticate to КонсультантПлюс, ГАРАНТ, legal MCP services or brokerage APIs.

Client behavior and automatic discovery differ; compatibility with a format does not guarantee identical responses or legal outcomes.
