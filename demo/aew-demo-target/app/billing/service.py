"""Subscription activation (REQ-001, TASK-002)."""

from datetime import datetime, timezone

from app.billing.models import Payment, PaymentStatus, Subscription, SubscriptionStatus


class BillingService:
    def activate(self, subscription: Subscription, payment: Payment, now: datetime | None = None) -> Subscription:
        """Activate the subscription for this payment.

        REQ-001: a subscription becomes ACTIVE only when its payment is confirmed.
        """
        if subscription.status is SubscriptionStatus.ACTIVE:
            return subscription
        if payment.status is PaymentStatus.FAILED:
            return subscription
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.activated_at = now or datetime.now(timezone.utc)
        return subscription
