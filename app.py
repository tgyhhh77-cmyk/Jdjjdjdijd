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

folder


@dp.message(Command("help"))
async def cmd_help(message: Message):
    db.increment_message_count(message.from_user.id)
    help_text = (
        "📖 <b>دليل الاستخدام</b>\n\n"
        "<b>📤 رفع ملف:</b>\n"
        "• أرسل ملف .txt مباشرة في المحادثة\n"
        "• أو اضغط /upload\n\n"
        "<b>🔍 البحث:</b>\n"
        "• /search النص_المطلوب\n"
        "• مثال: <code>/search محمد أحمد</code>\n\n"
        "<b>📂 إدارة الملفات:</b>\n"
        "• /myfiles - قائمة ملفاتك\n"
        "• /status - إحصائياتك الشخصية\n\n"
        "<b>👨‍💼 للمشرفين:</b>\n"
        "• /stats - إحصائيات البوت الكاملة"
    )
    await message.reply(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command("upload"))
async def cmd_upload(message: Message):
    db.increment_message_count(message.from_user.id)
    await message.reply(
        "📤 <b>جاهز لاستقبال ملفك!</b>\n\n"
        "أرسل لي ملف نصي بصيغة <code>.txt</code>\n"
        "✅ يمكن أن يكون الملف ضخماً — أنا أتعامل معه بكفاءة عالية!",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.document)
async def handle_document(message: Message):
    user = message.from_user
    db.increment_message_count(user.id)

    if not message.document.file_name.endswith('.txt'):
        await message.reply("❌ أقبل فقط ملفات <code>.txt</code>", parse_mode=ParseMode.HTML)
        db.add_log(user.id, "upload_rejected", f"Wrong format: {message.document.file_name}")
        return

    user_folder = get_user_folder(user.id)
    file_path = os.path.join(user_folder, message.document.file_name)

    if os.path.exists(file_path):
        os.remove(file_path)
        db.delete_user_file(user.id, message.document.file_name)

    msg = await message.reply("⏳ جاري تحميل الملف...", parse_mode=ParseMode.HTML)

    try:
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, file_path)
        file_size = os.path.getsize(file_path)

        db.add_file(user.id, message.document.file_name, file_path, file_size)
        db.add_log(user.id, "upload_success", f"File: {message.document.file_name}, Size: {file_size}")

        size_mb = file_size / (1024 * 1024)
        await msg.edit_text(
            f"✅ <b>تم رفع الملف بنجاح!</b>\n\n"
            f"📄 الاسم: <code>{message.document.file_name}</code>\n"
            f"📦 الحجم: <code>{size_mb:.2f} MB</code>\n\n"
            f"🔍 يمكنك البحث الآن باستخدام:\n"
            f"<code>/search النص_المطلوب</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Upload error for user {user.id}: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء تحميل الملف. حاول مرة أخرى.")
        db.add_log(user.id, "upload_error", str(e))

