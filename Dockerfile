FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

ARG INSTALL_AI=false
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

COPY requirements-ai-runtime.txt ./
RUN if [ "$INSTALL_AI" = "true" ]; then \
      python -m pip install --no-cache-dir \
        --timeout 300 --retries 10 \
        torch==2.11.0 torchvision==0.26.0 \
        --index-url "$TORCH_INDEX_URL" \
      && python -m pip install --no-cache-dir \
        --timeout 300 --retries 10 \
        -r requirements-ai-runtime.txt; \
    fi

RUN groupadd --gid 10001 waki \
    && useradd --uid 10001 --gid waki --no-create-home --shell /usr/sbin/nologin waki \
    && mkdir -p /app/data \
    && chown waki:waki /app/data

COPY app ./app

USER waki

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

