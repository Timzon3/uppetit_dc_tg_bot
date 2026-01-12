# main.py
from __future__ import annotations

import os
import logging
from datetime import datetime

from fastapi import FastAPI, Request
import uvicorn

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import (
    RC_LAYOUT,
    FREEZE_LAYOUT,
    RC_MULTIPLES,
    FREEZE_MULTIPLES,
)
from dates import available_delivery_dates
from sheets import (
    read_addresses,
    read_items,
    ensure_daily_sheet_exists,
    write_qty,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret")

# user_data keys
K_ORDER_TYPE = "order_type"          # "RC" | "FREEZE"
K_SUBTYPE = "subtype"                # "RC_1" | "RC_2" | None
K_DELIVERY_DATE = "delivery_date"    # ISO date
K_DAILY_SHEET = "daily_sheet"        # sheetC_2026-01-16
K_ADDRESS = "address"                # текст адреса
K_ADDRESS_COL = "address_col"        # буква колонки адреса
K_ITEMS_CACHE = "items_cache"        # list[str]


def cb(action: str, value: str = "") -> str:
    return f"{action}:{value}"


app = FastAPI()
ptb_app: Application | None = None


@app.get("/health")
async def health():
    return {"ok": True}


@app.post(f"/telegram/{WEBHOOK_SECRET}")
async def telegram_webhook(req: Request):
    if not ptb_app:
        return {"ok": False, "error": "bot not ready"}
    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}


def _layout_for(otype: str):
    return RC_LAYOUT if otype == "RC" else FREEZE_LAYOUT


def _multiples_for(otype: str):
    return RC_MULTIPLES if otype == "RC" else FREEZE_MULTIPLES


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

    if action == "back":
        await route_back(q, context, value)
        return

    if action == "create_order":
        await step_choose_order_type(q, context)

    elif action == "otype":
        context.user_data[K_ORDER_TYPE] = value  # RC/FREEZE
        if value == "RC":
            await step_choose_rc_subtype(q, context)
        else:
            context.user_data[K_SUBTYPE] = None
            await step_choose_store(q, context)

    elif action == "subtype":
        context.user_data[K_SUBTYPE] = value
        await step_choose_store(q, context)

    elif action == "storecol":
        # value = "COL|address"
        col, _, addr = value.partition("|")
        context.user_data[K_ADDRESS_COL] = col
        context.user_data[K_ADDRESS] = addr
        await step_choose_delivery_date(q, context)

    elif action == "ddate":
        context.user_data[K_DELIVERY_DATE] = value
        otype = context.user_data[K_ORDER_TYPE]
        layout = _layout_for(otype)

        daily_sheet = await ensure_daily_sheet_exists(
            layout=layout,
            order_prefix=otype,
            delivery_date=datetime.fromisoformat(value).date(),
        )
        context.user_data[K_DAILY_SHEET] = daily_sheet
        await step_choose_item(q, context)

    elif action == "item":
        await step_choose_qty(q, context, value)

    elif action == "qty":
        item_name, _, qty_str = value.partition("|")
        qty = int(qty_str)
        await finalize_add_item(q, context, item_name, qty)

    elif action == "show_items":
        await step_choose_item(q, context)

    elif action == "finish":
        await q.edit_message_text("✅ Заказ завершён. Спасибо!")
        context.user_data.clear()

    else:
        await q.edit_message_text("Не понял команду. Нажми /start")


async def route_back(q, context, target: str) -> None:
    if target == "otype":
        await step_choose_order_type(q, context)
    elif target == "subtype":
        await step_choose_rc_subtype(q, context)
    elif target == "store":
        await step_choose_store(q, context)
    elif target == "ddate":
        await step_choose_delivery_date(q, context)
    elif target == "item":
        await step_choose_item(q, context)
    else:
        await step_choose_order_type(q, context)


