from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.base import Base, SessionLocal, engine
from app.models import Admin, AdminRole, Category, Dish, SystemConfig
from app.core.security import get_password_hash


def upsert_config(db: Session, key: str, value: str, description: str) -> None:
    config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if config:
        config.config_value = value
        config.description = description
        return

    db.add(SystemConfig(config_key=key, config_value=value, description=description))


def seed_base_data(db: Session) -> None:
    configs = [
        ("lunch_deadline", "10:00", "午餐预订截止时间"),
        ("dinner_deadline", "16:00", "晚餐预订截止时间"),
        ("payment_timeout", "15", "支付超时关闭分钟数"),
        ("base_delivery_fee", "1", "非会员基础配送费"),
    ]
    for key, value, description in configs:
        upsert_config(db, key, value, description)

    category_names = [
        ("木子鸡", 10),
        ("烧腊", 20),
        ("凉皮", 30),
        ("黑金卤肉饭", 40),
        ("西式简餐", 50),
    ]
    category_map: dict[str, Category] = {}

    for name, sort_order in category_names:
        category = db.query(Category).filter(Category.name == name).first()
        if not category:
            category = Category(name=name, sort_order=sort_order, is_active=True)
            db.add(category)
            db.flush()
        else:
            category.sort_order = sort_order
            category.is_active = True
        category_map[name] = category

    dishes = [
        ("炸鸡腿", "木子鸡", Decimal("6.00"), "外脆里嫩，现炸出餐。", "fried-drumstick.jpg"),
        ("小木子鸡", "木子鸡", Decimal("8.90"), "经典木子鸡，小份刚刚好。", "muziji-small-rice.jpg"),
        ("豪华木子鸡", "木子鸡", Decimal("12.00"), "加量升级，满足感更强。", "muziji-deluxe-rice.jpg"),
        ("肉排双拼", "木子鸡", Decimal("17.00"), "双拼组合，一次满足两种口感。", "double-pork-cutlet.jpg"),
        ("蜜汁鸡腿", "烧腊", Decimal("6.00"), "蜜汁入味，鸡腿肉扎实。", "honey-drumstick.jpg"),
        ("烧鸭饭", "烧腊", Decimal("13.90"), "皮香肉嫩，酱汁入味。", "roast-duck-rice.jpg"),
        ("猪肘饭", "烧腊", Decimal("18.00"), "猪肘软糯，配饭浓香。", "pork-knuckle-rice.jpg"),
        ("叉烧饭", "烧腊", Decimal("19.80"), "秘制叉烧，鲜香入味。", "char-siu-rice.jpg"),
        ("烧鸭叉烧双拼", "烧腊", Decimal("19.80"), "烧鸭与叉烧双拼，经典组合。", "duck-char-siu-combo-rice.jpg"),
        ("猪肘叉烧双拼", "烧腊", Decimal("19.80"), "猪肘和叉烧双拼，口味更丰富。", "knuckle-char-siu-combo.jpg"),
        ("烧鸭猪肘双拼", "烧腊", Decimal("19.80"), "烧鸭搭配猪肘，一份吃到两种招牌。", "duck-knuckle-combo.jpg"),
        ("招牌凉皮", "凉皮", Decimal("10.00"), "清爽开胃，拌好即食。", "cold-noodle-signature.jpg"),
        ("鸡丝凉皮", "凉皮", Decimal("14.00"), "加量鸡丝，口感更足。", "cold-noodle-chicken.jpg"),
        ("麻酱凉皮", "凉皮", Decimal("12.00"), "麻酱浓香，口感筋道。", "cold-noodle-sesame.jpg"),
        ("牛肉凉皮", "凉皮", Decimal("16.00"), "牛肉搭配凉皮，清爽又顶饱。", "cold-noodle-beef.jpg"),
        ("黑金卤肉饭", "黑金卤肉饭", Decimal("17.00"), "黑金慢卤，咸香入味。", "black-gold-braised-pork-rice.jpg"),
        ("意大利面", "西式简餐", Decimal("16.80"), "酱香浓郁，适合作为热食正餐。", "pasta.jpg"),
        ("美式烤鸡(半只)", "西式简餐", Decimal("15.00"), "半只烤鸡份量足，适合加餐分享。", "half-roast-chicken.jpg"),
    ]
    for index, (name, category_name, price, description, image_name) in enumerate(dishes, start=1):
        dish = db.query(Dish).filter(Dish.name == name).first()
        if dish:
            dish.category_id = category_map[category_name].id
            dish.description = description
            dish.detail_content = description
            dish.image_url = f"https://sydroo.top/uploads/miniapp-assets/menu/{image_name}"
            dish.price = price
            dish.stock = 120
            dish.sort_order = index * 10
            dish.is_active = True
            dish.is_sold_out = False
            continue

        db.add(
            Dish(
                category_id=category_map[category_name].id,
                name=name,
                description=description,
                detail_content=description,
                image_url=f"https://sydroo.top/uploads/miniapp-assets/menu/{image_name}",
                price=price,
                stock=120,
                sort_order=index * 10,
                is_active=True,
                is_sold_out=False,
            )
        )


