# bot.py
import os
import sys
import time
import sqlite3
import threading
from typing import Optional

import requests
import stripe
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, jsonify

# ===============================
# CONFIG (via variáveis de ambiente)
# ===============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
PRICE_ID = os.getenv("PRICE_ID")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
BOT_USERNAME = os.getenv("BOT_USERNAME")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

missing = []
if not TELEGRAM_TOKEN: missing.append("TELEGRAM_TOKEN")
if GROUP_CHAT_ID == 0: missing.append("GROUP_CHAT_ID")
if not STRIPE_SECRET_KEY: missing.append("STRIPE_SECRET_KEY")
if not STRIPE_WEBHOOK_SECRET: missing.append("STRIPE_WEBHOOK_SECRET")
if not PRICE_ID: missing.append("PRICE_ID")
if not PUBLIC_BASE_URL: missing.append("PUBLIC_BASE_URL")
if not BOT_USERNAME: missing.append("BOT_USERNAME")
if missing:
    raise RuntimeError(f"Faltam variáveis de ambiente: {', '.join(missing)}")

stripe.api_key = STRIPE_SECRET_KEY
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

TELEGRAM_WEBHOOK_PATH = f"/telegram/{TELEGRAM_TOKEN}"

# ===============================
# DB (SQLite)
# ===============================
DB_PATH = "subscriptions.db"

def db_init():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS subs (
        telegram_user_id INTEGER PRIMARY KEY,
        subscription_id TEXT,
        customer_id TEXT,
        status TEXT,
        current_period_end INTEGER,
        created_at INTEGER
      )
    """)
    conn.commit()
    conn.close()

def db_upsert_sub(tg_id: int, sub_id: Optional[str], cust_id: Optional[str],
                  status: str, period_end_epoch: Optional[int]):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
      INSERT INTO subs (telegram_user_id, subscription_id, customer_id, status, current_period_end, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(telegram_user_id) DO UPDATE SET
        subscription_id=excluded.subscription_id,
        customer_id=excluded.customer_id,
        status=excluded.status,
        current_period_end=excluded.current_period_end
    """, (tg_id, sub_id, cust_id, status, int(period_end_epoch or 0), int(time.time())))
    conn.commit()
    conn.close()

