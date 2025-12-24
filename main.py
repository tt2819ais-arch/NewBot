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

# ========== АДМИНЫ ПО УМОЛЧАНИЮ ==========
DEFAULT_ADMINS = ['MaksimXyila', 'ar_got']  # Без @

# Динамический список администраторов (добавляются через @)
active_admins = set(DEFAULT_ADMINS)

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self):
        self.users = {}
        self.agents = {}
        self.transactions = []
        self.sessions = {}
        self.transaction_counter = 1
        self.session_counter = 1
        self.current_target = 0
        self.current_amount = 0
        self.active_session = False
        
    def add_user(self, user_id, username, full_name, role='user'):
        username = username or f"user_{user_id}"
        
        if user_id not in self.users:
            self.users[user_id] = {
                'id': user_id,
                'username': username,
                'full_name': full_name or "Неизвестно",
                'role': role
            }
            
            # Если username в списке админов
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
        """Добавить администратора по username"""
        if username not in active_admins:
            active_admins.add(username)
            logger.info(f"Добавлен новый админ: {username}")
        
        # Обновляем роль существующего пользователя если есть
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
        
        if self.active_session:
            self.current_amount += amount
        
        return transaction
    
    def get_transactions(self):
        return self.transactions[-10:]
    
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

# ========== ПРОВЕРКА АДМИНА ==========
def is_admin(user):
    if not user:
        return False
    
    username = user.username or ""
    return username in active_admins

# ========== ОБРАБОТЧИК ДОБАВЛЕНИЯ АДМИНА ПО @ ==========
async def handle_admin_addition(message: types.Message, text: str):
    """Обработка добавления админа в формате: админ @username"""
    # Ищем паттерн: "админ @username" (регистронезависимо)
    pattern = r'(?i)админ\s+@(\w+)'
    match = re.search(pattern, text)
    
    if match:
        # Проверяем что текущий пользователь - админ
        if not is_admin(message.from_user):
            await message.answer("⚠️ Только администраторы могут добавлять других админов")
            return
        
        new_admin_username = match.group(1)
        db.add_admin_by_username(new_admin_username)
        await message.answer(f"✅ @{new_admin_username} добавлен как администратор")

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
    await message.answer("👥 Список участников:", reply_markup=get_members_menu(show_delete=is_admin_user))

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

@dp.message_handler(Command('debug'))
async def debug_command(message: types.Message):
    """Команда для отладки"""
    user = message.from_user
    logger.info(f"DEBUG: User: {user.username}, ID: {user.id}")
    
    debug_info = f"""
👤 **Информация:**
Username: @{user.username or 'нет'}
Админ: {'✅' if is_admin(user) else '❌'}

📊 **Сессия:**
Активна: {'✅' if db.active_session else '❌'}
Цель: {db.current_target}₽
Текущая: {db.current_amount}₽

👑 **Админы:** {', '.join([f'@{a}' for a in active_admins])}

💾 **Данные в кэше:** {len(admin_temp_data)}
    """
    
    await message.answer(debug_info, parse_mode='Markdown')

@dp.message_handler(Command('test'))
async def test_command(message: types.Message):
    """Тестовая команда"""
    await message.answer("✅ Бот активен! Проверьте данные:")

# ========== ОБРАБОТКА ВСЕХ СООБЩЕНИЙ ==========
@dp.message_handler()
async def handle_all_messages(message: types.Message):
    text = message.text or ""
    user = message.from_user
    
    logger.info(f"Сообщение от @{user.username}: {text}")
    
    # 1. Проверяем добавление админа
    if 'админ' in text.lower() and '@' in text:
        await handle_admin_addition(message, text)
        return
    
    # 2. Проверяем назначение агента
    agent_pattern = r'(?i)агент\s+@(\w+)'
    agent_match = re.search(agent_pattern, text)
    
    if agent_match and is_admin(user):
        agent_username = agent_match.group(1)
        db.set_agent(agent_username)
        await message.answer(f"✅ @{agent_username} назначен агентом")
        return
    
    # 3. Если это админ - обрабатываем данные
    if is_admin(user):
        await handle_admin_data(message, text)
    else:
        logger.info(f"Игнорируем сообщение от не-админа: @{user.username}")

