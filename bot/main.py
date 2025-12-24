import asyncio
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from .config import config
from .handlers import register_handlers

bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

async def main():
    register_handlers(dp)
    
    # Удаляем вебхук и запускаем polling
    await bot.delete_webhook()
    await dp.start_polling()

if __name__ == '__main__':
    asyncio.run(main())
