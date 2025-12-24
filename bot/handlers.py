import re
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import ChatType

from config import config
from database import db
from keyboards import *
from states import AgentForm, SessionForm

logger = logging.getLogger(__name__)

# ========== КОМАНДЫ ==========

async def start_command(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    
    # Регистрируем пользователя
    db.add_user(user_id, username, full_name, 
                'admin' if username in config.ADMINS else 'user')
    
    if message.chat.type in ['group', 'supergroup']:
        text = "🤖 Бот помощник активирован в этой группе!"
    else:
        text = "Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос."
    
    await message.answer(text, reply_markup=get_main_menu())

async def help_command(message: types.Message):
    """Обработчик команды /help"""
    await message.answer("📋 Раздел помощи:", reply_markup=get_help_menu())

async def members_command(message: types.Message):
    """Обработчик команды /members"""
    users = db.get_all_users()
    is_admin = message.from_user.username in config.ADMINS if message.from_user.username else False
    await message.answer("👥 Список участников:", reply_markup=get_members_menu(users, is_admin))

async def rub_command(message: types.Message):
    """Установка цели на сессию"""
    if message.from_user.username not in config.ADMINS:
        return await message.answer("⚠️ Эта команда только для администраторов.")
    
    try:
        amount = int(message.text.split()[1])
        user = db.get_user(message.from_user.id)
        if user:
            session_id = db.create_session(user[0], amount)
            await message.answer(f"✅ Цель на сессию установлена: {amount}₽")
    except (IndexError, ValueError):
        await message.answer("Использование: /rub сумма")

async def stop_command(message: types.Message):
    """Остановка сессии"""
    if message.from_user.username not in config.ADMINS:
        return await message.answer("⚠️ Эта команда только для администраторов.")
    
    user = db.get_user(message.from_user.id)
    if user:
        session = db.get_active_session(user[0])
        if session:
            db.stop_session(session[0])
            await message.answer("✅ Сессия остановлена")
        else:
            await message.answer("⚠️ Нет активной сессии")

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ ==========

async def handle_agent_assignment(message: types.Message):
    """Назначение агента через триггер"""
    if message.from_user.username not in config.ADMINS:
        return
    
    text = message.text or ""
    pattern = r'(?i)агент\s+@(\w+)'
    match = re.search(pattern, text)
    
    if match:
        username = match.group(1)
        users = db.get_all_users()
        
        # Ищем пользователя
        for user in users:
            if user[2] == username:  # username в третьей колонке
                db.update_user_role(user[1], 'agent')  # user_id во второй колонке
                await message.answer(f"✅ @{username} назначен агентом")
                return
        
        # Если не нашли, создаем нового
        db.add_user(0, username, f"Агент @{username}", 'agent')
        await message.answer(f"✅ Создан новый агент @{username}")

async def handle_admin_message(message: types.Message):
    """Обработка сообщений администратора с данными"""
    if message.from_user.username not in config.ADMINS:
        return
    
    text = message.text or ""
    
    # Регулярные выражения для поиска данных
    phone_match = re.search(r'\+7\d{10}', text)
    amount_match = re.search(r'[!]?(\d+)[!]?', text)
    bank_match = re.search(r'(💚Сбер💚|💛Тбанк💛)', text)
    email_match = re.search(r'sir\+\d+@outluk\.ru', text)
    
    collected_data = {}
    
    if phone_match:
        collected_data['phone'] = phone_match.group()
    if amount_match:
        collected_data['amount'] = int(amount_match.group(1))
    if bank_match:
        collected_data['bank'] = bank_match.group()
    if email_match:
        collected_data['email'] = email_match.group()
    
    # Если нашли email, отправляем статистику
    if 'email' in collected_data:
        user = db.get_user(message.from_user.id)
        if user:
            session = db.get_active_session(user[0])
            if session:
                stats_text = f"""📊 Статистика:
Текущий оборот - {session[3]}₽
Цель на сессию - {session[2]}₽
Последний перевод - {collected_data.get('amount', 0)}₽"""
                
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton("История", callback_data="history"))
                
                await message.answer(stats_text, reply_markup=keyboard)
                
                # Сохраняем транзакцию
                if all(k in collected_data for k in ['phone', 'amount', 'bank', 'email']):
                    db.add_transaction(user[0], 
                                     collected_data['phone'], 
                                     collected_data['amount'], 
                                     collected_data['bank'], 
                                     collected_data['email'])
                    
                    # Обновляем сумму в сессии
                    db.update_session_amount(session[0], collected_data['amount'])

# ========== CALLBACK ОБРАБОТЧИКИ ==========

async def handle_members(callback: types.CallbackQuery):
    users = db.get_all_users()
    is_admin = callback.from_user.username in config.ADMINS if callback.from_user.username else False
    await callback.message.edit_text("👥 Список участников:", reply_markup=get_members_menu(users, is_admin))
    await callback.answer()

