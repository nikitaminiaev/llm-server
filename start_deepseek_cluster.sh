#!/bin/bash

ds4-server \
  -m ~/ds4/DeepSeek-V4-Flash-Q4KExperts-F16HC-F16Compressor-F16Indexer-Q8Attn-Q8Shared-Q8Out-chat-v2-imatrix-0731.gguf \
  --mtp ~/ds4/DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf \
  --mtp-draft 1 \
  --role coordinator \
  --layers 0:21 \
  --listen 0.0.0.0 8081 \
  --ctx 262144 \
  --kv-disk-dir ~/.ds4/server-kv \
  --kv-disk-space-mb 8192 \
  --host 0.0.0.0 --port 8000
