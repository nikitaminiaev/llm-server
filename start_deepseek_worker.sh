#!/bin/bash

ds4-server \
  -m ~/ds4/DeepSeek-V4-Flash-Q4KExperts-F16HC-F16Compressor-F16Indexer-Q8Attn-Q8Shared-Q8Out-chat-v2-imatrix-0731.gguf \
  --role worker \
  --layers 22:output \
  --coordinator 192.168.1.1 8081 \
  --ctx 262144
