# Helix-Signal agent instructions

This file applies to **every** Cursor agent, subagent, and automated edit on this repository.

## Typography: no em dashes

**Never use the em dash character (Unicode U+2014)** in any project output.

This includes:

- Markdown and docs (`README.md`, `docs/**`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, etc.)
- Comments in HTML, JS, Python, or config when they are user-facing or documentary
- Commit messages, PR descriptions, and release notes
- UI copy and labels (use `-`, `N/A`, or rephrase instead of an em dash as a null placeholder)

### Use instead

| Instead of | Use |
|------------|-----|
| `Feature [em dash] detail` (heading aside) | `Feature: detail` or `Feature (detail)` |
| `word [em dash] word` (break in a sentence) | comma, period, colon, or ` - ` (ASCII hyphen) |
| missing value em dash in UI | `-` or `N/A` |

### Examples

```markdown
# BAD (contains U+2014 em dash)
## v4.4.0 [em dash] Platform release
Anonymous visitors see a lite window [em dash] admin login bypasses clamps.

# GOOD
## v4.4.0: Platform release
Anonymous visitors see a lite window; admin login bypasses clamps.
```

```html
<!-- BAD -->
<span x-text="value ?? EM_DASH_PLACEHOLDER"></span>

<!-- GOOD -->
<span x-text="value ?? '-'"></span>
```

When editing existing files, **replace any em dash you find** with an allowed alternative. Do not introduce new ones.

## Other project conventions

- Single-operator product: no multi-user SaaS paths unless explicitly requested.
- Do not edit `.cursor/plans/` or attached plan files unless the user asks.
- Prefer minimal, focused diffs; match existing code style.
- Run `cd backend && PYTHONPATH=.. python -m pytest -q --ignore=tests/test_alembic.py --ignore=tests/test_integration.py` before claiming tests pass (alembic smoke uses SQLite; prod uses Postgres).
- Only commit when the user explicitly asks.

See also `.cursor/rules/no-em-dash.mdc` for the enforced Cursor rule.
