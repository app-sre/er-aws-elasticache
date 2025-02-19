SITE_PACKAGES_DIR ?= $(shell .venv/bin/python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
CONTAINER_ENGINE ?= $(shell which podman >/dev/null 2>&1 && echo podman || echo docker)

.PHONY: format
format:
	uv run ruff check
	uv run ruff format
	terraform fmt terraform

.PHONY: image_tests
image_tests:
	# hooks must be copied
	[ -d "hooks" ]
	[ -d "hooks_lib" ]

	# sources must be copied
	[ -d "$$TERRAFORM_MODULE_SRC_DIR" ]

	# test the terrform providers are downloaded
	[ -d "$$TF_PLUGIN_CACHE_DIR/registry.terraform.io/hashicorp/aws" ]
	[ -d "$$TF_PLUGIN_CACHE_DIR/registry.terraform.io/hashicorp/random" ]

	# test all files in ./hooks are executable
	[ -z "$(shell find hooks -type f -not -executable ! -name "__init__.py")" ]

.PHONY: code_tests
code_tests:
	uv run ruff check --no-fix
	uv run ruff format --check
	terraform fmt -check=true "$$TERRAFORM_MODULE_SRC_DIR"
	uv run mypy
	uv run pytest -vv --cov=er_aws_elasticache --cov=hooks --cov=hooks_lib --cov-report=term-missing --cov-report xml

in_container_test: image_tests code_tests

.PHONY: test
test:
	$(CONTAINER_ENGINE) build --progress plain --target test -t er-aws-elasticache:test .

.PHONY: build
build:
	$(CONTAINER_ENGINE) build --progress plain --target prod -t er-aws-elasticache:prod .

.PHONY: dev
dev:
	uv sync

.PHONY: generate-variables-tf
generate-variables-tf:
	external-resources-io tf generate-variables-tf er_aws_elasticache.app_interface_input.AppInterfaceInput --output terraform/variables.tf
