import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.db import init_db, save_session, get_session

client = TestClient(app)

def test_session_end_recording():
    init_db()
    sess_id = "test-call-end-001"
    save_session(sess_id, "hi-IN", "pm_kisan", "COLLECTING", {"landowner": True}, False, 0)
    
    # Call /api/session/end with specific reason
    resp = client.post("/api/session/end", data={"session_id": sess_id, "reason": "USER_ENDED"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["state"] == "ENDED"
    assert data["end_reason"] == "USER_ENDED"

    sess = get_session(sess_id)
    assert sess["state"] == "ENDED"
    assert sess["end_reason"] == "USER_ENDED"

def test_idempotent_turn_on_ended_session():
    init_db()
    sess_id = "test-call-ended-idempotent"
    save_session(sess_id, "hi-IN", "pm_kisan", "ENDED", {}, True, 0, end_reason="USER_ENDED")
    
    # Sending a turn to an ended session must return 200 with polite closure, NEVER 409
    dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    resp = client.post(
        "/api/turn",
        data={"session_id": sess_id, "language": "hi-IN", "turn_id": 99},
        files={"audio_file": ("test.wav", dummy_wav, "audio/wav")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "ENDED"
    assert data["completed"] is True
    assert "समाप्त" in data["agent_text"] or "ended" in data["agent_text"].lower()

