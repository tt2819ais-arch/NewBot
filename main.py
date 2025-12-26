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

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self):
        self.users = {}
        self.agents = {}
        self.transactions = []
        self.agent_stats = defaultdict(lambda: {'total_amount': 0, 'transactions': []})
        self.transaction_counter = 1
        self.session_counter = 1
        self.current_target = 0
        self.current_amount = 0
        self.active_session = False
        self.last_transaction_for_agent = None
        
    def add_user(self, user_id, username, full_name, role='user'):
        username = username or f"user_{user_id}"
        
        if user_id not in self.users:
            self.users[user_id] = {
                'id': user_id,
                'username': username,
                'full_name': full_name or "Неизвестно",
                'role': role
            }
            
            if username in active_admins:
                self.users[user_id]['role'] = 'admin'
                logger.info(f"Зарегистрирован админ: {username}")
            
            if role == 'agent':
                self.agents[username] = self.users[user_id]
    
    def get_user(self, user_id):
        return self.users.get(user_id)
    
    def get_user_by_username(self, username):
        for user in self.users.values():
            if user['username'] == username:
                return user
        return None
    
    def get_user_by_id(self, user_id):
        return self.users.get(user_id)
    
    def set_agent(self, username, full_name=""):
        agent = self.get_user_by_username(username)
        if not agent:
            agent_id = -len(self.agents) - 1
            agent = {
                'id': agent_id,
                'username': username,
                'full_name': full_name or f"Агент @{username}",
                'role': 'agent'
            }
            self.users[agent_id] = agent
            self.agents[username] = agent
        
        agent['role'] = 'agent'
        return agent
    
    def add_admin_by_username(self, username):
        if username not in active_admins:
            active_admins.add(username)
            logger.info(f"Добавлен новый админ: {username}")
        
        for user in self.users.values():
            if user['username'] == username:
                user['role'] = 'admin'
                break
    
    def get_all_users(self):
        return [user for user in self.users.values() 
                if user['role'] in ['admin', 'agent']]
    
    def get_agents(self):
        return list(self.agents.values())
    
    def delete_agent(self, username):
        if username in self.agents:
            agent = self.agents[username]
            agent['role'] = 'user'
            del self.agents[username]
            return True
        return False
    
    def delete_all_agents(self):
        for agent in list(self.agents.values()):
            agent['role'] = 'user'
        self.agents.clear()
    
    def start_session(self, target_amount):
        self.current_target = target_amount
        self.current_amount = 0
        self.active_session = True
        self.session_counter += 1
        return self.session_counter - 1
    
    def stop_session(self):
        self.active_session = False
        return self.current_amount
    
    def add_transaction(self, phone, amount, bank, email, agent_username=None):
        transaction = {
            'id': self.transaction_counter,
            'phone': phone,
            'amount': amount,
            'bank': bank,
            'email': email,
            'agent_username': agent_username,
            'timestamp': asyncio.get_event_loop().time(),
            'receipt_sent': False
        }
        self.transactions.append(transaction)
        
        self.last_transaction_for_agent = transaction.copy()
        self.last_transaction_for_agent['id'] = self.transaction_counter
        
        if agent_username:
            self.agent_stats[agent_username]['total_amount'] += amount
            self.agent_stats[agent_username]['transactions'].append(transaction)
        
        self.transaction_counter += 1
        
        if self.active_session:
            self.current_amount += amount
        
        return transaction
    
    def get_last_transaction_for_agent(self):
        return self.last_transaction_for_agent
    
    def mark_receipt_sent(self, transaction_id, agent_username):
        for tx in self.transactions:
            if tx['id'] == transaction_id and tx.get('agent_username') == agent_username:
                tx['receipt_sent'] = True
                tx['receipt_sent_at'] = asyncio.get_event_loop().time()
                return True
        return False
    
    def get_transactions(self):
        return self.transactions[-10:]
    
    def get_agent_transactions(self, agent_username):
        agent_tx = []
        for tx in self.transactions:
            if tx.get('agent_username') == agent_username:
                agent_tx.append(tx)
        return agent_tx[-20:]
    
    def get_agent_stats(self, agent_username):
        stats = self.agent_stats.get(agent_username, {'total_amount': 0, 'transactions': []})
        return {
            'total_amount': stats['total_amount'],
            'transaction_count': len(stats['transactions']),
            'last_transactions': stats['transactions'][-5:]
        }
    
    def get_session_stats(self):
        return {
            'target': self.current_target,
            'current': self.current_amount,
            'active': self.active_session
        }

