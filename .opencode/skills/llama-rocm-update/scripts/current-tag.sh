#!/usr/bin/env bash
# Печатает текущий ROCm-тег из llama-rocm-* контейнера.
# Пример вывода: rocm-7.2.4 (или код 1, если контейнера нет).
set -uo pipefail

# Без раннего exit в awk: ранний выход из конвейера рождает SIGPIPE (141)
# у distrobox list при включённом pipefail. Здесь обрабатываем весь вывод.
image=$(distrobox list 2>/dev/null | awk -F'|' '$2 ~ /llama-rocm-/ {gsub(/ /,"",$4); last=$4} END {print last}')

if [ -z "${image:-}" ]; then
  echo "llama-rocm-* контейнер не найден (не создан или не запущен)" >&2
  exit 1
fi

tag=$(echo "${image}" | sed -E 's/.*amd-strix-halo-toolboxes:(rocm-[0-9][^ ]*).*/\1/')
echo "${tag}"
