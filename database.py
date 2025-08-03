import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger(__name__)

def get_db_connection(config):
    return psycopg2.connect(**config, cursor_factory=RealDictCursor)

def create_tables(config):
    try:
        conn = get_db_connection(config)
        with conn.cursor() as cur:
            logger.info("Создание таблицы admins...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    telegram_id BIGINT PRIMARY KEY,
                    comment VARCHAR(100)
                );
            """)
            logger.info("Создание таблицы moderators...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS moderators (
                    user_id BIGINT PRIMARY KEY,
                    comment VARCHAR(100)
                );
            """)
            logger.info("Создание таблицы products...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    price DECIMAL(10, 2) NOT NULL,
                    category_id INTEGER,
                    sizes TEXT,
                    main_images BYTEA[]
                );
            """)
            logger.info("Создание таблицы promotions...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS promotions (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    banner_image BYTEA
                );
            """)
            logger.info("Создание таблицы categories...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    image BYTEA
                );
            """)
            logger.info("Создание таблицы product_colors...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_colors (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER REFERENCES products(id),
                    color VARCHAR(50) NOT NULL,
                    images BYTEA[]
                );
            """)
            logger.info("Создание таблицы main_banner...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS main_banner (
                    id SERIAL PRIMARY KEY,
                    image BYTEA
                );
            """)
            logger.info("Создание таблицы orders...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255),
                    customer_name VARCHAR(255) NOT NULL,
                    customer_phone VARCHAR(50) NOT NULL,
                    delivery_address TEXT NOT NULL,
                    delivery_type VARCHAR(50) NOT NULL,
                    delivery_method VARCHAR(50) NOT NULL,
                    cart_json JSONB NOT NULL,
                    total DECIMAL(10, 2) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                INSERT INTO admins (telegram_id, comment) 
                VALUES (%s, %s) 
                ON CONFLICT (telegram_id) DO NOTHING
            """, (580970066, "Главный админ"))
            conn.commit()
        conn.close()
        logger.info("Таблицы успешно созданы или уже существуют.")
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {str(e)}")
        raise