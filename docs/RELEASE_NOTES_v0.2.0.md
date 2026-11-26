# v0.2.0 Release Notes

## Added

- `fin_wiki.superagent`: StateStore / Worker / Watchdog / Router reference skeleton.
- `fin_wiki.adapters`: LLM adapter boundary with timeout, retry, JSON extraction,
  and OpenAI-compatible adapter.
- Long-term equity experiment:
  - cost-method to equity-method conversion
  - impairment non-reversal (Watchdog BLOCKED)
  - worker replacement
  - backlog recovery
- `docs/SUPERAGENT.md`.

## Tests

```text
54 tests passed
```

## Notes

- `superagent.py` is a reference skeleton, not a production scheduler.
- SQLite is local/single-node.
- v0.2.0 Zenodo record is not yet published; concept DOI remains:

```text
10.5281/zenodo.24295147
```
