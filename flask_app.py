import logging
from flask import Flask, jsonify, send_from_directory, request
import base64
import json
from database import get_db_connection
from config import DB_CONFIG
import requests
import hashlib
from datetime import datetime, timedelta



# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO  
)
logger = logging.getLogger(__name__)

last_order_times = {}

app = Flask(__name__, static_folder="webapp/static", static_url_path="/static")

def generate_tinkoff_token(payload):
    params = {k: str(v) for k, v in payload.items() if k != "Token" and k != "Receipt"}
    params["Password"] = TINKOFF_TERMINAL_PASSWORD
    sorted_params = sorted(params.items())
    concat = "".join(value for _, value in sorted_params)
    token = hashlib.sha256(concat.encode('utf-8')).hexdigest()
    logger.info(f"Generated Tinkoff token params: {sorted_params}")
    logger.info(f"Concatenated string: {concat}")
    logger.info(f"Generated token: {token}")
    return token

@app.route('/api/checkout', methods=['POST'])
def checkout():
    try:
        data = request.get_json()
        if not data or data.get('action') != 'checkout':
            return jsonify({"error": "Invalid request"}), 400

        logger.info(f"Получен заказ: {data}")

        user_id = data.get('user_id', 0)
        if not user_id:
            logger.warning("user_id отсутствует, используется заглушка: 0")

        now = datetime.now()
        last_order_time = last_order_times.get(user_id)
        if last_order_time and (now - last_order_time) < timedelta(seconds=5):
            logger.warning(f"Повторный заказ от {user_id} в течение 5 секунд, игнорируем")
            return jsonify({"status": "ignored", "message": "Повторный заказ проигнорирован"}), 429

        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (user_id, username, customer_name, customer_phone, delivery_address, delivery_type, delivery_method, cart_json, total, payment_status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, created_at",
                (
                    user_id,
                    data['username'],
                    data['customer']['name'],
                    data['customer']['phone'],
                    data['delivery']['address'],
                    data['delivery']['type'],
                    data['delivery']['method'],
                    json.dumps(data['cart']),
                    data['total'],
                    'PENDING'
                )
            )
            order_data = cur.fetchone()
            order_id = order_data["id"]
            created_at = order_data["created_at"]
            conn.commit()
        conn.close()

        last_order_times[user_id] = now

        receipt_items = []
        for item in data['cart']:
            receipt_items.append({
                "Name": item['name'],
                "Price": int(float(item['price']) * 100),
                "Quantity": item['quantity'],
                "Amount": int(float(item['price']) * item['quantity'] * 100),
                "Tax": "none"
            })

        amount_in_kopecks = int(float(data['total']) * 100)
        tinkoff_payload = {
            "TerminalKey": TINKOFF_TERMINAL_KEY,
            "Amount": amount_in_kopecks,
            "OrderId": str(order_id),
            "Description": f"Оплата заказа #{order_id}",
            "NotificationURL": "",
            "SuccessURL": "",
            "FailURL": "",
            "Receipt": {
                "Email": "customer@example.com",
                "Phone": data['customer']['phone'],
                "Taxation": "osn",
                "Items": receipt_items
            }
        }
        logger.info(f"Tinkoff payload before token: {tinkoff_payload}")
        tinkoff_payload["Token"] = generate_tinkoff_token(tinkoff_payload)
        logger.info(f"Tinkoff payload with token: {tinkoff_payload}")
        tinkoff_response = requests.post(TINKOFF_API_URL, json=tinkoff_payload)
        tinkoff_result = tinkoff_response.json()

        if tinkoff_response.status_code != 200 or not tinkoff_result.get("Success"):
            logger.error(f"Ошибка Т-Кассы: {tinkoff_result}")
            return jsonify({"error": "Tinkoff payment initialization failed", "message": tinkoff_result.get("Message", "Unknown error")}), 500

        payment_url = tinkoff_result["PaymentURL"]
        payment_id = str(tinkoff_result["PaymentId"])  

        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET payment_id = %s WHERE id = %s",
                (payment_id, order_id)
            )
            conn.commit()
        conn.close()

        return jsonify({"status": "success", "order_id": order_id, "payment_url": payment_url, "payment_id": payment_id}), 200

    except Exception as e:
        logger.error(f"Ошибка в /api/checkout: {str(e)}")
        return jsonify({"error": "Internal server error", "message": str(e)}), 500
    
