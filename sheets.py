# sheets.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

from config import ItemsRange, StoreBlock

# Здесь позже подключим Google Sheets API.
# Пока сделаем "заглушки", чтобы бот уже работал, даже без интеграции.

async def read_items_from_template(order_type: str, items_range: ItemsRange) -> list[str]:
    """
    TODO: Реализация:
      - прочитать из Google Sheets диапазон {col}{row_start}:{col}{row_end}
      - вернуть список наименований (без пустых строк)
    Пока возвращаем тестовый список.
    """
    return [
        "ТЕСТ Товар 1",
        "ТЕСТ Товар 2",
        "ТЕСТ Товар 3",
    ]


async def ensure_daily_sheet_exists(order_type: str, delivery_date: date) -> str:
    """
    TODO: Реализация:
      - проверить, есть ли лист/файл для этой даты
      - если нет — скопировать TEMPLATE_* и назвать, например RC_YYYY-MM-DD
      - вернуть имя листа/идентификатор
    """
    return f"{order_type}_{delivery_date.isoformat()}"


async def write_qty_to_sheet(
    order_type: str,
    daily_sheet_name: str,
    store: StoreBlock,
    item_name: str,
    qty: int,
) -> None:
    """
    TODO: Реализация:
      1) внутри блока store найти строку, где item_name совпадает в items_col
      2) записать qty в qty_col
    """
    return
