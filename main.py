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

# ========== АДМИНЫ ПО УМОЛЧАНИЮ ==========
DEFAULT_ADMINS = ['MaksimXyila', 'ar_got']  # Без @
active_admins = set(DEFAULT_ADMINS)

# Специальный доступ для @MaksimXyila
SPECIAL_ADMIN = 'MaksimXyila'

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ========== СОСТОЯНИЯ ==========
class SendMessageStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_message = State()

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
            'timestamp': asyncio.get_event_loop().time()
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

# ========== ХРАНИЛИЩЕ ДАННЫХ АДМИНА ==========
admin_temp_data = defaultdict(dict)

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
        InlineKeyboardButton("❌ Проблема с отправкой", callback_data=f"receipt_problem_{agent_username}")
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

# ========== ИЗВЛЕЧЕНИЕ СУММЫ ==========
def extract_amount_from_text(text):
    clean_text = re.sub(r'[^\d!]', ' ', text)
    parts = clean_text.split()
    
    for part in parts:
        match = re.match(r'^!?(\d+)!?$', part)
        if match:
            amount_str = match.group(1)
            if 'sir+' in text and amount_str in text.split('sir+')[1].split('@')[0]:
                continue
            try:
                return int(amount_str)
            except ValueError:
                continue
    
    return None

