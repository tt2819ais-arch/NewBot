import os
import re
import logging
import asyncio
from collections import defaultdict
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatType

# ========== НАСТРОЙКИ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMINS = ['MaksimXyila', 'ar_got']  # Без @

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self):
        self.users = {}  # user_id -> данные
        self.agents = {}  # username -> данные агента
        self.transactions = []
        self.sessions = {}
        self.transaction_counter = 1
        self.session_counter = 1
        self.current_target = 0
        self.current_amount = 0
        self.active_session = False
        
    def add_user(self, user_id, username, full_name, role='user'):
        if user_id not in self.users:
            self.users[user_id] = {
                'id': user_id,
                'username': username,
                'full_name': full_name,
                'role': role
            }
            if role == 'agent':
                self.agents[username] = self.users[user_id]
    
    def get_user(self, user_id):
        return self.users.get(user_id)
    
    def get_user_by_username(self, username):
        for user in self.users.values():
            if user['username'] == username:
                return user
        return None
    
    def set_agent(self, username, full_name=""):
        # Создаем или обновляем агента
        agent = self.get_user_by_username(username)
        if not agent:
            # Создаем нового с фиктивным ID
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
    
    def add_transaction(self, phone, amount, bank, email):
        transaction = {
            'id': self.transaction_counter,
            'phone': phone,
            'amount': amount,
            'bank': bank,
            'email': email,
            'timestamp': asyncio.get_event_loop().time()
        }
        self.transactions.append(transaction)
        self.transaction_counter += 1
        
        # Обновляем сумму в сессии
        if self.active_session:
            self.current_amount += amount
        
        return transaction
    
    def get_transactions(self):
        return self.transactions[-10:]  # Последние 10
    
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
        InlineKeyboardButton("Подключить подписку", callback_data="subscribe"),
        InlineKeyboardButton("Отправка чека", callback_data="send_receipt"),
        InlineKeyboardButton("Инструкция агента", callback_data="agent_instructions"),
        InlineKeyboardButton("Назад", callback_data="back_to_main")
    )
    return keyboard

def get_members_menu(show_delete=False):
    keyboard = InlineKeyboardMarkup(row_width=1)
    users = db.get_all_users()
    
    for user in users:
        role_icon = "👑" if user['role'] == 'admin' else "👤"
        btn_text = f"{role_icon} {user['role']}: @{user['username']}"
        keyboard.add(InlineKeyboardButton(btn_text, callback_data=f"view_{user['username']}"))
    
    if show_delete:
        keyboard.add(
            InlineKeyboardButton("❌ Удалить агента", callback_data="delete_agent_menu"),
            InlineKeyboardButton("🗑️ Удалить всех агентов", callback_data="delete_all_confirm")
        )
    
    keyboard.add(InlineKeyboardButton("« Назад", callback_data="back_to_main"))
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

# ========== КОМАНДЫ ==========
@dp.message_handler(Command('start'))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    
    # Регистрируем пользователя
    role = 'admin' if username in ADMINS else 'user'
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
    is_admin = message.from_user.username in ADMINS
    await message.answer("👥 Список участников:", reply_markup=get_members_menu(show_delete=is_admin))

@dp.message_handler(Command('rub'))
async def rub_command(message: types.Message):
    if message.from_user.username not in ADMINS:
        return await message.answer("⚠️ Только для администраторов")
    
    try:
        amount = int(message.text.split()[1])
        session_id = db.start_session(amount)
        await message.answer(f"✅ Цель на сессию установлена: {amount}₽")
    except:
        await message.answer("Использование: /rub сумма")

@dp.message_handler(Command('stop'))
async def stop_command(message: types.Message):
    if message.from_user.username not in ADMINS:
        return await message.answer("⚠️ Только для администраторов")
    
    if db.active_session:
        total = db.stop_session()
        await message.answer(f"✅ Сессия остановлена. Итог: {total}₽")
    else:
        await message.answer("⚠️ Нет активной сессии")

@dp.message_handler(Command('test'))
async def test_command(message: types.Message):
    """Тестовая команда для проверки"""
    await message.answer(
        "Тестовые данные для проверки:\n\n"
        "1. +79019786832\n"
        "2. 500!\n"
        "3. 💛Тбанк💛\n"
        "4. sir+123@outluk.ru"
    )

# ========== НАЗНАЧЕНИЕ АГЕНТА ==========
@dp.message_handler()
async def handle_messages(message: types.Message):
    text = message.text or ""
    username = message.from_user.username or ""
    
    # 1. Обработка назначения агента (регистронезависимо)
    agent_pattern = r'(?i)агент\s+@(\w+)'
    match = re.search(agent_pattern, text)
    
    if match and username in ADMINS:
        agent_username = match.group(1)
        agent = db.set_agent(agent_username)
        await message.answer(f"✅ @{agent_username} назначен агентом")
        return
    
    # 2. Обработка данных админа
    if username in ADMINS:
        await handle_admin_data(message, text)