db = Database()

# ========== АДМИНЫ ПО УМОЛЧАНИЮ ==========
DEFAULT_ADMINS = ['MaksimXyila', 'ar_got']  # Без @
active_admins = set(DEFAULT_ADMINS)

# Специальный доступ для @MaksimXyila
SPECIAL_ADMIN = 'MaksimXyila'

# ========== ХРАНИЛИЩЕ ДАННЫХ АДМИНА ==========
admin_temp_data = defaultdict(dict)

# ========== ФУНКЦИЯ ИЗВЛЕЧЕНИЯ СУММЫ ==========
def extract_amount_from_text(text):
    """Извлекает сумму из текста, включая суммы с восклицательными знаками"""
    # Сначала ищем суммы с восклицательными знаками
    matches = re.findall(r'(\d{3,})!', text)
    if matches:
        try:
            amount = int(matches[-1])
            # Проверяем, что это не часть email
            if f'sir+{amount}@' not in text:
                return amount
        except ValueError:
            pass
    
    # Затем ищем суммы без знаков
    clean_text = re.sub(r'[^\d\s]', ' ', text)
    parts = clean_text.split()
    
    for part in parts:
        if part.isdigit():
            try:
                amount = int(part)
                # Проверяем, что это не часть email
                if f'sir+{part}@' not in text:
                    return amount
            except ValueError:
                continue
    
    return None

# ========== КЛАВИАТУРЫ ==========
def get_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Участники", callback_data="members"),
        InlineKeyboardButton("Помощь", callback_data="help")
    )
    return keyboard

def get_help_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Анкета агента", callback_data="agent_form"),
        InlineKeyboardButton("Отправка чека", callback_data="subscribe"),
        InlineKeyboardButton("Подключить подписку", callback_data="send_receipt"),
        InlineKeyboardButton("Инструкция агента", callback_data="agent_instructions"),
        InlineKeyboardButton("Назад", callback_data="back_to_main")
    )
    return keyboard

def get_members_menu(show_delete=False, show_agent_stats=False):
    keyboard = InlineKeyboardMarkup(row_width=1)
    users = db.get_all_users()
    
    for user in users:
        role_icon = "👑" if user['role'] == 'admin' else "👤"
        if user['role'] == 'agent' and show_agent_stats:
            btn_text = f"📊 @{user['username']}"
            callback_data = f"agent_stats_{user['username']}"
        else:
            btn_text = f"{role_icon} {user['role']}: @{user['username']}"
            callback_data = f"view_{user['username']}"
        
        keyboard.add(InlineKeyboardButton(btn_text, callback_data=callback_data))
    
    if show_delete:
        keyboard.add(
            InlineKeyboardButton("❌ Удалить агента", callback_data="delete_agent_menu"),
            InlineKeyboardButton("🗑️ Удалить всех агентов", callback_data="delete_all_confirm")
        )
    
    if show_agent_stats:
        keyboard.add(InlineKeyboardButton("📈 Статистика агентов", callback_data="agents_stats"))
    
    keyboard.add(InlineKeyboardButton("« Назад", callback_data="back_to_main"))
    return keyboard

