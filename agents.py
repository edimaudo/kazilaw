import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PROVINCIAL_LEGISLATION = {
    "AB": {"name": "Alberta", "act": "Employment Standards Code", "url": "https://kings-printer.alberta.ca/1266.cfm?page=1997_014.cfm&leg_type=Regs&isbncln=9780779858910&display=html"},
    "BC": {"name": "British Columbia", "act": "Employment Standards Act", "url": "https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/00_96113_01"},
    "MB": {"name": "Manitoba", "act": "The Employment Standards Code", "url": "https://web2.gov.mb.ca/laws/statutes/ccsm/_pdf.php?cap=e110"},
    "NB": {"name": "New Brunswick", "act": "Employment Standards Act", "url": "https://laws.gnb.ca/en/pdf/cs/E-7.2.pdf"},
    "NL": {"name": "Newfoundland and Labrador", "act": "Labour Standards Act", "url": "https://www.assembly.nl.ca/Legislation/sr/statutes/l02.htm"},
    "NS": {"name": "Nova Scotia", "act": "Labour Standards Code", "url": "https://www.nslegislature.ca/sites/default/files/legc/statutes/labour%20standards%20code.pdf"},
    "NT": {"name": "Northwest Territories", "act": "Employment Standards Act", "url": "https://www.justice.gov.nt.ca/en/files/legislation/employment-standards/employment-standards.a.pdf"},
    "NU": {"name": "Nunavut", "act": "Labour Standards Act", "url": "https://www.gov.nu.ca/sites/default/files/policies-legislations/2025-11/Labour_Standards_Act__2022_.pdf"},
    "ON": {"name": "Ontario", "act": "Employment Standards Act, 2000", "url": "https://www.ontario.ca/laws/statute/00e41"},
    "PE": {"name": "Prince Edward Island", "act": "Employment Standards Act", "url": "https://www.princeedwardisland.ca/sites/default/files/b281/E-6.3-Employment%20Standards%20Act.pdf"},
    "QC": {"name": "Quebec", "act": "Act respecting labour standards", "url": "https://www.legisquebec.gouv.qc.ca/en/pdf/cs/N-1.1.pdf"},
    "SK": {"name": "Saskatchewan", "act": "The Saskatchewan Employment Act", "url": "https://publications.saskatchewan.ca/api/v1/products/70351/formats/78194/download"},
    "YT": {"name": "Yukon", "act": "Employment Standards Act", "url": "https://laws.yukon.ca/cms/images/LEGISLATION/PRINCIPAL/2002/2002-0072/2002-0072.pdf"}
}

async def audit_contract(contract_text: str, province_code: str = "ON") -> dict:
    code = province_code.upper()
    info = PROVINCIAL_LEGISLATION.get(code, PROVINCIAL_LEGISLATION["ON"])

    system_prompt = f"""
    You are an expert Employment Lawyer in {info['name']}, Canada. Audit the contract against the {info['act']}.
    Official Act URL: {info['url']}

    OUTPUT REQUIREMENT: Return strictly a valid JSON object matching this schema:
    {{
        "province_code": "{code}",
        "province_name": "{info['name']}",
        "statute_name": "{info['act']}",
        "official_statute_url": "{info['url']}",
        "has_violations": boolean,
        "identified_issues": [
            {{
                "clause_quote": "exact text from contract",
                "statute_section": "section ref e.g. s. 5(1)",
                "enforceability_analysis": "why it is unenforceable",
                "suggested_correction": "compliant reworded clause"
            }}
        ],
        "collaborative_hr_email_draft": "email text to HR requesting changes",
        "lawyer_summary_brief": "formal text summary for legal review",
        "disclaimer": "This summary is based on the legislation and is for informational purposes only."
    }}
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=[f"Audit this contract:\n\n{contract_text}"],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            response_mime_type="application/json"
        )
    )

    return json.loads(response.text)

async def ask_qa(question: str, province_code: str = "ON") -> dict:
    code = province_code.upper()
    info = PROVINCIAL_LEGISLATION.get(code, PROVINCIAL_LEGISLATION["ON"])

    system_prompt = f"""
    You are an Employment Legal Advisor in {info['name']}, Canada. Answer questions using the {info['act']}.
    Official Act URL: {info['url']}

    OUTPUT REQUIREMENT: Return strictly a valid JSON object matching this schema:
    {{
        "province_code": "{code}",
        "province_name": "{info['name']}",
        "statute_name": "{info['act']}",
        "official_statute_url": "{info['url']}",
        "answer": "detailed legal response",
        "citations": ["list of section citations e.g. Section 11"],
        "disclaimer": "Legal information only, not legal advice."
    }}
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=[f"User question: {question}"],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            response_mime_type="application/json"
        )
    )

    return json.loads(response.text)
