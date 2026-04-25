"""
Главный файл запуска бота Magic Vibes
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.settings import load_config
from database.models import Base
from services.monopay import MonoPayService

# Импорт роутеров
from handlers import menu, practices, individual, courses

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, config):
    """Действия при запуске бота"""
    logger.info("Bot starting...")


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
    
    # Создаем таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
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
    
    # Регистрируем роутеры
    dp.include_router(menu.router)
    dp.include_router(practices.router)
    dp.include_router(individual.router)
    dp.include_router(courses.router)
    
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
