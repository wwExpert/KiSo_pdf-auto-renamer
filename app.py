import streamlit as st
import os
import json
import time
import logging
import re
import shutil
import fitz  # PyMuPDF
import tempfile
import base64
import threading # For background monitoring
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from openai import OpenAI, APIError
from concurrent.futures import ThreadPoolExecutor

# --- Initialize Session State Variables (Earliest Point) ---
# This block ensures all session state keys are initialized before any other code
# might try to access them, especially logging or UI rendering.

if "log_messages" not in st.session_state:
    st.session_state.log_messages = []
if "processed_files" not in st.session_state:
    st.session_state.processed_files = []
if "monitoring_active" not in st.session_state:
    st.session_state.monitoring_active = False
if "observer" not in st.session_state:
    st.session_state.observer = None
if "file_event_handler" not in st.session_state:
    st.session_state.file_event_handler = None
if "monitor_thread" not in st.session_state:
    st.session_state.monitor_thread = None
if "openai_api_key" not in st.session_state:
    st.session_state.openai_api_key = os.getenv("OPENAI_API_KEY", "")
if "input_dir" not in st.session_state:
    st.session_state.input_dir = "C:/tmp/PDF_Input" # Default, will be updated by load_config
if "output_dir" not in st.session_state:
    st.session_state.output_dir = "C:/tmp/PDF_Processed" # Default
if "openai_model" not in st.session_state:
    st.session_state.openai_model = "gpt-4o-mini" # Default
if "config_loaded" not in st.session_state: # To ensure load_config runs once to update above defaults
    st.session_state.config_loaded = False


# --- Custom Streamlit Logging Handler ---
class StreamlitLogHandler(logging.Handler):
    def __init__(self, max_messages=100):
        super().__init__()
        self.max_messages = max_messages

    def emit(self, record):
        log_entry = self.format(record)
        # Ensure log_messages list exists, though it should by now
        if "log_messages" not in st.session_state:
            st.session_state.log_messages = []
        st.session_state.log_messages.append(log_entry)
        st.session_state.log_messages = st.session_state.log_messages[-self.max_messages:]

# --- Logging Configuration ---
root_logger = logging.getLogger()
if not any(isinstance(h, StreamlitLogHandler) for h in root_logger.handlers):
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(console_handler)
    streamlit_handler = StreamlitLogHandler()
    streamlit_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(streamlit_handler)
    logging.info("StreamlitLogHandler added and logging configured.")


# --- Configuration Handling ---
CONFIG_FILE = "config.json"

def load_config():
    # Defaults are already in session_state, here we primarily load from file if it exists
    # And ensure the loaded config updates session_state
    defaults_from_file_load = { # These are the keys expected from the file
        "input_dir": st.session_state.input_dir, # Use current session_state as initial default
        "output_dir": st.session_state.output_dir,
        "model": st.session_state.openai_model
    }
    loaded_config = defaults_from_file_load.copy()

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config_from_file = json.load(f)
            # Update loaded_config with values from file, ensuring all keys are present
            for key in defaults_from_file_load:
                if key in config_from_file:
                    loaded_config[key] = config_from_file[key]
            logging.info(f"Configuration loaded from {CONFIG_FILE}")
        except (IOError, json.JSONDecodeError) as e:
            st.warning(f"Error loading config file '{CONFIG_FILE}': {e}. Using current session defaults or initial defaults.")
            logging.error(f"Config file error: {e}")
    else:
        logging.info(f"'{CONFIG_FILE}' not found. Using current session defaults or initial defaults.")

    # Update session_state with the determined config (either from file or initial defaults)
    st.session_state.input_dir = loaded_config["input_dir"]
    st.session_state.output_dir = loaded_config["output_dir"]
    st.session_state.openai_model = loaded_config["model"]
    return loaded_config # Return a dict, though session_state is the primary store now


def save_config(config_dict):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_dict, f, indent=4)
        logging.info("Configuration saved successfully to config.json.")
        return True
    except IOError as e:
        st.error(f"Error saving config file: {e}")
        logging.error(f"Error saving config: {e}")
        return False

