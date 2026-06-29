# Photo28 Bot — Telegram бот для приёма заказов фотопечати

Telegram бот для приёма заказов фотопечати с веб-админкой для управления заказами.

## 🚀 Возможности

### Бот
- 📷 Приём фотографий в 4 форматах (Полароид, Инстакс, Классика)
- 📱 Поддержка загрузки без сжатия (файлами)
- 💰 Автоматический расчёт стоимости с прогрессивной шкалой
- 🎟 Система промокодов
- 🚚 Выбор доставки (ОЗОН, курьер, самовывоз)
- 💳 Приём оплаты переводом с подтверждением квитанцией
- 📋 Просмотр истории заказов

### Админ-панель
- 📊 Дашборд со статистикой
- 📋 Управление заказами и статусами
- 📥 Скачивание фото из Telegram
- ☁️ Выгрузка на Яндекс.Диск
- 🎟 Управление промокодами

## 📁 Структура проекта

```
photo28/
├── main.py              # Точка входа бота
├── admin.py             # Точка входа админки
├── requirements.txt     # Зависимости Python
├── env.example          # Пример .env файла
├── src/
│   ├── config.py        # Конфигурация
│   ├── database.py      # Подключение к БД
│   ├── bot/
│   │   ├── handlers/    # Обработчики команд
│   │   ├── keyboards/   # Клавиатуры
│   │   └── states/      # FSM состояния
│   ├── models/          # Модели данных
│   ├── services/        # Бизнес-логика
│   └── admin/           # Веб-админка
│       ├── app.py
│       ├── templates/
│       └── static/
└── storage/
    ├── photos/          # Скачанные фото
    └── bot.db           # SQLite база данных
```

## 🛠 Установка

### 1. Создание бота в Telegram

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Введите имя бота (например: `Photo28 Заказы`)
4. Введите username бота (например: `photo28_order_bot`)
5. Сохраните полученный токен

### 2. Настройка сервера (Timeweb Cloud / Ubuntu)

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python 3.11+
sudo apt install -y python3.11 python3.11-venv python3-pip

# Создание пользователя для бота (опционально)
sudo useradd -m -s /bin/bash photo28bot
sudo su - photo28bot

# Клонирование проекта
cd ~
git clone <your-repo-url> photo28
cd photo28

# Создание виртуального окружения
python3.11 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Конфигурация

```bash
# Копируем пример конфигурации
cp env.example .env

# Редактируем настройки
nano .env
```

Обязательные параметры в `.env`:
```env
BOT_TOKEN=1234567890:AABBccDDeeFFggHHiiJJkkLLmmNNooP

# Для Яндекс.Диска (опционально)
YANDEX_DISK_TOKEN=your_token

# Для админки
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
ADMIN_SECRET_KEY=random_string_for_sessions
```

### 4. Инициализация базы данных

```bash
source venv/bin/activate
python3 -c "
import asyncio
from src.database import init_db
asyncio.run(init_db())
print('База данных создана!')
"
```

### 5. Запуск

#### Запуск бота (webhook-режим)

`main.py` запускает aiohttp-сервер на порту `WEBHOOK_PORT` (по умолчанию 8081).
При старте автоматически выставляются вебхуки для каждой студии из реестра
через `lifecycle.startup` — вручную вызывать `setWebhook` не нужно.

```bash
source venv/bin/activate
python main.py
```

#### Запуск админки
```bash
source venv/bin/activate
python admin.py
```

Админка будет доступна на http://server-ip:8080

## 🔧 Настройка как systemd сервис

### Бот
Создайте файл `/etc/systemd/system/photo28-bot.service`:

```ini
[Unit]
Description=Photo28 Telegram Bot (webhook)
After=network.target

[Service]
User=photo28bot
WorkingDirectory=/home/photo28bot/photo28
Environment="PATH=/home/photo28bot/photo28/venv/bin"
ExecStart=/home/photo28bot/photo28/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Админка
Создайте файл `/etc/systemd/system/photo28-admin.service`:

```ini
[Unit]
Description=Photo28 Admin Panel
After=network.target

