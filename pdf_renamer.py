import os
import re
import shutil
import fitz  # PyMuPDF
import logging
import time
import tempfile
import base64
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from openai import OpenAI
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
    def __init__(self, input_dir: str, output_dir: str):
        """
        Initialisiert den FileHandler mit Eingabe- und Ausgabe-Verzeichnissen.
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
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
                    if best_candidate is not None:
                        image_path_local = store_image(best_candidate["image_bytes"])
                        if image_path_local:
                            vision_result = self.process_image_with_openai(image_path_local, page_text)
                        else:
                            vision_result = "NO_VISION_DATA"
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
            except Exception as e:
                logging.critical(f"Kritischer Fehler: Datei {pdf_path} konnte nicht verschoben werden - {e}")

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
                model="gpt-4o-mini",
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
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
            )
            output_text = response.choices[0].message.content.strip()
            logging.info("gpt-4o-mini Antwort:\n" + output_text)
            output_text = re.sub(r'<[^>]+>', '', output_text).strip()
            file_name = output_text.splitlines()[0].strip()
            file_name = re.sub(r'\s+', '_', file_name)
            file_name = re.sub(r'[^\w\-]', '', file_name)
            return file_name[:70] if file_name else "UNKNOWN_DOC"
        except Exception as e:
            logging.error(f"Fehler bei der gpt-4o-mini Verarbeitung: {e}")
            return "UNKNOWN_DOC"

def main():
    input_dir = "C:/tmp/PDF_Input"       # Bei Bedarf anpassen
    output_dir = "C:/tmp/PDF_Processed"   # Bei Bedarf anpassen
    event_handler = FileHandler(input_dir, output_dir)
    observer = Observer()
    observer.schedule(event_handler, input_dir, recursive=False)
    observer.start()
    logging.info(f"Überwache {input_dir} auf PDF-Dateien...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    event_handler.executor.shutdown(wait=True)

if __name__ == "__main__":
    main()
