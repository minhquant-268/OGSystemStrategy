# Module Strategies — Tai Lieu Trien Khai

> **Module**: Strategies Layer + Engine
> **Vi tri**: `src/strategies/`, `src/core/strategy_engine.py`
> **Ngay cap nhat**: 2026-03-07
> **Trang thai**: Done — 3 strategies + StrategyEngine da implement va test OK

---

## 1. Tong Quan

Tang strategy la trung tam xu ly logic giao dich. Moi strategy nhan vao DataFrame nen (OHLCV) va tra ve DataFrame duoc bo sung them cac cot tin hieu (signal, entry, sl, tp, ...).

### Nguyen tac thiet ke

- Moi strategy = 1 class ke thua `BaseStrategy` trong [`base_strategy.py`](../src/strategies/base_strategy.py)
- Moi strategy = 1 file rieng biet → de them moi, de test doc lap
- **Stateless**: Moi lan goi `calculate_signals()` la doc lap, khong luu trang thai
- **Khong raise exception ra ngoai**: Luon tra ve df (du co loi)
- **Khong tu loc symbol/timeframe**: Strategy chi tinh toan; viec loc du lieu la trach nhiem cua `strategy_engine`

### Phan chia trach nhiem (Cach A)

```
config/strategy_list.json          <- Khai bao strategy + danh sach (symbol, timeframe) chay
        |
        v
src/core/strategy_engine.py        <- Doc config, loc df theo (provider, symbol, timeframe),
        |                             goi calculate_signals(df) voi df sach 1 cap
        v
src/strategies/strategy_*.py       <- Chi xet logic indicator + signal, KHONG tu loc du lieu
```

**Luon flow mau du lieu:**

```
keyspace_monitor.py  (nhan event Redis)
     |
     v
strategy_engine.py   (loc df: df_clean = df[(df.symbol==X) & (df.timeframe==Y)])
     |
     v  df_clean cua dung 1 (symbol, timeframe)
strategy.calculate_signals(df_clean)
     |
     v  df co them signal, entry, sl, tp, ...
redis_publisher.py   (phat tin hieu ra Redis)
```

### Cau truc thu muc

```
src/strategies/
+-- base_strategy.py          # Abstract base class
+-- strategy_comboATR.py      # MACD + SMA + ATR
+-- strategy_MAcrossover.py   # EMA golden/death cross + ATR
+-- strategy_RSI.py           # RSI overbought/oversold + ATR

src/core/
+-- strategy_engine.py        # Engine dieu phoi (load config, filter, run)

config/
+-- strategy_list.json        # Khai bao strategy + (symbol, timeframe) chay

tests/
+-- test_strategies.py        # Unit test strategy + engine
```

### Quy uoc signal

| Gia tri | Y nghia |
|---|---|
| `0` | Hold — khong co tin hieu |
| `1` | BUY signal |
| `2` | SELL signal |

---

## 2. Config Strategy (`config/strategy_list.json`)

File [`config/strategy_list.json`](../config/strategy_list.json) dinh nghia toan bo strategy duoc chay.

**5 field duy nhat — don gian, khong thua:**

```json
[
  {
    "name": "comboATR",
    "enabled": true,
    "class": "src.strategies.strategy_comboATR.ComboATRStrategy",
    "symbols": ["BTCUSD"],
    "timeframes": ["10", "15"]
  },
  {
    "name": "MAcrossover",
    "enabled": true,
    "class": "src.strategies.strategy_MAcrossover.MACrossoverStrategy",
    "symbols": ["BTCUSD", "US30"],
    "timeframes": ["60"]
  },
  {
    "name": "RSI",
    "enabled": false,
    "class": "src.strategies.strategy_RSI.RSIStrategy",
    "symbols": "all",
    "timeframes": "all"
  }
]
```

**Giai thich cac field:**

| Field | Kieu | Mo ta |
|---|---|---|
| `name` | string | Ten strategy (de log va debug) |
| `enabled` | bool | `true`/`false` — engine chi chay strategy dang bat |
| `class` | string | Duong dan import day du den class |
| `symbols` | list\[str\] \| `"all"` | Danh sach symbol can chay; `"all"` = lay tat ca tu df |
| `timeframes` | list\[str\] \| `"all"` | Danh sach timeframe can chay; `"all"` = lay tat ca tu df |