# ========== ОТПРАВКА УВЕДОМЛЕНИЯ АГЕНТУ ==========
async def notify_agent_about_receipt(agent_username, transaction_data, group_chat_id):
    """Отправить уведомление агенту в ГРУППОВОЙ чат"""
    if not group_chat_id:
        logger.error(f"Нет ID группового чата для уведомления агенту @{agent_username}")
        return False
    
    try:
        # Ищем реального агента по username (не админа!)
        agent_user = None
        for user_data in db.users.values():
            if user_data['username'] == agent_username and user_data['role'] == 'agent':
                agent_user = user_data
                break
        
        # Если агент не найден или это админ, берем первого доступного агента
        if not agent_user:
            agents = db.get_agents()
            if agents:
                # Берем первого агента из списка (не админа!)
                for agent in agents:
                    if agent['role'] == 'agent':
                        # Проверяем что это не админ
                        if agent['username'] not in DEFAULT_ADMINS:
                            agent_username = agent['username']
                            break
            else:
                logger.error(f"Нет доступных агентов для уведомления")
                return False
        
        message_text = f"""👤 **Уведомление для агента @{agent_username}**

📧 Получены реквизиты для отправки чека:
• Email: `{transaction_data['email']}`
• Сумма: `{transaction_data['amount']}₽`
• Банк: {transaction_data['bank']}

**Вы отправили чек на указанную почту?**"""

        keyboard = get_agent_receipt_keyboard(
            transaction_data['id'], 
            agent_username
        )
        
        # Отправляем в ГРУППОВОЙ чат (ТОТ ЖЕ ЧАТ, ГДЕ АДМИН ОТПРАВИЛ ДАННЫЕ)
        await bot.send_message(
            chat_id=group_chat_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Уведомление отправлено агенту @{agent_username} в групповой чат {group_chat_id}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления агенту @{agent_username}: {e}")
        return False

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
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    
    if user_id not in admin_temp_data:
        admin_temp_data[user_id] = {
            'phone': None,
            'amount': None,
            'bank': None,
            'email': None,
            'timestamp': asyncio.get_event_loop().time()
        }
    
    data = admin_temp_data[user_id]
    data['timestamp'] = asyncio.get_event_loop().time()
    
    phone_match = re.search(r'\+7\d{10}', text)
    if phone_match:
        data['phone'] = phone_match.group()
    
    amount = extract_amount_from_text(text)
    if amount is not None:
        if 'sir+' in text:
            email_match = re.search(r'sir\+(\d+)@', text)
            if email_match:
                email_digits = email_match.group(1)
                if str(amount) == email_digits:
                    amount = None
        
        if amount is not None:
            data['amount'] = amount
    
    # ПОИСК БАНКА - ДОБАВЛЕН НОВЫЙ ТРИГГЕР
    if '💚Сбер💚' in text:
        data['bank'] = '💚Сбер💚'
    elif '💛Тбанк💛' in text:
        data['bank'] = '💛Тбанк💛'
    elif '💛Т-Банк💛' in text:  # НОВЫЙ ТРИГГЕР!
        data['bank'] = '💛Т-Банк💛'
    
    email_match = re.search(r'sir\+\d+@outluk\.ru', text)
    if email_match:
        data['email'] = email_match.group()
        
        # Ищем реального агента (не админа!)
        agents = db.get_agents()
        agent_username = None
        
        if agents:
            # Ищем агента, который НЕ является админом
            for agent in agents:
                if agent['username'] != username and agent['role'] == 'agent':
                    agent_username = agent['username']
                    break
            
            # Если не нашли, берем первого агента (даже если это админ)
            if not agent_username and agents:
                agent_username = agents[0]['username']
        else:
            # Если нет агентов, используем запасное имя
            agent_username = "agent"
        
        await process_admin_data(message, user_id, data, username, agent_username)
        return
    
    current_time = asyncio.get_event_loop().time()
    for uid in list(admin_temp_data.keys()):
        if current_time - admin_temp_data[uid]['timestamp'] > 600:
            del admin_temp_data[uid]

async def process_admin_data(message: types.Message, user_id: int, data: dict, admin_username: str, agent_username: str):
    """Обработка данных после получения email"""
    
    missing = []
    if not data.get('phone'): 
        missing.append("номер телефона (+7XXXXXXXXXX)")
    if not data.get('amount'): 
        missing.append("сумма (например: 9500!)")
    if not data.get('bank'): 
        missing.append("банк (💚Сбер💚 или 💛Тбанк💛 или 💛Т-Банк💛)")
    
    if missing:
        error_msg = f"⚠️ Не хватает данных:\n"
        for item in missing:
            error_msg += f"• {item}\n"
        error_msg += "\nОтправьте недостающие данные."
        await message.answer(error_msg)
        return
    
    # Сохраняем транзакцию с реальным агентом
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
    
    # Определяем правильное отображение банка
    bank_display = data['bank']
    if data['bank'] == '💛Т-Банк💛':
        bank_display = '💛Т-Банк💛'
    
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

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📜 История операций", callback_data="history"),
        InlineKeyboardButton("📊 Статистика агентов", callback_data="agents_stats")
    )
    
    await message.answer(stats_text, reply_markup=keyboard, parse_mode='Markdown')
    
    # Отправляем уведомление РЕАЛЬНОМУ АГЕНТУ в ГРУППОВОЙ чат
    last_transaction = db.get_last_transaction_for_agent()
    if last_transaction:
        group_chat_id = message.chat.id
        
        success = await notify_agent_about_receipt(agent_username, last_transaction, group_chat_id)
        if success:
            logger.info(f"✅ Уведомление отправлено реальному агенту @{agent_username}")
        else:
            await message.answer(f"⚠️ Не удалось отправить уведомление агенту @{agent_username}")
    
    # Очищаем кэш
    if user_id in admin_temp_data:
        del admin_temp_data[user_id]

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query_handler(lambda c: c.data.startswith('receipt_sent_'))
async def handle_receipt_sent(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    if len(parts) >= 4:
        transaction_id = int(parts[2])
        agent_username = parts[3]
        
        # Проверяем что нажал именно тот агент
        if callback.from_user.username != agent_username:
            await callback.answer("❌ Это уведомление не для вас")
            return
        
        # Отмечаем чек как отправленный
        success = db.mark_receipt_sent(transaction_id, agent_username)
        
        if success:
            await callback.message.edit_text(
                f"✅ @{agent_username} подтвердил отправку чека\n\n"
                f"Чек успешно отправлен на почту!",
                parse_mode='Markdown'
            )
            
            # Уведомляем админов
            for admin_username in active_admins:
                admin_user = db.get_user_by_username(admin_username)
                if admin_user and 'id' in admin_user:
                    try:
                        await bot.send_message(
                            chat_id=admin_user['id'],
                            text=f"✅ Агент @{agent_username} подтвердил отправку чека по транзакции #{transaction_id}",
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Ошибка уведомления админа @{admin_username}: {e}")
            
            await callback.answer("✅ Чек отмечен как отправленный!")
        else:
            await callback.answer("❌ Ошибка при отметке чека")
    else:
        await callback.answer("❌ Ошибка обработки")

@dp.callback_query_handler(lambda c: c.data.startswith('receipt_problem_'))
async def handle_receipt_problem(callback: types.CallbackQuery):
    agent_username = callback.data.split('_')[2]
    
    if callback.from_user.username != agent_username:
        await callback.answer("❌ Это уведомление не для вас")
        return
    
    await callback.message.edit_text(
        f"⚠️ @{agent_username} сообщил о проблеме с отправкой чека\n\n"
        f"Администраторы уведомлены о проблеме.",
        parse_mode='Markdown'
    )
    
    # Уведомляем админов о проблеме
    for admin_username in active_admins:
        admin_user = db.get_user_by_username(admin_username)
        if admin_user and 'id' in admin_user:
            try:
                await bot.send_message(
                    chat_id=admin_user['id'],
                    text=f"⚠️ Агент @{agent_username} сообщил о проблеме с отправкой чека!",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления админа @{admin_username}: {e}")
    
    await callback.answer("✅ Проблема сообщена администраторам")

@dp.callback_query_handler(lambda c: c.data == 'members')
async def show_members(callback: types.CallbackQuery):
    is_admin_user = is_admin(callback.from_user)
    await callback.message.edit_text(
        "👥 Список участников:",
        reply_markup=get_members_menu(show_delete=is_admin_user, show_agent_stats=is_admin_user)
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'agents_stats')
async def show_agents_stats(callback: types.CallbackQuery):
    agents = db.get_agents()
    
    if not agents:
        await callback.message.edit_text(
            "📊 **Статистика агентов:**\n\n❌ Нет активных агентов",
            reply_markup=get_agents_stats_menu()
        )
    else:
        stats_text = "📊 **Статистика агентов:**\n\n"
        for agent in agents:
            stats = db.get_agent_stats(agent['username'])
            stats_text += f"👤 **@{agent['username']}**\n"
            stats_text += f"   Всего оборот: `{stats['total_amount']}₽`\n"
            stats_text += f"   Операций: `{stats['transaction_count']}`\n\n"
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=get_agents_stats_menu(),
            parse_mode='Markdown'
        )
    
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('agent_detail_'))
async def show_agent_detail(callback: types.CallbackQuery):
    agent_username = callback.data.split('agent_detail_')[1]
    stats = db.get_agent_stats(agent_username)
    transactions = db.get_agent_transactions(agent_username)
    
    detail_text = f"""📊 **Детальная статистика агента @{agent_username}**

💰 **Общий оборот:** `{stats['total_amount']}₽`
📈 **Всего операций:** `{stats['transaction_count']}`

📜 **Последние операции:**\n"""
    
    if transactions:
        for i, tx in enumerate(reversed(transactions[-10:]), 1):
            receipt_status = "✅" if tx.get('receipt_sent') else "⏳"
            # Правильное отображение банка
            bank_display = tx['bank']
            if tx['bank'] == '💛Т-Банк💛':
                bank_display = '💛Т-Банк💛'
            detail_text += f"{i}. {receipt_status} `{tx['phone']}` - `{tx['amount']}₽` - {bank_display}\n"
    else:
        detail_text += "\n📭 Операций пока нет"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("« Назад к статистике", callback_data="agents_stats"))
    
    await callback.message.edit_text(
        detail_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('agent_stats_'))
