from datetime import date

from pydantic import BaseModel


class ReconciliationSummaryOut(BaseModel):
    start_date: date
    end_date: date
    order_count: int
    item_count: int
    gross_amount: str
    product_amount: str
    delivery_fee: str
    discount_amount: str
    revenue_amount: str
    cost_amount: str
    profit_amount: str
    profit_rate: str
    average_order_amount: str
    missing_cost_items: int


class ReconciliationDailyOut(BaseModel):
    date: date
    order_count: int
    item_count: int
    revenue_amount: str
    cost_amount: str
    profit_amount: str
    discount_amount: str


class ReconciliationDishOut(BaseModel):
    dish_id: int | None = None
    dish_name: str
    quantity: int
    sales_amount: str
    cost_amount: str
    profit_amount: str
    missing_cost_items: int = 0


class ReconciliationReportOut(BaseModel):
    generated_at: str
    summary: ReconciliationSummaryOut
    daily_rows: list[ReconciliationDailyOut]
    dish_rows: list[ReconciliationDishOut]
