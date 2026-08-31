#!/bin/bash
# RPC-воркер 2-узлового llama-cluster (Qwen3.8-Flash-Next Q6_K_XL).
# Запускается юнитом llama-rpc-llama.service внутри контейнера llama-rocm-10.0.
# --cache: веса кешируются в ~/.cache/llama.cpp/rpc (повторные загрузки без сети).
set -euo pipefail
exec ggml-rpc-server --host 0.0.0.0 --port 50052 --cache
