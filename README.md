# Magic Vibes Telegram Bot

Телеграм-бот для компании Magic Vibes с функциями записи на практики, индивидуальные сессии, продажи курсов и приема платежей через MonoPay.

## 🎯 Функционал

### Для клиентов:
- 📅 **Актуальные практики** - просмотр расписания и запись на групповые практики
- 🧘‍♀️ **Индивидуальная сессия** - запись на персональную работу с выбором времени
- 🎓 **Стартовый онлайн-курс** - покупка и доступ к стартовому курсу
- 📚 **Обучение 3 месяца** - запись на полноценную программу обучения
- 🛠 **Инструменты** - доступ к медитациям, аудио-практикам и материалам
- 💬 **Связь с менеджером** - прямой контакт с поддержкой
- 💳 **Оплата через MonoPay** - безопасные платежи в гривнах

## 📦 Установка

### 1. Клонируйте проект
```bash
git clone <your-repo>
cd magic_vibes_bot
```

### 2. Создайте виртуальное окружение
```bash
python -m venv venv

# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Установите зависимости
```bash
pip install -r requirements.txt
```

### 4. Настройте PostgreSQL

Создайте базу данных:
```sql
CREATE DATABASE magic_vibes_bot;
CREATE USER magic_vibes WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE magic_vibes_bot TO magic_vibes;
```

### 5. Настройте переменные окружения

Скопируйте `.env.example` в `.env` и заполните значения:
```bash
cp .env.example .env
```

Отредактируйте `.env`:
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=your_telegram_id

DB_HOST=localhost
DB_PORT=5432
DB_USER=magic_vibes
DB_PASSWORD=your_password
DB_NAME=magic_vibes_bot

MONOPAY_TOKEN=your_monopay_api_token
MONOPAY_MERCHANT_ID=your_merchant_id
```

### 6. Получите токены

#### Telegram Bot Token:
1. Найдите @BotFather в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Скопируйте полученный токен

#### MonoPay API:
1. Зарегистрируйтесь в [MonoPay](https://www.monobank.ua/)
2. Получите API токен в личном кабинете
3. Настройте webhook URL (см. раздел Webhook ниже)

### 7. Запустите бота
```bash
python main.py
```

## 🗃 Структура базы данных

### Основные таблицы:
- **users** - пользователи бота
- **practices** - групповые и индивидуальные практики
- **practice_schedules** - расписание практик
- **bookings** - бронирования
- **payments** - платежи
- **courses** - курсы (стартовый и 3-месячный)
- **course_enrollments** - записи на курсы
- **course_materials** - материалы курсов
- **manager_contacts** - контакты менеджеров

## 💳 Настройка MonoPay

### Webhook для обработки платежей

Создайте endpoint для получения уведомлений от MonoPay:

```python
from aiohttp import web
from services.monopay import MonoPayService

async def monopay_webhook(request):
    """Обработчик webhook от MonoPay"""
    
    # Получаем подпись из заголовков
    signature = request.headers.get('X-Sign')
    body = await request.text()
    
    # Проверяем подпись
    mono_service = MonoPayService(token, merchant_id)
    if not mono_service.verify_webhook_signature(signature, body):
        return web.Response(status=403, text="Invalid signature")
    
    # Обрабатываем данные
    data = await request.json()
    
    if data.get('status') == 'success':
        # Платеж успешен - обновляем статус в БД
        reference = data.get('reference')  # payment_123
        payment_id = int(reference.split('_')[1])
        
        # Обновляем статус платежа
        # ... ваша логика обновления БД
        
        # Если это курс - активируем доступ
        # Если это бронирование - подтверждаем его
    
    return web.Response(status=200)

# Добавьте роут
app = web.Application()
app.router.add_post('/webhook/monopay', monopay_webhook)
```

### Настройка webhook URL в MonoPay
В личном кабинете MonoPay укажите URL:
```
https://your-domain.com/webhook/monopay
```

## 🚀 Первоначальная настройка данных

### Добавление практик

```python
from database.models import Practice, PracticeType

# Групповая практика
group_practice = Practice(
    title="Утренняя йога",
    description="Мягкая практика для пробуждения тела и ума",
    practice_type=PracticeType.GROUP,
    duration_minutes=90,
    price=300.0,
    max_participants=15,
    is_active=True
)

# Индивидуальная сессия
individual = Practice(
    title="Индивидуальная сессия",
    description="Персональная работа 1-на-1",
    practice_type=PracticeType.INDIVIDUAL,
    duration_minutes=60,
    price=800.0,
    is_active=True
)
```

### Добавление курсов

```python
from database.models import Course, CourseType

# Стартовый курс
starter = Course(
    title="Стартовый онлайн-курс",
    description="Введение в практику для начинающих",
    course_type=CourseType.STARTER,
    price=1500.0,
    duration_days=30,
    is_active=True
)

# 3-месячное обучение
three_month = Course(
    title="Обучение 3 месяца",
    description="Полная программа углубленного изучения",
    course_type=CourseType.THREE_MONTH,
    price=8000.0,
    duration_days=90,
    is_active=True
)
```

### Добавление менеджера

```python
from database.models import ManagerContact

manager = ManagerContact(
    name="Екатерина",
    telegram_username="kate_magic_vibes",
    phone="+380991234567",
    is_active=True
)
```

## 📊 Админ-функции

Для администрирования можно создать отдельный модуль или бот. Основные функции:

- Создание/редактирование практик
- Управление расписанием
- Просмотр бронирований
- Подтверждение индивидуальных сессий
- Управление курсами и материалами
- Просмотр статистики платежей

## 🔒 Безопасность

- ✅ Все платежи через безопасный MonoPay API
- ✅ Проверка подписей webhook
- ✅ Валидация данных пользователей
- ✅ Защита от SQL-инъекций (SQLAlchemy ORM)
- ✅ Асинхронная обработка запросов

## 📝 Логи и мониторинг

Логи сохраняются в консоль. Для продакшена рекомендуется:

1. Настроить запись в файл:
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
```

2. Использовать Sentry для отслеживания ошибок
3. Настроить мониторинг через Prometheus/Grafana

## 🐳 Деплой с Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  bot:
    build: .
    env_file: .env
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: magic_vibes_bot
      POSTGRES_USER: magic_vibes
      POSTGRES_PASSWORD: your_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

## 🛠 Разработка и тестирование

### Запуск в режиме разработки
```bash
# Включите отладку SQL
# В main.py: engine = create_async_engine(..., echo=True)

python main.py
```

### Тестирование платежей
MonoPay предоставляет тестовое окружение. Используйте тестовые токены для разработки.

## 📞 Поддержка

По вопросам настройки и использования бота:
- Telegram: @your_support
- Email: support@magicvibes.com

## 📄 Лицензия

Проприетарное ПО. Все права защищены © 2024 Magic Vibes
