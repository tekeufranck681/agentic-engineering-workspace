"""Billing domain objects (TASK-001: subscription model with a PENDING status)."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SubscriptionStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


@dataclass
class Payment:
    payment_id: str
    amount_cents: int
    status: PaymentStatus


@dataclass
class Subscription:
    subscription_id: str
    customer_id: str
    plan: str
    status: SubscriptionStatus = SubscriptionStatus.PENDING
    activated_at: datetime | None = None
