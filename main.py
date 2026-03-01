import os
import re
import asyncio
import time
import io
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, compose
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, InputMediaVideo

# Watermark uchun kutubxona (requirements.txt ga Pillow qo'shilishi kerak)
try:
    from PIL import Image, ImageDraw, ImageFont
    WATERMARK_ENABLED = True
except ImportError:
    WATERMARK_ENABLED = False
    print("Ogohlantirish: Pillow kutubxonasi o'rnatilmagan. Watermark ishlamaydi.")

# ==========================================
# Asyncio xatoligini oldini olish
# ==========================================
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ==========================================
# 1. SOZLAMALAR VA KALITLAR
# ==========================================
required_keys = ["API_ID", "API_HASH", "SESSION_STRING", "BOT_TOKEN", "ADMIN_ID"]
missing_keys = [key for key in required_keys if not os.environ.get(key) or not str(os.environ.get(key)).strip()]

if missing_keys:
    print(f"❌ XATOLIK: Renderda quyidagi kalitlar yo'q: {', '.join(missing_keys)}")
    exit()

API_ID = int(os.environ.get("API_ID").strip())
API_HASH = os.environ.get("API_HASH").strip()
SESSION_STRING = os.environ.get("SESSION_STRING").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID").strip())

QIDIRUV_ANDOZASI = r'@[A-Za-z0-9_]+|https?://[^\s]+|t\.me/[^\s]+'

# Xotira ma'lumotlari (Database o'rnida)
xotira = {
    "manba_kanallar": [], # Qayerdan o'g'irlaymiz
    "asosiy_kanallar": [], # Asosiy kanalimiz
    "privat_kanallar": [], # Yopiq/Zaxira kanalimiz
    "avto_imzo": "\n\n👉 @BiziKanalgaObunaBuling", # Default imzo
    "suv_belgisi": "@BiziKanal", # Rasmga tushadigan yozuv
    "statistika": {"ushlandi": 0, "tasdiqlandi": 0, "bekor": 0}
}

# Albomlarni yig'ish va tasdiqlash kutish xonasi
media_kombayn = {}
kutayotgan_xabarlar = {}
xabar_id_counter = 1
admin_holati = {}

# Dastlabki sozlamalarni yuklash
def init_channels():
    raw_src = os.environ.get("SOURCE_CHATS", "")
    for c in raw_src.split(","):
        c = c.strip().replace("https://t.me/", "").replace("@", "").lower()
        if c: xotira["manba_kanallar"].append(c)
        
    raw_dest = os.environ.get("DESTINATION_CHANNEL", "")
    dest = raw_dest.strip().replace("https://t.me/", "").replace("@", "").lower()
    if dest: xotira["asosiy_kanallar"].append(dest)

init_channels()

