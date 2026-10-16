from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from utils import extract_text_from_file
import shutil
import os
import asyncio
from agents import audit_contract, ask_qa  # , translate_legal_result
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
    """Build a bilingual response from profiles retrieved live from firm pages.

    Individual lawyer names and profile URLs are intentionally not maintained in Python.
    Regulator websites are linked for user-led current-status verification rather than
    bulk-scraped. If a firm site blocks retrieval, the UI still shows official sources.
    """
    code = province.upper() if province else DEFAULT_PROVINCE
    if code not in VALID_PROVINCES:
        code = DEFAULT_PROVINCE
    locale = "fr" if str(language).lower().startswith("fr") else "en"
    jurisdiction = JURISDICTIONS[code]
    live_data = live_data or {"lawyers": [], "checked_at": None, "sources_checked": []}
    lawyers = []
    for raw_profile in live_data.get("lawyers", []):
        profile = dict(raw_profile)
        source_config = PROFILE_SOURCES.get(profile.get("source_id", ""), {})
        profile["profile_source_name"] = source_config.get(
            "name_fr" if locale == "fr" else "name_en",
            profile.get("profile_source_name", ""),
        )
        lawyers.append(profile)
    count = len(lawyers)

    if locale == "fr":
        if count == 0:
            coverage_note = (
                "Aucun profil n’a pu être récupéré automatiquement à partir des pages publiques des cabinets lors de cette vérification. "
                "Cela peut se produire si une source bloque les requêtes automatisées ou modifie sa structure. Utilisez les liens officiels ci-dessus pour rechercher les avocats."
            )
        elif count < 10:
            coverage_note = (
                f"{count} profil(s) public(s) ont été récupérés en direct. Cette liste n’est pas exhaustive; utilisez le répertoire officiel pour trouver d’autres avocats."
            )
        else:
            coverage_note = "Les profils ci-dessous ont été récupérés en direct à partir de pages publiques de cabinets. La liste n’est pas exhaustive."
        messages = {
            "profiles_heading": "Profils d’avocats publiés par les cabinets",
            "profiles_intro": "Ces profils sont extraits en direct des pages des cabinets. Leur présence sur une page de cabinet ne confirme pas l’inscription actuelle au tableau du barreau.",
            "view_profile": "Voir le profil",
            "verify_status": "Vérifier auprès du barreau",
            "empty_title": "Aucun profil récupéré pour cette sélection",
            "empty_body": "Le répertoire n’a pas pu extraire de profils pertinents des pages de cabinets accessibles. La recherche officielle demeure disponible dans les liens ci-dessus; les répertoires des barreaux ne sont pas récupérés en masse par cette application.",
            "profile_count": "{count} profil(s) de cabinet récupéré(s) en direct",
            "status_note": "Statut professionnel non vérifié automatiquement",
            "source_note": "Les noms et liens de profils proviennent des pages publiques des cabinets répertoriés. kazilaw ne confirme pas le statut auprès du barreau et ne recommande aucun avocat.",
            "last_checked": "Dernière vérification des sources",
            "profile_source": "Source du profil",
            "source_unavailable": "Source inaccessible ou récupération non autorisée",
            "source_no_matches": "Aucun profil pertinent trouvé sur cette page",
            "source_matches": "Profils récupérés",
        }
    else:
        if count == 0:
            coverage_note = (
                "No profiles could be retrieved automatically from public law-firm pages during this check. "
                "This can happen when a source blocks automated requests or changes its page structure. Use the official links above to search for lawyers."
            )
        elif count < 10:
            coverage_note = (
                f"Retrieved {count} public profile(s) directly from firm pages. This list is not exhaustive; use the official directory to find additional lawyers."
            )
        else:
            coverage_note = "The profiles below were retrieved directly from public law-firm pages. This list is not exhaustive."
        messages = {
            "profiles_heading": "Lawyer profiles published by firms",
            "profiles_intro": "These profiles are retrieved live from firm pages. A firm profile does not confirm current enrolment or practising status with the regulator.",
            "view_profile": "View profile",
            "verify_status": "Verify with regulator",
            "empty_title": "No profiles were retrieved for this selection",
            "empty_body": "The directory could not extract relevant profiles from accessible firm pages. Official searches remain available above; this application does not bulk-retrieve law-society directories.",
            "profile_count": "{count} public firm profile(s) retrieved live",
            "status_note": "Professional status not automatically verified",
            "source_note": "Names and profile links come from public pages of the listed firms. kazilaw does not verify regulator status automatically and does not endorse individual lawyers.",
            "last_checked": "Sources last checked",
            "profile_source": "Profile source",
            "source_unavailable": "Source unavailable or automated retrieval not permitted",
            "source_no_matches": "No matching profiles found on this page",
            "source_matches": "Profiles retrieved",
        }

    source_results = []
    for item in live_data.get("sources_checked", []):
        source = PROFILE_SOURCES.get(item.get("source_id"), {})
        source_results.append({
            "name": source.get("name_fr" if locale == "fr" else "name_en", item.get("name", "")),
            "url": item.get("url", source.get("listing_url", "")),
            "result": item.get("result", "unavailable"),
            "result_label": messages[{
                "unavailable": "source_unavailable",
                "no_matching_profiles": "source_no_matches",
                "profiles_found": "source_matches",
            }.get(item.get("result"), "source_unavailable")],
        })

    return {
        "province": code,
        "province_name": jurisdiction[f"name_{locale}"],
        "regulator_name": jurisdiction[f"regulator_name_{locale}"],
        "regulator_url": jurisdiction["regulator_url"],
        "practice_name": jurisdiction[f"practice_name_{locale}"],
        "practice_url": jurisdiction["practice_url"],
        "search_note": jurisdiction[f"search_note_{locale}"],
        "lawyers": lawyers,
        "language": locale,
        "checked_at": live_data.get("checked_at"),
        "sources_checked": source_results,
        "messages": {
            **messages,
            "coverage_note": coverage_note,
        },
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
