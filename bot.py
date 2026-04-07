#!/usr/bin/env python3
import requests
import time
import json
import sqlite3
import logging
from datetime import datetime, date
import config
from yookassa import Payment, Configuration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        balance INTEGER DEFAULT 0, selected_model TEXT DEFAULT 'deepseek-chat',
        free_requests_total INTEGER DEFAULT 20, free_requests_used INTEGER DEFAULT 0,
        daily_used INTEGER DEFAULT 0, last_reset_date TEXT, registered_at TEXT,
        referrals TEXT DEFAULT '[]')''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
        status TEXT, payment_id TEXT, yookassa_id TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_contacts (
        user_id INTEGER PRIMARY KEY, email TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'user_id': row[0], 'username': row[1], 'first_name': row[2],
                'balance': row[3], 'selected_model': row[4],
                'free_requests_total': row[5], 'free_requests_used': row[6],
                'daily_used': row[7], 'last_reset_date': row[8], 'registered_at': row[9],
                'referrals': json.loads(row[10]) if row[10] else []}
    return None

def create_user(user_id, username, first_name):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO users (user_id, username, first_name, balance, selected_model, free_requests_total, free_requests_used, daily_used, last_reset_date, registered_at, referrals) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
              (user_id, username, first_name, 0, 'deepseek-chat', config.FREE_REQUESTS_SYSTEM['registration_bonus'], 0, 0, str(date.today()), str(datetime.now()), '[]'))
    conn.commit()
    conn.close()

def update_user_balance(user_id, amount):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def save_user_email(user_id, email):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO user_contacts (user_id, email) VALUES (?, ?)', (user_id, email))
    conn.commit()
    conn.close()

