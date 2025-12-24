import os
import re
import logging
import asyncio
from collections import defaultdict
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== НАСТРОЙКИ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMINS = ['MaksimXyila', 'ar_got']

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ========== БАЗА ДАННЫХ В ПАМЯТИ ==========
class SimpleDB:
    def __init__(self):
        self.users = {}
        self.transactions = []
        self.sessions = {}
        self.user_counter = 1
        self.transaction_counter = 1
    
    def add_user(self, user_id, username, full_name, role='user'):
        if user_id not in self.users:
            self.users[user_id] = {
                'id': self.user_counter,
                'user_id': user_id,
                'username': username,
                'full_name': full_name,
                'role': role,
                'card_number': None,
                'account_number': None,
                'phone_number': None,
                'is_active': True
            }
            self.user_counter += 1
        return self.users[user_id]['id']
    
    def get_user(self, user_id):
        return self.users.get(user_id)
    
    def update_user_role(self, user_id, role):
        if user_id in self.users:
            self.users[user_id]['role'] = role
    
    def get_all_users(self):
        return [user for user in self.users.values() 
                if user['role'] in ['admin', 'agent']]
    
    def get_agents(self):
        return [user for user in self.users.values() 
                if user['role'] == 'agent' and user['is_active']]
    
    def add_transaction(self, agent_id, phone, amount, bank, email):
        transaction = {
            'id': self.transaction_counter,
            'agent_id': agent_id,
            'phone_number': phone,
            'amount': amount,
            'bank': bank,
            'email': email,
            'timestamp': asyncio.get_event_loop().time()
        }
        self.transactions.append(transaction)
        self.transaction_counter += 1
        return transaction['id']
    
    def get_transactions(self, agent_id=None):
        if agent_id:
            return [t for t in self.transactions if t['agent_id'] == agent_id]
        return self.transactions
    
    def create_session(self, agent_id, target_amount):
        # Деактивируем старые сессии
        for session in self.sessions.values():
            if session['agent_id'] == agent_id:
                session['is_active'] = False
        
        session_id = len(self.sessions) + 1
        self.sessions[session_id] = {
            'id': session_id,
            'agent_id': agent_id,
            'target_amount': target_amount,
            'current_amount': 0,
            'is_active': True,
            'start_time': asyncio.get_event_loop().time()
        }
        return session_id
    
    def get_active_session(self, agent_id):
        for session in self.sessions.values():
            if session['agent_id'] == agent_id and session['is_active']:
                return session
        return None
    
    def update_session_amount(self, session_id, amount):
        if session_id in self.sessions:
            self.sessions[session_id]['current_amount'] += amount

db = SimpleDB()

# ========== ХРАНИЛИЩЕ ВРЕМЕННЫХ ДАННЫХ ==========
user_data_cache = defaultdict(dict)

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
        InlineKeyboardButton("Инструкция агента", callback_data="agent_instructions"),
        InlineKeyboardButton("Назад", callback_data="back_to_main")
    )
    return keyboard

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    
    role = 'admin' if username in ADMINS else 'user'
    db.add_user(user_id, username, full_name, role)
    
    if message.chat.type in ['group', 'supergroup']:
        text = "🤖 Бот помощник активирован в этой группе!"
    else:
        text = "Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос."
    
    await message.answer(text, reply_markup=get_main_menu())

@dp.message_handler(commands=['rub'])
async def rub_command(message: types.Message):
    if message.from_user.username not in ADMINS:
        return await message.answer("⚠️ Только для администраторов")
    
    try:
        amount = int(message.text.split()[1])
        user = db.get_user(message.from_user.id)
        if user:
            session_id = db.create_session(user['id'], amount)
            await message.answer(f"✅ Цель на сессию установлена: {amount}₽")
    except:
        await message.answer("Использование: /rub сумма")

@dp.message_handler(commands=['test'])
async def test_command(message: types.Message):
    await message.answer("✅ Бот работает! Отправьте:\n1. +79019786832\n2. 345!\n3. 💛Тбанк💛\n4. sir+982851@outluk.ru")

# ========== СОБИРАЕМ ДАННЫЕ ИЗ СООБЩЕНИЙ ==========
@dp.message_handler()
async def handle_all_messages(message: types.Message):
    username = message.from_user.username
    text = message.text or ""
    
    # 1. Если это админ - собираем данные
    if username in ADMINS:
        await handle_admin_data(message, text)
    
    # 2. Если это команда назначения агента
    elif 'агент' in text.lower() and '@' in text:
        await handle_agent_assignment(message, text)

