"""
Обработчики главного меню и навигации
"""
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.inline import get_main_menu, get_back_to_main_menu
from database.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = Router()

WELCOME_TEXT = """
🌟 <b>Привет! Добро пожаловать в Magic Vibes!</b>

Я помогу вам:
✨ Записаться на актуальные практики
🧘‍♀️ Забронировать индивидуальную сессию
📚 Выбрать и оплатить курс обучения
🛠 Получить доступ к полезным материалам
💬 Связаться с менеджером

Выберите нужный раздел:
"""

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    """Обработка команды /start"""
    
    # Проверяем, есть ли пользователь в БД
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()
    
    # Если пользователя нет - создаем
    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        session.add(user)
        await session.commit()
    
    await message.answer(
        text=WELCOME_TEXT,
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    
    # Очищаем состояние
    await state.clear()
    
    await callback.message.edit_text(
        text=WELCOME_TEXT,
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "tools")
async def show_tools(callback: CallbackQuery):
    """Показ раздела Инструменты"""
    from keyboards.inline import get_tools_keyboard
    
    text = """
🛠 <b>Инструменты для практики</b>

Здесь вы найдете:
📖 Гайдовые медитации
🎵 Аудио-практики для самостоятельной работы
📝 Полезные статьи и материалы

Выберите категорию:
"""
    
    await callback.message.edit_text(
        text=text,
        reply_markup=get_tools_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "contact_manager")
async def contact_manager(callback: CallbackQuery, session: AsyncSession):
    """Связь с менеджером"""
    from keyboards.inline import get_manager_contact_keyboard
    from database.models import ManagerContact
    
    # Получаем активных менеджеров
    result = await session.execute(
        select(ManagerContact).where(ManagerContact.is_active == True)
    )
    managers = result.scalars().all()
    
    if managers:
        text = """
💬 <b>Связаться с менеджером</b>

Наши менеджеры с радостью ответят на все ваши вопросы!

Выберите удобный способ связи:
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_manager_contact_keyboard(managers),
            parse_mode="HTML"
        )
    else:
        text = """
💬 <b>Связаться с менеджером</b>

К сожалению, в данный момент менеджеры недоступны.
Попробуйте связаться позже или напишите нам напрямую: @magic_vibes_support
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("tools_"))
async def show_tool_category(callback: CallbackQuery):
    """Показ категорий инструментов"""
    
    category = callback.data.replace("tools_", "")
    
    texts = {
        "meditations": """
📖 <b>Медитации</b>

Здесь будут доступны гайдовые медитации для разных целей:
• Расслабление и снятие стресса
• Работа с эмоциями
• Утренние и вечерние практики
• Медитации для сна

<i>Раздел находится в разработке.</i>
""",
        "audio": """
🎵 <b>Аудио-практики</b>

Коллекция аудио для самостоятельной практики:
• Дыхательные упражнения
• Мантры и аффирмации
• Звуковые ванны
• Музыка для йоги

<i>Раздел находится в разработке.</i>
""",
        "articles": """
📝 <b>Статьи и материалы</b>

Полезные статьи по темам:
• Основы йоги и медитации
• Здоровый образ жизни
• Работа с энергией
• Советы от экспертов

<i>Раздел находится в разработке.</i>
"""
    }
    
    text = texts.get(category, "Раздел в разработке")
    
    await callback.message.edit_text(
        text=text,
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()
