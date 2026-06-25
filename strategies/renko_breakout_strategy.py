# strategies/renko_breakout_strategy.py
# Strategy 3 - Renko Trendline Breakout With Support/Resistance
# Inherits BaseStrategy, follows CTS architecture

import numpy as np
import pandas as pd
from strategies.base_strategy import BaseStrategy
from indicators.renko import RenkoBuilder, SupertrendIndicator, SwingDetector, _trendline_value_at


class RenkoBreakoutStrategy(BaseStrategy):
    """
    Strategy 3 - Renko Trendline Breakout With Support/Resistance

    BUY  : Green box close ABOVE bearish descending TL (min 2 touches)
           + supporting condition: horizontal support (min 2 swing lows)
             OR ascending bullish TL below price
    SELL : Red box close BELOW bullish ascending TL (min 2 touches)
           + supporting condition: horizontal resistance (min 2 swing highs)
             OR descending bearish TL above price
    EXIT : ST flip only (no ST check at entry)
    """

    def __init__(self, data_dict: dict, lot_size: float, **kwargs):
        super().__init__(data_dict, lot_size, **kwargs)

        self.box_size        = kwargs.get('box_size', 200)
        self.st_period       = kwargs.get('st_period', 5)
        self.st_factor       = kwargs.get('st_factor', 4.0)
        self.swing_left      = kwargs.get('swing_left', 2)
        self.swing_right     = kwargs.get('swing_right', 2)
        self.min_touches     = kwargs.get('min_touches', 2)
        self.touch_tolerance = kwargs.get('touch_tolerance', 0.5)
        self.max_tl_bars     = kwargs.get('max_tl_bars', 50)

    @property
    def required_timeframes(self):
        return ['2H']

    @property
    def optimization_params(self):
        return {}

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _count_tl_touches(self, renko_df, tl_type, end_idx):
        """
        Count renko boxes that touched the trendline up to end_idx (exclusive).
        tl_type : 'bearish' - checks renko_high vs bearish TL (swing highs)
                  'bullish' - checks renko_low  vs bullish TL (swing lows)
        """
        tolerance = self.box_size * self.touch_tolerance
        touches   = 0
        sh_hist   = renko_df['swing_highs_hist'].tolist()
        sl_hist   = renko_df['swing_lows_hist'].tolist()

        for j in range(end_idx):
            if tl_type == 'bearish':
                tl_val    = _trendline_value_at(sh_hist[j], j, self.max_tl_bars)
                price_val = renko_df['renko_high'].iloc[j]
            else:
                tl_val    = _trendline_value_at(sl_hist[j], j, self.max_tl_bars)
                price_val = renko_df['renko_low'].iloc[j]

            if tl_val is None:
                continue
            if abs(price_val - tl_val) <= tolerance:
                touches += 1

        return touches

    def _has_horizontal_support(self, sl_hist_i, min_swings=2):
        """
        Returns (True, level) if min_swings confirmed swing lows exist.
        Level = last confirmed swing low price.
        """
        if sl_hist_i and len(sl_hist_i) >= min_swings:
            return True, sl_hist_i[-1][1]
        return False, None

    def _has_horizontal_resistance(self, sh_hist_i, min_swings=2):
        """
        Returns (True, level) if min_swings confirmed swing highs exist.
        Level = last confirmed swing high price.
        """
        if sh_hist_i and len(sh_hist_i) >= min_swings:
            return True, sh_hist_i[-1][1]
        return False, None

    def _has_bullish_tl(self, sl_hist_i, bar_idx):
        """
        Returns (True, tl_value) if valid ascending bullish TL exists at bar_idx.
        Requires min 2 confirmed swing lows.
        """
        if sl_hist_i and len(sl_hist_i) >= 2:
            tl_val = _trendline_value_at(sl_hist_i, bar_idx, self.max_tl_bars)
            if tl_val is not None:
                return True, tl_val
        return False, None

    def _has_bearish_tl(self, sh_hist_i, bar_idx):
        """
        Returns (True, tl_value) if valid descending bearish TL exists at bar_idx.
        Requires min 2 confirmed swing highs.
        """
        if sh_hist_i and len(sh_hist_i) >= 2:
            tl_val = _trendline_value_at(sh_hist_i, bar_idx, self.max_tl_bars)
            if tl_val is not None:
                return True, tl_val
        return False, None

    # ------------------------------------------------------------------
    # MAIN SIGNAL GENERATION
    # ------------------------------------------------------------------

    def generate_signals(self):
        """
        Build Renko bricks, calculate Supertrend, detect swings,
        project trendlines, generate BUY/SELL/EXIT signals.
        Returns list of signal dicts.
        """

        # ---- 1. Build Renko bricks ----
        df_2h = self._data.get('2H')
        if df_2h is None or len(df_2h) == 0:
            raise ValueError("RenkoBreakoutStrategy requires '2H' key in data_dict")

        closes     = df_2h['close'].values
        timestamps = (
            df_2h.index
            if isinstance(df_2h.index, pd.DatetimeIndex)
            else pd.to_datetime(df_2h['timestamp'])
        )

        builder  = RenkoBuilder(box_size=self.box_size)
        renko_df = builder.build(closes)

        if renko_df is None or len(renko_df) < 20:
            return []

        # Map timestamps from source candle bar_index
        renko_df['timestamp'] = renko_df['bar_index'].apply(
            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]
        )
        renko_df = renko_df.reset_index(drop=True)

        # ---- 2. Supertrend ----
        st_calc  = SupertrendIndicator(atr_period=self.st_period, factor=self.st_factor)
        renko_df = st_calc.calculate(renko_df)

        # ---- 3. Swing detector ----
        swing_detector = SwingDetector(swing_left=self.swing_left, swing_right=self.swing_right)
        renko_df       = swing_detector.detect(renko_df)
        n              = len(renko_df)
        st_vals        = renko_df['st_dir'].tolist()
        sh_hist        = renko_df['swing_highs_hist'].tolist()
        sl_hist        = renko_df['swing_lows_hist'].tolist()

        # ---- 4. Iterate bricks and generate signals ----
        signals      = []
        position     = None
        entry_signal = None
        prev_close   = None
        prev_st_dir  = None

        for i in range(n):
            row      = renko_df.iloc[i]
            close    = row['renko_close']
            bar_time = row['timestamp']
            is_green = close > row['renko_open']
            is_red   = close < row['renko_open']
            st_dir   = st_vals[i]

            # ---- Trendline values at current bar ----
            btl_val   = _trendline_value_at(sh_hist[i],     i,     self.max_tl_bars)
            bltl_val  = _trendline_value_at(sl_hist[i],     i,     self.max_tl_bars)
            btl_prev  = _trendline_value_at(sh_hist[i - 1], i - 1, self.max_tl_bars) if i > 0 else None
            bltl_prev = _trendline_value_at(sl_hist[i - 1], i - 1, self.max_tl_bars) if i > 0 else None

            # ---- EXIT CHECK ----
            if position is not None and prev_st_dir is not None:

                if position == 'LONG' and prev_st_dir == -1 and st_dir == 1 and is_red:
                    signals.append({
                        'signal_type': 'EXIT',
                        'direction'  : 'LONG',
                        'exit_type'  : 'ST_FLIP_RED',
                        'bar_index'  : i,
                        'timestamp'  : bar_time,
                        'price'      : close,
                        'entry_ref'  : entry_signal,
                    })
                    position     = None
                    entry_signal = None

                elif position == 'SHORT' and prev_st_dir == 1 and st_dir == -1 and is_green:
                    signals.append({
                        'signal_type': 'EXIT',
                        'direction'  : 'SHORT',
                        'exit_type'  : 'ST_FLIP_GREEN',
                        'bar_index'  : i,
                        'timestamp'  : bar_time,
                        'price'      : close,
                        'entry_ref'  : entry_signal,
                    })
                    position     = None
                    entry_signal = None

            # ---- ENTRY CHECK ----
            if position is None:

                # ============================================================
                # BUY ENTRY
                # Primary   : green box close ABOVE bearish descending TL
                # Supporting: horizontal support (min 2 swing lows)
                #             OR ascending bullish TL below price
                # ============================================================
                buy_tl_cross = (
                    btl_val is not None
                    and btl_prev is not None
                    and prev_close is not None
                    and is_green
                    and close > btl_val
                    and prev_close <= btl_prev
                )

                if buy_tl_cross:
                    btl_touches = self._count_tl_touches(renko_df, 'bearish', i)

                    # Supporting condition Option B: horizontal support
                    has_h_sup, h_sup_level = self._has_horizontal_support(sl_hist[i], min_swings=2)

                    # Supporting condition Option C: ascending bullish TL below price
                    has_bltl, bltl_val_sup = self._has_bullish_tl(sl_hist[i], i)
                    bltl_below_price       = has_bltl and bltl_val_sup is not None and bltl_val_sup < close

                    supporting_ok = has_h_sup or bltl_below_price

                    print(
                        f"[BUY candidate] i={i} close={close:.0f} "
                        f"btl={btl_val:.0f} touches={btl_touches} "
                        f"h_sup={has_h_sup}(level={h_sup_level}) "
                        f"bltl_below={bltl_below_price}(val={bltl_val_sup}) "
                        f"supporting={supporting_ok}"
                    )

                    if btl_touches >= self.min_touches and supporting_ok:
                        signals.append({
                            'signal_type' : 'ENTRY',
                            'direction'   : 'LONG',
                            'entry_type'  : 'BUY_A',
                            'bar_index'   : i,
                            'timestamp'   : bar_time,
                            'price'       : close,
                            'btl_val'     : btl_val,
                            'bltl_val'    : bltl_val,
                            'btl_touches' : btl_touches,
                            'h_sup_level' : h_sup_level,
                        })
                        position     = 'LONG'
                        entry_signal = 'BUY_A'

                # ============================================================
                # SELL ENTRY
                # Primary   : red box close BELOW bullish ascending TL
                # Supporting: horizontal resistance (min 2 swing highs)
                #             OR descending bearish TL above price
                # ============================================================
                if position is None:
                    sell_tl_cross = (
                        bltl_val is not None
                        and bltl_prev is not None
                        and prev_close is not None
                        and is_red
                        and close < bltl_val
                        and prev_close >= bltl_prev
                    )

                    if sell_tl_cross:
                        bltl_touches = self._count_tl_touches(renko_df, 'bullish', i)

                        # Supporting condition Option B: horizontal resistance
                        has_h_res, h_res_level = self._has_horizontal_resistance(sh_hist[i], min_swings=2)

                        # Supporting condition Option C: descending bearish TL above price
                        has_btl, btl_val_res = self._has_bearish_tl(sh_hist[i], i)
                        btl_above_price      = has_btl and btl_val_res is not None and btl_val_res > close

                        supporting_ok = has_h_res or btl_above_price

                        print(
                            f"[SELL candidate] i={i} close={close:.0f} "
                            f"bltl={bltl_val:.0f} touches={bltl_touches} "
                            f"h_res={has_h_res}(level={h_res_level}) "
                            f"btl_above={btl_above_price}(val={btl_val_res}) "
                            f"supporting={supporting_ok}"
                        )

                        if bltl_touches >= self.min_touches and supporting_ok:
                            signals.append({
                                'signal_type'  : 'ENTRY',
                                'direction'    : 'SHORT',
                                'entry_type'   : 'SELL_A',
                                'bar_index'    : i,
                                'timestamp'    : bar_time,
                                'price'        : close,
                                'bltl_val'     : bltl_val,
                                'btl_val'      : btl_val,
                                'bltl_touches' : bltl_touches,
                                'h_res_level'  : h_res_level,
                            })
                            position     = 'SHORT'
                            entry_signal = 'SELL_A'

            # ---- Update previous bar state ----
            prev_close  = close
            prev_st_dir = st_dir

        # ---- DEBUG SUMMARY ----
        print(f"\nDEBUG: total_bricks={n}, total_signals={len(signals)}")
        buy_entries  = [s for s in signals if s.get('direction') == 'LONG'  and s['signal_type'] == 'ENTRY']
        sell_entries = [s for s in signals if s.get('direction') == 'SHORT' and s['signal_type'] == 'ENTRY']
        exits        = [s for s in signals if s['signal_type'] == 'EXIT']
        print(f"DEBUG: BUY={len(buy_entries)}, SELL={len(sell_entries)}, EXIT={len(exits)}")

        return signals
