# AnnA - Мессенджер/Социальная сеть

#Описание

Anna - это пет-проект социальной сети с функционалом чата в реальном времени, написанный с использованием микросервисной архитектуры. Проект включает backend на FastAPI, WebSocket для мгновенного обмена сообщениями, а также хранение медиафайлов.

# Стек технологий

- Python 3.11
- FastAPI  
- PostgreSQL + asyncpg  
- Redis (для кэширования и очередей)  
- MinIO (для хранения медиафайлов)  
- JWT авторизация
- Docker & Docker Compose  
- pytest для тестирования  

# Установка и запуск локально

## 1. Клонирование репозитория

git clone https://github.com/H1TgH/AnnA_Social_Site_Pet.git
cd AnnA_Social_Site_Pet

## 2. Создание .env файла

Создайте файл `.env` в корне проекта и заполните его своими данными (замените все <...> на свои локальные или тестовые значения.):

# URL вашей базы данных PostgreSQL
DATABASE_URL=postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:<DB_PORT>/<DB_NAME>

# Секретный ключ для JWT
SECRET_KEY=<YOUR_SECRET_KEY>

# URL фронтенда (например, для CORS)
FRONTEND_URL=http://localhost:3000

# Настройки SMTP для отправки писем
SMTP_HOST=<SMTP_HOST>
SMTP_PORT=<SMTP_PORT>
SMTP_USER=<SMTP_USER>
SMTP_PASSWORD=<SMTP_PASSWORD>
SMTP_FROM=<SENDER_NAME> <SMTP_USER>

# Redis (для статуса пользователей и очередей)
REDIS_URL=redis://<REDIS_HOST>:<REDIS_PORT>

# MinIO (для хранения медиафайлов)
MINIO_ACCESS_KEY=<MINIO_ACCESS_KEY>
MINIO_SECRET_KEY=<MINIO_SECRET_KEY>

## 3. Запуск бэкенда

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
docker-compose up --build

# Выполненный функционал

## Регистрация и авторизация пользователей (JWT + email подтверждение)
## CRUD операции с чатами, сообщениями и постами
## WebSocket чат в реальном времени
## Редактирование и удаление сообщений
## Создание постов с различным наполнением
## Загрузка и хранение медиафайлов через MinIO
## Поиск пользователей и фльтрация результатов поиска