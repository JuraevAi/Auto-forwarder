import os
import re
import asyncio
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, compose
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ==========================================
# Asyncio xatoligini oldini olish
# ==========================================
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ==========================================
# 1. SOZLAMALAR VA XATOLIKLARNI ANIQLASH (YANGILANGAN)
# ==========================================
required_keys = ["API_ID", "API_HASH", "SESSION_STRING", "BOT_TOKEN", "ADMIN_ID"]
missing_keys = [key for key in required_keys if not os.environ.get(key) or not str(os.environ.get(key)).strip()]

if missing_keys:
    print("\n" + "="*50)
    print("❌ XATOLIK: Render sozlamalarida quyidagi kalitlar topilmadi:")
    for mk in missing_keys:
        print(f"   👉 {mk}")
    print("Iltimos, Renderdagi 'Environment' bo'limiga kirib ularni to'g'rilang!")
    print("="*50 + "\n")
    exit()

try:
    API_ID = int(os.environ.get("API_ID").strip())
except ValueError:
    print("XATOLIK: API_ID faqat raqamlardan iborat bo'lishi kerak!")
    exit()

API_HASH = os.environ.get("API_HASH").strip()
SESSION_STRING = os.environ.get("SESSION_STRING").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID").strip())

DESTINATION_CHANNEL = os.environ.get("DESTINATION_CHANNEL", "").strip()
REPLACEMENT_TEXT = os.environ.get("REPLACEMENT_TEXT", DESTINATION_CHANNEL)
DEST_CLEAN = DESTINATION_CHANNEL.replace("https://t.me/", "").replace("@", "").lower()

QIDIRUV_ANDOZASI = r'@[A-Za-z0-9_]+|https?://[^\s]+|t\.me/[^\s]+'

kuzatiladigan_kanallar = []
admin_holati = {}

def init_channels():
    raw = os.environ.get("SOURCE_CHATS", "")
    for c in raw.split(","):
        c = c.strip().replace("https://t.me/", "").replace("@", "").lower()
        if c and c not in kuzatiladigan_kanallar:
            kuzatiladigan_kanallar.append(c)

init_channels()

# ==========================================
# 2. WEB SERVER
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Tugmali Gibrid Tizim 24/7 faol ishlamoqda!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

Thread(target=run_server, daemon=True).start()

# ==========================================
# 3. KLIENTLARNI YARATISH
# ==========================================
BOT_ID = None
userbot = Client("aygoqchi", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("boshqaruvchi", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def matnni_tahrirlash(matn: str) -> str:
    if not matn: return ""
    return re.sub(QIDIRUV_ANDOZASI, REPLACEMENT_TEXT, matn)

# ==========================================
# 4. USERBOT (Ayg'oqchi)
# ==========================================
@userbot.on_message(filters.channel)
async def xabar_kelganda(client: Client, message: Message):
    try:
        global BOT_ID
        if BOT_ID is None:
            BOT_ID = (await bot.get_me()).id

        kanal_username = message.chat.username.lower() if message.chat.username else ""
        kanal_id = str(message.chat.id)

        if kanal_username == DEST_CLEAN or kanal_id == DEST_CLEAN:
            return

        match_found = any(t == kanal_username or t == kanal_id or t in kanal_username for t in kuzatiladigan_kanallar)

        if match_found:
            asl_matn = message.text or message.caption or ""
            toz_matn = matnni_tahrirlash(asl_matn)
            yuborish_matni = f"🔔YANGI_XABAR_KODI🔔\n{toz_matn}"

            if message.text:
                await client.send_message(chat_id=BOT_ID, text=yuborish_matni)
            elif message.media:
                await client.copy_message(chat_id=BOT_ID, from_chat_id=message.chat.id, message_id=message.id, caption=yuborish_matni)
                
    except Exception as e:
        print(f"Userbot xatosi: {e}")

# ==========================================
# 5. ADMIN PANEL VA FOYDALANUVCHI MA'LUMOTLARI
# ==========================================
def bosh_menyu_tugmalari():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Kuzatilayotgan kanallar", callback_data="menyu_royxat")],
        [
            InlineKeyboardButton("➕ Kanal qo'shish", callback_data="menyu_qoshish"),
            InlineKeyboardButton("➖ O'chirish", callback_data="menyu_ochirish")
        ]
    ])

