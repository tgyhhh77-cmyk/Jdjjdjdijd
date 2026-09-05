import os
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from aiogram.enums import ParseMode

from config import BOT_TOKEN, ADMIN_IDS, UPLOAD_FOLDER, RESULTS_FOLDER
from database import Database
from searcher import LargeTextSearcher

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

def get_user_folder(user_id: int) -> str:
    folder = os.path.join(UPLOAD_FOLDER, str(user_id))
    os.makedirs(folder, exist_ok=True)
    return folder

# ==================== أمر /start ====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    db.add_or_update_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    db.add_log(user.id, "start", "User started bot")

    welcome_text = (
        f"👋 أهلاً وسهلاً {user.first_name}!\n\n"
        f"🤖 أنا بوت البحث المتقدم في الملفات النصية الكبيرة.\n\n"
        f"📋 الأوامر المتاحة:\n"
        f"/upload - طلب رفع ملف .txt\n"
        f"/search (نص) - البحث في ملفاتك\n"
        f"/myfiles - عرض ملفاتك المرفوعة\n"
        f"/status - إحصائيات حسابك\n"
        f"/help - المساعدة\n"
        f"/addfile - رفع ملف موجود على السيرفر\n\n"
        f"📎 طريقة الاستخدام:\n"
        f"1. أرسل لي ملف .txt مباشرة أو استخدم /upload\n"
        f"2. استخدم /search متبوعاً بالنص المطلوب\n"
        f"3. سأرسل لك النتائج فوراً!"
    )
    await message.reply(welcome_text)

# ==================== أمر /help ====================
@dp.message(Command("help"))
async def cmd_help(message: Message):
    db.increment_message_count(message.from_user.id)
    help_text = (
        "📖 دليل الاستخدام\n\n"
        "📤 رفع ملف:\n"
        "• أرسل ملف .txt مباشرة في المحادثة\n"
        "• أو اضغط /upload\n\n"
        "🔍 البحث:\n"
        "• /search النص_المطلوب\n"
        "• مثال: /search محمد أحمد\n\n"
        "📂 إدارة الملفات:\n"
        "• /myfiles - قائمة ملفاتك\n"
        "• /status - إحصائياتك الشخصية\n\n"
        "👨‍💼 للمشرفين:\n"
        "• /stats - إحصائيات البوت الكاملة\n"
        "• /addfile /path/to/file.txt - رفع ملف من السيرفر"
    )
    await message.reply(help_text)

# ==================== أمر /upload ====================
@dp.message(Command("upload"))
async def cmd_upload(message: Message):
    db.increment_message_count(message.from_user.id)
    await message.reply(
        "📤 جاهز لاستقبال ملفك!\n\n"
        "أرسل لي ملف نصي بصيغة .txt\n"
        "✅ يمكن أن يكون الملف ضخماً — أنا أتعامل معه بكفاءة عالية!"
    )

# ==================== رفع الملفات ====================
@dp.message(F.document)
async def handle_document(message: Message):
    user = message.from_user
    db.increment_message_count(user.id)

    if not message.document.file_name.endswith('.txt'):
        await message.reply("❌ أقبل فقط ملفات .txt")
        db.add_log(user.id, "upload_rejected", f"Wrong format: {message.document.file_name}")
        return

    max_size = 20 * 1024 * 1024
    if message.document.file_size > max_size:
        await message.reply(
            f"❌ الملف كبير جداً! الحد الأقصى هو 20 ميجابايت.\n"
            f"📦 حجم ملفك: {message.document.file_size / (1024*1024):.2f} MB"
        )
        db.add_log(user.id, "upload_rejected", f"File too large: {message.document.file_size}")
        return

    user_folder = get_user_folder(user.id)
    file_path = os.path.join(user_folder, message.document.file_name)

    if os.path.exists(file_path):
        os.remove(file_path)
        db.delete_user_file(user.id, message.document.file_name)

    msg = await message.reply("⏳ جاري تحميل الملف...")

    try:
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, file_path)
        file_size = os.path.getsize(file_path)

        db.add_file(user.id, message.document.file_name, file_path, file_size)
        db.add_log(user.id, "upload_success", f"File: {message.document.file_name}, Size: {file_size}")

        size_mb = file_size / (1024 * 1024)
        await msg.edit_text(
            f"✅ تم رفع الملف بنجاح!\n\n"
            f"📄 الاسم: {message.document.file_name}\n"
            f"📦 الحجم: {size_mb:.2f} MB\n\n"
            f"🔍 يمكنك البحث الآن باستخدام:\n"
            f"/search النص_المطلوب"
        )
    except Exception as e:
        logging.error(f"Upload error for user {user.id}: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء تحميل الملف. حاول مرة أخرى.")
        db.add_log(user.id, "upload_error", str(e))

