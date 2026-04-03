# ใช้ Python Image ที่เบาและปลอดภัย
FROM python:3.10-slim

# ตั้งค่า Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ติดตั้ง System Dependencies ที่จำเป็น (เช่น libpq สำหรับ PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements และติดตั้ง
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn uvicorn[standard]

# Copy Code ทั้งหมด
COPY . .

# Cloud Run จะส่ง PORT มาให้ทาง Environment Variable (default 8080)
ENV PORT=8080

# คำสั่ง Run Server (ใช้ Gunicorn คุม Uvicorn)
CMD exec gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --threads 8 app.main:app