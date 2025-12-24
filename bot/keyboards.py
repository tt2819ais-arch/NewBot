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
        InlineKeyboardButton("Инструкция агента", callback_data="agent_instructions"),
        InlineKeyboardButton("Назад", callback_data="back_to_main")
    )
    return keyboard

def get_members_menu(users, is_admin=False):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for user in users:
        user_id, _, username, full_name, role = user[:5]
        role_icon = "👑" if role == 'admin' else "👤"
        keyboard.add(InlineKeyboardButton(
            f"{role_icon} {role}: @{username}",
            callback_data=f"view_{user_id}"
        ))
    
    if is_admin:
        keyboard.add(
            InlineKeyboardButton("Удалить агента", callback_data="delete_agent_menu"),
            InlineKeyboardButton("Удалить всех агентов", callback_data="delete_all_confirm")
        )
    
    keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_main"))
    return keyboard

def get_delete_agents_menu(agents):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for agent in agents:
        user_id, _, username = agent[:3]
        keyboard.add(InlineKeyboardButton(
            f"❌ @{username}",
            callback_data=f"delete_{user_id}"
        ))
    
    keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_members"))
    return keyboard

def get_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="confirm_delete_all"),
        InlineKeyboardButton("❌ Нет", callback_data="cancel_delete")
    )
    return keyboard

def get_back_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_help"))
    return keyboard
