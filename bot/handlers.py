from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import ChatType
from sqlalchemy import and_

from .database import db, User, Transaction, Session
from .keyboards import *
from .states import AgentForm, SessionStates
from .config import config
from datetime import datetime

async def start_command(message: types.Message):
    """Обработчик команды /start для личных и групповых чатов"""
    
    # Определяем тип ответа в зависимости от чата
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        welcome_text = "🤖 Бот помощник активирован в этой группе!\n\nИспользуйте кнопки меню или команды:\n/members - Список участников\n/help - Помощь и инструкции"
    else:
        welcome_text = "Вы в главном меню, есть вопросы? Жми кнопки снизу, возможно там есть ответ на ваш вопрос."
    
    # Отправляем сообщение с клавиатурой
    await message.answer(welcome_text, reply_markup=get_main_menu())
    
    # Регистрируем пользователя в БД
    session = db.get_session()
    user = session.query(User).filter_by(user_id=message.from_user.id).first()
    
    if not user:
        username = message.from_user.username or ""
        role = 'admin' if username in config.ADMINS else 'user'
        
        user = User(
            user_id=message.from_user.id,
            username=username,
            full_name=message.from_user.full_name or "Неизвестно",
            role=role
        )
        session.add(user)
    
    session.commit()
    session.close()

async def help_command(message: types.Message):
    """Обработчик команды /help"""
    help_text = "📋 Раздел помощи. Выберите нужный раздел:"
    
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        # В группе отправляем как отдельное сообщение
        await message.answer(help_text, reply_markup=get_help_menu())
    else:
        # В личном чате можно редактировать
        await message.answer(help_text, reply_markup=get_help_menu())

async def members_command(message: types.Message):
    """Обработчик команды /members"""
    session = db.get_session()
    users = session.query(User).filter(User.role.in_(['admin', 'agent'])).all()
    session.close()
    
    is_admin = message.from_user.username in config.ADMINS if message.from_user.username else False
    
    members_text = "👥 Список участников:"
    
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.answer(members_text, reply_markup=get_members_menu(users, show_delete=is_admin))
    else:
        await message.answer(members_text, reply_markup=get_members_menu(users, show_delete=is_admin))

async def handle_group_message(message: types.Message):
    """Обработчик всех сообщений в группе"""
    
    # Проверяем триггеры для назначения агента
    text_lower = message.text.lower() if message.text else ""
    
    # Триггеры для назначения агента (регистронезависимые)
    agent_triggers = ['агент @', '/агент @']
    
    for trigger in agent_triggers:
        if trigger in text_lower:
            # Извлекаем username после триггера
            parts = message.text.split('@')
            if len(parts) > 1:
                username = parts[1].strip()
                await handle_agent_assignment_by_username(message, username)
            break
    
    # Проверяем административные команды
    await handle_admin_message(message)

async def handle_agent_assignment_by_username(message: types.Message, username: str):
    """Назначение агента по username"""
    if message.from_user.username in config.ADMINS:
        session = db.get_session()
        user = session.query(User).filter_by(username=username).first()
        
        if user:
            user.role = 'agent'
            session.commit()
            await message.answer(f"✅ Пользователь @{username} назначен агентом")
        else:
            # Если пользователя нет в БД, создаем
            new_agent = User(
                username=username,
                role='agent',
                full_name=f"Агент @{username}"
            )
            session.add(new_agent)
            session.commit()
            await message.answer(f"✅ Создан новый агент @{username}")
        
        session.close()

def register_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    
    # Команды для всех типов чатов
    dp.register_message_handler(
        start_command, 
        Command('start'), 
        chat_type=[ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]
    )
    
    dp.register_message_handler(
        help_command,
        Command('help'),
        chat_type=[ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]
    )
    
    dp.register_message_handler(
        members_command,
        Command('members'),
        chat_type=[ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]
    )
    
    # Административные команды
    dp.register_message_handler(
        set_session_target, 
        Command('rub'),
        chat_type=[ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]
    )
    
    dp.register_message_handler(
        stop_session, 
        Command('stop'),
        chat_type=[ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]
    )
    
    # Обработчик всех сообщений в группах (для триггеров)
    dp.register_message_handler(
        handle_group_message,
        chat_type=[ChatType.GROUP, ChatType.SUPERGROUP]
    )
    
    # Обработчики callback-запросов (инлайн кнопки)
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
    
    # FSM обработчики
    dp.register_message_handler(handle_agent_data, state=AgentForm.waiting_for_data, content_types=types.ContentType.ANY)
