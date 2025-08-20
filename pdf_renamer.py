import os
import re
import shutil
import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

import fitz  # PyMuPDF
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from openai import OpenAI


load_dotenv()
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
MAX_PAGES = int(os.getenv("MAX_PAGES", "4"))
_openai_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    """Create an OpenAI client lazily to avoid import side effects."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def wait_for_file_ready(
    path: str, timeout: float = 10.0, interval: float = 0.5
) -> bool:
    """Wait until a file is ready for reading."""
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(path):
            try:
                with open(path, "rb"):
                    return True
            except Exception:
                time.sleep(interval)
        else:
            time.sleep(interval)
    return False


def convert_pdf_to_images(pdf_path: str, max_pages: int | None = None) -> list[str]:
    """Konvertiert Seiten eines PDFs in Base64-kodierte JPEG-Bilder."""
    images: list[str] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            pix = page.get_pixmap()
            img_bytes = pix.tobytes("jpeg")
            images.append(base64.b64encode(img_bytes).decode("utf-8"))
    return images


class FileHandler(FileSystemEventHandler):
    def __init__(self, input_dir: str, output_dir: str, on_processed=None) -> None:
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.on_processed = on_processed
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.input_dir, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.process_existing_pdfs()

    def process_existing_pdfs(self) -> None:
        """Verarbeitet bereits vorhandene PDFs im Eingangsverzeichnis."""
        for file_name in os.listdir(self.input_dir):
            if file_name.lower().endswith(".pdf"):
                path = os.path.join(self.input_dir, file_name)
                logging.info(f"Verarbeite vorhandene Datei: {path}")
                self.executor.submit(self.process_pdf, path)

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        if event.src_path.lower().endswith(".pdf"):
            logging.info(f"Neue PDF erkannt: {event.src_path}")
            self.executor.submit(self.process_pdf, event.src_path)

    def process_pdf(self, pdf_path: str) -> None:
        try:
            if not wait_for_file_ready(pdf_path):
                raise FileNotFoundError(f"File {pdf_path} is not ready for processing.")
            images = convert_pdf_to_images(pdf_path, max_pages=MAX_PAGES)
            filename = self.generate_filename_with_openai(images)
            new_name = f"{filename}.pdf"
            new_path = os.path.join(self.output_dir, new_name)
            base_name = filename
            counter = 1
            while os.path.exists(new_path):
                new_name = f"{base_name}_{counter}.pdf"
                new_path = os.path.join(self.output_dir, new_name)
                counter += 1
            shutil.move(pdf_path, new_path)
            logging.info(f"Datei verschoben nach {new_path}")
            if self.on_processed:
                self.on_processed(new_path)
        except Exception as e:
            logging.error(f"Fehler beim Verarbeiten von {pdf_path}: {e}")
            fallback_name = f"Fehler_doc_{os.path.basename(pdf_path)}"
            fallback_path = os.path.join(self.output_dir, fallback_name)
            try:
                shutil.move(pdf_path, fallback_path)
                logging.info(f"Fallback-Name verwendet: {fallback_path}")
                if self.on_processed:
                    self.on_processed(fallback_path)
            except Exception as e2:
                logging.critical(
                    f"Kritischer Fehler: Datei {pdf_path} konnte nicht verschoben werden - {e2}"
                )

    def generate_filename_with_openai(self, images: list[str]) -> str:
        prompt = (
            "Analysiere das folgende Dokument und erzeuge einen Dateinamen im Format "
            "YYYY-MM-DD_FIRMA_DOKUMENTENTYP_ID. Gib nur den Dateinamen ohne Endung zurück."
        )
        content = [{"type": "text", "text": prompt}]
        for img in images:
            data_uri = f"data:image/jpeg;base64,{img}"
            content.append({"type": "image_url", "image_url": {"url": data_uri}})
        try:
            client = get_openai_client()
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": content}],
                max_tokens=100,
            )
            file_name = response.choices[0].message.content.strip()
            file_name = re.sub(r"\s+", "_", file_name)
            file_name = re.sub(r"[^\w\-]", "", file_name)
            return file_name[:70] if file_name else "UNKNOWN_DOC"
        except Exception as e:
            logging.error(f"Fehler bei der {MODEL_NAME} Verarbeitung: {e}")
            return "UNKNOWN_DOC"


def main() -> None:
    input_dir = os.getenv("INPUT_DIR", "C:/tmp/PDF_Input")
    output_dir = os.getenv("OUTPUT_DIR", "C:/tmp/PDF_Processed")
    handler = FileHandler(input_dir, output_dir)
    observer = Observer()
    observer.schedule(handler, input_dir, recursive=False)
    observer.start()
    logging.info(f"Überwache {input_dir} auf PDF-Dateien...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    handler.executor.shutdown(wait=True)


if __name__ == "__main__":
    main()
