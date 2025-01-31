FROM quay.io/redhat-services-prod/app-sre-tenant/er-base-cdktf-main/er-base-cdktf-main:cdktf-0.20.11-tf-1.6.6-py-3.11-v0.5.0-1@sha256:0c6f11a1a4057ceb6ea9fb9f5ec7eb0a5a2bdf7730416cbddda87b0f509e59a5 AS base
# keep in sync with pyproject.toml
LABEL konflux.additional-tags="0.3.1"

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5.27@sha256:5adf09a5a526f380237408032a9308000d14d5947eafa687ad6c6a2476787b4f /uv /bin/uv

COPY cdktf.json ./
# Download all necessary CDKTF providers and build the python cdktf modules.
# The python modules must be stored in the .gen directory because cdktf needs them there.
RUN cdktf-provider-sync .gen

# Python and UV related variables
ENV \
    # compile bytecode for faster startup
    UV_COMPILE_BYTECODE="true" \
    # disable uv cache. it doesn't make sense in a container
    UV_NO_CACHE=true \
    UV_NO_PROGRESS=true

COPY pyproject.toml uv.lock ./
# Test lock file is up to date
RUN uv lock --locked
# Install dependencies
RUN uv sync --frozen --no-group dev --no-install-project --python /usr/bin/python3

# the source code
COPY README.md ./
COPY hooks ./hooks
COPY hooks_lib ./hooks_lib
COPY er_aws_elasticache ./er_aws_elasticache
# Sync the project
RUN uv sync --frozen --no-group dev

FROM base AS prod
# get cdktf providers
COPY --from=builder ${TF_PLUGIN_CACHE_DIR} ${TF_PLUGIN_CACHE_DIR}
# get our app with the dependencies
COPY --from=builder ${APP} ${APP}

ENV \
    # Use the virtual environment
    PATH="${APP}/.venv/bin:${PATH}" \
    # cdktf python modules path
    PYTHONPATH="$APP/.gen"

FROM prod AS test
COPY --from=ghcr.io/astral-sh/uv:0.5.27@sha256:5adf09a5a526f380237408032a9308000d14d5947eafa687ad6c6a2476787b4f /uv /bin/uv

# install test dependencies
RUN uv sync --frozen

COPY Makefile ./
COPY tests ./tests

RUN make test

# Empty /tmp again because the test stage might have created files there, e.g. JSII_RUNTIME_PACKAGE_CACHE_ROOT
# and we want to run this test image in the dev environment
RUN rm -rf /tmp/*
