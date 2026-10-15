#!/usr/bin/env python3
"""Fill the page templates with fresh data. Usage: python3 render.py ladder_data.json TEMPLATE OUT [TEMPLATE OUT ...]"""
import json, sys
data = open(sys.argv[1], encoding="utf-8").read().strip()
json.loads(data)
assert "</script" not in data.lower()
for tpl, out in zip(sys.argv[2::2], sys.argv[3::2]):
    t = open(tpl, encoding="utf-8").read()
    assert t.count("/*__DATA__*/null") == 1, tpl
    open(out, "w", encoding="utf-8").write(t.replace("/*__DATA__*/null", data))
    print("rendered", out)
