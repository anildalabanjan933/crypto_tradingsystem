filepath = "engine/metrics_calculator.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

old = "        equity = [self.initial_capital]\n        for pnl in df_trades['net_pnl']:\n            equity.append(equity[-1] + float(pnl))\n\n        # Apply post-run tax as final deduction on last equity point\n        equity[-1] = equity[-1] - total_tax\n        self.metrics['equity_curve'] = equity"

new = "        equity = [self.initial_capital]\n        for pnl in df_trades['net_pnl']:\n            pnl_f = float(pnl)\n            trade_tax = pnl_f * tax_rate if pnl_f > 0 else 0.0\n            equity.append(equity[-1] + pnl_f - trade_tax)\n\n        self.metrics['equity_curve'] = equity"

if old in content:
    content = content.replace(old, new)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("FIXED")
else:
    print("ERROR: pattern not found")
