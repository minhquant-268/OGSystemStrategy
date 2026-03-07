# System Strategy - Module 4

Hệ thống tính toán kỹ thuật (Technical Analysis) theo thời gian thực, subscribe Redis Keyspace Notification và đẩy tín hiệu giao dịch lên Redis để OF_ctrader (Module 5) thực thi lệnh.

## Cách chạy

```bash
# Cài thư viện
pip install -r requirements.txt

# Chạy realtime (lắng nghe nến mới)
python main.py

# Chạy backfill (1000 nến lịch sử)
python back_fill_og.py

# Chạy test
pytest tests/
```

## Cấu trúc dự án

Xem file `docs/project_structure.md` để biết chi tiết.
