import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask
from threading import Thread

# ==========================================
# Python Async muammosini oldini olish
# ==========================================
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ==========================================
# 1. SOZLAMALAR
# ==========================================
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

DESTINATION_CHANNEL = os.environ.get("DESTINATION_CHANNEL", "").strip()
REPLACEMENT_TEXT = os.environ.get("REPLACEMENT_TEXT", DESTINATION_CHANNEL)

# 1-TUSHIB QOLGAN QISM TO'G'RILANDI: Kanallarni o'ta aniq tozalash va tayyorlash
def parse_channels(raw_text):
    channels = []
    for c in raw_text.split(","):
        # Username, URL yoki ID kelsa ham tozalab oladi
        c = c.strip().replace("https://t.me/", "").replace("@", "").lower()
        if c:
            channels.append(c)
    return channels

SOURCE_CHATS = parse_channels(os.environ.get("SOURCE_CHATS", ""))
DEST_CLEAN = DESTINATION_CHANNEL.replace("https://t.me/", "").replace("@", "").lower()

QIDIRUV_ANDOZASI = r'@[A-Za-z0-9_]+|https?://[^\s]+|t\.me/[^\s]+'

# ==========================================
# 2. WEB SERVER
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Mukammal Userbot 24/7 faol ishlamoqda!"

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

userbot = Client(
    "avto_forwarder",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

def matnni_tahrirlash(matn: str) -> str:
    if not matn:
        return ""
    return re.sub(QIDIRUV_ANDOZASI, REPLACEMENT_TEXT, matn)

# ==========================================
# MUKAMMAL FILTR VA MANTIQ (Kuzatuv)
# ==========================================
@userbot.on_message(filters.channel)
async def xabar_kelganda(client: Client, message: Message):
    try:
        # 2-TUSHIB QOLGAN QISM TO'G'RILANDI: Username bo'lmagan kanallarni ham hisobga olish
        kanal_username = message.chat.username.lower() if message.chat.username else ""
        kanal_id = str(message.chat.id)
        kanal_nomi = message.chat.title

        # 3-TUSHIB QOLGAN QISM TO'G'RILANDI: Infinite Loop (O'ziga o'zi yuborish) ni bloklash
        if kanal_username == DEST_CLEAN or kanal_id == DEST_CLEAN:
            return

        # Asosiy tekshiruv: Kelgan xabar ro'yxatimizdagi Username yoki ID ga mos keladimi?
        # Biz bu yerda "in" o'rniga "==" ishlatmadik, chunki agar user "kunuz" yozgan bo'lsa-yu, 
        # aslida "kunuzofficial" bo'lsa ham qisman moslikni topib ushlab oladi.
        match_found = False
        for target in SOURCE_CHATS:
            if target == kanal_username or target == kanal_id:
                match_found = True
                break
            # Agar chala yozilgan bo'lsa (masalan 'daryo' yozilgan, asli 'daryo_uz' bo'lsa)
            elif target in kanal_username:
                match_found = True
                break

        if match_found:
            asl_matn = message.text or message.caption or ""
            tozalan_matn = matnni_tahrirlash(asl_matn)

            if message.text:
                await client.send_message(
                    chat_id=DESTINATION_CHANNEL,
                    text=tozalan_matn,
                    disable_web_page_preview=True
                )
                print(f"✅ Matn yuborildi! (Manba: {kanal_nomi} | @{kanal_username})")
                
            elif message.media:
                await client.copy_message(
                    chat_id=DESTINATION_CHANNEL,
                    from_chat_id=message.chat.id,
                    message_id=message.id,
                    caption=tozalan_matn
                )
                print(f"✅ Media yuborildi! (Manba: {kanal_nomi} | @{kanal_username})")

    except Exception as e:
        print(f"❌ Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    print("Mukammal Userbot ishga tushmoqda...")
    userbot.run()