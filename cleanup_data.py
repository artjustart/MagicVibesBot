"""
Одноразовий скрипт очищення:
1. Видаляє ВСІХ користувачів та повʼязані з ними дані
   (bookings, payments, course_enrollments, questionnaires, closed_format_requests).
2. Видаляє практики, у назві яких є вказаний фрагмент (за замовчуванням "йога для мам").

Розклад (PracticeSchedule) самих практик, які залишаються — не зачіпаємо;
розклад віддалених практик зноситься каскадом.

ВНИМАНИЕ: незворотньо. Запускати тільки з прапором --yes.

Запуск на VPS:
  cd /opt/magic_vibes_bot
  venv/bin/python cleanup_data.py            # сухий показ що буде видалено
  venv/bin/python cleanup_data.py --yes      # реальне видалення
"""
import asyncio
import sys
from sqlalchemy import select, delete as sa_delete, func, or_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.settings import load_config
from database.models import (
    User, Booking, Payment, CourseEnrollment, Practice, PracticeSchedule,
    Questionnaire, ClosedFormatRequest,
)

PRACTICE_NAME_PATTERNS = ["йога для мам", "Йога для мам", "ЙОГА ДЛЯ МАМ"]


async def main(apply: bool):
    config = load_config()
    engine = create_async_engine(config.db.url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # 1) Підрахунок користувачів і повʼязаних даних
        users_count = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        bookings_count = (await session.execute(select(func.count()).select_from(Booking))).scalar() or 0
        payments_count = (await session.execute(select(func.count()).select_from(Payment))).scalar() or 0
        enrollments_count = (await session.execute(select(func.count()).select_from(CourseEnrollment))).scalar() or 0
        questionnaires_count = (await session.execute(select(func.count()).select_from(Questionnaire))).scalar() or 0
        closed_count = (await session.execute(select(func.count()).select_from(ClosedFormatRequest))).scalar() or 0

        # 2) Знайти практики "йога для мам"
        target_practices_result = await session.execute(
            select(Practice).where(or_(
                *[Practice.title.ilike(f"%{p}%") for p in PRACTICE_NAME_PATTERNS]
            ))
        )
        target_practices = target_practices_result.scalars().all()

        print("=" * 60)
        print("📊 ПЛАН ОЧИЩЕННЯ")
        print("=" * 60)
        print()
        print("👥 Користувачі та їх дані:")
        print(f"   • users:                     {users_count}")
        print(f"   • bookings:                  {bookings_count}")
        print(f"   • payments:                  {payments_count}")
        print(f"   • course_enrollments:        {enrollments_count}")
        print(f"   • questionnaires:            {questionnaires_count}")
        print(f"   • closed_format_requests:    {closed_count}")
        print()
        print(f"🪷 Практики «йога для мам» ({len(target_practices)} знайдено):")
        for p in target_practices:
            sched = (await session.execute(
                select(func.count()).select_from(PracticeSchedule).where(
                    PracticeSchedule.practice_id == p.id
                )
            )).scalar() or 0
            print(f"   • [{p.id}] {p.title}  •  {sched} дат у розкладі")
        if not target_practices:
            print("   <нічого не знайдено>")
        print()

        if not apply:
            print("⚠️  Це сухий прогін. Для реального видалення додайте --yes")
            await engine.dispose()
            return

        print("🚨 ВИКОНУЄМО ВИДАЛЕННЯ...")
        print()

        # 3) Зносимо все що FK-залежить від users
        # (порядок важливий: спочатку payments, потім bookings/enrollments, потім users)
        await session.execute(sa_delete(Payment))
        await session.execute(sa_delete(Booking))
        await session.execute(sa_delete(CourseEnrollment))
        await session.execute(sa_delete(Questionnaire))
        await session.execute(sa_delete(ClosedFormatRequest))
        await session.execute(sa_delete(User))
        await session.commit()
        print("✅ Користувачі та повʼязані дані видалені.")

        # 4) Видаляємо практики "йога для мам" з їх розкладом
        for p in target_practices:
            await session.execute(
                sa_delete(PracticeSchedule).where(PracticeSchedule.practice_id == p.id)
            )
            await session.execute(
                sa_delete(Practice).where(Practice.id == p.id)
            )
            print(f"✅ Видалено практику: {p.title}")
        await session.commit()

        print()
        print("🎉 Готово.")

    await engine.dispose()


if __name__ == "__main__":
    apply = "--yes" in sys.argv
    asyncio.run(main(apply))
