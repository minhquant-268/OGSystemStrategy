"""
strategies package
==================
Chua tat ca trading strategy cua he thong.

Moi strategy:
    - Ke thua BaseStrategy
    - Implement calculate_signals(df) -> df co them cot signal, entry, sl, tp
    - (Tuy chon) Implement get_indicators(df) -> dict de chart/debug

Danh sach strategy hien co:
    ComboATR    : MACD + SMA + ATR   -> strategy_comboATR.py
    MACrossover : EMA golden/death cross + ATR -> strategy_MAcrossover.py
    RSI         : RSI oversold/overbought + ATR -> strategy_RSI.py

Quy uoc signal:
    0 = Hold (khong co tin hieu)
    1 = BUY
    2 = SELL
"""
