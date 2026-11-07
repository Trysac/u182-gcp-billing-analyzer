"""Google Cloud Billing NDJSON export analyzer with exact Decimal arithmetic."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Literal

__all__ = [
    "BillingError",
    "BillingRow",
    "Credit",
    "Line",
    "__version__",
    "credits_by_type",
    "load_ndjson",
    "render",
    "summarize",
]

__version__ = "0.1.0"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

ErrorCode = Literal[
    "input_too_large",
    "invalid_json",
    "missing_field",
    "invalid_value",
    "currency_mismatch",
    "invalid_option",
]

MONTH_REGEX = re.compile(r"^\d{6}$")
TWO_PLACES = Decimal("0.01")


class BillingError(ValueError):
    """Base exception raised for billing analysis errors."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message: str = message


@dataclass(frozen=True)
class Credit:
    """Represents a credit applied to a billing row."""

    name: str
    amount: Decimal
    type: str


@dataclass(frozen=True)
class BillingRow:
    """Represents a parsed standard Cloud Billing export row."""

    invoice_month: str
    project: str | None
    service: str
    sku: str
    region: str | None
    cost: Decimal
    currency: str
    credits: tuple[Credit, ...]
    labels: Mapping[str, str]
    cost_type: str


@dataclass(frozen=True)
class Line:
    """Summarized line item aggregating gross, credits, and net cost."""

    key: str
    gross: Decimal
    credits: Decimal
    net: Decimal


def _parse_constant(constant: str) -> None:
    raise BillingError("invalid_value", f"invalid numeric literal: {constant}")


def _truncate_msg(raw: str) -> str:
    if len(raw) > 200:
        return raw[:197] + "..."
    return raw


def load_ndjson(
    text: str,
    *,
    max_bytes: int = 100_000_000,
    max_rows: int = 2_000_000,
) -> list[BillingRow]:
    """Parse newline-delimited JSON rows into BillingRow instances."""
    # Handle UTF-8 BOM if present
    if text.startswith("\ufeff"):
        text = text[1:]

    encoded_len = len(text.encode("utf-8"))
    if encoded_len > max_bytes:
        raise BillingError(
            "input_too_large",
            f"input size {encoded_len} bytes exceeds maximum allowed {max_bytes} bytes",
        )

    rows: list[BillingRow] = []
    lines = text.splitlines()
    row_count = 0

    for line_idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        row_count += 1
        if row_count > max_rows:
            raise BillingError(
                "input_too_large",
                f"line {line_idx}: row count {row_count} exceeds maximum allowed {max_rows} rows",
            )

        try:
            raw_data = json.loads(
                stripped,
                parse_float=Decimal,
                parse_int=Decimal,
                parse_constant=_parse_constant,
            )
        except BillingError:
            raise
        except Exception:
            snippet = _truncate_msg(stripped)
            raise BillingError(
                "invalid_json", f"line {line_idx}: invalid JSON: {snippet}"
            ) from None

        if not isinstance(raw_data, dict):
            snippet = _truncate_msg(stripped)
            raise BillingError(
                "invalid_value", f"line {line_idx}: expected JSON object, got {snippet}"
            )

        row = _parse_row(raw_data, line_idx, stripped)
        rows.append(row)

    return rows


