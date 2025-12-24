import re
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from sqlalchemy import and_

from .database import db, User, Transaction, Session
from .keyboards import *
from .states import AgentForm, SessionStates
from .config import config

async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    session = db.get_session()
    user = session.query(User).filter_by(user_id=user_id).first()
    
    if not user:
        role = 'admin' if username in config.ADMINS else 'user'
        user = User(
            user_id=user_id,
            username=username,
            full_name=full_name,
            role=role
        )
        session.add(user)
        session.commit()
    
    session.close()
    
    text = "Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос."
    await message.answer(text, reply_markup=get_main_menu())

async def handle_members(callback: types.CallbackQuery):
    session = db.get_session()
    users = session.query(User).filter(User.role.in_(['admin', 'agent'])).all()
    session.close()
    
    is_admin = callback.from_user.username in config.ADMINS
    
    await callback.message.edit_text(
        "Список участников:",
        reply_markup=get_members_menu(users, show_delete=is_admin)
    )
    await callback.answer()

async def handle_help(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Раздел помощи:",
        reply_markup=get_help_menu()
    )
    await callback.answer()

async def handle_agent_form(callback: types.CallbackQuery):
    form_text = """Обязательная анкета для регистрации агента.

1. ФИО:
2. Номер карты:
3. Номер счета:
4. Номер телефона:
5. Скриншот истории трат за Ноябрь/Декабрь.

Отправь данные одним сообщением."""
    
    await callback.message.answer(form_text, reply_markup=get_back_button())
    await AgentForm.waiting_for_data.set()
    await callback.answer()

async def handle_agent_data(message: types.Message, state: FSMContext):
    session = db.get_session()
    user = session.query(User).filter_by(user_id=message.from_user.id).first()
    
    if user and user.role == 'agent':
        # Закрепляем сообщение если это агент
        await message.pin()
    
    # Обновляем данные пользователя
    user.role = 'agent'
    session.commit()
    session.close()
    
    await message.answer("Анкета принята!")
    await state.finish()

async def handle_agent_instructions(callback: types.CallbackQuery):
    instructions_text = """Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.
1. Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.
2. Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.
3. После перевода отправляешь квитанцию на указанную почту."""
    
    await callback.message.answer(instructions_text, reply_markup=get_back_button())
    await callback.answer()

async def handle_video_send(callback: types.CallbackQuery):
    video_file = None
    
    if callback.data == 'subscribe':
        video_file = 'media/instructions.mp4'
    elif callback.data == 'send_receipt':
        video_file = 'media/check.mp4'
    
    if video_file:
        await callback.message.answer_video(types.InputFile(video_file))
    
    await callback.answer()

async def handle_agent_assignment(message: types.Message):
    pattern = r'(?i)агент\s*@(\w+)'
    match = re.search(pattern, message.text)
    
    if match and message.from_user.username in config.ADMINS:
        agent_username = match.group(1)
        
        session = db.get_session()
        user = session.query(User).filter_by(username=agent_username).first()
        
        if user:
            user.role = 'agent'
            session.commit()
            await message.answer(f"Пользователь @{agent_username} назначен агентом")
        else:
            await message.answer(f"Пользователь @{agent_username} не найден")
        
        session.close()

async def handle_admin_message(message: types.Message):
    text = message.text
    
    # Паттерны для распознавания
    phone_pattern = r'\+7\d{10}'
    amount_pattern = r'[!]?(\d+)[!]?'
    bank_patterns = ['Сбер', 'Тбанк']
    email_pattern = r'sir\+\d+@outluk\.ru'
    
    phone = re.search(phone_pattern, text)
    amount = re.search(amount_pattern, text)
    bank = next((b for b in bank_patterns if b in text), None)
    email = re.search(email_pattern, text)
    
    if any([phone, amount, bank, email]):
        session = db.get_session()
        
        # Сохраняем транзакцию если есть все данные
        if phone and amount and bank and email:
            # Получаем активную сессию
            active_session = session.query(Session).filter_by(is_active=True).first()
            
            if active_session:
                transaction = Transaction(
                    agent_id=active_session.agent_id,
                    phone_number=phone.group(),
                    amount=int(amount.group(1)),
                    bank=bank,
                    email=email.group()
                )
                session.add(transaction)
                
                # Обновляем сумму в сессии
                active_session.current_amount += int(amount.group(1))
                
                # Проверяем достижение цели
                if active_session.current_amount >= active_session.target_amount:
                    await send_session_statistics(message.chat.id, active_session.id)
        
        session.commit()
        session.close()
        
        # Отправляем статистику если есть email
        if email:
            await send_current_stats(message.chat.id)

async def send_current_stats(chat_id):
    session = db.get_session()
    active_session = session.query(Session).filter_by(is_active=True).first()
    
    if active_session:
        stats_text = f"""Текущий оборот - {active_session.current_amount}₽
Цель на сессию - {active_session.target_amount}₽
Последний перевод - {active_session.current_amount}₽"""
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("История", callback_data="history"))
        
        from .main import bot
        await bot.send_message(chat_id, stats_text, reply_markup=keyboard)
    
    session.close()

async def handle_history(callback: types.CallbackQuery):
    session = db.get_session()
    transactions = session.query(Transaction).all()
    
    history_text = "История операций:\n\n"
    for i, trans in enumerate(transactions[-10:], 1):  # Последние 10 операций
        history_text += f"{i}. {trans.phone_number} - {trans.amount}₽ - {trans.bank}\n"
    
    await callback.message.answer(history_text)
    await callback.answer()
    session.close()

