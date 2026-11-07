# Use Python Decimal for Exact Billing Calculation and Ingestion Limits

Status: accepted (generated, pending human review)

## Context

Cloud billing aggregations require absolute mathematical precision down to the cent without float drift, while handling potentially large BigQuery NDJSON exports safely.

## Decision

Configure `json.loads` to deserialize all numeric values to `Decimal` using `parse_float` and `parse_int`. Reject non-finite values (NaN, Infinity). Enforce explicit input size and row limits (`max_bytes`, `max_rows`) to avoid denial-of-service vulnerabilities.

## Consequences

Calculations of gross, credit, and net amounts are exact without floating-point artifacts. Large inputs exceeding limits fail fast with typed `BillingError` exceptions.
