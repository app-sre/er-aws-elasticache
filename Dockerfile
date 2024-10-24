FROM quay.io/app-sre/er-base-cdktf-aws:0.2.1 AS prod
COPY --from=ghcr.io/astral-sh/uv:0.4.26@sha256:7775c60dca9cc5827c36757c32c75985244d8f31447565fa8147e2b2e11ad280 /uv /bin/uv

# er-outputs-secrets version. keep in sync with pyproject.toml
LABEL konflux.additional-tags="0.1.0"

# Keep in sync with the 'cdktf-cdktf-provider-random' version in pyproject.toml
ENV TF_PROVIDER_RANDOM_VERSION="3.6.3"
ENV TF_PROVIDER_RANDOM_PATH="${TF_PLUGIN_CACHE}/registry.terraform.io/hashicorp/random/${TF_PROVIDER_RANDOM_VERSION}/linux_amd64"

RUN mkdir -p ${TF_PROVIDER_RANDOM_PATH} && \
    curl -sfL https://releases.hashicorp.com/terraform-provider-random/${TF_PROVIDER_RANDOM_VERSION}/terraform-provider-random_${TF_PROVIDER_RANDOM_VERSION}_linux_amd64.zip \
    -o /tmp/package-${TF_PROVIDER_RANDOM_VERSION}.zip && \
    unzip /tmp/package-${TF_PROVIDER_RANDOM_VERSION}.zip -d ${TF_PROVIDER_RANDOM_PATH}/ && \
    rm /tmp/package-${TF_PROVIDER_RANDOM_VERSION}.zip

WORKDIR ${HOME}

ENV \
    # Use the system python and let uv manage the application venv
    UV_PYTHON="/usr/bin/python3.11" \
    # compile bytecode for faster startup
    UV_COMPILE_BYTECODE="true" \
    # disable uv cache. it doesn't make sense in a container
    UV_NO_CACHE=true \
    # uv will run without updating the uv.lock file.
    UV_FROZEN=true \
    # Activate the virtual environment
    PATH="${HOME}/.venv/bin:${PATH}"


# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project --no-dev

# other project related files
COPY LICENSE /licenses/LICENSE
COPY README.md Makefile cdktf.json validate_plan.py ./

# the source code
COPY er_aws_elasticache ./er_aws_elasticache

# Sync the project
RUN uv sync --no-editable --no-dev

FROM prod AS test
RUN microdnf install -y make
# install test dependencies
RUN uv sync --no-editable

COPY tests ./tests
RUN make test
