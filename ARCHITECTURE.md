# 🏗 Архитектура бота Magic Vibes

## 📁 Структура проекта

```
magic_vibes_bot/
├── config/
│   ├── __init__.py
│   └── settings.py          # Конфигурация и загрузка .env
│
├── database/
│   ├── __init__.py
│   └── models.py            # SQLAlchemy модели (User, Practice, Booking, etc.)
│
├── handlers/
│   ├── __init__.py
│   ├── menu.py              # Главное меню и навигация
│   ├── practices.py         # Запись на групповые практики
│   ├── individual.py        # Индивидуальные сессии
│   └── courses.py           # Курсы (стартовый и 3-месячный)
│
├── keyboards/
│   ├── __init__.py
│   └── inline.py            # Inline-клавиатуры для навигации
│
├── services/
│   ├── __init__.py
│   └── monopay.py           # Интеграция с MonoPay API
│
├── .env.example             # Пример переменных окружения
├── .gitignore
├── main.py                  # Точка входа, запуск бота
├── init_db.py               # Скрипт инициализации БД
├── requirements.txt         # Python зависимости
├── README.md                # Основная документация
├── QUICKSTART.md            # Быстрый старт
└── ARCHITECTURE.md          # Этот файл
```

## 🔄 Поток данных

### 1. Запись на групповую практику

```
Пользователь
    ↓
[/start] → Главное меню
    ↓
[Актуальные практики] → Список практик из БД
    ↓
[Выбор практики] → Расписание (PracticeSchedule)
    ↓
[Выбор времени] → Создание Booking (status=PENDING)
    ↓
[Подтверждение] → Создание Payment
    ↓
MonoPay API → Создание invoice
    ↓
[Ссылка на оплату] → Пользователь переходит на MonoPay
    ↓
MonoPay Webhook → Обновление Payment (status=SUCCESS)
    ↓
Booking (status=CONFIRMED) → Уведомление пользователю
```

### 2. Индивидуальная сессия

```
Пользователь
    ↓
[Индивидуальная сессия] → Описание
    ↓
[Выбрать дату и время] → FSM state (waiting_for_datetime)
    ↓
Пользователь вводит дату → Парсинг datetime
    ↓
Создание PracticeSchedule + Booking
    ↓
Уведомление менеджеру → Ручное подтверждение
    ↓
Менеджер подтверждает → Создание Payment
    ↓
MonoPay → Оплата → Подтверждение
```

### 3. Покупка курса

```
Пользователь
    ↓
[Стартовый курс / 3 месяца] → Описание курса
    ↓
[Записаться на курс] → Создание CourseEnrollment (is_active=False)
    ↓
Создание Payment → MonoPay invoice
    ↓
Оплата → Payment (status=SUCCESS)
    ↓
CourseEnrollment (is_active=True)
    ↓
Отправка материалов (CourseMaterial) → Доступ к курсу
```

## 🗄 Модель данных

### Основные сущности

#### User (Пользователь)
- `telegram_id` - ID в Telegram (уникальный)
- `username` - @username
- `full_name` - Полное имя
- `phone`, `email` - Контакты
- `role` - CLIENT | MANAGER | ADMIN

#### Practice (Практика)
- `title` - Название
- `description` - Описание
- `practice_type` - GROUP | INDIVIDUAL
- `duration_minutes` - Длительность
- `price` - Стоимость
- `max_participants` - Макс. участников (для GROUP)

#### PracticeSchedule (Расписание)
- `practice_id` → Practice
- `datetime` - Дата и время
- `available_slots` - Доступные места
- `is_available` - Доступно ли

#### Booking (Бронирование)
- `user_id` → User
- `practice_id` → Practice
- `schedule_id` → PracticeSchedule
- `status` - PENDING | CONFIRMED | CANCELLED | COMPLETED

#### Payment (Платеж)
- `user_id` → User
- `booking_id` → Booking (опционально)
- `course_enrollment_id` → CourseEnrollment (опционально)
- `amount` - Сумма
- `status` - PENDING | SUCCESS | FAILED | REFUNDED
- `transaction_id` - ID транзакции MonoPay
- `payment_url` - Ссылка на оплату

#### Course (Курс)
- `title` - Название
- `description` - Описание
- `course_type` - STARTER | THREE_MONTH
- `price` - Стоимость
- `duration_days` - Длительность в днях

#### CourseEnrollment (Запись на курс)
- `user_id` → User
- `course_id` → Course
- `enrolled_at` - Дата записи
- `expires_at` - Дата окончания доступа
- `is_active` - Активен ли доступ

#### CourseMaterial (Материалы курса)
- `course_id` → Course
- `title` - Название
- `file_id` - Telegram file_id
- `file_type` - document | video | audio
- `order` - Порядок отображения

## 🔌 Интеграции

### MonoPay API

**Основные методы:**

1. **create_invoice()** - Создание счета на оплату
   - Входные данные: amount, description, reference
   - Возвращает: invoice_id, payment_url

2. **check_payment_status()** - Проверка статуса платежа
   - Входные данные: invoice_id
   - Возвращает: status, paid (boolean)

