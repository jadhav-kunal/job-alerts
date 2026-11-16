FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir httpx pyyaml
COPY jobalerts ./jobalerts
COPY config ./config
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "jobalerts", "run"]
