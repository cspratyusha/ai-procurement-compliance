"""Excel bills of quantities: CPPP and GeM publish BOQs as spreadsheets."""

import io
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extraction  # noqa: E402

# Laid out like an NIC eProcurement BOQ: tender details above the table,
# a header row, a section heading, then items with rates.
_ROWS = [
    ["Name of Work: Electrical works for the new office block", None, None, None, None],
    ["Tender Inviting Authority: Executive Engineer", None, None, None, None],
    [None, None, None, None, None],
    ["Sl. No.", "Item Description", "Quantity", "Units", "Estimated Rate"],
    [None, "Wiring works", None, None, None],
    [1, "Supply of 1200 mm sweep ceiling fan with electronic regulator, BEE 5 star", 50, "Nos", 3200],
    [2, "Supply of PVC insulated copper conductor single core cable 2.5 sq mm, 1100 V grade", 2000.0, "Metre", 28],
    [3, "Supply of 32 A double pole MCB", 40, "Nos", 450],
]


def _xlsx(rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "BoQ1"
    for row in rows:
        sheet.append(row)
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def test_xlsx_boq_rows_become_line_items():
    doc = extraction.extract("BOQ.xlsx", _xlsx(_ROWS))
    assert doc.method == "spreadsheet"
    items = extraction.split_line_items(doc.text)
    assert [i["quantity"] for i in items] == ["50 Nos", "2000 Metre", "40 Nos"]
    assert items[0]["query"].startswith("Supply of 1200 mm sweep ceiling fan")
    # The section heading and the tender details are not items.
    assert not any("Wiring works" == i["query"] for i in items)
    assert not any("Name of Work" in i["query"] for i in items)


def test_a_sheet_without_headings_is_read_by_its_serial_numbers():
    rows = [[1, "Ordinary Portland cement 43 grade in 50 kg bags", "820 bags"],
            [2, "TMT reinforcement bars Fe 500D, 12 mm", "12 tonnes"]]
    items = extraction.split_line_items(extraction.extract("boq.xlsx", _xlsx(rows)).text)
    assert [i["query"].split(",")[0] for i in items] == ["Ordinary Portland cement 43 grade in 50 kg bags",
                                                         "TMT reinforcement bars Fe 500D"]


def test_xls_is_read_too():
    xlwt = pytest.importorskip("xlwt", reason="writing a legacy .xls needs xlwt")
    book = xlwt.Workbook()
    sheet = book.add_sheet("BoQ1")
    for r, row in enumerate(_ROWS):
        for c, value in enumerate(row):
            if value is not None:
                sheet.write(r, c, value)
    buf = io.BytesIO()
    book.save(buf)
    items = extraction.split_line_items(extraction.extract("BOQ.xls", buf.getvalue()).text)
    assert len(items) == 3


def test_a_file_that_is_not_a_workbook_says_so():
    with pytest.raises(extraction.ExtractionError, match="Excel"):
        extraction.extract("BOQ.xlsx", b"PK\x03\x04 not really a workbook")