async def show_agent_stats(callback: types.CallbackQuery):
    agent_username = callback.data.split('agent_stats_')[1]
    stats = db.get_agent_stats(agent_username)
    
    stats_text = f"""📊 **Статистика агента @{agent_username}**

💰 Общий оборот: `{stats['total_amount']}₽`
📈 Всего операций: `{stats['transaction_count']}`

📜 Последние 5 операций:\n"""
    
    if stats['last_transactions']:
        for i, tx in enumerate(reversed(stats['last_transactions']), 1):
            receipt_status = "✅" if tx.get('receipt_sent') else "⏳"
            stats_text += f"{i}. {receipt_status} `{tx['phone']}` - `{tx['amount']}₽`\n"
    else:
        stats_text += "\n📭 Операций пока нет"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📋 Подробнее", callback_data=f"agent_detail_{agent_username}"))
    keyboard.add(InlineKeyboardButton("« Назад к списку", callback_data="members"))
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'help')
async def show_help(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Раздел помощи:", reply_markup=get_help_menu())
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'agent_form')
async def show_agent_form(callback: types.CallbackQuery):
    form_text = """📝 **Обязательная анкета для регистрации агента:**

1. ФИО:
2. Номер карты:
3. Номер счета:
4. Номер телефона:
5. Скриншот истории трат за Ноябрь/Декабрь.

Отправь данные одним сообщением."""
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📸 Пример скриншота", callback_data="example_screenshot"))
    
    await callback.message.answer(form_text, reply_markup=keyboard, parse_mode='Markdown')
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'example_screenshot')
async def show_example(callback: types.CallbackQuery):
    screenshot_files = [
        'example_screenshot.jpg',
        'example_screenshot.png',
        'example.jpg',
        'screenshot_example.jpg',
        'media/example_screenshot.png'
    ]
    
    for file_path in screenshot_files:
        if os.path.exists(file_path):
            try:
                photo = types.InputFile(file_path)
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=photo,
                    caption="📸 Пример скриншота истории трат"
                )
                await callback.answer()
                return
            except Exception as e:
                logger.error(f"Ошибка отправки фото: {e}")
    
    await callback.answer("📸 Пример скриншота будет добавлен позже")

