from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.base import SessionLocal
from app.models import Order
from app.api.v1.endpoints.payment import _mark_order_paid
from app.services.wechat_pay import get_wechat_pay_mode, is_wechat_pay_real_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Check or advance local payment state for a single order")
    parser.add_argument("order_no", help="Target order number")
    parser.add_argument("--mock-pay", action="store_true", help="Mark the order paid via local mock finalization")
    parser.add_argument("--transaction-id", default="", help="Optional transaction id for mock pay")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.order_no == args.order_no).first()
        if not order:
            print(f"[ERROR] Order not found: {args.order_no}")
            return

        print(f"[INFO] payment_mode={get_wechat_pay_mode()}")
        print(f"[INFO] order_no={order.order_no}")
        print(f"[INFO] status={order.status.value if hasattr(order.status, 'value') else order.status}")
        print(f"[INFO] actual_amount={order.actual_amount}")
        print(f"[INFO] transaction_id={order.transaction_id or '-'}")
        print(f"[INFO] paid_at={order.paid_at or '-'}")

        if not args.mock_pay:
            return

        if is_wechat_pay_real_mode():
            print("[ERROR] Current mode is real. Refusing to perform mock payment finalization.")
            return

        txid = args.transaction_id or f"local_mock_{int(datetime.now().timestamp())}"
        success, error = _mark_order_paid(order, txid, datetime.now(), db)
        if not success:
            print(f"[ERROR] Payment finalization failed: {error}")
            return

        print("[OK] Mock payment finalization succeeded.")
        print(f"[INFO] new_status={order.status.value if hasattr(order.status, 'value') else order.status}")
        print(f"[INFO] transaction_id={order.transaction_id}")
        print(f"[INFO] paid_at={order.paid_at}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