def seed_admin(db: Session) -> None:
    admin = db.query(Admin).filter(Admin.username == "admin").first()
    hashed_password = get_password_hash("Dymc12138")
    if admin:
        admin.password = hashed_password
        admin.real_name = "默认管理员"
        admin.role = AdminRole.super_admin
        admin.is_active = True
        return

    db.add(
        Admin(
            username="admin",
            password=hashed_password,
            real_name="默认管理员",
            role=AdminRole.super_admin,
            is_active=True,
        )
    )


def ensure_dish_schema(db: Session) -> None:
    existing_columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(dishes)")).fetchall()
    }

    if "detail_content" not in existing_columns:
        db.execute(text("ALTER TABLE dishes ADD COLUMN detail_content TEXT"))
        db.execute(text("UPDATE dishes SET detail_content = COALESCE(description, '') WHERE detail_content IS NULL"))

    if "is_sold_out" not in existing_columns:
        db.execute(text("ALTER TABLE dishes ADD COLUMN is_sold_out BOOLEAN DEFAULT 0"))
        db.execute(text("UPDATE dishes SET is_sold_out = 0 WHERE is_sold_out IS NULL"))

    db.commit()


def ensure_user_schema(db: Session) -> None:
    existing_columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(users)")).fetchall()
    }

    column_sql = {
        "public_uid": "ALTER TABLE users ADD COLUMN public_uid VARCHAR(32)",
        "is_member": "ALTER TABLE users ADD COLUMN is_member BOOLEAN DEFAULT 0 NOT NULL",
        "invite_code": "ALTER TABLE users ADD COLUMN invite_code VARCHAR(5)",
        "invited_by_user_id": "ALTER TABLE users ADD COLUMN invited_by_user_id INTEGER",
        "points": "ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0 NOT NULL",
        "total_spent": "ALTER TABLE users ADD COLUMN total_spent DECIMAL(10, 2) DEFAULT 0 NOT NULL",
        "member_joined_at": "ALTER TABLE users ADD COLUMN member_joined_at TIMESTAMP",
    }
    for column, sql in column_sql.items():
        if column not in existing_columns:
            db.execute(text(sql))

    db.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_public_uid_unique "
            "ON users(public_uid) WHERE public_uid IS NOT NULL AND public_uid != ''"
        )
    )
    db.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_invite_code_unique "
            "ON users(invite_code) WHERE invite_code IS NOT NULL AND invite_code != ''"
        )
    )
    db.commit()


def ensure_user_coupon_schema(db: Session) -> None:
    existing_columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(user_coupons)")).fetchall()
    }

    if "locked_order_id" not in existing_columns:
        db.execute(text("ALTER TABLE user_coupons ADD COLUMN locked_order_id INTEGER"))

    db.commit()


def ensure_order_schema(db: Session) -> None:
    existing_columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(orders)")).fetchall()
    }

    if "discount_amount" not in existing_columns:
        db.execute(text("ALTER TABLE orders ADD COLUMN discount_amount DECIMAL(10, 2) DEFAULT 0"))
        db.execute(text("UPDATE orders SET discount_amount = 0 WHERE discount_amount IS NULL"))

    if "coupon_id" not in existing_columns:
        db.execute(text("ALTER TABLE orders ADD COLUMN coupon_id INTEGER"))

    if "idempotency_key" not in existing_columns:
        db.execute(text("ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR(64)"))

    db.commit()

    existing_columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(orders)")).fetchall()
    }

    if "spend_counted_at" not in existing_columns:
        db.execute(text("ALTER TABLE orders ADD COLUMN spend_counted_at TIMESTAMP"))
        db.execute(
            text(
                """
                UPDATE orders
                SET spend_counted_at = paid_at
                WHERE paid_at IS NOT NULL
                  AND status != 'closed'
                  AND spend_counted_at IS NULL
                """
            )
        )

    db.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_transaction_id_unique "
            "ON orders(transaction_id) WHERE transaction_id IS NOT NULL AND transaction_id != ''"
        )
    )
    db.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_user_idempotency_key_unique "
            "ON orders(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key != ''"
        )
    )

    db.execute(
        text(
            """
            UPDATE users
            SET total_spent = COALESCE((
                SELECT SUM(orders.actual_amount)
                FROM orders
                WHERE orders.user_id = users.id
                  AND orders.paid_at IS NOT NULL
                  AND orders.status != 'closed'
            ), 0)
            """
        )
    )

    db.commit()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_user_schema(db)
        ensure_user_coupon_schema(db)
        ensure_order_schema(db)
        ensure_dish_schema(db)
        seed_base_data(db)
        seed_admin(db)
        db.commit()
        print("Database initialized successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
