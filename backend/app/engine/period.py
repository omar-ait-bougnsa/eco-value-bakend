"""Analysis periods and snapshot blending. Port of `src/engine/period.ts`."""
import calendar
from datetime import date, timedelta
from typing import NamedTuple

from ..data.seed import DATA_START, TODAY as DATA_END
from ..schemas import Quote, Snapshot


class Span(NamedTuple):
    """Inclusive date range."""
    start: date
    end: date


CURRENT_YEAR = DATA_END.year
YTD = Span(date(CURRENT_YEAR, 1, 1), DATA_END)
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def fmt_day(d: date) -> str:
    return f'{d.day:02d} {MON[d.month - 1]} {d.year}'


def clamp_period(p: Span) -> Span:
    start = min(max(p.start, DATA_START), DATA_END)
    end = min(max(p.end, DATA_START), DATA_END)
    return Span(end, start) if start > end else Span(start, end)


def year_period(y: int) -> Span:
    return YTD if y >= CURRENT_YEAR else Span(date(y, 1, 1), date(y, 12, 31))


def month_period(year: int, month: int) -> Span:
    """The current month is cut at today."""
    return clamp_period(Span(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])))


def last_12_months() -> Span:
    return Span(DATA_END - timedelta(days=364), DATA_END)


def period_presets() -> list[tuple[str, str, Span]]:
    return [
        ('ytd', 'Year to date', YTD),
        ('l12', 'Last 12 months', last_12_months()),
        *[(str(y), str(y), year_period(y)) for y in range(CURRENT_YEAR - 1, DATA_START.year - 1, -1)],
        ('2021-25', '2021–2025', Span(date(2021, 1, 1), date(2025, 12, 31))),
    ]


def period_weights(p0: Span) -> dict[str, float]:
    """Share of the period (by days) that falls in each yearly snapshot. The current year maps to "today"."""
    p = clamp_period(p0)
    total = (p.end - p.start).days + 1
    out: dict[str, float] = {}
    for y in range(DATA_START.year, CURRENT_YEAR + 1):
        ys = date(y, 1, 1)
        ye = DATA_END if y == CURRENT_YEAR else date(y, 12, 31)
        n = (min(p.end, ye) - max(p.start, ys)).days + 1
        if n > 0:
            out['today' if y == CURRENT_YEAR else str(y)] = n / total
    return out


def is_current_period(p: Span) -> bool:
    return period_weights(p).get('today', 0) > 0.9999


def touches_current_year(p: Span) -> bool:
    return period_weights(p).get('today', 0) > 0


def blend_snapshot(snapshots: list[Snapshot], p0: Span) -> Snapshot:
    """Day-weighted blend of the yearly snapshots covering the period.
    A period inside the current year returns the "today" snapshot untouched."""
    p = clamp_period(p0)
    w = period_weights(p)
    by_id = {s.id: s for s in snapshots}
    if w.get('today', 0) > 0.9999:
        return by_id['today']
    ids = [i for i in w if i in by_id]
    total = sum(w[i] for i in ids)

    def mix(f) -> float | None:
        acc = 0.0
        for i in ids:
            v = f(by_id[i])
            if v is None:
                return None
            acc += (w[i] / total) * v
        return acc

    inputs = {k: mix(lambda s, k=k: s.inputs[k]) or 0 for k in by_id['today'].inputs}
    ref = lambda r: Quote(low=mix(lambda s: s.refPrices[r].low), high=None)
    return Snapshot(
        id='period', label=period_label(p), asOf=p.end, inputs=inputs,
        refPrices={'DAP': ref('DAP'), 'MAP': ref('MAP'), 'TSP': ref('TSP')},
        source='Day-weighted blend of yearly averages (CRU) and current Standard cost / Argus inputs',
    )


def period_label(p0: Span) -> str:
    p = clamp_period(p0)
    if p == YTD:
        return 'Year to date'
    if p == last_12_months():
        return 'Last 12 months'
    if p == Span(date(2021, 1, 1), date(2025, 12, 31)):
        return '2021–2025'
    if p.start.year < CURRENT_YEAR and p == year_period(p.start.year):
        return str(p.start.year)
    if p.start == p.end:
        return fmt_day(p.start)
    if p == month_period(p.start.year, p.start.month):
        return f'{MON[p.start.month - 1]} {p.start.year}'
    return f'{fmt_day(p.start)} – {fmt_day(p.end)}'
