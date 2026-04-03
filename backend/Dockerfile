FROM python:3.12-slim

WORKDIR /app

# Install only debate engine deps (not the full 8GB camel/oasis stack)
COPY requirements-debate.txt .
RUN pip install --no-cache-dir -r requirements-debate.txt

# Copy app source
COPY . .

# Expose port
EXPOSE 5001

# Use gunicorn for production
CMD gunicorn --bind 0.0.0.0:${PORT:-5001} --workers 2 --timeout 120 "app:create_app()"
