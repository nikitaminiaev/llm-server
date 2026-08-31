#!/usr/bin/env bash
# Печатает новейший стабильный rocm-* тег из Docker Hub.
# Фильтрует "чистые" теги без суффикса _<timestamp> (например rocm-10.0),
# сортирует по версии ROCm (X.Y.Z) и берёт максимальный.
set -euo pipefail

REPO="kyuz0/amd-strix-halo-toolboxes"
URL="https://hub.docker.com/v2/repositories/${REPO}/tags?page_size=100"

# Чистые stable RОCm-теги: rocm-<major>.<minor>[.<patch>] без временного суффикса
tags=$(curl -fsS "$URL" \
  | python3 -c '
import sys, json, re
d = json.load(sys.stdin)
names = [t["name"] for t in d.get("results", [])]
pat = re.compile(r"^rocm-(\d+)\.(\d+)(?:\.(\d+))?$")
stable = []
for n in names:
    m = pat.match(n)
    if m:
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        stable.append(((major, minor, patch), n))
stable.sort(key=lambda kv: kv[0])
if stable:
    print(stable[-1][1])
else:
    print("stable rocm-* тег не найден", file=sys.stderr)
    sys.exit(1)
')
echo "$tags"