[Service]
User=photo28bot
WorkingDirectory=/home/photo28bot/photo28
Environment="PATH=/home/photo28bot/photo28/venv/bin"
ExecStart=/home/photo28bot/photo28/venv/bin/uvicorn src.admin.app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Управление сервисами
```bash
# Запуск
sudo systemctl start photo28-bot
sudo systemctl start photo28-admin

# Автозапуск при загрузке
sudo systemctl enable photo28-bot
sudo systemctl enable photo28-admin

# Просмотр логов
sudo journalctl -u photo28-bot -f
sudo journalctl -u photo28-admin -f

# Перезапуск
sudo systemctl restart photo28-bot
```

## 🔒 nginx: проксирование webhook и админки

Бот работает через webhook: nginx принимает HTTPS-запросы от Telegram и перенаправляет
их на локальный aiohttp-сервер (`WEBHOOK_PORT`, по умолчанию 8081).

```nginx
# Боты (webhook)
server {
    listen 443 ssl;
    server_name bots.example.com;

    # SSL-сертификат (например, Let's Encrypt)
    ssl_certificate     /etc/letsencrypt/live/bots.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bots.example.com/privkey.pem;

    # Telegram шлёт обновления сюда (per-studio URL: /webhook/{secret})
    location /webhook/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Health-check (используется мониторингом)
    location /healthz {
        proxy_pass http://127.0.0.1:8081;
    }
}

# Админка
server {
    listen 443 ssl;
    server_name admin.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/admin.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Обязательные переменные в `.env` для webhook-режима:
```env
BASE_WEBHOOK_URL=https://bots.example.com   # публичный URL без trailing slash
WEBHOOK_PORT=8081                            # порт aiohttp-сервера (localhost)
```

## ☁️ Интеграция с Яндекс.Диском

### Получение OAuth токена

1. Перейдите на https://oauth.yandex.ru/
2. Создайте приложение с правами на Яндекс.Диск
3. Получите OAuth токен
4. Добавьте в `.env`:
   ```
   YANDEX_DISK_TOKEN=your_token_here
   ```

### Структура на Яндекс.Диске

```
Photo28_Orders/
├── 2024-01/
│   ├── 240115-ABCD/
│   │   ├── 240115-ABCD_polaroid_standard_001.jpg
│   │   ├── 240115-ABCD_polaroid_standard_002.jpg
│   │   └── ...
│   └── 240116-EFGH/
│       └── ...
└── 2024-02/
    └── ...
```

## 📝 Workflow печати

1. **Клиент оформляет заказ** через бота
2. **Заказ появляется в админке** со статусом "Оплачен"
3. **Менеджер скачивает фото** кнопкой "Скачать фото"
4. **Фото сохраняются** в `storage/photos/{order_number}/`
5. **Менеджер печатает** фото из папки
6. **После печати** — загрузка на Яндекс.Диск (опционально)
7. **Смена статуса** на "Отправлен" уведомляет клиента

## 💰 Расчёт стоимости

### Классика 10×15
- 25₽ за штуку

### Полароид / Инстакс
Прогрессивная шкала:
| Количество | Стоимость |
|------------|-----------|
| 1-27 шт.   | 22₽/шт.   |
| 28 шт.     | 560₽      |
| 50 шт.     | 950₽      |
| 100 шт.    | 1900₽     |
| 150 шт.    | 2850₽     |
| 200 шт.    | 3800₽     |

## 🧪 Тестирование

1. Найдите бота в Telegram по username
2. Отправьте `/start`
3. Выберите формат, загрузите 10+ фото
4. Пройдите весь процесс заказа
5. Проверьте заказ в админке

## 📞 Поддержка

При возникновении проблем проверьте:
1. Логи бота: `journalctl -u photo28-bot -f`
2. Наличие токена бота в `.env`
3. Права на директорию `storage/`

