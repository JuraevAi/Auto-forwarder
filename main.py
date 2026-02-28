import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask
from threading import Thread

# ==========================================
# 1. SOZLAMALAR (Render.com dan olinadi)
# ==========================================
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

DESTINATION_CHANNEL = os.environ.get("DESTINATION_CHANNEL") 
REPLACEMENT_TEXT = os.environ.get("REPLACEMENT_TEXT", DESTINATION_CHANNEL)

# Qaysi kanallardan xabar olinadi? (Masalan: kunuz, daryo_uz)
SOURCE_CHATS_RAW = os.environ.get("SOURCE_CHATS", "")
SOURCE_CHATS = [chat.strip().replace("@", "") for chat in SOURCE_CHATS_RAW.split(",") if chat.strip()]

QIDIRUV_ANDOZASI = r'@[A-Za-z0-9_]+|https?://[^\s]+|t\.me/[^\s]+'

# ==========================================
# 2. WEB SERVER (Render botni uxlashiga yo'l qo'ymasligi uchun)
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Userbot 24/7 faol ishlamoqda!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

server_thread = Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# ==========================================
# 3. PYROGRAM USERBOT
# ==========================================
if not SESSION_STRING:
    print("XATOLIK: SESSION_STRING kiritilmagan!")
    exit()

# Botni ishga tushirish
userbot = Client(
    "avto_forwarder",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

def matnni_tahrirlash(matn: str) -> str:
    """Begona link va usernamelarni o'chirib, o'zimiznikini qo'yish"""
    if not matn:
        return ""
    return re.sub(QIDIRUV_ANDOZASI, REPLACEMENT_TEXT, matn)

# Xabarlarni ushlab olish va kanalga tashlash
@userbot.on_message(filters.chat(SOURCE_CHATS) & ~filters.edited)
async def xabar_kelganda(client: Client, message: Message):
    try:
        asl_matn = message.text or message.caption or ""
        tozalan_matn = matnni_tahrirlash(asl_matn)

        # Matnli xabar bo'lsa
        if message.text:
            await client.send_message(
                chat_id=DESTINATION_CHANNEL,
                text=tozalan_matn,
                disable_web_page_preview=True
            )
            print("Matnli xabar yuborildi!")
            
        # Rasm, video yoki boshqa media bo'lsa
        elif message.media:
            await client.copy_message(
                chat_id=DESTINATION_CHANNEL,
                from_chat_id=message.chat.id,
                message_id=message.id,
                caption=tozalan_matn
            )
            print("Media xabar yuborildi!")

    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    print("Userbot ishga tushmoqda...")
    userbot.run()
