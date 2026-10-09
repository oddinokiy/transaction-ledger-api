from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Account, EntryDirection, LedgerEntry, OutboxEvent, Transfer
from app.schemas import AccountCreate, TransferCreate


class LedgerError(Exception):
    pass


class AccountNotFound(LedgerError):
    pass


class CurrencyMismatch(LedgerError):
    pass


class InsufficientFunds(LedgerError):
    pass


def create_account(session: Session, payload: AccountCreate) -> Account:
    account = Account(**payload.model_dump())
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def account_balance(session: Session, account: Account) -> Decimal:
    signed_amount = case(
        (LedgerEntry.direction == EntryDirection.credit, LedgerEntry.amount),
        else_=-LedgerEntry.amount,
    )
    movement = session.scalar(
        select(func.coalesce(func.sum(signed_amount), 0)).where(
            LedgerEntry.account_id == account.id
        )
    )
    return Decimal(account.opening_balance) + Decimal(movement)


def create_transfer(
    session: Session,
    payload: TransferCreate,
    idempotency_key: str,
) -> Transfer:
    existing = session.scalar(
        select(Transfer).where(Transfer.idempotency_key == idempotency_key)
    )
    if existing:
        return existing

    if payload.source_account_id == payload.destination_account_id:
        raise LedgerError("Source and destination accounts must be different")

    accounts = session.scalars(
        select(Account)
        .where(Account.id.in_([payload.source_account_id, payload.destination_account_id]))
        .with_for_update()
    ).all()
    by_id = {account.id: account for account in accounts}

    if len(by_id) != 2:
        raise AccountNotFound("One or both accounts do not exist")

    source = by_id[payload.source_account_id]
    destination = by_id[payload.destination_account_id]
    if source.currency != destination.currency:
        raise CurrencyMismatch("Accounts must use the same currency")
    if account_balance(session, source) < payload.amount:
        raise InsufficientFunds("Source account has insufficient funds")

    transfer = Transfer(
        source_account_id=source.id,
        destination_account_id=destination.id,
        amount=payload.amount,
        currency=source.currency,
        idempotency_key=idempotency_key,
    )
    transfer.entries = [
        LedgerEntry(account_id=source.id, direction=EntryDirection.debit, amount=payload.amount),
        LedgerEntry(
            account_id=destination.id,
            direction=EntryDirection.credit,
            amount=payload.amount,
        ),
    ]
    session.add(transfer)
    session.flush()
    session.add(
        OutboxEvent(
            event_type="transfer.created",
            aggregate_id=transfer.id,
            payload={
                "transfer_id": str(transfer.id),
                "source_account_id": str(source.id),
                "destination_account_id": str(destination.id),
                "amount": str(payload.amount),
                "currency": source.currency,
            },
        )
    )
    session.commit()
    session.refresh(transfer)
    return transfer


def get_account(session: Session, account_id: UUID) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise AccountNotFound("Account does not exist")
    return account


def daily_volume(session: Session, report_date: date, currency: str) -> tuple[int, Decimal]:
    start = datetime.combine(report_date, time.min)
    end = start + timedelta(days=1)
    count, total = session.execute(
        select(func.count(Transfer.id), func.coalesce(func.sum(Transfer.amount), 0)).where(
            Transfer.currency == currency.upper(),
            Transfer.created_at >= start,
            Transfer.created_at < end,
        )
    ).one()
    return int(count), Decimal(total)

