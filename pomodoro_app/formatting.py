"""Formatação de tempo e datas usada pelas duas interfaces (padrão brasileiro)."""
from __future__ import annotations

import datetime as _dt
from typing import Optional

DATE_FORMAT = "%d/%m/%Y"
DATETIME_FORMAT = "%d/%m/%Y %H:%M"


def format_mmss(seconds: int) -> str:
    """125 -> "02:05". Valores negativos viram "00:00"."""
    minutes, secs = divmod(max(int(seconds), 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def format_date(value: Optional[_dt.date]) -> str:
    return value.strftime(DATE_FORMAT) if value else ""


def format_datetime(value: Optional[_dt.datetime]) -> str:
    return value.strftime(DATETIME_FORMAT) if value else ""


def parse_date(text: str) -> Optional[_dt.date]:
    """"15/11/2026" -> date(2026, 11, 15). Texto vazio -> None.
    Lança ValueError se o texto não for uma data válida no formato dd/mm/aaaa."""
    text = (text or "").strip()
    if not text:
        return None
    return _dt.datetime.strptime(text, DATE_FORMAT).date()