@dp.callback_query_handler(lambda c: c.data == 'agent_instructions')
async def show_instructions(callback: types.CallbackQuery):
    instructions = """📋 **Инструкция агента:**

Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.

1. Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.
2. Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.
3. После перевода отправляешь квитанцию на указанную почту."""
    
    await callback.message.answer(instructions, parse_mode='Markdown')
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data in ['subscribe', 'send_receipt'])
async def send_video(callback: types.CallbackQuery):
    # ВИДЕО ИСПРАВЛЕНО! Теперь точно правильно:
    # "Отправка чека" → check.mp4 (видео про отправку чека)
    # "Подключить подписку" → instructions.mp4 (видео про подключение)
    
    if callback.data == 'subscribe':  # Кнопка "Отправка чека"
        video_filename = 'check.mp4'  # ПРАВИЛЬНО!
        caption = "📹 Инструкция по отправке чека"
    else:  # send_receipt - Кнопка "Подключить подписку"
        video_filename = 'instructions.mp4'  # ПРАВИЛЬНО!
        caption = "📹 Инструкция по подключению подписки"
    
    logger.info(f"Отправка видео: {video_filename} для кнопки {callback.data}")
    
    try:
        # Пробуем разные пути
        video_paths = [
            video_filename,               # В корне проекта
            f"media/{video_filename}",    # В папке media/
            f"/app/{video_filename}",     # В Docker контейнере
            f"/app/media/{video_filename}"
        ]
        
        video_file = None
        for path in video_paths:
            if os.path.exists(path):
                video_file = types.InputFile(path)
                logger.info(f"Найдено видео по пути: {path}")
                break
        
        if video_file:
            await bot.send_video(
                chat_id=callback.message.chat.id,
                video=video_file,
                caption=caption
            )
            logger.info(f"✅ Видео отправлено: {video_filename}")
        else:
            await callback.message.answer(f"📹 {caption} (файл {video_filename} не найден)")
            
    except Exception as e:
        logger.error(f"Ошибка отправки видео: {e}")
        await callback.message.answer(f"📹 {caption}")
    
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'history')
async def show_history(callback: types.CallbackQuery):
    transactions = db.get_transactions()
    
    if not transactions:
        await callback.answer("📭 История операций пуста")
        return
    
    history_text = "📜 **История операций:**\n\n"
    for i, trans in enumerate(reversed(transactions), 1):
        receipt_status = "✅" if trans.get('receipt_sent') else "⏳"
        agent_info = f" @{trans.get('agent_username', 'unknown')}" if trans.get('agent_username') else ""
        
        # Правильное отображение банка
        bank_display = trans['bank']
        if trans['bank'] == '💛Т-Банк💛':
            bank_display = '💛Т-Банк💛'
        
        history_text += f"{i}. {receipt_status} `{trans['phone']}` - `{trans['amount']}₽` - {bank_display}{agent_info}\n"
    
    await callback.message.answer(history_text, parse_mode='Markdown')
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'delete_agent_menu')
async def show_delete_menu(callback: types.CallbackQuery):
    agents = db.get_agents()
    if not agents:
        await callback.answer("❌ Нет агентов для удаления")
        return
    
    await callback.message.edit_text(
        "Выберите агента для удаления:",
        reply_markup=get_delete_agents_menu()
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'delete_all_confirm')
async def confirm_delete_all(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить ВСЕХ агентов?",
        reply_markup=get_confirmation_keyboard()
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('delete_') and c.data != 'delete_all_confirm')
async def delete_single_agent(callback: types.CallbackQuery):
    username = callback.data.split('_')[1]
    if db.delete_agent(username):
        await callback.answer(f"✅ Агент @{username} удален")
    else:
        await callback.answer("❌ Агент не найден")
    
    await show_members(callback)

