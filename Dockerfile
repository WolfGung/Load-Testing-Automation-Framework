FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
LABEL org.opencontainers.image.authors="Pavel Zhukov Atum"
WORKDIR /work
COPY requirements.lock pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app app
COPY loadtest loadtest
COPY tools tools
COPY profiles profiles
RUN pip install --no-deps . && useradd --create-home runner && chown -R runner:runner /work
USER runner
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8120"]
