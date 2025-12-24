import re
import logging
import asyncio
from collections import defaultdict
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command

from config import config
from database import db
from keyboards import *
from states import AgentForm, SessionForm

logger = logging.getLogger(__name__)

# Хранилище временных данных пользователей
user_data_cache = defaultdict(dict)

def clear_old_data():
    """Очистка старых данных (старше 10 минут)"""
    current_time = asyncio.get_event_loop().time()
    to_delete = []
    
    for user_id, data in user_data_cache.items():
        if current_time - data.get('timestamp', 0) > 600:  # 10 минут
            to_delete.append(user_id)
    
    for user_id in to_delete:
        del user_data_cache[user_id]

async def handle_admin_message(message: types.Message):
    """Обработка сообщений администратора - собирает данные из нескольких сообщений"""
    
    # Проверяем что это админ
    username = message.from_user.username
    if username not in config.ADMINS:
        return
    
    text = message.text or ""
    user_id = message.from_user.id
    
    # Очищаем старые данные
    clear_old_data()
    
    # Инициализируем данные пользователя если нужно
    if user_id not in user_data_cache:
        user_data_cache[user_id] = {
            'phone': None,
            'amount': None,
            'bank': None,
            'email': None,
            'timestamp': asyncio.get_event_loop().time()
        }
    
    # Получаем текущие данные пользователя
    user_data = user_data_cache[user_id]
    
    # Обновляем timestamp
    user_data['timestamp'] = asyncio.get_event_loop().time()
    
    # Поиск номера телефона
    phone_pattern = r'\+7\d{10}'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        user_data['phone'] = phone_match.group()
        logger.info(f"Найден телефон: {user_data['phone']}")
    
    # Поиск суммы (форматы: 345! или !345 или просто 345)
    amount_pattern = r'[!]?(\d+)[!]?'
    amount_match = re.search(amount_pattern, text)
    if amount_match:
        user_data['amount'] = int(amount_match.group(1))
        logger.info(f"Найдена сумма: {user_data['amount']}")
    
    # Поиск банка
    bank_patterns = ['💚Сбер💚', '💛Тбанк💛']
    for pattern in bank_patterns:
        if pattern in text:
            user_data['bank'] = pattern
            logger.info(f"Найден банк: {user_data['bank']}")
            break
    
    # Поиск email
    email_pattern = r'sir\+\d+@outluk\.ru'
    email_match = re.search(email_pattern, text)
    if email_match:
        user_data['email'] = email_match.group()
        logger.info(f"Найден email: {user_data['email']}")
        
        # Когда нашли email - проверяем все данные
        await check_and_process_complete_data(message, user_id, user_data)
    else:
        # Если не email, просто обновляем данные
        user_data_cache[user_id] = user_data
        
        # Показываем что собрали на данный момент
        collected = []
        if user_data['phone']: collected.append("📞 телефон")
        if user_data['amount']: collected.append("💰 сумму")
        if user_data['bank']: collected.append("🏦 банк")
        
        if collected:
            status_msg = f"✅ Собрано: {', '.join(collected)}"
            if len(collected) == 3:
                status_msg += "\n📧 Ожидаю email для завершения..."
            await message.answer(status_msg)

async def check_and_process_complete_data(message: types.Message, user_id: int, user_data: dict):
    """Проверяет полные данные и обрабатывает их"""
    
    # Проверяем все ли данные собраны
    missing_fields = []
    if not user_data.get('phone'):
        missing_fields.append("номер телефона")
    if not user_data.get('amount'):
        missing_fields.append("сумма")
    if not user_data.get('bank'):
        missing_fields.append("банк")
    
    if missing_fields:
        await message.answer(f"⚠️ Не хватает данных: {', '.join(missing_fields)}")
        return
    
    # Все данные собраны - обрабатываем
    await process_complete_transaction(message, user_id, user_data)

async def process_complete_transaction(message: types.Message, user_id: int, user_data: dict):
    """Обработка полного набора данных"""
    
    # Получаем пользователя из БД
    user = db.get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден в базе")
        return
    
    agent_id = user[0]  # ID пользователя в БД
    
    # Получаем активную сессию
    session = db.get_active_session(agent_id)
    if not session:
        await message.answer("⚠️ Нет активной сессии. Используйте /rub сумма")
        return
    
    # Сохраняем транзакцию в БД
    transaction_id = db.add_transaction(
        agent_id,
        user_data['phone'],
        user_data['amount'],
        user_data['bank'],
        user_data['email']
    )
    
    # Обновляем сумму в сессии
    db.update_session_amount(session[0], user_data['amount'])
    
    # Получаем обновленные данные сессии
    updated_session = db.get_active_session(agent_id)
    
    # Формируем статистику
    stats_text = f"""📊 **СТАТИСТИКА ПОСЛЕ ОПЕРАЦИИ**

📞 **Телефон:** `{user_data['phone']}`
💰 **Сумма:** `{user_data['amount']}₽`
🏦 **Банк:** {user_data['bank']}
📧 **Email:** `{user_data['email']}`

📈 **СЕССИЯ:**
┣ Текущий оборот: `{updated_session[3]}₽`
┣ Цель на сессию: `{updated_session[2]}₽`
┗ Прогресс: `{min(100, int(updated_session[3] / updated_session[2] * 100))}%`"""

    # Клавиатура с кнопками
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📜 История операций", callback_data="history"),
        InlineKeyboardButton("👥 Участники", callback_data="members"),
        InlineKeyboardButton("📈 Детали сессии", callback_data="session_details")
    )
    
    await message.answer(stats_text, reply_markup=keyboard, parse_mode='Markdown')
    
    # Очищаем кэш для этого пользователя
    if user_id in user_data_cache:
        del user_data_cache[user_id]
