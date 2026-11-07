# Testing

Tests reside in `tests/test_gcp_billing_analyzer.py` and are executed via `pytest`.

### Coverage
- **Acceptance Tests**: Verifies core calculations, label/project/sku grouping logic, credit aggregation, and month filtering.
- **Error Handling**: Validates that bad JSON, missing fields, invalid values, currency mismatches, and invalid `by` parameters raise the correct `BillingError` codes.
- **Boundaries**: Ensures inputs exceeding size limits or row counts correctly trigger `input_too_large` errors.
