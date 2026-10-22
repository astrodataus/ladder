#!/usr/bin/env python3
"""Daily refresh for Ladder. Standard library only.

Usage: python3 refresh.py OLD_JSON NEW_JSON [--no-treasury]

Pulls the newest Treasury nominal and real (TIPS) curves, preferring
home.treasury.gov (same-day close) and falling back to FRED (H.15, about a
business day behind). Breakevens, fed funds, credit spreads and CPI come from
FRED. Annual returns (Damodaran) are carried over unchanged from OLD_JSON.

When FRED is unreachable (an outage or its maintenance page), the curves and
the real-yield history come from Treasury alone, which publishes the same
series, and the FRED-only figures (breakevens, fed funds, credit spreads, CPI
and the market strip) are carried over from OLD_JSON with their own as-of
dates. When neither source has anything newer, the run ends as "nothing newer".

Exit codes: 0 = NEW_JSON written with newer data; 3 = nothing newer than
OLD_JSON, or no source reachable (do not publish); 1 = a check failed (do not
publish).
"""
import csv, io, json, sys, time, urllib.request, datetime as dt

UAS = ["curl/8.5.0", "astrodata-ladder/0.2"]  # FRED refuses some agents; try each
TEN = [1 / 12, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
TCOLS = ["1 Mo", "3 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr"]
NOM_FRED = ["DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS3", "DGS5", "DGS7", "DGS10", "DGS20", "DGS30"]
RT = [5, 7, 10, 20, 30]
RCOLS = ["5 YR", "7 YR", "10 YR", "20 YR", "30 YR"]
REAL_FRED = ["DFII5", "DFII7", "DFII10", "DFII20", "DFII30"]
TURL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
        "daily-treasury-rates.csv/{y}/all?type={t}&field_tdr_date_value={y}&page&_format=csv")


class SourceDown(Exception):
    """A data source answered with something other than its CSV, or not at all."""


def warn(msg):
    # Shows as a warning on the GitHub Actions run, and as plain text anywhere else.
    print(f"::warning::{msg}")


def get(url, tries=3, timeout=40):
    for i in range(tries):
        try:
            ua = UAS[i % len(UAS)]
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=timeout) as r:
                txt = r.read().decode("utf-8-sig")
            if txt.lstrip()[:1] == "<":  # an HTML page (maintenance, error), not a CSV
                raise ValueError("answered with an HTML page, not CSV")
            return txt
        except Exception as e:
            print(f"  retry {i + 1}: {url[:90]} ({e})", file=sys.stderr)
            time.sleep(2)
    return None


def fred(series, start=None):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}" + (f"&cosd={start}" if start else "")
    txt = get(url)
    if txt is None:
        raise SourceDown(f"FRED unreachable for {series}")
    rows = list(csv.reader(io.StringIO(txt)))
    if not rows or len(rows[0]) < 2 or rows[0][1].strip() != series:
        raise SourceDown(f"FRED sent something other than the {series} CSV")
    out = {}
    try:
        for row in rows[1:]:
            if len(row) >= 2 and row[1] not in ("", "."):
                out[dt.date.fromisoformat(row[0])] = float(row[1])
    except ValueError as e:
        raise SourceDown(f"FRED {series} CSV did not parse ({e})")
    return out


def treasury(kind, year, cols):
    txt = get(TURL.format(y=year, t=kind), tries=2, timeout=25)
    if not txt:
        return {}
    rows = list(csv.DictReader(io.StringIO(txt)))
    out = {}
    try:
        for r in rows:
            m, d, y = r["Date"].split("/")
            out[dt.date(int(y), int(m), int(d))] = [float(r[c]) if r.get(c) not in (None, "") else None for c in cols]
    except (KeyError, ValueError) as e:
        print(f"  Treasury {kind} {year} did not parse ({e})", file=sys.stderr)
        return {}
    return out


def treasury_history(kind, cols, first_year, last_year):
    """Daily curves from Treasury, one CSV per year. Used when FRED is down."""
    out = {}
    for y in range(first_year, last_year + 1):
        t = treasury(kind, y, cols)
        if not t:
            raise SourceDown(f"Treasury {kind} {y} unreachable")
        out.update(t)
    return dict(sorted(out.items()))