**Params khong co trong config** — strategy su dung default values cua `__init__`.
Neu muon tuy chinh (macd_fast, sma_period, ...), sua truc tiep trong file strategy.

**Cartesian product:** Engine tu tinh `symbols x timeframes`. Vi du:
`symbols=["BTCUSD", "US30"]` + `timeframes=["10","60"]` → 4 runs doc lap.

**strategy_engine su dung config nay de:**
1. Dynamic import class qua `importlib`
2. Khoi tao instance voi default params: `strategy = StrategyClass()`
3. Tinh cartesian product `symbols x timeframes` → tung cap duoc xu ly doc lap
4. Loc df, goi `calculate_signals(df_filtered)` cho tung cap

---

## 3. BaseStrategy (`base_strategy.py`)

File: [`src/strategies/base_strategy.py`](../src/strategies/base_strategy.py)

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

## 4. ComboATR Strategy (`strategy_comboATR.py`)

File: [`src/strategies/strategy_comboATR.py`](../src/strategies/strategy_comboATR.py)

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

# df_clean da duoc strategy_engine loc san cho 1 (symbol, timeframe)
df_result = strategy.calculate_signals(df_clean)
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

**Indicators su dung:**
- `calculate_macd()` — [`src/utils/indicators/MACD.py`](../src/utils/indicators/MACD.py)
- `calculate_sma()` — [`src/utils/indicators/MA.py`](../src/utils/indicators/MA.py)
- `calculate_atr()` — [`src/utils/indicators/ATR.py`](../src/utils/indicators/ATR.py)

---

## 5. MACrossover Strategy (`strategy_MAcrossover.py`)

File: [`src/strategies/strategy_MAcrossover.py`](../src/strategies/strategy_MAcrossover.py)

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
df_result = strategy.calculate_signals(df_clean)
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
- Chi phat sinh signal TAI DEM cat — khong repeat khi dang trong cung chieu
- Tin hieu it hon ComboATR nhung manh hon (crossover la su kien hiem)
- Phu hop cho cac timeframe lon (H1, H4)

**Indicators su dung:**
- `calculate_ema()` — [`src/utils/indicators/MA.py`](../src/utils/indicators/MA.py)
- `calculate_atr()` — [`src/utils/indicators/ATR.py`](../src/utils/indicators/ATR.py)

---

## 6. RSI Strategy (`strategy_RSI.py`)

File: [`src/strategies/strategy_RSI.py`](../src/strategies/strategy_RSI.py)

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
df_result = strategy.calculate_signals(df_clean)
```

**Cot them vao DataFrame:**

| Cot | Mo ta |
|---|---|
| `RSI` | RSI indicator [0-100] |
| `ATR` | Average True Range |
| `signal` | 0/1/2 |
| `entry`, `sl`, `tp`, `sl_distance`, `tp_distance` | Gia vao/SL/TP |

**Indicators su dung:**
- `calculate_rsi()` — [`src/utils/indicators/RSI.py`](../src/utils/indicators/RSI.py)
- `calculate_atr()` — [`src/utils/indicators/ATR.py`](../src/utils/indicators/ATR.py)

---

## 7. So Sanh 3 Strategies

| Dac diem | ComboATR | MACrossover | RSI |
|---|---|---|---|
| **Indicator chinh** | MACD + SMA | EMA crossover | RSI |
| **Filter** | SMA + bullish/bearish candle | Khong | Khong |
| **Tan suat tin hieu** | Trung binh | It (chi tai crossover) | Phu thuoc nguong |
| **Phu hop timeframe** | M5-M30 | H1-H4 | M5-H1 |
| **Tham so quan trong** | `macd_slow`, `sma_period`, `kTP` | `short_period`, `long_period` | `rsi_period`, `overbought`/`oversold` |
| **Ro rang ve xu huong** | Tot (SMA filter) | Rat tot (crossover) | Kem (chi do luc) |

---

## 8. Them Strategy Moi

**Buoc 1:** Tao file `src/strategies/strategy_MyNew.py`

```python
from src.strategies.base_strategy import BaseStrategy
import pandas as pd

