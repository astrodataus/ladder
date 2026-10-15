#!/usr/bin/env python3
"""ladder_data.json -> data/csv/ladder_*.csv, the five tables the Omni app reads.

Usage: python3 to_csvs.py ladder_data.json OUT_DIR

The app's fromRows() turns these rows back into exactly the object the embedded
build carries; scripts/check_roundtrip.js proves it after every build.
"""
import csv, json, os, sys

TCOLS = ["t_1m", "t_3m", "t_6m", "t_1y", "t_2y", "t_3y", "t_5y", "t_7y", "t_10y", "t_20y", "t_30y"]
TEN_KEYS = ["0.08333333333333333", "0.25", "0.5", "1", "2", "3", "5", "7", "10", "20", "30"]
RIDX = [6, 7, 8, 9, 10]  # real tenors 5, 7, 10, 20, 30 sit in these columns


def fmt(v):
    return "" if v is None else repr(v) if isinstance(v, float) else str(v)


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow([fmt(v) for v in r])


def main():
    J = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)

    rows = [[m, "nominal"] + ys for m, ys in J["nm"]]
    for m, ys in J["rm"]:
        wide = [None] * 11
        for k, v in zip(RIDX, ys):
            wide[k] = v
        rows.append([m, "real"] + wide)
    write(os.path.join(out, "ladder_curves_monthly.csv"), ["month", "kind"] + TCOLS, rows)

    key = []
    F = J["facts"]
    for role, date, nom, real in [("latest", F["asof"], J["latest_nom"], J["latest_real"]),
                                  ("year_ago", F["ya_date"], J["ya_nom"], J["ya_real"]),
                                  ("real10_low", J["min_date"], J["min_nom"], J["min_real"])]:
        key.append([role, date, "nominal"] + [nom.get(k) for k in TEN_KEYS])
        key.append([role, date, "real"] + [real.get(k) for k in TEN_KEYS])
    write(os.path.join(out, "ladder_curves_keydates.csv"), ["role", "curve_date", "kind"] + TCOLS, key)

    write(os.path.join(out, "ladder_market_monthly.csv"),
          ["month", "fed_funds", "breakeven_5y", "breakeven_10y", "ig_spread", "hy_spread"], J["mk"])
    write(os.path.join(out, "ladder_returns_annual.csv"),
          ["year", "stocks", "bills", "tbond10", "inflation"], J["ret"])
    write(os.path.join(out, "ladder_facts.csv"), ["fact", "value"],
          [[k, "" if v is None else str(v)] for k, v in F.items()])
    print("wrote", out, {"curves": len(rows), "keydates": len(key), "market": len(J["mk"]), "returns": len(J["ret"]), "facts": len(F)})


if __name__ == "__main__":
    main()