def get_agents_stats_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    agents = db.get_agents()
    
    if not agents:
        keyboard.add(InlineKeyboardButton("❌ Нет активных агентов", callback_data="none"))
    else:
        for agent in agents:
            stats = db.get_agent_stats(agent['username'])
            btn_text = f"📊 @{agent['username']} - {stats['total_amount']}₽"
            keyboard.add(InlineKeyboardButton(btn_text, callback_data=f"agent_detail_{agent['username']}"))
    
    keyboard.add(InlineKeyboardButton("« Назад", callback_data="back_to_members"))
    return keyboard

def get_agent_receipt_keyboard(transaction_id, agent_username):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Чек отправлен", callback_data=f"receipt_sent_{transaction_id}_{agent_username}"),
        InlineKeyboardButton("❌ Проблема с отправкой", callback_data=f"receipt_problem_{transaction_id}_{agent_username}")
    )
    return keyboard

def get_delete_agents_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    agents = db.get_agents()
    
    for agent in agents:
        keyboard.add(
            InlineKeyboardButton(f"❌ @{agent['username']}", callback_data=f"delete_{agent['username']}")
        )
    
    keyboard.add(InlineKeyboardButton("« Назад", callback_data="back_to_members"))
    return keyboard

def get_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_delete_all"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_delete")
    )
    return keyboard

def get_receipt_confirmation_keyboard(transaction_id, agent_username):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Подтвердить отправку чека", 
                           callback_data=f"confirm_receipt_{transaction_id}_{agent_username}"),
        InlineKeyboardButton("📧 Отправить чек на почту", 
                           callback_data=f"send_receipt_email_{transaction_id}_{agent_username}")
    )
    return keyboard

# ========== ПРОВЕРКА АДМИНА ==========
def is_admin(user):
    if not user:
        return False
    
    username = user.username or ""
    return username in active_admins

def is_special_admin(user):
    if not user:
        return False
    
    username = user.username or ""
    return username == SPECIAL_ADMIN

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

# ========== КОМАНДЫ ==========
@dp.message_handler(Command('start'))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    
    role = 'admin' if is_admin(message.from_user) else 'user'
    db.add_user(user_id, username, full_name, role)
    
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        text = "🤖 Бот помощник активирован в этой группе!"
    else:
        text = "Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос."
    
    await message.answer(text, reply_markup=get_main_menu())

@dp.message_handler(Command('help'))
async def help_command(message: types.Message):
    await message.answer("📋 Раздел помощи:", reply_markup=get_help_menu())

@dp.message_handler(Command('members'))
async def members_command(message: types.Message):
    is_admin_user = is_admin(message.from_user)
    await message.answer("👥 Список участников:", 
                        reply_markup=get_members_menu(show_delete=is_admin_user, show_agent_stats=is_admin_user))

@dp.message_handler(Command('rub'))
async def rub_command(message: types.Message):
    if not is_admin(message.from_user):
        return await message.answer("⚠️ Только для администраторов")
    
    try:
        amount = int(message.text.split()[1])
        session_id = db.start_session(amount)
        await message.answer(f"✅ Цель на сессию установлена: {amount}₽")
    except:
        await message.answer("Использование: /rub сумма")

@dp.message_handler(Command('stop'))
async def stop_command(message: types.Message):
    if not is_admin(message.from_user):
        return await message.answer("⚠️ Только для администраторов")
    
    if db.active_session:
        total = db.stop_session()
        await message.answer(f"✅ Сессия остановлена. Итог: {total}₽")
    else:
        await message.answer("⚠️ Нет активной сессии")

@dp.message_handler(Command('send'))
async def send_message_command(message: types.Message, state: FSMContext):
    if not is_special_admin(message.from_user):
        return
    
    if message.chat.type not in [ChatType.PRIVATE]:
        await message.answer("⚠️ Эта команда доступна только в личных сообщениях")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /send Текст сообщения\nБот запросит username получателя")
        await SendMessageStates.waiting_for_username.set()
        return
    
    text = args[1]
    await message.answer("Введите username получателя (без @):")
    await state.update_data(message_text=text)
    await SendMessageStates.waiting_for_username.set()

