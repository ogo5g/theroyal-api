"""Abstract payment provider interface."""

from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentProvider(ABC):
    """
    All payment operations go through this interface.
    Never call a provider API directly from a router or model.
    """

    @abstractmethod
    async def create_virtual_account(
        self,
        email: str,
        first_name: str,
        last_name: str,
        phone: str | None = None,
        bvn: str | None = None,
    ) -> dict:
        """
        Create a virtual bank account for wallet funding.

        Returns:
            {
                "account_number": str,
                "bank_name": str,
                "reference": str,
            }
        """
        ...

    @abstractmethod
    async def verify_transaction(self, reference: str) -> dict:
        """
        Verify a transaction by its reference.

        Returns:
            {
                "reference": str,
                "amount": Decimal,
                "status": str,  # "success", "failed", "pending"
                "provider_reference": str,
                "metadata": dict,
            }
        """
        ...

    @abstractmethod
    async def initiate_transfer(
        self,
        amount: Decimal,
        bank_code: str,
        account_number: str,
        account_name: str,
        narration: str,
        reference: str,
    ) -> dict:
        """
        Initiate a bank transfer (payout).

        Returns:
            {
                "reference": str,
                "provider_reference": str,
                "status": str,
            }
        """
        ...

    @abstractmethod
    async def get_transaction(self, reference: str) -> dict:
        """
        Get transaction details by provider reference.

        Returns:
            {
                "reference": str,
                "amount": Decimal,
                "status": str,
                "metadata": dict,
            }
        """
        ...
