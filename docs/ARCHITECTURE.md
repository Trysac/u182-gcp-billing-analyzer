# Architecture

## Components

1. **Data Model**: Uses frozen `dataclasses` (`BillingRow`, `Credit`, `Line`) to ensure immutability during analysis.
2. **Parsing**: Streaming NDJSON parser using `json.loads` with custom `parse_float` and `parse_int` hooks set to `Decimal`.
3. **Analysis Engine**: A grouping and aggregation layer that computes totals using exact `Decimal` arithmetic.
4. **Renderer**: Transforms `Line` objects into display-ready strings (CSV or tabular text).

## Data Flow
1. Input String -> `load_ndjson` -> `list[BillingRow]`
2. `list[BillingRow]` -> `summarize` or `credits_by_type` -> `list[Line]` or `dict[str, Decimal]`
3. Summaries -> `render` -> String Output
