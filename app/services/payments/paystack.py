"""Paystack provider implementation for public APIs."""

import json

import httpx

from app.config import settings

class PaystackProvider:
    """Paystack API integration for bank listing and account verification."""

    def __init__(self):
        self.base_url = "https://api.paystack.co"
        self.secret_key = settings.PAYSTACK_SECRET_KEY

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.secret_key:
            headers["Authorization"] = f"Bearer {self.secret_key}"
        return headers

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated request to Paystack API."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method, url, headers=self._headers(), **kwargs
            )
            response.raise_for_status()
            return response.json()

    async def list_banks(self) -> list[dict]:
        """Fetch list of banks (Nigeria)."""
        # GET /bank?country=nigeria
        params = {"country": "nigeria"}
        data = await self._request("GET", "/bank", params=params)
        return data.get("data", [])

    async def resolve_account(self, account_number: str, bank_code: str) -> dict:
        """Resolve an account number into an account name."""
        # GET /bank/resolve?account_number=0001234567&bank_code=058
        params = {
            "account_number": account_number,
            "bank_code": bank_code,
        }
        data = await self._request("GET", "/bank/resolve", params=params)
        result = data.get("data", {})
        
        return {
            "account_name": result.get("account_name", ""),
            "account_number": result.get("account_number", ""),
            "bank_code": bank_code,
        }

paystack = PaystackProvider()
