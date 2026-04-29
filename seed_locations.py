"""
Сід двох локацій Magic Vibes у БД.
Запустити один раз після додавання моделі Location.
"""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.settings import load_config
from database.models import Base, Location


LOCATIONS = [
    {
        "title": "Локація на Рейтарській",
        "address": "вулиця Рейтарська, 13, Київ",
        "maps_url": "https://maps.app.goo.gl/FRfWGf8fsbxp4CSF7",
        "sort_order": 1,
    },
    {
        "title": "Локація на Пирогова",
        "address": "вулиця Пирогова, 5, Київ",
        "maps_url": "https://maps.app.goo.gl/NRhjx33edpd8HWMg8",
        "sort_order": 2,
    },
]


async def main():
    config = load_config()
    engine = create_async_engine(config.db.url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        for loc in LOCATIONS:
            existing = await session.execute(
                select(Location).where(Location.address == loc["address"])
            )
            if existing.scalar_one_or_none():
                print(f"⏭  Вже є: {loc['address']}")
                continue
            session.add(Location(**loc, is_active=True))
            print(f"✅ Додано: {loc['address']}")
        await session.commit()

    await engine.dispose()
    print("🎉 Готово")


if __name__ == "__main__":
    asyncio.run(main())
