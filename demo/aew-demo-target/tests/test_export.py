from app.billing.models import Subscription
from app.reporting.export import export_csv


def test_export():
    csv_text = export_csv([Subscription("sub_1", "cus_1", "pro")])
    assert csv_text == "subscription_id,customer_id,plan,status\nsub_1,cus_1,pro,PENDING\n"
