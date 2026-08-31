#!/bin/bash
# Координатор 2-узлового RPC-кластера llama-server: Qwen3.8-Flash-Next Q6_K_XL.
# Запускается systemd-юнитом llama-flash-cluster.service (по ручному запросу, disabled).
# Второй узел (192.168.1.2) используется как RPC-воркер (ggml-rpc-server, порт 50052).
set -euo pipefail

WORKER_HOST=192.168.1.2
WORKER_PORT=50052
MODEL_DIR=/home/nikita/models/Qwen3.8-Flash-Next
MODEL=$MODEL_DIR/Q6_K_XL/Qwen3.8-Flash-Next-UD-Q6_K_XL-00001-of-00006.gguf
MMPROJ=$MODEL_DIR/mmproj-BF16.gguf

exec llama-server \
  --model "$MODEL" \
  --mmproj "$MMPROJ" \
  --host 0.0.0.0 --port 8080 \
  --ctx-size 262144 \
  --split-mode layer \
  --rpc "${WORKER_HOST}:${WORKER_PORT}" \
  --main-gpu 0 \
  --tensor-split 0.5,0.5