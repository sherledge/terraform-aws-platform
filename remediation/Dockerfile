FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY webhook_handler.py .
RUN useradd -m -u 1000 appuser
USER appuser
EXPOSE 5000
CMD ["python", "webhook_handler.py"]