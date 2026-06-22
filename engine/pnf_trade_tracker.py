"""
PnF Trade Tracker
Track active trades, SL activation, exits, and re-entries
"""

import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime


class PnFTradeTracker:
    """
    Track PnF trades with:
    - Entry/exit prices
    - SL activation timing
    - Re-entry support
    - Trade statistics
    """

    def __init__(self):
        self.active_trades = []
        self.closed_trades = []
        self.trade_counter = 0

    def open_trade(self, col_idx: int, entry_price: float,
                   sl_price: float, timestamp: datetime,
                   sma10: Optional[float] = None,
                   sma20: Optional[float] = None,
                   adx: Optional[float] = None) -> Dict:
        """
        Open a new trade.

        Args:
            col_idx: Entry column index
            entry_price: Entry price
            sl_price: Stop loss price
            timestamp: Entry timestamp
            sma10: SMA10 at entry
            sma20: SMA20 at entry
            adx: ADX at entry

        Returns:
            Trade object
        """
        self.trade_counter += 1

        trade = {
            'trade_id': self.trade_counter,
            'entry_col_idx': col_idx,
            'entry_price': entry_price,
            'entry_timestamp': timestamp,
            'sl_price': sl_price,
            'sl_activated': False,
            'sl_activation_col': col_idx + 1,  # Activate after next column
            'exit_col_idx': None,
            'exit_price': None,
            'exit_timestamp': None,
            'exit_reason': None,
            'pnl': None,
            'pnl_percent': None,
            'sma10_entry': sma10,
            'sma20_entry': sma20,
            'adx_entry': adx,
            'status': 'OPEN',
        }

        self.active_trades.append(trade)
        return trade

    def close_trade(self, trade_id: int, exit_col_idx: int,
                    exit_price: float, exit_timestamp: datetime,
                    exit_reason: str) -> Dict:
        """
        Close an active trade.

        Args:
            trade_id: Trade ID to close
            exit_col_idx: Exit column index
            exit_price: Exit price
            exit_timestamp: Exit timestamp
            exit_reason: Reason for exit (SL_HIT, DOUBLE_TOP, etc.)

        Returns:
            Closed trade object
        """
        trade = None
        for t in self.active_trades:
            if t['trade_id'] == trade_id:
                trade = t
                break

        if trade is None:
            return None

        # Calculate PnL (negative for short)
        pnl = exit_price - trade['entry_price']
        pnl_percent = (pnl / trade['entry_price']) * 100

        trade['exit_col_idx'] = exit_col_idx
        trade['exit_price'] = exit_price
        trade['exit_timestamp'] = exit_timestamp
        trade['exit_reason'] = exit_reason
        trade['pnl'] = pnl
        trade['pnl_percent'] = pnl_percent
        trade['status'] = 'CLOSED'

        # Move to closed trades
        self.active_trades.remove(trade)
        self.closed_trades.append(trade)

        return trade

    def activate_sl(self, trade_id: int, current_col_idx: int) -> bool:
        """
        Activate SL for a trade.

        Args:
            trade_id: Trade ID
            current_col_idx: Current column index

        Returns:
            True if SL activated
        """
        for trade in self.active_trades:
            if trade['trade_id'] == trade_id:
                if current_col_idx >= trade['sl_activation_col']:
                    trade['sl_activated'] = True
                    return True

        return False

    def get_active_trade(self) -> Optional[Dict]:
        """Get current active trade (only one at a time)."""
        if len(self.active_trades) > 0:
            return self.active_trades[0]
        return None

    def get_trade_stats(self) -> Dict:
        """
        Get trade statistics.

        Returns:
            Dictionary with stats
        """
        if len(self.closed_trades) == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'max_win': 0,
                'max_loss': 0,
            }

        pnls = [t['pnl'] for t in self.closed_trades]
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]

        return {
            'total_trades': len(self.closed_trades),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': (len(winning) / len(self.closed_trades)) * 100 if len(self.closed_trades) > 0 else 0,
            'total_pnl': sum(pnls),
            'avg_pnl': sum(pnls) / len(pnls) if len(pnls) > 0 else 0,
            'max_win': max(winning) if winning else 0,
            'max_loss': min(losing) if losing else 0,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert closed trades to DataFrame."""
        return pd.DataFrame(self.closed_trades)