@dp.message(Command("search"))
async def cmd_search(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "❌ <b>استخدام خاطئ</b>\n\n"
            "الصيغة الصحيحة:\n"
            "<code>/search النص_المطلوب</code>\n\n"
            "مثال:\n<code>/search مرحبا بالعالم</code>",
            parse_mode=ParseMode.HTML
        )
        return

    query = args[1].strip()
    if len(query) < 2:
        await message.reply("❌ نص البحث قصير جداً. أدخل حرفين على الأقل.")
        return

    user_folder = get_user_folder(user_id)
    if not os.path.exists(user_folder) or not os.listdir(user_folder):
        await message.reply("❌ ليس لديك ملفات مرفوعة. أرسل ملفاً أولاً باستخدام /upload")
        return

    msg = await message.reply(f"🔍 جاري البحث عن: <code>{query}</code>...", parse_mode=ParseMode.HTML)

    try:
        searcher = LargeTextSearcher(user_folder)
        results, time_taken, total_data_processed, total_results = await searcher.async_query_files(query)

        db.add_search(user_id, query, total_results, time_taken, total_data_processed)
        db.add_log(user_id, "search", f"Query: {query}, Results: {total_results}")

        if total_results == 0:
            await msg.edit_text(
                f"😕 <b>لم أجد نتائج</b>\n\n"
                f"⏱️ الوقت: <code>{time_taken:.4f} ثانية</code>\n"
                f"📦 البيانات المُعالجة: <code>{total_data_processed / (1024**2):.2f} MB</code>",
                parse_mode=ParseMode.HTML
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
                f"✅ <b>تم العثور على {total_results} نتيجة</b>\n\n"
                f"⏱️ الوقت: <code>{time_taken:.4f} ثانية</code>\n"
                f"📦 البيانات: <code>{total_data_processed / (1024**2):.2f} MB</code>\n"
                f"📄 النتائج كثيرة، أرسلها لك في ملف...",
                parse_mode=ParseMode.HTML
            )
            await message.reply_document(FSInputFile(result_file), caption=f"🔍 نتائج البحث: {query}")
        else:
            text_results = "\n".join([f"• {r[:200]}" for r in results[:30]])
            if len(text_results) > 3500:
                text_results = text_results[:3500] + "\n\n... (تم اقتصاص الباقي)"

            await msg.edit_text(
                f"✅ <b>تم العثور على {total_results} نتيجة</b>\n\n"
                f"⏱️ الوقت: <code>{time_taken:.4f} ثانية</code>\n"
                f"📦 البيانات: <code>{total_data_processed / (1024**2):.2f} MB</code>\n\n"
                f"📝 <b>النتائج:</b>\n{text_results}",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logging.error(f"Search error for user {user_id}: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء البحث. حاول مرة أخرى.")
        db.add_log(user_id, "search_error", str(e))

@dp.message(Command("myfiles"))
async def cmd_myfiles(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    files = db.get_user_files(user_id)
    if not files:
        await message.reply("📂 ليس لديك ملفات مرفوعة.")
        return

    text = "📂 <b>ملفاتك المرفوعة:</b>\n\n"
    total_size = 0
    for i, f in enumerate(files, 1):
        size_mb = f['file_size'] / (1024 * 1024)
        total_size += f['file_size']
        text += f"{i}. <code>{f['filename']}</code> ({size_mb:.2f} MB)\n"

    text += f"\n📊 الإجمالي: <code>{len(files)}</code> ملف | <code>{total_size / (1024**2):.2f} MB</code>"
    await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    stats = db.get_user_stats(user_id)
    if not stats:
        await message.reply("❌ لم أجد بياناتك.")
        return

    text = (
        f"👤 <b>حالة حسابك</b>\n\n"
        f"🆔 المعرف: <code>{stats['telegram_id']}</code>\n"
        f"👤 الاسم: {stats['first_name']} {stats['last_name'] or ''}\n"
        f"📧 اليوزر: @{stats['username'] or '—'}\n"
        f"📅 تاريخ الانضمام: {stats['joined_at']}\n\n"
        f"📨 الرسائل المرسلة: <code>{stats['message_count']}</code>\n"
        f"📤 الملفات المرفوعة: <code>{stats['file_count']}</code>\n"
        f"🔍 عمليات البحث: <code>{stats['search_count']}</code>\n"
        f"🕐 آخر نشاط: {stats['last_activity']}"
    )
    await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    db.increment_message_count(user_id)

    if user_id not in ADMIN_IDS:
        await message.reply("⛔ هذا الأمر للمشرفين فقط.")
        return

    stats = db.get_stats()
    text = (
        f"📊 <b>إحصائيات البوت الكاملة</b>\n\n"
        f"👥 إجمالي المستخدمين: <code>{stats['users_count']}</code>\n"
        f"📤 الملفات المرفوعة: <code>{stats['files_count']}</code>\n"
        f"🔍 عمليات البحث: <code>{stats['searches_count']}</code>\n"
        f"💾 إجمالي الحجم المخزن: <code>{stats['total_size'] / (1024**3):.2f} GB</code>"
    )
    await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message()
async def handle_any_message(message: Message):
    db.increment_message_count(message.from_user.id)
    await message.reply(
        "❓ لم أفهم طلبك.\n\n"
        "استخدم /help لمعرفة الأوامر المتاحة.",
        parse_mode=ParseMode.HTML
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
