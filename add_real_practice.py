"""
Удаляет тестовые практики и добавляет реальную:
"Віброзвукова практика енерго-корекції та наповнення"
со расписанием на 8 ближайших воскресений в 11:00.
"""
import asyncio
from datetime import datetime, timedelta, time
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.settings import load_config
from database.models import (
    Practice, PracticeType, PracticeSchedule, Booking
)


PRACTICE_TITLE = "Віброзвукова практика енерго-корекції та наповнення"

PRACTICE_DESCRIPTION = """🪷 <b>Особлива вібро-звукова практика енерго-корекції та наповнення</b>

З індивідуальним опрацюванням кожного учасника.

✅ Кожен учасник в індивідуальному порядку пройде покрокові етапи РОБОТИ З ЕНЕРГО-ПОЛЕМ:
🏮 Очищення
🏮 Структуризація
🏮 Наповнення
🏮 Укріплення захисного поля

💛 Ми працюватимемо з:
• Бубнами
• Великою співочою чашею стоячи між гонгами
• Вібро-звуками у просторі 13 гонгів та гігантських планетарно-чакральних кришталевих чаш

📌 <b>Деталі</b>
📍 Київ, вул. Рейтарська, 13
🗓 Щонеділі, 11:00–14:00
👥 Групи макс. 13 учасників
🕒 Збір з 10:45, початок об 11:00, закінчення 14:00 (14:30)
💰 Цінність практики: 1500 грн

✨ З любов'ю, Magic Vibes 💫"""


async def main():
    config = load_config()
    engine = create_async_engine(config.db.url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # 1) Найти все существующие практики
        result = await session.execute(select(Practice))
        all_practices = result.scalars().all()

        old_practice_ids = [p.id for p in all_practices if p.title != PRACTICE_TITLE]

        if old_practice_ids:
            print(f"Удаляем {len(old_practice_ids)} тестовых практик и связанные данные...")

            # Удаляем bookings → schedules → practices в правильном порядке
            await session.execute(
                delete(Booking).where(Booking.practice_id.in_(old_practice_ids))
            )
            await session.execute(
                delete(PracticeSchedule).where(PracticeSchedule.practice_id.in_(old_practice_ids))
            )
            await session.execute(
                delete(Practice).where(Practice.id.in_(old_practice_ids))
            )
            await session.commit()
            print("✅ Тестовые практики удалены")

        # 2) Проверяем — нет ли уже нашей практики
        result = await session.execute(
            select(Practice).where(Practice.title == PRACTICE_TITLE)
        )
        practice = result.scalar_one_or_none()

        if practice:
            print(f"⚠️  Практика '{PRACTICE_TITLE}' уже существует (id={practice.id}). Обновляем расписание.")
            # Удаляем старое расписание
            await session.execute(
                delete(PracticeSchedule).where(PracticeSchedule.practice_id == practice.id)
            )
            await session.commit()
        else:
            practice = Practice(
                title=PRACTICE_TITLE,
                description=PRACTICE_DESCRIPTION,
                practice_type=PracticeType.GROUP,
                duration_minutes=180,
                price=1500.0,
                max_participants=13,
                is_active=True,
            )
            session.add(practice)
            await session.commit()
            await session.refresh(practice)
            print(f"✅ Создана практика '{PRACTICE_TITLE}' (id={practice.id})")

        # 3) Расписание — 8 ближайших воскресений в 11:00
        today = datetime.now()
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0 and today.time() >= time(11, 0):
            days_until_sunday = 7  # сегодня воскресенье уже прошло
        first_sunday = (today + timedelta(days=days_until_sunday)).replace(
            hour=11, minute=0, second=0, microsecond=0
        )

        for i in range(8):
            schedule_date = first_sunday + timedelta(weeks=i)
            session.add(PracticeSchedule(
                practice_id=practice.id,
                datetime=schedule_date,
                available_slots=13,
                is_available=True,
            ))
        await session.commit()
        print(f"✅ Создано 8 воскресных слотов с {first_sunday.strftime('%d.%m.%Y %H:%M')}")

    await engine.dispose()
    print("🎉 Готово")


if __name__ == "__main__":
    asyncio.run(main())
