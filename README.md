# AI-Powered PDF Renamer Bot with Streamlit UI

## Overview

This application provides a user-friendly web interface, built with Streamlit, to automatically rename PDF documents. It monitors a specified input folder, and when new PDFs arrive, it uses an OpenAI language model (e.g., GPT-4o mini) to analyze their content (text and images) and generate a structured, meaningful filename. The renamed files are then moved to a specified output folder.

This tool is designed to save time, reduce manual errors in file naming, and create a consistently organized document repository.

## Features

*   **Web-Based UI:** Easy-to-use interface built with Streamlit for configuration, starting/stopping the service, and monitoring progress.
*   **Watched Folder:** Automatically processes new PDF files dropped into a designated input directory.
*   **AI-Powered Renaming:** Leverages OpenAI's models to understand PDF content (including images) and suggest intelligent filenames.
*   **Configurable:** Input/output directories and the OpenAI model can be easily configured via the UI.
*   **Configuration Persistence:** Settings are saved locally in a `config.json` file for convenience.
*   **Detailed Logging:** View real-time processing status and detailed logs directly within the application.
*   **Cross-Platform:** Built with Python and Streamlit, usable on Windows, macOS, and Linux.

## Prerequisites

*   Python 3.7 or newer.
*   An OpenAI API key.
*   Access to the internet for OpenAI API calls and package downloads.

## Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-username/your-repository-name.git
    # Replace with the actual repository URL
    ```

2.  **Navigate to Project Directory:**
    ```bash
    cd your-repository-name
    ```

3.  **Create and Activate a Virtual Environment (Recommended):**
    *   On macOS and Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        python -m venv venv
        venv\Scripts\activate
        ```

4.  **Install Dependencies:**
    Make sure your virtual environment is activated, then run:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **OpenAI API Key:**
    *   **Recommended:** Set the `OPENAI_API_KEY` environment variable with your API key. The application will automatically detect and use it.
        *   On macOS/Linux: `export OPENAI_API_KEY='your_actual_api_key'` (add to `.bashrc` or `.zshrc` for persistence).
        *   On Windows (PowerShell): `$env:OPENAI_API_KEY='your_actual_api_key'` (add to Profile for persistence).
    *   **Alternative:** If the environment variable is not set, you can enter the API key directly into the designated field in the application's sidebar UI. This key is stored in `st.session_state` for the current session but is not saved to `config.json`.

2.  **Application Settings (via UI):**
    *   **Input PDF Folder:** The directory where you will place PDFs to be processed.
    *   **Processed PDF Folder:** The directory where renamed PDFs will be saved.
    *   **OpenAI Model:** The specific OpenAI model to be used for analysis (e.g., `gpt-4o-mini`).
    *   These settings can be configured in the application's sidebar and are saved in a `config.json` file in the application's root directory when you click "Save Settings". Default paths are provided (e.g., `C:/tmp/PDF_Input`), which you will likely want to change to valid paths on your system.

## Running the Application

1.  Ensure your virtual environment is activated.
2.  Navigate to the project's root directory (where `app.py` is located).
3.  Run the following command in your terminal:
    ```bash
    streamlit run app.py
    ```
4.  The application will typically open automatically in your default web browser (usually at `http://localhost:8501`). If not, the terminal will provide the URL to open.

## Usage

1.  **Open the Application:** Launch the app using `streamlit run app.py`.
2.  **Configure Settings (Sidebar):**
    *   If you haven't set the `OPENAI_API_KEY` environment variable, enter your API key in the "OpenAI API Key" field.
    *   Set the "Input PDF Folder" to the directory you want the bot to watch for new PDFs. Ensure this directory exists.
    *   Set the "Processed PDF Folder" to the directory where you want the renamed PDFs to be moved. Ensure this directory exists.
    *   Verify or change the "OpenAI Model" if needed.
    *   Click "Save Settings" to persist these directory and model configurations.
3.  **Start Monitoring:**
    *   In the main area of the application, click the "Start Monitoring" button.
    *   The "Bot Status" should change to "RUNNING", and configuration fields in the sidebar will become disabled.
4.  **Process Files:**
    *   Copy or move PDF files that you want to rename into the configured "Input PDF Folder".
    *   The application will detect new files and begin processing them.
5.  **Monitor Progress:**
    *   **Workflow Status Log:** The main area will display a table with the status of each file being processed (e.g., "Queued", "Processing...", "Success", "Error").
    *   **View Detailed Logs:** For more detailed information, expand the "View Detailed Logs" section. This shows logs from the application, including OpenAI API calls, file operations, and any errors with tracebacks.
6.  **Stop Monitoring:**
    *   When you want to stop the bot, click the "Stop Monitoring" button.
    *   The "Bot Status" will change to "STOPPED", and the configuration fields will be re-enabled. The background monitoring service will shut down gracefully.

## Troubleshooting

*   **Directory Not Found:** Ensure the Input and Processed PDF folders exist on your system before starting monitoring. The application currently checks for this when "Start Monitoring" is clicked.
*   **OpenAI API Errors:** Check the "View Detailed Logs" for specific error messages from the OpenAI API. This could be due to an invalid API key, insufficient credits, rate limits, or server-side issues with OpenAI.
*   **Permissions:** The application needs read/write permissions for the input and output directories, and permission to delete files from the input directory after successful processing (as `shutil.move` implies this).
*   **Dependencies:** If you encounter import errors, ensure all packages in `requirements.txt` were installed correctly in your active virtual environment.

---

This README provides a comprehensive guide to setting up and using the AI-Powered PDF Renamer Bot.
