from datetime import date, datetime, timedelta, timezone


APP_TIMEZONE = timezone(timedelta(hours=8))


def now_china() -> datetime:
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def today_china() -> date:
    return now_china().date()


def to_china_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(APP_TIMEZONE).replace(tzinfo=None)
