"""
Investment Debate API endpoints.

POST /api/debate/start       — start a new debate
GET  /api/debate/<id>/status — debate progress
GET  /api/debate/<id>/result — full result
GET  /api/debate/<id>/rounds/<n> — individual round
"""

import asyncio
import os
import threading
import uuid
from typing import Optional

from flask import jsonify, request

from . import debate_bp
from ..config import Config
from ..models.debate import DebateStatus
from ..services.investment_debate import (
    InvestmentDebateEngine,
    get_debate,
    list_debates,
)
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.debate")

# Keep track of running debate threads
_running: dict = {}


def _run_debate_async(debate_id: str, question: str, doc_text: str, file_name: Optional[str]):
    """Run the debate engine in a background thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        engine = InvestmentDebateEngine()
        loop.run_until_complete(engine.run_debate(question, doc_text, file_name, debate_id=debate_id))
        logger.info(f"Debate {debate_id} completed")
    except Exception as e:
        logger.exception(f"Debate {debate_id} failed: {e}")
        debate = get_debate(debate_id)
        if debate:
            debate.status = DebateStatus.FAILED
            debate.error = str(e)
    finally:
        loop.close()
        _running.pop(debate_id, None)


@debate_bp.route("/start", methods=["POST"])
def start_debate():
    """Start a new investment debate.

    Accepts either:
    - multipart form with 'file' (PDF/TXT/MD) + 'question' field
    - JSON body with 'text' and 'question'
    """
    question = None
    doc_text = None
    file_name = None

    if request.content_type and "multipart" in request.content_type:
        question = request.form.get("question")
        uploaded = request.files.get("file")

        if not question:
            return jsonify({"success": False, "error": "Missing 'question' field"}), 400

        if uploaded:
            file_name = uploaded.filename
            # Save to temp location
            upload_dir = Config.UPLOAD_FOLDER
            os.makedirs(upload_dir, exist_ok=True)
            temp_path = os.path.join(upload_dir, f"debate_{uuid.uuid4().hex}_{file_name}")
            uploaded.save(temp_path)

            try:
                doc_text = FileParser.extract_text(temp_path)
            except Exception as e:
                return jsonify({"success": False, "error": f"File parsing failed: {e}"}), 400
        else:
            doc_text = request.form.get("text", "")
    else:
        body = request.get_json(silent=True) or {}
        question = body.get("question")
        doc_text = body.get("text", "")
        file_name = body.get("file_name")

    if not question:
        return jsonify({"success": False, "error": "Missing 'question'"}), 400
    if not doc_text:
        return jsonify({"success": False, "error": "Missing document text or file"}), 400

    # Pre-create the debate result so we can return the ID immediately.
    # The engine will populate _debate_store under this ID.
    from ..models.debate import DebateResult
    from ..services.investment_debate import _debate_store

    result = DebateResult(question=question, file_name=file_name)
    debate_id = result.debate_id
    _debate_store[debate_id] = result

    # Start in background thread
    t = threading.Thread(
        target=_run_debate_async,
        args=(debate_id, question, doc_text, file_name),
        daemon=True,
    )
    _running[debate_id] = t
    t.start()

    logger.info(f"Debate {debate_id} started for question: {question[:80]}")
    return jsonify({
        "success": True,
        "debate_id": debate_id,
        "status": "running",
    })


@debate_bp.route("/<debate_id>/status", methods=["GET"])
def debate_status(debate_id: str):
    """Get debate progress."""
    debate = get_debate(debate_id)
    if not debate:
        return jsonify({"success": False, "error": "Debate not found"}), 404

    return jsonify({
        "success": True,
        "debate_id": debate_id,
        "status": debate.status.value,
        "progress": debate.progress,
        "rounds_completed": len(debate.rounds),
        "error": debate.error,
    })


@debate_bp.route("/<debate_id>/result", methods=["GET"])
def debate_result(debate_id: str):
    """Get full debate result."""
    debate = get_debate(debate_id)
    if not debate:
        return jsonify({"success": False, "error": "Debate not found"}), 404

    return jsonify({
        "success": True,
        "data": debate.model_dump(mode="json"),
    })


@debate_bp.route("/<debate_id>/rounds/<int:round_number>", methods=["GET"])
def debate_round(debate_id: str, round_number: int):
    """Get a specific debate round."""
    debate = get_debate(debate_id)
    if not debate:
        return jsonify({"success": False, "error": "Debate not found"}), 404

    for rd in debate.rounds:
        if rd.round_number == round_number:
            return jsonify({
                "success": True,
                "data": rd.model_dump(mode="json"),
            })

    return jsonify({"success": False, "error": f"Round {round_number} not found"}), 404


@debate_bp.route("/list", methods=["GET"])
def list_all_debates():
    """List all debates."""
    debates = list_debates()
    return jsonify({
        "success": True,
        "data": [
            {
                "debate_id": d.debate_id,
                "question": d.question,
                "status": d.status.value,
                "progress": d.progress,
                "file_name": d.file_name,
                "created_at": d.created_at.isoformat(),
            }
            for d in debates
        ],
    })
