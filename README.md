# KiSo_pdf-auto-renamer

Ein schlankes Python-Tool, das gescannte PDF-Dokumente automatisch umbenennt. 
Das Skript extrahiert Text und Bilder aus den Dateien und nutzt ein OpenAI-Modell, 
um aussagekräftige und einheitliche Dateinamen zu erzeugen. So lassen sich große Mengen eingehender Dokumente effizient organisieren.

## Funktionen
- Überwacht ein Eingangsverzeichnis auf neue PDFs
- Extrahiert Bilder und Text der Dokumente
- Generiert Dateinamen über das OpenAI-Modell (Standard: `gpt-4.1-nano`)
- Verschiebt die Dateien ins Ausgabeverzeichnis und nummeriert bei Namenskonflikten durch

## Voraussetzungen
- Python 3
- Abhängigkeiten aus `requirements.txt`

Installation der Pakete:

```bash
pip install -r requirements.txt
```

## Konfiguration
Legen Sie eine `.env`-Datei im Projektordner an und tragen Sie dort Ihre Einstellungen ein:

```bash
OPENAI_API_KEY='dein_api_schluessel'
INPUT_DIR='C:/tmp/PDF_Input'
OUTPUT_DIR='C:/tmp/PDF_Processed'
OPENAI_MODEL='gpt-4.1-nano'
```

`OPENAI_MODEL` ist optional und kann für andere Modelle angepasst werden.

## Verwendung
Starten Sie die Anwendung mit:

```bash
streamlit run streamlit_app.py
```

Die Anwendung überwacht das Eingangsverzeichnis und benennt sowohl bereits vorhandene als auch neue PDFs automatisch um. Eine kleine Weboberfläche zeigt den aktuellen Status an.

### Dauerbetrieb
Für einen permanenten Einsatz lässt sich das Skript z. B. als systemd- oder Windows-Dienst starten oder in den Autostart legen.

## Lizenz
Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
