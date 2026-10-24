"""Ops Telegram helpers: /check, /test replies and backend-error alerts.

Does not change business alert copy (试多观察 / 开单 templates).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from config import (
    FREEZE_MODE_SEND_X_ONLY,
    SMCT_REPO_ROOT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ERROR_ALERT_COOLDOWN_SECONDS,
)
from engine.runtime_state import RuntimeStateStore
from engine.trend_messages import build_format_test_message, build_format_test_message_15m
from services.telegram import TelegramSendError, send_telegram_message

logger = logging.getLogger("ops_status")


def extract_bot_command(text: str | None) -> str | None:
    """Return bare command name (e.g. 'check') from a Telegram message text."""
    if not text:
        return None
    raw = str(text).strip()
    if not raw.startswith("/"):
        return None
    token = raw.split()[0]
    name = token[1:]
    if "@" in name:
        name = name.split("@", 1)[0]
    name = name.strip().lower()
    return name or None


def extract_bot_command_arg(text: str | None) -> str | None:
    """Return first argument after /command (lowercased), or None if missing."""
    if not text:
        return None
    parts = str(text).strip().split()
    if len(parts) < 2:
        return None
    arg = parts[1].strip().lower()
    return arg or None


def _repo_root_candidates(explicit_cwd: str | None = None) -> list[str]:
    """Ordered git cwd candidates: explicit, SMCT_REPO_ROOT, install root, cwd."""
    roots: list[str] = []
    if explicit_cwd:
        roots.append(explicit_cwd)
    env_root = (SMCT_REPO_ROOT or os.getenv("SMCT_REPO_ROOT", "") or "").strip()
    if env_root:
        roots.append(env_root)
    # services/ops_status.py -> repo install root
    install_root = str(Path(__file__).resolve().parents[1])
    roots.append(install_root)
    roots.append(".")
    # Dedupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for root in roots:
        key = os.path.abspath(root)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(root)
    return ordered


def resolve_git_head(cwd: str | None = None) -> str:
    """Return short HEAD sha; prefer SMCT_REPO_ROOT / install root over fragile cwd."""
    for root in _repo_root_candidates(cwd):
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root,
                timeout=2,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            sha = (out or "").strip()
            if sha:
                return sha
        except Exception:
            continue
    return "n/a"


def build_check_message(
    health: dict[str, Any] | None = None,
    *,
    freeze_mode: bool | None = None,
    head_sha: str | None = None,
) -> str:
    health = health or {}
    freeze = FREEZE_MODE_SEND_X_ONLY if freeze_mode is None else bool(freeze_mode)
    head = head_sha if head_sha is not None else resolve_git_head()
    ok = bool(health.get("ok"))
    stale = bool(health.get("stale"))
    if ok:
        status = "running"
    elif stale:
        status = "stale"
    else:
        status = "error"

    age = health.get("seconds_since_last_scan")
    age_text = f"{age}s" if age is not None else "n/a"
    last_err = (health.get("last_scan_error") or "").strip() or "无"
    if len(last_err) > 160:
        last_err = last_err[:160] + "…"

    return (
        "🛠 /check\n"
        f"状态: {status}\n"
        f"HEAD: {head}\n"
        f"freeze: {1 if freeze else 0}\n"
        f"上次扫描: {age_text} ({'ok' if health.get('last_scan_ok') else 'fail'})\n"
        f"上次错误: {last_err}"
    )


def build_error_message(source: str, error: str) -> str:
    brief = (error or "unknown").strip()[:200] or "unknown"
    src = (source or "backend").strip()[:64] or "backend"
    return f"⚠️ 系统异常\n来源: {src}\n错误: {brief}"


def _error_fingerprint(source: str, error: str) -> str:
    return f"{source}|{(error or '')[:120]}"


def should_send_error_alert(
    state: RuntimeStateStore,
    source: str,
    error: str,
    *,
    cooldown_seconds: int | None = None,
    now: float | None = None,
) -> bool:
    cooldown = (
        TELEGRAM_ERROR_ALERT_COOLDOWN_SECONDS
        if cooldown_seconds is None
        else int(cooldown_seconds)
    )
    now_ts = time.time() if now is None else float(now)
    snap = state.get_snapshot()
    last = snap.get("last_error_alert") or {}
    last_at = float(last.get("at") or 0.0)
    last_fp = str(last.get("fingerprint") or "")
    fp = _error_fingerprint(source, error)
    if last_fp == fp and last_at and (now_ts - last_at) < cooldown:
        return False
    return True


def mark_error_alert_sent(state: RuntimeStateStore, source: str, error: str) -> None:
    state.state["last_error_alert"] = {
        "source": source,
        "fingerprint": _error_fingerprint(source, error),
        "error": (error or "")[:200],
        "at": time.time(),
    }
    state._save()


def notify_backend_error(
    source: str,
    error: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    state: RuntimeStateStore | None = None,
    cooldown_seconds: int | None = None,
) -> dict[str, Any]:
    """Push a TG ops alert for a backend failure (rate-limited). Never raises."""
    token = TELEGRAM_BOT_TOKEN if token is None else token
    chat_id = TELEGRAM_CHAT_ID if chat_id is None else chat_id
    store = state or RuntimeStateStore()
    if not token or not chat_id:
        logger.warning("ops_error_alert_skipped reason=missing_telegram_creds source=%s", source)
        return {"ok": False, "skipped": True, "reason": "missing_telegram_creds"}
    if not should_send_error_alert(store, source, error, cooldown_seconds=cooldown_seconds):
        logger.info("ops_error_alert_suppressed source=%s", source)
        return {"ok": True, "skipped": True, "reason": "cooldown"}
    message = build_error_message(source, error)
    try:
        result = send_telegram_message(token, chat_id, message)
        mark_error_alert_sent(store, source, error)
        return {"ok": True, "skipped": False, "telegram_result": result, "message": message}
    except TelegramSendError as exc:
        logger.warning("ops_error_alert_send_failed source=%s error=%s", source, exc)
        return {"ok": False, "skipped": False, "error": str(exc), "message": message}


def handle_check_command(
    *,
    state: RuntimeStateStore | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    reply_chat_id: str | None = None,
) -> dict[str, Any]:
    token = TELEGRAM_BOT_TOKEN if token is None else token
    configured_chat = str(TELEGRAM_CHAT_ID if chat_id is None else chat_id)
    dest = str(reply_chat_id or configured_chat)
    if configured_chat and dest != configured_chat:
        logger.info("ops_check_ignored foreign_chat=%s", dest)
        return {"ok": True, "skipped": True, "reason": "foreign_chat"}
    store = state or RuntimeStateStore()
    health = store.build_health_payload()
    # Prefer last_scan_ok from raw state for the "上次扫描" line.
    snap = store.get_snapshot()
    health = dict(health)
    health["last_scan_ok"] = bool(snap.get("last_scan_ok"))
    message = build_check_message(health)
    if not token or not dest:
        return {"ok": False, "skipped": True, "reason": "missing_telegram_creds", "message": message}
    result = send_telegram_message(token, dest, message)
    return {"ok": True, "skipped": False, "telegram_result": result, "message": message}



def handle_test_command(
    *,
    token: str | None = None,
    chat_id: str | None = None,
    reply_chat_id: str | None = None,
    arg: str | None = None,
) -> dict[str, Any]:
    """Reply with format sample copy (ops-only; no signal state mutation).

    Routing (L+user 2026-10-25):
    - first arg ``15`` / ``15m`` → 15m weak-reminder dual sample
    - missing / any other arg → existing 1H 试多/试空 dual sample (bare /test unchanged)
    """
    token = TELEGRAM_BOT_TOKEN if token is None else token
    configured_chat = str(TELEGRAM_CHAT_ID if chat_id is None else chat_id)
    dest = str(reply_chat_id or configured_chat)
    if configured_chat and dest != configured_chat:
        logger.info("ops_test_ignored foreign_chat=%s", dest)
        return {"ok": True, "skipped": True, "reason": "foreign_chat"}
    mode = (arg or "").strip().lower()
    if mode in {"15", "15m"}:
        message = build_format_test_message_15m()
        sample_kind = "15m"
    else:
        message = build_format_test_message()
        sample_kind = "1h"
    if not token or not dest:
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing_telegram_creds",
            "message": message,
            "sample_kind": sample_kind,
        }
    result = send_telegram_message(token, dest, message)
    return {
        "ok": True,
        "skipped": False,
        "telegram_result": result,
        "message": message,
        "sample_kind": sample_kind,
    }


def process_telegram_update(update: dict[str, Any], *, state: RuntimeStateStore | None = None) -> dict[str, Any]:
    """Handle one Bot API update. Supports /check and /test (business chat only)."""
    message = update.get("message") or update.get("edited_message") or {}
    text = message.get("text") or message.get("caption")
    command = extract_bot_command(text)
    if command not in {"check", "test"}:
        return {"ok": True, "handled": False, "command": command}
    chat = message.get("chat") or {}
    reply_chat_id = chat.get("id")
    reply_id = str(reply_chat_id) if reply_chat_id is not None else None
    try:
        if command == "check":
            result = handle_check_command(state=state, reply_chat_id=reply_id)
        else:
            result = handle_test_command(
                reply_chat_id=reply_id,
                arg=extract_bot_command_arg(text),
            )
        result["handled"] = True
        result["command"] = command
        return result
    except TelegramSendError as exc:
        logger.warning("ops_%s_send_failed error=%s", command, exc)
        return {"ok": False, "handled": True, "command": command, "error": str(exc)}
