"""
Обробники головного меню та навігації
"""
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.inline import get_main_menu, get_back_to_main_menu
from database.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = Router()

WELCOME_TEXT = """
✨ <b>Ласкаво просимо до Magic Vibes!</b> ✨

🪷 Тут ви можете:

🌟  Записатися на актуальні практики
🧘‍♀️  Забронювати індивідуальну сесію
📚  Обрати та сплатити курс навчання
🎧  Отримати доступ до медитацій та матеріалів
💬  Звʼязатися з менеджером

━━━━━━━━━━━━━━━━━
👇 Оберіть потрібний розділ:
"""

HELP_TEXT = """
ℹ️ <b>Допомога</b>

Цей бот допоможе вам записатися на практики Magic Vibes 💫

<b>Команди:</b>
/start — почати спочатку
/menu — головне меню
/help — ця підказка

Якщо щось не працює — натисніть «💬 Звʼязатися з менеджером» в меню, ми завжди раді допомогти 🤍
"""


async def _greet(message: Message, session: AsyncSession):
    """Показати головне меню (для /start та /menu)."""
    # Реєструємо користувача якщо ще немає
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name or "",
        )
        session.add(user)
        await session.commit()

    await message.answer(
        text=WELCOME_TEXT,
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    """Команда /start"""
    await _greet(message, session)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession):
    """Команда /menu — те саме головне меню"""
    await _greet(message, session)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    await message.answer(
        text=HELP_TEXT,
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    """Повернення до головного меню"""
    await state.clear()

    await callback.message.edit_text(
        text=WELCOME_TEXT,
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "tools")
async def show_tools(callback: CallbackQuery):
    """Розділ Інструменти"""
    from keyboards.inline import get_tools_keyboard

    text = """
🎧 <b>Інструменти та матеріали</b>

Тут ви знайдете:

📖  Гайдові медитації
🎵  Аудіо-практики для самостійної роботи
📝  Корисні статті та матеріали

━━━━━━━━━━━━━━━━━
👇 Оберіть категорію:
"""

    await callback.message.edit_text(
        text=text,
        reply_markup=get_tools_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "contact_manager")
async def contact_manager(callback: CallbackQuery, session: AsyncSession):
    """Звʼязок з менеджером"""
    from keyboards.inline import get_manager_contact_keyboard
    from database.models import ManagerContact

    result = await session.execute(
        select(ManagerContact).where(ManagerContact.is_active == True)
    )
    managers = result.scalars().all()

    if managers:
        text = """
💬 <b>Звʼязатися з менеджером</b>

Наші менеджери з радістю дадуть відповідь на всі ваші питання 🤍

━━━━━━━━━━━━━━━━━
👇 Оберіть зручний спосіб звʼязку:
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_manager_contact_keyboard(managers),
            parse_mode="HTML",
        )
    else:
        text = """
💬 <b>Звʼязатися з менеджером</b>

На жаль, зараз менеджери недоступні.
Спробуйте пізніше або напишіть нам напряму: @magic_vibes_support
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("tools_"))
async def show_tool_category(callback: CallbackQuery):
    """Категорії інструментів"""
    category = callback.data.replace("tools_", "")

    texts = {
        "meditations": """
📖 <b>Медитації</b>

Тут будуть доступні гайдові медитації для різних цілей:
• Розслаблення та зняття стресу
• Робота з емоціями
• Ранкові та вечірні практики
• Медитації для сну

<i>Розділ у розробці.</i>
""",
        "audio": """
🎵 <b>Аудіо-практики</b>

Колекція аудіо для самостійної практики:
• Дихальні вправи
• Мантри та афірмації
• Звукові ванни
• Музика для йоги

<i>Розділ у розробці.</i>
""",
        "articles": """
📝 <b>Статті та матеріали</b>

Корисні статті за темами:
• Основи йоги та медитації
• Здоровий спосіб життя
• Робота з енергією
• Поради від експертів

<i>Розділ у розробці.</i>
""",
    }

    text = texts.get(category, "Розділ у розробці")

    await callback.message.edit_text(
        text=text,
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()
