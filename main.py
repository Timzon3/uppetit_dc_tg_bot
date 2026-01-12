# main.py
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
import uvicorn

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import (
    STORES,
    RC_ITEMS_RANGE,
    FREEZE_ITEMS_RANGE,
    RC_MULTIPLES,
    FREEZE_MULTIPLES,
)
from dates import available_delivery_dates
from sheets import (
    read_items_from_template,
    ensure_daily_sheet_exists,
    write_qty_to_sheet,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # например https://xxxxx.onrender.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret")  # любой текст


# ====== Ключи состояния в user_data ======
K_STORE_ID = "store_id"
K_ORDER_TYPE = "order_type"      # "RC" | "FREEZE"
K_SUBTYPE = "subtype"            # "RC_1" | "RC_2" | None
K_DELIVERY_DATE = "delivery_date"
K_DAILY_SHEET = "daily_sheet"
K_ITEMS_CACHE = "items_cache"    # list[str]


# ====== Callback data ======
def cb(action: str, value: str = "") -> str:
    return f"{action}:{value}"


# ====== Меню ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот для оформления заказов.\n\nНажми: Создать заказ",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧾 Создать заказ", callback_data=cb("create_order"))]
        ])
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    action, _, value = q.data.partition(":")

    # Универсальная кнопка "назад"
    if action == "back":
        target = value
        await route_back(q, context, target)
        return

    # Роутинг
    if action == "create_order":
        await step_choose_store(q, context)
    elif action == "store":
        context.user_data[K_STORE_ID] = value
        await step_choose_order_type(q, context)
    elif action == "otype":
        context.user_data[K_ORDER_TYPE] = value  # RC / FREEZE
        # Для РЦ просим подтип (т.к. от него зависит календарь)
        if value == "RC":
            await step_choose_rc_subtype(q, context)
        else:
            context.user_data[K_SUBTYPE] = None
            await step_choose_delivery_date(q, context)
    elif action == "subtype":
        context.user_data[K_SUBTYPE] = value  # RC_1 / RC_2
        await step_choose_delivery_date(q, context)
    elif action == "ddate":
        # value = ISO date
        context.user_data[K_DELIVERY_DATE] = value
        # создаём/проверяем лист под дату
        daily_sheet = await ensure_daily_sheet_exists(
            context.user_data[K_ORDER_TYPE],
            datetime.fromisoformat(value).date(),
        )
        context.user_data[K_DAILY_SHEET] = daily_sheet
        await step_choose_item(q, context)
    elif action == "item":
        item_name = value
        await step_choose_qty(q, context, item_name)
    elif action == "qty":
        # value = "item_name|qty"
        item_name, _, qty_str = value.partition("|")
        qty = int(qty_str)
        await finalize_add_item(q, context, item_name, qty)
    elif action == "finish":
        await q.edit_message_text("✅ Заказ завершён. Спасибо!")
        context.user_data.clear()
    else:
        await q.edit_message_text("Не понял команду. Нажми /start")


async def route_back(q, context, target: str) -> None:
    if target == "store":
        await step_choose_store(q, context)
    elif target == "otype":
        await step_choose_order_type(q, context)
    elif target == "subtype":
        await step_choose_rc_subtype(q, context)
    elif target == "ddate":
        await step_choose_delivery_date(q, context)
    elif target == "item":
        await step_choose_item(q, context)
    else:
        await step_choose_store(q, context)


