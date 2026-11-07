# Security

## Threat Model

### Defended
- **Unbounded Input (DoS)**: `load_ndjson` enforces a strict 100MB input limit and 2,000,000 row limit. Error messages truncate input to 200 characters to protect log storage.
- **Floating Point Exploits**: Uses `Decimal` for all arithmetic. Rejects non-finite numbers (`NaN`, `Infinity`) via the `parse_constant` callback.
- **Confidentiality**: The library does not log input data. It uses a `NullHandler` for its logger to prevent accidental data leakage.

### Not Defended
- **Input Source Integrity**: Does not verify the source or integrity of the billing JSON file.
