"""Payment provider webhooks (ADR-001: activate from the payment webhook)."""

from app.billing.models import Payment, PaymentStatus, Subscription
from app.billing.service import BillingService


def on_payment_event(subscription: Subscription, payment_id: str, amount_cents: int, status: str,
                     service: BillingService | None = None) -> Subscription:
    """Handle POST /webhooks/payments (CON-001)."""
    payment = Payment(payment_id=payment_id, amount_cents=amount_cents, status=PaymentStatus(status))
    return (service or BillingService()).activate(subscription, payment)
