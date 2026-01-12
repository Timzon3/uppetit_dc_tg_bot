# sheets.py
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import date
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import MatrixLayout


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _col_letter_to_index(col: str) -> int:
    """A -> 1, B -> 2, ..."""
    col = col.upper()
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _index_to_col_letter(n: int) -> str:
    """1 -> A, 2 -> B, ..."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(r + ord("A")) + s
    return s


def _get_sheets_service():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON env var is missing")

    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


@dataclass(frozen=True)
class AddressCol:
    address: str
    col_letter: str   # куда писать количество (колонка адреса)
    col_index: int    # 1-based индекс колонки


async def read_addresses(layout: MatrixLayout) -> list[AddressCol]:
    """
    Читает адреса вправо по одной строке, начиная с layout.address_start_col_letter.
    Останавливается на первой пустой ячейке.
    """
    service = _get_sheets_service()
    sheet = layout.template_sheet_name

    start_idx = _col_letter_to_index(layout.address_start_col_letter)
    # Читаем с запасом вправо (например, 200 колонок) и сами остановимся на пустой.
    end_idx = start_idx + 200
    start_col = _index_to_col_letter(start_idx)
    end_col = _index_to_col_letter(end_idx)

    rng = f"{sheet}!{start_col}{layout.address_header_row}:{end_col}{layout.address_header_row}"

    resp = service.spreadsheets().values().get(
        spreadsheetId=layout.spreadsheet_id,
        range=rng,
        majorDimension="ROWS"
    ).execute()

    row = (resp.get("values") or [[]])[0]  # список значений по колонкам
    out: list[AddressCol] = []
    for offset, val in enumerate(row):
        v = (val or "").strip()
        if v == "":
            break
        col_index = start_idx + offset
        out.append(AddressCol(address=v, col_letter=_index_to_col_letter(col_index), col_index=col_index))

    return out


async def read_items(layout: MatrixLayout) -> list[str]:
    """
    Читает названия товаров из одной колонки в диапазоне строк.
    Учитывает исключения строк и значений.
    """
    service = _get_sheets_service()
    sheet = layout.template_sheet_name

    col = layout.item_name_col_letter.upper()
    rng = f"{sheet}!{col}{layout.item_row_start}:{col}{layout.item_row_end}"

    resp = service.spreadsheets().values().get(
        spreadsheetId=layout.spreadsheet_id,
        range=rng,
        majorDimension="COLUMNS",
    ).execute()

    col_vals = (resp.get("values") or [[]])[0]  # список строковых значений

    exclude_rows = layout.item_exclude_rows or set()
    exclude_values = set(x.strip() for x in (layout.item_exclude_values or set()))

    items: list[str] = []
    for i, val in enumerate(col_vals):
        row_num = layout.item_row_start + i
        if row_num in exclude_rows:
            continue
        v = (val or "").strip()
        if not v:
            continue
        if v in exclude_values:
            continue
        items.append(v)

    return items


async def ensure_daily_sheet_exists(layout: MatrixLayout, order_prefix: str, delivery_date: date) -> str:
    """
    Создаёт (если нет) лист на дату как копию template_sheet_name в том же spreadsheet_id.
    Имя листа: {order_prefix}_YYYY-MM-DD
    """
    service = _get_sheets_service()
    target_title = f"{order_prefix}_{delivery_date.isoformat()}"

    # 1) Получим список листов и найдём: существует ли уже target_title и template
    meta = service.spreadsheets().get(spreadsheetId=layout.spreadsheet_id).execute()
    sheets = meta.get("sheets", [])
    title_to_id = {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheets}

    if target_title in title_to_id:
        return target_title

    if layout.template_sheet_name not in title_to_id:
        raise RuntimeError(f"Template sheet '{layout.template_sheet_name}' not found")

    template_sheet_id = title_to_id[layout.template_sheet_name]

    # 2) Копируем template лист внутри того же spreadsheet
    copy_resp = service.spreadsheets().sheets().copyTo(
        spreadsheetId=layout.spreadsheet_id,
        sheetId=template_sheet_id,
        body={"destinationSpreadsheetId": layout.spreadsheet_id},
    ).execute()

    new_sheet_id = copy_resp["sheetId"]
    # 3) Переименуем
    service.spreadsheets().batchUpdate(
        spreadsheetId=layout.spreadsheet_id,
        body={
            "requests": [
                {"updateSheetProperties": {
                    "properties": {"sheetId": new_sheet_id, "title": target_title},
                    "fields": "title"
                }}
            ]
        }
    ).execute()

    return target_title


async def write_qty(layout: MatrixLayout, daily_sheet_name: str, item_name: str, address_col: str, qty: int) -> None:
    """
    Пишет qty в ячейку пересечения:
    - строка товара (ищем item_name в item_name_col_letter в диапазоне item_row_start..item_row_end)
    - колонка адреса = address_col (буква колонки)
    """
    service = _get_sheets_service()

    # читаем колонку с товарами на листе даты (она должна совпадать по структуре с шаблоном)
    col = layout.item_name_col_letter.upper()
    rng = f"{daily_sheet_name}!{col}{layout.item_row_start}:{col}{layout.item_row_end}"

    resp = service.spreadsheets().values().get(
        spreadsheetId=layout.spreadsheet_id,
        range=rng,
        majorDimension="COLUMNS",
    ).execute()

    col_vals = (resp.get("values") or [[]])[0]

    # найдём строку товара
    target_row: Optional[int] = None
    for i, val in enumerate(col_vals):
        if (val or "").strip() == item_name.strip():
            target_row = layout.item_row_start + i
            break

    if target_row is None:
        raise RuntimeError(f"Item '{item_name}' not found in sheet '{daily_sheet_name}'")

    # пишем qty в address_col + target_row
    cell = f"{daily_sheet_name}!{address_col.upper()}{target_row}"
    service.spreadsheets().values().update(
        spreadsheetId=layout.spreadsheet_id,
        range=cell,
        valueInputOption="USER_ENTERED",
        body={"values": [[qty]]},
    ).execute()

