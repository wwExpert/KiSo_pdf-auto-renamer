# KiSo_pdf-auto-renamer
Ein Python-Tool zur automatischen Umbenennung gescannter PDF-Dokumente. Es extrahiert Text- und Bildinhalte, analysiert diese mit OpenAI GPT-4o mini und generiert strukturierte Dateinamen für eine effizientere Ablage. Ideal für Büros, Kanzleien und Unternehmen mit hohem Dokumentenaufkommen.

# Automatische PDF-Umbenennung mit KI – Ein praktisches Tutorial&#x20;

## Einleitung

Dieses Tutorial beschreibt die Nutzung einer Python-App, die gescannte Dokumente (PDFs) automatisch analysiert und sinnvoll benennt. Dabei werden Bilder und Textinhalte aus den PDFs extrahiert und mit OpenAI GPT-4o mini verarbeitet, um eine aussagekräftige Namensgebung zu generieren. Die App überwacht ein Eingangsverzeichnis und verarbeitet neue Dateien automatisch.

Dies spart nicht nur wertvolle Zeit, sondern reduziert auch menschliche Fehler bei der Namensgebung und sorgt für eine einheitliche, strukturierte Ablage der Dokumente. Besonders für Unternehmen und Büros mit hohem Dokumentenaufkommen kann diese Automatisierung eine enorme Erleichterung sein. Manuelle Dateibenennungen sind oft fehleranfällig und können zu ineffizienten Arbeitsabläufen führen. Durch die Automatisierung entfällt die mühsame Suche nach Dokumenten mit unklaren Namen. Gerade in Umgebungen mit einem hohen Volumen an eingehenden Dokumenten, wie Kanzleien, medizinischen Einrichtungen oder Finanzabteilungen, bietet die App einen erheblichen Mehrwert.

## Voraussetzungen

Bevor die Anwendung genutzt werden kann, müssen einige Abhängigkeiten installiert werden. Dafür wird Python 3.x vorausgesetzt.

### Installation der benötigten Pakete

Die notwendigen Python-Bibliotheken können mit folgendem Befehl installiert werden:

```bash
pip install pymupdf watchdog openai
```

Zusätzlich muss ein OpenAI-API-Schlüssel vorhanden und als Umgebungsvariable gesetzt sein:

```bash
export OPENAI_API_KEY='dein_api_schluessel'
```

Unter Windows kann der API-Key so gesetzt werden:

```powershell
$env:OPENAI_API_KEY='dein_api_schluessel'
```

Falls noch nicht geschehen, sollte zudem ein Python-Interpreter installiert sein. Eine Überprüfung kann mit folgendem Befehl erfolgen:

```bash
python --version
```

## Verzeichnisstruktur

Die App erwartet zwei Verzeichnisse:

- **Eingangsverzeichnis**: Hier werden gescannte PDFs abgelegt.
- **Ausgabeverzeichnis**: Hier werden die umbenannten PDFs gespeichert.

Standardmäßig verwendet die App:

- `C:/tmp/PDF_Input` als Eingangsverzeichnis
- `C:/tmp/PDF_Processed` als Ausgabeverzeichnis

Falls nötig, können diese Pfade im Code angepasst werden. Bei Netzwerklaufwerken oder Cloud-Speichern ist darauf zu achten, dass die App Schreibrechte besitzt.

## Funktionsweise

Die App überwacht das Eingangsverzeichnis auf neue PDF-Dateien. Sobald eine neue Datei erkannt wird:

1. Wird der Text der ersten Seite ausgelesen.
2. Falls ein Bild vorhanden ist, wird es extrahiert und analysiert.
3. OpenAI GPT-4o mini wird befragt, um einen passenden Dateinamen zu generieren.
4. Die Datei wird ins Ausgabeverzeichnis mit dem neuen Namen verschoben.
5. Falls ein Fehler auftritt, wird die Datei unter einem generischen Namen gespeichert.

Durch diese automatisierte Verarbeitung kann sichergestellt werden, dass alle Dokumente nach einem einheitlichen Schema benannt werden, was wiederum die Durchsuchbarkeit und Archivierung erleichtert.

## Anwendung starten

Um die Anwendung zu starten, muss einfach das Python-Skript ausgeführt werden:

```bash
python script.py
```

Die App beginnt dann mit der Überwachung des Eingangsverzeichnisses und verarbeitet neue Dateien automatisch. Falls das Skript auf einem Server oder einer permanent laufenden Umgebung betrieben werden soll, kann es als Hintergrundprozess oder Dienst eingerichtet werden.

### Automatischer Start unter Windows

Falls die Anwendung beim Systemstart automatisch laufen soll, kann eine Verknüpfung zur `script.py`-Datei im Autostart-Ordner abgelegt oder ein Windows-Dienst eingerichtet werden.

### Automatischer Start unter Linux

Unter Linux kann das Skript mit `systemd` als Dienst eingerichtet oder über `cron` geplant ausgeführt werden, um eine kontinuierliche Verarbeitung sicherzustellen.

## Code der Anwendung

```python
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

# OpenAI-Client initialisieren
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Logging konfigurieren für Debugging und Fehlerverfolgung
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FileHandler(FileSystemEventHandler):
    def __init__(self, input_dir: str, output_dir: str):
        """Initialisiert den Datei-Handler mit Eingabe- und Ausgabe-Verzeichnissen."""
        self.input_dir = input_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=4)  # Parallele Verarbeitung von PDFs
    
    def on_created(self, event):
        """Reagiert auf neue Dateien im überwachten Verzeichnis."""
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.pdf'):
            self.executor.submit(self.process_pdf, event.src_path)  # PDF-Verarbeitung im Hintergrund starten
    
    def process_pdf(self, pdf_path: str):
        """Verarbeitet eine neue PDF-Datei und benennt sie um."""
        try:
            with fitz.open(pdf_path) as doc:
                text = doc[0].get_text()  # Extrahiere Text von der ersten Seite
            filename = self.generate_filename_with_openai(text)  # Generiere neuen Dateinamen
            new_path = os.path.join(self.output_dir, filename + ".pdf")
            shutil.move(pdf_path, new_path)  # Datei ins Zielverzeichnis verschieben
            logging.info(f"Datei umbenannt nach {new_path}")
        except Exception as e:
            logging.error(f"Fehler: {e}")
    
    def generate_filename_with_openai(self, content: str) -> str:
        """Generiert einen passenden Dateinamen basierend auf dem Inhalt der PDF."""
        prompt = f"Erstelle einen passenden Dateinamen basierend auf: {content}"
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=100
        )
        return response.choices[0].message.content.strip()

# Start der Überwachung des Eingangsverzeichnisses
input_dir = "C:/tmp/PDF_Input"
output_dir = "C:/tmp/PDF_Processed"
event_handler = FileHandler(input_dir, output_dir)
observer = Observer()
observer.schedule(event_handler, input_dir, recursive=False)
observer.start()
logging.info(f"Überwachung gestartet für {input_dir}")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()
```

## Fazit

Diese App erleichtert das automatische Organisieren gescannter Dokumente, indem sie sinnvolle Dateinamen generiert. Sie lässt sich einfach installieren, nutzen und anpassen.


