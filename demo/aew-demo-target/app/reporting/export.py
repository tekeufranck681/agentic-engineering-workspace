"""CSV export of subscriptions (unrelated to REQ-001)."""

import csv
import io

from app.billing.models import Subscription


def export_csv(subscriptions: list[Subscription]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["subscription_id", "customer_id", "plan", "status"])
    for s in subscriptions:
        writer.writerow([s.subscription_id, s.customer_id, s.plan, s.status.value])
    return out.getvalue()
