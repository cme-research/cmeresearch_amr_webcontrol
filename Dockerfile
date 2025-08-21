# Multi-arch base: works on Raspberry Pi 5 (arm64) and x86_64
FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

RUN mkdir /app/bin
COPY ./install/bin/restartSystem /app/bin
COPY ./install/bin/shutdownSystem /app/bin

# Expose Django default port
EXPOSE 8000

# Optional: define settings module explicitly (manage.py sets it too)
ENV DJANGO_SETTINGS_MODULE=django_project.settings

# Run database migrations and start the development server
# For production, consider using gunicorn/uvicorn and proper static handling
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
