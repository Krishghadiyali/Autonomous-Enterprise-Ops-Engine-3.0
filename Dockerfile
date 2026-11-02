FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-cache the local HuggingFace embedding model inside the image
RUN python -c "from langchain_huggingface import HuggingFaceEmbeddings; HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')"

# Copy application code, UI, seeder, tests, and policy PDF
COPY app/ ./app/
COPY ui/ ./ui/
COPY tests/ ./tests/
COPY pytest.ini ./pytest.ini
COPY seed.py ./seed.py
COPY Company_policy.pdf ./Company_policy.pdf

EXPOSE 8000 8501