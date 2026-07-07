import re

filepath = r'D:\crypto_trading_system\strategies\backtest\renko_smiio_supertrend_strategy.py'

with open(filepath, 'r') as f:
    content = f.read()

old_method = '''    def generate_signals(self) -> list:
        df = self._build_renko_df()
        timestamps = df['timestamp'].values
        n = len(df)
        box = self.renko_box

        closes    = df['renko_close'].values
        renko_dir = df['renko_dir'].values

        # --- SupertrendIndicator (same as RenkoReversal) ---
        # st_dir: -1 = GREEN (bullish), +1 = RED (bearish)
        st_ind = SupertrendIndicator(
            atr_period=self.st_atr_length,
            factor=self.st_factor,
        )
        df_st  = st_ind.calculate(df)
        st_dir = df_st['st_dir'].values

        # --- SMIIO ---
        smi, sig = compute_smiio(
            closes,
            short_len=self.smiio_shortlen,
            long_len=self.smiio_longlen,
            signal_len=self.smiio_siglen,
        )

        # --- Signal loop ---
        # st_dir: -1 = GREEN (bullish), +1 = RED (bearish)
        signals           = []
        current_direction = None
        pending           = None

        for i in range(1, n):
            ts    = str(pd.Timestamp(timestamps[i]).strftime(\'%Y-%m-%dT%H:%M:%S\'))
            close = closes[i]
            r_dir = renko_dir[i]
            st    = st_dir[i]
            prev_st = st_dir[i - 1]

            smi_cross_up   = smi[i] > sig[i] and smi[i - 1] <= sig[i - 1]
            smi_cross_down = smi[i] < sig[i] and smi[i - 1] >= sig[i - 1]
            st_flip_green  = prev_st == 1  and st == -1   # RED -> GREEN
            st_flip_red    = prev_st == -1 and st == 1    # GREEN -> RED
            smi_above      = smi[i] > sig[i]
            smi_below      = smi[i] < sig[i]

            # ----------------------------------------------------------
            # EXIT: ST flip confirmed — execute at current bar (i)
            # ----------------------------------------------------------
            if current_direction == \'long\' and st_flip_red and r_dir == -1:
                signals.append({
                    \'signal_type\': \'EXIT\',
                    \'price\':       self._apply_slippage(close, \'long\', False),
                    \'timestamp\':   ts,
                    \'sl_price\':    close - box,
                    \'entry_type\':  \'\',
                    \'exit_type\':   \'ST_FLIP_RED\',
                    \'direction\':   \'long\',
                })
                current_direction = None
                pending           = None

            elif current_direction == \'short\' and st_flip_green and r_dir == 1:
                signals.append({
                    \'signal_type\': \'EXIT\',
                    \'price\':       self._apply_slippage(close, \'short\', False),
                    \'timestamp\':   ts,
                    \'sl_price\':    close + box,
                    \'entry_type\':  \'\',
                    \'exit_type\':   \'ST_FLIP_GREEN\',
                    \'direction\':   \'short\',
                })
                current_direction = None
                pending           = None

            # ----------------------------------------------------------
            # SET PENDING on crossover or ST flip (no position open)
            # ----------------------------------------------------------
            if current_direction is None:

                # BUY_A: SMIIO crosses up + ST already GREEN
                if smi_cross_up and st == -1:
                    pending = {\'side\': \'long\', \'entry_type\': \'BUY_A\'}

                # BUY_B: ST flips GREEN + SMIIO already above signal
                elif st_flip_green and smi_above:
                    pending = {\'side\': \'long\', \'entry_type\': \'BUY_B\'}

                # SELL_A: SMIIO crosses down + ST already RED
                if smi_cross_down and st == 1:
                    pending = {\'side\': \'short\', \'entry_type\': \'SELL_A\'}

                # SELL_B: ST flips RED + SMIIO already below signal
                elif st_flip_red and smi_below:
                    pending = {\'side\': \'short\', \'entry_type\': \'SELL_B\'}

            # ----------------------------------------------------------
            # EXECUTE PENDING: confirmation brick closes in signal direction
            # entry executes at current bar (i)
            # ----------------------------------------------------------
            if pending is not None and current_direction is None:
                side = pending[\'side\']

                # Cancel stale pending if ST flips against it
                if side == \'long\' and st == 1:
                    pending = None
                elif side == \'short\' and st == -1:
                    pending = None

                elif side == \'long\' and r_dir == 1:
                    signals.append({
                        \'signal_type\': \'ENTRY\',
                        \'price\':       self._apply_slippage(close, \'long\', True),
                        \'timestamp\':   ts,
                        \'sl_price\':    close - box * 2,
                        \'entry_type\':  pending[\'entry_type\'],
                        \'exit_type\':   \'\',
                        \'direction\':   \'long\',
                    })
                    current_direction = \'long\'
                    pending           = None

                elif side == \'short\' and r_dir == -1:
                    signals.append({
                        \'signal_type\': \'ENTRY\',
                        \'price\':       self._apply_slippage(close, \'short\', True),
                        \'timestamp\':   ts,
                        \'sl_price\':    close + box * 2,
                        \'entry_type\':  pending[\'entry_type\'],
                        \'exit_type\':   \'\',
                        \'direction\':   \'short\',
                    })
                    current_direction = \'short\'
                    pending           = None

        return signals'''

