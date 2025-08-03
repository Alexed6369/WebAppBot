import logging
import threading
import json
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from database import get_db_connection, create_tables
from config import TOKEN, DB_CONFIG
import subprocess
import os
import psycopg2

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.handlers = [handler]

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

WEBAPP_URL = "https://x2id32-80-80-116-135.ru.tuna.am"
logger.info(f"Используется URL: {WEBAPP_URL}")

def run_flask():
    subprocess.Popen(["python", "flask_app.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

async def is_admin(telegram_id):
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS(SELECT 1 FROM admins WHERE telegram_id = %s)", (telegram_id,))
        result = cur.fetchone()["exists"]
    conn.close()
    return result

async def is_moderator(user_id):
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS(SELECT 1 FROM moderators WHERE user_id = %s)", (user_id,))
        result = cur.fetchone()["exists"]
    conn.close()
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получена команда /start от {update.effective_user.id}")
    user_id = update.effective_user.id
    is_admin_user = await is_admin(user_id)
    
    keyboard = [
        [InlineKeyboardButton("Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("Мои заказы", callback_data="my_orders")]
    ]
    if is_admin_user:
        keyboard.append([InlineKeyboardButton("Админ-панель", callback_data="admin_menu")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Добро пожаловать в магазин! Нажми ниже:", reply_markup=markup)

async def debug_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получено обновление: {update.to_dict()}")

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT id, created_at, total FROM orders WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        orders = cur.fetchall()
    conn.close()
    
    if not orders:
        await query.edit_message_text("У вас пока нет заказов.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]))
    else:
        keyboard = [[InlineKeyboardButton(f"Заказ #{o['id']} ({o['total']} ₽) - {o['created_at'].strftime('%d.%m.%Y')}", callback_data=f"order_{o['id']}")] for o in orders]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
        await query.edit_message_text("Ваши заказы:", reply_markup=InlineKeyboardMarkup(keyboard))

async def view_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    conn.close()
    
    if order:
        cart_items = order["cart_json"]
        delivery_type_map = {"pickup": "Самовывоз", "delivery": "Доставка до двери"}
        delivery_method_map = {
            "pickup": {"sdek": "СДЭК", "store": "Забрать со склада"},
            "delivery": {"sdek": "СДЭК", "yandex": "Яндекс Доставка", "store": "Доставка сотрудником магазина"}
        }
        delivery_type = delivery_type_map.get(order["delivery_type"], order["delivery_type"])
        delivery_method = delivery_method_map.get(order["delivery_type"], {}).get(order["delivery_method"], order["delivery_method"])
        
        order_text = f"📦 Заказ #{order['id']} от 🕒 {order['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
        order_text += f"👤 Клиент: {order['customer_name']}\n"
        order_text += f"📞 Телефон: {order['customer_phone']}\n"
        order_text += f"🏠 Адрес: {order['delivery_address']}\n"
        order_text += f"🚚 Тип доставки: {delivery_type} ({delivery_method})\n\n"
        order_text += "🛒 Товары:\n" + "\n".join([f"➡️ {item['name']} ({item['size']}, {item['color']}) - {item['quantity']} шт. ({item['price'] * item['quantity']} ₽)" for item in cart_items]) + "\n\n"
        order_text += f"💸 Итого: {order['total']} ₽"
        
        await query.edit_message_text(order_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="my_orders")]]))
    else:
        await query.edit_message_text("❌ Заказ не найден.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="my_orders")]]))

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("🛍️ Товары", callback_data="manage_products")],
            [InlineKeyboardButton("📢 Баннеры", callback_data="manage_promotions")],
            [InlineKeyboardButton("📋 Категории", callback_data="manage_categories")],
            [InlineKeyboardButton("🏞️ Главный баннер", callback_data="manage_main_banner")],
            [InlineKeyboardButton("👮‍♂️ Модераторы", callback_data="manage_moderators")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await update.message.reply_text("🔧 Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("🚫 У вас нет доступа.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "my_orders":
        await my_orders(update, context)
    elif query.data.startswith("order_"):
        await view_order(update, context)
    elif query.data == "admin_menu":
        if await is_admin(user_id):
            keyboard = [
                [InlineKeyboardButton("🛍️ Товары", callback_data="manage_products")],
                [InlineKeyboardButton("📢 Баннеры", callback_data="manage_promotions")],
                [InlineKeyboardButton("📋 Категории", callback_data="manage_categories")],
                [InlineKeyboardButton("🏞️ Главный баннер", callback_data="manage_main_banner")],
                [InlineKeyboardButton("👮‍♂️ Модераторы", callback_data="manage_moderators")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
            ]
            await query.edit_message_text("🔧 Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("🚫 У вас нет доступа.")
    elif query.data == "manage_moderators":
        if await is_admin(user_id):
            keyboard = [
                [InlineKeyboardButton("➕ Добавить модератора", callback_data="add_moderator")],
                [InlineKeyboardButton("🗑️ Удалить модератора", callback_data="delete_moderator")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")]
            ]
            await query.edit_message_text("👮‍♂️ Управление модераторами:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("🚫 У вас нет доступа.")
    elif query.data == "add_moderator":
        await query.edit_message_text("Введите Telegram ID пользователя для добавления в модераторы:")
        context.user_data["state"] = "WAITING_MODERATOR_ID"
    elif query.data == "delete_moderator":
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, comment FROM moderators")
            moderators = cur.fetchall()
        conn.close()
        if not moderators:
            await query.edit_message_text("👮‍♂️ Модераторов нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_moderators")]]))
        else:
            keyboard = [[InlineKeyboardButton(f"ID: {m['user_id']} ({m['comment'] or 'Без комментария'})", callback_data=f"delete_moderator_{m['user_id']}")] for m in moderators]
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_moderators")])
            await query.edit_message_text("Выберите модератора для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("delete_moderator_"):
        moderator_id = int(query.data.split("_")[2])
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM moderators WHERE user_id = %s", (moderator_id,))
            conn.commit()
        conn.close()
        await query.edit_message_text("✅ Модератор удалён.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_moderators")]]))
    elif query.data == "manage_products":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
            [InlineKeyboardButton("🗑️ Удалить товар", callback_data="delete_product")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")]
        ]
        await query.edit_message_text("🛍️ Управление товарами:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "manage_main_banner":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить главный баннер", callback_data="add_main_banner")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")]
        ]
        await query.edit_message_text("🏞️ Управление главным баннером:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "add_main_banner":
        await query.edit_message_text("Отправьте фото главного баннера:")
        context.user_data["state"] = "WAITING_MAIN_BANNER_PHOTO"
    elif query.data == "add_product":
        await query.edit_message_text("Введите название товара:")
        context.user_data["state"] = "WAITING_PRODUCT_NAME"
    elif query.data == "delete_product":
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM products")
            products = cur.fetchall()
        conn.close()
        if not products:
            await query.edit_message_text("🛍️ Товаров нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_products")]]))
        else:
            keyboard = [[InlineKeyboardButton(f"{p['name']} (ID: {p['id']})", callback_data=f"delete_product_{p['id']}")] for p in products]
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_products")])
            await query.edit_message_text("Выберите товар для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("delete_product_"):
        product_id = int(query.data.split("_")[2])
        conn = get_db_connection(DB_CONFIG)
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM product_colors WHERE product_id = %s", (product_id,))
                cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
                conn.commit()
            await query.edit_message_text("✅ Товар удалён.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_products")]]))
        except Exception as e:
            conn.rollback()
            logger.error(f"Ошибка при удалении товара: {str(e)}")
            await query.edit_message_text("❌ Ошибка при удалении товара.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_products")]]))
        finally:
            conn.close()
    elif query.data == "manage_promotions":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить баннер", callback_data="add_promotion")],
            [InlineKeyboardButton("🗑️ Удалить баннер", callback_data="delete_promotion")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await query.edit_message_text("📢 Управление баннерами:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "add_promotion":
        await query.edit_message_text("Введите заголовок баннера:")
        context.user_data["state"] = "WAITING_PROMOTION_TITLE"
    elif query.data == "delete_promotion":
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT id, title FROM promotions")
            promotions = cur.fetchall()
        conn.close()
        if not promotions:
            await query.edit_message_text("📢 Баннеров нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_promotions")]]))
        else:
            keyboard = [[InlineKeyboardButton(f"{p['title']} (ID: {p['id']})", callback_data=f"delete_promotion_{p['id']}")] for p in promotions]
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_promotions")])
            await query.edit_message_text("Выберите баннер для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("delete_promotion_"):
        promotion_id = int(query.data.split("_")[2])
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM promotions WHERE id = %s", (promotion_id,))
            conn.commit()
        conn.close()
        await query.edit_message_text("✅ Баннер удалён.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_promotions")]]))
    elif query.data == "manage_categories":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить категорию", callback_data="add_category")],
            [InlineKeyboardButton("🗑️ Удалить категорию", callback_data="delete_category")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")]
        ]
        await query.edit_message_text("📋 Управление категориями:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "add_category":
        await query.edit_message_text("Введите название новой категории:")
        context.user_data["state"] = "WAITING_CATEGORY_NAME"
    elif query.data == "delete_category":
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM categories")
            categories = cur.fetchall()
        conn.close()
        if not categories:
            await query.edit_message_text("📋 Категорий нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_categories")]]))
        else:
            keyboard = [[InlineKeyboardButton(f"{c['name']} (ID: {c['id']})", callback_data=f"delete_category_{c['id']}")] for c in categories]
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_categories")])
            await query.edit_message_text("Выберите категорию для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("delete_category_"):
        category_id = int(query.data.split("_")[2])
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id = %s", (category_id,))
            conn.commit()
        conn.close()
        await query.edit_message_text("✅ Категория удалена.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_categories")]]))
    elif query.data == "admin_back":
        keyboard = [
            [InlineKeyboardButton("🛍️ Товары", callback_data="manage_products")],
            [InlineKeyboardButton("📢 Баннеры", callback_data="manage_promotions")],
            [InlineKeyboardButton("📋 Категории", callback_data="manage_categories")],
            [InlineKeyboardButton("🏞️ Главный баннер", callback_data="manage_main_banner")],
            [InlineKeyboardButton("👮‍♂️ Модераторы", callback_data="manage_moderators")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await query.edit_message_text("🔧 Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("select_category_"):
        category_id = int(query.data.split("_")[2])
        context.user_data["product_data"]["category_id"] = category_id
        colors = ["Белый", "Чёрный", "Красный", "Бежевый", "Серый", "Оранжевый", "Синий", "Фиолетовый", "Зелёный", "Голубой"]
        keyboard = [[InlineKeyboardButton(f"{color} {'✅' if color in context.user_data['product_data']['colors'] else ''}", callback_data=f"color_{color.lower()}")] for color in colors]
        keyboard.append([InlineKeyboardButton("Подтвердить ✅", callback_data="confirm_colors")])
        await query.edit_message_text("Выберите возможные цвета товара:", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data["state"] = "WAITING_COLOR_SELECTION"
    elif query.data.startswith("color_"):
        color = query.data.split("_")[1].capitalize()
        if color in context.user_data["product_data"]["colors"]:
            context.user_data["product_data"]["colors"].remove(color)
        else:
            context.user_data["product_data"]["colors"].append(color)
        colors = ["Белый", "Чёрный", "Красный", "Бежевый", "Серый", "Оранжевый", "Синий", "Фиолетовый", "Зелёный", "Голубой"]
        keyboard = [[InlineKeyboardButton(f"{c} {'✅' if c in context.user_data['product_data']['colors'] else ''}", callback_data=f"color_{c.lower()}")] for c in colors]
        keyboard.append([InlineKeyboardButton("Подтвердить ✅", callback_data="confirm_colors")])
        await query.edit_message_text("Выберите возможные цвета товара:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "confirm_colors":
        if not context.user_data["product_data"]["colors"]:
            await query.edit_message_text("❌ Выберите хотя бы один цвет!")
        else:
            context.user_data["product_data"]["color_photos"] = {}
            context.user_data["product_data"]["current_color"] = context.user_data["product_data"]["colors"][0]
            context.user_data["product_data"]["current_color_index"] = 0
            await query.edit_message_text(f"Отправьте главную фотографию для цвета '{context.user_data['product_data']['current_color']}':")
            context.user_data["state"] = f"WAITING_MAIN_PHOTO_{context.user_data['product_data']['current_color']}"
    elif query.data == "add_more_photos":
        current_color = context.user_data["product_data"]["current_color"]
        await query.edit_message_text(f"Отправьте ещё одну фотографию для цвета '{current_color}':")
        context.user_data["state"] = f"WAITING_ADDITIONAL_PHOTO_{current_color}"
    elif query.data == "next_color":
        context.user_data["product_data"]["current_color_index"] += 1
        if context.user_data["product_data"]["current_color_index"] < len(context.user_data["product_data"]["colors"]):
            next_color = context.user_data["product_data"]["colors"][context.user_data["product_data"]["current_color_index"]]
            context.user_data["product_data"]["current_color"] = next_color
            await query.edit_message_text(f"Отправьте главную фотографию для цвета '{next_color}':")
            context.user_data["state"] = f"WAITING_MAIN_PHOTO_{next_color}"
        else:
            await query.edit_message_text("Введите размеры товара (через запятую, например: S,M,L):")
            context.user_data["state"] = "WAITING_SIZES"
    elif query.data == "back":
        is_admin_user = await is_admin(user_id)
        keyboard = [
            [InlineKeyboardButton("Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("Мои заказы", callback_data="my_orders")]
        ]
        if is_admin_user:
            keyboard.append([InlineKeyboardButton("Админ-панель", callback_data="admin_menu")])
        markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Добро пожаловать в магазин! Нажми ниже:", reply_markup=markup)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get("state")

    if state == "WAITING_MODERATOR_ID":
        if await is_admin(user_id):
            try:
                moderator_id = int(text)
                conn = get_db_connection(DB_CONFIG)
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO moderators (user_id, comment) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                        (moderator_id, "Модератор заказов")
                    )
                    conn.commit()
                conn.close()
                await update.message.reply_text(
                    f"✅ Модератор с ID {moderator_id} добавлен.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_moderators")]])
                )
            except ValueError:
                await update.message.reply_text("❌ Введите корректный Telegram ID (число).")
            context.user_data.clear()
        else:
            await update.message.reply_text("🚫 У вас нет доступа.")
            context.user_data.clear()
    elif state == "WAITING_CATEGORY_NAME":
        context.user_data["category_data"] = {"name": text}
        await update.message.reply_text("Отправьте фото категории:")
        context.user_data["state"] = "WAITING_CATEGORY_PHOTO"
    elif state == "WAITING_PRODUCT_NAME":
        context.user_data["product_data"] = {"name": text, "colors": [], "color_photos": {}, "current_color_index": 0}
        await update.message.reply_text("Введите цену товара (в рублях):")
        context.user_data["state"] = "WAITING_PRODUCT_PRICE"
    elif state == "WAITING_PRODUCT_PRICE":
        try:
            price = float(text)
            context.user_data["product_data"]["price"] = price
            await update.message.reply_text("Введите описание товара:")
            context.user_data["state"] = "WAITING_PRODUCT_DESCRIPTION"
        except ValueError:
            await update.message.reply_text("❌ Введите корректную цену (число):")
    elif state == "WAITING_PRODUCT_DESCRIPTION":
        context.user_data["product_data"]["description"] = text
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM categories")
            categories = cur.fetchall()
        conn.close()
        if not categories:
            await update.message.reply_text("❌ Сначала создайте хотя бы одну категорию в разделе 'Категории'.")
            context.user_data.clear()
        else:
            keyboard = [[InlineKeyboardButton(c["name"], callback_data=f"select_category_{c['id']}")] for c in categories]
            await update.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))
            context.user_data["state"] = "WAITING_CATEGORY_SELECTION"
    elif state == "WAITING_PROMOTION_TITLE":
        context.user_data["promotion_data"] = {"title": text}
        await update.message.reply_text("Отправьте фотографию баннера:")
        context.user_data["state"] = "WAITING_PROMOTION_PHOTO"
    elif state == "WAITING_SIZES":
        context.user_data["product_data"]["sizes"] = text
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            first_color = context.user_data["product_data"]["colors"][0]
            main_images = context.user_data["product_data"]["color_photos"].get(first_color, [])
            if not main_images:
                await update.message.reply_text("❌ Нет фотографий для первого цвета!")
                return
            cur.execute(
                "INSERT INTO products (name, description, price, category_id, sizes, main_images) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    context.user_data["product_data"]["name"],
                    context.user_data["product_data"]["description"],
                    context.user_data["product_data"]["price"],
                    context.user_data["product_data"]["category_id"],
                    context.user_data["product_data"]["sizes"],
                    main_images
                )
            )
            product_id = cur.fetchone()["id"]
            for color in context.user_data["product_data"]["colors"]:
                cur.execute(
                    "INSERT INTO product_colors (product_id, color, images) VALUES (%s, %s, %s)",
                    (product_id, color, context.user_data["product_data"]["color_photos"].get(color, []))
                )
            conn.commit()
        conn.close()
        await update.message.reply_text(
            f"✅ Товар '{context.user_data['product_data']['name']}' добавлен.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_products")]])
        )
        context.user_data.clear()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    if state not in ["WAITING_CATEGORY_PHOTO", "WAITING_PROMOTION_PHOTO", "WAITING_MAIN_BANNER_PHOTO"] and not state.startswith("WAITING_MAIN_PHOTO_") and not state.startswith("WAITING_ADDITIONAL_PHOTO_"):
        return

    photo_file = update.message.photo[-1]
    file = await photo_file.get_file()
    file_path = await file.download_to_drive()
    with open(file_path, 'rb') as f:
        image_data = f.read()
    images = [psycopg2.Binary(image_data)]
    os.remove(file_path)

    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        if state.startswith("WAITING_MAIN_PHOTO_"):
            current_color = context.user_data["product_data"]["current_color"]
            context.user_data["product_data"]["color_photos"][current_color] = images
            keyboard = [
                [InlineKeyboardButton("Добавить ещё", callback_data="add_more_photos")],
                [InlineKeyboardButton("Следующий цвет", callback_data="next_color")]
            ]
            await update.message.reply_text(
                f"✅ Главная фотография для цвета '{current_color}' добавлена.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif state.startswith("WAITING_ADDITIONAL_PHOTO_"):
            current_color = context.user_data["product_data"]["current_color"]
            context.user_data["product_data"]["color_photos"][current_color].extend(images)
            keyboard = [
                [InlineKeyboardButton("Добавить ещё", callback_data="add_more_photos")],
                [InlineKeyboardButton("Следующий цвет", callback_data="next_color")]
            ]
            await update.message.reply_text(
                f"✅ Дополнительная фотография для цвета '{current_color}' добавлена.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif state == "WAITING_CATEGORY_PHOTO":
            cur.execute(
                "INSERT INTO categories (name, image) VALUES (%s, %s)",
                (context.user_data["category_data"]["name"], images[0])
            )
            conn.commit()
            await update.message.reply_text(
                f"✅ Категория '{context.user_data['category_data']['name']}' добавлена.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_categories")]])
            )
        elif state == "WAITING_PROMOTION_PHOTO":
            cur.execute(
                "INSERT INTO promotions (title, banner_image) VALUES (%s, %s)",
                (context.user_data["promotion_data"]["title"], images[0])
            )
            conn.commit()
            await update.message.reply_text(
                f"✅ Баннер '{context.user_data['promotion_data']['title']}' добавлен.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_promotions")]])
            )
            context.user_data.clear()
        elif state == "WAITING_MAIN_BANNER_PHOTO":
            cur.execute("DELETE FROM main_banner")
            cur.execute(
                "INSERT INTO main_banner (image) VALUES (%s)",
                (images[0],)
            )
            conn.commit()
            await update.message.reply_text(
                "✅ Главный баннер добавлен.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_main_banner")]])
            )
            context.user_data.clear()

    logger.info(f"Добавлен баннер/акция: {state}")
    conn.close()
    if state in ["WAITING_CATEGORY_PHOTO", "WAITING_PROMOTION_PHOTO", "WAITING_MAIN_BANNER_PHOTO"]:
        context.user_data.clear()

def main():
    logger.info("Запуск приложения...")
    try:
        create_tables(DB_CONFIG)
        logger.info("Таблицы базы данных созданы или уже существуют")
    except Exception as e:
        logger.error(f"Не удалось создать таблицы: {str(e)}")
        return

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(my_orders, pattern="^my_orders$"))
    application.add_handler(CallbackQueryHandler(view_order, pattern="^order_"))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.ALL, debug_update), group=-1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()

if __name__ == "__main__":
    main()