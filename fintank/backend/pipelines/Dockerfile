# Fintank pipeline image. Built from backend/pipelines/ by `cdk deploy`
# (infra/pipeline_stack.py). Data lives in /data on the task's ephemeral disk.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIPELINE_DATA_ROOT=/data

WORKDIR /app
COPY requirements.txt pipelines/requirements.txt
RUN pip install -r pipelines/requirements.txt
COPY . pipelines/

RUN useradd --create-home --uid 10001 pipeline \
    && mkdir -p /data && chown pipeline /data
USER pipeline

ENTRYPOINT ["python", "-m", "pipelines"]
CMD ["--help"]
