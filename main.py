from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from utils import extract_text_from_file
import shutil
import os
import asyncio
from agents import audit_contract, ask_qa
from db import log_session
from translations import get_translations, TRANSLATIONS
from lawyers_data import JURISDICTIONS, PROFILE_SOURCES, MAX_LAWYERS_PER_JURISDICTION
from lawyers_service import get_live_profiles

app = FastAPI()
templates = Jinja2Templates(directory="templates")
LANGUAGE_COOKIE = "kazilaw_language"
DEFAULT_PROVINCE = "ON"
VALID_PROVINCES = set(JURISDICTIONS)


def get_language(request: Request) -> str:
    """Resolve selected UI language; English is the default."""
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


def lawyer_directory_payload(province: str, language: str, live_data: dict | None = None) -> dict:
    """Build a minimal bilingual directory response from live public firm profiles."""
    code = province.upper() if province else DEFAULT_PROVINCE
    if code not in VALID_PROVINCES:
        code = DEFAULT_PROVINCE
    locale = "fr" if str(language).lower().startswith("fr") else "en"
    jurisdiction = JURISDICTIONS[code]
    live_data = live_data or {"lawyers": []}
    lawyers = []
    for raw_profile in live_data.get("lawyers", []):
        profile = {
            "name": raw_profile.get("name", ""),
            "firm": raw_profile.get("firm", ""),
            "city": raw_profile.get("city", ""),
            "profile_url": raw_profile.get("profile_url", ""),
        }
        if profile["name"] and profile["profile_url"]:
            lawyers.append(profile)

    if locale == "fr":
        messages = {
            "view_profile": "Voir le profil",
            "verify_status": "Répertoire du barreau",
            "empty_body": "Aucun profil n’est actuellement disponible pour cette sélection. Consultez le répertoire officiel pour trouver des avocats en droit de l’emploi et du travail.",
        }
    else:
        messages = {
            "view_profile": "View profile",
            "verify_status": "Law-society directory",
            "empty_body": "No profiles are currently available for this selection. Use the official directory to find employment and labour lawyers.",
        }

    return {
        "province_name": jurisdiction[f"name_{locale}"],
        "regulator_name": jurisdiction[f"regulator_name_{locale}"],
        "regulator_url": jurisdiction["regulator_url"],
        "practice_name": jurisdiction[f"practice_name_{locale}"],
        "practice_url": jurisdiction["practice_url"],
        "lawyers": lawyers,
        "language": locale,
        "messages": messages,
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
    # Kept consistent with the existing application's configured translation agent.
    # If translate_legal_result is implemented in agents.py, import it above.
    from agents import translate_legal_result
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


@app.get("/lawyers", response_class=HTMLResponse)
async def get_lawyers_page(request: Request):
    """Display public lawyer profiles and source links for the selected province."""
    return templates.TemplateResponse("lawyers.html", template_context(request))


@app.get("/api/lawyers", response_class=JSONResponse)
async def get_lawyer_directory(
    province: str = Query(DEFAULT_PROVINCE, min_length=2, max_length=2),
    language: str = Query("en", max_length=5),
):
    """Return current profiles discovered from public firm pages for a province."""
    code = province.upper() if province else DEFAULT_PROVINCE
    if code not in VALID_PROVINCES:
        code = DEFAULT_PROVINCE
    live_data = await asyncio.to_thread(get_live_profiles, code, MAX_LAWYERS_PER_JURISDICTION)
    return JSONResponse(lawyer_directory_payload(code, language, live_data))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
