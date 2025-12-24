import os
from dotenv import load_dotenv

load_dotenv()

ADMINS = ['MaksimXyila', 'ar_got']  # Без @

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot.db')
    ADMINS = ADMINS
    
config = Config()
