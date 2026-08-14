"""P2 文件读取、隐私检查和结果文件测试。"""

import base64
import zipfile

import pytest

from soloflow.artifacts import write_artifacts, write_zip
from soloflow.file_processing import (
    FileAttachment,
    attachment_content,
    model_supports_images,
    redact_text,
)


def payload(filename: str, text: bytes) -> dict[str, str]:
    return {"filename": filename, "content_base64": base64.b64encode(text).decode("ascii")}


def test_text_and_csv_inputs_are_read_and_sensitive_values_are_detected():
    attachment = FileAttachment.from_payload(
        payload("notes.txt", "联系 13800138000 或 a@example.com".encode())
    )
    assert attachment.text == "联系 13800138000 或 a@example.com"
    assert {item.kind for item in attachment.findings} == {"phone", "email"}
    assert "[手机号已脱敏]" in redact_text(attachment.text)

    csv_file = FileAttachment.from_payload(payload("data.csv", "姓名,数量\n甲,2".encode()))
    assert "姓名 | 数量" in csv_file.text
    assert "甲 | 2" in csv_file.text


def test_docx_and_xlsx_artifacts_are_valid_zip_packages(tmp_path):
    artifacts = write_artifacts(
        tmp_path / "artifacts", "周报整理", "标题\n完成事项 | 状态", ["docx", "xlsx"]
    )
    assert len(artifacts) == 2
    for artifact in artifacts:
        with zipfile.ZipFile(artifact.path) as archive:
            assert archive.testzip() is None
    package = write_zip(tmp_path / "artifacts", artifacts)
    with zipfile.ZipFile(package.path) as archive:
        assert set(archive.namelist()) == {"周报整理.docx", "周报整理.xlsx"}


def test_pdf_artifact_has_pdf_signature(tmp_path):
    artifact = write_artifacts(tmp_path / "artifacts", "result", "测试内容", ["pdf"])[0]
    assert open(artifact.path, "rb").read(8).startswith(b"%PDF-")
    from pypdf import PdfReader

    assert len(PdfReader(artifact.path).pages) == 1


def test_image_model_capability_and_content():
    image = FileAttachment(
        filename="chart.png",
        media_type="image/png",
        size=3,
        data_base64=base64.b64encode(b"png").decode("ascii"),
    )
    assert not model_supports_images("deepseek-chat")
    assert model_supports_images("deepseek-vl2")
    with pytest.raises(ValueError, match="图片输入"):
        attachment_content([image], "deepseek-chat")
    content = attachment_content([image], "deepseek-vl2")
    assert isinstance(content, list)
    assert content[-1]["type"] == "image_url"
