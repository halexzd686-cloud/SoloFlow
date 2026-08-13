"""工作助手结果文件生成和 ZIP 打包。"""

# OOXML 和基础 PDF 模板包含不可拆分的协议行。
# ruff: noqa: E501

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from pydantic import BaseModel


class ArtifactRecord(BaseModel):
    name: str
    media_type: str
    path: str
    size: int


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", name).strip("-")
    return stem or "soloflow-result"


def _write_docx(path: Path, text: str) -> None:
    paragraphs = []
    for line in text.splitlines() or [""]:
        paragraphs.append(f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(paragraphs)}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr></w:body></w:document>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", document_rels)


def _write_xlsx(path: Path, text: str) -> None:
    rows = [line.split(" | ") for line in text.splitlines() or [""]]
    cells = []
    for row_index, row in enumerate(rows, 1):
        row_cells = []
        for col_index, value in enumerate(row, 1):
            column = ""
            number = col_index
            while number:
                number, remainder = divmod(number - 1, 26)
                column = chr(65 + remainder) + column
            row_cells.append(
                f'<c r="{column}{row_index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        cells.append(f'<row r="{row_index}">{"".join(row_cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(cells)}</sheetData></worksheet>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="结果" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def _write_pdf(path: Path, text: str) -> None:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen.canvas import Canvas

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        canvas = Canvas(str(path))
        canvas.setFont("STSong-Light", 11)
        y = 800
        for line in text.splitlines() or [""]:
            canvas.drawString(54, y, line[:100])
            y -= 18
            if y < 54:
                canvas.showPage()
                canvas.setFont("STSong-Light", 11)
                y = 800
        canvas.save()
        return
    except Exception:
        pass
    # 保证没有 reportlab 时仍能生成一个可打开的基础 PDF，非 ASCII 字符以 ? 表示。
    lines = [
        line.encode("latin-1", errors="replace").decode("latin-1")[:100]
        for line in text.splitlines()
    ]
    stream = (
        "BT /F1 11 Tf 54 800 Td "
        + " ".join(f"({html.escape(line)}) Tj 0 -18 Td" for line in lines or [""])
        + " ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream",
    ]
    content = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content += f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(content)
    content += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    content += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    content += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    path.write_bytes(content)


def write_artifacts(
    output_dir: Path, base_name: str, text: str, formats: list[str]
) -> list[ArtifactRecord]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(base_name)
    builders: dict[str, tuple[str, str, Any]] = {
        "md": (
            "text/markdown",
            ".md",
            lambda path, value: path.write_text(value, encoding="utf-8"),
        ),
        "markdown": (
            "text/markdown",
            ".md",
            lambda path, value: path.write_text(value, encoding="utf-8"),
        ),
        "txt": ("text/plain", ".txt", lambda path, value: path.write_text(value, encoding="utf-8")),
        "docx": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
            _write_docx,
        ),
        "xlsx": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
            _write_xlsx,
        ),
        "pdf": ("application/pdf", ".pdf", _write_pdf),
    }
    artifacts: list[ArtifactRecord] = []
    seen: set[str] = set()
    for requested in formats or ["md"]:
        normalized = requested.lower().lstrip(".")
        if normalized not in builders or normalized in seen:
            continue
        seen.add(normalized)
        media_type, extension, builder = builders[normalized]
        path = output_dir / f"{stem}{extension}"
        builder(path, text)
        artifacts.append(
            ArtifactRecord(
                name=path.name, media_type=media_type, path=str(path), size=path.stat().st_size
            )
        )
    if not artifacts:
        raise ValueError("至少选择一种支持的输出格式：Markdown、TXT、Word、Excel 或 PDF")
    return artifacts


def write_zip(
    output_dir: Path, artifacts: list[ArtifactRecord], name: str = "结果文件.zip"
) -> ArtifactRecord:
    path = output_dir / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifacts:
            archive.write(artifact.path, arcname=Path(artifact.path).name)
    return ArtifactRecord(
        name=path.name, media_type="application/zip", path=str(path), size=path.stat().st_size
    )
