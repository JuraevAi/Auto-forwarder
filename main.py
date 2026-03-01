import os
import re
import asyncio
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, compose
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# Asyncio xatoligini oldini olish
# ==========================================
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ==========================================
# 1. SOZLAMALAR (Render maxfiy seyfidan olinadi)
# ==========================================
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

DESTINATION_CHANNEL = os.environ.get("DESTINATION_CHANNEL", "").strip()
REPLACEMENT_TEXT = os.environ.get("REPLACEMENT_TEXT", DESTINATION_CHANNEL)
DEST_CLEAN = DESTINATION_CHANNEL.replace("https://t.me/", "").replace("@", "").lower()

QIDIRUV_ANDOZASI = r'@[A-Za-z0-9_]+|https?://[^\s]+|t\.me/[^\s]+'

# Xotirada saqlanuvchi kanallar ro'yxati (Boshlang'ich holatda Renderdan yuklanadi)
kuzatiladigan_kanallar = []

def init_channels():
    raw = os.environ.get("SOURCE_CHATS", "")
    for c in raw.split(","):
        c = c.strip().replace("https://t.me/", "").replace("@", "").lower()
        if c and c not in kuzatiladigan_kanallar:
            kuzatiladigan_kanallar.append(c)

init_channels()

# ==========================================
# 2. WEB SERVER (Render uxlamasligi uchun)
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Gibrid Userbot va Bot 24/7 faol ishlamoqda!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

server_thread = Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# ==========================================
# 3. KLIENTLARNI YARATISH
# ==========================================
if not SESSION_STRING or not BOT_TOKEN or not ADMIN_ID:
    print("XATOLIK: Maxfiy kalitlar to'liq kiritilmagan!")
    exit()

ADMIN_ID = int(ADMIN_ID)
BOT_ID = None

