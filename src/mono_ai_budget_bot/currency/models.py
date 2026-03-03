from __future__ import annotations

from pydantic import BaseModel


class MonoCurrencyRate(BaseModel):
    currencyCodeA: int
    currencyCodeB: int
    date: int
    rateBuy: float | None = None
    rateSell: float | None = None
    rateCross: float | None = None
