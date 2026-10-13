from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from utils import extract_text_from_file
import shutil
import os
from agents import audit_contract, ask_qa, translate_legal_result
from db import log_session
from translations import get_translations, TRANSLATIONS


app = FastAPI()
templates = Jinja2Templates(directory="templates")
LANGUAGE_COOKIE = "kazilaw_language"


def get_language(request: Request) -> str:
    """Resolve the selected UI language; English is the default."""
    value = request.cookies.get(LANGUAGE_COOKIE, "en").strip().lower().replace("_", "-")
    return "fr" if value in {"fr", "fr-ca"} else "en"


def template_context(request: Request) -> dict:
    language = get_language(request)
    path = request.url.path
    if path == "/":
        title_key = "landing_meta_title"
    elif path == "/audit":
        title_key = "audit_title"
    elif path == "/qa":
        title_key = "qa_title"
    elif path == "/lawyers":
        title_key = "lawyers_title"
    else:
        title_key = "not_found_title"
    return {
        "request": request,
        "language": language,
        "html_lang": "fr-CA" if language == "fr" else "en-CA",
        "t": get_translations(language),
        "all_translations": TRANSLATIONS,
        "page_title_key": title_key,
    }


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("index.html", template_context(request))


@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return templates.TemplateResponse("404.html", template_context(request), status_code=404)


@app.get("/audit", response_class=HTMLResponse)
async def get_audit(request: Request):
    """Contract audit section."""
    return templates.TemplateResponse("audit.html", template_context(request))


@app.post("/audit")
async def handle_audit(
    request: Request,
    file: UploadFile = File(None),
    clause_text: str = Form(None),
    province: str = Form("ON"),
):
    language = get_language(request)
    strings = get_translations(language)
    context = ""

    if file and file.filename:
        file_bytes = await file.read()
        context = extract_text_from_file(file_bytes, file.filename)

        if context == "ERROR_IMAGE_ONLY_PDF":
            return {
                "answer": f"## {strings['scanned_document_title']}\n\n{strings['scanned_document_message']}"
            }
    elif clause_text:
        context = clause_text

    if not context or context.startswith("ERROR_") or "Unsupported" in context:
        return {"answer": strings["no_readable_text"]}

    analysis = await audit_contract(context, province, language)
    log_session("audits", province, analysis)
    return {"answer": analysis}


@app.post("/translate-result")
async def translate_result(request: Request, text: str = Form(...), language: str = Form(None)):
    """Translate a displayed analysis to the selected UI language without losing it."""
    selected_language = "fr" if (language or get_language(request)).lower().startswith("fr") else "en"
    translated = await translate_legal_result(text, selected_language)
    return {"answer": translated}


@app.get("/qa", response_class=HTMLResponse)
async def get_qa(request: Request):
    """Q&A section."""
    return templates.TemplateResponse("qa.html", template_context(request))


@app.post("/qa")
async def handle_qa(
    request: Request,
    question: str = Form(...),
    province: str = Form("ON"),
):
    """Employment and labour Q&A section."""
    language = get_language(request)
    answer = await ask_qa(question, province, language)
    log_session("qa_inquiries", province, answer)
    return {"answer": answer}


# @app.get("/lawyers", response_class=HTMLResponse)
# async def get_lawyers_page(request: Request):
#     """Serves the list of labour and employment specialists."""
#     specialists = [
#         {"name": "S. Margot Blight", "firm": "S. Margot Blight, Lawyer", "city": "Mississauga"},
#         {"name": "David Bannon", "firm": "Hicks Morley Hamilton Stewart Storie LLP", "city": "Toronto"},
#         {"name": "Matthew Louis Certosimo", "firm": "Borden Ladner Gervais LLP", "city": "Toronto"},
#         {"name": "Patrick Michael Rory Groom", "firm": "McMillan LLP", "city": "Toronto"},
#         {"name": "John Hyde", "firm": "Hyde HR Law", "city": "Toronto"},
#         {"name": "Donald B. Jarvis", "firm": "Filion Wakely Thorup Angeletti LLP", "city": "Toronto"},
#         {"name": "Jeffrey David Arthur Murray", "firm": "Stringer LLP", "city": "Toronto"},
#         {"name": "Garth O'Neill", "firm": "GOLaw Professional Corporation", "city": "Thunder Bay"},
#         {"name": "Donald Shanks", "firm": "Cheadles LLP", "city": "Thunder Bay"},
#         {"name": "Ronald Snyder", "firm": "Xphoria Spirits Inc.", "city": "Ottawa"}
#     ]
#     return templates.TemplateResponse(
#         "lawyers.html", {**template_context(request), "specialists": specialists}
#     )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
