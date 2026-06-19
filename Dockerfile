FROM python:3.12-slim

# Evita criação de arquivos .pyc
ENV PYTHONDONTWRITEBYTECODE=1

# Logs aparecem imediatamente no container
ENV PYTHONUNBUFFERED=1

# Instala o uv a partir da imagem oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copia arquivos de dependências primeiro para aproveitar cache do Docker
COPY pyproject.toml uv.lock ./

# Instala dependências de produção
RUN uv sync \
    --frozen \
    --no-dev \
    --compile-bytecode

# Copia código da aplicação
COPY . .

# Remove caches desnecessários
RUN find . -type d -name "__pycache__" -exec rm -rf {} +

# Inicia o pipeline
CMD ["uv", "run", "python", "-m", "extract.run"]