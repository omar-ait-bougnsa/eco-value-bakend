FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
# Indexed into the knowledge base on first start (app/rag/index.py)
COPY sample-uploads ./sample-uploads
COPY engine.md ./

RUN useradd --system --no-create-home api && \
    chown -R api:api /srv
USER api

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
