"""
Скрипт для первоначального заполнения базы данных
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.settings import load_config
from database.models import (
    Base, Practice, PracticeType, Course, CourseType, 
    ManagerContact, PracticeSchedule
)
from datetime import datetime, timedelta


async def init_database():
    """Инициализация базы данных с тестовыми данными"""
    
    config = load_config()
    
    engine = create_async_engine(
        config.db.url,
        echo=True
    )
    
    # Создаем таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with session_maker() as session:
        
        # Добавляем групповую практику
        group_practice = Practice(
            title="Утренняя йога",
            description="""Мягкая практика для пробуждения тела и ума.

Что вас ждет:
• Дыхательные упражнения
• Асаны для всего тела
• Медитация
• Шавасана

Подходит для всех уровней подготовки.""",
            practice_type=PracticeType.GROUP,
            duration_minutes=90,
            price=300.0,
            max_participants=15,
            is_active=True
        )
        session.add(group_practice)
        
        # Добавляем еще одну групповую практику
        evening_practice = Practice(
            title="Вечерняя расслабляющая практика",
            description="""Спокойная практика для завершения дня.

Что вас ждет:
• Мягкие растяжки
• Работа с дыханием
• Расслабление
• Медитация для сна

Идеально после рабочего дня.""",
            practice_type=PracticeType.GROUP,
            duration_minutes=75,
            price=250.0,
            max_participants=12,
            is_active=True
        )
        session.add(evening_practice)
        
        # Добавляем индивидуальную сессию
        individual = Practice(
            title="Индивидуальная сессия",
            description="""Персональная работа один-на-один с практиком.

Что включено:
• Анализ ваших запросов
• Индивидуальный подход
• Глубокая проработка
• Детальная обратная связь
• Домашнее задание

Длительность по договоренности.""",
            practice_type=PracticeType.INDIVIDUAL,
            duration_minutes=60,
            price=800.0,
            is_active=True
        )
        session.add(individual)
        
        # Добавляем стартовый курс
        starter_course = Course(
            title="Стартовый онлайн-курс 'Основы йоги'",
            description="""Полный вводный курс для начинающих.

Программа курса:
• 10 видео-уроков
• Теория и практика
• Домашние задания
• Поддержка куратора
• Доступ к материалам 30 дней
• Сертификат по окончании

Начните свой путь в йоге правильно!""",
            course_type=CourseType.STARTER,
            price=1500.0,
            duration_days=30,
            is_active=True
        )
        session.add(starter_course)
        
        # Добавляем 3-месячный курс
        three_month_course = Course(
            title="Обучение 3 месяца 'Трансформация'",
            description="""Полная программа углубленного изучения и практики.

Что вас ждет:
• 12 еженедельных живых занятий
• Доступ ко всем записям
• 3 индивидуальные консультации
• Домашние задания с проверкой
• Работа в группе единомышленников
• Персональный план развития
• Итоговая сертификация

Трансформируйте свою жизнь за 3 месяца!""",
            course_type=CourseType.THREE_MONTH,
            price=8000.0,
            duration_days=90,
            is_active=True
        )
        session.add(three_month_course)
        
        # Добавляем контакт менеджера
        manager = ManagerContact(
            name="Екатерина",
            telegram_username="kate_magic_vibes",
            phone="+380991234567",
            is_active=True
        )
        session.add(manager)
        
        await session.commit()
        
        # Добавляем расписание для групповых практик на ближайшую неделю
        await session.refresh(group_practice)
        await session.refresh(evening_practice)
        
        # Утренняя йога - по понедельникам, средам, пятницам в 9:00
        for day_offset in [0, 2, 4, 7, 9, 11]:  # Ближайшие 2 недели
            schedule_date = datetime.now() + timedelta(days=day_offset)
            schedule_date = schedule_date.replace(hour=9, minute=0, second=0, microsecond=0)
            
            schedule = PracticeSchedule(
                practice_id=group_practice.id,
                datetime=schedule_date,
                available_slots=15,
                is_available=True
            )
            session.add(schedule)
        
        # Вечерняя практика - по вторникам, четвергам в 19:00
        for day_offset in [1, 3, 8, 10]:  # Ближайшие 2 недели
            schedule_date = datetime.now() + timedelta(days=day_offset)
            schedule_date = schedule_date.replace(hour=19, minute=0, second=0, microsecond=0)
            
            schedule = PracticeSchedule(
                practice_id=evening_practice.id,
                datetime=schedule_date,
                available_slots=12,
                is_available=True
            )
            session.add(schedule)
        
        await session.commit()
        
        print("✅ База данных успешно инициализирована!")
        print(f"✅ Создано практик: 3")
        print(f"✅ Создано курсов: 2")
        print(f"✅ Создано расписаний: 10")
        print(f"✅ Создано менеджеров: 1")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