def _parse_row(data: dict[str, Any], line_idx: int, raw_line: str) -> BillingRow:
    # 1. invoice.month
    invoice = data.get("invoice")
    if invoice is None or not isinstance(invoice, dict) or "month" not in invoice:
        raise BillingError(
            "missing_field", f"line {line_idx}: missing field 'invoice.month' in {raw_line[:100]}"
        )
    invoice_month = invoice["month"]
    if not isinstance(invoice_month, str) or not MONTH_REGEX.match(invoice_month):
        raise BillingError(
            "invalid_value",
            f"line {line_idx}: invoice.month must be YYYYMM string, got {invoice_month!r}",
        )

    # 2. project.id (nullable)
    project_val = data.get("project")
    project_id: str | None = None
    if project_val is not None:
        if isinstance(project_val, dict):
            raw_id = project_val.get("id")
            if raw_id is not None and not isinstance(raw_id, str):
                raise BillingError(
                    "invalid_value", f"line {line_idx}: project.id must be string or null"
                )
            project_id = raw_id
        else:
            raise BillingError(
                "invalid_value", f"line {line_idx}: project must be an object or null"
            )

    # 3. service.description
    service_val = data.get("service")
    if service_val is None or not isinstance(service_val, dict) or "description" not in service_val:
        raise BillingError("missing_field", f"line {line_idx}: missing field 'service.description'")
    service_desc = service_val["description"]
    if not isinstance(service_desc, str):
        raise BillingError("invalid_value", f"line {line_idx}: service.description must be string")

    # 4. sku.description
    sku_val = data.get("sku")
    if sku_val is None or not isinstance(sku_val, dict) or "description" not in sku_val:
        raise BillingError("missing_field", f"line {line_idx}: missing field 'sku.description'")
    sku_desc = sku_val["description"]
    if not isinstance(sku_desc, str):
        raise BillingError("invalid_value", f"line {line_idx}: sku.description must be string")

    # 5. location.region (nullable)
    location_val = data.get("location")
    region: str | None = None
    if location_val is not None:
        if isinstance(location_val, dict):
            raw_region = location_val.get("region")
            if raw_region is not None and not isinstance(raw_region, str):
                raise BillingError(
                    "invalid_value", f"line {line_idx}: location.region must be string or null"
                )
            region = raw_region
        else:
            raise BillingError(
                "invalid_value", f"line {line_idx}: location must be an object or null"
            )

    # 6. cost (must be Decimal; bool or string is rejected)
    if "cost" not in data or data["cost"] is None:
        raise BillingError("missing_field", f"line {line_idx}: missing field 'cost'")
    cost_val = data["cost"]
    if isinstance(cost_val, bool) or not isinstance(cost_val, Decimal):
        raise BillingError(
            "invalid_value", f"line {line_idx}: cost must be a numeric value, got {cost_val!r}"
        )

    # 7. currency
    if "currency" not in data or data["currency"] is None:
        raise BillingError("missing_field", f"line {line_idx}: missing field 'currency'")
    currency = data["currency"]
    if not isinstance(currency, str) or not currency.strip():
        raise BillingError("invalid_value", f"line {line_idx}: currency must be a non-empty string")

    # 8. credits[] {name, amount, type}
    credits_list: list[Credit] = []
    credits_val = data.get("credits")
    if credits_val is not None:
        if not isinstance(credits_val, list):
            raise BillingError("invalid_value", f"line {line_idx}: credits must be an array")
        for c_idx, item in enumerate(credits_val):
            if not isinstance(item, dict):
                raise BillingError(
                    "invalid_value", f"line {line_idx}: credit[{c_idx}] must be an object"
                )
            if "name" not in item or "amount" not in item or "type" not in item:
                raise BillingError(
                    "missing_field",
                    f"line {line_idx}: credit[{c_idx}] missing name, amount, or type",
                )
            c_name = item["name"]
            c_amount = item["amount"]
            c_type = item["type"]
            if not isinstance(c_name, str):
                raise BillingError(
                    "invalid_value", f"line {line_idx}: credit[{c_idx}].name must be string"
                )
            if isinstance(c_amount, bool) or not isinstance(c_amount, Decimal):
                raise BillingError(
                    "invalid_value",
                    f"line {line_idx}: credit[{c_idx}].amount must be numeric, got {c_amount!r}",
                )
            if not isinstance(c_type, str):
                raise BillingError(
                    "invalid_value", f"line {line_idx}: credit[{c_idx}].type must be string"
                )
            credits_list.append(Credit(name=c_name, amount=c_amount, type=c_type))

    # 9. labels[] {key, value} - duplicate keys keep the last
    labels_dict: dict[str, str] = {}
    labels_val = data.get("labels")
    if labels_val is not None:
        if not isinstance(labels_val, list):
            raise BillingError("invalid_value", f"line {line_idx}: labels must be an array")
        for l_idx, item in enumerate(labels_val):
            if not isinstance(item, dict):
                raise BillingError(
                    "invalid_value", f"line {line_idx}: label[{l_idx}] must be an object"
                )
            if "key" not in item or "value" not in item:
                raise BillingError(
                    "missing_field", f"line {line_idx}: label[{l_idx}] missing key or value"
                )
            l_key = item["key"]
            l_val = item["value"]
            if not isinstance(l_key, str) or not isinstance(l_val, str):
                raise BillingError(
                    "invalid_value", f"line {line_idx}: label key and value must be strings"
                )
            labels_dict[l_key] = l_val

    # 10. cost_type
    cost_type_val = data.get("cost_type")
    if cost_type_val is None:
        raise BillingError("missing_field", f"line {line_idx}: missing field 'cost_type'")
    if not isinstance(cost_type_val, str):
        raise BillingError("invalid_value", f"line {line_idx}: cost_type must be a string")

    return BillingRow(
        invoice_month=invoice_month,
        project=project_id,
        service=service_desc,
        sku=sku_desc,
        region=region,
        cost=cost_val,
        currency=currency,
        credits=tuple(credits_list),
        labels=labels_dict,
        cost_type=cost_type_val,
    )


