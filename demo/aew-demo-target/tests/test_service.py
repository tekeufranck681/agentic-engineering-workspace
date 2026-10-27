"""Acceptance tests for REQ-001: activate only after payment confirmation."""

from datetime import datetime, timezone

import pytest

from app.billing.models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from app.billing.service import BillingService

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)


def pending_subscription() -> Subscription:
    return Subscription(subscription_id="sub_1", customer_id="cus_1", plan="pro")


@pytest.mark.parametrize("status", [PaymentStatus.FAILED, PaymentStatus.PENDING])
def test_ac_001_unconfirmed_payment_does_not_activate(status):
    sub = BillingService().activate(pending_subscription(), Payment("pay_1", 2900, status), now=NOW)
    assert sub.status is SubscriptionStatus.PENDING
    assert sub.activated_at is None


def test_ac_002_confirmed_payment_activates():
    sub = BillingService().activate(pending_subscription(), Payment("pay_1", 2900, PaymentStatus.CONFIRMED), now=NOW)
    assert sub.status is SubscriptionStatus.ACTIVE
    assert sub.activated_at == NOW


def test_an_active_subscription_keeps_its_first_activation_time():
    sub = BillingService().activate(pending_subscription(), Payment("pay_1", 2900, PaymentStatus.CONFIRMED), now=NOW)
    later = datetime(2026, 10, 28, tzinfo=timezone.utc)
    BillingService().activate(sub, Payment("pay_2", 2900, PaymentStatus.CONFIRMED), now=later)
    assert sub.activated_at == NOW
