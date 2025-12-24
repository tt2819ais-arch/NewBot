import asyncio
import logging
from aiogram import Bot, Dispatcher, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from .config import config, set_default_commands
from .handlers import register_handlers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def on_startup(dp: Dispatcher):
    """Действия при запуске бота"""
    await set_default_commands(dp.bot)
    logger.info("Бот запущен и готов к работе!")

async def on_shutdown(dp: Dispatcher):
    """Действия при выключении бота"""
    logger.info("Бот выключается...")

def main():
    """Основная функция запуска бота"""
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(bot, storage=MemoryStorage())
    
    # Регистрируем обработчики
    register_handlers(dp)
    
    # Запускаем бота
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )

if __name__ == '__main__':
    main()
