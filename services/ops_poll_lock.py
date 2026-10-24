"""Exclusive flock for Telegram ops getUpdates poller.

When smct-alert and smct-webhook both load app:app, only one process should
long-poll getUpdates. Hold the returned file handle for the poller's lifetime.
"""

from __future__ import annotations

import fcntl
import logging
import os
from typing import IO

logger = logging.getLogger("ops_poll_lock")


def try_acquire_ops_poll_lock(path: str) -> IO[str] | None:
    """Exclusive non-blocking flock. None => another process holds the lock."""
    parent = os.path.dirname(path) or "."
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError:
        pass
    try:
        fh = open(path, "a+", encoding="utf-8")
    except OSError as exc:
        logger.warning("ops_poll_lock_open_failed path=%s error=%s", path, exc)
        return None
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    except OSError as exc:
        logger.warning("ops_poll_lock_failed path=%s error=%s", path, exc)
        fh.close()
        return None
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()}\n")
        fh.flush()
    except OSError:
        pass
    return fh


def release_ops_poll_lock(fh: IO[str] | None) -> None:
    if fh is None:
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        fh.close()
    except OSError:
        pass
