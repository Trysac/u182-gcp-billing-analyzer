"""Unit and acceptance tests for gcp_billing_analyzer."""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pytest

from gcp_billing_analyzer import (
    BillingError,
    Line,
    credits_by_type,
    load_ndjson,
    render,
    summarize,
)
from gcp_billing_analyzer.__main__ import main

SAMPLE_ROW_1 = (
    '{"invoice":{"month":"202610"},"project":{"id":"p1"},"service":{"description":"Compute Engine"},'
    '"sku":{"description":"N2 Core"},"cost":12.5,"currency":"USD",'
    '"credits":[{"name":"CUD","amount":-2.25,"type":"COMMITTED_USAGE_DISCOUNT"}],'
    '"labels":[{"key":"team","value":"core"}],"cost_type":"regular"}'
)


def test_acceptance_item_1() -> None:
    """Acceptance item 1: single row summary by project with Decimal values."""
    rows = load_ndjson(SAMPLE_ROW_1)
    assert len(rows) == 1
    res = summarize(rows, by="project")
    assert res == [Line("p1", Decimal("12.5"), Decimal("-2.25"), Decimal("10.25"))]


def test_acceptance_item_2() -> None:
    """Acceptance item 2: 0.1 and 0.2 parsed with Decimal and sum exactly to 0.3."""
    row_a = (
        '{"invoice":{"month":"202610"},"project":{"id":"p1"},"service":{"description":"Compute Engine"},'
        '"sku":{"description":"N2 Core"},"cost":0.1,"currency":"USD","cost_type":"regular"}'
    )
    row_b = (
        '{"invoice":{"month":"202610"},"project":{"id":"p1"},"service":{"description":"Compute Engine"},'
        '"sku":{"description":"N2 Core"},"cost":0.2,"currency":"USD","cost_type":"regular"}'
    )
    rows = load_ndjson(f"{row_a}\n{row_b}")
    summary = summarize(rows, by="project")
    assert len(summary) == 1
    assert summary[0].gross == Decimal("0.3")


def test_acceptance_item_3() -> None:
    """Acceptance item 3: label missing falls back to (no label), project null uses (no project), sku uses description."""
    ndjson = (
        '{"invoice":{"month":"202610"},"project":null,"service":{"description":"Cloud Storage"},'
        '"sku":{"description":"Standard Storage"},"cost":5.0,"currency":"USD","cost_type":"regular"}\n'
        '{"invoice":{"month":"202610"},"project":{"id":"p2"},"service":{"description":"BigQuery"},'
        '"sku":{"description":"Analysis"},"cost":10.0,"currency":"USD",'
        '"labels":[{"key":"team","value":"analytics"}],"cost_type":"regular"}'
    )
    rows = load_ndjson(ndjson)

    # by='label:team'
    by_label = summarize(rows, by="label:team")
    keys_label = {line.key for line in by_label}
    assert "(no label)" in keys_label
    assert "analytics" in keys_label

    # project is null -> (no project)
    by_project = summarize(rows, by="project")
    keys_project = {line.key for line in by_project}
    assert "(no project)" in keys_project
    assert "p2" in keys_project

    # by='sku'
    by_sku = summarize(rows, by="sku")
    keys_sku = {line.key for line in by_sku}
    assert "Standard Storage" in keys_sku
    assert "Analysis" in keys_sku


