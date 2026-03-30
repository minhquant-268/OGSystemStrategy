# KNN Trend Navigator — Mô tả logic tính toán chi tiết

> Port từ PineScript **AI Trend Navigator** (Zeiierman).
> File code: `src/indicators/KNN_trend.py`

---

## Tổng quan

KNN Trend sử dụng thuật toán **K-Nearest Neighbors** để:
1. Tạo đường xu hướng thông minh (KNN Moving Average)
2. Phân loại xu hướng bullish/bearish (KNN Prediction)
3. Sinh tín hiệu giao dịch (crossover, switch, ...)

---

## Step 1: Tính Price Value (`value_in`)

Lấy giá theo phương pháp được chọn, rồi làm mượt bằng MA.

| `price_method` | Công thức |
|----------------|-----------|
| `"hl2"` (mặc định) | `SMA((high + low) / 2, ma_len)` |
| `"sma"` | `SMA(close, ma_len)` |
| `"ema"` | `EMA(close, ma_len)` |
| `"wma"` | `WMA(close, ma_len)` |
| `"hma"` | `HMA(close, ma_len)` |

**Vai trò**: Đây là **dữ liệu đầu vào** để KNN tìm kiếm trong quá khứ.

---

## Step 2: Tính Target Value (`target_in`)

Lấy giá mục tiêu theo phương pháp khác.

| `target_method` | Công thức |
|-----------------|-----------|
| `"rma"` (mặc định) | `RMA(close, target_ma_len)` = Wilder smoothing |
| `"sma"` | `SMA(close, target_ma_len)` |
| `"ema"` | `EMA(close, target_ma_len)` |
| `"wma"` | `WMA(close, target_ma_len)` |
| `"hma"` | `HMA(close, target_ma_len)` |
| `"atr"` | `ATR(14)` — Average True Range |

**Vai trò**: Đây là **giá trị tham chiếu** mà KNN so sánh khoảng cách.

---

## Step 3: KNN Moving Average (`meanOfKClosest`) ⭐

### Bài toán
> "Giá hiện tại đang ở vùng nào? Hãy tìm trong quá khứ những lúc giá **tương tự nhất**, rồi lấy trung bình để dự đoán."

### Thuật toán

Với **mỗi nến hiện tại** (index `i`):

1. Khởi tạo mảng `n_neighbors` phần tử:
   ```
   closest_distances = [1e10, 1e10, 1e10]   ← khoảng cách (rất lớn ban đầu)
   closest_values    = [0.0,  0.0,  0.0]    ← giá trị tương ứng
   ```

2. Duyệt `window_size = max(n_neighbors, 30)` nến quá khứ (nến `i-1` → nến `i-window_size`):
   ```
   distance = |target_in[i] - value_in[i-j]|
   ```

3. Với mỗi nến quá khứ:
   - Tìm **vị trí có khoảng cách lớn nhất** trong mảng `closest_distances`
   - Nếu `distance` mới **nhỏ hơn** khoảng cách lớn nhất đó → **thay thế**

4. Kết quả: lấy trung bình cộng của `n_neighbors` giá trị gần nhất:
   ```
   knn_ma_raw[i] = sum(closest_values) / n_neighbors
   ```

### Ví dụ cụ thể

`n_neighbors = 3`, `window_size = 30`, nến hiện tại #100, `target_in[100] = 105.2`:

```
Nến #99: value_in = 103.0  → distance = |105.2 - 103.0| = 2.2
Nến #98: value_in = 105.5  → distance = |105.2 - 105.5| = 0.3  ← gần!
Nến #97: value_in = 108.0  → distance = |105.2 - 108.0| = 2.8
Nến #96: value_in = 104.9  → distance = |105.2 - 104.9| = 0.3  ← gần!
Nến #95: value_in = 101.0  → distance = |105.2 - 101.0| = 4.2
Nến #94: value_in = 105.0  → distance = |105.2 - 105.0| = 0.2  ← gần nhất!
...duyệt đến nến #70
```

Quá trình cập nhật mảng:

```
Ban đầu:      distances = [1e10,  1e10,  1e10]    values = [0,     0,     0    ]

Sau nến #99:  distances = [2.2,   1e10,  1e10]    values = [103.0, 0,     0    ]
Sau nến #98:  distances = [2.2,   0.3,   1e10]    values = [103.0, 105.5, 0    ]
Sau nến #97:  distances = [2.2,   0.3,   2.8 ]    values = [103.0, 105.5, 108.0]
Sau nến #96:  distances = [2.2,   0.3,   0.3 ]    values = [103.0, 105.5, 104.9]
                           ↑ 2.8 lớn nhất bị thay bằng 0.3, 108.0→104.9
Sau nến #94:  distances = [0.2,   0.3,   0.3 ]    values = [105.0, 105.5, 104.9]
                           ↑ 2.2 lớn nhất bị thay bằng 0.2, 103.0→105.0
```

