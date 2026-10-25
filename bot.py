"""Telegram-бот, который напоминает о тренировках."""
import logging
import os
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db
from parsing import format_days, parse_days, parse_time

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("workout-bot")

DEFAULT_TZ = "UTC"  # переопределяется переменной DEFAULT_TZ в .env

TITLE, DAYS, TIME, EXERCISES = range(4)

HELP = (
    "Я напоминаю о тренировках 💪\n\n"
    "/add — добавить тренировку\n"
    "/list — мои тренировки\n"
    "/delete — удалить тренировку\n"
    "/timezone Europe/Riga — часовой пояс\n"
    "/stats — сколько тренировок сделано за 30 дней\n"
    "/cancel — отменить ввод"
)


# ---------- планировщик ----------

def job_name(workout_id: int) -> str:
    return f"workout-{workout_id}"


def schedule(job_queue, workout: dict, tz: str) -> None:
    """Ставит ежедневную задачу на нужные дни недели."""
    when = time(workout["hour"], workout["minute"], tzinfo=ZoneInfo(tz))
    # у нас 0 = понедельник, в JobQueue 0 = воскресенье
    days = tuple((d + 1) % 7 for d in workout["days"])
    job_queue.run_daily(
        send_reminder,
        time=when,
        days=days,
        chat_id=workout["chat_id"],
        name=job_name(workout["id"]),
        data=workout["id"],
    )


def unschedule(job_queue, workout_id: int) -> None:
    for job in job_queue.get_jobs_by_name(job_name(workout_id)):
        job.schedule_removal()


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    workout = db.get_workout(context.job.data)
    if workout is None:
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Сделала", callback_data=f"log:{workout['id']}:done"),
        InlineKeyboardButton("⏭ Пропустила", callback_data=f"log:{workout['id']}:skipped"),
    ]])
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"🏋️ Время тренировки: {workout['title']}\n\n{workout['exercises']}",
        reply_markup=keyboard,
    )


async def on_startup(app: Application) -> None:
    """После перезапуска бота восстанавливаем все напоминания из базы."""
    default_tz = os.getenv("DEFAULT_TZ", DEFAULT_TZ)
    for workout in db.all_workouts():
        schedule(app.job_queue, workout, db.get_tz(workout["chat_id"], default_tz))
    await app.bot.set_my_commands([
        BotCommand("add", "добавить тренировку"),
        BotCommand("list", "мои тренировки"),
        BotCommand("delete", "удалить тренировку"),
        BotCommand("timezone", "часовой пояс"),
        BotCommand("stats", "статистика"),
        BotCommand("help", "помощь"),
    ])
    log.info("Восстановлено тренировок: %d", len(db.all_workouts()))


# ---------- простые команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP)


def user_tz(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    return db.get_tz(chat_id, context.bot_data["default_tz"])


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    workouts = db.list_workouts(update.effective_chat.id)
    if not workouts:
        await update.message.reply_text("Пока нет тренировок. Добавь первую: /add")
        return
    lines = []
    for w in workouts:
        lines.append(
            f"• {w['title']} — {format_days(w['days'])} в {w['hour']:02d}:{w['minute']:02d}\n"
            f"{w['exercises']}"
        )
    tz = user_tz(context, update.effective_chat.id)
    await update.message.reply_text("\n\n".join(lines) + f"\n\n🕐 Часовой пояс: {tz}")


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    workouts = db.list_workouts(update.effective_chat.id)
    if not workouts:
        await update.message.reply_text("Удалять пока нечего.")
        return
    buttons = [
        [InlineKeyboardButton(
            f"🗑 {w['title']} ({format_days(w['days'])}, {w['hour']:02d}:{w['minute']:02d})",
            callback_data=f"del:{w['id']}",
        )]
        for w in workouts
    ]
    await update.message.reply_text("Какую удалить?", reply_markup=InlineKeyboardMarkup(buttons))


async def timezone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            f"Сейчас: {user_tz(context, chat_id)}\n"
            "Чтобы изменить: /timezone Europe/Riga"
        )
        return
    tz = context.args[0]
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        await update.message.reply_text(
            "Не знаю такой пояс. Формат: Europe/Riga, Europe/Moscow, Asia/Almaty…"
        )
        return
    db.set_tz(chat_id, tz)
    for w in db.list_workouts(chat_id):  # пересоздаём напоминания с новым поясом
        unschedule(context.job_queue, w["id"])
        schedule(context.job_queue, w, tz)
    await update.message.reply_text(f"Готово, часовой пояс: {tz}")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = db.stats(update.effective_chat.id, 30)
    await update.message.reply_text(
        f"За 30 дней:\n✅ сделано: {s['done']}\n⏭ пропущено: {s['skipped']}"
    )