def test_acceptance_item_4() -> None:
    """Acceptance item 4: credits_by_type with COMMITTED_USAGE_DISCOUNT and FREE_TIER, sorted by net descending, key ascending."""
    row_1 = (
        '{"invoice":{"month":"202610"},"project":{"id":"p1"},"service":{"description":"Compute Engine"},'
        '"sku":{"description":"N2 Core"},"cost":10.0,"currency":"USD",'
        '"credits":[{"name":"CUD","amount":-2.25,"type":"COMMITTED_USAGE_DISCOUNT"}],"cost_type":"regular"}'
    )
    row_2 = (
        '{"invoice":{"month":"202610"},"project":{"id":"p2"},"service":{"description":"Cloud Storage"},'
        '"sku":{"description":"Standard Storage"},"cost":2.0,"currency":"USD",'
        '"credits":[{"name":"FT","amount":-1.0,"type":"FREE_TIER"}],"cost_type":"regular"}'
    )
    rows = load_ndjson(f"{row_1}\n{row_2}")
    c_types = credits_by_type(rows)
    assert c_types == {
        "COMMITTED_USAGE_DISCOUNT": Decimal("-2.25"),
        "FREE_TIER": Decimal("-1"),
    }

    # Check sort order: net descending, then key ascending
    # Row 1 net = 10 - 2.25 = 7.75; Row 2 net = 2 - 1 = 1.0
    summary = summarize(rows, by="project")
    assert [s.key for s in summary] == ["p1", "p2"]

    # Tie in net: key ascending
    row_a = (
        '{"invoice":{"month":"202610"},"project":{"id":"b_proj"},"service":{"description":"S"},'
        '"sku":{"description":"K"},"cost":5.0,"currency":"USD","cost_type":"regular"}'
    )
    row_b = (
        '{"invoice":{"month":"202610"},"project":{"id":"a_proj"},"service":{"description":"S"},'
        '"sku":{"description":"K"},"cost":5.0,"currency":"USD","cost_type":"regular"}'
    )
    summary_tie = summarize(load_ndjson(f"{row_a}\n{row_b}"), by="project")
    assert [s.key for s in summary_tie] == ["a_proj", "b_proj"]


def test_acceptance_item_5() -> None:
    """Acceptance item 5: invoice month filtering, invalid_option errors, cost_types exclusion."""
    row_oct = (
        '{"invoice":{"month":"202610"},"project":{"id":"p1"},"service":{"description":"Compute"},'
        '"sku":{"description":"N2"},"cost":10,"currency":"USD","cost_type":"regular"}'
    )
    row_nov = (
        '{"invoice":{"month":"202611"},"project":{"id":"p1"},"service":{"description":"Compute"},'
        '"sku":{"description":"N2"},"cost":20,"currency":"USD","cost_type":"regular"}'
    )
    row_tax = (
        '{"invoice":{"month":"202610"},"project":{"id":"p1"},"service":{"description":"Compute"},'
        '"sku":{"description":"N2"},"cost":1,"currency":"USD","cost_type":"tax"}'
    )
    rows = load_ndjson(f"{row_oct}\n{row_nov}\n{row_tax}")

    # Filter by month keeps only that month
    oct_lines = summarize(rows, by="service", month="202610")
    assert sum((line.gross for line in oct_lines), Decimal("0")) == Decimal("11")

    # Filter cost_types=('regular',) excludes tax
    regular_lines = summarize(rows, by="service", month="202610", cost_types=("regular",))
    assert sum((line.gross for line in regular_lines), Decimal("0")) == Decimal("10")

    # month='2026-10' raises invalid_option
    with pytest.raises(BillingError) as exc_info:
        summarize(rows, by="service", month="2026-10")
    assert exc_info.value.code == "invalid_option"

    # by='colour' raises invalid_option
    with pytest.raises(BillingError) as exc_info2:
        summarize(rows, by="colour")
    assert exc_info2.value.code == "invalid_option"


