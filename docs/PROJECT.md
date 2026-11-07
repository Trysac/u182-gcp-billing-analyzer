# Project Record

## Objective
Analyze Google Cloud Billing exports in newline-delimited JSON format to calculate gross, credits, and net cost, ensuring exact arithmetic using Python's `Decimal` type.

## Scope
- Ingestion of standard BigQuery detailed billing NDJSON exports.
- Aggregation of costs and credits by dimensions (project, service, sku, region, or labels).
- Breakdown of credits by type.
- Rendering of summaries into text tables or RFC 4180 CSVs.
- Command-line interface for common analysis tasks.

## Out of Scope
- Querying Google Cloud APIs or BigQuery directly.
- Processing non-standard billing exports (e.g., pricing catalogs, FOCUS formatted data, or flattened CSV billing files).
- Forecasting, billing anomaly detection, or visualization.

## Factory run u182 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | gemini-3.8-flash | yes | 4402 | 14961 | 0 | 0 | 0.0297 |
| fix-1 | gemini-3.8-flash | no | 20929 | 372 | 0 | 37445 | 0.0199 |
| fix-2 | gemini-3.8-flash | no | 66185 | 1863 | 0 | 453068 | 0.0906 |
| audit | gemini-3.1-flash-lite | no | 32101 | 144 | 0 | 20351 | 0.0088 |
| docs | gemini-3.1-flash-lite | no | 148218 | 1565 | 0 | 0 | 0.0394 |

Total: $0.1884. Prices: Anthropic list prices.
