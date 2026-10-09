from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas import (
    AccountCreate,
    AccountRead,
    BalanceRead,
    DailyVolumeRead,
    TransferCreate,
    TransferRead,
)
from app.service import (
    AccountNotFound,
    CurrencyMismatch,
    InsufficientFunds,
    LedgerError,
    account_balance,
    create_account,
    create_transfer,
    daily_volume,
    get_account,
)

app = FastAPI(
    title="Transaction Ledger API",
    version="0.1.0",
    description="A double-entry ledger demonstrating transactional API design and idempotency.",
)

SessionDependency = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def post_account(payload: AccountCreate, session: SessionDependency) -> AccountRead:
    return AccountRead.model_validate(create_account(session, payload))


@app.get("/accounts/{account_id}/balance", response_model=BalanceRead)
def get_balance(account_id: UUID, session: SessionDependency) -> BalanceRead:
    try:
        account = get_account(session, account_id)
    except AccountNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return BalanceRead(
        account_id=account.id,
        currency=account.currency,
        balance=account_balance(session, account),
    )


@app.post("/transfers", response_model=TransferRead, status_code=status.HTTP_201_CREATED)
def post_transfer(
    payload: TransferCreate,
    session: SessionDependency,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=128)],
) -> TransferRead:
    try:
        transfer = create_transfer(session, payload, idempotency_key)
    except AccountNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (CurrencyMismatch, InsufficientFunds, LedgerError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return TransferRead.model_validate(transfer)


@app.get("/reports/daily-volume", response_model=DailyVolumeRead)
def get_daily_volume(
    report_date: date,
    currency: str,
    session: SessionDependency,
) -> DailyVolumeRead:
    transfer_count, total_amount = daily_volume(session, report_date, currency)
    return DailyVolumeRead(
        date=report_date.isoformat(),
        currency=currency.upper(),
        transfer_count=transfer_count,
        total_amount=total_amount,
    )

