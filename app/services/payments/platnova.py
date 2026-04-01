"""Platnova payment provider implementation."""

from decimal import Decimal

import httpx

from app.config import settings
from app.services.payments.base import PaymentProvider


class PlatnovaProvider(PaymentProvider):
    """Platnova API integration for virtual accounts, verification, and transfers."""

    def __init__(self):
        self.base_url = settings.PLATNOVA_BASE_URL.rstrip("/")
        self.api_key = settings.PLATNOVA_API_KEY
        self.wallet_id = settings.PLATNOVA_WALLET_ID

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated request to Platnova API."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method, url, headers=self._headers(), **kwargs
            )
            response.raise_for_status()
            return response.json()

    async def create_virtual_account(
        self,
        email: str,
        first_name: str,
        last_name: str,
        phone: str | None = None,
        bvn: str | None = None,
    ) -> dict:
        """Create a Platnova virtual account for a user."""
        payload = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone or "",
            "bvn": bvn or "",
        }

        data = await self._request("POST", "/v1/virtual-accounts", json=payload)

        # Normalize response to our interface contract
        account_data = data.get("data", data)
        return {
            "account_number": account_data.get("account_number", ""),
            "bank_name": account_data.get("bank_name", ""),
            "reference": account_data.get("reference", ""),
        }

    async def verify_transaction(self, reference: str) -> dict:
        """Verify a transaction status with Platnova."""
        data = await self._request("GET", f"/v1/transactions/verify/{reference}")

        txn = data.get("data", data)
        return {
            "reference": reference,
            "amount": Decimal(str(txn.get("amount", 0))),
            "status": txn.get("status", "pending"),
            "provider_reference": txn.get("provider_reference", txn.get("id", "")),
            "metadata": txn,
        }

    async def initiate_transfer(
        self,
        amount: Decimal,
        bank_code: str,
        account_number: str,
        account_name: str,
        narration: str,
        reference: str,
    ) -> dict:
        """Initiate a bank transfer (payout) via Platnova."""
        payload = {
            "amount": float(amount),
            "bank_code": bank_code,
            "account_number": account_number,
            "account_name": account_name,
            "narration": narration,
            "reference": reference,
            "wallet_id": self.wallet_id,
            "currency": "NGN",
        }

        data = await self._request("POST", "/v1/transfers", json=payload)

        transfer = data.get("data", data)
        return {
            "reference": reference,
            "provider_reference": transfer.get("id", ""),
            "status": transfer.get("status", "pending"),
        }

    async def get_transaction(self, reference: str) -> dict:
        """Get transaction details from Platnova."""
        data = await self._request("GET", f"/v1/transactions/{reference}")

        txn = data.get("data", data)
        return {
            "reference": reference,
            "amount": Decimal(str(txn.get("amount", 0))),
            "status": txn.get("status", "pending"),
            "metadata": txn,
        }


# Singleton instance
platnova = PlatnovaProvider()
