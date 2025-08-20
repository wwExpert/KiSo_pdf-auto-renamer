import sys
from pathlib import Path
from unittest import mock
import fitz

sys.path.append(str(Path(__file__).resolve().parent.parent))
from pdf_renamer import FileHandler, convert_pdf_to_images


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


def test_convert_pdf_respects_max_pages(tmp_path):
    pdf_path = tmp_path / "multi.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    images = convert_pdf_to_images(str(pdf_path), max_pages=2)
    assert len(images) == 2
