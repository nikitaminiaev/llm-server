#!/bin/bash

MODEL_DIR=~/models/Qwen3.8-Flash-Next

llama-server \
  -m "$MODEL_DIR/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf" \
  --mmproj "$MODEL_DIR/mmproj-BF16.gguf" --mmproj-device ROCm0 \
  -dev ROCm0 -ngl all \
  -fa on -fit off --load-mode none --lazy-mode on-direct \
  -ctk f16 -ctv f16 \
  -c 262144 -b 16384 -ub 16384 --parallel 1 --jinja \
  --host 0.0.0.0 --port 8081 \
  --spec-type draft-mtp,ngram-mod --spec-draft-n-max 3 \
  --spec-draft-model "$MODEL_DIR/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf" \
  --spec-draft-device ROCm0 --spec-draft-ngl all \
  --sleep-idle-seconds 3600
