# Gemini Movie Analyzer

A Windows desktop tool to analyze MP4 videos using the Google Gemini API.

## build

pyinstaller --onefile --noconsole run_app.py

## Features (Planned)

*   Drag & drop MP4 files.
*   Input custom prompts or use templates.
*   Select Gemini models (`config/models.yaml`).
*   Analyze videos via Gemini API (uploading files and generating content).
*   Save analysis results to text files in the `output/` directory.
*   Manage settings (API key, last used model, etc.) via `config/settings.json` (planned).

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd GeminiMovieToDoc
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    # On Windows cmd:
    .venv\Scripts\activate
    # On Git Bash / Linux / macOS:
    # source .venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure API Key:**
    *   Rename `.env.example` to `.env`.
    *   Open `.env` and replace `"YOUR_GEMINI_API_KEY_HERE"` with your actual Google Gemini API key.
    *   **Important:** Keep your `.env` file secure and do not commit it to version control (`.gitignore` should already exclude it).

5.  **Run the application:**
    ```bash
    python src/ui/main_window.py
    ```

## Project Structure

(See `詳細仕様.md` for a detailed structure diagram)

*   `src/`: Main application code.
    *   `ui/`: PySide6 UI components.
    *   `backend/`: Gemini API interaction and background tasks.
    *   `config/`: Configuration loading and validation.
    *   `utils/`: Common utilities (logging, file operations).
    *   `cli.py`: Command-line interface (future development).
*   `tests/`: Unit, integration, and UI tests.
*   `config/`: User configuration (e.g., `models.yaml`).
*   `output/`: Default directory for analysis results (Git ignored).
*   `sample/`: Sample prompts or templates.
*   `docs/`: Specifications and documentation.
*   `tests_data/`: Data files used for testing.

## Contributing

(Contribution guidelines TBD)

## License

(License information TBD) 