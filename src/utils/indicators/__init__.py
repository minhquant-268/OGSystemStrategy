"""
indicators package
==================
Thu vien indicator ky thuat cho toan bo he thong.

Moi indicator = 1 file rieng de de doc, test va them moi.

Import theo package:
    from src.utils.indicators.indicator_MA   import calculate_sma, calculate_ema
    from src.utils.indicators.indicator_MACD import calculate_macd
    from src.utils.indicators.indicator_ATR  import calculate_atr
    from src.utils.indicators.indicator_RSI  import calculate_rsi
    from src.utils.indicators.indicator_BollingerBands import calculate_bollinger_bands
    from src.utils.indicators.indicator_ADX  import calculate_adx

Danh sach file:
    indicator_MA.py             -> calculate_sma(), calculate_ema()
    indicator_MACD.py           -> calculate_macd()  -> (macd, signal, hist)
    indicator_ATR.py            -> calculate_atr()   -> pd.Series
    indicator_RSI.py            -> calculate_rsi()   -> pd.Series
    indicator_BollingerBands.py -> calculate_bollinger_bands() -> (upper, mid, lower)
                                   calculate_bb_percent_b()    -> pd.Series
                                   calculate_bb_bandwidth()    -> pd.Series
    indicator_ADX.py            -> calculate_adx()  -> (adx, plus_di, minus_di)
"""