def get_user_email(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT email FROM user_contacts WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def update_selected_model(user_id, model):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET selected_model = ? WHERE user_id = ?', (model, user_id))
    conn.commit()
    conn.close()

def create_payment_record(user_id, amount, payment_id, yookassa_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT INTO payments (user_id, amount, status, payment_id, yookassa_id, created_at) VALUES (?, ?, ?, ?, ?, ?)',
              (user_id, amount, 'pending', payment_id, yookassa_id, str(datetime.now())))
    conn.commit()
    conn.close()

def update_payment_status(yookassa_id, status):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('UPDATE payments SET status = ? WHERE yookassa_id = ?', (status, yookassa_id))
    conn.commit()
    conn.close()

def get_payment_by_payment_id(payment_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'user_id': row[1], 'amount': row[2], 'status': row[3],
                'payment_id': row[4], 'yookassa_id': row[5], 'created_at': row[6]}
    return None

def reset_daily_limits(user_data):
    today = str(date.today())
    if user_data.get('last_reset_date') != today:
        user_data['daily_used'] = 0
        user_data['last_reset_date'] = today
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        c.execute('UPDATE users SET daily_used = ?, last_reset_date = ? WHERE user_id = ?',
                  (0, today, user_data['user_id']))
        conn.commit()
        conn.close()
        return True
    return False

def can_make_free_request(user, model):
    reset_daily_limits(user)
    if user['daily_used'] < config.FREE_REQUESTS_SYSTEM['daily_free'] and model in config.FREE_REQUESTS_SYSTEM['free_models']:
        return True, 'daily'
    if user['free_requests_used'] < user['free_requests_total']:
        return True, 'bonus'
    return False, None

# ========== MAX API ==========
MAX_TOKEN = config.MAX_BOT_TOKEN
MAX_API_URL = "https://platform-api.max.ru"

def send_message(chat_id, text, keyboard=None):
    if not chat_id:
        logger.error("No chat_id")
        return
    params = {'chat_id': int(chat_id)}  # ← используем chat_id, а не user_id
    payload = {'text': text}
    if keyboard:
        payload['attachments'] = [{'type': 'inline_keyboard', 'payload': {'buttons': keyboard}}]
    try:
        r = requests.post(
            f"{MAX_API_URL}/messages",
            headers={'Authorization': MAX_TOKEN},
            params=params,
            json=payload,
            timeout=10
        )
        print(f"DEBUG: {r.status_code} {r.text}")
        if r.status_code != 200:
            logger.error(f"Send error: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"Send error: {e}")

# ========== AI ФУНКЦИИ ==========
def process_ai(user_message, model_info):
    try:
        if model_info['api_type'] == 'deepseek':
            headers = {'Authorization': f"Bearer {config.DEEPSEEK_API_KEY}", 'Content-Type': 'application/json'}
            url = f"{config.DEEPSEEK_API_BASE}/chat/completions"
        else:
            headers = {'Authorization': f"Bearer {config.PROXYAPI_KEY}", 'Content-Type': 'application/json'}
            url = f"{config.PROXYAPI_BASE}/chat/completions"
        data = {'model': model_info['model_name'], 'messages': [{'role': 'user', 'content': user_message}], 'stream': False}
        r = requests.post(url, headers=headers, json=data, timeout=60)
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content'], None
        return None, f"API error: {r.status_code}"
    except Exception as e:
        return None, str(e)

# ========== ОБРАБОТЧИКИ ==========
def handle_start(chat_id, user_id, username, first_name):
    user = get_user(user_id)
    if not user:
        create_user(user_id, username, first_name)
        user = get_user(user_id)
    reset_daily_limits(user)
    text = f"""🤖 Привет, {first_name}!

🎁 БЕСПЛАТНЫЙ ТАРИФ:
• {config.FREE_REQUESTS_SYSTEM['daily_free']} запросов в день
• +{user['free_requests_total']} бонусных запросов

💫 Твой баланс:
• Бесплатные: {user['free_requests_total'] - user['free_requests_used']}/{user['free_requests_total']}
• Ежедневные: {user['daily_used']}/{config.FREE_REQUESTS_SYSTEM['daily_free']}
• Баланс: {user['balance']} руб

🚀 /models — выбрать модель
🛒 /buy — пополнить баланс"""
    send_message(chat_id, text)  # <-- здесь chat_id

def handle_balance(chat_id, user_id):
    user = get_user(user_id)
    if not user:
        handle_start(chat_id, user_id, '', '')
        return
    reset_daily_limits(user)
    text = f"""💫 ТВОЙ БАЛАНС:

🎁 Бесплатные: {user['free_requests_total'] - user['free_requests_used']}/{user['free_requests_total']}
📅 Ежедневные: {user['daily_used']}/{config.FREE_REQUESTS_SYSTEM['daily_free']}
💰 Баланс: {user['balance']} руб
🧠 Модель: {config.MODELS[user['selected_model']]['name']}"""
    send_message(chat_id, text)

def handle_models(chat_id, user_id):
    keyboard = []
    for mid, info in config.MODELS.items():
        price = 'БЕСПЛАТНО' if info['price'] == 0 else f"{info['price']} руб"
        keyboard.append([{'type': 'callback', 'text': f"{info['name']} - {price}", 'payload': f"model_{mid}"}])
    keyboard.append([{'type': 'callback', 'text': "📋 Описание", 'payload': "model_info"}])
    send_message(chat_id, "🤖 Выбери модель:", keyboard)

def handle_buy(chat_id, user_id):
    email = get_user_email(user_id)
    if not email:
        keyboard = [[{'type': 'callback', 'text': "📧 Указать email", 'payload': "set_email"}]]
        send_message(chat_id, "📢 Для пополнения нужен email для чека", keyboard)
        return
    keyboard = [
        [{'type': 'callback', 'text': "10 руб (тест)", 'payload': "buy_10"}],
        [{'type': 'callback', 'text': "300 руб", 'payload': "buy_300"}],
        [{'type': 'callback', 'text': "1000 руб", 'payload': "buy_1000"}],
        [{'type': 'callback', 'text': "2000 руб", 'payload': "buy_2000"}]
    ]
    send_message(chat_id, f"💫 Выбери сумму:\n📧 Чек на {email}", keyboard)

def handle_message_text(chat_id, user_id, text, username, first_name, waiting):
    if waiting.get(user_id):
        if '@' in text and '.' in text:
            save_user_email(user_id, text)
            send_message(chat_id, f"✅ Email сохранен: {text}\nТеперь используйте /buy")
            waiting[user_id] = False
            return 
        else:
            send_message(chat_id, "❌ Неверный email. Попробуйте еще раз:")
        return
    
    user = get_user(user_id)
    if not user:
        handle_start(chat_id, user_id, username, first_name)
        return
    
    reset_daily_limits(user)
    model = config.MODELS[user['selected_model']]
    
    can_free, free_type = can_make_free_request(user, user['selected_model'])
    if not can_free and user['balance'] < model['price']:
        send_message(chat_id, f"❌ Недостаточно средств! Нужно {model['price']} руб\n🛒 /buy")
        return
    
    cost = 0
    if can_free:
        if free_type == 'daily':
            user['daily_used'] += 1
        else:
            user['free_requests_used'] += 1
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        c.execute('UPDATE users SET daily_used = ?, free_requests_used = ? WHERE user_id = ?',
                  (user['daily_used'], user['free_requests_used'], user_id))
        conn.commit()
        conn.close()
    else:
        cost = model['price']
        update_user_balance(user_id, -cost)
    
    send_message(chat_id, "🤔 Думает...")
    response, error = process_ai(text, model)
    if error:
        if cost > 0:
            update_user_balance(user_id, cost)
        send_message(chat_id, f"❌ Ошибка: {error}")
    else:
        send_message(chat_id, f"🦄 {model['name']}:\n\n{response}")
        
def answer_callback(callback_id, text=None):
    payload = {'callback_query_id': callback_id}
    if text:
        payload['text'] = text
    try:
        r = requests.post(f"{MAX_API_URL}/answerCallbackQuery", headers={'Authorization': MAX_TOKEN}, json=payload, timeout=10)
        if r.status_code != 200:
            logger.error(f"Callback error: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"Callback error: {e}")        

def handle_callback(update, waiting):
    # Пробуем извлечь из разных мест
    user_id = update.get('user_id') or update.get('callback', {}).get('user_id') or update.get('user', {}).get('user_id')
    chat_id = update.get('chat_id') or update.get('callback', {}).get('chat_id') or update.get('message', {}).get('chat_id')
    data = update.get('payload') or update.get('callback', {}).get('payload') or update.get('data')
    
    print(f"DEBUG: user_id={user_id}, chat_id={chat_id}, data={data}")
    
    if not chat_id:
        # Если chat_id не найден, пробуем отправить в известный чат
        chat_id = 76702591
        print(f"DEBUG: используем chat_id по умолчанию: {chat_id}")
    
    if not data:
        send_message(chat_id, "❌ Ошибка: кнопка не передала данные")
        return
    
    if data == "set_email":
        send_message(chat_id, "📧 Введите ваш email:")
        waiting[user_id] = True
        return  
    elif data.startswith("buy_"):
        amount = data.split("_")[1]
        send_message(chat_id, f"💰 Пополнение на {amount} руб (временно)")
    elif data.startswith("model_"):
        mid = data.replace("model_", "")
        if mid == "info":
            text = "📋 ОПИСАНИЕ МОДЕЛЕЙ:\n\n"
            for m, info in config.MODELS.items():
                price = "БЕСПЛАТНО" if info['price'] == 0 else f"{info['price']} руб"
                text += f"• {info['name']} ({price}): {info['description']}\n\n"
            send_message(chat_id, text)
        elif mid in config.MODELS:
            update_selected_model(user_id, mid)
            send_message(chat_id, f"✅ Модель изменена на: {config.MODELS[mid]['name']}")

# ========== GET_UPDATES ==========
def get_updates(offset):
    try:
        params = {'timeout': 30}
        if offset:
            params['marker'] = offset
        r = requests.get(f"{MAX_API_URL}/updates", headers={'Authorization': MAX_TOKEN}, params=params, timeout=35)
        if r.status_code == 200:
            data = r.json()
            return data.get('updates', []), data.get('marker')
        else:
            logger.error(f"Updates error: {r.status_code} {r.text}")
            return [], None
    except Exception as e:
        logger.error(f"Updates error: {e}")
        return [], None

# ========== MAIN ==========
def main():
    init_db()
    print("✅ Бот запущен на Max")
    offset = 0
    waiting = {}
    while True:
        try:
            updates, new_marker = get_updates(offset)
            if new_marker:
                offset = new_marker
            
            if updates:
                print(f"Получено обновлений: {len(updates)}")
            
            for u in updates:
                update_type = u.get('update_type')
                print(f"Тип обновления: {update_type}")
                
                if update_type == 'bot_started':
                    chat_id = u.get('chat_id')
                    user_id = u.get('user', {}).get('user_id')
                    first_name = u.get('user', {}).get('first_name', '')
                    username = u.get('user', {}).get('username', '')
                    print(f"bot_started: chat_id={chat_id}, user_id={user_id}") 
                    if chat_id and user_id:
                        handle_start(chat_id, user_id, username, first_name)
                
                elif update_type == 'message_created':
                    msg = u.get('message', {})
                    chat_id = msg.get('recipient', {}).get('chat_id')
                    user_id = msg.get('sender', {}).get('user_id')
                    first_name = msg.get('sender', {}).get('first_name', '')
                    username = msg.get('sender', {}).get('username', '')
                    text = msg.get('body', {}).get('text', '')
                    print(f"message_created: chat_id={chat_id}, text={text}")

                    if waiting.get(user_id):
                        if '@' in text and '.' in text:
                            save_user_email(user_id, text)
                            send_message(chat_id, f"✅ Email сохранен: {text}\nТеперь используйте /buy")
                            waiting[user_id] = False
                        else:
                           send_message(chat_id, "❌ Неверный email. Попробуйте еще раз:")
                        continue
                    
                    if text == '/start':
                        handle_start(chat_id, user_id, username, first_name)
                    elif text == '/balance':
                        handle_balance(chat_id, user_id)
                    elif text == '/models':
                        handle_models(chat_id, user_id)
                    elif text == '/buy':
                        handle_buy(chat_id, user_id)
                    elif text.startswith('/'):
                        send_message(chat_id, "Неизвестная команда")
                    elif text:
                        handle_message_text(chat_id, user_id, text, username, first_name, waiting)
                
                elif update_type == 'message_callback':
                        print(f"FULL CALLBACK: {json.dumps(u, indent=2)}")  # ← красиво выведет всё
                        handle_callback(u, waiting)
            
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
