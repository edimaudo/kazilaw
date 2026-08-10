# onllaw

**onllaw** Legal Support System focused on democratizing access to employment law in Canada by providing contract review and employment rights Q&A.  

Data is from the different Ministry of Labour across Canada

- [Ontario Ministry of Labour](https://www.ontario.ca/laws/statute/00e41)

## Key Features
- **Employment Standards Q&A**: Summarized answers regarding employment rights across the Country.
- **Dual-Mode Contract Review**:
    - **Full Review**: Upload `.pdf`, `.doc`, `.docx` files for compliance check.
    - **Clause Spotlight**: Paste specific sections (e.g., Termination, Non-solicit) for targeted review.

## Technological Implementation
- **AI Orchestration**: Airia
- **Backend**: FastAPI
- **Frontend**: Jinja2

## Project Structure
```
onllaw/
├── main.py         
├── agents.py       
├── utils.py        
├── templates/
│   ├── base.html       
│   ├── index.html      
│   ├── qa.html         
│   ├── audit.html
│   ├── lawyer.html     
│   └── 404.html              
├── requirements.txt    
├── vercel.json         
└── README.md
```