# --- Helper Functions & FileHandler Class (content remains the same as previous version) ---
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def store_image(image_bytes: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(image_bytes)
            temp_file_path = tmp.name
        logging.info(f"Image temporarily stored at: {temp_file_path}")
        return temp_file_path
    except Exception as e:
        logging.error(f"Error storing image temporarily: {e}")
        return ""

class FileHandler(FileSystemEventHandler):
    def __init__(self, input_dir: str, output_dir: str, model_name: str, openai_api_key: str, status_update_callback: callable):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.model_name = model_name
        self.status_update_callback = status_update_callback
        if openai_api_key:
            self.openai_client = OpenAI(api_key=openai_api_key)
            logging.info("FileHandler: OpenAI client initialized.")
        else:
            logging.error("FileHandler: OpenAI API key not provided. Client not initialized.")
            self.openai_client = None
        os.makedirs(output_dir, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=4)
        logging.info("FileHandler initialized.")

    def on_created(self, event):
        if event.is_directory:
            logging.debug(f"Directory event ignored: {event.src_path}")
            return
        if event.src_path.lower().endswith('.pdf'):
            original_filename = os.path.basename(event.src_path)
            logging.info(f"New PDF detected: {event.src_path} by FileHandler.")
            self.status_update_callback(original_filename, "", "Queued for processing")
            self.executor.submit(self.process_pdf, event.src_path)
        else:
            logging.debug(f"Non-PDF file event ignored: {event.src_path}")

    def process_pdf(self, pdf_path: str):
        original_filename = os.path.basename(pdf_path)
        logging.info(f"Processing PDF: {original_filename}")
        self.status_update_callback(original_filename, "", "Processing...")

        if not self.openai_client:
            self.status_update_callback(original_filename, "", "Error: OpenAI client not initialized")
            logging.error("OpenAI client not initialized in process_pdf.")
            return

        try:
            logging.debug(f"Attempting to open PDF: {pdf_path}")
            with fitz.open(pdf_path) as doc:
                first_page = doc.load_page(0)
                page_text = first_page.get_text()
                logging.debug(f"Extracted text from PDF (first page, length {len(page_text)}).")
                images = first_page.get_images(full=True)
                best_candidate = None
                if images:
                    logging.debug(f"Found {len(images)} images in PDF.")
                    for img_info in images:
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        area = width * height
                        if best_candidate is None or area > best_candidate["area"]:
                            best_candidate = {"image_bytes": base_image["image"], "area": area, "xref": xref}
                    if best_candidate:
                         logging.debug(f"Best image candidate found with area {best_candidate['area']} (xref: {best_candidate['xref']}).")
                else:
                    logging.warning(f"No images found in PDF: {original_filename}")

                image_path_local = None
                vision_result = "NO_VISION_DATA"

                if best_candidate:
                    try:
                        image_path_local = store_image(best_candidate["image_bytes"])
                        if image_path_local:
                            logging.info(f"Best image stored locally at {image_path_local}, proceeding with vision.")
                            vision_result = self.process_image_with_openai(image_path_local, page_text)
                        else:
                            self.status_update_callback(original_filename, "", "Error: Failed to store image")
                            vision_result = "IMAGE_STORE_FAILED"
                            logging.error("Failed to store image for vision processing.")
                    finally:
                        if image_path_local and os.path.exists(image_path_local):
                            try:
                                os.remove(image_path_local)
                                logging.info(f"Temporary image file {image_path_local} deleted.")
                            except Exception as e_remove:
                                logging.error(f"Error deleting temporary image file {image_path_local}: {e_remove}")
                else:
                    self.status_update_callback(original_filename, "", "No usable image found")
                    vision_result = "NO_IMAGE_FOUND"

            if vision_result in ["NO_VISION_DATA", "IMAGE_STORE_FAILED", "NO_IMAGE_FOUND"]:
                 self.status_update_callback(original_filename, "", f"Processing issue: {vision_result}")
            elif vision_result in ["Vision Analysis Failed", "Vision Analysis Failed due to API Error"]:
                pass

            content_for_naming = vision_result if vision_result not in ["NO_VISION_DATA", "IMAGE_STORE_FAILED", "NO_IMAGE_FOUND", "Vision Analysis Failed", "Vision Analysis Failed due to API Error"] else page_text
            if not content_for_naming:
                content_for_naming = "No content available"
                logging.warning(f"No content (vision or text) available for naming PDF {original_filename}")

            filename = self.generate_filename_with_openai(content_for_naming)

            if filename in ["UNKNOWN_DOC", "UNKNOWN_DOC_API_ERROR"]:
                self.status_update_callback(original_filename, filename, f"Naming failed ({filename})")
                logging.warning(f"Failed to generate a proper name for {original_filename}, result: {filename}")

            base_name = filename
            new_name = f"{base_name}.pdf"
            new_path_base = os.path.normpath(os.path.join(self.output_dir, new_name))

            counter = 1
            new_path = new_path_base
            while os.path.exists(new_path):
                new_name = f"{base_name}_{counter}.pdf"
                new_path = os.path.normpath(os.path.join(self.output_dir, new_name))
                counter += 1

            if len(new_name) > 240:
                base_name_truncated = base_name[:240 - 4]
                new_name = base_name_truncated + ".pdf"
                new_path = os.path.normpath(os.path.join(self.output_dir, new_name))
                counter = 1
                while os.path.exists(new_path):
                    new_name = f"{base_name_truncated}_{counter}.pdf"
                    new_path = os.path.normpath(os.path.join(self.output_dir, new_name))
                    counter +=1

            shutil.move(pdf_path, new_path)
            logging.info(f"File moved from {pdf_path} to {new_path}")
            self.status_update_callback(original_filename, os.path.basename(new_path), "Success")

        except Exception as e:
            logging.error(f"Critical error processing PDF {pdf_path}: {e}", exc_info=True)
            self.status_update_callback(original_filename, "", f"Error: {str(e)}")

    def process_image_with_openai(self, image_path: str, page_text: str) -> str:
        text_prompt = "Extrahiere den Text aus dem Bild und analysiere den Inhalt. Ziel ist es, relevante Informationen zu identifizieren, um einen Dateinamen zu generieren. Referenznummern, Betreff, Absender, Empfänger, Datumsangaben sind besonders wichtig. Beispiel: YYYY-MM-DD_FIRMA_DOKUMENTENTYP (z.B. Rechnung)_Betreff_ID"
        base_image_filename = os.path.basename(image_path)
        try:
            base64_image = encode_image(image_path)
            data_uri = f"data:image/jpeg;base64,{base64_image}"
            logging.info(f"Processing image {image_path} with OpenAI model {self.model_name}")
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": [{"type": "text", "text": text_prompt},{"type": "image_url", "image_url": {"url": data_uri}},]}],
                max_tokens=300
            )
            vision_output = response.choices[0].message.content
            logging.info(f"OpenAI Vision output received for {image_path} (Length: {len(vision_output)} chars)")
            return vision_output
        except APIError as e:
            error_details = f"OpenAI API Error (Vision) for {image_path}: Status {e.status_code}, Response: {e.response.text if e.response else 'N/A'}"
            logging.error(error_details)
            self.status_update_callback(base_image_filename, "", "Error: OpenAI API (Vision)")
            return "Vision Analysis Failed due to API Error"
        except Exception as e:
            logging.error(f"Error in OpenAI Vision processing for {image_path}: {e}", exc_info=True)
            self.status_update_callback(base_image_filename, "", "Error: Vision processing")
            return "Vision Analysis Failed"

    def generate_filename_with_openai(self, content: str) -> str:
        prompt = (
            f"Analysiere den folgenden Inhalt:\n{content}\n\n"
            f"Erzeuge einen prägnanten, aussagekräftigen Dateinamen im Format: YYYY-MM-DD_FIRMA_DOKUMENTENTYP_ID\n"
            f"Beispiel: 2024-11-23_AOK_Rückzahlung_Kndnr1234\n"
            f"Verwende ausschließlich alphanumerische Zeichen und Unterstriche. Gib nur den Dateinamen (ohne Dateiendung) zurück."
        )
        try:
            logging.info(f"Generating filename with OpenAI model {self.model_name} based on content (length: {len(content)}).")
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100
            )
            output_text = response.choices[0].message.content.strip()
            logging.info(f"OpenAI Filename generation response: {output_text}")
            output_text = re.sub(r'<[^>]+>', '', output_text).strip()
            try: file_name = output_text.splitlines()[0].strip()
            except IndexError: file_name = ""
            if not file_name:
                logging.warning("OpenAI response for filename was empty after initial processing.")
                return "UNKNOWN_DOC"
            file_name = re.sub(r'\s+', '_', file_name)
            file_name = re.sub(r'[^\w\-]', '', file_name)
            file_name = re.sub(r'_+', '_', file_name)
            file_name = file_name.strip('_')
            if not file_name:
                logging.warning("Filename became empty after sanitization.")
                return "UNKNOWN_DOC"
            return file_name[:70] if file_name else "UNKNOWN_DOC"
        except APIError as e:
            error_details = f"OpenAI API Error (Filename generation): Status {e.status_code}, Response: {e.response.text if e.response else 'N/A'}"
            logging.error(error_details)
            return "UNKNOWN_DOC_API_ERROR"
        except Exception as e:
            logging.error(f"Error in OpenAI filename generation: {e}", exc_info=True)
            return "UNKNOWN_DOC"