# ==========================================
# 2. WEB SERVER
# ==========================================
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Media-Kombayn va Gibrid Tizim 24/7 faol!"
Thread(target=lambda: app_web.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()

# ==========================================
# 3. KLIENTLARNI YARATISH
# ==========================================
BOT_ID = None
userbot = Client("aygoqchi", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("boshqaruvchi", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def matnni_tahrirlash(matn: str) -> str:
    if not matn: return ""
    toza = re.sub(QIDIRUV_ANDOZASI, "", matn) # Manba havolalarini o'chiramiz
    return toza + xotira["avto_imzo"] # Avto-imzoni qo'shamiz

# Rasmga Watermark qo'shish funksiyasi
async def add_watermark(client, message: Message):
    if not WATERMARK_ENABLED or not message.photo:
        return None
    try:
        photo_path = await client.download_media(message, in_memory=True)
        img = Image.open(photo_path)
        draw = ImageDraw.Draw(img)
        # Oddiy shrift va o'lcham
        text = xotira["suv_belgisi"]
        width, height = img.size
        
        # O'ng burchak pastga yozamiz
        position = (width - (len(text) * 12), height - 40)
        # Qora fonli oq yozuv (o'qilishi oson bo'lishi uchun)
        draw.text(position, text, fill=(255, 255, 255))
        
        out = io.BytesIO()
        img.save(out, format="JPEG")
        out.name = "watermarked.jpg"
        return out
    except Exception as e:
        print(f"Watermark xatosi: {e}")
        return None

# ==========================================
# 4. USERBOT - MEDIA KOMBAYN VA OVCHI
# ==========================================
@userbot.on_message(filters.channel)
async def xabar_kelganda(client: Client, message: Message):
    try:
        global BOT_ID
        if BOT_ID is None: BOT_ID = (await bot.get_me()).id

        kanal_username = message.chat.username.lower() if message.chat.username else ""
        kanal_id = str(message.chat.id)

        # O'zimizning kanallardan kelganini inkor qilamiz
        barcha_bizning_kanallar = xotira["asosiy_kanallar"] + xotira["privat_kanallar"]
        if kanal_username in barcha_bizning_kanallar or kanal_id in barcha_bizning_kanallar:
            return

        match_found = any(t == kanal_username or t == kanal_id or t in kanal_username for t in xotira["manba_kanallar"])

        if match_found:
            xotira["statistika"]["ushlandi"] += 1
            
            # --- ALBOM (MEDIA KOMBAYN) MANTIQI ---
            if message.media_group_id:
                mg_id = message.media_group_id
                if mg_id not in media_kombayn:
                    media_kombayn[mg_id] = []
                    # 3 soniya kutamiz, barcha rasmlar yetib kelguncha
                    asyncio.create_task(process_media_group(client, mg_id, message.chat.title))
                media_kombayn[mg_id].append(message)
                return

            # --- YAKKA XABAR MANTIQI ---
            global xabar_id_counter
            curr_id = str(xabar_id_counter)
            xabar_id_counter += 1
            
            asl_matn = message.text or message.caption or ""
            toz_matn = matnni_tahrirlash(asl_matn)

            kutayotgan_xabarlar[curr_id] = {
                "type": "single",
                "message": message,
                "caption": toz_matn
            }
            
            # Adminga namunani yuboramiz
            if message.text:
                await bot.send_message(ADMIN_ID, toz_matn, disable_web_page_preview=True)
            elif message.media:
                await userbot.copy_message(ADMIN_ID, message.chat.id, message.id, caption=toz_matn)
            
            # Boshqaruv tugmalari
            tugmalar = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Asosiyga", callback_data=f"yubor_asosiy_{curr_id}"),
                 InlineKeyboardButton("🔒 Privatga", callback_data=f"yubor_privat_{curr_id}")],
                [InlineKeyboardButton("🚀 Ikkalasiga", callback_data=f"yubor_ikkala_{curr_id}")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"bekor_{curr_id}")]
            ])
            await bot.send_message(ADMIN_ID, f"👆 **YANGI POST!**\nManba: {message.chat.title}\nQayerga joylaymiz?", reply_markup=tugmalar)

    except Exception as e:
        print(f"Userbot xatosi: {e}")

# Albomlarni qayta ishlash funksiyasi
async def process_media_group(client: Client, mg_id: str, chat_title: str):
    await asyncio.sleep(3) # Qolgan qismlar kelishini kutamiz
    messages = media_kombayn.pop(mg_id, [])
    if not messages: return

    # Xabarlarni id bo'yicha tartiblaymiz
    messages.sort(key=lambda x: x.id)
    
    global xabar_id_counter
    curr_id = str(xabar_id_counter)
    xabar_id_counter += 1
    
    # Faqat birinchi rasmning tagiga matn yoziladi
    asl_matn = messages[0].caption or ""
    toz_matn = matnni_tahrirlash(asl_matn)

    kutayotgan_xabarlar[curr_id] = {
        "type": "album",
        "messages": messages,
        "caption": toz_matn
    }
    
    # Adminga albomni yuboramiz
    media_list = []
    for i, msg in enumerate(messages):
        cap = toz_matn if i == 0 else ""
        if msg.photo:
            media_list.append(InputMediaPhoto(msg.photo.file_id, caption=cap))
        elif msg.video:
            media_list.append(InputMediaVideo(msg.video.file_id, caption=cap))
            
    await bot.send_media_group(ADMIN_ID, media_list)
    
    tugmalar = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Asosiyga", callback_data=f"yubor_asosiy_{curr_id}"),
         InlineKeyboardButton("🔒 Privatga", callback_data=f"yubor_privat_{curr_id}")],
        [InlineKeyboardButton("🚀 Ikkalasiga", callback_data=f"yubor_ikkala_{curr_id}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"bekor_{curr_id}")]
    ])
    await bot.send_message(ADMIN_ID, f"👆 **YANGI ALBOM ({len(messages)} ta media)!**\nManba: {chat_title}\nQayerga joylaymiz?", reply_markup=tugmalar)


# ==========================================
# 5. KENGAYTIRILGAN ADMIN PANEL
# ==========================================
def bosh_menyu_tugmalari():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistika", callback_data="menyu_stat")],
        [InlineKeyboardButton("📡 Manba (Qayerdan olamiz)", callback_data="menyu_manba")],
        [InlineKeyboardButton("📢 Asosiy Kanal", callback_data="menyu_asosiy_kanal"),
         InlineKeyboardButton("🔒 Privat Kanal", callback_data="menyu_privat_kanal")],
        [InlineKeyboardButton("✍️ Avto-Imzo va Watermark", callback_data="menyu_imzo")]
    ])

