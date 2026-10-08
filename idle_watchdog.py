#!/usr/bin/env python3
"""Llama-server idle watchdog.

Polls the journals of the managed units (see UNITS) for the "entering
sleeping state" marker emitted by llama.cpp when a model server becomes
idle. After a configurable grace period with no further activity, restarts
the unit that slept so the loaded models are dropped from VRAM and the iGPU
can power down. Only the unit owning the freshest sleep marker is tracked;
when that unit is stopped the cycle resets and waits for another managed
unit to sleep.

Shutdown logic: once the models have been unloaded (restart happened) and no
SSH session has been active for a grace period, and no tmux session exists,
the host is powered off (sudo -n shutdown -h now). Any new SSH/tmux activity
cancels the pending shutdown.

Safety: the host is never powered off unless it has been up for MIN_UPTIME,
and any shutdown state persisted from a previous boot is cleared on a recent
reboot. This prevents powering off freshly-booted hosts based on stale state.

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
from datetime import datetime, timedelta
from pathlib import Path

CHECK_INTERVAL = 60
IDLE_GRACE = 5 * 60
# Managed llama-server units; the watchdog tracks the one whose journal has
# the freshest sleep marker and restarts that unit on idle.
UNITS = ["llama-server.service", "llama-server-strix.service"]
SLEEP_MARKER = "entering sleeping state"
ACTION = "restart"

# Shutdown conditions ---
# 1) How long the models must have been unloaded before shutdown is considered.
SHUTDOWN_GRACE = 60 * 60
# 2) Max idle time of the most-recently-active SSH session before shutdown.
SSH_GRACE = 30 * 60
SHUTDOWN_CMD = ["sudo", "-n", "shutdown", "-h", "now"]
SHUTDOWN_DRYRUN = False

# Never consider shutdown until the host has been up at least this long.
# Prevents bricking the machine right after boot (old state + persistent
# journal would otherwise trigger an immediate power-off).
MIN_UPTIME = 30 * 60


def uptime_seconds() -> float:
    """Host uptime in seconds, read from /proc/uptime."""
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return float("inf")

STATE_DIR = Path.home() / ".local/state/llama-watcher"
STATE_FILE = STATE_DIR / "state.json"


def log(msg: str) -> None:
    print(f"[llama-watcher] {msg}", flush=True)


def journal(unit: str, since: datetime | None = None) -> str:
    cmd = [
        "journalctl",
        "--user",
        "-u",
        unit,
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
        log(f"journalctl failed for {unit}: {e}")
        return ""


def parse_ts(line: str) -> datetime | None:
    head = line.split(" ", 1)[0]
    try:
        dt = datetime.fromisoformat(head)
        # Naive timestamps (as written by datetime.now().isoformat()) are
        # already local wall-clock time; leave them as-is.
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def find_last_sleep(units: list[str]) -> tuple[datetime, str] | None:
    """Freshest sleep marker across the given units.

    Returns (timestamp, unit) of the newest "entering sleeping state" line
    found in any of the units' journals, or None if none has ever slept.
    Only pass *active* units: journals are persistent, so a stopped unit's
    old marker would otherwise outrank an active unit's newer cycle forever.
    """
    best: tuple[datetime, str] | None = None
    for unit in units:
        out = journal(unit)
        for line in out.splitlines():
            if SLEEP_MARKER in line:
                ts = parse_ts(line)
                if ts is None:
                    continue
                if best is None or ts > best[0]:
                    best = (ts, unit)
    return best


REQUEST_RE = re.compile(
    # request accepted by the router (start of an API call)
    r"proxying request to model"
    # task started processing (prefill in progress)
    r"|\bslot\b.*\blaunch_slot_\b.*\bprocessing task\b"
    # generation finished (legacy marker)
    r"|\bslot\b.*\brelease\b.*\bstop processing: n_tokens"
)


def has_request_activity_since(ts: datetime) -> bool:
    """True if a real inference request was served on any managed unit since ts.

    Matches markers of actual API traffic, both at request start (router
    "proxying request" line, slot "processing task" line) and at completion
    ("slot release ... stop processing: n_tokens = N"). These appear solely
    for real requests, not for server startup or model unload, so they are a
    reliable signal that a model was reloaded and used again after unload.
    Scans every managed unit so a request to either server cancels a pending
    reload/shutdown.
    """
    for unit in UNITS:
        out = journal(unit, since=ts)
        for line in out.splitlines():
            if REQUEST_RE.search(line):
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
        "shutdown_countdown": False,
        "last_unload_iso": None,
        "last_session_iso": None,
        "tracked_unit": None,
    }


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_service_active(unit: str) -> bool:
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() == "active"
    except Exception:
        return True


def active_units() -> list[str]:
    """Managed units that are currently active."""
    return [u for u in UNITS if is_service_active(u)]


def run_action(unit: str) -> None:
    log(f"running: systemctl --user {ACTION} {unit}")
    try:
        subprocess.run(
            ["systemctl", "--user", ACTION, unit],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        log(f"action failed: {e}")


def has_ssh_sessions() -> bool:
    """True if any SSH session is present (via `w -h`, lines with pts/*)."""
    try:
        out = subprocess.run(
            ["w", "-h"], capture_output=True, text=True, timeout=10
        ).stdout
        return any("pts/" in line for line in out.splitlines())
    except Exception as e:
        log(f"w -h failed: {e}")
        return True


def has_tmux_sessions() -> bool:
    """True if any tmux session exists (`tmux list-sessions` exit 0)."""
    try:
        r = subprocess.run(
            ["tmux", "list-sessions"], capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except Exception as e:
        log(f"tmux list-sessions failed: {e}")
        return True


def has_blocking_sessions() -> bool:
    """Blocking activity: an SSH session or a tmux session."""
    return has_ssh_sessions() or has_tmux_sessions()


def run_shutdown() -> None:
    if SHUTDOWN_DRYRUN:
        log(f"DRYRUN would run: {SHUTDOWN_CMD}")
        return
    log(f"running: {' '.join(SHUTDOWN_CMD)}")
    try:
        subprocess.run(SHUTDOWN_CMD, capture_output=True, text=True, timeout=15)
    except Exception as e:
        log(f"shutdown failed: {e}")


_stop = False


def _on_signal(signum, frame):
    global _stop
    log(f"received signal {signum}, exiting")
    _stop = True


def check_shutdown(state: dict, now: datetime) -> bool:
    """Evaluate shutdown conditions once the models are unloaded.

    Returns True if shutdown was issued. Updates and saves state as needed.
    """
    unload_iso = state.get("last_action_iso") or state.get("last_unload_iso")
    unload = parse_ts(unload_iso) if unload_iso else None
    if unload is None:
        return False

    if uptime_seconds() < MIN_UPTIME:
        log(f"host up only {int(uptime_seconds())}s (< {MIN_UPTIME}s): "
            "definitely not shutting down this cycle")
        return False

    if has_request_activity_since(unload):
        log("new inference request after unload: models reloaded, "
            "reset shutdown countdown")
        state["action_taken"] = False
        state["last_action_iso"] = None
        state["last_sleep_iso"] = None
        state["shutdown_countdown"] = False
        state["last_unload_iso"] = None
        save_state(state)
        return False

    last_session_iso = state.get("last_session_iso")
    last_session = parse_ts(last_session_iso) if last_session_iso else None

    if has_blocking_sessions():
        state["last_session_iso"] = now.isoformat()
        state["last_unload_iso"] = unload_iso
        if state.get("shutdown_countdown"):
            log("blocking SSH/tmux activity detected, cancelling shutdown")
            state["shutdown_countdown"] = False
        save_state(state)
        log("blocking sessions present, shutdown countdown paused")
        return False

    unload_age = now - unload
    session_age = (
        (now - last_session) if last_session is not None else timedelta.max
    )

    if unload_age < timedelta(seconds=SHUTDOWN_GRACE):
        if state.get("shutdown_countdown"):
            state["shutdown_countdown"] = False
            save_state(state)
        log(
            f"no sessions, but models unloaded only {unload_age} ago "
            f"(need {SHUTDOWN_GRACE}s); not shutting down yet"
        )
        return False

    if session_age < timedelta(seconds=SSH_GRACE):
        if state.get("shutdown_countdown"):
            state["shutdown_countdown"] = False
            save_state(state)
        log(
            f"no sessions, but last session only {session_age} ago "
            f"(need {SSH_GRACE}s); not shutting down yet"
        )
        return False

    log(
        f"shutdown conditions met: models unloaded {unload_age} ago, "
        f"last session {session_age} ago. Powering off."
    )
    run_shutdown()
    state["shutdown_countdown"] = False
    save_state(state)
    return True


def main() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    log(
        f"started: check_interval={CHECK_INTERVAL}s, idle_grace={IDLE_GRACE}s, "
        f"units={','.join(UNITS)}, action={ACTION}, "
        f"shutdown_grace={SHUTDOWN_GRACE}s, "
        f"ssh_grace={SSH_GRACE}s, min_uptime={MIN_UPTIME}s, "
        f"dryrun={SHUTDOWN_DRYRUN}"
    )

    # If the host was rebooted recently, any persisted shutdown target from a
    # previous session is stale. Reset it so a fresh idle cycle starts instead
    # of powering off right after boot.
    state = load_state()
    if uptime_seconds() < MIN_UPTIME and (
        state.get("action_taken") or state.get("last_unload_iso")
    ):
        log(f"recent boot (uptime < {MIN_UPTIME}s): clearing stale shutdown "
            "state, starting a fresh idle cycle")
        state.update(
            {
                "last_sleep_iso": None,
                "action_taken": False,
                "last_action_iso": None,
                "last_unload_iso": None,
                "shutdown_countdown": False,
                "last_session_iso": None,
                "tracked_unit": None,
            }
        )
        save_state(state)

    while not _stop:
        try:
            now = datetime.now()
            state = load_state()
            actives = active_units()
            found = find_last_sleep(actives)

            if found is None:
                if not actives and state.get("action_taken"):
                    # Every managed unit is off after our reload: models are
                    # out of VRAM, so the shutdown evaluation still applies.
                    log("no managed unit is active after reload; "
                        "evaluating shutdown")
                    check_shutdown(state, now)
                    time.sleep(CHECK_INTERVAL)
                    continue
                if state.get("last_sleep_iso") or state.get("action_taken"):
                    log("no sleep markers in active units, clearing state")
                    save_state(
                        {
                            "last_sleep_iso": None,
                            "action_taken": False,
                            "last_action_iso": None,
                            "last_seen_sleep_iso": state.get("last_seen_sleep_iso"),
                            "tracked_unit": None,
                        }
                    )
                time.sleep(CHECK_INTERVAL)
                continue

            last_sleep, tracked_unit = found
            last_sleep_iso = last_sleep.isoformat()
            prev_seen = state.get("last_seen_sleep_iso")

            if prev_seen != last_sleep_iso:
                log(f"new sleep marker observed at {last_sleep_iso} "
                    f"({tracked_unit})")
                state["last_seen_sleep_iso"] = last_sleep_iso

            if (
                state.get("last_sleep_iso") != last_sleep_iso
                or state.get("tracked_unit") != tracked_unit
            ):
                # (re)enter the idle-detection cycle for this sleep marker,
                # even if it was previously seen (state might have been reset
                # to null while last_seen_sleep_iso still holds this marker),
                # or when the tracked unit switched (e.g. llama-server was
                # stopped and strix became the active server).
                if (
                    state.get("tracked_unit")
                    and state.get("tracked_unit") != tracked_unit
                ):
                    log(f"tracked unit switched: {state['tracked_unit']} -> "
                        f"{tracked_unit}, restarting idle cycle")
                state["last_sleep_iso"] = last_sleep_iso
                state["tracked_unit"] = tracked_unit
                state["action_taken"] = False
                state["last_action_iso"] = None
                state["last_unload_iso"] = None
                state["shutdown_countdown"] = False
                save_state(state)

            if state.get("last_sleep_iso") is None:
                time.sleep(CHECK_INTERVAL)
                continue

            if state.get("action_taken"):
                do_shutdown = check_shutdown(state, now)
                if do_shutdown:
                    # shutdown will power off the host; nothing left to do here
                    time.sleep(CHECK_INTERVAL)
                    continue
                time.sleep(CHECK_INTERVAL)
                continue

            if now - last_sleep < timedelta(seconds=IDLE_GRACE):
                time.sleep(CHECK_INTERVAL)
                continue

            if not is_service_active(tracked_unit):
                log(f"unit {tracked_unit} not active, resetting cycle "
                    "(waiting for server to come up before considering "
                    "shutdown)")
                state["last_sleep_iso"] = None
                state["action_taken"] = False
                state["last_action_iso"] = None
                state["last_unload_iso"] = None
                state["shutdown_countdown"] = False
                state["tracked_unit"] = None
                save_state(state)
                time.sleep(CHECK_INTERVAL)
                continue

            if has_request_activity_since(last_sleep):
                log("request activity after sleep, waiting for new sleep event")
                state["last_sleep_iso"] = None
                state["action_taken"] = False
                state["last_action_iso"] = None
                save_state(state)
                time.sleep(CHECK_INTERVAL)
                continue

            log(
                f"idle confirmed: sleep at {last_sleep_iso} on "
                f"{tracked_unit}, grace {IDLE_GRACE}s expired, no activity"
            )
            run_action(tracked_unit)
            state["action_taken"] = True
            state["last_action_iso"] = now.isoformat()
            state["tracked_unit"] = tracked_unit
            save_state(state)

        except Exception as e:
            log(f"loop error: {e}")

        time.sleep(CHECK_INTERVAL)

    return 0


if __name__ == "__main__":
    sys.exit(main())