**Kết quả**: `knn_ma_raw[100] = (105.0 + 105.5 + 104.9) / 3 = 105.13`

### Tại sao cách này hiệu quả?

| Yếu tố | Giải thích |
|---------|-----------|
| **Lọc nhiễu** | Chỉ lấy nến có giá tương tự → bỏ qua spike/outlier |
| **Adaptive** | Tự điều chỉnh theo vùng giá hiện tại, không cứng nhắc như SMA/EMA |
| **n_neighbors nhỏ (3)** | Nhạy hơn, bám sát giá → phản ứng nhanh |
| **n_neighbors lớn (50+)** | Mượt hơn, ít nhiễu → phản ứng chậm |
| **window_size (30)** | Phạm vi tìm kiếm: chỉ nhìn 30 nến gần nhất |

---

## Step 4: Smooth KNN MA

Từ `knn_ma_raw`, tạo 2 đường:

```
knn_ma  = WMA(knn_ma_raw, 5)              ← đường xu hướng chính (NHANH)
knn_avg = RMA(knn_ma_raw, smoothing_period) ← đường trung bình chậm (THAM CHIẾU)
```

- `knn_ma` phản ứng nhanh → dùng để bắt tín hiệu
- `knn_avg` phản ứng chậm → dùng làm mốc so sánh (như đường MA chậm trong hệ MA crossover)

---

## Step 5: KNN Prediction (Classifier) ⭐

### Mục đích
> Phân loại xu hướng hiện tại là **bullish (+1)** hay **bearish (-1)** dựa trên "KNN candle".

### Bước 5.1: Tạo "KNN Candle"

Biến đường `knn_ma_raw` thành **nến giả** (pseudo-candle):

```
price = (knn_ma_raw + close) / 2           ← giá tham chiếu để tính distance

c = RMA(knn_ma_raw[shift 1 nến], 50)       ← "close" của nến KNN (trễ 1 nến, smooth mạnh)
o = RMA(knn_ma_raw, 50)                    ← "open" của nến KNN (smooth mạnh)
```

**Cách đọc nến KNN**:
- `c < o` → nến KNN **TĂNG** (close cũ < open mới) → **Bullish** ✅
- `c > o` → nến KNN **GIẢM** → **Bearish** ❌

Ví dụ:
```
Nến #50:  c = 104.0,  o = 104.5  →  c < o  →  Bullish ✅
Nến #51:  c = 104.3,  o = 104.1  →  c > o  →  Bearish ❌
```

### Bước 5.2: Tìm nến gần nhất (KNN Classification)

Với **mỗi nến hiện tại**, duyệt **10 nến trước**:

```
for j = 1 to 10:
    distance = sqrt((price[hiện tại - j] - price[hiện tại])²)
    # Tìm nến có distance NHỎ NHẤT
```

Ví dụ tại nến #100, `price[100] = 105.0`:

```
j=1:  price[99] = 105.3  → distance = 0.3
j=2:  price[98] = 104.1  → distance = 0.9
j=3:  price[97] = 106.5  → distance = 1.5
j=4:  price[96] = 105.1  → distance = 0.1  ← NHỎ NHẤT!
j=5:  price[95] = 103.0  → distance = 2.0
...
j=10: price[90] = 107.2  → distance = 2.2
```

### Bước 5.3: Đếm Pos / Neg

**Điểm đặc biệt**: Mỗi khi tìm được nến gần hơn (distance nhỏ hơn min trước đó), thuật toán **cộng dồn** Pos hoặc Neg ngay lập tức:

```
j=1: distance=0.3 < 1e10 → min mới! → c[99]=104.2, o[99]=104.5 → c<o → Pos_count=1
j=2: distance=0.9 > 0.3  → bỏ qua
j=3: distance=1.5 > 0.3  → bỏ qua
j=4: distance=0.1 < 0.3  → min mới! → c[96]=103.8, o[96]=103.5 → c>o → Neg_count=1
j=5: distance=2.0 > 0.1  → bỏ qua
...
```

### Bước 5.4: Quyết định

```
if Pos_count > Neg_count → output = +1  (BULLISH)
else                     → output = -1  (BEARISH, kể cả khi hòa)
```

### Bước 5.5: Smooth kết quả