async def step_choose_order_type(q, context) -> None:
    kb = [
        [InlineKeyboardButton("🏬 РЦ", callback_data=cb("otype", "RC"))],
        [InlineKeyboardButton("🧊 Заморозка", callback_data=cb("otype", "FREEZE"))],
        [InlineKeyboardButton("⛔ Отмена", callback_data=cb("finish"))],
    ]
    await q.edit_message_text("Выбери тип заказа:", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_rc_subtype(q, context) -> None:
    kb = [
        [InlineKeyboardButton("РЦ-1: наклейки + соевый", callback_data=cb("subtype", "RC_1"))],
        [InlineKeyboardButton("РЦ-2: Магария + майонез", callback_data=cb("subtype", "RC_2"))],
        [InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "otype"))],
    ]
    await q.edit_message_text("Выбери подтип РЦ:", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_store(q, context) -> None:
    otype = context.user_data[K_ORDER_TYPE]
    layout = _layout_for(otype)
    addresses = await read_addresses(layout)

    kb = []
    for a in addresses[:40]:  # если адресов много — потом сделаем пагинацию
        kb.append([InlineKeyboardButton(a.address, callback_data=cb("storecol", f"{a.col_letter}|{a.address}"))])

    back_to = "subtype" if otype == "RC" else "otype"
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", back_to))])
    kb.append([InlineKeyboardButton("⛔ Отмена", callback_data=cb("finish"))])

    await q.edit_message_text("Выбери магазин:", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_delivery_date(q, context) -> None:
    otype = context.user_data[K_ORDER_TYPE]
    subtype = context.user_data.get(K_SUBTYPE)
    opts = available_delivery_dates(otype, subtype)

    kb = [[InlineKeyboardButton(o.label, callback_data=cb("ddate", o.delivery_date.isoformat()))] for o in opts]
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "store"))])

    await q.edit_message_text(
        f"Магазин: {context.user_data.get(K_ADDRESS)}\n"
        f"Выбери дату доставки:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def step_choose_item(q, context) -> None:
    otype = context.user_data[K_ORDER_TYPE]
    layout = _layout_for(otype)

    items = await read_items(layout)
    context.user_data[K_ITEMS_CACHE] = items

    kb = []
    for name in items[:40]:
        kb.append([InlineKeyboardButton(name, callback_data=cb("item", name))])

    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "ddate"))])
    kb.append([InlineKeyboardButton("✅ Завершить заказ", callback_data=cb("finish"))])

    await q.edit_message_text("Выбери товар:", reply_markup=InlineKeyboardMarkup(kb))


async def step_choose_qty(q, context, item_name: str) -> None:
    otype = context.user_data[K_ORDER_TYPE]
    multiples = _multiples_for(otype)
    multiple = multiples.get(item_name, 1)

    suggested = [multiple, multiple * 2, multiple * 3]
    kb = [[InlineKeyboardButton(str(x), callback_data=cb("qty", f"{item_name}|{x}"))] for x in suggested]
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=cb("back", "item"))])

    await q.edit_message_text(
        f"Товар: {item_name}\nКратность: {multiple}\n\nВыбери количество:",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def finalize_add_item(q, context, item_name: str, qty: int) -> None:
    otype = context.user_data[K_ORDER_TYPE]
    layout = _layout_for(otype)
    daily_sheet = context.user_data[K_DAILY_SHEET]
    address_col = context.user_data[K_ADDRESS_COL]

    await write_qty(layout, daily_sheet, item_name, address_col, qty)

    await q.edit_message_text(
        f"✅ Добавлено: {item_name} — {qty}\n"
        f"Магазин: {context.user_data.get(K_ADDRESS)}\n"
        f"Лист: {daily_sheet}\n\n"
        f"Что дальше?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить ещё товар", callback_data=cb("show_items"))],
            [InlineKeyboardButton("✅ Завершить заказ", callback_data=cb("finish"))],
        ]),
    )


def build_bot() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env var is missing")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(on_callback))
    return application


@app.on_event("startup")
async def on_startup() -> None:
    global ptb_app
    ptb_app = build_bot()
    await ptb_app.initialize()
    await ptb_app.start()

    if WEBHOOK_URL:
        url = f"{WEBHOOK_URL}/telegram/{WEBHOOK_SECRET}"
        try:
            await ptb_app.bot.set_webhook(url)
            log.info("Webhook set: %s", url)
        except Exception as e:
            log.error("Failed to set webhook (will retry later): %s", e)

    log.info("BOT STARTED")



@app.on_event("shutdown")
async def on_shutdown() -> None:
    if ptb_app:
        await ptb_app.stop()
        await ptb_app.shutdown()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
