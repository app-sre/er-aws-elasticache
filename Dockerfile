FROM quay.io/redhat-services-prod/app-sre-tenant/er-base-cdktf-main/er-base-cdktf-main:cdktf-0.20.11-tf-1.6.6-py-3.12-v0.6.0-1 AS base
# keep in sync with pyproject.toml
LABEL konflux.additional-tags="0.3.2"

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5.28@sha256:8bd47d593fb4a8ac5820c08265b651570e99e3c47d3247980a704174784c6a7f /uv /bin/uv

# Python and UV related variables
ENV \
    # compile bytecode for faster startup
    UV_COMPILE_BYTECODE="true" \
    # disable uv cache. it doesn't make sense in a container
    UV_NO_CACHE=true \
    UV_NO_PROGRESS=true

COPY cdktf.json pyproject.toml uv.lock ./
# Test lock file is up to date
RUN uv lock --locked
# Install dependencies
RUN uv sync --frozen --no-group dev --no-install-project --python /usr/bin/python3
# Download all necessary terraform providers
RUN cdktf-provider-sync

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
COPY --from=ghcr.io/astral-sh/uv:0.5.28@sha256:8bd47d593fb4a8ac5820c08265b651570e99e3c47d3247980a704174784c6a7f /uv /bin/uv

# install test dependencies
RUN uv sync --frozen

COPY Makefile ./
COPY tests ./tests

RUN make _test

# Empty /tmp again because the test stage might have created files there, e.g. JSII_RUNTIME_PACKAGE_CACHE_ROOT
# and we want to run this test image in the dev environment
RUN rm -rf /tmp/*
