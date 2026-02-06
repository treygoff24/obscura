# Contributing to Obscura

Thanks for your interest in contributing!

## Getting Started

1. Fork the repo and clone your fork
2. Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3. Install dev dependencies: `pip install -e ".[dev,ui]"`
4. Run tests: `python -m pytest tests/`

## Making Changes

- Create a feature branch from `main`
- Write tests for new functionality
- Keep commits focused — one logical change per commit
- Run the full test suite before submitting a PR

## Testing

```bash
python -m pytest tests/ -m "not ui"  # default: non-UI tests
python -m pytest tests/ --ui         # full suite (includes Playwright UI tests)
```

UI tests require Playwright browsers: `python -m playwright install`

## Reporting Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

**Do not include real documents or sensitive keywords in bug reports.**

## Code Style

- Type hints on public functions
- `regex` module (not stdlib `re`) for pattern matching
- Test file names mirror source: `src/obscura/foo.py` → `tests/test_foo.py`
