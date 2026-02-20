from pydantic import BaseModel, Field


class MonoAccount(BaseModel):
    id: str
    balance: int
    creditLimit: int = 0
    currencyCode: int
    cashbackType: str | None = None
    type: str | None = None
    iban: str | None = None
    maskedPan: list[str] = Field(default_factory=list)


class MonoClientInfo(BaseModel):
    name: str | None = None
    accounts: list[MonoAccount] = Field(default_factory=list)