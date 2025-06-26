import os
import threading
import streamlit as st
from watchdog.observers import Observer
from pdf_renamer import FileHandler

st.title("PDF Auto Renamer")
input_dir = st.text_input("Eingangsverzeichnis", os.getenv("INPUT_DIR", "C:/tmp/PDF_Input"))
output_dir = st.text_input("Ausgabeverzeichnis", os.getenv("OUTPUT_DIR", "C:/tmp/PDF_Processed"))

if 'processed_files' not in st.session_state:
    st.session_state.processed_files = []

observer = st.session_state.get('observer')
handler = st.session_state.get('handler')


def on_processed(path: str) -> None:
    st.session_state.processed_files.append(os.path.basename(path))


def start_watching() -> None:
    handler = FileHandler(input_dir, output_dir, on_processed=on_processed)
    observer = Observer()
    observer.schedule(handler, input_dir, recursive=False)
    observer.start()
    st.session_state.observer = observer
    st.session_state.handler = handler


def stop_watching() -> None:
    observer = st.session_state.get('observer')
    handler = st.session_state.get('handler')
    if observer and handler:
        observer.stop()
        observer.join()
        handler.executor.shutdown(wait=True)
    st.session_state.observer = None
    st.session_state.handler = None

col1, col2 = st.columns(2)
if col1.button("Überwachung starten") and observer is None:
    threading.Thread(target=start_watching, daemon=True).start()
    st.success("Überwachung gestartet")
if col2.button("Überwachung stoppen") and observer:
    stop_watching()
    st.warning("Überwachung gestoppt")

st.subheader("Verarbeitete Dateien")
for f in st.session_state.processed_files[-20:]:
    st.write(f)
