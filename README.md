# Transaction Ledger API

[![CI](https://github.com/oddinokiy/transaction-ledger-api/actions/workflows/ci.yml/badge.svg)](https://github.com/oddinokiy/transaction-ledger-api/actions/workflows/ci.yml)

A small financial ledger service built to demonstrate Python API development, relational data modelling, transactional consistency, idempotency, and automated testing.

## Engineering properties

- FastAPI request validation and generated OpenAPI documentation
- PostgreSQL in Docker Compose; SQLite only for isolated tests
- Double-entry ledger: each transfer creates one debit and one matching credit
- Atomic transfer creation with row locking on PostgreSQL
- Idempotency keys prevent duplicate transfers
- Currency and insufficient-funds validation
- Unit/integration tests and GitHub Actions

## Data model

```text
accounts 1 ---- * ledger_entries * ---- 1 transfers
```

The account balance is derived from immutable ledger entries plus the opening balance. A transfer is valid only when its debit and credit entries sum to zero.

## Run with Docker

```bash
docker compose up --build
```

OpenAPI documentation: `http://localhost:8000/docs`

## Example

Create two accounts:

```bash
curl -X POST http://localhost:8000/accounts \
  -H 'Content-Type: application/json' \
  -d '{"owner_name":"Alice","currency":"EUR","opening_balance":"100.00"}'
```

Create a transfer using the returned account IDs:

```bash
curl -X POST http://localhost:8000/transfers \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-transfer-0001' \
  -d '{"source_account_id":"SOURCE_UUID","destination_account_id":"DESTINATION_UUID","amount":"25.00"}'
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check .
pytest --cov=app
```

## Scope and limitations

This is a portfolio project, not a production payment system. It does not yet implement authentication, foreign exchange, asynchronous event delivery, Alembic migrations, or reconciliation. Those are explicit follow-up milestones rather than implied capabilities.
