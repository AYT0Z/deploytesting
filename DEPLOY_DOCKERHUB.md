# Деплой на VPS через Docker Hub (без build на сервере)

Ниже готовый сценарий: собираешь образы у себя, пушишь в Docker Hub, на VPS только `pull + up`.

## 1) Подготовка Docker Hub

Создай (или используй существующий) аккаунт Docker Hub:

- `watchtogether-backend`
- `watchtogether-frontend`

Можно private или public, но если private — на VPS нужен `docker login`.

## 2) Сборка и push образов (локально)

Из корня проекта:

```bash
docker login
docker build -t <DOCKERHUB_USER>/watchtogether-backend:latest ./backend
docker build -t <DOCKERHUB_USER>/watchtogether-frontend:latest ./frontend
docker push <DOCKERHUB_USER>/watchtogether-backend:latest
docker push <DOCKERHUB_USER>/watchtogether-frontend:latest
```

Пример с версией:

```bash
docker build -t <DOCKERHUB_USER>/watchtogether-backend:v1 ./backend
docker build -t <DOCKERHUB_USER>/watchtogether-frontend:v1 ./frontend
docker push <DOCKERHUB_USER>/watchtogether-backend:v1
docker push <DOCKERHUB_USER>/watchtogether-frontend:v1
```

## 3) Копирование файлов на VPS

На VPS нужна папка проекта, например `/opt/watchtogether`.

Минимально необходимые файлы на VPS:

- `docker-compose.hub.yml`
- `.env` (создаётся из `.env.hub.example`)

Передай файлы на VPS любым способом (`scp`, `rsync`, git).

## 4) Настройка `.env` на VPS

На VPS:

```bash
cd /opt/watchtogether
cp .env.hub.example .env
nano .env
```

Обязательно измени:

- `DOCKERHUB_USER`
- `IMAGE_TAG` (`latest` или версия, например `v1`)
- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `DJANGO_ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`

## 5) Запуск на VPS

```bash
cd /opt/watchtogether
docker login            # если образы private
docker compose --env-file .env -f docker-compose.hub.yml pull
docker compose --env-file .env -f docker-compose.hub.yml up -d
```

Проверка:

```bash
docker compose -f docker-compose.hub.yml ps
docker compose -f docker-compose.hub.yml logs -f backend
docker compose -f docker-compose.hub.yml logs -f frontend
```

## 6) Открытие сайта

- Если `APP_PORT=80`: `http://<VPS_IP>`
- Если `APP_PORT=8080`: `http://<VPS_IP>:8080`
- Если домен уже направлен на VPS: `http://<ваш-домен>`

## 7) Обновление проекта (новая версия)

Локально:

```bash
docker build -t <DOCKERHUB_USER>/watchtogether-backend:v2 ./backend
docker build -t <DOCKERHUB_USER>/watchtogether-frontend:v2 ./frontend
docker push <DOCKERHUB_USER>/watchtogether-backend:v2
docker push <DOCKERHUB_USER>/watchtogether-frontend:v2
```

На VPS:

1. поменяй `IMAGE_TAG=v2` в `.env`
2. выполни:

```bash
docker compose --env-file .env -f docker-compose.hub.yml pull
docker compose --env-file .env -f docker-compose.hub.yml up -d
```

## 8) Вариант: Nginx на VPS (host-level)

Если хочешь, чтобы Nginx был установлен прямо на VPS, используй:

- `docker-compose.host-nginx.yml`
- `deploy/nginx/watchtogether.conf`
- `.env.host-nginx.example`

Схема:

- Docker фронт доступен только локально: `127.0.0.1:8080`
- Nginx на VPS слушает `:80` и проксирует в `127.0.0.1:8080`

Команды:

```bash
cp .env.host-nginx.example .env
nano .env
docker compose --env-file .env -f docker-compose.host-nginx.yml pull
docker compose --env-file .env -f docker-compose.host-nginx.yml up -d
```

Установка Nginx на VPS:

```bash
sudo apt update && sudo apt install -y nginx
sudo cp deploy/nginx/watchtogether.conf /etc/nginx/sites-available/watchtogether
sudo ln -sf /etc/nginx/sites-available/watchtogether /etc/nginx/sites-enabled/watchtogether
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```
