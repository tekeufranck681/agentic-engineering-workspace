from app.billing.models import Subscription, SubscriptionStatus
from app.billing.webhooks import on_payment_event


def test_confirmed_webhook_activates():
    sub = on_payment_event(Subscription("sub_1", "cus_1", "pro"), "pay_1", 2900, "CONFIRMED")
    assert sub.status is SubscriptionStatus.ACTIVE


def test_failed_webhook_does_not_activate():
    sub = on_payment_event(Subscription("sub_1", "cus_1", "pro"), "pay_1", 2900, "FAILED")
    assert sub.status is SubscriptionStatus.PENDING
