#!/usr/bin/env python3
"""Llama-server idle watchdog.

Polls the journal of llama-server.service for the "entering sleeping state"
marker emitted by llama.cpp's router when a model server becomes idle. After
a configurable grace period with no further activity, restarts the service
so the loaded models are dropped from VRAM and the iGPU can power down.

Runs as a standalone systemd --user service. Does not modify any existing
configuration of llama-server.
"""

from __future__ import annotations

import json
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHECK_INTERVAL = 60
IDLE_GRACE = 5 * 60
LOG_UNIT = "llama-server.service"
SLEEP_MARKER = "entering sleeping state"
SLEEP_LINE_RE = re.compile(r"\bsleep\w*", re.IGNORECASE)
ACTION = "restart"


def is_sleep_line(line: str) -> bool:
    return bool(SLEEP_LINE_RE.search(line))

STATE_DIR = Path.home() / ".local/state/llama-watcher"
STATE_FILE = STATE_DIR / "state.json"


def log(msg: str) -> None:
    print(f"[llama-watcher] {msg}", flush=True)


def journal(since: datetime | None = None) -> str:
    cmd = [
        "journalctl",
        "--user",
        "-u",
        LOG_UNIT,
        "--no-pager",
        "-q",
        "--output=short-iso",
    ]
    if since is not None:
        cmd.append(f"--since={since.isoformat()}")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return out.stdout
    except Exception as e:
        log(f"journalctl failed: {e}")
        return ""


def parse_ts(line: str) -> datetime | None:
    head = line.split(" ", 1)[0]
    try:
        dt = datetime.fromisoformat(head)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz=None).replace(tzinfo=None)
    except ValueError:
        return None


def find_last_sleep() -> datetime | None:
    out = journal()
    last: datetime | None = None
    for line in out.splitlines():
        if SLEEP_MARKER in line:
            ts = parse_ts(line)
            if ts is not None:
                last = ts
    return last


def has_activity_since(ts: datetime) -> bool:
    out = journal(since=ts)
    for line in out.splitlines():
        if is_sleep_line(line):
            continue
        return True
    return False


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "last_sleep_iso": None,
        "action_taken": False,
        "last_action_iso": None,
        "last_seen_sleep_iso": None,
    }


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_service_active() -> bool:
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", LOG_UNIT],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() == "active"
    except Exception:
        return True


def run_action() -> None:
    log(f"running: systemctl --user {ACTION} {LOG_UNIT}")
    try:
        subprocess.run(
            ["systemctl", "--user", ACTION, LOG_UNIT],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        log(f"action failed: {e}")


_stop = False


def _on_signal(signum, frame):
    global _stop
    log(f"received signal {signum}, exiting")
    _stop = True


def main() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    log(
        f"started: check_interval={CHECK_INTERVAL}s, idle_grace={IDLE_GRACE}s, "
        f"unit={LOG_UNIT}, action={ACTION}"
    )

    while not _stop:
        try:
            now = datetime.now()
            state = load_state()
            last_sleep = find_last_sleep()

            if last_sleep is None:
                if state.get("last_sleep_iso") or state.get("action_taken"):
                    log("no sleep markers in journal, clearing state")
                    save_state(
                        {
                            "last_sleep_iso": None,
                            "action_taken": False,
                            "last_action_iso": None,
                            "last_seen_sleep_iso": state.get("last_seen_sleep_iso"),
                        }
                    )
                time.sleep(CHECK_INTERVAL)
                continue

            last_sleep_iso = last_sleep.isoformat()
            prev_seen = state.get("last_seen_sleep_iso")

            if prev_seen != last_sleep_iso:
                log(f"new sleep marker observed at {last_sleep_iso}")
                state = {
                    "last_sleep_iso": last_sleep_iso,
                    "action_taken": False,
                    "last_action_iso": None,
                    "last_seen_sleep_iso": last_sleep_iso,
                }
                save_state(state)

            if state.get("last_sleep_iso") is None:
                time.sleep(CHECK_INTERVAL)
                continue

            if state.get("action_taken"):
                time.sleep(CHECK_INTERVAL)
                continue

            if now - last_sleep < timedelta(seconds=IDLE_GRACE):
                time.sleep(CHECK_INTERVAL)
                continue

            if not is_service_active():
                log("service not active, leaving it as-is")
                state["action_taken"] = True
                state["last_action_iso"] = now.isoformat()
                save_state(state)
                time.sleep(CHECK_INTERVAL)
                continue

            if has_activity_since(last_sleep):
                log("activity detected after sleep, waiting for new sleep event")
                state["last_sleep_iso"] = None
                state["action_taken"] = False
                state["last_action_iso"] = None
                save_state(state)
                time.sleep(CHECK_INTERVAL)
                continue

            log(
                f"idle confirmed: sleep at {last_sleep_iso}, "
                f"grace {IDLE_GRACE}s expired, no activity"
            )
            run_action()
            state["action_taken"] = True
            state["last_action_iso"] = now.isoformat()
            save_state(state)

        except Exception as e:
            log(f"loop error: {e}")

        time.sleep(CHECK_INTERVAL)

    return 0


if __name__ == "__main__":
    sys.exit(main())
