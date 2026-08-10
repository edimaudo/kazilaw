import datetime
import os
from google.cloud import firestore

# Automatically picks up GCP credentials or running environment on Cloud Run
db = firestore.Client(project=os.getenv("GCP_PROJECT_ID"))

def log_session(session_type: str, province: str, data: dict):
    """Saves session metadata and agent results directly to Firestore."""
    try:
        doc_ref = db.collection(session_type).document()
        doc_ref.set({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "province": province,
            "result": data
        })
    except Exception as e:
        print(f"Firestore log error (non-blocking): {e}")
