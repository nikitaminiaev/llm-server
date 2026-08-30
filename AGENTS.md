# Модельный сервер на Strix Halo (llama-server router)

Конфигурация llama-server (router с несколькими моделями) на хосте
Nikita MS-S1-MAX (Ubuntu, Ryzen AI MAX / AMD iGPU, без дискретной GPU).

## Назначение репо

Репозиторий содержит конфиг и скрипты для локального LLM-сервера,
который работает **внутри distrobox-контейнера** `llama-rocm-*`
(образ `kyuz0/amd-strix-halo-toolboxes:<rocm-tag>`), запускается как
**user** systemd-юнит `llama-server.service` и авто-стартует при логине.

Файлы:

- `models.ini` — пресеты моделей для режима роутера llama-server
  (`llama-server --models-preset`). Модели лежат на хосте в `~/models/...`
  и видны в контейнере через монтирование `$HOME` (distrobox).
- `start_server.sh` — команда запуска llama-server в режиме роутера
  (`--models-preset ~/models/config/models.ini --port 8080`).
- `start_deepseek_cluster.sh` / `start_deepseek_worker.sh` — кластер DeepSeek
  (ds4-server), **отдельный проект** (образ `strix-halo-ds4-toolbox`,
  юнит `llama-deepseek-cluster.service`, disabled, запускается руками).
- `idle_watchdog.py` / `llama-watcher.service` — сторож простоя: рестартует
  `llama-server.service`, когда модели загружены только в VRAM и iGPU простаивает.

## Ключевые юниты (systemd --user)

| Юнит | Источник | Статус | Что делает |
|------|----------|--------|-----------|
| `llama-server.service` | контейнер `llama-rocm-*` | enabled (авто-старт) | llama-server router :8080 |
| `llama-watcher.service` | python `idle_watchdog.py` | enabled | сторож простоя, рестартует сервер |
| `llama-deepseek-cluster.service` | контейнер `ds4-multi-node-rocm-*` | disabled (руками) | ds4 кластер coordinator |

Файлы юнитов: `~/.config/systemd/user/`. Перезапуск сервиса:
`systemctl --user restart llama-server.service`.

## Обновление контейнера llama-rocm

Если в `kyuz0/amd-strix-halo-toolboxes` вышел более свежий стабильный ROCm-тег
(например текущий `rocm-7.2.4` → `rocm-10.0`), контейнер и юнит можно обновить.

**Используй скилл `llama-rocm-update`** (`.opencode/skills/llama-rocm-update/`).
Он определяет актуальный тег, создаёт новый distrobox-контейнер, проверяет GPU и
`/health`, патчит `llama-server.service`, перезапускает и удаляет старый контейнер:

```bash
.opencode/skills/llama-rocm-update/scripts/update.sh
```

Не затрагивай кластер DeepSeek при этом обновлении — это отдельный проект (~/ds).

## Правила работы

- Контейнер/модели не клонировать: обновление контейнера только через скилл
  `llama-rocm-update` по описанному выше алгоритму.
- После правки `models.ini` достаточно `systemctl --user restart llama-server.service`.
- Репо моделирующего сервера `~/ds` — вне этого репо.
