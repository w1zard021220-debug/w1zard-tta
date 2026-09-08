import telebot
import requests
import base64
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ================= НАСТРОЙКИ КЛЮЧЕЙ =================
TELEGRAM_BOT_TOKEN = "8868901043:AAFxArEHuWiIoS-WdxhEJujYRMrac6tiGt0"
PROXY_API_KEY = "sk-lLJox1FKfolbZOyZX9EIqXUB0qPYLUX2"
# ===================================================

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
API_URL = "https://api.proxyapi.ru/v1/chat/completions"

SYSTEM_PROMPT = """
Ты — профессиональный школьный репетитор и отличник. Твоя задача — решить задание СТРОГО в формате для записи в школьную тетрадь.

ЖЕСТКИЕ ПРАВИЛА:
1. НИКАКОЙ ВОДЫ. Никаких приветствий, вступлений ("Вот решение:"), пояснений от себя или прощаний. Сразу начинай с оформления.
2. ФОРМАТ ДЛЯ ТОЧНЫХ НАУК (Математика, Алгебра, Геометрия, Физика, Химия):
   Дано: (кратко условия)
   Найти / Доказать: (что требуется)
   Решение:
   (Понятные пошаговые действия с формулами и вычислениями)
   Ответ: (жирным, четко и однозначно).

3. ФОРМАТ ДЛЯ ГУМАНИТАРНЫХ НАУК (Русский язык, Литература, История, Обществознание):
   - Только тезисы, четкие списки или готовый текст для переписывания.
   - Если в задании нужно вставить буквы/знаки: выдели вставленные буквы жирным шрифтом.

4. ЗАПРЕЩЕНО ИСПОЛЬЗОВАТЬ LaTeX (никаких обратных слэшей, \\frac, \\text). Формулы пиши простыми символами: "/", "^", "*".

5. Язык: Русский. Текст должен быть компактным, чтобы легко переписать в тетрадь за 2 минуты.
"""

def encode_image(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message, 
        "⚡ *W1zarD School Fast-Pass Bot [VISION]*\n\n"
        "Я готов! Скинь мне:\n"
        "📸 **Фотографию** задачи или упражнения\n"
        "✍️ Либо обычный **текст**\n\n"
        "Я мгновенно выдам готовый чистовик для тетради.",
        parse_mode="Markdown"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    status_msg = bot.reply_to(message, "⏳ Считываю фото и пишу чистовик...")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        base64_image = encode_image(downloaded_file)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {PROXY_API_KEY}"
        }
        
        user_text = message.caption if message.caption else "Реши задание на этой фотографии."
        combined_instruction = f"{SYSTEM_PROMPT}\n\nЗадание ученика: {user_text}"
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": combined_instruction},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            "max_tokens": 1500
        }
        
        response = requests.post(API_URL, headers=headers, json=payload, timeout=35)
        
        if response.status_code == 200:
            result = response.json()
            answer = result['choices'][0]['message']['content'].strip()
            bot.delete_message(message.chat.id, status_msg.message_id)
            try:
                bot.reply_to(message, answer, parse_mode="Markdown")
            except Exception:
                bot.reply_to(message, answer)
        else:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', str(response.text))
            bot.edit_message_text(f"❌ Ошибка API ({response.status_code}): {error_msg}", message.chat.id, status_msg.message_id)
            
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка распознавания: {e}", message.chat.id, status_msg.message_id)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text.startswith('/'):
        return
    status_msg = bot.reply_to(message, "⏳ Секунду, пишу чистовик...")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {PROXY_API_KEY}"
    }
    
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message.text}
        ],
        "temperature": 0.3
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            result = response.json()
            answer = result['choices'][0]['message']['content'].strip()
            bot.delete_message(message.chat.id, status_msg.message_id)
            bot.reply_to(message, answer, parse_mode="Markdown")
        else:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', 'Неизвестная ошибка')
            bot.edit_message_text(f"❌ Ошибка API ({response.status_code}): {error_msg}", message.chat.id, status_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка соединения: {e}", message.chat.id, status_msg.message_id)

# Простейший веб-сервер для прохождения health check на Render Web Service
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot is alive 24/7!")
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

if __name__ == "__main__":
    # 1. Запуск веб-сервера в фоне
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # 2. Запуск телеграм-бота
    print("🚀 Безотказный VISION-бот запущен 24/7!")
    bot.infinity_polling()