```
knn_prediction_raw = [+1, +1, -1, +1, -1, +1, +1, ...]    ← nhảy liên tục
knn_prediction     = WMA(knn_prediction_raw, 3)             ← smooth
                   = [NaN, NaN, 0.33, 0.33, -0.33, ...]
```

- `> 0` → **bullish**
- `< 0` → **bearish**

### Sơ đồ tổng hợp

```
knn_ma_raw ──┬── (shift 1) ── RMA(50) ──→ c (close KNN candle)
             │
             └── RMA(50) ──────────────→ o (open KNN candle)

knn_ma_raw + close ── /2 ──→ price (tính distance)

Với mỗi nến:
  Duyệt 10 nến trước
  → Tìm nến có price gần nhất (cộng dồn khi tìm thấy min mới)
  → Kiểm tra c vs o tại nến đó
  → Đếm Pos/Neg
  → Pos > Neg → +1 (bullish)
  → else → -1 (bearish)
  → WMA(3) smooth
```

---

## Step 6: Tín hiệu giao dịch (Signals)

### 6.1 KNN Color

```
knn_ma hiện tại > knn_ma nến trước → knn_color = 1  (Up — đang tăng)
knn_ma hiện tại < knn_ma nến trước → knn_color = -1 (Down — đang giảm)
knn_ma hiện tại = knn_ma nến trước → knn_color = 0  (Neutral)
```

### 6.2 Crossover / Crossunder

```
cross_over_avg  = knn_ma CẮT LÊN knn_avg
                = (knn_ma > knn_avg) AND (knn_ma[1] <= knn_avg[1])
                → Tín hiệu MUA

cross_under_avg = knn_ma CẮT XUỐNG knn_avg
                = (knn_ma < knn_avg) AND (knn_ma[1] >= knn_avg[1])
                → Tín hiệu BÁN
```

### 6.3 Switch Up / Down

```
switch_up   = knn_ma[1] < knn_ma AND knn_ma[1] <= knn_ma[2]
            → Nến trước là đáy, bắt đầu TĂNG (đổi hướng lên)

switch_down = knn_ma[1] > knn_ma AND knn_ma[1] >= knn_ma[2]
            → Nến trước là đỉnh, bắt đầu GIẢM (đổi hướng xuống)
```

---

## Bảng tổng hợp Output

| Key | Type | Ý nghĩa |
|-----|------|---------|
| `knn_ma` | `pd.Series` | Đường xu hướng chính (WMA-5 smoothed) |
| `knn_avg` | `pd.Series` | Đường trung bình chậm (RMA-smoothing) |
| `knn_prediction` | `pd.Series` | `> 0` bullish, `< 0` bearish |
| `knn_color` | `pd.Series` | `1` Up, `-1` Down, `0` Neutral |
| `cross_over_avg` | `pd.Series` bool | `True` khi knn_ma cắt lên knn_avg |
| `cross_under_avg` | `pd.Series` bool | `True` khi knn_ma cắt xuống knn_avg |
| `switch_up` | `pd.Series` bool | `True` khi knn_ma bắt đầu tăng |
| `switch_down` | `pd.Series` bool | `True` khi knn_ma bắt đầu giảm |

---

## Tham số tuning

| Tham số | Mặc định | Tăng lên | Giảm xuống |
|---------|----------|----------|-----------|
| `ma_len` | 5 | Mượt hơn, chậm hơn | Nhạy hơn, nhiều nhiễu |
| `target_ma_len` | 5 | Target mượt hơn | Target nhạy hơn |
| `n_neighbors` | 3 | Đường mượt, ít nhạy | Đường nhạy, bám sát giá |
| `smoothing_period` | 50 | knn_avg rất chậm | knn_avg nhanh hơn |

---

## Cách sử dụng trong Strategy

```python
from src.indicators.KNN_trend import calculate_knn_trend

result = calculate_knn_trend(
    high  = df["high"],
    low   = df["low"],
    close = df["close"],
    price_method   = "hl2",
    target_method  = "rma",
    ma_len         = 5,
    target_ma_len  = 5,
    n_neighbors    = 3,
    smoothing_period = 50,
)

# Lấy giá trị
knn_ma         = result["knn_ma"]
knn_avg        = result["knn_avg"]
knn_prediction = result["knn_prediction"]

# Tín hiệu đơn giản
buy_signal  = result["cross_over_avg"]
sell_signal = result["cross_under_avg"]

# Tín hiệu mạnh (kết hợp prediction + crossover)
strong_buy  = (knn_prediction > 0) & result["cross_over_avg"]
strong_sell = (knn_prediction < 0) & result["cross_under_avg"]
```
