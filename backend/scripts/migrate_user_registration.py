from sqlalchemy import inspect, text

from app.db.base import engine


def _default_registered_expression(dialect_name: str) -> str:
    nickname_check = "nickname IS NOT NULL AND nickname != '' AND nickname NOT LIKE '微信用户%'"
    if dialect_name == "sqlite":
        return f"CASE WHEN {nickname_check} THEN 1 ELSE 0 END"
    return f"CASE WHEN {nickname_check} THEN TRUE ELSE FALSE END"


def main() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    dialect_name = engine.dialect.name

    with engine.begin() as conn:
        if "is_registered" not in columns:
            if dialect_name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN is_registered BOOLEAN NOT NULL DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_registered BOOLEAN NOT NULL DEFAULT FALSE"))

        if "registered_at" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN registered_at TIMESTAMP NULL"))

        conn.execute(
            text(
                "UPDATE users "
                f"SET is_registered = {_default_registered_expression(dialect_name)} "
                "WHERE is_registered IS NULL OR is_registered = 0"
            )
        )
        conn.execute(
            text(
                "UPDATE users "
                "SET registered_at = COALESCE(registered_at, updated_at, created_at) "
                "WHERE is_registered = 1"
            )
        )
        conn.execute(
            text(
                "UPDATE users "
                "SET public_uid = NULL "
                "WHERE is_registered = 0 AND nickname LIKE '微信用户%'"
            )
        )


if __name__ == "__main__":
    main()
