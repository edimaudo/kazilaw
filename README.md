# KaziLaw

**KaziLaw** is a tool focused on democratizing access to employment law information in Canada by providing employment contract review and the ability to perform employment rights Q&A.  

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
├── main.py                      # FastAPI route definitions, and Jinja2 rendering
├── requirements.txt             # Python project dependencies
└── utils.py                     # Document text extraction helpers
```
