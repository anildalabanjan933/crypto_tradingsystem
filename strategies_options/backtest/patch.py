import shutil
f = "algotest_backtest.py"
shutil.copy(f, f + ".bak")
s = open(f).read()
I = " "
R = [
    ('i = bisect.bisect_right(self.t, ts) - 1',
     'i = bisect.bisect_left(self.t, ts) - 1', 1),
    ('    def fill_at(self, ts):',
     '    def peak(self, ts):\n        i = bisect.bisect_left(self.t, ts) - 1\n        return self.c[i]["high"] if i >= 0 else 0\n\n    def fill_at(self, ts):', 1),
    ('sl_level = l["mkt"] * (1 + SL_RECOST_PCT)',
     'sl_level = l["mkt"] * (1 + SL_RECOST_PCT)\n' + I*20 + 'm = max(m, sl["series"].peak(cur))', 1),
    ('sl_level = l["mkt"] * (1 + SL_MAIN_PCT)',
     'sl_level = l["mkt"] * (1 + SL_MAIN_PCT)\n' + I*28 + 'm = max(m, ml["series"].peak(cur))', 1),
    ('if m >= lz["trig"]:',
     'if max(m, lz["series"].peak(cur)) >= lz["trig"]:', 1),
    ('lz["leg"]["raw"] = px * (1 + SLIP)',
     'lz["leg"]["raw"] = lz["trig"] * (1 + SLIP)', 1),
    ('lzstate["pnl"] += ef - lz["leg"]["raw"]',
     'ef = lz["trail_sl"] * (1 - SLIP)\n' + I*36 + 'lzstate["pnl"] += ef - lz["leg"]["raw"]', 1),
]
for old, new, expect in R:
    found = s.count(old)
    assert found == expect, f"MISMATCH ({found} vs {expect}): {old}"
    s = s.replace(old, new)
open(f, "w").write(s)
print("PATCHED OK")
