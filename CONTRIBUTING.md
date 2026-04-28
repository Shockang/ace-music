# Contributing

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

For local ACE-Step work, install the optional GPU dependencies separately:

```bash
pip install -e ".[dev,model]"
```

The `.[model]` extra is intended for local GPU-backed generation and is intentionally excluded from public CI.

## Quality Gates

Run these before opening a pull request:

```bash
ruff check src tests examples
pytest -q
ace-music generate --mock --description "contribution smoke test" --duration 5 --output-dir ./tmp-smoke --summary-json ./tmp-smoke/summary.json
```

## Pull Requests

- Keep changes focused and reviewable.
- Update documentation when user-facing behavior changes.
- Include test evidence in the pull request description.
- If a change affects GPU-backed flows, provide a mock-mode reproduction path when possible.

## Bug Reports vs Feature Requests

- Use the bug template when something currently supported behaves incorrectly.
- Use the feature template when proposing a new capability or API change.
- For support questions, prefer the support route described in [SUPPORT.md](SUPPORT.md).