async def handle_help(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Раздел помощи:", reply_markup=get_help_menu())
    await callback.answer()

async def handle_agent_form(callback: types.CallbackQuery):
    form_text = """📝 Обязательная анкета для регистрации агента.

1. ФИО:
2. Номер карты:
3. Номер счета:
4. Номер телефона:
5. Скриншот истории трат за Ноябрь/Декабрь.

Отправь данные одним сообщением."""
    
    await callback.message.answer(form_text, reply_markup=get_back_keyboard())
    await AgentForm.waiting_for_data.set()
    await callback.answer()

async def handle_agent_instructions(callback: types.CallbackQuery):
    instructions = """📋 Инструкция агента:

Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.
1. Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.
2. Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.
3. После перевода отправляешь квитанцию на указанную почту."""
    
    await callback.message.answer(instructions, reply_markup=get_back_keyboard())
    await callback.answer()

async def handle_video_send(callback: types.CallbackQuery):
    video_map = {
        'subscribe': 'instructions.mp4',
        'send_receipt': 'check.mp4'
    }
    
    video_file = video_map.get(callback.data)
    if video_file:
        # В реальном коде здесь отправка видео
        await callback.message.answer(f"📹 Видео {video_file} будет отправлено в группу")
    await callback.answer()

async def handle_history(callback: types.CallbackQuery):
    transactions = db.get_transactions()[:10]  # Последние 10
    if transactions:
        history_text = "📜 История операций:\n\n"
        for i, trans in enumerate(transactions, 1):
            history_text += f"{i}. {trans[2]} - {trans[3]}₽ - {trans[4]}\n"
    else:
        history_text = "📭 История операций пуста"
    
    await callback.message.answer(history_text)
    await callback.answer()

async def handle_delete_menu(callback: types.CallbackQuery):
    agents = db.get_agents()
    if agents:
        await callback.message.edit_text("Выберите агента для удаления:", reply_markup=get_delete_agents_menu(agents))
    else:
        await callback.answer("❌ Нет агентов для удаления")

async def handle_delete_all_confirm(callback: types.CallbackQuery):
    await callback.message.edit_text("⚠️ Вы уверены, что хотите удалить ВСЕХ агентов?", reply_markup=get_confirmation_keyboard())
    await callback.answer()

async def delete_agent(callback: types.CallbackQuery):
    user_id = int(callback.data.split('_')[1])
    db.delete_agent(user_id)
    await callback.answer("✅ Агент удален")
    await handle_members(callback)

async def delete_all_agents(callback: types.CallbackQuery):
    db.delete_all_agents()
    await callback.answer("✅ Все агенты удалены")
    await handle_members(callback)

async def handle_back(callback: types.CallbackQuery):
    if callback.data == 'back_to_main':
        await callback.message.edit_text("Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос.", reply_markup=get_main_menu())
    elif callback.data == 'back_to_help':
        await handle_help(callback)
    elif callback.data == 'back_to_members':
        await handle_members(callback)
    elif callback.data == 'cancel_delete':
        await handle_members(callback)
    await callback.answer()

async def handle_agent_data(message: types.Message, state: FSMContext):
    """Получение анкеты агента"""
    user = db.get_user(message.from_user.id)
    if user and user[4] == 'agent':  # role в пятой колонке
        # Здесь можно закрепить сообщение в группе
        pass
    
    await message.answer("✅ Анкета принята!")
    await state.finish()

# ========== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ==========

def register_handlers(dp: Dispatcher):
    # Команды
    dp.register_message_handler(start_command, Command('start'))
    dp.register_message_handler(help_command, Command('help'))
    dp.register_message_handler(members_command, Command('members'))
    dp.register_message_handler(rub_command, Command('rub'))
    dp.register_message_handler(stop_command, Command('stop'))
    
    # Обработчики сообщений
    dp.register_message_handler(handle_agent_assignment)
    dp.register_message_handler(handle_admin_message)
    
    # Callback обработчики
    dp.register_callback_query_handler(handle_members, lambda c: c.data == 'members')
    dp.register_callback_query_handler(handle_help, lambda c: c.data == 'help')
    dp.register_callback_query_handler(handle_agent_form, lambda c: c.data == 'agent_form')
    dp.register_callback_query_handler(handle_agent_instructions, lambda c: c.data == 'agent_instructions')
    dp.register_callback_query_handler(handle_video_send, lambda c: c.data in ['subscribe', 'send_receipt'])
    dp.register_callback_query_handler(handle_history, lambda c: c.data == 'history')
    dp.register_callback_query_handler(handle_delete_menu, lambda c: c.data == 'delete_agent_menu')
    dp.register_callback_query_handler(handle_delete_all_confirm, lambda c: c.data == 'delete_all_confirm')
    dp.register_callback_query_handler(delete_agent, lambda c: c.data.startswith('delete_') and not c.data == 'delete_all_confirm')
    dp.register_callback_query_handler(delete_all_agents, lambda c: c.data == 'confirm_delete_all')
    dp.register_callback_query_handler(handle_back, lambda c: c.data.startswith('back_') or c.data == 'cancel_delete')
    
    # FSM обработчики
    dp.register_message_handler(handle_agent_data, state=AgentForm.waiting_for_data, content_types=types.ContentType.ANY)