class MyNewStrategy(BaseStrategy):
    def __init__(self, param1=10):
        super().__init__(name="MyNew")
        self.param1 = param1

    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Nhan df cua DUNG MOT cap (symbol, timeframe) da duoc strategy_engine loc san.
        KHONG tu loc symbol hay timeframe ben trong ham nay.
        """
        if not self.validate_df(df):
            return df
        df = df.copy()
        # ... logic tinh indicator va signal ...
        df["signal"] = 0
        return df
```

**Buoc 2:** Dang ky trong [`config/strategy_list.json`](../config/strategy_list.json):
```json
{
  "name": "MyNew",
  "enabled": true,
  "class": "src.strategies.strategy_MyNew.MyNewStrategy",
  "params": {"param1": 10},
  "symbols": [
    {"provider": "CAPITALCOM", "symbol": "BTCUSD", "timeframe": "m10"}
  ]
}
```

**Buoc 3:** Strategy engine se tu dong load qua dynamic import va goi `calculate_signals()` voi df da duoc loc.

---

## 9. Ket Qua Test Thuc Te

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

---

## 11. StrategyEngine (`strategy_engine.py`)

File: [`src/core/strategy_engine.py`](../src/core/strategy_engine.py)

Engine dieu phoi cac strategy: doc config, loc df, goi `calculate_signals()`, tra ve ket qua.

### Khoi tao
```python
from src.core.strategy_engine import StrategyEngine

engine = StrategyEngine(config_path="config/strategy_list.json")
```

### Chay voi DataFrame
```python
# df co the chua nhieu symbol va timeframe
results = engine.run(df)

for r in results:
    print(r.strategy_name, r.symbol, r.timeframe)
    print(r.df_result[["date_time", "signal", "entry", "sl", "tp"]])
```

### StrategyResult
```python
@dataclass
class StrategyResult:
    strategy_name : str            # Ten strategy (vd: "comboATR")
    provider      : str            # Provider (vd: "CAPITALCOM") - lay tu df neu co
    symbol        : str            # Symbol (vd: "BTCUSD")
    timeframe     : str            # Timeframe (vd: "10")
    df_result     : pd.DataFrame   # DataFrame da duoc bo sung signal + indicator
```

### Luong xu ly ben trong engine
```python
# Pseudo-code cua engine.run(df):
for strategy_cfg in self._configs:               # Moi strategy trong config
    if not strategy_cfg.enabled: continue
    strategy = dynamic_import(strategy_cfg.class_)  # Dung default params
    for (sym, tf) in cartesian(symbols, timeframes): # symbols x timeframes
        df_clean = filter_df(df, sym, tf)            # Loc df -> 1 cap duy nhat
        df_result = strategy.calculate_signals(df_clean)
        results.append(StrategyResult(...))
```

### symbols va timeframes = "all"
Neu config khai bao `"all"`, engine tu dong lay tat ca gia tri duy nhat trong df.

```json
// Chi dinh tuong minh:
{"symbols": ["BTCUSD", "US30"], "timeframes": ["10", "60"]}
// Chay tat ca:
{"symbols": "all", "timeframes": "all"}
```

---

## 12. Chay Test

```bash
# Chay tat ca tests
pytest tests/test_strategies.py -v

# Chi test 1 strategy
pytest tests/test_strategies.py -v -k "TestComboATR"

# Chi test engine
pytest tests/test_strategies.py -v -k "TestStrategyEngine"

# Smoke test nhanh (khong can pytest)
python tests/test_strategies.py
```

---

## 13. Module Tiep Theo Can Implement

```
src/core/keyspace_monitor.py  <- Lang nghe Redis event, goi engine.run(df)
src/core/redis_publisher.py   <- Ghi OG/signal len Redis sau khi co ket qua
```

**Giao dien du kien voi strategy_engine:**
```python
# Trong keyspace_monitor.py:
from src.core.strategy_engine import StrategyEngine

engine = StrategyEngine()  # Load 1 lan khi startup

def on_new_candle(df: pd.DataFrame):
    results = engine.run(df)
    for r in results:
        redis_publisher.publish(r)
```
