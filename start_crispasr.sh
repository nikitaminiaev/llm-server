#!/bin/bash
exec /home/nikita/models/crispasr --server \
    -m /home/nikita/models/parakeet-tdt-0.6b-v3-q8_0.gguf \
    --host 0.0.0.0 --port 8081
