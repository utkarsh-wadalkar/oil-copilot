FROM python:3.12-slim
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml ./
COPY app ./app
# CPU-only torch avoids pulling multi-GB CUDA wheels into the image.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install ".[memory]"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
