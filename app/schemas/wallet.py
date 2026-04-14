"""Wallet request/response schemas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class WalletResponse(BaseModel):
    wallet_balance: Decimal
    total_saved: Decimal
    total_withdrawn: Decimal
    wallet_activated: bool
    wallet_bypass: bool
    virtual_account_number: str | None = None
    virtual_account_bank: str | None = None

    model_config = {"from_attributes": True}


class VirtualAccountResponse(BaseModel):
    account_number: str
    bank_name: str
    reference: str

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    id: uuid.UUID
    txn_id: str
    amount: Decimal
    type: str
    category: str
    reference: str
    description: str
    status: str
    provider_reference: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