# ---------- кнопки ----------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    chat_id = update.effective_chat.id

    if parts[0] == "log":
        workout_id, status = int(parts[1]), parts[2]
        workout = db.get_workout(workout_id)
        if workout is None or workout["chat_id"] != chat_id:
            await query.edit_message_reply_markup(None)
            return
        db.add_log(workout_id, chat_id, status)
        mark = "✅ Записала: сделано" if status == "done" else "⏭ Записала: пропущено"
        await query.edit_message_text(f"{query.message.text}\n\n{mark}")

    elif parts[0] == "del":
        workout_id = int(parts[1])
        if db.delete_workout(workout_id, chat_id):
            unschedule(context.job_queue, workout_id)
            await query.edit_message_text("Удалено 🗑")
        else:
            await query.edit_message_text("Эта тренировка уже удалена.")


# ---------- диалог /add ----------

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Как назовём тренировку? Например: Ноги или Утренняя зарядка")
    return TITLE


async def add_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["title"] = update.message.text.strip()[:100]
    await update.message.reply_text(
        "В какие дни? Например: пн ср пт, будни, выходные или каждый день"
    )
    return DAYS


async def add_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    days = parse_days(update.message.text)
    if days is None:
        await update.message.reply_text("Не поняла дни 🤔 Попробуй так: пн ср пт")
        return DAYS
    context.user_data["days"] = days
    await update.message.reply_text("Во сколько напомнить? Формат ЧЧ:ММ, например 18:30")
    return TIME


async def add_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    t = parse_time(update.message.text)
    if t is None:
        await update.message.reply_text("Не похоже на время. Нужен формат ЧЧ:ММ, например 07:45")
        return TIME
    context.user_data["hour"], context.user_data["minute"] = t.hour, t.minute
    await update.message.reply_text(
        "Теперь упражнения — каждое с новой строки, например:\n"
        "Приседания 3x12\nВыпады 3x10\nПланка 3x40 сек"
    )
    return EXERCISES


async def add_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    d = context.user_data
    workout = db.add_workout(
        chat_id, d["title"], d["days"], d["hour"], d["minute"], update.message.text.strip()
    )
    schedule(context.job_queue, workout, user_tz(context, chat_id))
    await update.message.reply_text(
        f"Добавила ✅\n{workout['title']} — {format_days(workout['days'])} "
        f"в {workout['hour']:02d}:{workout['minute']:02d}"
    )
    d.clear()
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Отменила.")
    return ConversationHandler.END


def main() -> None:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Не найден BOT_TOKEN. Создай файл .env (см. .env.example).")

    db.init_db(os.getenv("DB_PATH", "workout_bot.db"))

    app = Application.builder().token(token).post_init(on_startup).build()
    app.bot_data["default_tz"] = os.getenv("DEFAULT_TZ", DEFAULT_TZ)

    text = filters.TEXT & ~filters.COMMAND
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            TITLE: [MessageHandler(text, add_title)],
            DAYS: [MessageHandler(text, add_days)],
            TIME: [MessageHandler(text, add_time)],
            EXERCISES: [MessageHandler(text, add_exercises)],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
    ))
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("timezone", timezone_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CallbackQueryHandler(on_button))

    log.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
