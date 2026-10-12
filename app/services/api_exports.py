"""Binary exports shared by import and reporting endpoints."""
from io import BytesIO
from fastapi.responses import Response

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def excel_response(headers, rows, filename):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Report")
    for values in [headers, *rows]:
        cells = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            # Imported/user text must never become an executable spreadsheet formula.
            if isinstance(value, str):
                cell.data_type = "s"
            cells.append(cell)
        sheet.append(cells)
    output = BytesIO()
    workbook.save(output)
    return Response(output.getvalue(), media_type=XLSX_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def error_excel_response(errors, filename):
    import json
    return excel_response(["Row", "Message", "Data"], [
        [item.get("row"), item.get("message") or "; ".join(item.get("errors") or []),
         json.dumps(item.get("data") or {}, ensure_ascii=False, default=str)]
        for item in errors
    ], filename)


def pdf_response(headers, rows, filename):
    from html import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, TableStyle

    output = BytesIO()
    style = getSampleStyleSheet()["BodyText"]
    style.fontSize = 8
    style.leading = 10
    cells = [[Paragraph(escape(str(value if value is not None else "")), style)
              for value in values] for values in [headers, *rows]]
    document = SimpleDocTemplate(output, pagesize=landscape(A4),
                                 leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    table = LongTable(cells, repeatRows=1, colWidths=[document.width / len(headers)] * len(headers))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    document.build([Paragraph("Recent Upload Report", getSampleStyleSheet()["Title"]), table])
    return Response(output.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