# ========== ОБРАБОТКА ДАННЫХ АДМИНА ==========
async def handle_admin_data(message: types.Message, text: str):
    user_id = message.from_user.id
    
    # Инициализируем кэш для пользователя
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
    
    # Ищем телефон (формат: +7XXXXXXXXXX)
    phone_match = re.search(r'\+7\d{10}', text)
    if phone_match:
        data['phone'] = phone_match.group()
    
    # Ищем сумму (форматы: 500! или !500 или просто 500)
    amount_match = re.search(r'[!]?(\d+)[!]?', text)
    if amount_match:
        data['amount'] = int(amount_match.group(1))
    
    # Ищем банк
    if '💚Сбер💚' in text:
        data['bank'] = '💚Сбер💚'
    elif '💛Тбанк💛' in text:
        data['bank'] = '💛Тбанк💛'
    
    # Ищем email (формат: sir+цифры@outluk.ru)
    email_match = re.search(r'sir\+\d+@outluk\.ru', text)
    if email_match:
        data['email'] = email_match.group()
        
        # КОГДА НАШЛИ EMAIL - ОБРАБАТЫВАЕМ ВСЕ ДАННЫЕ
        await process_admin_data(message, user_id, data)
    
    # Очистка старых данных (старше 10 минут)
    current_time = asyncio.get_event_loop().time()
    for uid in list(admin_temp_data.keys()):
        if current_time - admin_temp_data[uid]['timestamp'] > 600:
            del admin_temp_data[uid]

async def process_admin_data(message: types.Message, user_id: int, data: dict):
    """Обработка полных данных админа после получения email"""
    
    # Проверяем все ли данные есть
    missing = []
    if not data.get('phone'): missing.append("номер телефона")
    if not data.get('amount'): missing.append("сумма")
    if not data.get('bank'): missing.append("банк")
    
    if missing:
        await message.answer(f"⚠️ Не хватает данных: {', '.join(missing)}")
        return
    
    # Все данные есть - сохраняем транзакцию
    transaction = db.add_transaction(
        data['phone'],
        data['amount'],
        data['bank'],
        data['email']
    )
    
    # Получаем статистику сессии
    stats = db.get_session_stats()
    
    # Формируем статистику
    stats_text = f"""📊 **СТАТИСТИКА**

📞 Номер: `{data['phone']}`
💰 Сумма: `{data['amount']}₽`
🏦 Банк: {data['bank']}
📧 Email: `{data['email']}`

📈 **СЕССИЯ:**
Текущий оборот: `{stats['current']}₽`
Цель на сессию: `{stats['target']}₽`
Последний перевод: `{data['amount']}₽**"""

    # Добавляем кнопку История
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📜 История операций", callback_data="history"))
    
    await message.answer(stats_text, reply_markup=keyboard, parse_mode='Markdown')
    
    # Очищаем временные данные
    if user_id in admin_temp_data:
        del admin_temp_data[user_id]

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query_handler(lambda c: c.data == 'members')
async def show_members(callback: types.CallbackQuery):
    is_admin = callback.from_user.username in ADMINS
    await callback.message.edit_text(
        "👥 Список участников:",
        reply_markup=get_members_menu(show_delete=is_admin)
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
    await callback.answer("Здесь будет пример скриншота")

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
    video_file = 'instructions.mp4' if callback.data == 'subscribe' else 'check.mp4'
    
    try:
        # Пытаемся отправить видео
        with open(f"media/{video_file}", 'rb') as video:
            await bot.send_video(
                chat_id=callback.message.chat.id,
                video=types.InputFile(video),
                caption=f"📹 {video_file}"
            )
    except FileNotFoundError:
        await callback.message.answer(f"📹 Видео {video_file} будет отправлено в группу")
    except Exception as e:
        logger.error(f"Ошибка отправки видео: {e}")
        await callback.message.answer(f"📹 Видеоинструкция: {video_file}")
    
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == 'history')
async def show_history(callback: types.CallbackQuery):
    transactions = db.get_transactions()
    
    if not transactions:
        await callback.answer("📭 История операций пуста")
        return
    
    history_text = "📜 **История операций:**\n\n"
    for i, trans in enumerate(reversed(transactions), 1):
        history_text += f"{i}. `{trans['phone']}` - `{trans['amount']}₽` - {trans['bank']}\n"
    
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
    
    # Возвращаемся к списку
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
    is_admin = callback.from_user.username in ADMINS
    await callback.message.edit_text(
        "👥 Список участников:",
        reply_markup=get_members_menu(show_delete=is_admin)
    )
    await callback.answer()

# ========== ЗАПУСК ==========
async def on_startup(dp: Dispatcher):
    # Устанавливаем команды бота
    commands = [
        types.BotCommand("start", "Запустить бота"),
        types.BotCommand("help", "Помощь и инструкции"),
        types.BotCommand("members", "Список участников"),
        types.BotCommand("rub", "Установить цель на сессию (админы)"),
        types.BotCommand("stop", "Остановить сессию (админы)"),
    ]
    await bot.set_my_commands(commands)
    
    logger.info("✅ Бот запущен и готов к работе!")

async def on_shutdown(dp: Dispatcher):
    logger.info("❌ Бот выключается...")

if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