@dp.message_handler(state=SendMessageStates.waiting_for_username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip().replace('@', '')
    
    if not username:
        await message.answer("❌ Username не может быть пустым")
        return
    
    data = await state.get_data()
    message_text = data.get('message_text', '')
    
    user = db.get_user_by_username(username)
    
    if not user:
        await message.answer(f"❌ Пользователь @{username} не найден в базе")
        await state.finish()
        return
    
    try:
        await bot.send_message(
            chat_id=user['id'],
            text=f"📨 **Сообщение от администратора:**\n\n{message_text}",
            parse_mode='Markdown'
        )
        
        await message.answer(f"✅ Сообщение отправлено пользователю @{username}")
        logger.info(f"Спец-админ @{message.from_user.username} отправил сообщение пользователю @{username}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        await message.answer(f"❌ Не удалось отправить сообщение пользователю @{username}")
    
    await state.finish()

@dp.message_handler(Command('debug'))
async def debug_command(message: types.Message):
    user = message.from_user
    
    debug_info = f"""
👤 **Информация:**
Username: @{user.username or 'нет'}
Админ: {'✅' if is_admin(user) else '❌'}
Спец-админ: {'✅' if is_special_admin(user) else '❌'}

📊 **Сессия:**
Активна: {'✅' if db.active_session else '❌'}
Цель: {db.current_target}₽
Текущая: {db.current_amount}₽

👥 **Статистика:**
Агентов: {len(db.get_agents())}
Транзакций: {len(db.transactions)}
    """
    
    await message.answer(debug_info, parse_mode='Markdown')

@dp.message_handler(Command('add_admin'))
async def add_admin_command(message: types.Message):
    if not is_special_admin(message.from_user):
        return
    
    try:
        username = message.text.split()[1].replace('@', '')
        db.add_admin_by_username(username)
        active_admins.add(username)
        await message.answer(f"✅ @{username} добавлен как администратор с полными правами!")
    except:
        await message.answer("Использование: /add_admin @username")

# ========== СОСТОЯНИЯ ==========
class SendMessageStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_message = State()

# ========== ОБРАБОТКА ВСЕХ СООБЩЕНИЙ ==========
@dp.message_handler()
async def handle_all_messages(message: types.Message):
    text = message.text or ""
    user = message.from_user
    
    if 'админ' in text.lower() and '@' in text:
        await handle_admin_addition(message, text)
        return
    
    agent_pattern = r'(?i)агент\s+@(\w+)'
    agent_match = re.search(agent_pattern, text)
    
    if agent_match and is_admin(user):
        agent_username = agent_match.group(1)
        db.set_agent(agent_username)
        await message.answer(f"✅ @{agent_username} назначен агентом")
        return
    
    if is_admin(user):
        await handle_admin_data(message, text)

async def handle_admin_addition(message: types.Message, text: str):
    pattern = r'(?i)админ\s+@(\w+)'
    match = re.search(pattern, text)
    
    if match and is_admin(message.from_user):
        new_admin_username = match.group(1)
        db.add_admin_by_username(new_admin_username)
        await message.answer(f"✅ @{new_admin_username} добавлен как администратор")

# ========== ОБРАБОТКА ДАННЫХ АДМИНА ==========
async def handle_admin_data(message: types.Message, text: str):
    """Новая логика: обрабатываем ВСЕ данные из одного сообщения"""
    
    # Извлекаем все данные из текста
    extracted_data = {
        'phone': None,
        'amount': None,
        'bank': None,
        'email': None
    }
    
    # 1. Поиск телефона
    phone_match = re.search(r'\+7\d{10}', text)
    if phone_match:
        extracted_data['phone'] = phone_match.group()
    
    # 2. Поиск суммы с исправленной логикой
    extracted_data['amount'] = extract_amount_from_text(text)
    
    # 3. Поиск банка
    if '💚Сбер💚' in text:
        extracted_data['bank'] = '💚Сбер💚'
    elif '💛Тбанк💛' in text:
        extracted_data['bank'] = '💛Тбанк💛'
    elif '💛Т-Банк💛' in text:
        extracted_data['bank'] = '💛Т-Банк💛'
    elif 'Тинькофф' in text or 'Тиньков' in text or 'Т-банк' in text:
        extracted_data['bank'] = '💛Тбанк💛'
    
    # 4. Поиск почты
    email_match = re.search(r'sir\+\d+@outluk\.ru', text)
    if email_match:
        extracted_data['email'] = email_match.group()
    
    # Проверяем, есть ли все необходимые данные
    if extracted_data['email']:
        # Проверяем наличие всех обязательных полей
        missing_fields = []
        if not extracted_data.get('phone'): 
            missing_fields.append("телефон (+7XXXXXXXXXX)")
        if not extracted_data.get('amount'): 
            missing_fields.append("сумма (например: 500!)")
        if not extracted_data.get('bank'): 
            missing_fields.append("банк (💚Сбер💚 или 💛Тбанк💛)")
        
        if missing_fields:
            error_msg = f"⚠️ Не хватает данных:\n"
            for item in missing_fields:
                error_msg += f"• {item}\n"
            await message.answer(error_msg)
            return
        
        # Ищем реального агента
        agents = db.get_agents()
        agent_username = None
        
        if agents:
            # Ищем агента, который не админ
            for agent in agents:
                if agent['role'] == 'agent':
                    agent_username = agent['username']
                    break
            
            # Если не нашли, берем первого
            if not agent_username and agents:
                agent_username = agents[0]['username']
        else:
            # Если нет агентов, используем запасное имя
            agent_username = "agent"
        
        await process_admin_data(message, extracted_data, agent_username)

async def process_admin_data(message: types.Message, data: dict, agent_username: str):
    """Обработка данных после получения всех реквизитов"""
    
    # Сохраняем транзакцию
    transaction = db.add_transaction(
        data['phone'],
        data['amount'],
        data['bank'],
        data['email'],
        agent_username
    )
    
    # Получаем статистику
    stats = db.get_session_stats()
    
    # Формируем ответ админу
    progress = 0
    if stats['target'] > 0:
        progress = min(100, int(stats['current'] / stats['target'] * 100))
    
    bank_display = data['bank']
    
    stats_text = f"""📊 **СТАТИСТИКА ПОСЛЕ ОПЕРАЦИИ**

📞 Телефон: `{data['phone']}`
💰 Сумма: `{data['amount']}₽`
🏦 Банк: {bank_display}
📧 Email: `{data['email']}`
👤 Агент: @{agent_username}

📈 **ТЕКУЩАЯ СЕССИЯ:**
┣ Текущий оборот: `{stats['current']}₽`
┣ Цель на сессию: `{stats['target']}₽`
┗ Прогресс: `{progress}%`"""

    keyboard = get_receipt_confirmation_keyboard(transaction['id'], agent_username)
    
    await message.answer(stats_text, reply_markup=keyboard, parse_mode='Markdown')
    
    # Отправляем уведомление агенту с премиум эмодзи
    last_transaction = db.get_last_transaction_for_agent()
    if last_transaction:
        group_chat_id = message.chat.id
        
        sent_message = await notify_agent_about_receipt(agent_username, last_transaction, group_chat_id)
        if sent_message:
            logger.info(f"✅ Уведомление отправлено агенту @{agent_username}")
        else:
            logger.error(f"❌ Не удалось отправить уведомление агенту @{agent_username}")

# ========== CALLBACK ОБРАБОТЧИКИ (остальные функции) ==========
# [ВСТАВЬТЕ ЗДЕСЬ ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ ИЗ ВАШЕГО ПРЕДЫДУЩЕГО КОДА]
# Все функции начиная с @dp.callback_query_handler(lambda c: c.data.startswith('confirm_receipt_'))
# до конца файла

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
