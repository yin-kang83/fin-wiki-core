# Changelog

All notable changes to this project are documented here.

## v0.2.0

- Add `fin_wiki.superagent`: StateStore / Worker / Watchdog / Router skeleton.
- Add `fin_wiki.adapters`: LLM adapter boundary (timeout/retry/JSON/OpenAI-compatible).
- Add long-term equity experiment: cost→equity conversion, impairment non-reversal,
  worker replacement, backlog recovery.
- Add `docs/SUPERAGENT.md` and tests for append-only store, watchdog, worker retry.
- Zenodo v0.2.0: DOI `10.5281/zenodo.24553812` (concept `10.5281/zenodo.24295147`).

## v0.1.3

- Fix 8 logic findings from the external Codex review:
  immutable ledger records, consecutive corrections, atomic batch commit,
  annual-report extraction, DAG input shadowing, early-adoption scope,
  namespaced case-version lookup, and immutable document versions.
- Add `docs/REVIEW_FIXES.md` and `fin_wiki/tests/test_review_contracts.py`.
- Tests: 36 passed.

## v0.1.2

- Add `CITATION.cff`.
- Add project changelog.
- Document release/verification notes.

## v0.1.1

- Add `docs/ARCHITECTURE.svg` and embed it in README/architecture docs.
- Add `docs/DESIGN.md`: design rationale, failure modes → invariants → modules.
- Add `CONTRIBUTING.md` and `SECURITY.md`.
- Keep core tests at 26 passed.

## v0.1.0

- Initial open-source core: evidence index, append-only dual-time fact store,
  deterministic compiler, adapter, pure Decimal operators, DAG, rule versions,
  applicability resolver, case evaluator, annual-report disclosure adapter.
- Synthetic tests: 26 passed.
- MIT license.
