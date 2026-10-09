from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountCreate(BaseModel):
    owner_name: str = Field(min_length=1, max_length=120)
    currency: str = Field(min_length=3, max_length=3)
    opening_balance: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)

    @field_validator("currency")
    @classmethod
    def normalise_currency(cls, value: str) -> str:
        return value.upper()


class AccountRead(BaseModel):
    id: UUID
    owner_name: str
    currency: str
    opening_balance: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BalanceRead(BaseModel):
    account_id: UUID
    currency: str
    balance: Decimal


class TransferCreate(BaseModel):
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=2)


class TransferRead(BaseModel):
    id: UUID
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    currency: str
    idempotency_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