# ==================== أمر /addfile ====================
@dp.message(Command("addfile"))
async def cmd_addfile(message: Message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.reply("⛔ هذا الأمر للمشرفين فقط.")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "❌ استخدم الأمر بهذه الصيغة:\n"
            "/addfile /path/to/file.txt\n\n"
            "مثال: /addfile /home/ec2-user/bot/uploads/ulp.txt"
        )
        return
    
    file_path = args[1].strip()
    
    if not os.path.exists(file_path):
        await message.reply(f"❌ الملف غير موجود: {file_path}")
        return
    
    if not file_path.endswith('.txt'):
        await message.reply("❌ الملف يجب أن يكون بصيغة .txt")
        return
    
    try:
        file_name = os.path.basename(file_path)
        user_folder = get_user_folder(user_id)
        dest_path = os.path.join(user_folder, file_name)
        
        import shutil
        shutil.copy2(file_path, dest_path)
        
        file_size = os.path.getsize(dest_path)
        
        if file_size == 0:
            await message.reply("❌ الملف فارغ (0 بايت)! تأكد من الملف الصحيح.")
            os.remove(dest_path)
            return
        
        db.delete_user_file(user_id, file_name)
        db.add_file(user_id, file_name, dest_path, file_size)
        
        await message.reply(
            f"✅ تم رفع الملف بنجاح!\n"
            f"📄 الاسم: {file_name}\n"
            f"📦 الحجم: {file_size/(1024**2):.2f} MB"
        )
        
    except Exception as e:
        await message.reply(f"❌ خطأ: {str(e)[:200]}")

# ==================== أمر /search ====================
@dp.message(Command("search"))
async def cmd_search(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "❌ استخدام خاطئ\n\n"
            "الصيغة الصحيحة:\n"
            "/search النص_المطلوب\n\n"
            "مثال:\n/search مرحبا بالعالم"
        )
        return

    query = args[1].strip()
    if len(query) < 2:
        await message.reply("❌ نص البحث قصير جداً. أدخل حرفين على الأقل.")
        return

    user_folder = get_user_folder(user_id)
    if not os.path.exists(user_folder) or not os.listdir(user_folder):
        await message.reply("❌ ليس لديك ملفات مرفوعة. أرسل ملفاً أولاً.")
        return

    msg = await message.reply(f"🔍 جاري البحث عن: {query}...")

    try:
        searcher = LargeTextSearcher(user_folder)
        results, time_taken, total_data_processed, total_results = await searcher.async_query_files(query)

        db.add_search(user_id, query, total_results, time_taken, total_data_processed)
        db.add_log(user_id, "search", f"Query: {query}, Results: {total_results}")

        if total_results == 0:
            await msg.edit_text(
                f"😕 لم أجد نتائج\n\n"
                f"⏱️ الوقت: {time_taken:.4f} ثانية\n"
                f"📦 البيانات المُعالجة: {total_data_processed / (1024**2):.2f} MB"
            )
            return

        if total_results > 50:
            safe_query = "".join(c for c in query if c.isalnum() or c in (' ', '-', '_')).rstrip()[:30]
            result_file = os.path.join(RESULTS_FOLDER, f"user_{user_id}_{safe_query}.txt")
            with open(result_file, 'w', encoding='utf-8') as f:
                f.write(f"بحث عن: {query}\n")
                f.write(f"الوقت: {time_taken:.4f} ثانية\n")
                f.write(f"عدد النتائج: {total_results}\n")
                f.write("-" * 50 + "\n\n")
                for i, line in enumerate(results, 1):
                    f.write(f"{i}. {line}\n")

            await msg.edit_text(
                f"✅ تم العثور على {total_results} نتيجة\n\n"
                f"⏱️ الوقت: {time_taken:.4f} ثانية\n"
                f"📦 البيانات: {total_data_processed / (1024**2):.2f} MB\n"
                f"📄 النتائج كثيرة، أرسلها لك في ملف..."
            )
            await message.reply_document(FSInputFile(result_file), caption=f"🔍 نتائج البحث: {query}")
        else:
            text_results = "\n".join([f"• {r[:200]}" for r in results[:30]])
            if len(text_results) > 3500:
                text_results = text_results[:3500] + "\n\n... (تم اقتصاص الباقي)"

            await msg.edit_text(
                f"✅ تم العثور على {total_results} نتيجة\n\n"
                f"⏱️ الوقت: {time_taken:.4f} ثانية\n"
                f"📦 البيانات: {total_data_processed / (1024**2):.2f} MB\n\n"
                f"📝 النتائج:\n{text_results}"
            )

    except Exception as e:
        logging.error(f"Search error for user {user_id}: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء البحث. حاول مرة أخرى.")
        db.add_log(user_id, "search_error", str(e))

