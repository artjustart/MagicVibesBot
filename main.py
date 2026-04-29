"""
Главный файл запуска бота Magic Vibes
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat, MenuButtonCommands
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.settings import load_config
from database.models import Base
from services.monopay import MonoPayService

# Импорт роутеров
from handlers import (
    menu, practices, individual, courses, admin, locations,
    closed_format, questionnaire,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, config):
    """Действия при запуске бота"""
    logger.info("Bot starting...")

    # Меню-команди для всіх користувачів
    user_commands = [
        BotCommand(command="start", description="🚀 Запустити бота"),
        BotCommand(command="menu", description="🪷 Головне меню"),
        BotCommand(command="help", description="ℹ️ Допомога"),
    ]
    await bot.set_my_commands(commands=user_commands, scope=BotCommandScopeDefault())

    # Розширений набір для адмінів (видно лише їм)
    admin_commands = user_commands + [
        BotCommand(command="admin", description="🛠 Адмін-панель"),
    ]
    for admin_id in config.tg_bot.admin_ids:
        try:
            await bot.set_my_commands(
                commands=admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:
            logger.warning(f"Failed to set admin commands for {admin_id}: {e}")

    # Кнопка "Menu" біля поля вводу повідомлень
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def on_shutdown(bot: Bot, config):
    """Действия при остановке бота"""
    logger.info("Bot shutting down...")


async def main():
    """Основная функция запуска бота"""
    
    # Загружаем конфигурацию
    config = load_config()
    
    # Создаем подключение к БД
    engine = create_async_engine(
        config.db.url,
        echo=False,  # True для отладки SQL запросов
        pool_pre_ping=True
    )
    
    # Створюємо таблиці + ідемпотентні ALTER для нових колонок існуючих таблиць.
    # Спочатку create_all (створить таблиці на свіжій інсталяції з усіма колонками),
    # потім ALTER ADD COLUMN IF NOT EXISTS — для існуючих БД, де колонки немає.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sql_text(
            "ALTER TABLE practices ADD COLUMN IF NOT EXISTS details TEXT"
        ))
    
    # Создаем фабрику сессий
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # Инициализируем бота и диспетчер
    bot = Bot(
        token=config.tg_bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher()
    
    # Инициализируем сервис платежей
    mono_service = MonoPayService(
        token=config.monopay.token,
        merchant_id=config.monopay.merchant_id
    )
    
    # Middleware для передачи сессии БД в хендлеры
    @dp.update.middleware()
    async def db_session_middleware(handler, event, data):
        async with session_maker() as session:
            data['session'] = session
            data['mono_service'] = mono_service
            data['config'] = config
            return await handler(event, data)
    
    # Регистрируем роутеры (admin — першим, щоб /admin перехоплювався фільтром)
    dp.include_router(admin.router)
    dp.include_router(menu.router)
    dp.include_router(locations.router)
    dp.include_router(practices.router)
    dp.include_router(individual.router)
    dp.include_router(courses.router)
    dp.include_router(closed_format.router)
    dp.include_router(questionnaire.router)
    
    # Запускаем действия при старте
    await on_startup(bot, config)
    
    try:
        # Запускаем polling
        logger.info("Starting polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    finally:
        # Действия при остановке
        await on_shutdown(bot, config)
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