# ========== ОБРАБОТКА ДАННЫХ АДМИНА ==========
async def handle_admin_data(message: types.Message, text: str):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    
    logger.info(f"Обрабатываю данные админа @{username}: {text}")
    
    # Инициализация кэша
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
    
    # Поиск телефона
    phone_match = re.search(r'\+7\d{10}', text)
    if phone_match:
        data['phone'] = phone_match.group()
        logger.info(f"Найден телефон: {data['phone']}")
    
    # Поиск суммы
    amount_match = re.search(r'[!]?(\d+)[!]?', text)
    if amount_match:
        data['amount'] = int(amount_match.group(1))
        logger.info(f"Найдена сумма: {data['amount']}")
    
    # Поиск банка
    if '💚Сбер💚' in text:
        data['bank'] = '💚Сбер💚'
        logger.info("Найден банк: Сбер")
    elif '💛Тбанк💛' in text:
        data['bank'] = '💛Тбанк💛'
        logger.info("Найден банк: Тбанк")
    
    # Поиск email - КЛЮЧЕВОЙ МОМЕНТ!
    email_match = re.search(r'sir\+\d+@outluk\.ru', text)
    if email_match:
        data['email'] = email_match.group()
        logger.info(f"НАЙДЕН EMAIL: {data['email']}")
        
        # СРАЗУ ЖЕ обрабатываем данные
        await process_admin_data(message, user_id, data)
        return
    
    # Если не email, просто логируем
    logger.info(f"Данные кэшированы для @{username}")

async def process_admin_data(message: types.Message, user_id: int, data: dict):
    """Обработка данных после получения email"""
    logger.info(f"Начинаю обработку данных для user_id {user_id}")
    
    # Проверяем все ли данные есть
    missing = []
    if not data.get('phone'): missing.append("телефон")
    if not data.get('amount'): missing.append("сумма")
    if not data.get('bank'): missing.append("банк")
    
    if missing:
        logger.warning(f"Не хватает данных: {missing}")
        await message.answer(f"⚠️ Не хватает: {', '.join(missing)}")
        return
    
    logger.info(f"Все данные есть! Телефон: {data['phone']}, Сумма: {data['amount']}, Банк: {data['bank']}, Email: {data['email']}")
    
    # Сохраняем транзакцию
    transaction = db.add_transaction(
        data['phone'],
        data['amount'],
        data['bank'],
        data['email']
    )
    
    # Получаем статистику
    stats = db.get_session_stats()
    
    # Формируем ответ
    stats_text = f"""📊 **СТАТИСТИКА ПОСЛЕ ОПЕРАЦИИ**

📞 Телефон: `{data['phone']}`
💰 Сумма: `{data['amount']}₽`
🏦 Банк: {data['bank']}
📧 Email: `{data['email']}`

📈 **ТЕКУЩАЯ СЕССИЯ:**
┣ Текущий оборот: `{stats['current']}₽`
┣ Цель на сессию: `{stats['target']}₽`
┗ Прогресс: `{min(100, int(stats['current'] / stats['target'] * 100))}%`"""

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📜 История операций", callback_data="history"))
    
    try:
        await message.answer(stats_text, reply_markup=keyboard, parse_mode='Markdown')
        logger.info("✅ Статистика отправлена успешно!")
    except Exception as e:
        logger.error(f"Ошибка отправки статистики: {e}")
        await message.answer("❌ Ошибка при отправке статистики")
    
    # Очищаем кэш
    if user_id in admin_temp_data:
        del admin_temp_data[user_id]
        logger.info(f"Кэш очищен для user_id {user_id}")

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query_handler(lambda c: c.data == 'members')
async def show_members(callback: types.CallbackQuery):
    is_admin_user = is_admin(callback.from_user)
    await callback.message.edit_text(
        "👥 Список участников:",
        reply_markup=get_members_menu(show_delete=is_admin_user)
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
    # ВИДЕО ПРАВИЛЬНО НАЗНАЧЕНЫ:
    # "Подключить подписку" -> check.mp4
    # "Отправка чека" -> instructions.mp4
    if callback.data == 'subscribe':
        video_filename = 'instructions.mp4'  # ПРАВИЛЬНО!
        caption = "📹 Инструкция по подключению подписки"
    else:  # send_receipt
        video_filename = 'check.mp4'  # ПРАВИЛЬНО!
        caption = "📹 Инструкция по отправке чека"
    
    try:
        # Пробуем разные пути к файлу
        video_paths = [
            video_filename,
            f"media/{video_filename}",
            f"/app/{video_filename}",
            f"/app/media/{video_filename}"
        ]
        
        video_file = None
        for path in video_paths:
            if os.path.exists(path):
                video_file = types.InputFile(path)
                logger.info(f"Найдено видео: {path}")
                break
        
        if video_file:
            await bot.send_video(
                chat_id=callback.message.chat.id,
                video=video_file,
                caption=caption
            )
        else:
            await callback.message.answer(f"📹 {caption}")
            
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
        reply_markup=get_members_menu(show_delete=is_admin_user)
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
    await bot.set_my_commands(commands)
    
    logger.info("=" * 60)
    logger.info("🤖 Ready!")
    logger.info(f"Админы по умолчанию: {DEFAULT_ADMINS}")
    logger.info(f"Токен: {BOT_TOKEN[:15]}...")
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
