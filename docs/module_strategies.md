# Module Strategies -- Tai Lieu Trien Khai

> **Module**: Strategies Layer
> **Vi tri**: `src/strategies/`
> **Ngay cap nhat**: 2026-03-07
> **Trang thai**: Done -- 3 strategies da implement va test OK

---

## 1. Tong Quan

Tang strategy la trung tam xu ly logic giao dich. Moi strategy nhan vao DataFrame nen (OHLCV) va tra ve DataFrame buoc sung them cac cot tin hieu (signal, entry, sl, tp, ...).

**Nguyen tac thiet ke:**
- Moi strategy = 1 class ke thua `BaseStrategy`
- Moi strategy = 1 file rieng biet -> de them moi, de test doc lap
- Khong co trang thai toan cuc (stateless) -> moi lan goi `calculate_signals()` la doc lap
- Khong raise exception ra ngoai -> luon tra ve df (du co loi)

```
src/strategies/
+-- __init__.py
+-- base_strategy.py          # Abstract base class
+-- strategy_comboATR.py      # MACD + SMA + ATR
+-- strategy_MAcrossover.py   # EMA golden/death cross + ATR
+-- strategy_RSI.py           # RSI overbought/oversold + ATR
```

**Quy uoc signal:**

| Gia tri | Y nghia |
|---|---|
| `0` | Hold -- khong co tin hieu |
| `1` | BUY signal |
| `2` | SELL signal |

---

## 2. BaseStrategy (`base_strategy.py`)

Tat ca strategy bat buoc ke thua `BaseStrategy`:

```python
from src.strategies.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(name="MyStrategy")

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # ... logic ...
        df["signal"] = 0
        return df
```

**Phuong thuc cua BaseStrategy:**

| Phuong thuc | Bat buoc | Mo ta |
|---|---|---|
| `calculate_signals(df)` | Yes (abstractmethod) | Tinh toan va tra ve df co them signal |
| `get_indicators(df)` | No (optional) | Tra ve dict indicator de chart/debug |
| `validate_df(df, required_cols)` | No (helper) | Kiem tra df hop le truoc khi xu ly |

**validate_df:**
```python
# Goi o dau calculate_signals() de bao ve khoi input loi
if not self.validate_df(df, required_cols=["open", "high", "low", "close"]):
    return df
```

---

## 3. ComboATR Strategy (`strategy_comboATR.py`)

**Logic:**
```
BUY  khi: nen tang (close>open) AND gia tren SMA AND MACD duong (MACD>0)
SELL khi: nen giam (close<open) AND gia duoi SMA AND MACD am (MACD<0)
SL   = entry +/- kSL * ATR
TP   = entry +/- kTP * ATR
```

**Khoi tao:**
```python
from src.strategies.strategy_comboATR import ComboATRStrategy

strategy = ComboATRStrategy(
    macd_fast=5,      # Chu ky EMA nhanh MACD
    macd_slow=25,     # Chu ky EMA cham MACD
    macd_signal=5,    # Chu ky signal line
    sma_period=20,    # Chu ky SMA filter trend
    atr_period=5,     # Chu ky ATR cho SL/TP
    kSL=2.3,          # SL = 2.3 x ATR
    kTP=5.3,          # TP = 5.3 x ATR
)
df_result = strategy.calculate_signals(df)
```

**Cot them vao DataFrame:**

| Cot | Kieu | Mo ta |
|---|---|---|
| `MACD` | float | MACD line |
| `MACD_Signal` | float | Signal line cua MACD |
| `MACD_Hist` | float | Histogram = MACD - Signal |
| `SMA` | float | Simple Moving Average |
| `ATR` | float | Average True Range (Wilder) |
| `signal` | int | 0/1/2 |
| `entry` | float | Gia vao lenh (=close tai nen co tin hieu) |
| `sl` | float | Gia Stop Loss |
| `tp` | float | Gia Take Profit |
| `sl_distance` | float | Khoang cach SL (= kSL * ATR) |
| `tp_distance` | float | Khoang cach TP (= kTP * ATR) |

**Cong thuc SL/TP:**
```
BUY  entry = close
     sl    = close - kSL * ATR   (duoi entry)
     tp    = close + kTP * ATR   (tren entry)

SELL entry = close
     sl    = close + kSL * ATR   (tren entry)
     tp    = close - kTP * ATR   (duoi entry)
```

**Indicators dung:** `MACD` (tu `MA.py`), `SMA` (tu `MA.py`), `ATR` (tu `ATR.py`)

---

## 4. MACrossover Strategy (`strategy_MAcrossover.py`)

**Logic:**
```
BUY  khi: EMA_short cat len tren EMA_long (golden cross)
SELL khi: EMA_short cat xuong duoi EMA_long (death cross)
SL   = entry +/- kSL * ATR
TP   = entry +/- kTP * ATR
```

**Khoi tao:**
```python
from src.strategies.strategy_MAcrossover import MACrossoverStrategy

strategy = MACrossoverStrategy(
    short_period=10,  # Chu ky EMA ngan
    long_period=30,   # Chu ky EMA dai
    atr_period=5,     # Chu ky ATR cho SL/TP
    kSL=2.0,          # SL = 2.0 x ATR
    kTP=4.0,          # TP = 4.0 x ATR
)
df_result = strategy.calculate_signals(df)
```

