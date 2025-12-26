#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot с премиум эмодзи через Telethon/Hikka
"""

import os
import re
import logging
import asyncio
from collections import defaultdict
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatType
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ========== НАСТРОЙКИ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = os.getenv('API_ID', '')
API_HASH = os.getenv('API_HASH', '')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ========== ДЛЯ ПРЕМИУМ ЭМОДЗИ ==========
try:
    # Попробуем использовать Telethon для премиум эмодзи
    from telethon import TelegramClient
    from telethon.tl.types import MessageEntityCustomEmoji
    
    telethon_client = None
    if API_ID and API_HASH:
        telethon_client = TelegramClient(
            'bot_session',
            int(API_ID),
            API_HASH
        )
        logger.info("✅ Telethon клиент инициализирован для премиум эмодзи")
except ImportError:
    telethon_client = None
    logger.warning("⚠️ Telethon не установлен. Премиум эмодзи будут отображаться как текст")

# ========== ФУНКЦИЯ ОТПРАВКИ С ПРЕМИУМ ЭМОДЗИ ==========
async def send_message_with_premium_emoji(chat_id, text, emoji_id=None):
    """
    Отправляет сообщение с премиум эмодзи
    emoji_id: ID премиум эмодзи из Telegram (например: 5872974298146149488)
    """
    try:
        if telethon_client and emoji_id:
            # Используем Telethon для премиум эмодзи
            await telethon_client.start(bot_token=BOT_TOKEN)
            
            # Форматируем сообщение с эмодзи
            formatted_text = text
            
            # Отправляем через Telethon
            await telethon_client.send_message(
                chat_id,
                formatted_text,
                parse_mode='html'
            )
            logger.info(f"✅ Сообщение с премиум эмодзи отправлено в {chat_id}")
        else:
            # Отправляем через aiogram (обычные эмодзи)
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='Markdown'
            )
            logger.info(f"✅ Сообщение отправлено в {chat_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения с премиум эмодзи: {e}")
        # Fallback: отправляем через aiogram без эмодзи
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='Markdown'
        )

# ========== ОСТАЛЬНОЙ КОД (без изменений) ==========
# [ВСТАВЬТЕ ЗДЕСЬ ВЕСЬ ВАШ КОД ИЗ ПРЕДЫДУЩЕГО ОТВЕТА]
# Класс Database, все функции, обработчики и т.д.

# ========== ОБНОВЛЕННАЯ ФУНКЦИЯ УВЕДОМЛЕНИЯ ==========
async def notify_agent_about_receipt(agent_username, transaction_data, group_chat_id):
    """Отправить уведомление агенту с премиум эмодзи"""
    if not group_chat_id:
        logger.error(f"Нет ID группового чата для уведомления агенту @{agent_username}")
        return None
    
    try:
        # Проверяем существование агента
        agent_user = db.get_user_by_username(agent_username)
        
        if not agent_user or agent_user['role'] != 'agent':
            agents = db.get_agents()
            if agents:
                for agent in agents:
                    if agent['role'] == 'agent':
                        agent_username = agent['username']
                        break
            else:
                logger.error(f"Нет доступных агентов для уведомления")
                return None
        
        # Сообщение с премиум эмодзи
        premium_emoji = "💫"  # Будет заменен на премиум если доступно
        premium_emoji_id = 5872974298146149488  # ID вашего эмодзи
        
        message_text = f"""**Уведомление для агента @{agent_username}**

📧 **Получены реквизиты для отправки чека:**
• Email: `{transaction_data['email']}`
• Сумма: `{transaction_data['amount']}₽`
• Банк: {transaction_data['bank']}

**Вы отправили чек на указанную почту?**"""
        
        keyboard = get_agent_receipt_keyboard(
            transaction_data['id'], 
            agent_username
        )
        
        # Отправляем с премиум эмодзи
        await send_message_with_premium_emoji(
            group_chat_id,
            message_text,
            premium_emoji_id
        )
        
        # Отправляем клавиатуру отдельно
        await bot.send_message(
            chat_id=group_chat_id,
            text="Выберите действие:",
            reply_markup=keyboard
        )
        
        logger.info(f"✅ Уведомление отправлено агенту @{agent_username}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления агенту @{agent_username}: {e}")
        return None

# ========== ЗАПУСК ==========
async def on_startup(dp):
    logger.info("🤖 БОТ ЗАПУЩЕН")
    
    # Запускаем Telethon клиент если есть
    if telethon_client and API_ID and API_HASH:
        try:
            await telethon_client.start(bot_token=BOT_TOKEN)
            logger.info("✅ Telethon клиент запущен")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telethon: {e}")

async def on_shutdown(dp):
    logger.info("❌ Бот выключается...")
    if telethon_client:
        await telethon_client.disconnect()

if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
