# Деплой на VPS (Ubuntu 22.04 / 24.04, Debian 12)

Бот ставится в `/opt/reportbot`. Входящие порты ему не нужны: он сам опрашивает Telegram,
а Postgres доступен только внутри Docker-сети.

Все команды выполняются от root (или через `sudo`).

## 1. Подготовка сервера

```bash
apt update && apt upgrade -y
apt install -y git curl ca-certificates
```

Swap на 2 ГБ (обязательно для 1 ГБ RAM, желательно и для 2 ГБ):

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Файрвол — оставляем только SSH:

```bash
ufw allow OpenSSH && ufw --force enable
```

## 2. Docker

Официальный скрипт установки Docker Engine + Compose plugin:

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker compose version
```

## 3. Код

```bash
git clone https://github.com/Query-dev-ux/ReportBot.git /opt/reportbot
cd /opt/reportbot
```

Если репозиторий приватный — клонируйте с
[Personal Access Token](https://github.com/settings/tokens) (права `Contents: Read`)
или добавьте на сервер deploy key.

## 4. Настройки

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Обязательно поменять:

| Переменная | Что указать |
|---|---|
| `BOT_TOKEN` | токен от @BotFather |
| `ADMIN_KEY` | длинный случайный ключ, например из `openssl rand -hex 16` |
| `POSTGRES_PASSWORD` | случайный пароль, например из `openssl rand -hex 16` |

`POSTGRES_PASSWORD` задается **до первого запуска**: Postgres применяет его только при
создании базы. Чтобы сменить пароль потом, его нужно менять и в базе (`ALTER USER`).

## 5. Запуск

```bash
chmod +x scripts/*.sh
docker compose up -d --build
docker compose logs -f bot
```

В логах должно появиться `Start polling`. Выход из логов — `Ctrl+C`, бот продолжит работать.

Контейнеры с `restart: unless-stopped` сами поднимаются после перезагрузки сервера.

## 6. Бэкапы

Ежедневный бэкап в 03:00, хранятся 14 дней в `/opt/reportbot/backups`:

```bash
(crontab -l 2>/dev/null; echo '0 3 * * * /opt/reportbot/scripts/backup.sh >> /var/log/reportbot-backup.log 2>&1') | crontab -
```

Проверить вручную: `/opt/reportbot/scripts/backup.sh`.

Бэкапы лежат на том же сервере — периодически копируйте их к себе:

```bash
scp root@SERVER_IP:/opt/reportbot/backups/*.sql.gz ./
```

Восстановление: `/opt/reportbot/scripts/restore.sh backups/reportbot_YYYY-MM-DD_HH-MM.sql.gz`.

## Обновление

После пуша в `main`:

```bash
/opt/reportbot/scripts/deploy.sh
```

## Полезные команды

```bash
cd /opt/reportbot
docker compose ps                 # статус
docker compose logs -f --tail 100 bot
docker compose restart bot        # перезапуск
docker compose up -d bot          # применить изменения .env (restart их не подхватывает)
docker compose down               # остановить (данные БД сохраняются)
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'   # консоль БД
free -h && df -h                  # память и диск
```
