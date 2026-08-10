from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from utils import extract_text_from_file
from agents import ask_esa_lawyer
import shutil
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

@app.get("/audit", response_class=HTMLResponse)
async def get_qa_page(request: Request):
    """Reasoning: This renders the UI when the user clicks the link."""
    return templates.TemplateResponse("audit.html", {"request": request})

@app.post("/audit")
async def handle_audit(file: UploadFile = File(None), clause_text: str = Form(None)):
    context = ""
    
    # Extraction with Scanned PDF Detection
    if file and file.filename:
        file_bytes = await file.read()
        context = extract_text_from_file(file_bytes, file.filename)
        
        # Check for the specific error string from our updated utils.py
        if context == "ERROR_IMAGE_ONLY_PDF":
            return {
                "answer": (
                    "SCANNED DOCUMENT DETECTED\n\n"
                    "This PDF appears to be a scan or an image. Our system cannot read 'flat' text from images. "
                    "To review this, please upload a digital PDF, docx, or doc file (where you can highlight text) or "
                    "manually paste the clauses into the 'Specific Clause' tab."
                )
            }
    elif clause_text:
        context = clause_text

    if not context or "Unsupported" in context:
        return {"answer": "Error: No readable text was provided for analysis."}

   # Specialized Review prompt --> this needed to be moved
    audit_prompt = (
        "Act as an Employment Law Expert in Canada. Audit the following text for ESA compliance.\n"
        "1. Identify any illegal or unenforceable clauses.\n"
        "2. Suggest specific corrections.\n"
        "3.  If there is an illegal or unenforceable clause(s) PROVDE A DRAFT collaborative EMAIL to HR\n[Provide a collaborative email draft here]\n\n"
        "4. If there is an illegal or unenforceable clause(s) provide a DRAFT SUMMARY FOR LAWYER\n[Provide a formal legal summary here]\n\n"
        f"CONTRACT CONTENT:\n{context}"
    )
    
    # Call the Agent
    analysis = await ask_esa_lawyer(audit_prompt)
    return {"answer": analysis}


@app.get("/qa", response_class=HTMLResponse)
async def get_qa_page(request: Request):
    """Reasoning: This renders the UI when the user clicks the link."""
    return templates.TemplateResponse("qa.html", {"request": request})

@app.post("/qa")
async def handle_qa_logic(question: str = Form(...)):
    """Reasoning: This processes the actual AI question after the user hits submit."""
    answer = await ask_esa_lawyer(question)
    return {"answer": answer}
    return response

# @app.get("/lawyers", response_class=HTMLResponse)
# async def get_lawyers_page(request: Request):
#     """
#     Serves the list of LSO Certified Specialists. 
#     """
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
    
#     return templates.TemplateResponse("lawyers.html", {
#         "request": request, 
#         "specialists": specialists
#     })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