def _validate_filters_and_currency(
    rows: Sequence[BillingRow],
    *,
    month: str | None = None,
    cost_types: Sequence[str] | None = None,
) -> list[BillingRow]:
    if month is not None and not MONTH_REGEX.match(month):
        raise BillingError("invalid_option", f"invalid month format: {month!r}; expected YYYYMM")

    filtered: list[BillingRow] = []
    for row in rows:
        if month is not None and row.invoice_month != month:
            continue
        if cost_types is not None and row.cost_type not in cost_types:
            continue
        filtered.append(row)

    currencies = {r.currency for r in filtered}
    if len(currencies) > 1:
        raise BillingError(
            "currency_mismatch",
            f"multiple currencies present in dataset: {', '.join(sorted(currencies))}",
        )

    return filtered


def summarize(
    rows: Sequence[BillingRow],
    *,
    by: str,
    month: str | None = None,
    cost_types: Sequence[str] | None = None,
) -> list[Line]:
    """Summarize billing rows grouped by project, service, sku, region, or label:<key>."""
    valid_base = {"project", "service", "sku", "region"}
    if by not in valid_base and not by.startswith("label:"):
        msg = (
            f"invalid 'by' parameter: {by!r}; "
            "must be 'project', 'service', 'sku', 'region', or 'label:<key>'"
        )
        raise BillingError("invalid_option", msg)

    filtered = _validate_filters_and_currency(rows, month=month, cost_types=cost_types)
    if not filtered:
        return []

    label_key: str | None = None
    if by.startswith("label:"):
        label_key = by[len("label:") :]

    gross_acc: dict[str, Decimal] = {}
    credits_acc: dict[str, Decimal] = {}

    for row in filtered:
        if by == "project":
            key = row.project if row.project is not None else "(no project)"
        elif by == "service":
            key = row.service
        elif by == "sku":
            key = row.sku
        elif by == "region":
            key = row.region if row.region is not None else "(no region)"
        elif label_key is not None:
            key = row.labels.get(label_key, "(no label)")
        else:
            key = "(no label)"

        row_credits = sum((c.amount for c in row.credits), Decimal("0"))
        gross_acc[key] = gross_acc.get(key, Decimal("0")) + row.cost
        credits_acc[key] = credits_acc.get(key, Decimal("0")) + row_credits

    lines: list[Line] = []
    for k in gross_acc:
        g = gross_acc[k]
        c = credits_acc[k]
        lines.append(Line(key=k, gross=g, credits=c, net=g + c))

    # Sorted by net descending, then key ascending
    lines.sort(key=lambda item: (-item.net, item.key))
    return lines


def credits_by_type(
    rows: Sequence[BillingRow],
    *,
    month: str | None = None,
) -> dict[str, Decimal]:
    """Aggregate total credits by credit type, sorted by type key."""
    filtered = _validate_filters_and_currency(rows, month=month, cost_types=None)
    type_totals: dict[str, Decimal] = {}
    for row in filtered:
        for credit in row.credits:
            type_totals[credit.type] = type_totals.get(credit.type, Decimal("0")) + credit.amount

    return {k: type_totals[k] for k in sorted(type_totals.keys())}


def render(lines: Sequence[Line], fmt: Literal["csv", "text"]) -> str:
    """Render summarized lines to CSV or formatted text table."""
    if fmt not in ("csv", "text"):
        raise BillingError("invalid_option", f"invalid format: {fmt!r}; must be 'csv' or 'text'")

    if fmt == "csv":
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\r\n")
        writer.writerow(["key", "gross", "credits", "net"])
        for line in lines:
            writer.writerow(
                [
                    line.key,
                    f"{line.gross.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN):.2f}",
                    f"{line.credits.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN):.2f}",
                    f"{line.net.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN):.2f}",
                ]
            )
        return out.getvalue()

    # fmt == 'text'
    if not lines:
        return ""

    formatted_rows = [
        (
            line.key,
            f"{line.gross.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN):.2f}",
            f"{line.credits.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN):.2f}",
            f"{line.net.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN):.2f}",
        )
        for line in lines
    ]

    headers = ("KEY", "GROSS", "CREDITS", "NET")
    col_widths = [max(len(headers[i]), max(len(r[i]) for r in formatted_rows)) for i in range(4)]

    header_str = (
        f"{headers[0]:<{col_widths[0]}}  "
        f"{headers[1]:>{col_widths[1]}}  "
        f"{headers[2]:>{col_widths[2]}}  "
        f"{headers[3]:>{col_widths[3]}}"
    )
    separator = (
        f"{'=' * col_widths[0]}  "
        f"{'=' * col_widths[1]}  "
        f"{'=' * col_widths[2]}  "
        f"{'=' * col_widths[3]}"
    )

    out_lines = [header_str, separator]
    for r in formatted_rows:
        out_lines.append(
            f"{r[0]:<{col_widths[0]}}  "
            f"{r[1]:>{col_widths[1]}}  "
            f"{r[2]:>{col_widths[2]}}  "
            f"{r[3]:>{col_widths[3]}}"
        )

    return "\n".join(out_lines) + "\n"
