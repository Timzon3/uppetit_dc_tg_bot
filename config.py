# config.py
from dataclasses import dataclass
from typing import Iterable

# ====== 1) ШАБЛОНЫ (Google Sheets) ======
# ВАЖНО: spreadsheet_id — это ID из ссылки Google Sheets (между /d/ и /edit)

RC_TEMPLATE_SPREADSHEET_ID = "1d6FO0tJQnRvSrnP41dCCCrdNQOYFSzXdyXDPI6RE53U"
RC_TEMPLATE_SHEET_NAME = "общий"

FREEZE_TEMPLATE_SPREADSHEET_ID = "1tGpxU5MJZ8MOTK-uaIswtMYkEuXw1pTxXqCVwrvEhSM"
FREEZE_TEMPLATE_SHEET_NAME = "Сводный"


# ====== 2) МАТРИЦА: адреса по строке, товары по строкам в одной колонке ======
@dataclass(frozen=True)
class MatrixLayout:
    # где лежит шаблон (мастер-лист), который копируется на дату
    spreadsheet_id: str
    template_sheet_name: str

    # Адреса в заголовке: читаем вправо начиная с (address_header_row, address_start_col_letter),
    # пока не встретим пустую ячейку.
    address_header_row: int
    address_start_col_letter: str

    # Товары: читаем названия товаров из одной колонки в диапазоне строк
    item_name_col_letter: str
    item_row_start: int
    item_row_end: int

    # Исключения: какие строки внутри диапазона товаров НЕ читать (шапки/итоги/пустышки)
    # Пример: {7, 10}
    item_exclude_rows: set[int] | None = None

    # Дополнительно: какие значения считать "мусором" и не включать в список товаров
    # (например: "ИТОГО", "Всего", "-", "")
    item_exclude_values: set[str] | None = None


# ====== 3) Конфигурации под каждый тип заказа ======
# РЦ:
# - адреса: строка 1, стартовая колонка C => C1, D1, E1... пока не пусто
# - товары: колонка B, строки 5..13 включительно
RC_LAYOUT = MatrixLayout(
    spreadsheet_id=RC_TEMPLATE_SPREADSHEET_ID,
    template_sheet_name=RC_TEMPLATE_SHEET_NAME,

    address_header_row=1,
    address_start_col_letter="C",

    item_name_col_letter="B",
    item_row_start=5,
    item_row_end=13,

    # TODO: сюда добавишь строки-исключения, если надо, например {6, 9}
    item_exclude_rows=set(),

    # TODO: сюда добавишь слова/значения, которые не считаем товаром
    # Пример: {"ИТОГО", "Всего", "-"}
    item_exclude_values=set(),
)

# Заморозка:
# - адреса: строка 5, стартовая колонка U => U5, V5, W5... пока не пусто
# - товары: колонка B, строки 23..29 включительно
FREEZE_LAYOUT = MatrixLayout(
    spreadsheet_id=FREEZE_TEMPLATE_SPREADSHEET_ID,
    template_sheet_name=FREEZE_TEMPLATE_SHEET_NAME,

    address_header_row=5,
    address_start_col_letter="U",

    item_name_col_letter="B",
    item_row_start=23,
    item_row_end=29,

    # TODO: строки-исключения
    item_exclude_rows=set(),

    # TODO: значения-исключения
    item_exclude_values=set(),
)


# ====== 4) КРАТНОСТИ (на старте словарём; позже можно вынести в отдельный лист) ======
# Ключ = точное имя товара как в таблице. Значение = кратность (1, 6, 12...)
RC_MULTIPLES: dict[str, int] = {
    # TODO: заполни по мере готовности
    # "Соевый соус 30 мл": 10,
}

FREEZE_MULTIPLES: dict[str, int] = {
    # TODO
}


# ====== 5) ПРАВИЛА ДАТ / ДЕДЛАЙНЫ ======
# (оставляю как было — ты уже описывал логику; время дедлайна задаём здесь)
DEADLINE_HOUR = 23
DEADLINE_MINUTE = 59
TIMEZONE = "Europe/Moscow"
