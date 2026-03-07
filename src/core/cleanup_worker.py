# cleanup_worker.py
# Vai trò: Background thread dọn dẹp dữ liệu cũ trên Redis định kỳ
# - Chạy mỗi 5 phút (300 giây)
# - Scan tất cả list key pattern OG:* và signal:*
# - Giữ tối đa 1000 items mỗi list, xóa hash key tương ứng
# - Xóa hash key "mồ côi" không còn tồn tại trong list