@bot.on_message(filters.private)
async def bot_boshqaruv(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text or ""

    if text == "/start":
        admin_holati[ADMIN_ID] = None
        user = message.from_user
        info_text = (
            f"👋 Salom, **{user.first_name}**!\n\n"
            "🎛 **Gibrid Boshqaruv Markazi v3.0**\n"
            "Botni sozlash uchun quyidagi menyudan foydalaning:"
        )
        await message.reply_text(info_text, reply_markup=bosh_menyu_tugmalari())
        return

    # Holatlar bo'yicha matn kutish
    holat = admin_holati.get(ADMIN_ID)
    if holat:
        if holat.startswith("qoshish_"):
            kategoriya = holat.split("_")[1]
            yangi = text.strip().replace("https://t.me/", "").replace("@", "").lower()
            if not yangi: return await message.reply_text("Noto'g'ri format.")
            
            xotira[kategoriya].append(yangi)
            await message.reply_text(f"✅ @{yangi} qo'shildi!", reply_markup=bosh_menyu_tugmalari())
            admin_holati[ADMIN_ID] = None

        elif holat == "imzo_kutmoqda":
            xotira["avto_imzo"] = f"\n\n{text}"
            await message.reply_text("✅ Avto-imzo saqlandi!", reply_markup=bosh_menyu_tugmalari())
            admin_holati[ADMIN_ID] = None
            
        elif holat == "watermark_kutmoqda":
            xotira["suv_belgisi"] = text.strip()
            await message.reply_text("✅ Watermark matni saqlandi!", reply_markup=bosh_menyu_tugmalari())
            admin_holati[ADMIN_ID] = None


# ==========================================
# 6. TUGMALAR (CALLBACKS)
# ==========================================
@bot.on_callback_query()
async def tugmalar_boshqaruvi(client: Client, cq: CallbackQuery):
    if cq.from_user.id != ADMIN_ID: return await cq.answer("Ruxsat yo'q!", show_alert=True)
    
    data = cq.data

    # Xabarlarni yuborish mantiqi
    if data.startswith("yubor_") or data.startswith("bekor_"):
        amal, target, qism, msg_id = "", "", "", ""
        if data.startswith("bekor_"):
            msg_id = data.split("_")[1]
            amal = "bekor"
        else:
            _, target, msg_id = data.split("_")
            amal = "yubor"

        if msg_id not in kutayotgan_xabarlar:
            return await cq.answer("⚠️ Bu xabar eskirgan yoki topilmadi.", show_alert=True)

        xabar_data = kutayotgan_xabarlar[msg_id]
        
        if amal == "bekor":
            xotira["statistika"]["bekor"] += 1
            await cq.edit_message_text("❌ Xabar bekor qilindi.")
            del kutayotgan_xabarlar[msg_id]
            return

        # Qaysi kanallarga yuboramiz?
        target_list = []
        if target in ["asosiy", "ikkala"]: target_list.extend(xotira["asosiy_kanallar"])
        if target in ["privat", "ikkala"]: target_list.extend(xotira["privat_kanallar"])

        if not target_list:
            return await cq.answer("⚠️ O'sha yo'nalish bo'yicha kanal qo'shilmagan!", show_alert=True)

        # Yuborish jarayoni
        await cq.edit_message_text("⏳ Yuborilmoqda...")
        xotira["statistika"]["tasdiqlandi"] += 1

        for kanal in target_list:
            try:
                if xabar_data["type"] == "single":
                    msg = xabar_data["message"]
                    cap = xabar_data["caption"]
                    
                    # Watermark qo'shish (faqat rasm bo'lsa)
                    wm_photo = await add_watermark(userbot, msg) if WATERMARK_ENABLED and msg.photo else None
                    
                    if wm_photo:
                        await userbot.send_photo(kanal, wm_photo, caption=cap)
                    elif msg.text:
                        await userbot.send_message(kanal, cap, disable_web_page_preview=True)
                    else:
                        await userbot.copy_message(kanal, msg.chat.id, msg.id, caption=cap)
                        
                elif xabar_data["type"] == "album":
                    messages = xabar_data["messages"]
                    media_list = []
                    for i, msg in enumerate(messages):
                        cap = xabar_data["caption"] if i == 0 else ""
                        if msg.photo: media_list.append(InputMediaPhoto(msg.photo.file_id, caption=cap))
                        elif msg.video: media_list.append(InputMediaVideo(msg.video.file_id, caption=cap))
                    await userbot.send_media_group(kanal, media_list)
            except Exception as e:
                print(f"Yuborishda xato: {e}")

        await cq.edit_message_text(f"✅ Muvaffaqiyatli joylandi! ({target.capitalize()})")
        del kutayotgan_xabarlar[msg_id]
        return

    # Menyu navigatsiyasi
    elif data == "menyu_asosiy":
        admin_holati[ADMIN_ID] = None
        await cq.message.edit_text("🎛 **Boshqaruv Markazi:**", reply_markup=bosh_menyu_tugmalari())

    elif data == "menyu_stat":
        stat = xotira["statistika"]
        matn = (
            "📊 **BOT STATISTIKASI**\n\n"
            f"📡 Tutilgan jami xabarlar: **{stat['ushlandi']}** ta\n"
            f"✅ Kanalga chiqarildi: **{stat['tasdiqlandi']}** ta\n"
            f"❌ Bekor qilindi (Axlat): **{stat['bekor']}** ta"
        )
        ortga = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ortga", callback_data="menyu_asosiy")]])
        await cq.message.edit_text(matn, reply_markup=ortga)

    elif data in ["menyu_manba", "menyu_asosiy_kanal", "menyu_privat_kanal"]:
        kat_dict = {"menyu_manba": "manba_kanallar", "menyu_asosiy_kanal": "asosiy_kanallar", "menyu_privat_kanal": "privat_kanallar"}
        kat_nomi = kat_dict[data]
        
        matn = f"📂 **{kat_nomi.replace('_', ' ').capitalize()} ro'yxati:**\n\n"
        kanallar = xotira[kat_nomi]
        if not kanallar: matn += "Hozircha bo'sh."
        else: matn += "\n".join([f"• @{k}" for k in kanallar])
        
        tugmalar = [
            [InlineKeyboardButton("➕ Kanal qo'shish", callback_data=f"add_{kat_nomi}")],
            [InlineKeyboardButton("➖ O'chirish", callback_data=f"rem_{kat_nomi}")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="menyu_asosiy")]
        ]
        await cq.message.edit_text(matn, reply_markup=InlineKeyboardMarkup(tugmalar))

    elif data.startswith("add_"):
        kategoriya = data.replace("add_", "")
        admin_holati[ADMIN_ID] = f"qoshish_{kategoriya}"
        await cq.message.edit_text("✍️ Iltimos, kanalning `@username` ini yuboring:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor qilish", callback_data=f"menyu_{kategoriya.replace('kanallar', 'kanal')}")]]))

    elif data.startswith("rem_"):
        kategoriya = data.replace("rem_", "")
        kanallar = xotira[kategoriya]
        if not kanallar: return await cq.answer("O'chirish uchun kanal yo'q!", show_alert=True)
        
        tugmalar = [[InlineKeyboardButton(f"🗑 @{k}", callback_data=f"del_{kategoriya}_{k}")] for k in kanallar]
        tugmalar.append([InlineKeyboardButton("🔙 Ortga", callback_data=f"menyu_{kategoriya.replace('kanallar', 'kanal')}")])
        await cq.message.edit_text("O'chirish uchun kanalni tanlang:", reply_markup=InlineKeyboardMarkup(tugmalar))

    elif data.startswith("del_"):
        _, kategoriya, kanal = data.split("_", 2)
        if kanal in xotira[kategoriya]:
            xotira[kategoriya].remove(kanal)
            await cq.answer(f"@{kanal} o'chirildi!", show_alert=True)
        await cq.message.edit_text(f"✅ @{kanal} o'chirildi.", reply_markup=bosh_menyu_tugmalari())

    elif data == "menyu_imzo":
        matn = (
            f"✍️ **Joriy Avto-imzo:**\n`{xotira['avto_imzo']}`\n\n"
            f"🖼 **Joriy Watermark (Rasmga):**\n`{xotira['suv_belgisi']}`"
        )
        tugmalar = [
            [InlineKeyboardButton("📝 Imzoni o'zgartirish", callback_data="set_imzo")],
            [InlineKeyboardButton("🎨 Watermarkni o'zgartirish", callback_data="set_watermark")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="menyu_asosiy")]
        ]
        await cq.message.edit_text(matn, reply_markup=InlineKeyboardMarkup(tugmalar))

    elif data == "set_imzo":
        admin_holati[ADMIN_ID] = "imzo_kutmoqda"
        await cq.message.edit_text("Yangi Avto-imzoni matn ko'rinishida yuboring:\n*(Masalan: 👉 Bizi kanalga o'ting)*")
        
    elif data == "set_watermark":
        admin_holati[ADMIN_ID] = "watermark_kutmoqda"
        await cq.message.edit_text("Rasmga tushadigan qisqacha Watermark matnini yuboring:\n*(Masalan: @MeningKanalim)*")

# ==========================================
# 7. ISHGA TUSHIRISH
# ==========================================
if __name__ == "__main__":
    print("Mukammal Media-Kombayn Tizimi ishga tushmoqda...")
    compose([userbot, bot])