# --- Streamlit UI & Application Logic ---
st.set_page_config(layout="wide")
st.title("📄 PDF Renamer Bot")

# Load configuration from file into session_state ONCE if not already marked as loaded.
# This ensures that defaults set at the top are updated from config.json if it exists.
if not st.session_state.config_loaded:
    load_config() # This function now updates session_state directly
    st.session_state.config_loaded = True
    logging.info("Initial configuration processed from file (if exists) or defaults.")


def update_status_display(original_name, new_name, status_message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    found = False
    for item in st.session_state.processed_files:
        if item["Original Filename"] == original_name:
            item["New Filename"] = new_name if new_name else item.get("New Filename", "")
            item["Status"] = status_message
            item["Timestamp"] = timestamp
            found = True
            break
    if not found:
        st.session_state.processed_files.append({
            "Original Filename": original_name, "New Filename": new_name,
            "Status": status_message, "Timestamp": timestamp
        })

def start_monitoring_service(input_dir, output_dir, model_name, openai_api_key_val):
    logging.info(f"Attempting to start monitoring service: Input='{input_dir}', Output='{output_dir}', Model='{model_name}'")
    try:
        st.session_state.file_event_handler = FileHandler(
            input_dir, output_dir, model_name, openai_api_key_val, update_status_display
        )
        st.session_state.observer = Observer()
        st.session_state.observer.schedule(st.session_state.file_event_handler, input_dir, recursive=False)
        st.session_state.observer.start()
        logging.info(f"Observer started, watching directory: {input_dir}")
        logging.warning("This is a test warning log from monitoring service start.") # Test log
        while st.session_state.get("monitoring_active", False):
            time.sleep(1)
    except Exception as e:
        logging.error(f"FATAL: Exception in monitoring service startup or loop: {e}", exc_info=True)
        st.session_state.monitoring_active = False
    finally:
        logging.info("Monitoring service shutdown sequence initiated.")
        if st.session_state.observer and st.session_state.observer.is_alive():
            st.session_state.observer.stop()
            st.session_state.observer.join()
            logging.info("Observer stopped and joined.")
        if st.session_state.file_event_handler and st.session_state.file_event_handler.executor:
            st.session_state.file_event_handler.executor.shutdown(wait=True)
            logging.info("FileHandler ThreadPoolExecutor shut down.")
        st.session_state.observer = None
        st.session_state.file_event_handler = None
        logging.info("Monitoring service fully shut down.")

# --- Sidebar UI ---
with st.sidebar:
    st.header("🔑 API Configuration")
    st.session_state.openai_api_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=st.session_state.openai_api_key,
        help="Loaded from OPENAI_API_KEY env var if set, otherwise enter here.",
        disabled=st.session_state.monitoring_active or bool(os.getenv("OPENAI_API_KEY"))
    )
    if os.getenv("OPENAI_API_KEY"):
        st.caption("API Key loaded from environment variable.")
    elif not st.session_state.openai_api_key:
         st.warning("OpenAI API Key is required.")

    st.header("⚙️ Bot Settings")
    is_monitoring = st.session_state.monitoring_active
    # Use st.session_state values directly for text_input values
    st.session_state.input_dir = st.text_input("Input PDF Folder", value=st.session_state.input_dir, disabled=is_monitoring)
    st.session_state.output_dir = st.text_input("Processed PDF Folder", value=st.session_state.output_dir, disabled=is_monitoring)
    st.session_state.openai_model = st.text_input("OpenAI Model", value=st.session_state.openai_model, disabled=is_monitoring)

    if st.button("Save Settings", disabled=is_monitoring):
        # Config to save should come from current session_state values
        current_config_to_save = {
            "input_dir": st.session_state.input_dir,
            "output_dir": st.session_state.output_dir,
            "model": st.session_state.openai_model
        }
        if save_config(current_config_to_save): st.success("Settings saved!")
        else: st.error("Failed to save settings.")

