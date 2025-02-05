SITE_PACKAGES_DIR ?= $(shell .venv/bin/python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
CONTAINER_ENGINE ?= $(shell which podman >/dev/null 2>&1 && echo podman || echo docker)

.PHONY: format
format:
	uv run ruff check
	uv run ruff format

.PHONY: image_tests
image_tests:
	# test /tmp must be empty
	[ -z "$(shell ls -A /tmp)" ]
	# hooks must be copied
	[ -d "hooks" ]
	[ -d "hooks_lib" ]
	# test all files in ./hooks are executable
	[ -z "$(shell find hooks -type f -not -executable ! -name "__init__.py")" ]

.PHONY: code_tests
code_tests:
	uv run ruff check --no-fix
	uv run ruff format --check
	uv run mypy
	uv run pytest -vv --cov=er_aws_elasticache --cov-report=term-missing --cov-report xml

.PHONY: dependency_tests
dependency_tests:
	python -c "import cdktf_cdktf_provider_random"
	python -c "import cdktf_cdktf_provider_aws"

_test: image_tests code_tests dependency_tests

.PHONY: test
test:
	$(CONTAINER_ENGINE) build --progress plain --target test -t er-aws-elasticache:test .

.PHONY: build
build:
	$(CONTAINER_ENGINE) build --progress plain --target prod -t er-aws-elasticache:prod .

.PHONY: dev
dev:
	uv sync
