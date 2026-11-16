# -*- coding: utf-8 -*-
"""
ربات تحویل ورد — اختیاری. تحویل اصلی هفتگی از طریق GitHub Actions
(بعد از ساخت ورد، فایل هفته را با Bot API برایت می‌فرستد) انجام می‌شود
و نیازی به سرور همیشه‌روشن ندارد.
این ربات فقط وقتی لازم است که بخواهی هر وقت خواستی دستور بدهی:
  /hafte        ورد تست‌های همین هفته
  /kamel        ورد کلی همه تست‌ها
  /visual_hafte ورد حافظه/پمفلت همین هفته
  /visual_kamel ورد کلی حافظه/پمفلت
  /amar         شمارش‌ها از out/report.json
فقط OWNER_CHAT_ID جواب می‌گیرد. اجرا: python bot.py
روی Render رایگان: Web Service با Start Command همین فایل؛ چون
Render رایگان بعد از ۱۵ دقیقه بی‌کاری می‌خوابد، اولین دستور حدود
یک دقیقه طول می‌کشد تا بیدار شود — این طبیعی است، نه خرابی.
"""
import json
import os
from datetime import date, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

OUT = os.environ.get("OUT_DIR", "out")
# اگر OWNER_CHAT_ID تنظیم نشده باشد، هیچ‌کس جواب نمی‌گیرد
# (قبلاً ۰ یعنی همه مجاز بودند — باگ امنیتی).
OWNER = int(os.environ.get("OWNER_CHAT_ID", "0") or 0)


def latest_weekly(prefix):
    d = os.path.join(OUT, "weekly")
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.startswith(prefix + "-") and f.endswith(".docx"))
    return os.path.join(d, files[-1]) if files else None


def allowed(update: Update):
    return OWNER != 0 and update.effective_chat.id == OWNER


async def send_file(update: Update, path, caption):
    if not path or not os.path.exists(path):
        await update.message.reply_text("هنوز فایلی ساخته نشده. اول collector اجرا شود.")
        return
    with open(path, "rb") as f:
        await update.message.reply_document(document=f, filename=os.path.basename(path), caption=caption)
    # JSON همراهش برای اپ: همان سوال‌ها به‌صورت ساخت‌یافته، کنار ورد.
    json_path = os.path.splitext(path)[0] + ".json"
    if os.path.exists(json_path):
        with open(json_path, "rb") as f:
            await update.message.reply_document(
                document=f, filename=os.path.basename(json_path),
                caption="JSON همین فایل، برای اپلیکیشن")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    await update.message.reply_text(
        "سلام داش 👋\n/hafte — ورد تست‌های همین هفته\n/kamel — ورد کلی تست‌ها\n"
        "/visual_hafte — ورد حافظه/پمفلت همین هفته\n/visual_kamel — ورد کلی حافظه/پمفلت\n/amar — شمارش‌ها")


async def hafte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if allowed(update):
        await send_file(update, latest_weekly("Quiz"), "تست‌های همین هفته")


async def kamel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if allowed(update):
        await send_file(update, os.path.join(OUT, "Neuronurse-Quiz-Kamel.docx"), "فایل کلی همه تست‌ها")


async def visual_hafte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if allowed(update):
        await send_file(update, latest_weekly("Visual"), "حافظه و پمفلت همین هفته")


async def visual_kamel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if allowed(update):
        await send_file(update, os.path.join(OUT, "Neuronurse-Visual-Kamel.docx"), "فایل کلی حافظه و پمفلت")


async def amar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    p = os.path.join(OUT, "report.json")
    if not os.path.exists(p):
        await update.message.reply_text("هنوز گزارشی نیست.")
        return
    r = json.load(open(p, encoding="utf-8"))
    txt = (f"تست‌ها: {r.get('total_quiz')}\nحافظه/پمفلت: {r.get('total_visual')}\n"
           f"تست بدون جواب: {len(r.get('quiz_no_answer', []))}\n"
           f"تست بدون توضیح: {len(r.get('quiz_no_explanation', []))}\n"
           f"هفته‌ها: {len(r.get('weeks', {}))}")
    await update.message.reply_text(txt)


def main():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hafte", hafte))
    app.add_handler(CommandHandler("kamel", kamel))
    app.add_handler(CommandHandler("visual_hafte", visual_hafte))
    app.add_handler(CommandHandler("visual_kamel", visual_kamel))
    app.add_handler(CommandHandler("amar", amar))
    print("ربات روشن شد (polling).")
    app.run_polling()


if __name__ == "__main__":
    main()