# --- Main Area UI ---
col1, col2 = st.columns([0.7, 0.3])

with col1:
    st.subheader("🚀 Control Panel")
    if st.session_state.monitoring_active:
        if st.button("Stop Monitoring"):
            logging.info("Stop Monitoring button clicked.")
            st.session_state.monitoring_active = False
            if st.session_state.monitor_thread and st.session_state.monitor_thread.is_alive():
                st.session_state.monitor_thread.join(timeout=10)
                if st.session_state.monitor_thread.is_alive():
                    logging.warning("Monitoring thread did not terminate in time.")
            st.session_state.monitor_thread = None
            st.info("Monitoring service stopping... UI will update shortly.")
            time.sleep(1)
            st.rerun()
    else:
        if st.button("Start Monitoring"):
            logging.info("Start Monitoring button clicked.")
            if not st.session_state.openai_api_key:
                st.error("OpenAI API Key is not set. Please configure it.")
            elif not os.path.isdir(st.session_state.input_dir):
                 st.error(f"Input directory '{st.session_state.input_dir}' not found.")
            elif not os.path.isdir(st.session_state.output_dir):
                 st.error(f"Output directory '{st.session_state.output_dir}' not found.")
            else:
                st.session_state.monitoring_active = True
                st.session_state.processed_files = []
                logging.info("Starting monitoring thread...")
                logging.error("This is a test error log from Start Monitoring.") # Test log
                st.session_state.monitor_thread = threading.Thread(
                    target=start_monitoring_service,
                    args=(st.session_state.input_dir, st.session_state.output_dir,
                          st.session_state.openai_model, st.session_state.openai_api_key),
                    daemon=True
                )
                st.session_state.monitor_thread.start()
                st.success(f"Monitoring started for '{st.session_state.input_dir}'.")
                st.rerun()
with col2:
    st.subheader("ℹ️ Bot Status")
    if st.session_state.monitoring_active:
        st.success(f"RUNNING\nWatching: {st.session_state.input_dir}")
    else:
        st.warning("STOPPED")

st.header("📊 Workflow Status Log")
if st.session_state.processed_files:
    st.dataframe(st.session_state.processed_files[::-1], column_order=("Timestamp", "Original Filename", "New Filename", "Status"), use_container_width=True)
else:
    st.info("No files processed yet or monitoring not active.")

with st.expander("📄 View Detailed Logs", expanded=False):
    if st.session_state.log_messages:
        log_display = "\n".join(st.session_state.log_messages)
        st.text_area("Logs", value=log_display, height=300, disabled=True, key="log_display_area")
    else:
        st.info("No log messages yet.")
    if st.button("Clear Logs"):
        st.session_state.log_messages = []
        logging.info("UI logs cleared by user.")
        st.rerun()