def daily_curves(series_list, tcols, kind, start, use_treasury):
    by = {}
    fred_ok = True
    try:
        for j, s in enumerate(series_list):
            for d, v in fred(s, start.isoformat()).items():
                by.setdefault(d, [None] * len(series_list))[j] = v
    except SourceDown as e:
        warn(f"{e}; using Treasury alone for the curves")
        by, fred_ok = {}, False
    src = "FRED" if fred_ok else "none"
    if use_treasury:
        for y in sorted({start.year, dt.date.today().year}):
            t = treasury(kind, y, tcols)
            if t:
                src = "Treasury"
            for d, vals in t.items():
                if d >= start:
                    base = by.get(d, [None] * len(series_list))
                    by[d] = [v if v is not None else b for v, b in zip(vals, base)]
    return dict(sorted(by.items())), src, fred_ok


def r2(x):
    return None if x is None else round(float(x), 2)


def month_end(daily):
    out = {}
    for d, vals in daily.items():
        out[d.strftime("%Y-%m")] = vals  # sorted input, so the last day of each month wins
    return out


def last_on_or_before(daily, d):
    keys = [k for k in daily if k <= d]
    return daily[keys[-1]], keys[-1]


def since(series, v):
    last = max(series)
    prior = [d for d, x in series.items() if x >= v and d < last - dt.timedelta(days=200)]
    return max(prior).isoformat() if prior else None


