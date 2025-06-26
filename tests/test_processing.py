import os
from pathlib import Path
from unittest import mock
import fitz

from pdf_renamer import FileHandler


def create_dummy_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


def test_process_existing_pdfs(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    pdf_path = input_dir / "sample.pdf"
    create_dummy_pdf(pdf_path)

    with mock.patch.object(
        FileHandler, "generate_filename_with_openai", return_value="test_doc"
    ):
        handler = FileHandler(str(input_dir), str(output_dir))
        handler.executor.shutdown(wait=True)

    assert (output_dir / "test_doc.pdf").exists()
