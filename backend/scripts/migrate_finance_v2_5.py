import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import engine


def ensure_column(table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        print(f"{table_name}.{column_name} already exists")
        return

    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))
    print(f"added {table_name}.{column_name}")


def main() -> None:
    ensure_column("dishes", "cost_price", "cost_price DECIMAL(10, 2) NOT NULL DEFAULT 0")
    ensure_column("order_items", "cost_price", "cost_price DECIMAL(10, 2) NOT NULL DEFAULT 0")


if __name__ == "__main__":
    main()
