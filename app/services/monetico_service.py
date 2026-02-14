"""
Monetico payment service — STUB.

Prepares the integration with the Monetico bank payment API (CM-CIC).
For now, methods return placeholder data. The actual implementation will
plug into the real Monetico API using HMAC-SHA1 signatures.

Configuration (in .env, not yet required):
    MONETICO_TPE          — Terminal number (e.g. "1234567")
    MONETICO_COMPANY_CODE — Company code (e.g. "nomadays")
    MONETICO_HMAC_KEY     — HMAC key (40-char hex from the Monetico back-office)
    MONETICO_URL          — Payment gateway URL
                            sandbox: https://p.monetico-services.com/test/paiement.cgi
                            prod:    https://p.monetico-services.com/paiement.cgi
"""

import hashlib
import hmac
import os
from datetime import datetime
from typing import Optional


class MoneticoService:
    """Monetico payment gateway service (stub implementation)."""

    def __init__(self):
        self.tpe = os.getenv("MONETICO_TPE", "")
        self.company_code = os.getenv("MONETICO_COMPANY_CODE", "")
        self.hmac_key = os.getenv("MONETICO_HMAC_KEY", "")
        self.gateway_url = os.getenv(
            "MONETICO_URL",
            "https://p.monetico-services.com/test/paiement.cgi",
        )

    @property
    def is_configured(self) -> bool:
        """Check if Monetico credentials are set."""
        return bool(self.tpe and self.company_code and self.hmac_key)

    def create_payment_request(
        self,
        amount: float,
        currency: str,
        reference: str,
        return_url: str,
        cancel_url: str,
        notify_url: Optional[str] = None,
    ) -> dict:
        """
        Create a Monetico payment request.

        In production, this will build the signed form data and return
        the payment gateway URL. For now, returns a placeholder.

        Args:
            amount: Payment amount (e.g. 1500.00)
            currency: ISO 4217 currency code (e.g. "EUR")
            reference: Unique payment reference (e.g. "FA-2026-0042-deposit")
            return_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
            notify_url: Webhook URL for server-to-server notification

        Returns:
            dict with payment_url and payment_id
        """
        if not self.is_configured:
            # Stub: return placeholder
            return {
                "payment_url": None,
                "payment_id": f"stub-{reference}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "status": "stub",
                "message": "Monetico non configuré — paiement en ligne bientôt disponible",
            }

        # ── Real implementation (to be completed) ──
        # Build the MAC seal, construct the payment form, and return the URL.
        # For now, even with credentials, return stub.
        return {
            "payment_url": None,
            "payment_id": f"monetico-{reference}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "status": "stub",
            "message": "Monetico configuré mais pas encore implémenté",
        }

    def verify_payment_response(self, data: dict, received_seal: str) -> bool:
        """
        Verify the HMAC seal on a Monetico payment response (webhook).

        This uses the HMAC-SHA1 algorithm as specified in the Monetico docs.
        The seal is computed over specific fields in a defined order.

        Args:
            data: Monetico response data (from POST webhook)
            received_seal: The MAC value sent by Monetico

        Returns:
            True if the seal is valid
        """
        if not self.hmac_key:
            # Stub: always accept (for testing)
            return True

        expected_seal = self._compute_seal(data)
        return hmac.compare_digest(expected_seal, received_seal.lower())

    def _compute_seal(self, fields: dict) -> str:
        """
        Compute the HMAC-SHA1 seal for Monetico data.

        According to Monetico specs:
        1. Concatenate fields in the defined order with '*'
        2. Compute HMAC-SHA1 with the secret key
        3. Return lowercase hex digest
        """
        # Field order as per Monetico specification
        ordered_keys = [
            "TPE", "date", "montant", "reference",
            "texte-libre", "version", "lgue", "societe",
            "mail", "nbrech", "dateech1", "montantech1",
            "dateech2", "montantech2", "dateech3", "montantech3",
            "dateech4", "montantech4",
        ]

        parts = []
        for key in ordered_keys:
            parts.append(f"{key}={fields.get(key, '')}")
        data_string = "*".join(parts)

        # Decode the hex key
        try:
            key_bytes = bytes.fromhex(self.hmac_key)
        except ValueError:
            key_bytes = self.hmac_key.encode("utf-8")

        mac = hmac.new(key_bytes, data_string.encode("utf-8"), hashlib.sha1)
        return mac.hexdigest().lower()


# Singleton
monetico_service = MoneticoService()
