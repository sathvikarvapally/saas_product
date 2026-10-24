from calendar import monthrange
from datetime import datetime


def next_period_end(start: datetime, billing_interval: str) -> datetime:
    months = {"monthly": 1, "quarterly": 3, "annual": 12}[billing_interval]
    month_index = start.year * 12 + start.month - 1 + months
    year, month = divmod(month_index, 12)
    month += 1
    return start.replace(year=year, month=month, day=min(start.day, monthrange(year, month)[1]))
