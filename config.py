# config.py
from dataclasses import dataclass

# ====== 1) ШАБЛОНЫ (Google Sheets) ======
# TODO: сюда вставишь ID таблиц и названия листов-шаблонов
# Например, если ссылка такая:
# https://docs.google.com/spreadsheets/d/1AbCDEFgHIjk.../edit#gid=0
# то spreadsheet_id = "1AbCDEFgHIjk..."
RC_TEMPLATE_SPREADSHEET_ID = "PASTE_RC_SHEET_ID_HERE"          # TODO
RC_TEMPLATE_SHEET_NAME = "TEMPLATE_RC"                         # TODO

FREEZE_TEMPLATE_SPREADSHEET_ID = "PASTE_FREEZE_SHEET_ID_HERE"  # TODO
FREEZE_TEMPLATE_SHEET_NAME = "TEMPLATE_FREEZE"                 # TODO


# ====== 2) ДИАПАЗОНЫ ТОВАРОВ (откуда бот читает наименования) ======
@dataclass(frozen=True)
class ItemsRange:
    sheet_name: str
    col_letter: str
    row_start: int
    row_end: int

# TODO: укажи колонку и строки для наименований
RC_ITEMS_RANGE = ItemsRange(
    sheet_name=RC_TEMPLATE_SHEET_NAME,
    col_letter="C",      # TODO
    row_start=8,         # TODO
    row_end=120,         # TODO
)

FREEZE_ITEMS_RANGE = ItemsRange(
    sheet_name=FREEZE_TEMPLATE_SHEET_NAME,
    col_letter="C",      # TODO
    row_start=8,         # TODO
    row_end=120,         # TODO
)


# ====== 3) МАГАЗИНЫ И ИХ БЛОКИ В ШАБЛОНАХ ======
# TODO: здесь ты задашь диапазоны строк/столбцов для каждого адреса.
# Мы будем:
# 1) искать товар по имени в колонке товаров внутри блока
# 2) писать количество в qty_col_letter

@dataclass(frozen=True)
class StoreBlock:
    store_id: str
    store_name: str

    # Блок в РЦ-шаблоне
    rc_row_start: int
    rc_row_end: int
    rc_items_col_letter: str   # где в блоке написаны товары (обычно та же колонка, что и RC_ITEMS_RANGE)
    rc_qty_col_letter: str     # куда писать количества

    # Блок в Заморозке-шаблоне
    freeze_row_start: int
    freeze_row_end: int
    freeze_items_col_letter: str
    freeze_qty_col_letter: str

STORES: list[StoreBlock] = [
    # TODO: заполни реальные диапазоны по адресу
    StoreBlock(
        store_id="store_1",
        store_name="Блохина 1/75",  # TODO
        rc_row_start=12, rc_row_end=40, rc_items_col_letter="C", rc_qty_col_letter="F",  # TODO
        freeze_row_start=12, freeze_row_end=40, freeze_items_col_letter="C", freeze_qty_col_letter="F",  # TODO
    ),
]


# ====== 4) КРАТНОСТИ ======
# Ты хотел сначала автосчитать товары, а потом отдельно проставить кратность.
# Для MVP начнем с простого словаря (позже перенесем в Google Sheets "SKU_RULES").
# Ключ = точное имя как в шаблоне.
RC_MULTIPLES: dict[str, int] = {
    # "Соевый соус 30мл": 10,
    # "Наклейки ...": 1,
    # TODO
}

FREEZE_MULTIPLES: dict[str, int] = {
    # TODO
}


# ====== 5) ПРАВИЛА ДАТ / ДЕДЛАЙНЫ ======
# TODO: время дедлайна "вечер" (в 24-часовом формате)
DEADLINE_HOUR = 20
DEADLINE_MINUTE = 0
TIMEZONE = "Europe/Moscow"
