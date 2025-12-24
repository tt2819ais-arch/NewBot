import logging
import os
import sys
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

# Получение токена
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not API_TOKEN:
    # Если не нашли в переменных окружения, используем прямой токен
    API_TOKEN = '8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc'
    logger.warning("Используется хардкодный токен!")
else:
    logger.info("Токен получен из переменных окружения")

logger.info(f"Токен (первые 10 символов): {API_TOKEN[:10]}...")

# Инициализация
try:
    bot = Bot(token=API_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(bot, storage=storage)
    logger.info("Бот инициализирован успешно")
except Exception as e:
    logger.error(f"Ошибка инициализации бота: {e}")
    sys.exit(1)

# Главное меню
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
    
    # Добавляем кнопки построчно
    keyboard.add(buttons[0], buttons[1])
    keyboard.add(buttons[2], buttons[3])
    keyboard.add(buttons[4], buttons[5])
    
    return keyboard

# Команда /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    logger.info(f"Получена команда /start от {message.from_user.id} в чате {message.chat.id}")
    
    # Отправляем приветствие
    await message.reply(
        "🤖 Привет! Я бот для групповых чатов.\n\n"
        "Используйте /menu для вызова меню\n"
        "Или /help для справки"
    )

# Команда /menu
@dp.message_handler(commands=['menu'])
async def cmd_menu(message: types.Message):
    logger.info(f"Получена команда /menu от {message.from_user.id}")
    
    # Проверяем тип чата
    if message.chat.type in ['group', 'supergroup']:
        await message.answer(
            "🎛️ <b>Главное меню бота</b>\n\n"
            "Выберите действие:",
            reply_markup=get_main_menu(),
            parse_mode='HTML'
        )
    else:
        await message.answer(
            "⚠️ Этот бот предназначен для работы в групповых чатах!\n"
            "Добавьте меня в группу, чтобы использовать все функции."
        )

# Команда /help
@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = (
        "🆘 <b>Помощь по боту</b>\n\n"
        "📋 <b>Основные команды:</b>\n"
        "/start - начать работу с ботом\n"
        "/menu - открыть главное меню\n"
        "/help - показать эту справку\n"
        "/ping - проверить работу бота\n\n"
        
        "🎯 <b>Инлайн-меню:</b>\n"
        "• Статистика группы\n"
        "• Настройки бота\n"
        "• Объявления\n"
        "• Управление участниками\n"
        "• Случайные числа\n\n"
        
        "⚙️ <b>Для администраторов:</b>\n"
        "/announce [текст] - сделать объявление\n\n"
        
        "📌 <b>Примечание:</b>\n"
        "Бот работает в групповых чатах"
    )
    
    await message.answer(help_text, parse_mode='HTML')

# Команда /ping
@dp.message_handler(commands=['ping'])
async def cmd_ping(message: types.Message):
    await message.answer("🏓 <b>Понг!</b>\nБот работает нормально!", parse_mode='HTML')

# Команда /announce
@dp.message_handler(commands=['announce'])
async def cmd_announce(message: types.Message):
    if message.chat.type in ['group', 'supergroup']:
        text = message.get_args()
        if text:
            await message.answer(f"📢 <b>Объявление:</b>\n\n{text}", parse_mode='HTML')
        else:
            await message.answer("Использование: /announce ваш текст")
    else:
        await message.answer("Эта команда работает только в группах")

# Обработчик инлайн-кнопок
@dp.callback_query_handler(lambda c: c.data.startswith('menu_'))
async def process_callback(callback_query: types.CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    logger.info(f"Нажата кнопка {data} пользователем {user_id}")
    
    # Отвечаем на callback, чтобы убрать "часики"
    await callback_query.answer()
    
    # Обработка разных кнопок
    import random
    responses = {
        "menu_stats": "📊 <b>Статистика группы</b>\n\n"
                     "• Участников: [информация]\n"
                     "• Активность: высокая\n"
                     "• Сообщений сегодня: ~150\n"
                     "• Администраторов: несколько",
        
        "menu_settings": "⚙️ <b>Настройки бота</b>\n\n"
                        "• Авто-модерация: включена\n"
                        "• Приветствия: включены\n"
                        "• Анти-спам: активно\n"
                        "• Логирование: ведется",
        
        "menu_announce": "📢 <b>Функция объявлений</b>\n\n"
                        "Используйте команду:\n"
                        "<code>/announce ваш текст</code>\n\n"
                        "Или напишите мне в личные сообщения для массовой рассылки",
        
        "menu_members": "👥 <b>Управление участниками</b>\n\n"
                       "Доступные команды:\n"
                       "/kick - исключить участника\n"
                       "/ban - забанить участника\n"
                       "/mute - ограничить в чате\n\n"
                       "⚠️ Требуются права администратора",
        
        "menu_help": "ℹ️ <b>Помощь</b>\n\n"
                    "Основные команды:\n"
                    "/menu - главное меню\n"
                    "/help - подробная справка\n"
                    "/ping - проверка работы\n\n"
                    "Для связи: @ваш_аккаунт",
        
        "menu_random": f"🎲 <b>Случайное число:</b> {random.randint(1, 100)}\n\n"
                      f"🎯 <b>Орел или решка:</b> {random.choice(['Орел', 'Решка'])}\n"
                      f"🎪 <b>Удача:</b> {random.choice(['Да', 'Нет', 'Возможно'])}"
    }
    
    response = responses.get(data, "❌ Неизвестная команда")
    
    try:
        # Редактируем существующее сообщение
        await callback_query.message.edit_text(
            response,
            reply_markup=get_main_menu(),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения: {e}")
        # Если не получилось отредактировать, отправляем новое
        await bot.send_message(
            chat_id,
            response,
            reply_markup=get_main_menu(),
            parse_mode='HTML'
        )

# Обработчик любых сообщений (для отладки)
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def debug_handler(message: types.Message):
    logger.info(f"Получено сообщение: chat_id={message.chat.id}, "
                f"type={message.chat.type}, text={message.text}")

# Запуск бота
async def on_startup(dp):
    try:
        bot_info = await bot.get_me()
        logger.info(f"✅ Бот успешно запущен!")
        logger.info(f"🤖 Имя бота: @{bot_info.username}")
        logger.info(f"🆔 ID бота: {bot_info.id}")
        logger.info(f"📛 Имя: {bot_info.first_name}")
        logger.info(f"🚀 Бот готов к работе!")
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}")

async def on_shutdown(dp):
    logger.info("🛑 Остановка бота...")

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🚀 Запуск Telegram бота...")
    logger.info("=" * 50)
    
    try:
        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            timeout=60,
            relax=0.1
        )
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