@app.route('/api/check_order_status', methods=['GET'])
def check_order_status():
    order_id = request.args.get('order_id')
    if not order_id:
        return jsonify({"error": "Order ID is required"}), 400

    try:
        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payment_status FROM orders WHERE id = %s",
                (order_id,)
            )
            result = cur.fetchone()
        conn.close()

        if result:
            return jsonify({"status": result['payment_status']}), 200
        else:
            return jsonify({"error": "Order not found"}), 404

    except Exception as e:
        logger.error(f"Ошибка при проверке статуса заказа {order_id}: {str(e)}")
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

@app.route('/api/tkassa_notifications', methods=['POST'])
def tkassa_notifications():
    data = request.get_json()
    logger.info(f"Получено уведомление от Т-Кассы: {data}")
    payment_id = str(data.get('PaymentId'))
    status = data.get('Status')
    order_id = data.get('OrderId')

    if not payment_id or not order_id:
        logger.warning("Отсутствует payment_id или order_id в уведомлении")
        return jsonify({"status": "ok"}), 200

    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT payment_status, created_at, user_id, username, customer_name, customer_phone, delivery_address, delivery_type, delivery_method, cart_json, total "
            "FROM orders WHERE payment_id = %s AND id = %s",
            (payment_id, order_id)
        )
        order = cur.fetchone()

        if not order:
            logger.info(f"Заказ {order_id} с платежом {payment_id} не найден в базе, пропускаем")
            conn.close()
            return jsonify({"status": "ok"}), 200

        if order['payment_status'] == 'CONFIRMED':
            logger.info(f"Заказ {order_id} с платежом {payment_id} уже подтвержден, пропускаем")
            conn.close()
            return jsonify({"status": "ok"}), 200

        if datetime.now() - order['created_at'] > timedelta(days=1):
            logger.info(f"Заказ {order_id} слишком старый (создан {order['created_at']}), пропускаем")
            conn.close()
            return jsonify({"status": "ok"}), 200

        if status == 'CONFIRMED':
            logger.info(f"Платёж {payment_id} подтверждён для заказа {order_id}")
            cur.execute(
                "UPDATE orders SET payment_status = 'CONFIRMED' WHERE id = %s AND payment_id = %s",
                (order_id, payment_id)
            )
            conn.commit()
        else:
            conn.close()
            return jsonify({"status": "ok"}), 200

    conn.close()

    if status == 'CONFIRMED':
        user_id = order['user_id']
        username = order['username']
        total = order['total']
        created_at = order['created_at']
        cart_json = order['cart_json']
        customer_name = order['customer_name']
        customer_phone = order['customer_phone']
        delivery_address = order['delivery_address']
        delivery_type = order['delivery_type']
        delivery_method = order['delivery_method']

        delivery_type_map = {"pickup": "Самовывоз", "delivery": "Доставка до двери"}
        delivery_method_map = {
            "pickup": {"sdek": "СДЭК", "store": "Забрать со склада"},
            "delivery": {"sdek": "СДЭК", "yandex": "Яндекс Доставка", "store": "Доставка сотрудником магазина"}
        }
        delivery_type_text = delivery_type_map.get(delivery_type, delivery_type)
        delivery_method_text = delivery_method_map.get(delivery_type, {}).get(delivery_method, delivery_method)

        order_text = f"🔔 Новый оплаченный заказ #{order_id}\n\n"
        order_text += f"👤 Покупатель: @{username} (ID: {user_id})\n"
        order_text += f"📋 Номер заказа: {order_id}\n"
        order_text += f"🛒 Содержание заказа:\n" + "\n".join(
            [f"- {item['name']} ({item['size']}, {item['color']}) - {item['quantity']} шт. ({item['price'] * item['quantity']} ₽)"
             for item in cart_json]) + "\n\n"
        order_text += f"💰 Стоимость: {total} ₽\n"
        order_text += f"🏠 Адрес доставки: {delivery_address}\n"
        order_text += f"🙋‍♂️ ФИО: {customer_name}\n"
        order_text += f"📞 Телефон: {customer_phone}\n"
        order_text += f"🚚 Тип получения: {delivery_type_text}\n"
        order_text += f"📦 Подтип получения: {delivery_method_text}\n"
        order_text += f"⏰ Время создания: {created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"

        user_text = (
            f"✅ Заказ #{order_id} успешно оплачен!\n\n"
            f"👤 Покупатель: @{username} (ID: {user_id})\n"
            f"💰 Сумма: {total} ₽\n"
            f"Спасибо за покупку! Скоро с вами свяжется модератор."
        )
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {"chat_id": user_id, "text": user_text}
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Уведомление об успешной оплате отправлено пользователю {user_id}")
            else:
                logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {response.text}")
        except Exception as e:
            logger.error(f"Исключение при отправке пользователю {user_id}: {str(e)}")

        conn = get_db_connection(DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM moderators")
            moderators = cur.fetchall()
        conn.close()

        if moderators:
            for moderator in moderators:
                moderator_id = moderator['user_id']
                try:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {"chat_id": moderator_id, "text": order_text}
                    response = requests.post(url, json=payload)
                    if response.status_code == 200:
                        logger.info(f"Уведомление отправлено модератору {moderator_id}")
                    else:
                        logger.error(f"Ошибка отправки модератору {moderator_id}: {response.text}")
                except Exception as e:
                    logger.error(f"Исключение при отправке модератору {moderator_id}: {str(e)}")

    return jsonify({"status": "ok"}), 200

@app.route('/api/categories', methods=['GET'])
def get_categories():
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, image FROM categories")
        categories = cur.fetchall()
    conn.close()
    return jsonify([{
        "id": c["id"],
        "name": c["name"],
        "image": base64.b64encode(c["image"]).decode('utf-8') if c["image"] else None
    } for c in categories])

@app.route('/api/main_banner', methods=['GET'])
def get_main_banner():
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT image, CURRENT_TIMESTAMP as last_updated FROM main_banner ORDER BY id DESC LIMIT 1")
        banner = cur.fetchone()
    conn.close()
    if banner and banner["image"]:
        return jsonify({
            "image": base64.b64encode(banner["image"]).decode('utf-8'),
            "last_updated": banner["last_updated"].isoformat()
        })
    return jsonify({"image": None, "last_updated": None})

@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, price, category_id, main_images[1] as image FROM products"
        )
        products = cur.fetchall()
    conn.close()
    return jsonify([{
        "id": p["id"],
        "name": p["name"],
        "description": p["description"],
        "price": float(p["price"]),
        "category_id": p["category_id"],
        "image": base64.b64encode(p["image"]).decode('utf-8') if p["image"] else None
    } for p in products])

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, price, category_id, sizes, main_images "
            "FROM products WHERE id = %s",
            (product_id,)
        )
        product = cur.fetchone()
        cur.execute(
            "SELECT color, images FROM product_colors WHERE product_id = %s",
            (product_id,)
        )
        colors = cur.fetchall()
    conn.close()
    if product:
        return jsonify({
            "id": product["id"],
            "name": product["name"],
            "description": product["description"],
            "price": float(product["price"]),
            "category_id": product["category_id"],
            "sizes": product["sizes"],
            "main_images": [base64.b64encode(img).decode('utf-8') for img in product["main_images"]] if product["main_images"] else [],
            "colors": [
                {
                    "color": c["color"],
                    "images": [base64.b64encode(img).decode('utf-8') for img in c["images"]] if c["images"] else []
                } for c in colors
            ]
        })
    else:
        return jsonify({"error": "Product not found"}), 404

@app.route('/api/promotions', methods=['GET'])
def get_promotions():
    conn = get_db_connection(DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SELECT id, title, banner_image, CURRENT_TIMESTAMP as last_updated FROM promotions")
        promotions = cur.fetchall()
    conn.close()
    response = [{
        "id": p["id"],
        "title": p["title"],
        "banner_image": base64.b64encode(p["banner_image"]).decode('utf-8') if p["banner_image"] else None,
        "last_updated": p["last_updated"].isoformat()
    } for p in promotions]
    return jsonify({"promotions": response, "last_updated": max([p["last_updated"].isoformat() for p in promotions], default=None)})

@app.route('/')
def index():
    return send_from_directory('webapp', 'index.html')

@app.route('/<path:filename>')
def serve_html(filename):
    return send_from_directory('webapp', filename)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)