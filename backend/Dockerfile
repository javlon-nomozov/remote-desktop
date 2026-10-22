FROM python:3.12-slim

WORKDIR /app

# Bog'liqliklar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ilova kodi
COPY . .

ENV PORT=8080
# uvicorn PID 1 bo'lishi uchun exec (signal handling). Cloud Run $PORT beradi.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
