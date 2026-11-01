"""Bounded, dependency-free data exports. Spreadsheet cells never contain formulas."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZIP_DEFLATED, ZipFile

from starlette.exceptions import HTTPException
from starlette.responses import Response

MAX_ROWS = 10_000
MAX_JOIN_ROWS = 1_000
MAX_LINKS = 10_000
MAX_BYTES = 32 * 1024 * 1024
FORMATS = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _xlsx(headers: Sequence[str], rows: Sequence[Sequence[str | None]]) -> bytes:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    root = Element("worksheet", xmlns=ns)
    cols = SubElement(root, "cols")
    SubElement(cols, "col", min="1", max=str(len(headers)), width="24", customWidth="1")
    data = SubElement(root, "sheetData")
    for values in (headers, *rows):
        row = SubElement(data, "row")
        for value in values:
            cell = SubElement(row, "c", t="inlineStr")
            text = SubElement(SubElement(cell, "is"), "t", {"xml:space": "preserve"})
            text.text = _XML_INVALID.sub("", value or "")
    xml = tostring(root, encoding="utf-8", xml_declaration=True)
    output = io.BytesIO()
    relns = "http://schemas.openxmlformats.org/package/2006/relationships"
    docrel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    sheettype = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{sheettype}.sheet.main+xml"/>'
            f'<Override PartName="/xl/worksheets/sheet1.xml" '
            f'ContentType="{sheettype}.worksheet+xml"/>'
            f'<Override PartName="/xl/styles.xml" ContentType="{sheettype}.styles+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{relns}">'
            f'<Relationship Id="rId1" Type="{docrel}/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{docrel}">'
            '<sheets><sheet name="Export" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{relns}">'
            f'<Relationship Id="rId1" Type="{docrel}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{docrel}/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/styles.xml",
            f'<styleSheet xmlns="{ns}">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="1"><xf applyAlignment="1"><alignment wrapText="1" '
            'vertical="top"/></xf></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
            "</cellStyles></styleSheet>",
        )
        archive.writestr("xl/worksheets/sheet1.xml", xml)
    return output.getvalue()


def download(slug: str, format: str, headers: list[str], rows: list[list[str | None]]) -> Response:
    """All values are text to preserve Decimal, UUID and large integer precision."""
    # Check before rendering; XLSX has a per-cell text limit of 32767 UTF-16 units.
    if (
        sum(len((value or "").encode("utf-8")) for row in [headers, *rows] for value in row)
        > MAX_BYTES
    ):
        raise HTTPException(413, "Export is too large. Narrow the filters.")
    if format == "xlsx":
        if any(len((v or "").encode("utf-16-le")) > 65534 for row in [headers, *rows] for v in row):
            raise HTTPException(413, "A cell exceeds the XLSX text limit. Choose CSV.")
        content = _xlsx(headers, rows)
    elif format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        for row in [headers, *rows]:
            writer.writerow(
                "'" + value
                if value
                and (
                    value.startswith(("\t", "\r", "\n"))
                    or value.lstrip().startswith(("=", "+", "-", "@"))
                )
                else value
                for value in row
            )
        content = output.getvalue().encode("utf-8-sig")
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Export is too large. Narrow the filters.")
    return Response(
        content,
        media_type=FORMATS[format],
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.{format}"',
        },
    )
