---
name: llama-rocm-update
description: Обновление контейнера amd-strix-halo-toolboxes (ROCm) для llama-server на этой машине. Используй когда пользователь просит обновить контейнер llama-rocm / ROCm-образ / llama-server на новую версию: проверка актуального тега в Docker Hub, создание нового distrobox-контейнера, проверка работоспособности, правка и перезапуск systemd-юнита llama-server.service, удаление старого контейнера. Не касается ds4-кластера (это отдельный проект в ~/ds).
---
# Обновление llama-rocm-контейнера (llama-server)

Контейнер `llama-rocm-*` образ `docker.io/kyuz0/amd-strix-halo-toolboxes:<rocm-tag>`
запускает llama-server (router) как **user** systemd-юнит `llama-server.service`,
который автоматически стартует при логине (default.target).

> ⚠️ Это обновление **деструктивное**: создаётся новый контейнер, перезапускается
> сервис, старый контейнер удаляется. Перед стартом подтверждай у пользователя.
> Не трогай ds4-кластер (`llama-deepseek-cluster.service`, контейнер
> `ds4-multi-node-rocm-*`, образ `strix-halo-ds4-toolbox`) — это отдельный проект.

## Рабочий каталог

Сессии агента — `/home/nikita/models/config`. Скилл использует относительный путь
`scripts/` от себя.

## Быстрый запуск (готовые команды)

**Автоматический полный сценарий** (рекомендуется) — `scripts/update.sh` всё делает сам:
определяет текущий/новый тег, спрашивает подтверждения (кроме `--yes`), создаёт контейнер,
проверяет GPU и /health, патчит юнит, перезапускает сервис, удаляет старый контейнер:

```bash
scripts/update.sh                    # с подтверждениями
scripts/update.sh --yes rocm-10.0    # автоматически на конкретный тег
```

Хелперы для диагностики вручную:

```bash
scripts/current-tag.sh   # текущий тег из контейнера
scripts/latest-tag.sh    # новейший стабильный rocm-* тег из Docker Hub
```

Если теги совпали — `update.sh` сам сообщит «уже актуально» и остановится.
Ручной пошаговый сценарий — ниже, если нужно контролировать каждый шаг.

## Пошаговый workflow

### 1. Остановить сервис

```bash
systemctl --user stop llama-server.service
```

### 2. Создать новый контейнер

Имя контейнера = `llama-rocm-<newtag>` (совпадает с правилом из юнита), например
`llama-rocm-10.0`:

```bash
distrobox create llama-rocm-<newtag> \
  --image docker.io/kyuz0/amd-strix-halo-toolboxes:<newtag> \
  -- --device /dev/dri --device /dev/kfd --group-add video --group-add render --group-add sudo \
  --security-opt seccomp=unconfined
```

> `start_server.sh` и `models.ini` доступны внутри контейнера через монтирование
> `$HOME` в distrobox — ничего дополнительно монтировать не нужно.

### 3. Проверить, что работает

**a) GPU доступен в контейнере:**

```bash
distrobox enter llama-rocm-<newtag> -- llama-cli --list-devices
```

Должны быть видны AMD-устройства (gfx1151). Если `/dev/dri` не виден — см. `troubleshooting.md`.

**b) Сервер поднимается и отвечает:**

```bash
distrobox enter llama-rocm-<newtag> -- /home/nikita/models/config/start_server.sh
```

фоново, затем пинг health-эндпоинта:

```bash
curl -fsS http://127.0.0.1:8080/health
```

После проверки останови фоновый процесс (Ctrl-C / kill), чтобы не было конфликта порта.

### 4. Обновить systemd-юнит `llama-server.service`

Файл: `~/.config/systemd/user/llama-server.service`. Замени `<newtag>` в трёх местах:
`ExecStartPre` (имя контейнера + тег образа), `ExecStart` (имя контейнера), `ExecStop`
(имя контейнера). Текущее содержимое:

```ini
ExecStartPre=-/usr/bin/distrobox create --name llama-rocm-<tag> --image docker.io/kyuz0/amd-strix-halo-toolboxes:<tag> -- --device /dev/dri --device /dev/kfd --group-add video --group-add render --group-add sudo --security-opt seccomp=unconfined
ExecStart=/usr/bin/distrobox enter llama-rocm-<tag> -- /home/nikita/models/config/start_server.sh
ExecStop=/usr/bin/podman stop --time 10 llama-rocm-<tag>
```

Затем:

```bash
systemctl --user daemon-reload
systemctl --user enable --now llama-server.service
sleep 15 && systemctl --user status llama-server.service --no-pager
curl -fsS http://127.0.0.1:8080/health
```

### 5. Удалить старый контейнер

Только после того как новый сервис стабильно работает:

```bash
distrobox rm llama-rocm-<oldtag> --force
```

## Порядок окончательного подтверждения

1. Подтверди у пользователя новый тег до шага 2.
2. Подтверди удаление старого контейнера перед шагом 5.

## Нестандартные сценарии

Если образ не тянется, GPU не виден, сервис не стартует или старый контейнер не
удаляется — смотри `troubleshooting.md`.
