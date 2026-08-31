# Отладка обновления llama-rocm

## Контейнер не создаётся / distrobox create падает

- Проверь доступ к сети и Docker Hub:
  `curl -fsSI https://hub.docker.com/v2/repositories/kyuz0/amd-strix-halo-toolboxes/tags?page_size=1`
- Ошибка «already exists»: такой контейнер уже есть. Удали мешающий:
  `distrobox rm llama-rocm-<tag> --force`, затем повтори create.
- Нет прав на `/dev/kfd`/`/dev/dri` на хосте: проверь `ls -l /dev/kfd /dev/dri`.
- Юзер не в группах video/render: `groups`.

## В контейнере не видно GPU (llama-cli --list-devices пуст/ошибка)

- Проверь, что флаги переданы РАЗДЕЛИТЕЛЕМ `--`: 
  `distrobox create NAME --image IMG -- --device /dev/dri ...`
  Всё после `--` уходит в команду создания обычного контейнера (podman).
- Проверь передачу устройств: `distrobox enter NAME -- ls -l /dev/dri /dev/kfd`.
- На Strix Halo для ROCm обязателен `/dev/kfd` и `render` (см. README проекта-образов).

## Сервер не отвечает на /health после перезапуска

- Смотри лог юнита: `journalctl --user -u llama-server.service -n 50 --no-pager`.
- Проверь, что предыдущий ручной процесс сервера не держит порт 8080:
  `ss -ltnp | grep 8080` → убей лишний (`pkill -f start_server.sh`).
- health-эндпоинт: llama-server слушает `/health` на `--host 0.0.0.0 --port 8080`.

## Юнит обновился, но сервис крашится на старте

- Проверь, что в `ExecStartPre`/`ExecStart`/`ExecStop` имена контейнера совпадают
  с созданным: `grep -E 'Exec(Start|Stop)' ~/.config/systemd/user/llama-server.service`.
- `systemctl --user daemon-reload` обязателен после правки юнита.
- `distrobox enter <имя>` в юните подразумевает созданный контейнер с этим точным именем.

## Старый контейнер не удаляется

- Сначала убедись, что он остановлен: `distrobox stop llama-rocm-<old> --force`.
- Затем `distrobox rm llama-rocm-<old> --force`.
- Если podman жалуется на конфликт по имени: `podman rm -f llama-rocm-<old>`.

## Hidden apparmor/selinux на Ubuntu

- Ubuntu использует apparmor; distrobox-контейнеры создаются с
  `--security-opt seccomp=unconfined`. Если inference падает с причудливыми
  ошибками, проверь dmesg/jounal на блокировки: `dmesg | grep -i apparmor`.
