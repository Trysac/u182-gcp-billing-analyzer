"""CLI entry point for gcp-billing-analyzer."""

from __future__ import annotations

import argparse
import sys
from decimal import ROUND_HALF_EVEN, Decimal

from gcp_billing_analyzer import (
    BillingError,
    credits_by_type,
    load_ndjson,
    render,
    summarize,
)

TWO_PLACES = Decimal("0.01")


def main(argv: list[str] | None = None) -> int:
    """Run CLI commands."""
    parser = argparse.ArgumentParser(
        prog="gcp-billing-analyzer",
        description="Analyze Google Cloud billing NDJSON exports with exact Decimal arithmetic.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="-",
        help="Path to NDJSON export file or '-' for stdin (default: -)",
    )
    parser.add_argument(
        "--by",
        default="project",
        help="Aggregation key: project, service, sku, region, or label:<key> (default: project)",
    )
    parser.add_argument(
        "--month",
        default=None,
        help="Filter by invoice month in YYYYMM format (e.g. 202610)",
    )
    parser.add_argument(
        "--cost-type",
        action="append",
        dest="cost_types",
        default=None,
        help="Filter by cost_type (repeatable, e.g. --cost-type regular)",
    )
    parser.add_argument(
        "--credits",
        action="store_true",
        help="Print total credits broken down by credit type instead of summary lines",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "text"],
        default="text",
        help="Output format: text or csv (default: text)",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse uses 2 for argument errors
        return int(exc.code) if isinstance(exc.code, int) else 2

    try:
        if args.file == "-":
            content = sys.stdin.read()
        else:
            with open(args.file, encoding="utf-8") as f:
                content = f.read()
    except OSError as err:
        sys.stderr.write(f"Error reading file: {err}\n")
        return 2

    try:
        rows = load_ndjson(content)
        if args.credits:
            by_type = credits_by_type(rows, month=args.month)
            if args.format == "csv":
                sys.stdout.write("type,amount\r\n")
                for c_type, amt in by_type.items():
                    rounded = amt.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)
                    sys.stdout.write(f"{c_type},{rounded:.2f}\r\n")
            else:
                for c_type, amt in by_type.items():
                    rounded = amt.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)
                    sys.stdout.write(f"{c_type}: {rounded:.2f}\n")
            return 0

        lines = summarize(
            rows,
            by=args.by,
            month=args.month,
            cost_types=args.cost_types,
        )
        output = render(lines, args.format)
        sys.stdout.write(output)
        return 0
    except BillingError as err:
        sys.stderr.write(f"Billing error [{err.code}]: {err}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
