#!/usr/bin/env python3
"""Rating workbooks for the two-rater relevance check (PROTOCOL.md B.7).

One .xlsx per rater from results/relevance/items-R*.json: an instruction sheet
with a worked example, and the 60 blinded records with a dropdown judgement
and a note column. Raters fill in only the shaded cells.
"""
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

FONT = "Arial"
FILL = PatternFill("solid", fgColor="FFF2CC")
HEAD = PatternFill("solid", fgColor="D9E2E8")
THIN = Side(style="thin", color="B7C4CC")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CHOICES = ("On-topic", "Not on-topic")
QUESTION = ("Is this document on-topic for someone who searched for the term shown "
            "in EU policy and funding for agriculture, mining or the bioeconomy?")


def f(bold=False, size=10, italic=False, color="000000"):
    return Font(name=FONT, bold=bold, size=size, italic=italic, color=color)


def instructions(ws, rater, n):
    ws.title = "Instructions"
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 95
    rows = [
        ("Relevance check", ""),
        ("Study", "BioFairNet back-test of the Policy & Grant Finder — pre-registered, doi:10.17605/OSF.IO/QC2SP"),
        ("Rater", rater),
        ("Records", f"{n}, on the sheet 'Ratings'"),
        ("", ""),
        ("The question", QUESTION),
        ("How to answer", "For each row, choose On-topic or Not on-topic in the yellow 'Judgement' column. "
                          "Judge the record on its own, from its title and summary; open the source link only "
                          "if those are not enough."),
        ("Note", "Optional. Use it for borderline cases: one line on why it was a close call."),
        ("Please do not", "change any other cell; look up how the tool ranked a record; discuss records with "
                          "the other rater before you have both finished; or open the study's "
                          "results/relevance folder until you are done."),
        ("When finished", "Save the file and return it to the study lead. 'Rated' at the top of the Ratings "
                          "sheet should read " + f"{n} of {n}."),
        ("", ""),
        ("Example row", "(made up, to show the format — not one of your records)"),
    ]
    for r, (a, b) in enumerate(rows, 1):
        ws.cell(r, 1, a).font = f(bold=True, size=14 if r == 1 else 10)
        c = ws.cell(r, 2, b)
        c.font = f(size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 1).alignment = Alignment(vertical="top")
    ws.cell(6, 2).font = f(bold=True, size=11)
    ex = [("Search term", "soil"), ("Type", "EU funding record"), ("Title", "Restoring soil carbon on arable farms"),
          ("Summary", "Field trials of cover crops and reduced tillage to raise soil organic carbon…"),
          ("Judgement", "On-topic"), ("Note", "")]
    for i, (a, b) in enumerate(ex, 13):
        ws.cell(i, 1, a).font = f(italic=True, color="5B6B76")
        c = ws.cell(i, 2, b)
        c.font = f(italic=True, color="5B6B76")
        if a in ("Judgement", "Note"):
            c.fill = FILL


def ratings(ws, items):
    ws.title = "Ratings"
    cols = [("Item", 6), ("Search term", 14), ("Type", 16), ("Date", 11), ("Title", 42),
            ("Summary", 70), ("Source link", 22), ("Judgement", 15), ("Note (optional)", 32)]
    ws["A1"] = "Rated"
    ws["A1"].font = f(bold=True)
    last = len(items) + 3
    ws["B1"] = f'=COUNTIF(H4:H{last},"{CHOICES[0]}")+COUNTIF(H4:H{last},"{CHOICES[1]}")&" of {len(items)}"'
    ws["B1"].font = f(bold=True)
    ws["D1"] = "Fill in only the yellow cells: Judgement (choose from the list) and, if you like, Note."
    ws["D1"].font = f(italic=True, color="5B6B76")
    for c, (name, width) in enumerate(cols, 1):
        cell = ws.cell(3, c, name)
        cell.font = f(bold=True)
        cell.fill = HEAD
        cell.border = BOX
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    dv = DataValidation(type="list", formula1='"' + ",".join(CHOICES) + '"', allow_blank=True,
                        showErrorMessage=True, errorTitle="Judgement",
                        error="Please choose On-topic or Not on-topic.")
    ws.add_data_validation(dv)
    for r, it in enumerate(items, 4):
        vals = [it["item"], it["query"], it["type"], it["date"] or "", it["title"], it["summary"],
                it["url"], None, None]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(r, c, v)
            cell.font = f()
            cell.border = BOX
            cell.alignment = Alignment(wrap_text=c in (5, 6, 9), vertical="top")
        link = ws.cell(r, 7)
        if it["url"]:
            link.hyperlink = it["url"]
            link.value = "open record"
            link.font = Font(name=FONT, size=10, color="1F6F78", underline="single")
        for c in (8, 9):
            ws.cell(r, c).fill = FILL
        dv.add(f"H{r}")
        ws.row_dimensions[r].height = 60
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:I{last}"


def main(relevance_dir="paper/results/relevance"):
    d = Path(relevance_dir)
    out = d / "sheets"
    out.mkdir(exist_ok=True)
    for rater in ("R1", "R2"):
        items = json.loads((d / f"items-{rater}.json").read_text(encoding="utf-8"))
        wb = Workbook()
        instructions(wb.active, f"Rater {rater[1]}", len(items))
        ratings(wb.create_sheet(), items)
        wb.active = 1
        path = out / f"relevance-rating-{rater}.xlsx"
        wb.save(path)
        print(path)


if __name__ == "__main__":
    main(*sys.argv[1:])
