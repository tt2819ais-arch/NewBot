from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
        InlineKeyboardButton("Инструкция агента", callback_data="agent_instructions")
    )
    return keyboard

def get_members_menu(agents, show_delete=False):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for agent in agents:
        role = "👑 Админ" if agent.role == 'admin' else "👤 Агент"
        keyboard.add(InlineKeyboardButton(
            f"{role}: @{agent.username}",
            callback_data=f"agent_{agent.user_id}"
        ))
    
    if show_delete:
        keyboard.add(
            InlineKeyboardButton("Удалить агента", callback_data="delete_agent"),
            InlineKeyboardButton("Удалить всех агентов", callback_data="delete_all_agents")
        )
    
    keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_main"))
    return keyboard

def get_delete_agents_menu(agents):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for agent in agents:
        keyboard.add(InlineKeyboardButton(
            f"❌ @{agent.username}",
            callback_data=f"delete_{agent.user_id}"
        ))
    
    keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_members"))
    return keyboard

def get_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Да", callback_data="confirm_delete_all"),
        InlineKeyboardButton("Нет", callback_data="cancel_delete")
    )
    return keyboard

def get_back_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_help"))
    return keyboard