3. **cancel_invoice()** - Отмена счета
   - Входные данные: invoice_id

4. **verify_webhook_signature()** - Проверка подписи webhook
   - Защита от поддельных уведомлений

**Webhook поток:**
```
MonoPay → POST /webhook/monopay
    ↓
Проверка подписи (X-Sign header)
    ↓
Парсинг данных платежа
    ↓
Обновление Payment в БД
    ↓
Если success → Активация Booking/CourseEnrollment
    ↓
Уведомление пользователю
```

## 🎯 FSM (Finite State Machine)

### IndividualSessionStates
- `waiting_for_datetime` - Ожидание ввода даты/времени
- `waiting_for_notes` - Ожидание дополнительных заметок (опционально)

Пример использования:
```python
@router.callback_query(F.data == "individual_choose_datetime")
async def choose_datetime(callback, state: FSMContext):
    await state.set_state(IndividualSessionStates.waiting_for_datetime)
    # Теперь следующее сообщение обработается соответствующим хендлером

@router.message(IndividualSessionStates.waiting_for_datetime)
async def process_datetime(message: Message, state: FSMContext):
    # Обработка введенной даты
    await state.clear()  # Очистка состояния
```

## 🔐 Безопасность

### 1. Защита от SQL-инъекций
- Использование SQLAlchemy ORM
- Параметризованные запросы

### 2. Валидация платежей
- Проверка подписи webhook от MonoPay
- Сверка transaction_id с БД

### 3. Контроль доступа
- Проверка user_id для всех операций
- Role-based access (CLIENT, MANAGER, ADMIN)

### 4. Защита от переполнения
- Ограничение available_slots
- Проверка дат в будущем
- Валидация форматов данных

## ⚡ Производительность

### Database
- **Async I/O**: asyncpg для неблокирующих запросов
- **Connection pooling**: встроенный в SQLAlchemy
- **Indexes**: на telegram_id, practice_id, schedule_id

### Bot
- **Async handlers**: все обработчики асинхронные
- **Middleware**: session передается через middleware
- **Polling**: aiogram 3.x с оптимизированным polling

## 🧩 Расширяемость

### Добавление новых типов практик
```python
# В models.py
class PracticeType(enum.Enum):
    GROUP = "group"
    INDIVIDUAL = "individual"
    WORKSHOP = "workshop"  # Новый тип
```

### Добавление новых способов оплаты
```python
# Создать services/stripe.py
class StripeService:
    async def create_payment_intent(self, amount):
        # Реализация
        pass

# В handlers добавить выбор способа оплаты
```

### Добавление админ-панели
```python
# Создать handlers/admin.py
@router.message(Command("admin"))
async def admin_panel(message: Message):
    # Проверка роли
    if user.role != UserRole.ADMIN:
        return
    
    # Показать админ-меню
```

## 📊 Мониторинг и логирование

### Структура логов
```python
# В main.py
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
```

### Метрики для отслеживания
- Количество новых пользователей/день
- Количество бронирований/день
- Конверсия: просмотр → бронирование → оплата
- Средний чек
- Отмены бронирований
- Ошибки платежей

## 🔄 Жизненный цикл бронирования

```
PENDING (создано)
    ↓
    ├─→ CONFIRMED (оплачено)
    │       ↓
    │   COMPLETED (завершено)
    │
    └─→ CANCELLED (отменено)
```

**Автоматические действия:**
- За 24 часа до практики → Напоминание пользователю
- После окончания → Статус COMPLETED
- Через 15 минут без оплаты → Автоотмена (опционально)

## 🌐 Масштабирование

### Горизонтальное масштабирование
- Использовать Redis для FSM storage
- Запустить несколько инстансов бота
- Load balancer для webhook

### Вертикальное масштабирование
- Увеличить connection pool БД
- Оптимизировать индексы
- Кэширование частых запросов

## 🔧 Конфигурация

### Переменные окружения (.env)
```
# Бот
BOT_TOKEN - Токен Telegram бота
ADMIN_IDS - ID администраторов (через запятую)

# База данных
DB_HOST - Хост БД
DB_PORT - Порт БД
DB_USER - Пользователь БД
DB_PASSWORD - Пароль
DB_NAME - Название БД

# Платежи
MONOPAY_TOKEN - API токен MonoPay
MONOPAY_MERCHANT_ID - ID мерчанта
```

## 🚀 Деплой

### Production checklist
- [ ] Настроены все переменные окружения
- [ ] БД на отдельном сервере
- [ ] HTTPS для webhook
- [ ] Логирование в файлы
- [ ] Мониторинг (Prometheus/Grafana)
- [ ] Backup БД
- [ ] Systemd service для автозапуска
- [ ] Rate limiting для API
- [ ] Тестовые платежи проверены

### Рекомендуемый стек для продакшена
- **Сервер**: Ubuntu 22.04 LTS
- **БД**: PostgreSQL 15
- **Процесс**: Systemd service
- **Reverse proxy**: Nginx (для webhook)
- **SSL**: Let's Encrypt
- **Мониторинг**: Prometheus + Grafana
- **Логи**: ELK Stack или Loki