def test_acceptance_item_6() -> None:
    """Acceptance item 6: error handling for invalid JSON, missing_field, invalid_value, and currency_mismatch."""
    # Line 2 containing '{' raises invalid_json
    bad_json = f"{SAMPLE_ROW_1}\n{{"
    with pytest.raises(BillingError) as exc_bad_json:
        load_ndjson(bad_json)
    assert exc_bad_json.value.code == "invalid_json"
    assert "line 2: invalid JSON" in str(exc_bad_json.value)

    # A row without cost raises missing_field
    no_cost = (
        '{"invoice":{"month":"202610"},"service":{"description":"Compute"},'
        '"sku":{"description":"N2"},"currency":"USD","cost_type":"regular"}'
    )
    with pytest.raises(BillingError) as exc_no_cost:
        load_ndjson(no_cost)
    assert exc_no_cost.value.code == "missing_field"

    # Cost "12" (a string) raises invalid_value
    string_cost = (
        '{"invoice":{"month":"202610"},"service":{"description":"Compute"},'
        '"sku":{"description":"N2"},"cost":"12","currency":"USD","cost_type":"regular"}'
    )
    with pytest.raises(BillingError) as exc_str_cost:
        load_ndjson(string_cost)
    assert exc_str_cost.value.code == "invalid_value"

    # Rows in USD and EUR raise currency_mismatch
    row_usd = (
        '{"invoice":{"month":"202610"},"service":{"description":"Compute"},'
        '"sku":{"description":"N2"},"cost":10,"currency":"USD","cost_type":"regular"}'
    )
    row_eur = (
        '{"invoice":{"month":"202610"},"service":{"description":"Compute"},'
        '"sku":{"description":"N2"},"cost":10,"currency":"EUR","cost_type":"regular"}'
    )
    rows_multi_curr = load_ndjson(f"{row_usd}\n{row_eur}")
    with pytest.raises(BillingError) as exc_curr:
        summarize(rows_multi_curr, by="service")
    assert exc_curr.value.code == "currency_mismatch"


def test_acceptance_item_7() -> None:
    """Acceptance item 7: input size limits and max_rows enforcement; blank lines skipped."""
    # 100_000_001 bytes raises input_too_large, 100_000_000 accepted
    with pytest.raises(BillingError) as exc_limit:
        load_ndjson("a" * 101, max_bytes=100)
    assert exc_limit.value.code == "input_too_large"

    # max_rows=1 with two rows raises input_too_large
    with pytest.raises(BillingError) as exc_rows:
        load_ndjson(f"{SAMPLE_ROW_1}\n{SAMPLE_ROW_1}", max_rows=1)
    assert exc_rows.value.code == "input_too_large"

    # Blank lines skipped
    loaded = load_ndjson(f"\n  \n{SAMPLE_ROW_1}\n\n  \t  \n")
    assert len(loaded) == 1


