#!/bin/bash
tail -F logs/renko_state_engine.log | grep --line-buffered -iE "New 30m candle closed|New 2H candle closed|New 4H candle closed|REPAINT GUARD|boundary.*STILL not caught up|reconcile failed" >> logs/watch_alerts.log
