# WatchTogether — совместный просмотр

Веб-сервис: комната с ссылкой на видео (Rutube, YouTube, VK или прямой `.mp4`/`.m3u8`) и синхронизация воспроизведения по WebSocket (Django Channels).

## Стек

- **Backend:** Django 4.2, DRF, JWT, Channels, Daphne, Redis (опционально).
- **Frontend:** Vue 3, Vite, Pinia, Vue Router, Vuetify 3, Video.js, Axios.

## Запуск для разработки

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
.\.venv\Scripts\daphne.exe -b 127.0.0.1 -p 8000 config.asgi:application
```

Без `REDIS_URL` в `.env` используется **InMemoryChannelLayer** (достаточно для локальной проверки одним процессом).

### 2. Frontend

```powershell
cd frontend
npm install --legacy-peer-deps
npm run dev
```

Откройте **`http://127.0.0.1:5173`** (не `http://localhost:5173`, если браузер отдаёт ошибку **-102** / «соединение отклонено»: на Windows `localhost` часто идёт на IPv6, а dev-сервер слушает IPv4). Запросы к `/api` и `/ws` проксируются на `http://127.0.0.1:8000`.

### Учётная запись

Зарегистрируйтесь на главной странице, затем создайте комнату с поддерживаемой ссылкой. Просмотр комнаты по URL `/room/<slug>` доступен без входа (по ссылке).

## Продакшен

- Задайте `DJANGO_DEBUG=false`, надёжный `DJANGO_SECRET_KEY`, `REDIS_URL` для Channels.
- Соберите фронт: `cd frontend && npm run build`, раздавайте `dist` через nginx/caddy или WhiteNoise.
- `psycopg2-binary` установите при необходимости PostgreSQL (на Windows нужны подходящие колёса под версию Python).

## Docker

Конфигурация контейнеров не включена в репозиторий; при переносе в Docker обычно поднимают сервисы `web` (Daphne), `redis`, `postgres` и фронт как статику или отдельный образ.