new_method = '''    def generate_signals(self) -> list:
        df = self._build_renko_df()
        timestamps = df['timestamp'].values
        n = len(df)
        box = self.renko_box

        closes    = df['renko_close'].values
        renko_dir = df['renko_dir'].values

        # --- SupertrendIndicator ---
        st_ind = SupertrendIndicator(
            atr_period=self.st_atr_length,
            factor=self.st_factor,
        )
        df_st  = st_ind.calculate(df)
        st_dir = df_st['st_dir'].values

        # --- SMIIO ---
        smi, sig = compute_smiio(
            closes,
            short_len=self.smiio_shortlen,
            long_len=self.smiio_longlen,
            signal_len=self.smiio_siglen,
        )

        # --- Signal loop ---
        signals           = []
        current_direction = None
        pending           = None
        pending_set_bar   = -1
        last_exit_ts      = None

        for i in range(1, n):
            ts    = str(pd.Timestamp(timestamps[i]).strftime(\'%Y-%m-%dT%H:%M:%S\'))
            close = closes[i]
            r_dir = renko_dir[i]
            st    = st_dir[i]
            prev_st = st_dir[i - 1]

            smi_cross_up   = smi[i] > sig[i] and smi[i - 1] <= sig[i - 1]
            smi_cross_down = smi[i] < sig[i] and smi[i - 1] >= sig[i - 1]
            st_flip_green  = prev_st == 1  and st == -1
            st_flip_red    = prev_st == -1 and st == 1
            smi_above      = smi[i] > sig[i]
            smi_below      = smi[i] < sig[i]

            # FIX 2: Cancel pending if not confirmed within 1 bar
            if pending is not None and i > pending_set_bar + 1:
                pending = None
                pending_set_bar = -1

            # ----------------------------------------------------------
            # EXIT: ST flip confirmed
            # ----------------------------------------------------------
            if current_direction == \'long\' and st_flip_red and r_dir == -1:
                signals.append({
                    \'signal_type\': \'EXIT\',
                    \'price\':       self._apply_slippage(close, \'long\', False),
                    \'timestamp\':   ts,
                    \'sl_price\':    close - box,
                    \'entry_type\':  \'\',
                    \'exit_type\':   \'ST_FLIP_RED\',
                    \'direction\':   \'long\',
                })
                current_direction = None
                pending           = None
                pending_set_bar   = -1
                last_exit_ts      = ts

            elif current_direction == \'short\' and st_flip_green and r_dir == 1:
                signals.append({
                    \'signal_type\': \'EXIT\',
                    \'price\':       self._apply_slippage(close, \'short\', False),
                    \'timestamp\':   ts,
                    \'sl_price\':    close + box,
                    \'entry_type\':  \'\',
                    \'exit_type\':   \'ST_FLIP_GREEN\',
                    \'direction\':   \'short\',
                })
                current_direction = None
                pending           = None
                pending_set_bar   = -1
                last_exit_ts      = ts

            # ----------------------------------------------------------
            # SET PENDING — FIX 1: skip same bar as exit
            #             — FIX 3: single if/elif chain
            # ----------------------------------------------------------
            if current_direction is None and ts != last_exit_ts:

                if smi_cross_up and st == -1:
                    pending = {\'side\': \'long\', \'entry_type\': \'BUY_A\'}
                    pending_set_bar = i

                elif st_flip_green and smi_above:
                    pending = {\'side\': \'long\', \'entry_type\': \'BUY_B\'}
                    pending_set_bar = i

                elif smi_cross_down and st == 1:
                    pending = {\'side\': \'short\', \'entry_type\': \'SELL_A\'}
                    pending_set_bar = i

                elif st_flip_red and smi_below:
                    pending = {\'side\': \'short\', \'entry_type\': \'SELL_B\'}
                    pending_set_bar = i

            # ----------------------------------------------------------
            # EXECUTE PENDING
            # ----------------------------------------------------------
            if pending is not None and current_direction is None:
                side = pending[\'side\']

                if side == \'long\' and st == 1:
                    pending = None
                    pending_set_bar = -1

                elif side == \'short\' and st == -1:
                    pending = None
                    pending_set_bar = -1

                elif side == \'long\' and r_dir == 1:
                    signals.append({
                        \'signal_type\': \'ENTRY\',
                        \'price\':       self._apply_slippage(close, \'long\', True),
                        \'timestamp\':   ts,
                        \'sl_price\':    close - box * 2,
                        \'entry_type\':  pending[\'entry_type\'],
                        \'exit_type\':   \'\',
                        \'direction\':   \'long\',
                    })
                    current_direction = \'long\'
                    pending           = None
                    pending_set_bar   = -1

                elif side == \'short\' and r_dir == -1:
                    signals.append({
                        \'signal_type\': \'ENTRY\',
                        \'price\':       self._apply_slippage(close, \'short\', True),
                        \'timestamp\':   ts,
                        \'sl_price\':    close + box * 2,
                        \'entry_type\':  pending[\'entry_type\'],
                        \'exit_type\':   \'\',
                        \'direction\':   \'short\',
                    })
                    current_direction = \'short\'
                    pending           = None
                    pending_set_bar   = -1

        return signals'''

if old_method in content:
    content = content.replace(old_method, new_method)
    with open(filepath, 'w') as f:
        f.write(content)
    print('SUCCESS: generate_signals method replaced with 3 fixes applied')
else:
    print('ERROR: old method not found - content may have changed')
    print('Searching for key signature...')
    if 'pending           = None' in content and 'last_exit_ts' not in content:
        print('File looks like GitHub version but exact match failed')
        print('Check for whitespace or encoding differences')
    elif 'last_exit_ts' in content:
        print('File already has last_exit_ts - fix already applied')
    else:
        print('Unknown state - check file manually')