userbot = Client("aygoqchi", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("boshqaruvchi", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def matnni_tahrirlash(matn: str) -> str:
    if not matn:
        return ""
    return re.sub(QIDIRUV_ANDOZASI, REPLACEMENT_TEXT, matn)

# ==========================================
# 4. USERBOT (Ayg'oqchi) - Ma'lumot tutuvchi
# ==========================================
@userbot.on_message(filters.channel)
async def xabar_kelganda(client: Client, message: Message):
    try:
        global BOT_ID
        if BOT_ID is None:
            BOT_ID = (await bot.get_me()).id

        kanal_username = message.chat.username.lower() if message.chat.username else ""
        kanal_id = str(message.chat.id)

        # O'ziga-o'zi cheksiz yuborishni bloklash
        if kanal_username == DEST_CLEAN or kanal_id == DEST_CLEAN:
            return

        # Kanal ro'yxatda bormi?
        match_found = False
        for target in kuzatiladigan_kanallar:
            if target == kanal_username or target == kanal_id or target in kanal_username:
                match_found = True
                break

        if match_found:
            asl_matn = message.text or message.caption or ""
            tozalan_matn = matnni_tahrirlash(asl_matn)
            
            # Yashirin kod qo'shamiz, toki Oddiy Bot buni oddiy xabar emasligini bilsin
            maxsus_belgi = "🔔YANGI_XABAR_KODI🔔\n"
            yuborish_matni = f"{maxsus_belgi}{tozalan_matn}"

            # Userbot tozalangan xabarni Oddiy Botga (orqa fonda) jo'natadi
            if message.text:
                await client.send_message(chat_id=BOT_ID, text=yuborish_matni)
            elif message.media:
                await client.copy_message(chat_id=BOT_ID, from_chat_id=message.chat.id, message_id=message.id, caption=yuborish_matni)
                
    except Exception as e:
        print(f"Userbot xatosi: {e}")

# ==========================================
# 5. ODDIY BOT (Menejer) - Tasdiqlash va Boshqaruv
# ==========================================
@bot.on_message(filters.private)
async def bot_boshqaruv(client: Client, message: Message):
    text = message.text or message.caption or ""

    # A) Agar xabar Userbotdan kelgan "Yangi post" bo'lsa
    if text.startswith("🔔YANGI_XABAR_KODI🔔"):
        toza_matn = text.replace("🔔YANGI_XABAR_KODI🔔\n", "")
        
        tugmalar = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Kanalga chiqarish", callback_data="tasdiq")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="bekor")]
        ])
        
        # Bot xabarni Adminga tugmalar bilan jo'natadi
        if message.text:
            await client.send_message(chat_id=ADMIN_ID, text=toza_matn, reply_markup=tugmalar, disable_web_page_preview=True)
        elif message.media:
            await client.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.id, caption=toza_matn, reply_markup=tugmalar)
        return

    # B) Faqat Adminga ruxsat berilgan buyruqlar
    if message.from_user.id != ADMIN_ID:
        return

    if message.text.startswith("/start"):
        yozuv = (
            "🤖 **Gibrid Boshqaruv Paneliga xush kelibsiz!**\n\n"
            "Men sizning ayg'oqchi Userbotingizni boshqaraman.\n\n"
            "📋 **Buyruqlar:**\n"
            "🔹 `/kanallar` - Kuzatilayotgan kanallar ro'yxati\n"
            "🔹 `/qoshish @username` - Yangi kanal qo'shish\n"
            "🔹 `/ochirish @username` - Kanalni olib tashlash"
        )
        await message.reply_text(yozuv)

    elif message.text.startswith("/kanallar"):
        if not kuzatiladigan_kanallar:
            await message.reply_text("📂 Hozircha hech qanday kanal kuzatilmayapti.")
            return
        royxat = "📊 **Kuzatilayotgan kanallar:**\n\n"
        for i, k in enumerate(kuzatiladigan_kanallar, 1):
            royxat += f"{i}. @{k}\n"
        await message.reply_text(royxat)

    elif message.text.startswith("/qoshish"):
        try:
            yangi = message.text.split()[1].replace("https://t.me/", "").replace("@", "").lower()
            if yangi in kuzatiladigan_kanallar:
                await message.reply_text("⚠️ Bu kanal allaqachon ro'yxatda bor!")
            else:
                kuzatiladigan_kanallar.append(yangi)
                await message.reply_text(f"✅ @{yangi} ro'yxatga qo'shildi!")
        except IndexError:
            await message.reply_text("❌ Xato! Format: `/qoshish @kunuz`")

    elif message.text.startswith("/ochirish"):
        try:
            eski = message.text.split()[1].replace("https://t.me/", "").replace("@", "").lower()
            if eski in kuzatiladigan_kanallar:
                kuzatiladigan_kanallar.remove(eski)
                await message.reply_text(f"🗑 @{eski} ro'yxatdan o'chirildi!")
            else:
                await message.reply_text("⚠️ Bunday kanal topilmadi.")
        except IndexError:
            await message.reply_text("❌ Xato! Format: `/ochirish @kunuz`")

# ==========================================
# 6. TUGMALARNI QABUL QILISH (Callback)
# ==========================================
@bot.on_callback_query()
async def tugma_bosildi(client: Client, callback_query):
    # Faqat Admin bosa olishini kafolatlaymiz
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("Sizga ruxsat yo'q!", show_alert=True)
        return

    data = callback_query.data
    
    if data == "tasdiq":
        try:
            if callback_query.message.text:
                await client.send_message(DESTINATION_CHANNEL, callback_query.message.text, disable_web_page_preview=True)
            elif callback_query.message.media:
                await client.copy_message(DESTINATION_CHANNEL, callback_query.message.chat.id, callback_query.message.id, caption=callback_query.message.caption)
            
            await callback_query.edit_message_reply_markup(None)
            await callback_query.answer("✅ Muvaffaqiyatli kanalga joylandi!", show_alert=True)
        except Exception as e:
            await callback_query.answer(f"Xatolik: {e}", show_alert=True)

    elif data == "bekor":
        await callback_query.edit_message_reply_markup(None)
        await callback_query.message.reply_text("❌ Xabar rad etildi va kanalga joylanmadi.")
        await callback_query.answer("Rad etildi.")

# ==========================================
# 7. IKKALASINI BIR VAQTDA ISHGA TUSHIRISH
# ==========================================
if __name__ == "__main__":
    print("Gibrid Tizim (Userbot + Oddiy Bot) ishga tushmoqda...")
    compose([userbot, bot])