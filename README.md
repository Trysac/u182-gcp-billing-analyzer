# gcp-billing-analyzer

Analyze Google Cloud Billing detailed BigQuery exports with exact Decimal arithmetic. This utility prevents floating-point drift common in spreadsheet software and preserves nested credit structures (e.g., CUDs, Free Tier) lost in flattened CSV exports.

## Installation

```bash
pip install gcp-billing-analyzer
```

## Usage

```python
from gcp_billing_analyzer import load_ndjson, summarize, render

with open("export.json", encoding="utf-8") as f:
    rows = load_ndjson(f.read())

lines = summarize(rows, by="project", month="202610")
print(render(lines, "text"))
```

## API Summary

- `load_ndjson(text: str, *, max_bytes: int = 100_000_000, max_rows: int = 2_000_000) -> list[BillingRow]`
- `summarize(rows: Sequence[BillingRow], *, by: str, month: str | None = None, cost_types: Sequence[str] | None = None) -> list[Line]`
- `credits_by_type(rows: Sequence[BillingRow], *, month: str | None = None) -> dict[str, Decimal]`
- `render(lines: Sequence[Line], fmt: Literal["csv", "text"]) -> str`

### Errors

All public functions may raise `BillingError(code, message)` with codes: `input_too_large`, `invalid_json`, `missing_field`, `invalid_value`, `currency_mismatch`, `invalid_option`.

### Options

- `by`: "project", "service", "sku", "region", or "label:<key>"
- `fmt`: "csv" or "text"

## Why not alternative tools?

Spreadsheet tools drift with floating-point arithmetic and flattened CSV exports drop nested credit arrays. This utility computes sums using the `decimal` module for exact precision and parses the full NDJSON structure.

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for the threat model and limits.
