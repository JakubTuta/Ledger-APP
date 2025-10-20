FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY query_service/ ./query_service/

CMD ["python", "-m", "query_service.main"]
