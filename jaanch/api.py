"""REST API and Web Chat backend for Jaanch.

Endpoints:
- POST /api/documents/upload: Upload, validate (15 MB), extract, and analyze offer letters
- GET  /api/documents/{doc_id}: Retrieve detailed document analysis
- GET  /api/documents/history: Retrieve analysis history
- POST /api/chat: Conversational endpoint supporting text offers and follow-up Q&A
- GET  /api/health: Health probe
- GET  /: Web Chat interface
"""

import base64
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .cards import document_analysis_card, generate_document_cybercrime_docket, verdict_card
from .document_analyzer import DocumentAnalysisResult, analyze_offer_document
from .document_parser import (
    DocumentParsingError,
    InsufficientTextError,
    parse_document,
)
from .document_qa import answer_document_question, is_follow_up_question
from .document_security import (
    DEFAULT_MAX_UPLOAD_MB,
    DocumentSecurityError,
    EncryptedDocumentError,
    FileTooLargeError,
    InvalidFileSignatureError,
    MAX_UPLOAD_BYTES,
    store_uploaded_file,
    validate_file_properties,
)
from .document_store import DOCUMENT_STORE
from .pipeline import run_local

LOGGER = logging.getLogger("jaanch.api")

app = FastAPI(
    title="Jaanch Offer Letter Fraud Detection Agent",
    description="AI-powered recruitment scam and offer letter authenticity verification engine.",
    version="1.0.0",
)

# Allow CORS for development and cross-origin embedding
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parent / "web"


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    doc_id: Optional[str] = None


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "agent": "jaanch",
        "service": "offer-letter-fraud-detection",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
):
    """Securely uploads, extracts, and analyzes an offer letter document (PDF, DOCX, Image, TXT)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    try:
        content = await file.read()
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {err}")

    # Validate size & signatures
    try:
        doc_id, stored_path, safe_filename, size, sha256 = store_uploaded_file(
            file_bytes=content,
            original_filename=file.filename,
            declared_mime=file.content_type,
        )
    except FileTooLargeError as err:
        raise HTTPException(status_code=413, detail=str(err))
    except (DocumentSecurityError, ValueError) as err:
        raise HTTPException(status_code=400, detail=str(err))

    conv_id = conversation_id or f"conv_{doc_id[:8]}"

    # Save initial document record
    ext = Path(safe_filename).suffix.lower().replace(".", "")
    DOCUMENT_STORE.save_document(
        doc_id=doc_id,
        filename=safe_filename,
        file_type=ext,
        file_size=size,
        sha256=sha256,
        stored_path=str(stored_path),
        conversation_id=conv_id,
        status="processing",
    )

    # Extract text & metadata
    try:
        doc = parse_document(content, safe_filename, doc_id)
    except EncryptedDocumentError as err:
        raise HTTPException(status_code=422, detail=str(err))
    except InsufficientTextError as err:
        raise HTTPException(status_code=422, detail=str(err))
    except DocumentParsingError as err:
        raise HTTPException(status_code=422, detail=f"Document parsing error: {err}")

    # Execute hybrid fraud detection
    try:
        analysis = await analyze_offer_document(doc)
    except Exception as err:
        LOGGER.exception(f"Document analysis failed: {err}")
        raise HTTPException(status_code=500, detail="Internal analysis error while processing document.")

    # Save completed analysis
    DOCUMENT_STORE.save_analysis(analysis, conversation_id=conv_id)

    # Attach interactive card payload for seamless rendering
    card_payload = document_analysis_card(analysis)

    result_dict = analysis.to_dict()
    result_dict["card_payload"] = card_payload
    result_dict["conversation_id"] = conv_id
    result_dict["doc_id"] = doc_id

    return JSONResponse(status_code=200, content=result_dict)


@app.get("/api/documents/history")
async def get_history(limit: int = 20):
    """Retrieves recent document analysis history."""
    return JSONResponse(status_code=200, content={"history": DOCUMENT_STORE.list_history(limit=limit)})


@app.get("/api/documents/{doc_id}")
async def get_document_analysis(doc_id: str):
    """Retrieves a previously computed document analysis by its document ID."""
    analysis = DOCUMENT_STORE.get_analysis(doc_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis for document ID '{doc_id}' not found.")
    result_dict = analysis.to_dict()
    result_dict["card_payload"] = document_analysis_card(analysis)
    return JSONResponse(status_code=200, content=result_dict)


@app.post("/api/chat")
async def chat_interaction(req: ChatRequest):
    """Conversational endpoint handling pasted offers, follow-up Q&A, and guidance."""
    msg = req.message.strip()
    conv_id = req.conversation_id or "default_user"
    latest_doc = None

    if req.doc_id:
        latest_doc = DOCUMENT_STORE.get_analysis(req.doc_id)
    else:
        latest_doc = DOCUMENT_STORE.get_latest_analysis(conv_id)

    # 1. Check for specific action triggers
    low = msg.lower()
    if "how_to_report" in low or "how do i report" in low:
        from .cards import REPORT_STEPS
        return {"response": REPORT_STEPS, "type": "text"}

    if "get_docket" in low or "cybercrime docket" in low or "copy docket" in low:
        if latest_doc:
            docket = generate_document_cybercrime_docket(latest_doc)
            return {"response": docket, "type": "docket"}
        return {"response": "Please scan an offer letter or paste a message first to generate a complaint docket.", "type": "text"}

    # 2. Check for follow-up questions on an earlier document
    if latest_doc and is_follow_up_question(msg):
        answer = await answer_document_question(msg, latest_doc)
        return {
            "response": answer,
            "type": "follow_up_answer",
            "doc_id": latest_doc.doc_id,
            "classification": latest_doc.classification,
            "risk_score": latest_doc.risk_score,
        }

    # 3. Check if input is a pasted text offer
    result = await run_local(msg)
    payload = verdict_card(result.risk, result.verdict, result.verdict_text, result.signals, result.checked)

    from .llm import explain
    narration = await explain(msg, result.risk, result.verdict_text, result.signals)

    return {
        "response": narration,
        "type": "verdict",
        "risk_score": result.risk * 10,  # Map 1-10 to 0-100
        "verdict": result.verdict,
        "card_payload": payload,
    }


@app.get("/", response_class=HTMLResponse)
async def serve_web_chat():
    """Serves the integrated Jaanch Web Chat Interface with document upload support."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Jaanch Web Chat: index.html not found.</h2>")
