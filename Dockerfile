# Dockerfile — TimeManager Pro Worker
FROM python:3.12-slim

# محیط کار
WORKDIR /app

# فقط requirements را اول کپی کن (برای cache لایه‌ها)
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# بقیه کد را کپی کن
COPY . .

# اجرای worker
CMD ["python", "-m", "worker.reminder_worker"]
