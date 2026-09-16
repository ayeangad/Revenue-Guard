FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml README.md ./
COPY domain ./domain
COPY agent ./agent
COPY apps ./apps
COPY commerce ./commerce
COPY evals ./evals
COPY infrastructure ./infrastructure
RUN uv pip install --system -e ".[dev]"
EXPOSE 8000 8001