**Cot them vao DataFrame:**

| Cot | Mo ta |
|---|---|
| `MA_Short` | EMA ngan han |
| `MA_Long` | EMA dai han |
| `ATR` | Average True Range |
| `signal` | 0/1/2 |
| `entry`, `sl`, `tp`, `sl_distance`, `tp_distance` | Gia vao/SL/TP |

**Dac diem crossover:**
- Chi phat sinh signal TAI DEM cat -- khong repeat khi dang trong cung chieu
- Tin hieu it hon ComboATR nhung manh hon (crossover la su kien hiem)
- Phu hop cho cac timeframe lon (H1, H4)

**Indicators dung:** `calculate_ema` (tu `MA.py`), `calculate_atr` (tu `ATR.py`)

---

## 5. RSI Strategy (`strategy_RSI.py`)

**Logic:**
```
BUY  khi: RSI < oversold  (mac dinh 30) -- qua ban
SELL khi: RSI > overbought (mac dinh 70) -- qua mua
SL   = entry +/- kSL * ATR
TP   = entry +/- kTP * ATR
```

**Khoi tao:**
```python
from src.strategies.strategy_RSI import RSIStrategy

strategy = RSIStrategy(
    rsi_period=14,    # Chu ky RSI
    overbought=70.0,  # Nguong qua mua -> SELL
    oversold=30.0,    # Nguong qua ban -> BUY
    atr_period=5,     # Chu ky ATR cho SL/TP
    kSL=1.5,          # SL = 1.5 x ATR
    kTP=3.0,          # TP = 3.0 x ATR
)
df_result = strategy.calculate_signals(df)
```

**Cot them vao DataFrame:**

| Cot | Mo ta |
|---|---|
| `RSI` | RSI indicator [0-100] |
| `ATR` | Average True Range |
| `signal` | 0/1/2 |
| `entry`, `sl`, `tp`, `sl_distance`, `tp_distance` | Gia vao/SL/TP |

**Indicators dung:** `calculate_rsi` (tu `RSI.py`), `calculate_atr` (tu `ATR.py`)

---

## 6. So Sanh 3 Strategies

| Dac diem | ComboATR | MACrossover | RSI |
|---|---|---|---|
| **Indicator chinh** | MACD + SMA | EMA crossover | RSI |
| **Filter** | SMA + bullish/bearish candle | Khong | Khong |
| **Tan suat tin hieu** | Trung binh | It (chi tai crossover) | Phu thuoc nguong |
| **Phu hop timeframe** | M5-M30 | H1-H4 | M5-H1 |
| **Tham so quan trong** | `macd_slow`, `sma_period`, `kTP` | `short_period`, `long_period` | `rsi_period`, `overbought`/`oversold` |
| **Ro rang ve xu huong** | Tot (SMA filter) | Rat tot (crossover) | Kem (chi do luc) |

---

## 7. Them Strategy Moi

**Buoc 1:** Tao file `src/strategies/strategy_MyNew.py`

```python
from src.strategies.base_strategy import BaseStrategy
import pandas as pd

class MyNewStrategy(BaseStrategy):
    def __init__(self, param1=10):
        super().__init__(name="MyNew")
        self.param1 = param1

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.validate_df(df):
            return df
        df = df.copy()
        # ... logic ...
        df["signal"] = 0
        return df
```

**Buoc 2:** Dang ky trong `config/strategy_list.json`:
```json
{
  "name": "MyNew",
  "enabled": true,
  "class": "src.strategies.strategy_MyNew.MyNewStrategy",
  "params": {"param1": 10},
  "symbols": [{"provider": "CAPITALCOM", "symbol": "BTCUSD", "timeframe": "m10"}]
}
```

**Buoc 3:** Strategy engine se tu dong load qua dynamic import.

---

## 8. Ket Qua Test Thuc Te

Chay tren 100 nen gia lap (seed=0):

```
ComboATR   : 100 nen | BUY=2 SELL=1 | SL/TP check: OK
  2026-01-01 07:00  signal=2  entry=104.16  sl=105.79  tp=100.42
  2026-01-01 14:50  signal=1  entry=100.29  sl=98.36   tp=104.74

MACrossover: 100 nen | BUY=2 SELL=1 | SL/TP check: OK
  2026-01-01 07:00  signal=2  entry=104.16  sl=105.57  tp=101.34
  2026-01-01 14:30  signal=1  entry=100.30  sl=98.67   tp=103.57

RSIStrategy: 100 nen | BUY=1 SELL=1 | SL/TP check: OK
  2026-01-01 08:20  signal=1  entry=103.07  sl=101.92  tp=105.35
  2026-01-01 15:40  signal=2  entry=101.47  sl=102.50  tp=99.42

ALL STRATEGIES OK
```

---

## 9. Buoc Tiep Theo

```
Module tiep theo -> src/core/strategy_engine.py  (load strategy tu config, goi calculate_signals)
                 -> src/core/keyspace_monitor.py  (lang nghe Redis event, trigger engine)
                 -> src/core/redis_publisher.py   (ghi OG/signal len Redis)
                 -> tests/test_strategies.py      (unit test tung strategy)
```
