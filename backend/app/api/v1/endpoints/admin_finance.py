from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import Admin, Dish, Order, OrderItem, OrderStatus
from app.schemas.admin_finance import (
    ReconciliationDailyOut,
    ReconciliationDishOut,
    ReconciliationReportOut,
    ReconciliationSummaryOut,
)
from app.schemas.response import ResponseModel
from app.utils.timezone import now_china, today_china


router = APIRouter()

PAID_ORDER_STATUSES = {
    OrderStatus.confirmed,
    OrderStatus.delivering,
    OrderStatus.completed,
}


def _amount(value) -> Decimal:
    return Decimal(str(value or "0.00")).quantize(Decimal("0.01"))


def _money(value: Decimal) -> str:
    return str(_amount(value))


def _rate(part: Decimal, total: Decimal) -> str:
    if total <= 0:
        return "0.00"
    return str(((part / total) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _empty_money_row(target_date: date) -> dict:
    return {
        "date": target_date,
        "order_count": 0,
        "item_count": 0,
        "revenue_amount": Decimal("0.00"),
        "cost_amount": Decimal("0.00"),
        "profit_amount": Decimal("0.00"),
        "discount_amount": Decimal("0.00"),
    }


def _item_unit_cost(item: OrderItem, dish_lookup: dict[int, Dish]) -> tuple[Decimal, bool]:
    cost = _amount(getattr(item, "cost_price", Decimal("0.00")))
    if cost > 0:
        return cost, False

    dish = dish_lookup.get(int(item.dish_id))
    if dish:
        cost = _amount(getattr(dish, "cost_price", Decimal("0.00")))

    return cost, cost <= 0


@router.get("/reconciliation", response_model=ResponseModel[ReconciliationReportOut])
async def get_reconciliation_report(
    days: int = Query(7, ge=1, le=31),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if start_date:
        target_start = start_date
        target_end = end_date or today_china()
        if target_start > target_end:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
        range_days = (target_end - target_start).days + 1
        if range_days > 366:
            raise HTTPException(status_code=400, detail="自定义统计范围不能超过 366 天")
    else:
        target_end = end_date or today_china()
        target_start = target_end - timedelta(days=days - 1)
        range_days = days

    orders = (
        db.query(Order)
        .filter(
            Order.delivery_date >= target_start,
            Order.delivery_date <= target_end,
            Order.status.in_(PAID_ORDER_STATUSES),
            Order.paid_at.isnot(None),
        )
        .order_by(Order.delivery_date.asc(), Order.created_at.asc(), Order.id.asc())
        .all()
    )
    order_ids = [order.id for order in orders]
    order_items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id.in_(order_ids))
        .order_by(OrderItem.id.asc())
        .all()
        if order_ids
        else []
    )
    dish_ids = {int(item.dish_id) for item in order_items if item.dish_id is not None}
    dish_lookup = {
        int(dish.id): dish
        for dish in (db.query(Dish).filter(Dish.id.in_(dish_ids)).all() if dish_ids else [])
    }

    items_by_order: dict[int, list[OrderItem]] = defaultdict(list)
    for item in order_items:
        items_by_order[int(item.order_id)].append(item)

    daily_map = {
        target_start + timedelta(days=offset): _empty_money_row(target_start + timedelta(days=offset))
        for offset in range(range_days)
    }
    dish_map: dict[tuple[int | None, str], dict] = {}

    product_amount = Decimal("0.00")
    delivery_fee = Decimal("0.00")
    discount_amount = Decimal("0.00")
    revenue_amount = Decimal("0.00")
    cost_amount = Decimal("0.00")
    item_count = 0
    missing_cost_items = 0

    for order in orders:
        day = daily_map.setdefault(order.delivery_date, _empty_money_row(order.delivery_date))
        order_revenue = _amount(order.actual_amount)
        order_discount = _amount(getattr(order, "discount_amount", Decimal("0.00")))
        order_items_for_report = items_by_order.get(int(order.id), [])

        product_amount += _amount(order.total_amount)
        delivery_fee += _amount(order.delivery_fee)
        discount_amount += order_discount
        revenue_amount += order_revenue

        day["order_count"] += 1
        day["revenue_amount"] += order_revenue
        day["discount_amount"] += order_discount

        for item in order_items_for_report:
            quantity = int(item.quantity or 0)
            unit_cost, cost_missing = _item_unit_cost(item, dish_lookup)
            item_cost = (unit_cost * quantity).quantize(Decimal("0.01"))
            item_sales = _amount(item.subtotal)
            item_profit = item_sales - item_cost
            item_count += quantity
            cost_amount += item_cost
            day["item_count"] += quantity
            day["cost_amount"] += item_cost
            day["profit_amount"] += item_profit
            if cost_missing:
                missing_cost_items += quantity

            dish_key = (int(item.dish_id) if item.dish_id is not None else None, item.dish_name)
            if dish_key not in dish_map:
                dish_map[dish_key] = {
                    "dish_id": dish_key[0],
                    "dish_name": item.dish_name,
                    "quantity": 0,
                    "sales_amount": Decimal("0.00"),
                    "cost_amount": Decimal("0.00"),
                    "profit_amount": Decimal("0.00"),
                    "missing_cost_items": 0,
                }
            dish_row = dish_map[dish_key]
            dish_row["quantity"] += quantity
            dish_row["sales_amount"] += item_sales
            dish_row["cost_amount"] += item_cost
            dish_row["profit_amount"] += item_profit
            if cost_missing:
                dish_row["missing_cost_items"] += quantity

    profit_amount = revenue_amount - cost_amount
    gross_amount = product_amount + delivery_fee
    average_order_amount = revenue_amount / len(orders) if orders else Decimal("0.00")

    daily_rows = []
    for row in sorted(daily_map.values(), key=lambda item: item["date"]):
        row_profit = row["revenue_amount"] - row["cost_amount"]
        daily_rows.append(
            ReconciliationDailyOut(
                date=row["date"],
                order_count=row["order_count"],
                item_count=row["item_count"],
                revenue_amount=_money(row["revenue_amount"]),
                cost_amount=_money(row["cost_amount"]),
                profit_amount=_money(row_profit),
                discount_amount=_money(row["discount_amount"]),
            )
        )

    dish_rows = [
        ReconciliationDishOut(
            dish_id=row["dish_id"],
            dish_name=row["dish_name"],
            quantity=row["quantity"],
            sales_amount=_money(row["sales_amount"]),
            cost_amount=_money(row["cost_amount"]),
            profit_amount=_money(row["profit_amount"]),
            missing_cost_items=row["missing_cost_items"],
        )
        for row in sorted(
            dish_map.values(),
            key=lambda item: (item["profit_amount"], item["sales_amount"], item["quantity"]),
            reverse=True,
        )
    ]

    return ResponseModel(
        data=ReconciliationReportOut(
            generated_at=now_china().isoformat(),
            summary=ReconciliationSummaryOut(
                start_date=target_start,
                end_date=target_end,
                order_count=len(orders),
                item_count=item_count,
                gross_amount=_money(gross_amount),
                product_amount=_money(product_amount),
                delivery_fee=_money(delivery_fee),
                discount_amount=_money(discount_amount),
                revenue_amount=_money(revenue_amount),
                cost_amount=_money(cost_amount),
                profit_amount=_money(profit_amount),
                profit_rate=_rate(profit_amount, revenue_amount),
                average_order_amount=_money(average_order_amount),
                missing_cost_items=missing_cost_items,
            ),
            daily_rows=daily_rows,
            dish_rows=dish_rows,
        )
    )