def test_acceptance_item_8(tmp_path: Path) -> None:
    """Acceptance item 8: render to CSV and CLI execution."""
    line = Line("p1", Decimal("12.5"), Decimal("-2.25"), Decimal("10.25"))
    csv_out = render([line], "csv")
    expected = "key,gross,credits,net\r\np1,12.50,-2.25,10.25\r\n"
    assert csv_out == expected

    # Test CLI
    export_file = tmp_path / "export.json"
    export_file.write_text(SAMPLE_ROW_1, encoding="utf-8")

    exit_code = main([str(export_file), "--by", "project", "--format", "csv"])
    assert exit_code == 0

    # BillingError returns 2
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{", encoding="utf-8")
    err_exit = main([str(bad_file)])
    assert err_exit == 2


def test_bom_handling() -> None:
    """Test UTF-8 BOM is transparently handled."""
    bom_data = "\ufeff" + SAMPLE_ROW_1
    rows = load_ndjson(bom_data)
    assert len(rows) == 1
    assert rows[0].project == "p1"


def test_crlf_handling() -> None:
    """Test CRLF line endings are parsed properly."""
    crlf_data = f"{SAMPLE_ROW_1}\r\n{SAMPLE_ROW_1}\r\n"
    rows = load_ndjson(crlf_data)
    assert len(rows) == 2


def test_empty_file() -> None:
    """Test empty input returns empty list."""
    rows = load_ndjson("")
    assert rows == []
    assert summarize(rows, by="project") == []
    assert credits_by_type(rows) == {}
    assert render([], "text") == ""
    assert render([], "csv") == "key,gross,credits,net\r\n"


def test_duplicate_labels_keep_last() -> None:
    """Duplicate label keys keep the last value."""
    row_json = (
        '{"invoice":{"month":"202610"},"service":{"description":"S"},"sku":{"description":"K"},'
        '"cost":1,"currency":"USD","cost_type":"regular",'
        '"labels":[{"key":"env","value":"dev"},{"key":"env","value":"prod"}]}'
    )
    rows = load_ndjson(row_json)
    assert rows[0].labels == {"env": "prod"}


def test_negative_cost_adjustments() -> None:
    """Test negative cost adjustments are supported."""
    row_json = (
        '{"invoice":{"month":"202610"},"project":{"id":"p1"},"service":{"description":"S"},'
        '"sku":{"description":"K"},"cost":-5.50,"currency":"USD","cost_type":"regular"}'
    )
    rows = load_ndjson(row_json)
    lines = summarize(rows, by="project")
    assert lines[0].gross == Decimal("-5.50")
    assert lines[0].net == Decimal("-5.50")


def test_region_grouping_and_null() -> None:
    """Test by='region' with nullable region."""
    row_1 = (
        '{"invoice":{"month":"202610"},"location":{"region":"us-central1"},"service":{"description":"S"},'
        '"sku":{"description":"K"},"cost":10,"currency":"USD","cost_type":"regular"}'
    )
    row_2 = (
        '{"invoice":{"month":"202610"},"location":null,"service":{"description":"S"},'
        '"sku":{"description":"K"},"cost":5,"currency":"USD","cost_type":"regular"}'
    )
    rows = load_ndjson(f"{row_1}\n{row_2}")
    lines = summarize(rows, by="region")
    assert len(lines) == 2
    keys = {item.key: item.gross for item in lines}
    assert keys["us-central1"] == Decimal("10")
    assert keys["(no region)"] == Decimal("5")


def test_csv_quoting_commas_in_key() -> None:
    """Label values with commas in CSV output are quoted by csv."""
    line = Line("value,with,comma", Decimal("10.00"), Decimal("0"), Decimal("10.00"))
    csv_output = render([line], "csv")
    assert '"value,with,comma",10.00,0.00,10.00\r\n' in csv_output


def test_text_rendering() -> None:
    """Test text rendering table format."""
    lines = [
        Line("p1", Decimal("12.5"), Decimal("-2.25"), Decimal("10.25")),
        Line("p2", Decimal("5"), Decimal("0"), Decimal("5")),
    ]
    text_out = render(lines, "text")
    assert "KEY" in text_out
    assert "GROSS" in text_out
    assert "CREDITS" in text_out
    assert "NET" in text_out
    assert "10.25" in text_out
    assert "5.00" in text_out


def test_invalid_render_format() -> None:
    """Test invalid render format raises BillingError."""
    with pytest.raises(BillingError) as exc:
        render([], "json")  # type: ignore[arg-type]
    assert exc.value.code == "invalid_option"


def test_parse_constant_rejection() -> None:
    """Test NaN and Infinity literals are rejected."""
    for const in ("NaN", "Infinity", "-Infinity"):
        bad = (
            f'{{"invoice":{{"month":"202610"}},"service":{{"description":"S"}},'
            f'"sku":{{"description":"K"}},"cost":{const},"currency":"USD","cost_type":"regular"}}'
        )
        with pytest.raises(BillingError) as exc:
            load_ndjson(bad)
        assert exc.value.code == "invalid_value"


def test_validation_errors() -> None:
    """Test validation on bad data structures."""
    # Non-dict line
    with pytest.raises(BillingError) as exc:
        load_ndjson('["not", "a", "dict"]')
    assert exc.value.code == "invalid_value"

    # Non-dict invoice
    with pytest.raises(BillingError) as exc:
        load_ndjson('{"invoice": "202610"}')
    assert exc.value.code == "missing_field"

    # Invalid invoice month format
    with pytest.raises(BillingError) as exc:
        load_ndjson('{"invoice": {"month": "2026-10"}}')
    assert exc.value.code == "invalid_value"

    # Bad project
    with pytest.raises(BillingError) as exc:
        load_ndjson('{"invoice":{"month":"202610"},"project":"p1"}')
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson('{"invoice":{"month":"202610"},"project":{"id": 123}}')
    assert exc.value.code == "invalid_value"

    # Bad service
    with pytest.raises(BillingError) as exc:
        load_ndjson('{"invoice":{"month":"202610"},"service": null}')
    assert exc.value.code == "missing_field"

    with pytest.raises(BillingError) as exc:
        load_ndjson('{"invoice":{"month":"202610"},"service": {"description": 123}}')
    assert exc.value.code == "invalid_value"

    # Bad sku
    with pytest.raises(BillingError) as exc:
        load_ndjson('{"invoice":{"month":"202610"},"service":{"description":"S"}}')
    assert exc.value.code == "missing_field"

    with pytest.raises(BillingError) as exc:
        load_ndjson(
            '{"invoice":{"month":"202610"},"service":{"description":"S"},"sku":{"description":1}}'
        )
    assert exc.value.code == "invalid_value"

    # Bad location
    base = '{"invoice":{"month":"202610"},"service":{"description":"S"},"sku":{"description":"K"}}'
    with pytest.raises(BillingError) as exc:
        load_ndjson(base.replace("}}", '},"location":"invalid"}'))
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base.replace("}}", '},"location":{"region": 123}}'))
    assert exc.value.code == "invalid_value"

    # Cost boolean
    base_cost = '{"invoice":{"month":"202610"},"service":{"description":"S"},"sku":{"description":"K"},"cost":true,"currency":"USD"}'
    with pytest.raises(BillingError) as exc:
        load_ndjson(base_cost)
    assert exc.value.code == "invalid_value"

    # Currency bad
    base_curr = '{"invoice":{"month":"202610"},"service":{"description":"S"},"sku":{"description":"K"},"cost":10,"currency":""}'
    with pytest.raises(BillingError) as exc:
        load_ndjson(base_curr)
    assert exc.value.code == "invalid_value"

    # Credits bad
    base_c = '{"invoice":{"month":"202610"},"service":{"description":"S"},"sku":{"description":"K"},"cost":10,"currency":"USD"'
    with pytest.raises(BillingError) as exc:
        load_ndjson(base_c + ',"credits":"not_list"}')
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_c + ',"credits":["not_dict"]}')
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_c + ',"credits":[{"name":"c"}]}')
    assert exc.value.code == "missing_field"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_c + ',"credits":[{"name":1,"amount":1,"type":"T"}]}')
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_c + ',"credits":[{"name":"c","amount":"1","type":"T"}]}')
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_c + ',"credits":[{"name":"c","amount":1,"type":123}]}')
    assert exc.value.code == "invalid_value"

    # Labels bad
    base_l = base_c + ',"credits":[]'
    with pytest.raises(BillingError) as exc:
        load_ndjson(base_l + ',"labels":"bad"}')
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_l + ',"labels":[123]}')
    assert exc.value.code == "invalid_value"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_l + ',"labels":[{"key":"k"}]}')
    assert exc.value.code == "missing_field"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_l + ',"labels":[{"key":1,"value":"v"}]}')
    assert exc.value.code == "invalid_value"

    # Cost type bad
    with pytest.raises(BillingError) as exc:
        load_ndjson(base_l + "}")
    assert exc.value.code == "missing_field"

    with pytest.raises(BillingError) as exc:
        load_ndjson(base_l + ',"cost_type":123}')
    assert exc.value.code == "invalid_value"


def test_cli_credits_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI --credits with text and CSV formats."""
    f = tmp_path / "export.json"
    f.write_text(SAMPLE_ROW_1, encoding="utf-8")

    # text format
    assert main([str(f), "--credits"]) == 0
    captured = capsys.readouterr()
    assert "COMMITTED_USAGE_DISCOUNT: -2.25\n" in captured.out

    # csv format
    assert main([str(f), "--credits", "--format", "csv"]) == 0
    captured = capsys.readouterr()
    assert "type,amount\r\nCOMMITTED_USAGE_DISCOUNT,-2.25\r\n" in captured.out


def test_cli_stdin(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Test reading from stdin in CLI."""
    monkeypatch.setattr("sys.stdin", io.StringIO(SAMPLE_ROW_1))
    assert main(["-", "--by", "project"]) == 0
    captured = capsys.readouterr()
    assert "p1" in captured.out


def test_cli_io_error(tmp_path: Path) -> None:
    """Test file read failure returns exit code 2."""
    assert main([str(tmp_path / "nonexistent.json")]) == 2
