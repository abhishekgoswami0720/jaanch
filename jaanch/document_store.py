"""SQLite persistence engine for Jaanch offer letter documents and fraud analyses.

Stores document records, full structured analyses, and links them to
conversations to support follow-up Q&A without repeated scans.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from .document_analyzer import DocumentAnalysisResult

LOGGER = logging.getLogger("jaanch.document_store")

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "jaanch_documents.db"


class DocumentStore:
    """Manages SQLite storage for offer letter documents and analysis records."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    upload_time TEXT NOT NULL,
                    stored_path TEXT,
                    status TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    doc_id TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    classification TEXT NOT NULL,
                    risk_score INTEGER NOT NULL,
                    confidence TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    latest_doc_id TEXT,
                    last_active TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_document(
        self,
        doc_id: str,
        filename: str,
        file_type: str,
        file_size: int,
        sha256: str,
        stored_path: Optional[str] = None,
        conversation_id: str = "",
        status: str = "uploaded",
    ) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents 
                (doc_id, conversation_id, filename, file_type, file_size, sha256, upload_time, stored_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, conversation_id, filename, file_type, file_size, sha256, now_utc, stored_path, status),
            )
            if conversation_id:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_conversations (conversation_id, latest_doc_id, last_active)
                    VALUES (?, ?, ?)
                    """,
                    (conversation_id, doc_id, now_utc),
                )
            conn.commit()

    def save_analysis(self, result: DocumentAnalysisResult, conversation_id: str = "") -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        conv_id = conversation_id or result.doc_id
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analyses 
                (doc_id, conversation_id, classification, risk_score, confidence, document_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.doc_id,
                    conv_id,
                    result.classification,
                    result.risk_score,
                    result.confidence,
                    result.document_type,
                    json.dumps(result.to_dict()),
                    now_utc,
                ),
            )
            # Update document status to analyzed
            conn.execute(
                "UPDATE documents SET status = 'analyzed' WHERE doc_id = ?",
                (result.doc_id,),
            )
            if conv_id:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_conversations (conversation_id, latest_doc_id, last_active)
                    VALUES (?, ?, ?)
                    """,
                    (conv_id, result.doc_id, now_utc),
                )
            conn.commit()

    def get_analysis(self, doc_id: str) -> Optional[DocumentAnalysisResult]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM analyses WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if not row:
                return None
            data = json.loads(row["payload_json"])
            return DocumentAnalysisResult(**data)

    def get_latest_analysis(self, conversation_id: str) -> Optional[DocumentAnalysisResult]:
        with self._get_connection() as conn:
            # Check user_conversations table first
            conv_row = conn.execute(
                "SELECT latest_doc_id FROM user_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if conv_row and conv_row["latest_doc_id"]:
                return self.get_analysis(conv_row["latest_doc_id"])

            # Fallback to querying analyses directly
            row = conn.execute(
                "SELECT payload_json FROM analyses WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            if not row:
                return None
            data = json.loads(row["payload_json"])
            return DocumentAnalysisResult(**data)

    def list_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT a.doc_id, a.conversation_id, a.classification, a.risk_score, 
                       a.confidence, a.document_type, a.created_at, d.filename, d.file_size
                FROM analyses a
                LEFT JOIN documents d ON a.doc_id = d.doc_id
                ORDER BY a.created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_document(self, doc_id: str) -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM analyses WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return True


# Global default store instance
DOCUMENT_STORE = DocumentStore()
