# Contributing

Thanks for considering a contribution.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest fin_wiki/tests -q
```

## Principles

- Keep the core deterministic: no LLM calls in `fin_wiki/` runtime;
- Facts are append-only; corrections use `supersedes`;
- Missing/ambiguous inputs must fail closed, not default;
- Every fact needs a verifiable source span;
- New behavior needs a test using synthetic data only.

## Pull requests

- Keep changes focused;
- Include tests;
- Do not add real annual reports, question banks, customer data, or secrets.
