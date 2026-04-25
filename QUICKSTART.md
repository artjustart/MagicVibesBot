# 🚀 Быстрый старт

## Пошаговая инструкция для запуска бота

### 1. Предварительные требования
- Python 3.11+
- PostgreSQL 14+
- Git

### 2. Получите токен бота
1. Откройте Telegram
2. Найдите @BotFather
3. Отправьте `/newbot`
4. Введите название: `Magic Vibes Bot`
5. Введите username: `magic_vibes_bot` (или любой другой доступный)
6. **Скопируйте токен** (формат: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 3. Настройте PostgreSQL

#### Linux/Mac:
```bash
# Установка PostgreSQL (если еще не установлен)
# Ubuntu/Debian:
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib

# Mac (Homebrew):
brew install postgresql
brew services start postgresql

# Создание пользователя и БД
sudo -u postgres psql

# В psql:
CREATE DATABASE magic_vibes_bot;
CREATE USER magic_vibes WITH PASSWORD 'secure_password_123';
GRANT ALL PRIVILEGES ON DATABASE magic_vibes_bot TO magic_vibes;
\q
```

#### Windows:
```
1. Скачайте PostgreSQL: https://www.postgresql.org/download/windows/
2. Установите PostgreSQL
3. Откройте pgAdmin
4. Создайте БД: magic_vibes_bot
5. Создайте пользователя: magic_vibes
```

### 4. Клонирование и установка

```bash
# Клонируйте репозиторий
git clone <your-repo-url>
cd magic_vibes_bot

# Создайте виртуальное окружение
python -m venv venv

# Активируйте окружение
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Установите зависимости
pip install -r requirements.txt
```

### 5. Настройка переменных окружения

```bash
# Скопируйте пример
cp .env.example .env

# Откройте .env в редакторе
nano .env  # или любой другой редактор
```

Заполните значения:
```env
# Ваш токен от @BotFather
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Ваш Telegram ID (узнайте у @userinfobot)
ADMIN_IDS=123456789

# Настройки БД
DB_HOST=localhost
DB_PORT=5432
DB_USER=magic_vibes
DB_PASSWORD=secure_password_123
DB_NAME=magic_vibes_bot

# MonoPay (временно можно оставить пустым для тестов)
MONOPAY_TOKEN=test_token
MONOPAY_MERCHANT_ID=test_merchant
```

### 6. Инициализация базы данных

```bash
# Создайте таблицы и тестовые данные
python init_db.py
```

Вы должны увидеть:
```
✅ База данных успешно инициализирована!
✅ Создано практик: 3
✅ Создано курсов: 2
✅ Создано расписаний: 10
✅ Создано менеджеров: 1
```

### 7. Запуск бота

```bash
python main.py
```

Вы должны увидеть:
```
INFO - Bot starting...
INFO - Starting polling...
```

### 8. Тестирование

1. Откройте Telegram
2. Найдите вашего бота по username
3. Отправьте `/start`
4. Вы должны увидеть главное меню с кнопками

### 9. Проверка функционала

#### Тест 1: Запись на практику
1. Нажмите "📅 Актуальные практики"
2. Выберите "Утренняя йога"
3. Выберите дату
4. Подтвердите бронирование
5. Перейдите к оплате (пока тестовая)

#### Тест 2: Индивидуальная сессия
1. Нажмите "🧘‍♀️ Индивидуальная сессия"
2. Нажмите "📅 Выбрать дату и время"
3. Введите: `01.01.2025 15:00`
4. Проверьте создание запроса

#### Тест 3: Курсы
1. Нажмите "🎓 Стартовый онлайн-курс"
2. Нажмите "✅ Записаться на курс"
3. Проверьте создание записи

## ⚙️ Настройка MonoPay (для реальных платежей)

### Получение токенов:

1. **Регистрация в MonoPay**
   - Перейдите: https://www.monobank.ua/
   - Создайте бизнес-аккаунт
   - Подайте заявку на подключение платежей

2. **Получите токены**
   - В личном кабинете: Настройки → API
   - Скопируйте Token
   - Скопируйте Merchant ID

3. **Обновите .env**
   ```env
   MONOPAY_TOKEN=ваш_настоящий_токен
   MONOPAY_MERCHANT_ID=ваш_merchant_id
   ```

4. **Настройте Webhook**
   - Вам нужен публичный HTTPS домен
   - URL: `https://your-domain.com/webhook/monopay`
   - См. раздел "Деплой" ниже

## 🌐 Деплой на сервер (опционально)

### Вариант 1: VPS (DigitalOcean, Hetzner, etc.)

```bash
# На сервере
git clone <your-repo>
cd magic_vibes_bot

# Установите зависимости
pip install -r requirements.txt

# Настройте .env

# Инициализируйте БД
python init_db.py

# Запустите через systemd
sudo nano /etc/systemd/system/magicvibes-bot.service
```

Содержимое service файла:
```ini
[Unit]
Description=Magic Vibes Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/magic_vibes_bot
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Запустите сервис
sudo systemctl daemon-reload
sudo systemctl enable magicvibes-bot
sudo systemctl start magicvibes-bot

# Проверьте статус
sudo systemctl status magicvibes-bot
```

### Вариант 2: Docker

```bash
# Запустите через Docker Compose
docker-compose up -d

# Просмотр логов
docker-compose logs -f bot
```

## 🐛 Решение проблем

### Проблема: "Database connection failed"
**Решение:**
```bash
# Проверьте, запущен ли PostgreSQL
sudo systemctl status postgresql

# Проверьте подключение
psql -U magic_vibes -d magic_vibes_bot -h localhost
```

### Проблема: "Module not found"
**Решение:**
```bash
# Переустановите зависимости
pip install --upgrade -r requirements.txt
```

### Проблема: "Bot doesn't respond"
**Решение:**
```bash
# Проверьте логи
python main.py

# Проверьте токен бота
# Отправьте запрос:
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

### Проблема: "Payment failed"
**Решение:**
- Убедитесь, что токены MonoPay корректные
- Проверьте, что webhook URL доступен
- Используйте тестовые данные для отладки

## 📞 Получить помощь

Если что-то не работает:
1. Проверьте логи: `python main.py`
2. Убедитесь, что все переменные окружения заполнены
3. Проверьте подключение к БД
4. Создайте Issue в репозитории

## ✅ Чеклист перед запуском

- [ ] Python 3.11+ установлен
- [ ] PostgreSQL установлен и запущен
- [ ] База данных создана
- [ ] Виртуальное окружение активировано
- [ ] Зависимости установлены (`pip install -r requirements.txt`)
- [ ] Файл .env настроен с правильными значениями
- [ ] `python init_db.py` выполнен успешно
- [ ] Бот запущен (`python main.py`)
- [ ] Тестовое сообщение `/start` работает

Если все пункты выполнены - поздравляем! Ваш бот готов к работе! 🎉
