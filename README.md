# KaziLaw

## Overview
**kazilaw** analyzes employment contracts and answer questions on employment and labor law for the Canadian workforce.  

## Key Features
- **Employment Standards Q&A**: Summarized answers regarding employment rights across the Country.
- **Dual-Mode Contract Review**:
    - **Full Review**: Upload `.pdf`, `.doc`, `.docx` files for compliance check.
    - **Clause Spotlight**: Paste specific sections (e.g., Termination, Non-solicit) for targeted review.

## Technological Implementation
- **Web Framework & Server**: FastAPI 
- **Agent & LLM Engine**: Google GenAI SDK (google-genai) with Gemini 3.5 Flash/Pro
- **Cloud Hosting & Compute**: Google Cloud Run (Docker Containerized)
- **Database & Session Logging**: Google Cloud Firestore
- **Document Processing & OCR**: PyMuPDF (fitz) and python-docx
- **Template Engine**: Jinja2

## Project Structure
```
kazilaw/
├── templates/
│   ├── 404.html                 # Custom error page
│   ├── audit.html               # Contract review & clause spotlight
│   ├── base.html                # Global layout, province selector, theme & font controls
│   ├── index.html               # Landing page 
│   ├── lawyers.html             # Provincial legal specialist directory
│   └── qa.html                  # Employment standards Q&A form 
├── Dockerfile                   # Container definition for Google Cloud Run deployment
├── agents.py                    # Agent information
├── db.py                        # Google Cloud Firestore session logging helper
├── main.py                      # Routes and Jinja2 rendering
├── requirements.txt             # Dependencies
└── utils.py                     # Document text extraction helpers
```

# Local Setup and Execution Guide

Step-by-step instructions for running the application locally or within a container environment.

---

## Prerequisites

* **Python 3.11+**
* **Git**
* **Google Gemini API Key** ([Obtain API Key](https://aistudio.google.com/))

---

## Environment Setup

### 1. Clone the Repository

```bash
git clone [kazilaw](https://github.com/edimaudo/kazilaw.git)
cd kazilaw

# Create virtual environment (macOS / Linux)
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell):
# python -m venv venv
# .\venv\Scripts\Activate.ps1

```

### 2. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
**Note**: Verify requirements.txt contains fastapi, uvicorn, google-genai, pymupdf, python-docx, python-dotenv, jinja2, and python-multipart.

### 3. Environment Variable Configuration

```bash
touch .env
```

GEMINI_API_KEY=your_actual_gemini_api_key_here

### 4. Launching the Application

#### Option A: Local ASGI Server (Uvicorn)
```bash
uvicorn main:app --reload --port 8080
```

#### Option B: Docker Container
```bash
# Build the container image
docker build -t maplelaw-app .

# Run the container
docker run -p 8080:8080 -e GEMINI_API_KEY="your_actual_gemini_api_key_here" maplelaw-app
```
Landing Page: http://127.0.0.1:8080/
Contract Review Interface: http://127.0.0.1:8080/audit
Legal Q&A Interface: http://127.0.0.1:8080/qa