async def handle_admin_data(message: types.Message, text: str):
    user_id = message.from_user.id
    
    # Инициализируем кэш
    if user_id not in user_data_cache:
        user_data_cache[user_id] = {
            'phone': None,
            'amount': None,
            'bank': None,
            'email': None
        }
    
    data = user_data_cache[user_id]
    
    # Ищем телефон
    phone_match = re.search(r'\+7\d{10}', text)
    if phone_match:
        data['phone'] = phone_match.group()
        logger.info(f"Найден телефон: {data['phone']}")
    
    # Ищем сумму
    amount_match = re.search(r'[!]?(\d+)[!]?', text)
    if amount_match:
        data['amount'] = int(amount_match.group(1))
        logger.info(f"Найдена сумма: {data['amount']}")
    
    # Ищем банк
    if '💚Сбер💚' in text:
        data['bank'] = '💚Сбер💚'
        logger.info("Найден банк: Сбер")
    elif '💛Тбанк💛' in text:
        data['bank'] = '💛Тбанк💛'
        logger.info("Найден банк: Тбанк")
    
    # Ищем email
    email_match = re.search(r'sir\+\d+@outluk\.ru', text)
    if email_match:
        data['email'] = email_match.group()
        logger.info(f"Найден email: {data['email']}")
        
        # Когда нашли email - обрабатываем
        await process_complete_data(message, user_id, data)
    else:
        # Показываем что собрали
        collected = []
        if data['phone']: collected.append("телефон")
        if data['amount']: collected.append("сумму")
        if data['bank']: collected.append("банк")
        
        if collected:
            await message.answer(f"✅ Собрано: {', '.join(collected)}")

async def process_complete_data(message: types.Message, user_id: int, data: dict):
    """Обработка полных данных"""
    # Проверяем все ли есть
    if not all([data['phone'], data['amount'], data['bank'], data['email']]):
        missing = []
        if not data['phone']: missing.append("телефон")
        if not data['amount']: missing.append("сумму")
        if not data['bank']: missing.append("банк")
        await message.answer(f"⚠️ Не хватает: {', '.join(missing)}")
        return
    
    # Получаем пользователя
    user = db.get_user(user_id)
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        return
    
    # Получаем активную сессию
    session = db.get_active_session(user['id'])
    if not session:
        await message.answer("⚠️ Нет активной сессии. Используйте /rub сумма")
        return
    
    # Сохраняем транзакцию
    db.add_transaction(user['id'], data['phone'], data['amount'], data['bank'], data['email'])
    
    # Обновляем сессию
    db.update_session_amount(session['id'], data['amount'])
    
    # Получаем обновленную сессию
    updated_session = db.get_active_session(user['id'])
    
    # Отправляем статистику
    stats_text = f"""📊 **СТАТИСТИКА**

📞 Телефон: {data['phone']}
💰 Сумма: {data['amount']}₽
🏦 Банк: {data['bank']}
📧 Email: {data['email']}

📈 Сессия:
Текущий оборот: {updated_session['current_amount']}₽
Цель: {updated_session['target_amount']}₽
Прогресс: {min(100, int(updated_session['current_amount'] / updated_session['target_amount'] * 100))}%"""
    
    await message.answer(stats_text, parse_mode='Markdown')
    
    # Очищаем кэш
    if user_id in user_data_cache:
        del user_data_cache[user_id]

async def handle_agent_assignment(message: types.Message, text: str):
    """Назначение агента"""
    if message.from_user.username not in ADMINS:
        return
    
    # Ищем username после @
    import re
    match = re.search(r'@(\w+)', text)
    if match:
        username = match.group(1)
        user = db.get_user(0)  # Ищем существующего
        
        # Просто показываем сообщение
        await message.answer(f"✅ Агент @{username} назначен")

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query_handler(lambda c: c.data == 'members')
async def show_members(callback: types.CallbackQuery):
    users = db.get_all_users()
    text = "👥 Участники:\n\n"
    for user in users:
        role = "👑 Админ" if user['role'] == 'admin' else "👤 Агент"
        text += f"{role}: @{user['username']}\n"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_main"))
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'help')
async def show_help(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Раздел помощи:", reply_markup=get_help_menu())
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'agent_form')
async def show_agent_form(callback: types.CallbackQuery):
    form_text = """📝 Анкета агента:

1. ФИО:
2. Номер карты:
3. Номер счета:
4. Номер телефона:
5. Скриншот истории трат"""
    
    await callback.message.answer(form_text)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'agent_instructions')
async def show_instructions(callback: types.CallbackQuery):
    instructions = """📋 Инструкция агента:

1. Следи за поступлениями
2. Отправляй скрины операций
3. Переводи по реквизитам
4. Отправляй квитанции"""
    
    await callback.message.answer(instructions)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'back_to_main')
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Вы в главном меню",
        reply_markup=get_main_menu()
    )
    await callback.answer()

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    logger.info("🚀 Запуск бота...")
    executor.start_polling(dp, skip_updates=True)
