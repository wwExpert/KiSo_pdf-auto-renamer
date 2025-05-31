import os
import re
import shutil
import fitz  # PyMuPDF
import logging
import time
import tempfile
import base64
import argparse # Added argparse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from openai import OpenAI, APIError # Import APIError
from concurrent.futures import ThreadPoolExecutor

# Erstelle eine Instanz des OpenAI-Clients (API-Key wird über die Umgebungsvariable bezogen)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Logging-Konfiguration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def encode_image(image_path):
    """
    Liest eine lokale Bilddatei und gibt einen Base64-kodierten String zurück.
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def store_image(image_bytes: bytes) -> str:
    """
    Speichert Bildbytes temporär auf der Festplatte und gibt den Dateipfad zurück.
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(image_bytes)
            temp_file_path = tmp.name
        logging.info(f"Bild zwischengespeichert unter: {temp_file_path}")
        return temp_file_path
    except Exception as e:
        logging.error(f"Fehler beim Zwischenspeichern des Bildes: {e}")
        return ""

class FileHandler(FileSystemEventHandler):
    def __init__(self, input_dir: str, output_dir: str, model_name: str):
        """
        Initialisiert den FileHandler mit Eingabe- und Ausgabe-Verzeichnissen und dem OpenAI-Modellnamen.
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.model_name = model_name # Store model name
        os.makedirs(output_dir, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=4)

    def on_created(self, event):
        """
        Wird aufgerufen, wenn eine neue Datei erstellt wird.
        Bei PDF-Dateien wird die Verarbeitung asynchron gestartet.
        """
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.pdf'):
            logging.info(f"Neue PDF erkannt: {event.src_path}")
            self.executor.submit(self.process_pdf, event.src_path)

    def process_pdf(self, pdf_path: str):
        """
        Verarbeitet eine PDF-Datei:
        - Extrahiert den Text und das beste Bild der ersten Seite.
        - Speichert das Bild temporär und konvertiert es in einen Base64-String.
        - Ruft die OpenAI API zur Bildanalyse auf.
        - Generiert einen neuen Dateinamen und verschiebt die Datei ins Ausgabe-Verzeichnis.
        """
        try:
            with fitz.open(pdf_path) as doc:
                first_page = doc.load_page(0)
                page_text = first_page.get_text()
                images = first_page.get_images(full=True)
                best_candidate = None
                if images:
                    for img in images:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        width = base_image.get("width") or 0
                        height = base_image.get("height") or 0
                        area = width * height
                        if best_candidate is None or area > best_candidate["area"]:
                            best_candidate = {"image_bytes": base_image["image"], "area": area}
                    image_path_local = None  # Initialize image_path_local
                    if best_candidate is not None:
                        try:
                            image_path_local = store_image(best_candidate["image_bytes"])
                            if image_path_local:
                                vision_result = self.process_image_with_openai(image_path_local, page_text)
                            else:
                                vision_result = "NO_VISION_DATA"
                        finally:
                            if image_path_local and os.path.exists(image_path_local):
                                try:
                                    os.remove(image_path_local)
                                    logging.info(f"Temporäre Bilddatei {image_path_local} gelöscht.")
                                except Exception as e_remove:
                                    logging.error(f"Fehler beim Löschen der temporären Bilddatei {image_path_local}: {e_remove}")
                    else:
                        vision_result = "NO_VISION_DATA"
                else:
                    vision_result = "NO_VISION_DATA"
        except Exception as e:
            logging.error(f"Fehler beim Öffnen der PDF {pdf_path}: {e}")
            return

        logging.info(f"Vision Result: {vision_result}")
        filename = self.generate_filename_with_openai(vision_result)
        base_name = filename
        new_name = f"{base_name}.pdf"
        new_path = os.path.normpath(os.path.join(self.output_dir, new_name))
        counter = 1
        while os.path.exists(new_path):
            new_name = f"{base_name}_{counter}.pdf"
            new_path = os.path.normpath(os.path.join(self.output_dir, new_name))
            counter += 1

        new_name = new_name[:240]
        new_path = os.path.normpath(os.path.join(self.output_dir, new_name))

        try:
            shutil.move(pdf_path, new_path)
            logging.info(f"Datei verschoben nach {new_path}")
        except Exception as e:
            fallback_name = f"Fehler_doc_{os.path.basename(pdf_path)}"
            fallback_path = os.path.normpath(os.path.join(self.output_dir, fallback_name))
            try:
                shutil.move(pdf_path, fallback_path)
                logging.info(f"Fallback-Name verwendet: {fallback_path}")
            except Exception as e_critical:
                logging.critical(f"Kritischer Fehler: Datei {pdf_path} konnte nicht verschoben werden - {e_critical}")

    def process_image_with_openai(self, image_path: str, page_text: str) -> str:
        """
        Verarbeitet ein Bild mittels der OpenAI API, indem das Bild als Base64-kodierter data URI übergeben wird.
        """
        text = "Extrahiere den Text aus dem Bild und analysiere den Inhalt. Ziel ist es, relevante Informationen zu identifizieren, um einen Dateinamen zu generieren. Referenznummern, Betreff, Absender, Empfänger, Datumsangaben sind besonders wichtig. Beispiel: YYYY-MM-DD_FIRMA_DOKUMENTENTYP (z.B. Rechnung)_Betreff_ID"
        try:
            base64_image = encode_image(image_path)
            data_uri = f"data:image/jpeg;base64,{base64_image}"
            logging.info(f"Verarbeite Bild mit OpenAI, data URI Länge: {len(data_uri)}")
            response = openai_client.chat.completions.create(
                model=self.model_name, # Use stored model name
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": text},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                max_tokens=300,
            )
            vision_output = response.choices[0].message.content
            logging.info(f"OpenAI Vision output erhalten (Länge: {len(vision_output)} Zeichen)")
            return vision_output
        except APIError as e:
            error_details = f"OpenAI API Error during Vision processing: Status Code: {e.status_code}, Response: {e.response.text if e.response else 'N/A'}, Request ID: {e.request_id if hasattr(e, 'request_id') else 'N/A'}"
            logging.error(error_details)
            return "Vision Analysis Failed due to API Error"
        except Exception as e:
            logging.error(f"Fehler bei der OpenAI Vision Verarbeitung: {e}")
            return "Vision Analysis Failed"

    def generate_filename_with_openai(self, content: str) -> str:
        """
        Nutzt den analysierten Inhalt, um einen prägnanten Dateinamen zu generieren.
        Der Textprompt wird über die OpenAI API an das Modell gesendet.
        """
        prompt = (
            f"Analysiere den folgenden Inhalt:\n"
            f"{content}\n\n"
            f"Erzeuge einen prägnanten, aussagekräftigen Dateinamen im Format: "
            f"YYYY-MM-DD_FIRMA_DOKUMENTENTYP_ID\n"
            f"Beispiel: 2024-11-23_AOK_Rückzahlung_Kndnr1234\n"
            f"Verwende ausschließlich alphanumerische Zeichen und Unterstriche. "
            f"Gib nur den Dateinamen (ohne Dateiendung) zurück."
        )
        try:
            response = openai_client.chat.completions.create(
                model=self.model_name, # Use stored model name
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
            )
            output_text = response.choices[0].message.content.strip()
            logging.info("OpenAI model response:\n" + output_text) # Generic log message

            # a. Get output_text from OpenAI (done above)
            # b. Strip HTML tags
            output_text = re.sub(r'<[^>]+>', '', output_text).strip()

            # c. Take the first line
            try:
                file_name = output_text.splitlines()[0].strip()
            except IndexError:
                file_name = "" # Handle empty output_text case

            # d. If file_name is empty, return "UNKNOWN_DOC"
            if not file_name:
                logging.warning("OpenAI response resulted in empty filename after initial processing.")
                return "UNKNOWN_DOC"

            # e. Replace whitespace with underscores
            file_name = re.sub(r'\s+', '_', file_name)

            # f. Keep only alphanumeric, hyphens (and underscores via \w)
            file_name = re.sub(r'[^\w\-]', '', file_name)

            # g. Consolidate multiple underscores
            file_name = re.sub(r'_+', '_', file_name)

            # h. Strip leading/trailing underscores
            file_name = file_name.strip('_')

            # i. If file_name is empty after sanitization, return "UNKNOWN_DOC"
            if not file_name:
                logging.warning("Filename became empty after sanitization.")
                return "UNKNOWN_DOC"

            # j. Truncate to 70 characters
            file_name = file_name[:70]

            # k. Final check (redundant due to checks at step i and d, but good for safety)
            return file_name if file_name else "UNKNOWN_DOC"
        except APIError as e:
            error_details = f"OpenAI API Error during filename generation: Status Code: {e.status_code}, Response: {e.response.text if e.response else 'N/A'}, Request ID: {e.request_id if hasattr(e, 'request_id') else 'N/A'}"
            logging.error(error_details)
            return "UNKNOWN_DOC_API_ERROR"
        except Exception as e:
            logging.error(f"Error during OpenAI processing or filename sanitization: {e}")
            return "UNKNOWN_DOC"

def main():
    parser = argparse.ArgumentParser(description="Monitors a directory for PDF files, processes them using AI, and renames them.")
    parser.add_argument(
        "-i",
        "--input-dir",
        default="C:/tmp/PDF_Input",
        help="Directory to monitor for new PDF files. Default: C:/tmp/PDF_Input"
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="C:/tmp/PDF_Processed",
        help="Directory to store processed PDF files. Default: C:/tmp/PDF_Processed"
    )
    parser.add_argument(
        "-m",
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model to use for processing. Default: gpt-4o-mini"
    )
    args = parser.parse_args()

    # Verwende die geparsten Argumente
    event_handler = FileHandler(args.input_dir, args.output_dir, args.model) # Pass model
    observer = Observer()
    observer.schedule(event_handler, args.input_dir, recursive=False) # Verwende args.input_dir
    observer.start()
    logging.info(f"Überwache {args.input_dir} auf PDF-Dateien...") # Verwende args.input_dir
    try:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Beende Programm...")
            observer.stop()
            observer.join()
    finally:
        logging.info("Räume Executor auf...")
        event_handler.executor.shutdown(wait=True)

if __name__ == "__main__":
    main()
