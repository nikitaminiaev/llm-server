#!/bin/bash
# Combined supervisor: llama.cpp (8080) + CrispASR (8081) in one container.
#
# - starts both servers
# - on crash of one, restarts ONLY that one (the other keeps running)
# - on SIGTERM/SIGINT, forwards to children and exits (clean shutdown)
# - watches /home/nikita/models/.llama-reload: when present, restarts ONLY llama
#   (used by idle_watchdog.py so CrispASR is not interrupted by llama idle recycle)

RELOAD_TRIGGER="/home/nikita/models/.llama-reload"

cleanup() {
    echo "start_all: shutdown signal received, terminating children"
    kill -TERM "$LLAMA_PID" "$CRISP_PID" 2>/dev/null
    wait
    exit 0
}
trap cleanup TERM INT

start_llama() {
    llama-server --models-preset /home/nikita/models/config/models.ini \
        --host 0.0.0.0 --port 8080 --models-max 3 --parallel 1 --sleep-idle-seconds 1800 &
    LLAMA_PID=$!
    echo "start_all: llama-server started (pid $LLAMA_PID)"
}

start_crisp() {
    /home/nikita/models/crispasr --server \
        -m /home/nikita/models/parakeet-tdt-0.6b-v3-q8_0.gguf \
        --host 0.0.0.0 --port 8081 &
    CRISP_PID=$!
    echo "start_all: crispasr started (pid $CRISP_PID)"
}

# drop any stale trigger from a previous run
rm -f "$RELOAD_TRIGGER"

start_llama
start_crisp

# trigger watcher: reload only llama when the trigger file appears
( while true; do
    if [ -e "$RELOAD_TRIGGER" ]; then
        rm -f "$RELOAD_TRIGGER"
        echo "start_all: llama reload triggered"
        pkill -TERM -f 'llama-server --models-preset' 2>/dev/null
    fi
    sleep 3
  done ) &

# supervisor loop: restart only the child that died
while true; do
    wait -n
    if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
        echo "start_all: llama-server exited, restarting"
        start_llama
    fi
    if ! kill -0 "$CRISP_PID" 2>/dev/null; then
        echo "start_all: crispasr exited, restarting"
        start_crisp
    fi
done
