import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Initialize the client
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


async def audit_contract(contract_text: str, province_code: str = "ON", language: str = "en") -> str:
    """Return a Markdown contract review in the selected interface language."""
    code = province_code.upper()
    info = PROVINCIAL_LEGISLATION.get(code, PROVINCIAL_LEGISLATION["ON"])

    if language == "fr":
        system_prompt = f"""
        Vous êtes une personne spécialiste du droit de l'emploi et du travail en {info['name']}, au Canada. Analysez le contrat selon la loi {info['act']}.
        Source officielle de la loi : {info['url']}.
        Si la demande n'est pas valide, expliquez-le dans la section d'analyse juridique et laissez les autres sections vides.

        LANGUE : Rédigez toute la réponse en français canadien naturel, clair et professionnel. Gardez les noms officiels des lois et les citations législatives exacts lorsque c'est nécessaire, mais expliquez leur portée en français. Ne prétendez pas qu'une conclusion constitue un avis juridique définitif.
        FORMAT : Réponse en Markdown seulement, jamais en JSON. Respectez exactement la structure et les titres suivants :

        ## ANALYSE JURIDIQUE
        [Résumé détaillé de l'examen du contrat par rapport à la loi]

        ### STATUT
        [État général de la conformité et de l'applicabilité]

        ## DISPOSITIONS APPLICABLES
        [Liste des dispositions pertinentes de la loi, par exemple l'article 5(1)]

        ## PROCHAINES ÉTAPES RECOMMANDÉES
        [Mesures concrètes recommandées]

        INSTRUCTION CONDITIONNELLE IMPORTANTE : N'incluez les deux titres suivants que si vous relevez une infraction, une violation potentielle ou un problème juridique. Si le contrat semble conforme et qu'aucun problème n'est relevé, omettez entièrement ces titres et leur contenu :

        ## ÉBAUCHE DE COURRIEL AUX RH
        [Courriel demandant les modifications nécessaires]

        ## ÉBAUCHE DE COURRIEL À UN AVOCAT
        [Résumé ou courriel formel destiné à un examen juridique]
        """
    else:
        system_prompt = f"""
        You are an expert Employment Lawyer in {info['name']}, Canada. Audit the contract against the {info['act']}.
        Official Act URL: {info['url']}. If it is not a valid request, say so in the legal answer section and keep the other sections empty.

        OUTPUT REQUIREMENT: Return a purely Markdown formatted report. Do NOT return JSON.
        You MUST strictly use the following layout and headers:

        ## LEGAL ANALYSIS
        [Provide your detailed summary of the contract review against the legislation]

        ### STATUS
        [Provide the overall enforceability and compliance status]

        ## APPLICABLE SECTIONS
        [List the applicable sections from the {info['act']}, e.g., s. 5(1)]

        ## RECOMMENDED NEXT STEPS
        [Provide actionable steps based on your analysis]

        CRITICAL CONDITIONAL INSTRUCTION:
        Only generate the next two headers if there are potential infractions, violations, or legal issues found in the contract. If the contract is fully compliant and has no issues, DO NOT include these headers or their contents at all:

        ## DRAFT HR EMAIL
        [Draft email text to HR requesting the necessary changes]

        ## DRAFT LAWYER EMAIL
        [Draft formal text summary/email for legal review]
        """

    response = await client.aio.models.generate_content(
        model="gemini-3.5-flash",
        contents=[f"Audit this contract:\n\n{contract_text}"],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            thinking_config=types.ThinkingConfig(thinking_level="MEDIUM") # Options: "MINIMAL", "LOW", "MEDIUM", "HIGH" # old --> temperature=0.1 # temperature was depreciated
        )
        # config=types.GenerateContentConfig(
        #     system_instruction=system_prompt,
        #     temperature=0.1
        #     # JSON mime type removed; defaulting to standard text/markdown output
        # )
    )
    return response.text


async def ask_qa(question: str, province_code: str = "ON", language: str = "en") -> str:
    """Return a Markdown legal information response in the selected language."""
    code = province_code.upper()
    info = PROVINCIAL_LEGISLATION.get(code, PROVINCIAL_LEGISLATION["ON"])

    if language == "fr":
        system_prompt = f"""
        Vous êtes une personne conseillère en information juridique sur le droit de l'emploi et du travail en {info['name']}, au Canada. Répondez à la question à partir de la loi {info['act']}.
        Source officielle de la loi : {info['url']}.
        Si la demande n'est pas pertinente ou valide, indiquez-le dans la réponse juridique.

        LANGUE : Rédigez toute la réponse en français canadien naturel, clair et professionnel. Conservez les titres officiels des lois et les citations exactes lorsqu'il le faut, en expliquant leur sens en français. Ne présentez pas la réponse comme un avis juridique personnalisé.
        FORMAT : Markdown seulement, jamais en JSON. Utilisez exactement les titres suivants :

        ## RÉPONSE JURIDIQUE
        [Réponse juridique détaillée]

        ## SOURCES ET CITATIONS
        [Liste des dispositions pertinentes de la loi, par exemple l'article 11]

        ## AVERTISSEMENT
        *Ces renseignements sont fournis à titre informatif et ne constituent pas un avis juridique.*
        """
    else:
        system_prompt = f"""
        You are an Employment Legal Advisor in {info['name']}, Canada. Answer questions using the {info['act']}.
        Official Act URL: {info['url']}. If it is not a valid request, say so in the legal answer section.

        OUTPUT REQUIREMENT: Return a purely Markdown formatted response. Do NOT return JSON.
        Please structure your response using the following headers:

        ## LEGAL ANSWER
        [Detailed legal response]

        ## CITATIONS
        [List of section citations from the {info['act']}, e.g., Section 11]

        ## DISCLAIMER
        *This information is based on the legislation and is for informational purposes only. It does not constitute legal advice.*
        """

    response = await client.aio.models.generate_content(
        model="gemini-3.5-flash",
        contents=[f"User question: {question}"],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            thinking_config=types.ThinkingConfig(thinking_level="MEDIUM") # Options: "MINIMAL", "LOW", "MEDIUM", "HIGH" # old --> temperature=0.1 # temperature was depreciated
        )
    )
    return response.text
