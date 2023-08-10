
########################################
# BACKEND SERVICE
########################################

FROM python:3.7-slim AS base-backend
SHELL ["/bin/bash", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
WORKDIR /service
USER root

RUN apt-get update
RUN apt-get install -y --no-install-recommends git

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements*.txt ./
RUN pip3 install -r requirements-prod.txt

########################################
# WEBUI CLIENT
########################################

FROM node:18 as base-webui
SHELL ["/bin/bash", "-c"]
WORKDIR /service
USER root

RUN git clone https://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@github.com/Bondifuzz/webui-client.git
RUN cd webui-client && rm package-lock.json && npm install && npm run build

########################################
# RELEASE IMAGE
########################################

FROM python:3.7-slim
SHELL ["/bin/bash", "-c"]
ENV PYTHONUNBUFFERED=1
WORKDIR /service
USER root

ARG ENVIRONMENT=prod
ARG SERVICE_NAME=api-gateway
ARG SERVICE_VERSION=None
ARG COMMIT_ID=None
ARG COMMIT_DATE=None
ARG BUILD_DATE=None
ARG GIT_BRANCH=None

ENV ENVIRONMENT=$ENVIRONMENT
ENV SERVICE_NAME=$SERVICE_NAME
ENV SERVICE_VERSION=$SERVICE_VERSION
ENV COMMIT_ID=$COMMIT_ID
ENV COMMIT_DATE=$COMMIT_DATE
ENV BUILD_DATE=$BUILD_DATE
ENV GIT_BRANCH=$GIT_BRANCH

COPY --from=base-backend /opt/venv /opt/venv
COPY logging.yaml index.html ./
COPY api_gateway ./api_gateway

COPY --from=base-webui /service/webui-client/build/locales ./locales
COPY --from=base-webui /service/webui-client/build/static ./static
COPY --from=base-webui /service/webui-client/build/index.html .
COPY --from=base-webui /service/webui-client/build/favicon.ico .
COPY --from=base-webui /service/webui-client/build/robots.txt .

COPY book ./book

ENV PATH="/opt/venv/bin:$PATH"
CMD python3 -m uvicorn \
	--factory api_gateway.app.main:create_app \
    --host 0.0.0.0 \
    --port 8080 \
    --workers 1 \
    --log-config logging.yaml \
    --lifespan on
