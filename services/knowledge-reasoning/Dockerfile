# Phase 1: no HTTP service exists yet (the FastAPI test harness is Phase 5
# scope), so this image's only defined entrypoint is the fixture loader,
# run against whatever KR_* env vars point at (docker-compose.dev.yml's
# services by default). Extend the CMD once app/ exists.

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY contracts ./contracts
COPY knowledge_reasoning ./knowledge_reasoning
COPY fixtures ./fixtures

RUN pip install --no-cache-dir -e .

ENV KR_ENV=dev \
    KR_GRAPH_BACKEND=postgres \
    KR_STANDARDS_BACKEND=postgres \
    KR_RETRIEVAL_BACKEND=fixture

CMD ["python", "-m", "knowledge_reasoning.loader.run"]
