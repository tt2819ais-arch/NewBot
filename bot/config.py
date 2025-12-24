import os
from aiogram import Bot
from aiogram.types import BotCommand

ADMINS = ['MaksimXyila', 'ar_got']  # Без @

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot.db')
    ADMINS = ADMINS
    
config = Config()

async def set_default_commands(bot: Bot):
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Помощь и инструкции"),
        BotCommand("members", "Список участников"),
        BotCommand("rub", "Установить цель на сессию"),
        BotCommand("stop", "Остановить сессию"),
    ]
    await bot.set_my_commands(commands)
