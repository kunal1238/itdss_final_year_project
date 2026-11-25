FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
RUN useradd -m itdss && mkdir -p data && chown -R itdss data ml
USER itdss
VOLUME /app/backend/data
EXPOSE 8000
# Behind a reverse proxy set FORWARDED_ALLOW_IPS to the proxy's address so rate limits see real clients.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
