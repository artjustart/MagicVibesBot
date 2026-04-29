"""
Одноразовий сід: записує детальний (довгий) опис практики
у поле Practice.details для існуючої віброзвукової групової практики.
Ідемпотентний — не перезаписує існуючий details.

Запуск на VPS:
  cd /opt/magic_vibes_bot && venv/bin/python seed_practice_details.py
"""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.settings import load_config
from database.models import Practice, PracticeType


VIBRATION_TITLE = "Віброзвукова практика енерго-корекції та наповнення"

VIBRATION_DETAILS = """📖 <b>ДЕТАЛЬНІШЕ ПРО ПРАКТИКУ</b>
━━━━━━━━━━━━━━━━━

Під час групової практики ми створюємо цілісне вібро-звукове поле,
у якому кожен учасник може мʼяко зануритися у процес внутрішньої гармонізації.

Практика проходить у кілька етапів:

<b>1️⃣  Активація бубнами</b>
Ми починаємо з включення через бубни. Цей етап допомагає очистити
енергетичне поле від напруги, деструктивних емоцій та внутрішніх блоків,
а також активувати тіло на глибинному рівні.

<b>2️⃣  Робота зі співочою чашею</b>
Учасник стає стопами у велику співочу чашу, створюючи ефект
"звукової ванни". Вібрація проходить через тіло, мʼяко впливаючи
на кожну клітинку, допомагаючи структурувати, заземлити
та гармонізувати внутрішній стан.

<b>3️⃣  Гонг-сесія</b>
Далі учасники переходять у лежаче положення та занурюються
у глибинну медитативну гонг-сесію. Звуки гонгів допомагають
зупинити внутрішній діалог, розслабити нервову систему
та відкрити доступ до глибших шарів підсвідомості.

<b>4️⃣  Кришталеві чаші та інструменти сили</b>
Чакральні гігантські кришталеві чаші та інші інструменти сили
створюють високовібраційне поле, у якому тіло, емоції та внутрішній
простір поступово приходять до більш цілісного стану.

━━━━━━━━━━━━━━━━━
Це не просто звукова медитація.
Це глибока вібро-звукова робота у просторі Magic Vibes 💫"""


async def main():
    config = load_config()
    engine = create_async_engine(config.db.url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        result = await session.execute(
            select(Practice).where(
                Practice.practice_type == PracticeType.GROUP,
                Practice.title == VIBRATION_TITLE,
            )
        )
        practice = result.scalar_one_or_none()

        if not practice:
            print(f"⚠️  Практика '{VIBRATION_TITLE}' не знайдена. Спочатку запустіть add_real_practice.py")
            await engine.dispose()
            return

        if practice.details and practice.details.strip():
            print(f"⏭  details для '{practice.title}' вже заповнено — пропускаю.")
        else:
            practice.details = VIBRATION_DETAILS
            await session.commit()
            print(f"✅ details записано для '{practice.title}'")

    await engine.dispose()
    print("🎉 Готово")


if __name__ == "__main__":
    asyncio.run(main())
