from datetime import UTC, datetime
from decimal import Decimal

from app.models import EntryDirection, LedgerEntry, OutboxEvent


def create_account(client, owner: str, balance: str = "0.00", currency: str = "EUR"):
    response = client.post(
        "/accounts",
        json={"owner_name": owner, "currency": currency, "opening_balance": balance},
    )
    assert response.status_code == 201
    return response.json()


def test_transfer_creates_balanced_entries_and_updates_balances(client, session):
    source = create_account(client, "Source", "100.00")
    destination = create_account(client, "Destination")

    response = client.post(
        "/transfers",
        headers={"Idempotency-Key": "transfer-0001"},
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": "35.50",
        },
    )

    assert response.status_code == 201
    entries = session.query(LedgerEntry).all()
    assert len(entries) == 2
    assert {entry.direction for entry in entries} == {
        EntryDirection.debit,
        EntryDirection.credit,
    }
    assert sum(
        entry.amount if entry.direction == EntryDirection.credit else -entry.amount
        for entry in entries
    ) == Decimal("0.00")
    assert client.get(f"/accounts/{source['id']}/balance").json()["balance"] == "64.50"
    assert client.get(f"/accounts/{destination['id']}/balance").json()["balance"] == "35.50"


def test_idempotency_key_prevents_duplicate_transfer(client, session):
    source = create_account(client, "Source", "100.00")
    destination = create_account(client, "Destination")
    payload = {
        "source_account_id": source["id"],
        "destination_account_id": destination["id"],
        "amount": "20.00",
    }
    headers = {"Idempotency-Key": "same-request-key"}

    first = client.post("/transfers", headers=headers, json=payload)
    second = client.post("/transfers", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert session.query(LedgerEntry).count() == 2
    event = session.query(OutboxEvent).one()
    assert event.event_type == "transfer.created"
    assert str(event.aggregate_id) == first.json()["id"]


def test_daily_volume_report_aggregates_transfers(client):
    source = create_account(client, "Source", "100.00")
    destination = create_account(client, "Destination")
    client.post(
        "/transfers",
        headers={"Idempotency-Key": "report-transfer-01"},
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": "25.00",
        },
    )

    today = datetime.now(UTC).date().isoformat()
    response = client.get(
        "/reports/daily-volume",
        params={"report_date": today, "currency": "eur"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "date": today,
        "currency": "EUR",
        "transfer_count": 1,
        "total_amount": "25.00",
    }


def test_transfer_rejects_insufficient_funds_without_entries(client, session):
    source = create_account(client, "Source", "10.00")
    destination = create_account(client, "Destination")

    response = client.post(
        "/transfers",
        headers={"Idempotency-Key": "insufficient-0001"},
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": "10.01",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Source account has insufficient funds"
    assert session.query(LedgerEntry).count() == 0


def test_transfer_rejects_currency_mismatch(client):
    source = create_account(client, "Source", "100.00", "EUR")
    destination = create_account(client, "Destination", "0.00", "USD")

    response = client.post(
        "/transfers",
        headers={"Idempotency-Key": "currency-0001"},
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "amount": "20.00",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Accounts must use the same currency"

