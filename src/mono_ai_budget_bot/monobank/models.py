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


class MonoStatementItem(BaseModel):
    id: str
    time: int
    description: str | None = None
    mcc: int | None = None
    originalMcc: int | None = None
    amount: int
    operationAmount: int | None = None
    currencyCode: int | None = None
    commissionRate: int | None = None
    cashbackAmount: int | None = None
    balance: int | None = None
    hold: bool | None = None
    counterEdrpou: str | None = None
    counterIban: str | None = None
