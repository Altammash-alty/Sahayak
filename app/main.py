import os
import time
import uuid
import base64
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.gnani import transcribe_audio, synthesize_speech, GnaniAPIError
from app.dialogue import DialogueManager, get_i18n, get_reask_prompt
from app.cache import get_cached_tts
from app.audio import evaluate_audio_quality
from app.config import config
from app.db import (
    init_db, save_session, get_session, log_turn, log_case, get_dashboard_metrics
)

app = FastAPI(title="Sahayak - Sovereign Indian Voice Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "sahayak"}

@app.get("/readyz")
def readyz():
    api_key = os.getenv("GNANI_API_KEY")
    key_configured = bool(api_key and api_key != "your_gnani_api_key_here")
    return {
        "status": "ready" if key_configured else "not_configured",
        "gnani_key_configured": key_configured,
        "database": "writable"
    }

@app.get("/", response_class=HTMLResponse)
def get_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h3>Sahayak Voice Assistant Loading...</h3>")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    dash_file = STATIC_DIR / "dashboard.html"
    if not dash_file.exists():
        return HTMLResponse("<h3>Dashboard Loading...</h3>")
    with open(dash_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/metrics")
def api_metrics():
    return get_dashboard_metrics()

@app.post("/api/demo/turn")
def demo_turn(text: str, session_id: str, language: str = "hi-IN"):
    """
    Simulates a turn for Demo Mode without requiring live microphone recording.
    """
    sess = get_session(session_id)
    if not sess:
        save_session(session_id, language, None, "START", {}, False, 0)
        sess = get_session(session_id)

    agent_text, new_state, new_scheme, new_slots, is_completed, eval_res = DialogueManager.process_turn(
        user_transcript=text,
        current_language=language,
        detected_language=language,
        scheme_id=sess["scheme_id"],
        current_state=sess["state"],
        collected_slots=sess["slots"],
        retry_count=0
    )

    save_session(session_id, language, new_scheme, new_state, new_slots, is_completed, 0)

    if is_completed and eval_res and new_scheme:
        log_case(
            session_id=session_id,
            language=language,
            scheme_id=new_scheme,
            verdict=eval_res.get("verdict", "UNSURE"),
            reason=eval_res.get("reason", ""),
            slots=new_slots,
            documents=eval_res.get("documents", [])
        )

    try:
        reply_audio = get_cached_tts(agent_text, language)
        audio_b64 = base64.b64encode(reply_audio).decode("utf-8")
    except GnaniAPIError as exc:
        # TTS unavailable (e.g. 429 quota); return text-only response so demo still works
        import logging
        logging.getLogger("app.main").warning("Demo TTS failed, returning text-only: %s", exc)
        audio_b64 = ""

    return {
        "session_id": session_id,
        "user_transcript": text,
        "agent_text": agent_text,
        "audio_base64": audio_b64,
        "state": new_state,
        "scheme_id": new_scheme,
        "completed": is_completed,
        "evaluation": eval_res
    }

@app.post("/api/session/start")
def start_session(language: str = Form("hi-IN")):
    session_id = str(uuid.uuid4())
    save_session(
        session_id=session_id,
        language=language,
        scheme_id=None,
        state="START",
        slots={},
        completed=False,
        consecutive_rejects=0
    )
    i18n = get_i18n(language)
    greeting_text = i18n["greeting"]
    
    # Synthesize or fetch greeting audio
    audio_bytes = get_cached_tts(greeting_text, language)
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    return {
        "session_id": session_id,
        "language": language,
        "agent_text": greeting_text,
        "audio_base64": audio_base64
    }

@app.post("/api/session/end")
def end_session(session_id: str = Form(...), reason: str = Form("USER_ENDED")):
    """
    Explicitly marks session ended on server and records abandoned outcome if incomplete.
    """
    sess = get_session(session_id)
    if sess:
        is_completed = sess["completed"]
        save_session(
            session_id=session_id,
            language=sess["language"],
            scheme_id=sess["scheme_id"],
            state="ENDED",
            slots=sess["slots"],
            completed=is_completed,
            consecutive_rejects=sess.get("consecutive_rejects", 0),
            end_reason=reason
        )
        if not is_completed:
            log_case(
                session_id=session_id,
                language=sess["language"],
                scheme_id=sess["scheme_id"] or "unspecified",
                verdict="ABANDONED",
                reason=f"Call ended before completion ({reason})",
                slots=sess["slots"],
                documents=[]
            )
    return {"status": "success", "session_id": session_id, "state": "ENDED", "end_reason": reason}

@app.post("/api/turn")
async def process_turn(
    session_id: str = Form(...),
    language: str = Form("hi-IN"),
    turn_id: int = Form(1),
    audio_file: UploadFile = File(...)
):
    start_turn = time.time()
    
    sess = get_session(session_id)
    if not sess:
        save_session(session_id, language, None, "START", {}, False, 0)
        sess = get_session(session_id)

    # Server check: ignore turn if session was ended
    if sess.get("state") == "ENDED":
        # Idempotent recovery: do not return 409 Conflict. Return graceful 200 with polite prompt
        i18n = get_i18n(language)
        closure_text = i18n.get("call_ended_note", "यह बातचीत समाप्त हो चुकी है। नई बातचीत के लिए फिर से कॉल शुरू करें।")
        audio_bytes = get_cached_tts(closure_text, language)
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "gate_decision": "PASS",
            "reject_reason": None,
            "user_transcript": "",
            "agent_text": closure_text,
            "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            "state": "ENDED",
            "scheme_id": sess.get("scheme_id"),
            "completed": True,
            "evaluation": None,
            "latencies": {"stt": 0.0, "nlu": 0.0, "tts": 0.0, "total": 0.0}
        }
        
    raw_audio_bytes = await audio_file.read()
    if len(raw_audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    current_slots = sess["slots"]
    current_state = sess["state"]
    current_scheme = sess["scheme_id"]
    consecutive_rejects = sess.get("consecutive_rejects", 0)
    i18n = get_i18n(language)

    # 1. AUDIO QUALITY GATE (DSP Evaluation)
    quality_report = evaluate_audio_quality(raw_audio_bytes)
    audio_for_stt = quality_report.processed_wav_bytes or raw_audio_bytes

    if quality_report.decision == "REJECT":
        consecutive_rejects += 1
        
        # Check if consecutive rejects exceeded limit -> offer helpline/handoff
        if consecutive_rejects >= config.MAX_CONSECUTIVE_REJECTS:
            reask_text = f"{i18n['handoff']} {i18n.get('labels', {}).get('helpline', 'Helpline:')} 155261 / 14567 / 1967."
            new_state = "ENDED"
            is_completed = True
        else:
            reask_text = get_reask_prompt(i18n, quality_report.reject_reason or "EMPTY_TRANSCRIPT", consecutive_rejects)
            new_state = current_state
            is_completed = False

        save_session(session_id, language, current_scheme, new_state, current_slots, is_completed, consecutive_rejects)

        tts_start = time.time()
        reply_audio = get_cached_tts(reask_text, language)
        tts_latency = time.time() - tts_start
        total_latency = time.time() - start_turn

        log_turn(
            session_id=session_id,
            turn_num=len(current_slots) + 1,
            user_transcript="[AUDIO REJECTED: " + str(quality_report.reject_reason) + "]",
            agent_text=reask_text,
            stt_latency=0.0,
            nlu_latency=0.0,
            tts_latency=tts_latency,
            total_latency=total_latency,
            gate_decision=quality_report.decision,
            reject_reason=quality_report.reject_reason,
            audio_duration=quality_report.duration_sec,
            rms_dbfs=quality_report.rms_dbfs,
            snr_db=quality_report.snr_db
        )

        return {
            "session_id": session_id,
            "gate_decision": "REJECT",
            "reject_reason": quality_report.reject_reason,
            "user_transcript": "",
            "agent_text": reask_text,
            "audio_base64": base64.b64encode(reply_audio).decode("utf-8"),
            "state": new_state,
            "scheme_id": current_scheme,
            "completed": is_completed,
            "evaluation": None,
            "latencies": {
                "stt": 0.0,
                "nlu": 0.0,
                "tts": round(tts_latency, 2),
                "total": round(total_latency, 2)
            }
        }

    # 2. GNANI PRISMA STT
    stt_res = transcribe_audio(audio_for_stt, language_code=language)
    user_transcript = stt_res.get("transcript", "").strip()
    detected_lang = stt_res.get("detected_language_code")
    stt_latency = stt_res.get("measured_latency", 0.0)

    # Check for empty/very short transcript (Gate rejects empty transcript even if audio passed)
    if len(user_transcript) <= 1:
        consecutive_rejects += 1
        if consecutive_rejects >= config.MAX_CONSECUTIVE_REJECTS:
            reask_text = f"{i18n['handoff']} {i18n.get('labels', {}).get('helpline', 'Helpline:')} 155261 / 14567 / 1967."
            new_state = "ENDED"
            is_completed = True
        else:
            reask_text = get_reask_prompt(i18n, "EMPTY_TRANSCRIPT", consecutive_rejects)
            new_state = current_state
            is_completed = False

        save_session(session_id, language, current_scheme, new_state, current_slots, is_completed, consecutive_rejects)

        tts_start = time.time()
        reply_audio = get_cached_tts(reask_text, language)
        tts_latency = time.time() - tts_start
        total_latency = time.time() - start_turn

        log_turn(
            session_id=session_id,
            turn_num=len(current_slots) + 1,
            user_transcript="[EMPTY TRANSCRIPT]",
            agent_text=reask_text,
            stt_latency=stt_latency,
            nlu_latency=0.0,
            tts_latency=tts_latency,
            total_latency=total_latency,
            gate_decision="REJECT",
            reject_reason="EMPTY_TRANSCRIPT",
            audio_duration=quality_report.duration_sec,
            rms_dbfs=quality_report.rms_dbfs,
            snr_db=quality_report.snr_db
        )

        return {
            "session_id": session_id,
            "gate_decision": "REJECT",
            "reject_reason": "EMPTY_TRANSCRIPT",
            "user_transcript": "",
            "agent_text": reask_text,
            "audio_base64": base64.b64encode(reply_audio).decode("utf-8"),
            "state": new_state,
            "scheme_id": current_scheme,
            "completed": is_completed,
            "evaluation": None,
            "latencies": {
                "stt": round(stt_latency, 2),
                "nlu": 0.0,
                "tts": round(tts_latency, 2),
                "total": round(total_latency, 2)
            }
        }

    # Successful user response -> reset consecutive rejects counter
    consecutive_rejects = 0

    # 3. DIALOGUE MANAGEMENT & DETERMINISTIC RULES ENGINE
    nlu_start = time.time()
    agent_text, new_state, new_scheme, new_slots, is_completed, eval_res = DialogueManager.process_turn(
        user_transcript=user_transcript,
        current_language=language,
        detected_language=detected_lang,
        scheme_id=current_scheme,
        current_state=current_state,
        collected_slots=current_slots,
        retry_count=consecutive_rejects
    )
    nlu_latency = time.time() - nlu_start

    # Update session in DB
    save_session(
        session_id=session_id,
        language=language,
        scheme_id=new_scheme,
        state=new_state,
        slots=new_slots,
        completed=is_completed,
        consecutive_rejects=consecutive_rejects
    )

    # Log case if evaluation completed
    if is_completed and eval_res and new_scheme:
        log_case(
            session_id=session_id,
            language=language,
            scheme_id=new_scheme,
            verdict=eval_res.get("verdict", "UNSURE"),
            reason=eval_res.get("reason", ""),
            slots=new_slots,
            documents=eval_res.get("documents", [])
        )

    # 4. GNANI TIMBRE TTS (with Caching)
    tts_start = time.time()
    try:
        reply_audio = get_cached_tts(agent_text, language)
        audio_b64 = base64.b64encode(reply_audio).decode("utf-8")
    except Exception as exc:
        # If live synthesis times out or hits 429 concurrency, return clean 200 with text transcript
        # and empty audio payload so browser displays the reply without a 'Connection glitch' warning.
        import logging as _logging
        _logging.getLogger("app.main").warning("Live TTS degraded to text-only mode: %s", exc)
        reply_audio = b""
        audio_b64 = ""
    tts_latency = time.time() - tts_start
    total_latency = time.time() - start_turn

    # Log turn to DB with quality gate metrics
    log_turn(
        session_id=session_id,
        turn_num=len(new_slots) + 1,
        user_transcript=user_transcript,
        agent_text=agent_text,
        stt_latency=stt_latency,
        nlu_latency=nlu_latency,
        tts_latency=tts_latency,
        total_latency=total_latency,
        gate_decision=quality_report.decision,
        reject_reason=None,
        audio_duration=quality_report.duration_sec,
        rms_dbfs=quality_report.rms_dbfs,
        snr_db=quality_report.snr_db
    )

    audio_base64 = audio_b64

    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "gate_decision": quality_report.decision,
        "reject_reason": None,
        "user_transcript": user_transcript,
        "agent_text": agent_text,
        "audio_base64": audio_base64,
        "state": new_state,
        "scheme_id": new_scheme,
        "completed": is_completed,
        "evaluation": eval_res,
        "latencies": {
            "stt": round(stt_latency, 2),
            "nlu": round(nlu_latency, 3),
            "tts": round(tts_latency, 2),
            "total": round(total_latency, 2)
        }
    }
