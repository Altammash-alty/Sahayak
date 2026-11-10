import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "sahayak.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        created_at REAL,
        language TEXT,
        scheme_id TEXT,
        state TEXT,
        slots_json TEXT,
        completed INTEGER DEFAULT 0,
        consecutive_rejects INTEGER DEFAULT 0
    )
    """)
    
    # Check if consecutive_rejects column exists (for migrations)
    cursor.execute("PRAGMA table_info(sessions)")
    columns = [col[1] for col in cursor.fetchall()]
    if "consecutive_rejects" not in columns:
        cursor.execute("ALTER TABLE sessions ADD COLUMN consecutive_rejects INTEGER DEFAULT 0")
    if "end_reason" not in columns:
        cursor.execute("ALTER TABLE sessions ADD COLUMN end_reason TEXT DEFAULT NULL")

    # Turns table (telemetry, audio quality gate, and transcripts)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS turns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        turn_num INTEGER,
        speaker TEXT,
        user_transcript TEXT,
        agent_text TEXT,
        stt_latency REAL,
        nlu_latency REAL,
        tts_latency REAL,
        total_latency REAL,
        gate_decision TEXT,
        reject_reason TEXT,
        audio_duration REAL,
        rms_dbfs REAL,
        snr_db REAL,
        created_at REAL,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    )
    """)

    cursor.execute("PRAGMA table_info(turns)")
    turn_cols = [col[1] for col in cursor.fetchall()]
    for col_name, col_type in [
        ("gate_decision", "TEXT"),
        ("reject_reason", "TEXT"),
        ("audio_duration", "REAL"),
        ("rms_dbfs", "REAL"),
        ("snr_db", "REAL")
    ]:
        if col_name not in turn_cols:
            cursor.execute(f"ALTER TABLE turns ADD COLUMN {col_name} {col_type}")

    # Cases table (auditable eligibility records)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        language TEXT,
        scheme_id TEXT,
        verdict TEXT,
        reason TEXT,
        slots_json TEXT,
        documents_json TEXT,
        created_at REAL,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    )
    """)
    
    conn.commit()
    conn.close()

def save_session(session_id: str, language: str, scheme_id: Optional[str], state: str, slots: Dict[str, Any], completed: bool = False, consecutive_rejects: int = 0, end_reason: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sessions (session_id, created_at, language, scheme_id, state, slots_json, completed, consecutive_rejects, end_reason)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(session_id) DO UPDATE SET
        language=excluded.language,
        scheme_id=excluded.scheme_id,
        state=excluded.state,
        slots_json=excluded.slots_json,
        completed=excluded.completed,
        consecutive_rejects=excluded.consecutive_rejects,
        end_reason=COALESCE(excluded.end_reason, sessions.end_reason)
    """, (session_id, time.time(), language, scheme_id, state, json.dumps(slots, ensure_ascii=False), 1 if completed else 0, consecutive_rejects, end_reason))
    conn.commit()
    conn.close()

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT session_id, language, scheme_id, state, slots_json, completed, consecutive_rejects, end_reason FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "session_id": row[0],
        "language": row[1],
        "scheme_id": row[2],
        "state": row[3],
        "slots": json.loads(row[4]) if row[4] else {},
        "completed": bool(row[5]),
        "consecutive_rejects": row[6] if len(row) > 6 and row[6] is not None else 0,
        "end_reason": row[7] if len(row) > 7 else None
    }

def log_turn(session_id: str, turn_num: int, user_transcript: str, agent_text: str,
             stt_latency: float, nlu_latency: float, tts_latency: float, total_latency: float,
             gate_decision: Optional[str] = "PASS", reject_reason: Optional[str] = None,
             audio_duration: float = 0.0, rms_dbfs: float = 0.0, snr_db: float = 0.0):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO turns (session_id, turn_num, speaker, user_transcript, agent_text,
                      stt_latency, nlu_latency, tts_latency, total_latency,
                      gate_decision, reject_reason, audio_duration, rms_dbfs, snr_db, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, turn_num, "user+agent", user_transcript, agent_text,
          stt_latency, nlu_latency, tts_latency, total_latency,
          gate_decision, reject_reason, audio_duration, rms_dbfs, snr_db, time.time()))
    conn.commit()
    conn.close()

def log_case(session_id: str, language: str, scheme_id: str, verdict: str, reason: str, slots: Dict[str, Any], documents: List[str]):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO cases (session_id, language, scheme_id, verdict, reason, slots_json, documents_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, language, scheme_id, verdict, reason, json.dumps(slots, ensure_ascii=False), json.dumps(documents, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()

def get_dashboard_metrics() -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM sessions")
    total_sessions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE completed = 1")
    completed_sessions = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(total_latency), AVG(stt_latency), AVG(tts_latency) FROM turns")
    avg_lats = cursor.fetchone()
    avg_total_lat = round(avg_lats[0] or 0.0, 2)
    avg_stt_lat = round(avg_lats[1] or 0.0, 2)
    avg_tts_lat = round(avg_lats[2] or 0.0, 2)

    # Gate reject statistics
    cursor.execute("SELECT COUNT(*) FROM turns")
    total_turns = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM turns WHERE gate_decision = 'REJECT'")
    rejected_turns = cursor.fetchone()[0]
    reject_rate = round((rejected_turns / total_turns * 100), 1) if total_turns > 0 else 0.0
    
    cursor.execute("""
    SELECT c.id, c.session_id, c.language, c.scheme_id, c.verdict, c.reason, c.created_at, s.completed, s.end_reason
    FROM cases c LEFT JOIN sessions s ON c.session_id = s.session_id
    ORDER BY c.id DESC LIMIT 50
    """)
    cases = []
    for r in cursor.fetchall():
        cases.append({
            "id": r[0],
            "session_id": r[1],
            "language": r[2],
            "scheme_id": r[3],
            "verdict": r[4],
            "reason": r[5],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r[6])),
            "completed": bool(r[7]),
            "end_reason": r[8] if len(r) > 8 else None
        })
        
    conn.close()
    return {
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "completion_rate": round((completed_sessions / total_sessions * 100), 1) if total_sessions > 0 else 0.0,
        "avg_total_latency": avg_total_lat,
        "avg_stt_latency": avg_stt_lat,
        "avg_tts_latency": avg_tts_lat,
        "total_turns": total_turns,
        "rejected_turns": rejected_turns,
        "gate_reject_rate": reject_rate,
        "cases": cases
    }
