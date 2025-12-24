import logging
import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения
API_TOKEN = os.getenv('TELEGRAM_TOKEN', '8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc')

# Проверка токена
if not API_TOKEN:
    logger.error("Токен не найден! Установите переменную окружения TELEGRAM_TOKEN")
    exit(1)

# Инициализация бота
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

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
        await message.answer(
            "Этот бот предназначен для работы в групповых чатах!\n"
            "Добавьте меня в группу и используйте команды /start или /menu"
        )

# Обработчик команды /help
@dp.message_handler(commands=['help'])
async def send_help(message: types.Message):
    help_text = (
        "🆘 Помощь по использованию бота:\n\n"
        "📋 Доступные команды:\n"
        "/start или /menu - главное меню\n"
        "/help - эта справка\n"
        "/ping - проверка работы бота\n\n"
        "🎯 Инлайн-меню содержит:\n"
        "• Статистика группы\n"
        "• Настройки бота\n"
        "• Функции объявлений\n"
        "• Управление участниками\n"
        "• Случайные числа\n\n"
        "⚙️ Бот работает в групповых чатах!"
    )
    
    if message.chat.type in ['group', 'supergroup']:
        await message.answer(help_text, reply_markup=get_main_menu())
    else:
        await message.answer(help_text)

# Обработчик команды /ping
@dp.message_handler(commands=['ping'])
async def ping(message: types.Message):
    await message.answer("🏓 Понг! Бот работает исправно!")

# Обработчик инлайн-кнопок
@dp.callback_query_handler(lambda c: c.data.startswith('menu_'))
async def process_callback(callback_query: types.CallbackQuery):
    data = callback_query.data
    
    # Отвечаем на callback_query, чтобы убрать "часики" у кнопки
    await callback_query.answer()
    
    # Обработка разных кнопок
    if data == "menu_stats":
        response = (
            "📊 Статистика группы:\n"
            "• Участников: информация обновляется\n"
            "• Активность: высокая\n"
            "• Сообщений сегодня: 150\n"
            "• Бот добавлен: ✓"
        )
    elif data == "menu_settings":
        response = (
            "⚙️ Настройки бота:\n"
            "• Уведомления: включены\n"
            "• Авто-модерация: активна\n"
            "• Приветствие: включено\n"
            "• Режим: групповой чат"
        )
    elif data == "menu_announce":
        response = (
            "📢 Функция объявлений:\n"
            "Чтобы отправить объявление всем участникам:\n\n"
            "1. Ответьте на это сообщение командой:\n"
            "<code>/announce ваш текст</code>\n\n"
            "2. Или упомяните бота:\n"
            "@{} ваше объявление"
        ).format((await bot.get_me()).username)
    elif data == "menu_members":
        response = (
            "👥 Управление участниками:\n"
            "• /kick - исключить участника\n"
            "• /ban - забанить участника\n"
            "• /mute - ограничить возможность писать\n\n"
            "⚠️ Требуются права администратора!"
        )
    elif data == "menu_help":
        response = (
            "ℹ️ Помощь и поддержка:\n\n"
            "📌 Основные команды:\n"
            "/start - запуск бота\n"
            "/menu - главное меню\n"
            "/help - справка\n\n"
            "🔧 Для администраторов:\n"
            "Используйте меню для управления группой"
        )
    elif data == "menu_random":
        import random
        responses = [
            f"🎲 Ваше случайное число: {random.randint(1, 100)}",
            f"🎯 Выпало: {random.randint(1, 6)} (кубик)",
            f"🔢 Случайное: {random.choice(['Орёл', 'Решка'])}",
            f"🎪 Магия чисел: {random.randint(1, 20)}"
        ]
        response = random.choice(responses)
    else:
        response = "Неизвестная команда"
    
    await bot.send_message(
        callback_query.message.chat.id,
        response,
        reply_markup=get_main_menu(),
        parse_mode='HTML'
    )

# Обработчик команды /announce
@dp.message_handler(commands=['announce'])
async def announce(message: types.Message):
    if message.chat.type in ['group', 'supergroup']:
        # Проверяем, является ли отправитель администратором
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        
        if chat_member.status in ['creator', 'administrator']:
            text = message.text.replace('/announce', '').strip()
            if text:
                await message.answer(f"📢 Объявление от администратора:\n\n{text}")
            else:
                await message.answer("Использование: /announce ваш текст")
        else:
            await message.answer("⛔ Эта команда только для администраторов!")

# Обработчик упоминания бота
@dp.message_handler(lambda message: message.text and 
                   ((await bot.get_me()).username in message.text))
async def mention_handler(message: types.Message):
    if message.chat.type in ['group', 'supergroup']:
        await message.reply(
            "👋 Я здесь! Используйте /menu для вызова меню",
            reply_markup=get_main_menu()
        )

# Обработчик новых участников
@dp.message_handler(content_types=['new_chat_members'])
async def new_member_handler(message: types.Message):
    for new_member in message.new_chat_members:
        if new_member.id == (await bot.get_me()).id:
            await message.answer(
                "🤖 Спасибо за добавление! Я бот для управления группой.\n"
                "Используйте /menu для доступа к функциям управления.",
                reply_markup=get_main_menu()
            )
            break

# Функция для уведомления о запуске
async def on_startup(dp):
    bot_info = await bot.get_me()
    logger.info(f"Бот @{bot_info.username} запущен!")
    logger.info(f"ID бота: {bot_info.id}")
    logger.info(f"Имя бота: {bot_info.first_name}")
    
    # Отправляем сообщение разработчику, если указан ID
    developer_id = os.getenv('DEVELOPER_ID')
    if developer_id:
        try:
            await bot.send_message(
                developer_id,
                f"🤖 Бот @{bot_info.username} успешно запущен!\n"
                f"Время запуска: {asyncio.get_event_loop().time()}\n"
                f"Готов к работе в группах!"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление разработчику: {e}")

# Функция для уведомления об остановке
async def on_shutdown(dp):
    logger.info("Бот останавливается...")
    await bot.close()

# Запуск бота
if __name__ == '__main__':
    logger.info("Запуск бота...")
    
    try:
        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown
        )
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
