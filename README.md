# gcp-billing-analyzer

[![PyPI version](https://img.shields.io/pypi/v/trysac-gcp-billing-analyzer)](https://pypi.org/project/trysac-gcp-billing-analyzer/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-gcp-billing-analyzer)](LICENSE)
[![CI](https://github.com/Trysac/u182-gcp-billing-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u182-gcp-billing-analyzer/actions/workflows/ci.yml)

Analyze Google Cloud billing exports in newline-delimited JSON: gross, credits and net cost by project, service, SKU, region or label with exact Decimal sums

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-gcp-billing-analyzer
# or
uv add trysac-gcp-billing-analyzer
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import gcp_billing_analyzer

# normalize() trims surrounding whitespace and lower-cases the text.
print(gcp_billing_analyzer.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    gcp_billing_analyzer.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