# ==================== أمر /myfiles ====================
@dp.message(Command("myfiles"))
async def cmd_myfiles(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    files = db.get_user_files(user_id)
    if not files:
        await message.reply("📂 ليس لديك ملفات مرفوعة.")
        return

    text = "📂 ملفاتك المرفوعة:\n\n"
    total_size = 0
    for i, f in enumerate(files, 1):
        size_mb = f['file_size'] / (1024 * 1024)
        total_size += f['file_size']
        text += f"{i}. {f['filename']} ({size_mb:.2f} MB)\n"

    text += f"\n📊 الإجمالي: {len(files)} ملف | {total_size / (1024**2):.2f} MB"
    await message.reply(text)

# ==================== أمر /status ====================
@dp.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    stats = db.get_user_stats(user_id)
    if not stats:
        await message.reply("❌ لم أجد بياناتك.")
        return

    text = (
        f"👤 حالة حسابك\n\n"
        f"🆔 المعرف: {stats['telegram_id']}\n"
        f"👤 الاسم: {stats['first_name']} {stats['last_name'] or ''}\n"
        f"📧 اليوزر: @{stats['username'] or '—'}\n"
        f"📅 تاريخ الانضمام: {stats['joined_at']}\n\n"
        f"📨 الرسائل المرسلة: {stats['message_count']}\n"
        f"📤 الملفات المرفوعة: {stats['file_count']}\n"
        f"🔍 عمليات البحث: {stats['search_count']}\n"
        f"🕐 آخر نشاط: {stats['last_activity']}"
    )
    await message.reply(text)

# ==================== أمر /stats ====================
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    if user_id not in ADMIN_IDS:
        await message.reply("⛔ هذا الأمر للمشرفين فقط.")
        return

    stats = db.get_stats()
    text = (
        f"📊 إحصائيات البوت الكاملة\n\n"
        f"👥 إجمالي المستخدمين: {stats['users_count']}\n"
        f"📤 الملفات المرفوعة: {stats['files_count']}\n"
        f"🔍 عمليات البحث: {stats['searches_count']}\n"
        f"💾 إجمالي الحجم المخزن: {stats['total_size'] / (1024**3):.2f} GB"
    )
    await message.reply(text)

# ==================== الرسائل غير المعروفة ====================
@dp.message()
async def handle_any_message(message: Message):
    db.increment_message_count(message.from_user.id)
    await message.reply(
        "❓ لم أفهم طلبك.\n\n"
        "استخدم /help لمعرفة الأوامر المتاحة."
    )

# ==================== تشغيل البوت ====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