def main():
    old_path, new_path = sys.argv[1], sys.argv[2]
    use_treasury = "--no-treasury" not in sys.argv
    J = json.load(open(old_path))
    old_asof = dt.date.fromisoformat(J["facts"]["asof"])
    today = dt.date.today()
    start = dt.date(today.year - 1, 1, 1)

    nom, nsrc, ok_n = daily_curves(NOM_FRED, TCOLS, "daily_treasury_yield_curve", start, use_treasury)
    real, rsrc, ok_r = daily_curves(REAL_FRED, RCOLS, "daily_treasury_real_yield_curve", start, use_treasury)
    fred_ok = ok_n and ok_r
    nom = {d: v for d, v in nom.items() if v[8] is not None}
    real = {d: v for d, v in real.items() if v[2] is not None}
    if not nom or not real:
        warn("Neither FRED nor Treasury answered with curves; trying again on the next run.")
        return 3
    asof, real_asof = max(nom), max(real)
    print(f"nominal through {asof} ({nsrc}), real through {real_asof} ({rsrc}); page had {old_asof}")
    if asof <= old_asof:
        print("Nothing newer than the published data.")
        return 3

    last_n, last_r = nom[asof], real[real_asof]
    for v in [x for x in last_n + last_r if x is not None]:
        if not (-5 < v < 25):
            print("Implausible yield", v); return 1

    # monthly curves: keep history before the window, replace months inside it
    nm_new, rm_new = month_end(nom), month_end(real)
    cut = start.strftime("%Y-%m")
    J["nm"] = [r for r in J["nm"] if r[0] < cut] + [[m, [r2(x) for x in v]] for m, v in nm_new.items()]
    J["rm"] = [r for r in J["rm"] if r[0] < cut] + [[m, [r2(x) for x in v]] for m, v in rm_new.items()]

    ya_n, ya_date = last_on_or_before(nom, asof - dt.timedelta(days=365))
    ya_r, _ = last_on_or_before(real, real_asof - dt.timedelta(days=365))
    key = lambda xs: {str(t): r2(v) for t, v in xs if v is not None}
    J["latest_nom"], J["latest_real"] = key(zip(TEN, last_n)), key(zip(RT, last_r))
    J["ya_nom"], J["ya_real"] = key(zip(TEN, ya_n)), key(zip(RT, ya_r))

    # long real-yield histories for the "most since" facts and the 2021 low
    if fred_ok:
        try:
            r10 = fred("DFII10"); r30 = fred("DFII30")
        except SourceDown as e:
            warn(f"{e}; using Treasury alone for the history")
            fred_ok = False
    if not fred_ok:
        try:
            hist = treasury_history("daily_treasury_real_yield_curve", RCOLS, 2003, real_asof.year)
        except SourceDown as e:
            warn(f"{e}; nothing published, trying again on the next run.")
            return 3
        r10 = {d: v[2] for d, v in hist.items() if v[2] is not None}
        r30 = {d: v[4] for d, v in hist.items() if v[4] is not None}
    for d, v in real.items():
        if v[2] is not None: r10[d] = v[2]
        if v[4] is not None: r30[d] = v[4]
    r10 = dict(sorted(r10.items())); r30 = dict(sorted(r30.items()))
    dmin = min(r10, key=r10.get)
    lo = dmin - dt.timedelta(days=10)
    if fred_ok:
        full_nom = {}
        for j, s in enumerate(NOM_FRED):
            for d, v in fred(s, lo.isoformat()).items():
                if d <= dmin: full_nom.setdefault(d, [None] * 11)[j] = v
        full_real = {}
        for j, s in enumerate(REAL_FRED):
            for d, v in fred(s, lo.isoformat()).items():
                if d <= dmin: full_real.setdefault(d, [None] * 5)[j] = v
    else:
        try:
            full_nom = {d: v for d, v in treasury_history("daily_treasury_yield_curve", TCOLS, lo.year, dmin.year).items() if d <= dmin}
        except SourceDown as e:
            warn(f"{e}; nothing published, trying again on the next run.")
            return 3
        full_real = {d: v for d, v in hist.items() if lo <= d <= dmin}
    mn, _ = last_on_or_before(full_nom, dmin)
    mr, _ = last_on_or_before(full_real, dmin)
    J["min_nom"], J["min_real"], J["min_date"] = key(zip(TEN, mn)), key(zip(RT, mr)), dmin.isoformat()

    F = J["facts"]
    market = None
    if fred_ok:
        try:
            market = [fred(s) for s in ["T5YIE", "T10YIE", "DFF", "BAMLC0A0CM", "BAMLH0A0HYM2", "CPIAUCSL"]]
        except SourceDown as e:
            warn(f"{e}; carrying the market figures over")
    if market is None:
        warn(f"FRED is unreachable: breakevens, fed funds, spreads, CPI and the market strip are carried over "
             f"(breakevens as of {F.get('be_asof')}, spreads as of {F.get('spread_asof')}, CPI {F.get('cpi_month')}).")
    F.update({
        "asof": asof.isoformat(), "real_asof": real_asof.isoformat(),
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_nominal": nsrc, "source_real": rsrc,
        "real10": r2(r10[max(r10)]), "real10_last_higher": since(r10, r10[max(r10)]),
        "real10_min": r2(r10[dmin]), "real10_min_date": dmin.isoformat(),
        "real30": r2(r30[max(r30)]), "real30_last_higher": since(r30, r30[max(r30)]), "real30_first": min(r30).isoformat(),
        "nom10": r2(last_n[8]), "nom10_ya": r2(ya_n[8]), "ya_date": ya_date.isoformat(),
    })

    if market is not None:
        be5, be10, dff, ig, hy, cpi = market
        lastv = lambda s: s[max(s)]
        cpis = sorted(cpi.items())
        F.update({
            "be5": r2(lastv(be5)), "be10": r2(lastv(be10)), "be_asof": max(be10).isoformat(),
            "dff": r2(lastv(dff)), "ig": r2(lastv(ig)), "hy": r2(lastv(hy)), "spread_asof": max(hy).isoformat(),
            "cpi_yoy": round(cpis[-1][1] / cpis[-13][1] * 100 - 100, 2), "cpi_month": cpis[-1][0].isoformat(),
        })

        # market strip, month-end, from 1990
        def me(s):
            o = {}
            for d, v in sorted(s.items()):
                if d.year >= 1990: o[d.strftime("%Y-%m")] = v
            return o
        cols = [me(dff), me(be5), me(be10), me(ig), me(hy)]
        months = sorted(set().union(*cols))
        J["mk"] = [[m] + [None if c.get(m) is None else round(c[m], 2) for c in cols] for m in months]

    # checks before anything is published
    assert len(J["nm"]) >= 440 and len(J["rm"]) >= 280, "monthly history shrank"
    assert J["nm"][-1][0] == asof.strftime("%Y-%m"), "latest month missing"
    assert all(J["latest_nom"].get(k) is not None for k in ["0.25", "2", "10", "30"]), "latest curve incomplete"
    json.dump(J, open(new_path, "w"), separators=(",", ":"))
    print(f"wrote {new_path}: close {F['asof']}, 10-yr {F['nom10']}%, 10-yr real {F['real10']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