async def set_session_target(message: types.Message):
    if message.from_user.username in config.ADMINS:
        try:
            amount = int(message.text.split()[1])
            
            session_db = db.get_session()
            
            # Завершаем старые сессии
            old_sessions = session_db.query(Session).filter_by(is_active=True).all()
            for s in old_sessions:
                s.is_active = False
                s.end_time = datetime.now()
            
            # Создаем новую сессию
            new_session = Session(
                target_amount=amount,
                is_active=True
            )
            session_db.add(new_session)
            session_db.commit()
            session_db.close()
            
            await message.answer(f"Цель на сессию установлена: {amount}₽")
            
        except (IndexError, ValueError):
            await message.answer("Использование: /rub сумма")

async def stop_session(message: types.Message):
    if message.from_user.username in config.ADMINS:
        session_db = db.get_session()
        active_session = session_db.query(Session).filter_by(is_active=True).first()
        
        if active_session:
            active_session.is_active = False
            active_session.end_time = datetime.now()
            session_db.commit()
            
            await send_session_statistics(message.chat.id, active_session.id)
            session_db.close()

async def send_session_statistics(chat_id, session_id):
    session_db = db.get_session()
    session_data = session_db.query(Session).filter_by(id=session_id).first()
    
    if session_data:
        transactions = session_db.query(Transaction).filter_by(agent_id=session_data.agent_id).all()
        
        stats_text = f"История сессии агента:\n"
        stats_text += f"Цель: {session_data.target_amount}₽\n"
        stats_text += f"Достигнуто: {session_data.current_amount}₽\n\n"
        stats_text += "Операции:\n"
        
        for trans in transactions:
            stats_text += f"📞 {trans.phone_number} - {trans.amount}₽ - {trans.bank}\n"
        
        from .main import bot
        await bot.send_message(chat_id, stats_text)
    
    session_db.close()

async def handle_delete_agent(callback: types.CallbackQuery):
    session = db.get_session()
    agents = session.query(User).filter_by(role='agent').all()
    session.close()
    
    await callback.message.edit_text(
        "Выберите агента для удаления:",
        reply_markup=get_delete_agents_menu(agents)
    )
    await callback.answer()

async def handle_delete_all_agents(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Вы уверены, что хотите удалить всех агентов?",
        reply_markup=get_confirmation_keyboard()
    )
    await callback.answer()

async def delete_selected_agent(callback: types.CallbackQuery):
    agent_id = int(callback.data.split('_')[1])
    
    session = db.get_session()
    agent = session.query(User).filter_by(user_id=agent_id).first()
    
    if agent and agent.role == 'agent':
        session.delete(agent)
        session.commit()
        await callback.answer(f"Агент @{agent.username} удален")
    else:
        await callback.answer("Агент не найден")
    
    session.close()
    
    # Обновляем список
    await handle_members(callback)

async def delete_all_agents(callback: types.CallbackQuery):
    session = db.get_session()
    agents = session.query(User).filter_by(role='agent').all()
    
    for agent in agents:
        session.delete(agent)
    
    session.commit()
    session.close()
    
    await callback.answer("Все агенты удалены")
    await handle_members(callback)

async def handle_back(callback: types.CallbackQuery):
    if callback.data == 'back_to_main':
        await callback.message.edit_text(
            "Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос.",
            reply_markup=get_main_menu()
        )
    elif callback.data == 'back_to_help':
        await handle_help(callback)
    elif callback.data == 'back_to_members':
        await handle_members(callback)
    
    await callback.answer()

def register_handlers(dp: Dispatcher):
    # Команды
    dp.register_message_handler(start_command, Command('start'))
    dp.register_message_handler(set_session_target, Command('rub'))
    dp.register_message_handler(stop_session, Command('stop'))
    
    # Обработчики триггеров
    dp.register_message_handler(handle_agent_assignment)
    dp.register_message_handler(handle_admin_message)
    
    # Callback handlers
    dp.register_callback_query_handler(handle_members, lambda c: c.data == 'members')
    dp.register_callback_query_handler(handle_help, lambda c: c.data == 'help')
    dp.register_callback_query_handler(handle_agent_form, lambda c: c.data == 'agent_form')
    dp.register_callback_query_handler(handle_agent_instructions, lambda c: c.data == 'agent_instructions')
    dp.register_callback_query_handler(handle_video_send, lambda c: c.data in ['subscribe', 'send_receipt'])
    dp.register_callback_query_handler(handle_history, lambda c: c.data == 'history')
    dp.register_callback_query_handler(handle_delete_agent, lambda c: c.data == 'delete_agent')
    dp.register_callback_query_handler(handle_delete_all_agents, lambda c: c.data == 'delete_all_agents')
    dp.register_callback_query_handler(delete_selected_agent, lambda c: c.data.startswith('delete_') and not c.data.startswith('delete_all'))
    dp.register_callback_query_handler(delete_all_agents, lambda c: c.data == 'confirm_delete_all')
    dp.register_callback_query_handler(handle_back, lambda c: c.data.startswith('back_'))
    
    # FSM handlers
    dp.register_message_handler(handle_agent_data, state=AgentForm.waiting_for_data)