# ====== Шаги ======
async def step_choose_store(q, context) -> None:
    buttons = []
    for s in STORES:
        buttons.append([InlineKeyboardButton(s.store_name, callback_data=cb("store", s.store_id))])
    kb = buttons + [[InlineKeyboardButton("⛔ Отмена", callback_data=cb("finish"))]]
    await q.edit_message_text("Выбери магазин:", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_order_type(q, context) -> None:
    kb = [
        [InlineKeyboardButton("🏬 РЦ", callback_data=cb("otype", "RC"))],
        [InlineKeyboardButton("🧊 Заморозка", callback_data=cb("otype", "FREEZE"))],
        [InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "store"))],
    ]
    await q.edit_message_text("Выбери тип заказа:", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_rc_subtype(q, context) -> None:
    # TODO: можешь переименовать кнопки как хочешь
    kb = [
        [InlineKeyboardButton("РЦ-1: наклейки + соевый", callback_data=cb("subtype", "RC_1"))],
        [InlineKeyboardButton("РЦ-2: Магария + майонез", callback_data=cb("subtype", "RC_2"))],
        [InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "otype"))],
    ]
    await q.edit_message_text("Выбери подтип РЦ (влияет на даты):", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_delivery_date(q, context) -> None:
    otype = context.user_data.get(K_ORDER_TYPE)
    subtype = context.user_data.get(K_SUBTYPE)
    opts = available_delivery_dates(otype, subtype)

    kb = [[InlineKeyboardButton(o.label, callback_data=cb("ddate", o.delivery_date.isoformat()))] for o in opts]
    back_to = "subtype" if otype == "RC" else "otype"
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", back_to))])

    await q.edit_message_text("Выбери дату доставки (доступные варианты):", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_item(q, context) -> None:
    otype = context.user_data.get(K_ORDER_TYPE)

    # читаем список товаров из шаблона (пока заглушка)
    if otype == "RC":
        items = await read_items_from_template("RC", RC_ITEMS_RANGE)
    else:
        items = await read_items_from_template("FREEZE", FREEZE_ITEMS_RANGE)

    context.user_data[K_ITEMS_CACHE] = items

    kb = []
    for name in items[:25]:  # чтобы не раздувать клавиатуру
        kb.append([InlineKeyboardButton(name, callback_data=cb("item", name))])

    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "ddate"))])
    kb.append([InlineKeyboardButton("✅ Завершить заказ", callback_data=cb("finish"))])

    await q.edit_message_text("Выбери товар:", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_qty(q, context, item_name: str) -> None:
    otype = context.user_data.get(K_ORDER_TYPE)

    multiple = 1
    if otype == "RC":
        multiple = RC_MULTIPLES.get(item_name, 1)
    else:
        multiple = FREEZE_MULTIPLES.get(item_name, 1)

    # Простейшие кнопки количества (позже сделаем ввод числом)
    suggested = [multiple, multiple * 2, multiple * 3]
    kb = [[InlineKeyboardButton(str(x), callback_data=cb("qty", f"{item_name}|{x}"))] for x in suggested]

    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "item"))])

    await q.edit_message_text(
        f"Товар: {item_name}\n"
        f"Кратность: {multiple}\n\n"
        f"Выбери количество (пока кнопками):",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def finalize_add_item(q, context, item_name: str, qty: int) -> None:
    otype = context.user_data.get(K_ORDER_TYPE)
    store_id = context.user_data.get(K_STORE_ID)
    daily_sheet = context.user_data.get(K_DAILY_SHEET)

    store = next((s for s in STORES if s.store_id == store_id), None)
    if not store:
        await q.edit_message_text("Ошибка: магазин не найден. Нажми /start")
        context.user_data.clear()
        return

    # TODO: здесь мы позже будем писать в Google Sheets по твоим диапазонам
    await write_qty_to_sheet(otype, daily_sheet, store, item_name, qty)

    kb = [
        [InlineKeyboardButton("➕ Добавить ещё товар", callback_data=cb("item", ""))],  # будет отработано как step_choose_item
        [InlineKeyboardButton("✅ Завершить заказ", callback_data=cb("finish"))],
    ]
    # трюк: если item пустой — просто снова покажем список
    await q.edit_message_text(
        f"Добавлено: {item_name} — {qty}\n"
        f"Лист заказа: {daily_sheet}\n\n"
        f"Что дальше?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить ещё товар", callback_data=cb("show_items"))],
            [InlineKeyboardButton("✅ Завершить заказ", callback_data=cb("finish"))],
        ]),
    )


async def show_items(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await step_choose_item(q, context)


# ====== FastAPI wrapper для webhook ======
app = FastAPI()
ptb_app: Application | None = None


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True}


@app.post(f"/telegram/{WEBHOOK_SECRET}")
async def telegram_webhook(req: Request) -> dict[str, Any]:
    if not ptb_app:
        return {"ok": False, "error": "bot not ready"}

    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}


def build_bot() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env var is missing")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(show_items, pattern=r"^show_items:"))
    application.add_handler(CallbackQueryHandler(on_callback))
    return application


@app.on_event("startup")
async def on_startup() -> None:
    global ptb_app
    ptb_app = build_bot()
    await ptb_app.initialize()
    await ptb_app.start()

    # Если задан WEBHOOK_URL — ставим webhook (Render)
    if WEBHOOK_URL:
        url = f"{WEBHOOK_URL}/telegram/{WEBHOOK_SECRET}"
        log.info("Setting webhook: %s", url)
        await ptb_app.bot.set_webhook(url)

    log.info("BOT STARTED")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if ptb_app:
        await ptb_app.stop()
        await ptb_app.shutdown()


if __name__ == "__main__":
    # Локально можно запускать так же (для Render всё равно будет uvicorn)
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
