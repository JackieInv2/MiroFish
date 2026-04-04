FROM python:3.12-slim

WORKDIR /app

# Install backend deps from slim requirements
COPY backend/requirements-debate.txt ./
RUN pip install --no-cache-dir -r requirements-debate.txt

# Copy backend source
COPY backend/ ./backend/

WORKDIR /app/backend

ENV DEMO_MODE=true
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "--timeout", "120", "app:create_app()"]