def db_find_by_subscription(sub_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_user_id, status FROM subs WHERE subscription_id=?", (sub_id,))
    row = c.fetchone()
    conn.close()
    return row

def db_get_all_expired(now_epoch: Optional[int] = None):
    now_epoch = now_epoch or int(time.time())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_user_id FROM subs WHERE current_period_end < ? AND status != 'canceled'", (now_epoch,))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def db_set_status_by_sub(sub_id: str, status: str, period_end_epoch: Optional[int] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if period_end_epoch is None:
        c.execute("UPDATE subs SET status=? WHERE subscription_id=?", (status, sub_id))
    else:
        c.execute("UPDATE subs SET status=?, current_period_end=? WHERE subscription_id=?", (status, int(period_end_epoch), sub_id))
    conn.commit()
    conn.close()

# ===============================
# TELEGRAM helpers (HTTP)
# ===============================
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def tg_call(method, payload):
    try:
        r = requests.post(f"{API_BASE}/{method}", json=payload, timeout=15)
        if not r.ok:
            print("Telegram API error:", r.text, file=sys.stdout)
        return r.json()
    except Exception as e:
        print("Telegram call exception:", e, file=sys.stdout)
        return {"ok": False, "error": str(e)}

def send_dm(user_id, text, buttons=None):
    data = {"chat_id": user_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    return tg_call("sendMessage", data)

def create_one_use_invite() -> Optional[str]:
    expire = int(time.time()) + 24 * 3600
    res = tg_call("createChatInviteLink", {"chat_id": GROUP_CHAT_ID, "expire_date": expire, "member_limit": 1})
    if res.get("ok") and res["result"].get("invite_link"):
        return res["result"]["invite_link"]
    return None

def kick_from_group(user_id: int):
    tg_call("banChatMember", {"chat_id": GROUP_CHAT_ID, "user_id": user_id})
    time.sleep(0.5)
    tg_call("unbanChatMember", {"chat_id": GROUP_CHAT_ID, "user_id": user_id})

# ===============================
# UI / Textos
# ===============================
INTRO_1 = (
    "Hola, cariño 😘\n"
    "Soy *Daniela* y aquí comparto mi contenido más *exclusivo*.\n"
    "¿Quieres ver una probadita gratis? 🔥"
)
INTRO_2 = (
    "Dentro de *Daniela Vip* encontrarás fotos y videos sin censura, sorpresas diarias "
    "y atención personalizada. ¿Te enseño algunas muestras? 👀"
)
MUESTRAS_HEADER = "Aquí tienes *algunas fotos gratis* 📸\nDisfrútalas:"
MUESTRAS_FOOTER = (
    "¿Te gustaron? 😏\n"
    "Si quieres *más contenido exclusivo* y acceso completo, toca abajo:"
)
PAGO_OK = "💖 *¡Pago confirmado!* Preparando tu acceso VIP…"
INVITE_READY = (
    "✨ ¡Listo! Entra con este *enlace único* (24h, 1 uso):\n\n{invite}\n\n"
    "Te espero adentro… 💋"
)
RENEW_FAIL = (
    "⚠️ Tu pago no se procesó o la suscripción fue cancelada.\n"
    "Tu acceso fue pausado. Cuando regularices, te reactivo el acceso. 💬"
)
FALLBACK = (
    "No te entendí 😅\n"
    "Pulsa *🆓 Ver fotos gratis* o *💳 Suscribirme ahora*."
)

PHOTOS = [
    "AgACAgEAAxkBAAMEaJ0EcSsxX5pDz9AP9pArdkkSAAGdAALssDEb-k3oRAXL7AjJVWfxAQADAgADbQADNgQ",
    "AgACAgEAAxkBAAMFaJ0Eccad85zp3X08PzOc-JBIryAAAuuwMRv6TehELOxoQSuw_TIBAAMCAANtAAM2BA",
    "AgACAgEAAxkBAAMGaJ0EcS8jOgn1wLFvy56_BAuR0jkAAu2wMRv6TehE4NhOjH31DScBAAMCAAN4AAM2BA"
]

def make_checkout_session(chat_id: int) -> str:
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": PRICE_ID, "quantity": 1}],
            success_url=f"https://t.me/{BOT_USERNAME}?start=paid",
            cancel_url=f"https://t.me/{BOT_USERNAME}?start=cancel",
            client_reference_id=str(chat_id),
            customer_creation="always",
            metadata={"telegram_user_id": str(chat_id)},
        )
        return session.url
    except Exception as e:
        print("[checkout] erro criando checkout:", e, file=sys.stdout)
        return f"https://t.me/{BOT_USERNAME}"

def kb_inicio(chat_id: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🆓 Ver fotos gratis", callback_data="ver_muestras"))
    checkout_url = make_checkout_session(chat_id)
    if checkout_url:
        kb.add(InlineKeyboardButton("💳 Suscribirme ahora", url=checkout_url))
    else:
        kb.add(InlineKeyboardButton("❌ Error creando pago", callback_data="error_pago"))
    return kb

def kb_post_muestras(chat_id: int):
    kb = InlineKeyboardMarkup()
    checkout_url = make_checkout_session(chat_id)
    if checkout_url:
        kb.add(InlineKeyboardButton("✅ Quiero suscribirme", url=checkout_url))
    else:
        kb.add(InlineKeyboardButton("❌ Error creando pago", callback_data="error_pago"))
    kb.add(InlineKeyboardButton("🔁 Ver de nuevo", callback_data="ver_muestras"))
    return kb

# ===============================
# BOT handlers (webhook)
# ===============================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, INTRO_1, reply_markup=kb_inicio(message.chat.id))
    bot.send_message(message.chat.id, INTRO_2)


@bot.callback_query_handler(func=lambda c: c.data == "error_pago")
def cb_error_pago(call):
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "⚠️ Lo siento, ocurrió un error creando tu pago.\n"
        "Por favor, intenta de nuevo más tarde o contacta soporte."
    )


@bot.callback_query_handler(func=lambda c: c.data == "ver_muestras")
def cb_ver_muestras(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    bot.send_message(chat_id, MUESTRAS_HEADER)
    for fid in PHOTOS:
        bot.send_photo(chat_id, fid)
    bot.send_message(chat_id, MUESTRAS_FOOTER, reply_markup=kb_post_muestras(chat_id))

# ===============================
# FLASK endpoints
# ===============================
@app.get("/")
def health():
    return "OK", 200

@app.post(TELEGRAM_WEBHOOK_PATH)
def telegram_webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
        bot.process_new_updates([update])
    except Exception as e:
        print("Erro no telegram_webhook:", e, file=sys.stdout)
    return "OK", 200

@app.post("/webhook")
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        tel_id = int(data.get("client_reference_id") or data.get("metadata", {}).get("telegram_user_id", 0))
        sub_id = data.get("subscription")
        cust_id = data.get("customer")

        try:
            sub = stripe.Subscription.retrieve(sub_id) if sub_id else None
            period_end = sub["current_period_end"] if sub else int(time.time()) + 30*24*3600
            status = sub["status"] if sub else "active"
        except Exception as e:
            print("[webhook] erro recuperando subscription:", e, file=sys.stdout)
            period_end = int(time.time()) + 30*24*3600
            status = "active"

        if tel_id:
            db_upsert_sub(tel_id, sub_id, cust_id, status, period_end)
            send_dm(tel_id, PAGO_OK)
            invite = create_one_use_invite()
            if invite:
                send_dm(tel_id, INVITE_READY.format(invite=invite))
            else:
                send_dm(tel_id, "Pago ok, pero no pude generar tu invitación ahora. Escríbeme y lo resuelvo enseguida. 💬")

    elif etype == "invoice.payment_succeeded":
        sub_id = data.get("subscription")
        if sub_id:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                db_set_status_by_sub(sub_id, sub["status"], sub["current_period_end"])
            except Exception as e:
                print("[webhook] erro ao atualizar status pós-sucesso:", e, file=sys.stdout)
                db_set_status_by_sub(sub_id, "active")

    elif etype == "invoice.payment_failed":
        sub_id = data.get("subscription")
        if sub_id:
            row = db_find_by_subscription(sub_id)
            if row:
                tel_id, _ = row
                db_set_status_by_sub(sub_id, "past_due")
                kick_from_group(tel_id)
                send_dm(tel_id, RENEW_FAIL)

    elif etype in ["customer.subscription.deleted", "customer.subscription.updated"]:
        sub = data
        sub_id = sub.get("id")
        status = sub.get("status")
        row = db_find_by_subscription(sub_id)
        if row:
            tel_id, _ = row
            db_set_status_by_sub(sub_id, status, sub.get("current_period_end"))
            if status in ["canceled", "unpaid"]:
                kick_from_group(tel_id)
                send_dm(tel_id, RENEW_FAIL)

    return jsonify({"received": True}), 200

@app.get("/sucesso")
def pagina_sucesso():
    return f"""
    <html>
      <head>
        <meta charset="UTF-8">
        <title>Pagamento Confirmado</title>
        <style>
          body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 50px; background-color: #f7f7f7; }}
          .container {{ background: white; padding: 30px; border-radius: 10px; display: inline-block; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }}
          h1 {{ color: #2ecc71; }}
          a.botao {{ background-color: #2ecc71; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-size: 18px; display: inline-block; margin-top: 20px; }}
          a.botao:hover {{ background-color: #27ae60; }}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>✅ Pagamento Confirmado!</h1>
          <p>Bem-vindo ao nosso grupo VIP no Telegram!</p>
          <a href="https://t.me/{BOT_USERNAME}" class="botao">Abrir o Bot</a>
        </div>
      </body>
    </html>
    """

@app.post("/create-checkout-session")
def create_checkout_session():
    try:
        data = request.get_json(silent=True) or {}
        chat_id = int(data.get("chat_id", 0))
        url = make_checkout_session(chat_id) if chat_id else f"https://t.me/{BOT_USERNAME}"
        return jsonify({"url": url})
    except Exception as e:
        return jsonify(error=str(e)), 400

# ===============================
# tarefa diária
# ===============================
def daily_pruner():
    while True:
        try:
            now = int(time.time())
            for uid in db_get_all_expired(now):
                try:
                    kick_from_group(uid)
                    print(f"[PRUNER] expulsado por expiración: {uid}", file=sys.stdout)
                except Exception as e:
                    print(f"[PRUNER] error expulsando {uid}: {e}", file=sys.stdout)
        except Exception as e:
            print("[PRUNER] error ciclo:", e, file=sys.stdout)
        time.sleep(24 * 3600)

# ===============================
# MAIN
# ===============================
def start_bot():
    print("[INIT] Iniciando aplicação...", file=sys.stdout)
    db_init()
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.set_webhook(
        url=f"{PUBLIC_BASE_URL}{TELEGRAM_WEBHOOK_PATH}",
        allowed_updates=telebot.util.update_types,
        drop_pending_updates=True
    )
    threading.Thread(target=daily_pruner, daemon=True).start()

if __name__ == "__main__":
    start_bot()
    port = int(os.environ["PORT"])
    print(f"[FLASK] Rodando na porta {port}", file=sys.stdout)
    app.run(host="0.0.0.0", port=port)































