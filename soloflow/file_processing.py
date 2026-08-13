"""本地输入文件读取、图片能力判断和敏感信息检查。"""

# 文件格式协议和中文提示中保留少量长行。
# ruff: noqa: E501

from __future__ import annotations

import base64
import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pydantic import BaseModel, Field

SUPPORTED_EXTENSIONS = frozenset(
    {".docx", ".xlsx", ".csv", ".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg"}
)
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})
MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class SensitiveFinding(BaseModel):
    kind: str
    label: str
    masked_sample: str = ""
    suggestion: str


class FileAttachment(BaseModel):
    """一次运行中的本地输入文件，不保存 API Key。"""

    filename: str
    media_type: str
    size: int
    text: str = ""
    data_base64: str = ""
    findings: list[SensitiveFinding] = Field(default_factory=list)
    warning: str = ""

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()

    @property
    def is_image(self) -> bool:
        return self.extension in IMAGE_EXTENSIONS

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FileAttachment:
        filename = Path(str(payload.get("filename", ""))).name
        if not filename:
            raise ValueError("附件缺少文件名")
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"暂不支持文件类型：{extension or '未知类型'}")
        encoded = str(payload.get("content_base64", ""))
        try:
            raw = base64.b64decode(encoded, validate=True) if encoded else b""
        except ValueError as exc:
            raise ValueError(f"文件内容无法读取：{filename}") from exc
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError(f"文件过大（单个文件上限 20 MB）：{filename}")
        text, warning = extract_text(filename, raw)
        findings = scan_sensitive(text)
        return cls(
            filename=filename,
            media_type=MEDIA_TYPES[extension],
            size=len(raw),
            text=text,
            data_base64=encoded,
            findings=findings,
            warning=warning,
        )


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text(filename: str, raw: bytes) -> tuple[str, str]:
    extension = Path(filename).suffix.lower()
    if extension in {".txt", ".md"}:
        return decode_text(raw), ""
    if extension == ".csv":
        return _extract_csv(raw), ""
    if extension == ".docx":
        return _extract_docx(raw), ""
    if extension == ".xlsx":
        return _extract_xlsx(raw), ""
    if extension == ".pdf":
        return _extract_pdf(raw)
    if extension in IMAGE_EXTENSIONS:
        return "", "图片不会被 OCR；只有支持图片输入的 DeepSeek 模型可以处理。"
    raise ValueError(f"暂不支持文件类型：{extension or '未知类型'}")


def _extract_csv(raw: bytes) -> str:
    text = decode_text(raw)
    rows = csv.reader(io.StringIO(text))
    return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)


def _extract_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
    except (KeyError, ElementTree.ParseError, zipfile.BadZipFile) as exc:
        raise ValueError("Word 文件结构无法读取") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _extract_xlsx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                for item in shared_root.iter(f"{namespace}si"):
                    shared.append("".join(node.text or "" for node in item.iter(f"{namespace}t")))
            sheet_name = "xl/worksheets/sheet1.xml"
            sheet_root = ElementTree.fromstring(archive.read(sheet_name))
    except (KeyError, ElementTree.ParseError, zipfile.BadZipFile) as exc:
        raise ValueError("Excel 文件结构无法读取") from exc

    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rows: list[str] = []
    for row in sheet_root.iter(f"{namespace}row"):
        values: list[str] = []
        for cell in row.findall(f"{namespace}c"):
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{namespace}v")
            inline_node = cell.find(f"{namespace}is")
            value = value_node.text if value_node is not None and value_node.text else ""
            if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                value = shared[int(value)]
            elif cell_type == "inlineStr" and inline_node is not None:
                value = "".join(node.text or "" for node in inline_node.iter(f"{namespace}t"))
            values.append(value)
        if values:
            rows.append(" | ".join(values))
    return "\n".join(rows)


def _extract_pdf(raw: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        return text, "" if text else "PDF 没有可提取的文本；扫描件和 OCR 暂不支持。"
    except ImportError:
        return "", "当前环境缺少 PDF 文本提取组件；扫描件和 OCR 暂不支持。"
    except Exception as exc:
        raise ValueError("PDF 文件无法读取") from exc


def scan_sensitive(text: str) -> list[SensitiveFinding]:
    patterns = [
        ("phone", "手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)", "请确认是否需要脱敏手机号"),
        (
            "email",
            "邮箱",
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "请确认是否需要脱敏邮箱",
        ),
        ("id_card", "身份证号", r"(?<!\d)\d{17}[\dXx](?!\d)", "请确认是否需要脱敏身份证号"),
        ("bank_card", "银行卡号", r"(?<!\d)\d{16,19}(?!\d)", "请确认是否需要脱敏长数字串"),
    ]
    findings: list[SensitiveFinding] = []
    seen: set[tuple[str, str]] = set()
    for kind, label, pattern, suggestion in patterns:
        for match in re.finditer(pattern, text):
            sample = match.group(0)
            masked = sample[:2] + "*" * max(0, len(sample) - 4) + sample[-2:]
            key = (kind, masked)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                SensitiveFinding(
                    kind=kind, label=label, masked_sample=masked, suggestion=suggestion
                )
            )
    return findings


def redact_text(text: str) -> str:
    replacements = [
        (r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已脱敏]"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]"),
        (r"(?<!\d)\d{17}[\dXx](?!\d)", "[身份证号已脱敏]"),
        (r"(?<!\d)\d{16,19}(?!\d)", "[长数字串已脱敏]"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def model_supports_images(model: str) -> bool:
    normalized = model.lower()
    return any(marker in normalized for marker in ("-vl", "vision", "visual", "image"))


def attachment_content(attachments: list[FileAttachment], model: str) -> str | list[dict[str, Any]]:
    images = [attachment for attachment in attachments if attachment.is_image]
    if images and not model_supports_images(model):
        raise ValueError(
            "当前 DeepSeek 模型没有标记为支持图片输入，请切换到带 vl/vision 标识的模型"
        )
    text_parts = [
        f"【附件：{attachment.filename}】\n{attachment.text}"
        for attachment in attachments
        if attachment.text.strip()
    ]
    text = "\n\n".join(text_parts)
    if not images:
        return text
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for image in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image.media_type};base64,{image.data_base64}",
                },
            }
        )
    return content
