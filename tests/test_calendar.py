from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from billing import PKT, add_calendar_months, grant_month, pkt, utc


def at_pkt(year, month, day, hour=15, minute=35):
    return datetime(year, month, day, hour, minute, tzinfo=PKT)


def ymd(value):
    local = pkt(value)
    return local.year, local.month, local.day, local.hour, local.minute


def test_same_date_next_month_30_and_31_day_months():
    start = at_pkt(2026, 4, 30, 11, 20)
    may = add_calendar_months(start, 1, 30)
    june = add_calendar_months(start, 2, 30)
    july = add_calendar_months(start, 3, 30)
    assert ymd(may) == (2026, 5, 30, 11, 20)
    assert ymd(june) == (2026, 6, 30, 11, 20)
    assert ymd(july) == (2026, 7, 30, 11, 20)
    jan31 = at_pkt(2026, 1, 31, 23, 35)
    assert ymd(add_calendar_months(jan31, 1, 31)) == (2026, 2, 28, 23, 35)
    assert ymd(add_calendar_months(jan31, 2, 31)) == (2026, 3, 31, 23, 35)
    assert ymd(add_calendar_months(jan31, 3, 31)) == (2026, 4, 30, 23, 35)
    assert ymd(add_calendar_months(jan31, 4, 31)) == (2026, 5, 31, 23, 35)


def test_february_28_and_leap_29():
    leap = at_pkt(2024, 2, 29, 9, 0)
    assert ymd(add_calendar_months(leap, 1, 29)) == (2024, 3, 29, 9, 0)
    assert ymd(add_calendar_months(leap, 12, 29)) == (2025, 2, 28, 9, 0)
    nonleap = at_pkt(2025, 2, 28, 9, 0)
    assert ymd(add_calendar_months(nonleap, 1, 28)) == (2025, 3, 28, 9, 0)
    jan31_leap = at_pkt(2024, 1, 31, 18, 0)
    assert ymd(add_calendar_months(jan31_leap, 1, 31)) == (2024, 2, 29, 18, 0)
    assert ymd(add_calendar_months(jan31_leap, 13, 31)) == (2025, 2, 28, 18, 0)


def test_anchor_survives_short_month_then_returns():
    class Shop:
        paid_until = None
        billing_day = None

    shop = Shop()
    start = at_pkt(2026, 1, 31, 10, 0)
    grant_month(shop, start)
    assert shop.billing_day == 31
    assert ymd(shop.paid_until) == (2026, 2, 28, 10, 0)
    grant_month(shop, at_pkt(2026, 2, 10, 10, 0))
    assert shop.billing_day == 31
    assert ymd(shop.paid_until) == (2026, 3, 31, 10, 0)
    grant_month(shop, utc(shop.paid_until) - timedelta(days=1))
    assert ymd(shop.paid_until) == (2026, 4, 30, 10, 0)


def test_expired_restart_takes_new_payment_day():
    class Shop:
        paid_until = add_calendar_months(at_pkt(2026, 1, 31), 1, 31)
        billing_day = 31

    shop = Shop()
    later = at_pkt(2026, 3, 10, 8, 15)
    grant_month(shop, later)
    assert shop.billing_day == 10
    assert ymd(shop.paid_until) == (2026, 4, 10, 8, 15)
