#!/bin/bash

# SWA bounded replay — ускорение prefill длинных промптов (README весов 1017)
export DS4_ENABLE_V41_DECODER_SWA_BOUNDED_REPLAY=1

# V4.1 Flash: только tensor-parallel между двумя нодами (pipeline --layers не поддерживается)
ds4-server \
  -m ~/ds4/DeepSeek-V4.1-Flash-1017-Q2.gguf \
  --mtp-model ~/ds4/DeepSeek-V4.1-Flash-1017-DSpark-MXFP4.gguf \
  --dspark \
  --vision ~/ds4/DeepSeek-V4.1-Flash-1017-vision-BF16.gguf \
  --tensor-parallel --role coordinator \
  --listen 0.0.0.0 8081 --transport tcp \
  --ctx 262144 \
  --kv-disk-dir ~/.ds4/server-kv \
  --kv-disk-space-mb 8192 \
  --host 0.0.0.0 --port 8000
