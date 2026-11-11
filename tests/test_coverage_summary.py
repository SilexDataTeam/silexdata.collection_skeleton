# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""coverage-summary: the docsite page rendered from coverage.py's index.html."""

import pathlib
import subprocess
import sys

import pytest

SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github"
    / "actions"
    / "coverage-summary"
    / "generate_coverage_summary.py"
)

# coverage.py 7.x index.html file tables, reduced to the markup the script
# reads. Branch coverage adds the "branches" and "partial" columns.
HEADS = {
    "branch": ["file", "statements", "missing", "excluded", "branches", "partial", "coverage"],
    "line": ["file", "statements", "missing", "excluded", "coverage"],
}
ROWS = {
    "branch": [
        ("z_9d8e_inventory_py.html", "plugins/inventory/inventory.py",
         ["101", "3", "0", "22", "2"], "96%"),
        ("z_6fa0_test_inventory_py.html", "tests/unit/test_inventory.py",
         ["185", "0", "0", "6", "0"], "100%"),
    ],
    "line": [
        ("z_c09b_manage_akamai_py.html", "plugins/modules/manage_akamai.py",
         ["88", "6", "1"], "93%"),
    ],
}


def index_html(kind, heads=None):
    head = "".join(
        f'<th id="{h}" aria-sort="none">{h}<span class="arrows"></span></th>'
        for h in heads or HEADS[kind]
    )
    body = "".join(
        f'<tr class="region"><td class="name left"><a href="{href}">{name}</a></td>'
        + "".join(f"<td>{n}</td>" for n in numbers)
        + f'<td class="right" data-ratio="1 1">{pct}</td></tr>'
        for href, name, numbers, pct in ROWS[kind]
    )
    total = '<tr class="total"><td class="name left">Total</td><td>1</td></tr>'
    return (
        '<table class="index" data-sortable><thead><tr class="tablehead">'
        f"{head}</tr></thead><tbody>{body}</tbody><tfoot>{total}</tfoot></table>"
    )


def summarize(tmp_path, html):
    index = tmp_path / "index.html"
    index.write_text(html)
    output = tmp_path / "coverage-report.rst"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(index), str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, output


def table_rows(rst):
    """The list-table's body rows as [file, statements, missing, coverage]."""
    rows, row = [], None
    for line in rst.splitlines():
        if line.startswith("   * - "):
            row = [line.removeprefix("   * - ")]
            rows.append(row)
        elif line.startswith("     - ") and row is not None:
            row.append(line.removeprefix("     - "))
    return rows[1:]


@pytest.mark.parametrize("kind", ["branch", "line"])
def test_columns_are_found_by_header_not_position(tmp_path, kind):
    proc, output = summarize(tmp_path, index_html(kind))
    assert proc.returncode == 0, proc.stderr
    assert table_rows(output.read_text()) == [
        [f"`{name} <../coverage/{href}>`_", numbers[0], numbers[1], pct]
        for href, name, numbers, pct in ROWS[kind]
    ]


def test_totals_row_is_not_listed_as_a_file(tmp_path):
    _, output = summarize(tmp_path, index_html("branch"))
    assert "Total" not in output.read_text()


def test_unrecognised_table_fails_instead_of_misreporting(tmp_path):
    heads = [h for h in HEADS["line"] if h != "missing"]
    proc, output = summarize(tmp_path, index_html("line", heads))
    assert proc.returncode != 0
    assert "missing" in proc.stderr
    assert not output.exists()
