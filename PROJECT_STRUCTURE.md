# 📊 Визуальная структура проекта Magic Vibes Bot

```
magic_vibes_bot/
│
├── 📄 main.py                    # ⭐ ТОЧКА ВХОДА - запуск бота
├── 📄 init_db.py                 # 🔧 Инициализация БД с тестовыми данными
├── 📄 webhook.py                 # 🔗 Webhook для приема платежей от MonoPay
│
├── 📄 requirements.txt           # 📦 Python зависимости
├── 📄 .env.example              # 🔐 Пример переменных окружения
├── 📄 .gitignore                # 🚫 Игнорируемые файлы для Git
│
├── 📖 README.md                 # 📚 Основная документация
├── 📖 QUICKSTART.md             # 🚀 Быстрый старт
├── 📖 ARCHITECTURE.md           # 🏗️ Архитектура и техническая документация
│
├── 📁 config/                   # ⚙️ КОНФИГУРАЦИЯ
│   ├── __init__.py
│   └── settings.py              # Загрузка .env, классы конфигурации
│
├── 📁 database/                 # 🗄️ БАЗА ДАННЫХ
│   ├── __init__.py
│   └── models.py                # SQLAlchemy модели (10 таблиц)
│                                #   - User (пользователи)
│                                #   - Practice (практики)
│                                #   - PracticeSchedule (расписание)
│                                #   - Booking (бронирования)
│                                #   - Payment (платежи)
│                                #   - Course (курсы)
│                                #   - CourseEnrollment (записи на курсы)
│                                #   - CourseMaterial (материалы)
│                                #   - ManagerContact (контакты менеджеров)
│
├── 📁 handlers/                 # 🎮 ОБРАБОТЧИКИ КОМАНД И CALLBACK
│   ├── __init__.py
│   ├── menu.py                  # Главное меню, навигация, инструменты
│   ├── practices.py             # Групповые практики + оплата
│   ├── individual.py            # Индивидуальные сессии + FSM
│   └── courses.py               # Курсы (стартовый + 3 месяца)
│
├── 📁 keyboards/                # ⌨️ КЛАВИАТУРЫ
│   ├── __init__.py
│   └── inline.py                # Inline-клавиатуры для всех функций
│                                #   - Главное меню
│                                #   - Список практик
│                                #   - Расписание
│                                #   - Подтверждение бронирования
│                                #   - Оплата
│                                #   - Курсы
│                                #   - Инструменты
│
└── 📁 services/                 # 🔌 ВНЕШНИЕ СЕРВИСЫ
    ├── __init__.py
    └── monopay.py               # MonoPayService:
                                 #   - create_invoice()
                                 #   - check_payment_status()
                                 #   - cancel_invoice()
                                 #   - verify_webhook_signature()
```

## 🔄 Потоки данных

### 1️⃣ Запись на практику
```
Пользователь отправляет /start
    ↓
menu.py → Главное меню (6 кнопок)
    ↓
[Актуальные практики]
    ↓
practices.py → Загрузка Practice из БД
    ↓
Показ списка → keyboards.inline.get_practices_keyboard()
    ↓
Пользователь выбирает практику
    ↓
practices.py → Загрузка PracticeSchedule
    ↓
Показ расписания → keyboards.inline.get_practice_schedule_keyboard()
    ↓
Пользователь выбирает время
    ↓
practices.py → Создание Booking (PENDING)
    ↓
Подтверждение → keyboards.inline.get_booking_confirmation_keyboard()
    ↓
[Подтвердить и оплатить]
    ↓
practices.py → Создание Payment
    ↓
services.monopay.create_invoice()
    ↓
Получение payment_url
    ↓
keyboards.inline.get_payment_keyboard() → Кнопка "Оплатить"
    ↓
Пользователь оплачивает через MonoPay
    ↓
MonoPay → webhook.py (POST /webhook/monopay)
    ↓
Проверка подписи → verify_webhook_signature()
    ↓
Обновление Payment (SUCCESS)
    ↓
Обновление Booking (CONFIRMED)
    ↓
Уведомление пользователю ✅
```

### 2️⃣ Индивидуальная сессия с FSM
```
[Индивидуальная сессия]
    ↓
individual.py → Описание
    ↓
[Выбрать дату и время]
    ↓
FSM.set_state(waiting_for_datetime)
    ↓
Пользователь вводит: "01.01.2025 15:00"
    ↓
individual.py → process_individual_datetime()
    ↓
Парсинг datetime.strptime()
    ↓
Создание PracticeSchedule + Booking
    ↓
FSM.clear()
    ↓
Уведомление: "Запрос создан, ждите подтверждения"
    ↓
[Менеджер подтверждает вручную]
    ↓
admin_confirm_individual_session() → Создание Payment
    ↓
MonoPay → Оплата → Подтверждение
```

### 3️⃣ Покупка курса
```
[Стартовый курс] или [3 месяца]
    ↓
courses.py → Загрузка Course
    ↓
Показ описания
    ↓
[Записаться на курс]
    ↓
courses.py → Создание CourseEnrollment (is_active=False)
    ↓
Создание Payment
    ↓
MonoPay → payment_url
    ↓
Оплата
    ↓
webhook.py → Payment (SUCCESS)
    ↓
courses.activate_course_access()
    ↓
CourseEnrollment (is_active=True)
    ↓
Отправка CourseMaterial пользователю 📚
```

## 📊 Статистика проекта

- **Всего файлов:** 15
- **Python модулей:** 10
- **Строк кода:** ~2500+
- **Таблиц БД:** 10
- **Обработчиков:** 20+
- **Клавиатур:** 12
- **FSM состояний:** 2
- **Интеграций:** 1 (MonoPay)

## 🎯 Ключевые компоненты

### 🔑 Основные технологии
- **aiogram 3.4** - async Telegram Bot Framework
- **SQLAlchemy 2.0** - ORM для работы с БД
- **asyncpg** - async PostgreSQL драйвер
- **aiohttp** - async HTTP клиент/сервер
- **environs** - управление переменными окружения

### 🛠️ Главные модули

1. **main.py** (68 строк)
   - Точка входа приложения
   - Инициализация Bot, Dispatcher
   - Middleware для БД сессий
   - Регистрация роутеров

2. **database/models.py** (234 строки)
   - 10 SQLAlchemy моделей
   - Relationships между таблицами
   - Enums для статусов

3. **handlers/** (4 файла, ~650 строк)
   - menu.py - главное меню
   - practices.py - групповые практики
   - individual.py - индивидуальные сессии
   - courses.py - курсы и обучение

4. **services/monopay.py** (174 строки)
   - Полная интеграция с MonoPay API
   - Создание счетов
   - Проверка статусов
   - Webhook валидация

5. **keyboards/inline.py** (185 строк)
   - 12 различных клавиатур
   - Динамическая генерация кнопок
   - Навигация по всему боту

## 🚀 Готово к использованию!

Этот бот включает в себя:
✅ Полную систему бронирования
✅ Интеграцию с платежами MonoPay
✅ Управление курсами
✅ FSM для сложных сценариев
✅ Расширяемую архитектуру
✅ Подробную документацию
✅ Скрипты инициализации
✅ Примеры конфигурации
