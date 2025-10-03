import os
import requests
from flask import Flask, request, jsonify, abort
import openai
import logging

# config
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")  # قابل تغییر
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")  # یک مقدار تصادفی امن مثل "supersecret123"
PORT = int(os.environ.get("PORT", 5000))
EXTERNAL_URL = os.environ.get("EXTERNAL_URL")  # آدرس اپلیکیشن روی Render (https://bot-vgmr.onrender.com)

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("لطفاً TELEGRAM_TOKEN و OPENAI_API_KEY را به عنوان env vars تنظیم کنید.")

openai.api_key = OPENAI_API_KEY

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send_telegram_message(chat_id, text, reply_to_message_id=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": reply_to_message_id,
        "parse_mode": "Markdown"
    }
    resp = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)
    return resp.json()

def query_openai_system(user_text):
    # اینجا یک درخواست ساده chat completion می‌سازه
    try:
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=700,
            temperature=0.6,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        app.logger.exception("OpenAI error")
        return f"خطا هنگام تماس با OpenAI: {e}"

@app.route("/health")
def health():
    return "ok", 200

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    """
    برای تنظیم وبهوک از این اندپوینت استفاده کن یا از curl.
    نیاز: EXTERNAL_URL و WEBHOOK_SECRET (اختیاری ولی قویاً توصیه شده)
    """
    if not EXTERNAL_URL:
        return jsonify({"error": "EXTERNAL_URL env var تنظیم نشده"}), 400

    webhook_url = EXTERNAL_URL.rstrip("/") + "/tg_webhook"
    params = {
        "url": webhook_url,
    }
    headers = {}
    # اگر WEBHOOK_SECRET تعیین شده، آن را در پارامتر secret_token قرار می‌دهیم
    if WEBHOOK_SECRET:
        params["secret_token"] = WEBHOOK_SECRET

    resp = requests.post(f"{TELEGRAM_API}/setWebhook", json=params, timeout=15)
    return jsonify(resp.json())

@app.route("/tg_webhook", methods=["POST"])
def tg_webhook():
    # امنیت: اگر secret token ست شده، header مربوطه را بررسی کن
    if WEBHOOK_SECRET:
        header_val = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_val != WEBHOOK_SECRET:
            app.logger.warning("Invalid webhook secret token")
            abort(403)

    data = request.get_json(force=True)
    app.logger.info("Update received: %s", data)

    # فقط پیام‌های متنی ساده را هندل می‌کنیم — می‌تونی گسترش بدی
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        message_id = msg.get("message_id")

        # میشه فرمان /start و ... رو جدا هندل کرد
        if text and text.startswith("/start"):
            send_telegram_message(chat_id, "سلام لیدر پارام من بات هوشمند دیابت پلاس مددی هستم و توسط مبین ساخته شدم که مجهز به هوش مصنوعی هست تقدیم به شما🌹", reply_to_message_id=message_id)
            return jsonify({"ok": True})

        if not text:
            send_telegram_message(chat_id, "فقط پیام‌های متنی پشتیبانی میشن فعلاً.", reply_to_message_id=message_id)
            return jsonify({"ok": True})

        # پاسخ گرفتن از OpenAI
        # برای جلوگیری از طولانی شدن، اول یه پیام "در حال پردازش..." ارسال میکنیم (اختیاری)
        loading = send_telegram_message(chat_id, "در حال درخواست به ChatGPT... لطفا صبر کن.", reply_to_message_id=message_id)

        answer = query_openai_system(text)

        # ارسال پاسخ
        send_telegram_message(chat_id, answer, reply_to_message_id=message_id)

    return jsonify({"ok": True})

if __name__ == "__main__":
    # برای اجرا محلی (render از gunicorn استفاده می‌کنه)
    app.run(host="0.0.0.0", port=PORT)