@dp.callback_query_handler(lambda c: c.data == 'confirm_delete_all')
async def delete_all_agents(callback: types.CallbackQuery):
    db.delete_all_agents()
    await callback.answer("✅ Все агенты удалены")
    await show_members(callback)

@dp.callback_query_handler(lambda c: c.data in ['back_to_main', 'cancel_delete'])
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос.",
        reply_markup=get_main_menu()
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'back_to_members')
async def back_to_members(callback: types.CallbackQuery):
    is_admin_user = is_admin(callback.from_user)
    await callback.message.edit_text(
        "👥 Список участников:",
        reply_markup=get_members_menu(show_delete=is_admin_user, show_agent_stats=is_admin_user)
    )
    await callback.answer()

# ========== ЗАПУСК ==========
async def on_startup(dp: Dispatcher):
    commands = [
        types.BotCommand("start", "Запустить бота"),
        types.BotCommand("help", "Помощь и инструкции"),
        types.BotCommand("members", "Список участников"),
        types.BotCommand("rub", "Установить цель на сессию"),
        types.BotCommand("stop", "Остановить сессию"),
        types.BotCommand("debug", "Отладка"),
    ]
    
    # Специальная команда только для @MaksimXyila
    if SPECIAL_ADMIN in active_admins:
        commands.append(types.BotCommand("send", "Отправить сообщение пользователю"))
    
    await bot.set_my_commands(commands)
    
    logger.info("=" * 60)
    logger.info("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    logger.info(f"Админы: {', '.join(active_admins)}")
    logger.info(f"Спец-админ: @{SPECIAL_ADMIN}")
    logger.info("=" * 60)

async def on_shutdown(dp: Dispatcher):
    logger.info("❌ Бот выключается...")

if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
