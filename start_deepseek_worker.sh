#!/bin/bash

# SWA bounded replay — ускорение prefill длинных промптов (README весов 1017)
export DS4_ENABLE_V41_DECODER_SWA_BOUNDED_REPLAY=1

# V4.1 Flash: TP-воркер запускается бинарём ds4 (не ds4-server)
ds4 \
  -m ~/ds4/DeepSeek-V4.1-Flash-1017-Q2.gguf \
  --mtp-model ~/ds4/DeepSeek-V4.1-Flash-1017-DSpark-MXFP4.gguf \
  --dspark \
  --vision ~/ds4/DeepSeek-V4.1-Flash-1017-vision-BF16.gguf \
  --tensor-parallel --role worker \
  --coordinator 192.168.1.1 8081 --transport tcp \
  --ctx 262144
