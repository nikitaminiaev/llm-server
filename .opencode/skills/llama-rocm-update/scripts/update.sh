#!/usr/bin/env bash
# Полное обновление llama-rocm-контейнера и службы llama-server.service.
#
# Использование:
#   update.sh                    # спросит текущий/новый тег, подтверждения
#   update.sh --yes              # без подтверждений (автоматически)
#   update.sh 10.0               # конкретный ROCm-номер (можно rocm-10.0)
#   update.sh --yes 10.0
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="$HOME/.config/systemd/user/llama-server.service"
IMAGE_PREFIX="docker.io/kyuz0/amd-strix-halo-toolboxes"
YES=0
NEW_NUM=""

for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    *) NEW_NUM="${a#rocm-}" ;;
  esac
done

confirm() {
  if [ "$YES" -eq 1 ]; then return 0; fi
  read -r -p "$1 [y/N] " ans </dev/tty
  [[ "$ans" =~ ^[YyДд] ]]
}

fail() { echo "ОШИБКА: $*" >&2; exit 1; }

[ -f "$SERVICE" ] || fail "не найден юнит: $SERVICE"

# Текущий контейнер берём из юнита (имя с префиксом llama-rocm-)
OLD_CONTAINER=$(grep -oE 'llama-rocm-[0-9.]+' "$SERVICE" | head -1)
[ -n "$OLD_CONTAINER" ] || fail "не смог определить текущий контейнер из юнита"
OLD_NUM="${OLD_CONTAINER#llama-rocm-}"
echo "Текущий контейнер: $OLD_CONTAINER (ROCm: $OLD_NUM)"

if [ -z "$NEW_NUM" ]; then
  LATEST=$("$SCRIPT_DIR/latest-tag.sh") || fail "не смог получить актуальный тег"
  NEW_NUM="${LATEST#rocm-}"
fi
NEW_CONTAINER="llama-rocm-${NEW_NUM}"
NEW_IMAGE_TAG="rocm-${NEW_NUM}"
echo "Новый контейнер:  $NEW_CONTAINER (образ: ${IMAGE_PREFIX}:${NEW_IMAGE_TAG})"

if [ "$OLD_NUM" = "$NEW_NUM" ]; then
  echo "Уже актуально: ROCm $NEW_NUM совпадает с текущим. Обновление не требуется."
  exit 0
fi

confirm "Создать новый distrobox-контейнер ${NEW_CONTAINER} (образ :${NEW_IMAGE_TAG})?" || exit 0

echo ">> Стоп сервиса llama-server.service"
systemctl --user stop llama-server.service

echo ">> Pull образа ${IMAGE_PREFIX}:${NEW_IMAGE_TAG}"
podman pull "${IMAGE_PREFIX}:${NEW_IMAGE_TAG}" || fail "podman pull не удался"

echo ">> Создание контейнера ${NEW_CONTAINER}"
distrobox create "$NEW_CONTAINER" \
  --image "${IMAGE_PREFIX}:${NEW_IMAGE_TAG}" \
  -- --device /dev/dri --device /dev/kfd --group-add video --group-add render --group-add sudo \
  --security-opt seccomp=unconfined || fail "distrobox create не удался"

echo ">> Проверка GPU в контейнере"
distrobox enter "$NEW_CONTAINER" -- llama-cli --list-devices || fail "llama-cli --list-devices не показал устройства"

echo ">> Запуск сервера для проверки"
distrobox enter "$NEW_CONTAINER" -- /home/nikita/models/config/start_server.sh >/tmp/llama-rocm-update-server.log 2>&1 &
sleep 20
if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then
  echo ">> /health OK"
else
  echo ">> /health не ответил за 20с, лог:" >&2
  tail -30 /tmp/llama-rocm-update-server.log >&2
  pkill -f "llama-rocm-${NEW_NUM}.*start_server.sh" 2>/dev/null
  fail "сервер в новом контейнере не отвечает"
fi

# Остановка тестового сервера: podman stop контейнера гарантированно убивает
# и фоновый podman exec, и llama-server внутри (иначе порт 8080 остаётся занят).
pkill -f "llama-rocm-${NEW_NUM}.*start_server.sh" 2>/dev/null
podman stop --time 5 "$NEW_CONTAINER" 2>/dev/null || true
sleep 3
# Юнит сам поднимет контейнер и сервер на шаге enable --now.

confirm "Обновить юнит $SERVICE и перезапустить его?" || exit 0

echo ">> Патчим юнит (${OLD_CONTAINER} -> ${NEW_CONTAINER}, :rocm-${OLD_NUM} -> :${NEW_IMAGE_TAG})"
# Разделитель # (не /): в путях образа есть слэши docker.io/kyuz0/...
# Заменяем только имя контейнера и ТЕГ образа, не трогая префикс registry:
sed -i \
  -e "s#llama-rocm-${OLD_NUM}#${NEW_CONTAINER}#g" \
  -e "s#toolboxes:rocm-${OLD_NUM}#toolboxes:rocm-${NEW_NUM}#g" \
  "$SERVICE"

systemctl --user daemon-reload
systemctl --user enable --now llama-server.service
sleep 15
systemctl --user status llama-server.service --no-pager | head -20
curl -fsS http://127.0.0.1:8080/health && echo "OK" || fail "сервис после перезапуска не ответил"

confirm "Удалить старый контейнер ${OLD_CONTAINER}?" || { echo "Старый контейнер оставлен."; exit 0; }
distrobox rm "$OLD_CONTAINER" --force
echo "Готово."
