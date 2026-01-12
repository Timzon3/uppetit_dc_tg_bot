# dates.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo

from config import DEADLINE_HOUR, DEADLINE_MINUTE, TIMEZONE

TZ = ZoneInfo(TIMEZONE)

@dataclass(frozen=True)
class DeliveryOption:
    label: str          # текст для кнопки
    delivery_date: date # дата доставки


def _deadline_dt(d: date) -> datetime:
    """Дедлайн в 'вечер' указанного дня."""
    return datetime.combine(d, time(DEADLINE_HOUR, DEADLINE_MINUTE), tzinfo=TZ)


def next_tuesday(d: date) -> date:
    # 0=Mon ... 1=Tue
    days_ahead = (1 - d.weekday()) % 7
    return d + timedelta(days=days_ahead)


def next_thursday(d: date) -> date:
    # 3=Thu
    days_ahead = (3 - d.weekday()) % 7
    return d + timedelta(days=days_ahead)


def next_friday(d: date) -> date:
    # 4=Fri
    days_ahead = (4 - d.weekday()) % 7
    return d + timedelta(days=days_ahead)


def available_delivery_dates(order_type: str, subtype: str | None, now: datetime | None = None) -> list[DeliveryOption]:
    """
    Возвращает 1–3 допустимые даты доставки.
    order_type: "RC" | "FREEZE"
    subtype:
      - для RC: "RC_1" (наклейки+соевый), "RC_2" (Магария+майонез)
      - для FREEZE пока можно None
    """
    now = now.astimezone(TZ) if now else datetime.now(TZ)
    today = now.date()

    # ===== RC subtype 1: дедлайны ВС и СР, доставки ВТ и ЧТ =====
    if order_type == "RC" and subtype == "RC_1":
        # Дедлайн на ближайший вторник: воскресенье (перед этой неделей)
        # Удобно считать так: определим "вторник этой логистической недели"
        tuesday = next_tuesday(today)
        # воскресенье перед этим вторником = tuesday - 2 дня
        sunday_before_tuesday = tuesday - timedelta(days=2)

        thursday = next_thursday(today)
        # среда перед четвергом = thursday - 1 день
        wednesday_before_thursday = thursday - timedelta(days=1)

        options: list[DeliveryOption] = []

        # Окно на вторник (если сейчас до дедлайна воскресенья)
        if now <= _deadline_dt(sunday_before_tuesday):
            options.append(DeliveryOption(label=f"Ближайшая доставка: ВТ {tuesday.isoformat()}", delivery_date=tuesday))
        # Окно на четверг (если сейчас до дедлайна среды)
        if now <= _deadline_dt(wednesday_before_thursday):
            options.append(DeliveryOption(label=f"Ближайшая доставка: ЧТ {thursday.isoformat()}", delivery_date=thursday))

        # Если оба окна закрыты — уходим на следующую неделю (вторник)
        if not options:
            next_week_tuesday = next_tuesday(today + timedelta(days=7))
            options.append(DeliveryOption(label=f"Следующая доставка: ВТ {next_week_tuesday.isoformat()}", delivery_date=next_week_tuesday))

        # Можно добавить 2-ю опцию "следующая после ближайшей", если нужно
        return options[:2]

    # ===== RC subtype 2: дедлайн ВС, доставка ПТ, иначе следующая ПТ =====
    if order_type == "RC" and subtype == "RC_2":
        friday = next_friday(today)

        # дедлайн = воскресенье перед этой пятницей
        sunday_before_friday = friday - timedelta(days=5)  # ПТ-5 = ВС

        if now <= _deadline_dt(sunday_before_friday):
            return [DeliveryOption(label=f"Ближайшая доставка: ПТ {friday.isoformat()}", delivery_date=friday)]
        else:
            next_week_friday = next_friday(today + timedelta(days=7))
            return [DeliveryOption(label=f"Следующая доставка: ПТ {next_week_friday.isoformat()}", delivery_date=next_week_friday)]

    # ===== FREEZE: дедлайн ВС всегда (день доставки ты уточнишь) =====
    if order_type == "FREEZE":
        # TODO: уточни день доставки по заморозке (например СР/ЧТ/ПТ)
        # Пока просто даём выбрать "следующую дату" = +2 дня, но позже заменим
        delivery = today + timedelta(days=2)
        return [DeliveryOption(label=f"Доставка: {delivery.isoformat()} (временная логика)", delivery_date=delivery)]

    # fallback
    return [DeliveryOption(label=f"Доставка: {today.isoformat()} (fallback)", delivery_date=today)]
