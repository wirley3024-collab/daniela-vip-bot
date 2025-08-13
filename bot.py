import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===============================
# CONFIGURACIONES
# ===============================
TOKEN = "8295186417:AAHx6aLSG31DvUDnC4MI8JYxpK0FKH8uAdM"
PAYMENT_LINK = "https://buy.stripe.com/28EfZj4vo0J4bD0ggX0RG00"

# Fotos (file_id)
PHOTOS = [
    "AgACAgEAAxkBAAMEaJ0EcSsxX5pDz9AP9pArdkkSAAGdAALssDEb-k3oRAXL7AjJVWfxAQADAgADbQADNgQ",
    "AgACAgEAAxkBAAMFaJ0Eccad85zp3X08PzOc-JBIryAAAuuwMRv6TehELOxoQSuw_TIBAAMCAANtAAM2BA",
    "AgACAgEAAxkBAAMGaJ0EcS8jOgn1wLFvy56_BAuR0jkAAu2wMRv6TehE4NhOjH31DScBAAMCAAN4AAM2BA"
]

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

def kb_inicio():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🆓 Ver muestras", callback_data="ver_muestras"))
    kb.add(InlineKeyboardButton("ℹ️ Saber más", callback_data="saber_mas"))
    return kb

def kb_post_muestras():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Sí, quiero el enlace", callback_data="pedir_enlace"))
    kb.add(InlineKeyboardButton("🔁 Ver de nuevo", callback_data="ver_muestras"))
    return kb

def kb_pago():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 Suscribirme ahora", url=PAYMENT_LINK))
    kb.add(InlineKeyboardButton("❓ Dudas", callback_data="dudas"))
    return kb

# Mensajes
INTRO_1 = (
    "Hola cariño 😘\n"
    "Soy *Daniela* y te voy a cuidar *muy bien* por aquí… ¿Seguimos? 🔥"
)

INTRO_2 = (
    "Dentro de *Daniela Vip* comparto mis fotos y vídeos más *calientes*, sin censura, "
    "con sorpresas diarias y atención personalizada. ¿Quieres una probadita gratis? 👀"
)

MUESTRAS_HEADER = "Aquí tienes *algunas fotos gratis* 📸\nDisfrútalas:"
MUESTRAS_FOOTER = (
    "¿Te gustaron las fotos? 😏\n"
    "Si quieres *más contenido exclusivo* y acceso completo, puedo enviarte el *enlace de pago*."
)

SABER_MAS = (
    "🔒 *¿Qué recibes en Daniela Vip?*\n"
    "• Contenido exclusivo diario (fotos y vídeos)\n"
    "• Peticiones personalizadas (en privado)\n"
    "• Sorpresas en vivo\n"
    "• Soporte 1 a 1 conmigo 💋\n\n"
    "¿Listo para entrar? Pulsa abajo:"
)

CTA_FINAL = (
    "Perfecto 😈\n"
    "Si ya estás segura/o, toca el botón y te doy acceso inmediato:"
)

DUDAS = (
    "¿Tienes dudas? Escríbeme lo que necesitas y te respondo por aquí 💬"
)

FALLBACK = (
    "No te entendí 😅\n"
    "Pulsa *🆓 Ver muestras* para recibir fotos gratis o *ℹ️ Saber más* para conocer el club."
)

# Handlers
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, INTRO_1, reply_markup=kb_inicio())
    bot.send_message(message.chat.id, INTRO_2)

@bot.callback_query_handler(func=lambda c: c.data == "ver_muestras")
def cb_ver_muestras(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    bot.send_message(chat_id, MUESTRAS_HEADER)
    for fid in PHOTOS:
        bot.send_photo(chat_id, fid)
    bot.send_message(chat_id, MUESTRAS_FOOTER, reply_markup=kb_post_muestras())

@bot.callback_query_handler(func=lambda c: c.data == "saber_mas")
def cb_saber_mas(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, SABER_MAS, reply_markup=kb_pago())

@bot.callback_query_handler(func=lambda c: c.data == "pedir_enlace")
def cb_pedir_enlace(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, CTA_FINAL, reply_markup=kb_pago())

@bot.callback_query_handler(func=lambda c: c.data == "dudas")
def cb_dudas(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, DUDAS)

@bot.message_handler(func=lambda m: True)
def any_text(message):
    text = (message.text or "").lower()
    if any(w in text for w in ["gratis", "muestra", "fotos"]):
        bot.send_message(message.chat.id, MUESTRAS_HEADER)
        for fid in PHOTOS:
            bot.send_photo(message.chat.id, fid)
        bot.send_message(message.chat.id, MUESTRAS_FOOTER, reply_markup=kb_post_muestras())
    elif any(w in text for w in ["pago", "link", "enlace"]):
        bot.send_message(message.chat.id, CTA_FINAL, reply_markup=kb_pago())
    else:
        bot.send_message(message.chat.id, FALLBACK, reply_markup=kb_inicio())

print("🤖 Daniela Vip Bot ejecutándose…")
bot.infinity_polling(skip_pending=True)