@bot.on_message(filters.private)
async def xabarlarni_qabul_qilish(client: Client, message: Message):
    text = message.text or message.caption or ""

    # A) Userbotdan kelgan xabarlarni tasdiqlash uchun
    if text.startswith("🔔YANGI_XABAR_KODI🔔"):
        if message.from_user.id != ADMIN_ID: return
        toza_matn = text.replace("🔔YANGI_XABAR_KODI🔔\n", "")
        tugmalar = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Kanalga chiqarish", callback_data="tasdiq")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="bekor")]
        ])
        
        if message.text:
            await client.send_message(ADMIN_ID, toza_matn, reply_markup=tugmalar, disable_web_page_preview=True)
        elif message.media:
            await client.copy_message(ADMIN_ID, message.chat.id, message.id, caption=toza_matn, reply_markup=tugmalar)
        return

    # B) /start bosilganda foydalanuvchi ma'lumotlarini (3 ta ustunlik) chiqarish
    if text == "/start":
        user = message.from_user
        uid = user.id
        name = user.first_name
        if user.last_name: name += f" {user.last_name}"
        uname = f"@{user.username}" if user.username else "Mavjud emas"

        # Chiroyli 3 qatorlik ustun format (Barcha uchun ochiq)
        info_text = (
            "👤 **FOYDALANUVCHI MA'LUMOTLARI**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 **ID Raqam:** `{uid}`\n"
            f"🪪 **Ism-Familiya:** {name}\n"
            f"🔗 **Username:** {uname}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        # Agar bu shaxs ADMIN bo'lsa, ma'lumot tagidan Boshqaruv panelini ham qo'shib beramiz
        if uid == ADMIN_ID:
            admin_holati[ADMIN_ID] = None 
            info_text += "\n🎛 **Asosiy Boshqaruv Paneli:**\nBotni boshqarish uchun quyidagi tugmalardan foydalaning."
            await message.reply_text(info_text, reply_markup=bosh_menyu_tugmalari())
        else:
            # Agar oddiy odam bo'lsa, faqatgina ma'lumotini tashlaydi va o'zini yaxshi bot qilib ko'rsatadi
            info_text += "\n👋 Xush kelibsiz! Men yopiq tizimda ishlovchi yordamchi botman."
            await message.reply_text(info_text)
        return

    # D) Faqat Adminga ruxsat berilgan qo'shish jarayoni
    if message.from_user.id == ADMIN_ID and admin_holati.get(ADMIN_ID) == "kanal_kutmoqda":
        yangi = text.strip().replace("https://t.me/", "").replace("@", "").lower()
        if not yangi:
            await message.reply_text("Iltimos, to'g'ri kanal nomini yuboring.")
            return
            
        if yangi in kuzatiladigan_kanallar:
            await message.reply_text(f"⚠️ **@{yangi}** allaqachon ro'yxatda bor!", reply_markup=bosh_menyu_tugmalari())
        else:
            kuzatiladigan_kanallar.append(yangi)
            await message.reply_text(f"✅ **@{yangi}** muvaffaqiyatli qo'shildi!", reply_markup=bosh_menyu_tugmalari())
        
        admin_holati[ADMIN_ID] = None

# ==========================================
# 6. TUGMALAR BOSILGANDA (Callback)
# ==========================================
@bot.on_callback_query()
async def tugma_bosildi(client: Client, cq: CallbackQuery):
    if cq.from_user.id != ADMIN_ID:
        await cq.answer("Sizga ruxsat yo'q!", show_alert=True)
        return

    data = cq.data

    if data == "tasdiq":
        try:
            if cq.message.text:
                await client.send_message(DESTINATION_CHANNEL, cq.message.text, disable_web_page_preview=True)
            elif cq.message.media:
                await client.copy_message(DESTINATION_CHANNEL, cq.message.chat.id, cq.message.id, caption=cq.message.caption)
            await cq.edit_message_reply_markup(None)
            await cq.answer("Xabar kanalingizga joylandi! ✅", show_alert=True)
        except Exception as e:
            await cq.answer(f"Xatolik: {e}", show_alert=True)
    
    elif data == "bekor":
        await cq.edit_message_reply_markup(None)
        await cq.message.reply_text("❌ Xabar rad etildi.")
        await cq.answer("Rad etildi.")

    elif data == "menyu_asosiy":
        admin_holati[ADMIN_ID] = None
        await cq.message.edit_text("🎛 **Asosiy Boshqaruv Paneli:**", reply_markup=bosh_menyu_tugmalari())

    elif data == "menyu_royxat":
        admin_holati[ADMIN_ID] = None
        if not kuzatiladigan_kanallar:
            matn = "📂 Hozircha hech qanday kanal kuzatilmayapti."
        else:
            matn = "📊 **Kuzatilayotgan kanallar:**\n\n" + "\n".join([f"{i+1}. @{k}" for i, k in enumerate(kuzatiladigan_kanallar)])
        ortga = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ortga", callback_data="menyu_asosiy")]])
        await cq.message.edit_text(matn, reply_markup=ortga)

    elif data == "menyu_qoshish":
        admin_holati[ADMIN_ID] = "kanal_kutmoqda"
        ortga = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor qilish", callback_data="menyu_asosiy")]])
        await cq.message.edit_text("✍️ **Kanal qo'shish:**\n\nIltimos, qo'shmoqchi bo'lgan kanalingizning `@username` ni yoki havolasini yuboring.", reply_markup=ortga)

    elif data == "menyu_ochirish":
        admin_holati[ADMIN_ID] = None
        if not kuzatiladigan_kanallar:
            await cq.answer("O'chirish uchun kanallar yo'q!", show_alert=True)
            return
            
        tugmalar = [[InlineKeyboardButton(f"🗑 @{k} ni o'chirish", callback_data=f"del_{k}")] for k in kuzatiladigan_kanallar]
        tugmalar.append([InlineKeyboardButton("🔙 Ortga", callback_data="menyu_asosiy")])
        
        await cq.message.edit_text("Keraksiz kanalni tanlang:", reply_markup=InlineKeyboardMarkup(tugmalar))

    elif data.startswith("del_"):
        kanal_nomi = data.replace("del_", "")
        if kanal_nomi in kuzatiladigan_kanallar:
            kuzatiladigan_kanallar.remove(kanal_nomi)
            await cq.answer(f"@{kanal_nomi} o'chirildi! ✅", show_alert=True)
        await cq.message.edit_text(f"✅ **@{kanal_nomi}** ro'yxatdan olib tashlandi.", reply_markup=bosh_menyu_tugmalari())

# ==========================================
# 7. ISHGA TUSHIRISH
# ==========================================
if __name__ == "__main__":
    print("Gibrid Tizim ishga tushmoqda...")
    compose([userbot, bot])