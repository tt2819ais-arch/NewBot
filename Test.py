import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота с вашим токеном
API_TOKEN = '8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc'
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Главное меню с инлайн-кнопками
def get_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    buttons = [
        InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings"),
        InlineKeyboardButton("📢 Объявление", callback_data="menu_announce"),
        InlineKeyboardButton("👥 Участники", callback_data="menu_members"),
        InlineKeyboardButton("ℹ️ Помощь", callback_data="menu_help"),
        InlineKeyboardButton("🎲 Рандом", callback_data="menu_random")
    ]
    
    keyboard.add(*buttons[:2])
    keyboard.add(*buttons[2:4])
    keyboard.add(*buttons[4:])
    
    return keyboard

# Обработчик команды /start или /menu
@dp.message_handler(commands=['start', 'menu'])
async def send_welcome(message: types.Message):
    # Проверяем, находится ли бот в групповом чате
    if message.chat.type in ['group', 'supergroup']:
        await message.answer(
            "🤖 Добро пожаловать! Я тестовый бот для групповых чатов.\n\n"
            "Выберите действие из меню ниже:",
            reply_markup=get_main_menu()
        )
    else:
        await message.answer("Этот бот предназначен для работы в групповых чатах!")

# Обработчик инлайн-кнопок
@dp.callback_query_handler(lambda c: c.data.startswith('menu_'))
async def process_callback(callback_query: types.CallbackQuery):
    data = callback_query.data
    
    # Отвечаем на callback_query, чтобы убрать "часики" у кнопки
    await callback_query.answer()
    
    # Обработка разных кнопок
    if data == "menu_stats":
        await bot.send_message(
            callback_query.message.chat.id,
            "📊 Статистика группы:\n"
            "• Участников: [информация о количестве]\n"
            "• Активность: высокая\n"
            "• Сообщений сегодня: 150",
            reply_markup=get_main_menu()
        )
    elif data == "menu_settings":
        await bot.send_message(
            callback_query.message.chat.id,
            "⚙️ Настройки бота:\n"
            "• Уведомления: включены\n"
            "• Авто-модерация: активна\n"
            "• Приветствие: включено",
            reply_markup=get_main_menu()
        )
    elif data == "menu_announce":
        await bot.send_message(
            callback_query.message.chat.id,
            "📢 Функция объявлений:\n"
            "Используйте /announce текст\n"
            "для отправки объявления",
            reply_markup=get_main_menu()
        )
    elif data == "menu_members":
        await bot.send_message(
            callback_query.message.chat.id,
            "👥 Управление участниками:\n"
            "• /kick - исключить участника\n"
            "• /ban - забанить участника\n"
            "• /mute - ограничить возможность писать",
            reply_markup=get_main_menu()
        )
    elif data == "menu_help":
        await bot.send_message(
            callback_query.message.chat.id,
            "ℹ️ Доступные команды:\n"
            "/start или /menu - главное меню\n"
            "/help - справка\n"
            "/stats - статистика\n"
            "Все функции доступны через инлайн-меню!",
            reply_markup=get_main_menu()
        )
    elif data == "menu_random":
        import random
        await bot.send_message(
            callback_query.message.chat.id,
            f"🎲 Случайное число: {random.randint(1, 100)}",
            reply_markup=get_main_menu()
        )

# Обработчик команды /help
@dp.message_handler(commands=['help'])
async def send_help(message: types.Message):
    if message.chat.type in ['group', 'supergroup']:
        await message.answer(
            "🆘 Помощь по использованию бота:\n\n"
            "1. Используйте команду /menu для вызова меню\n"
            "2. Нажимайте на кнопки для выполнения действий\n"
            "3. Бот работает только в групповых чатах\n\n"
            "Для связи с разработчиком: @ваш_аккаунт",
            reply_markup=get_main_menu()
        )

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен! Добавьте его в группу и используйте команды /start или /menu")
    executor.start_polling(dp, skip_updates=True)
