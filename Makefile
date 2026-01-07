.DEFAULT_GOAL	:= help
PROJECT_NAME	:=
PYTHON_VERSION	:= 3.13
PATH_TO_ROOT 	:= $(shell git rev-parse --show-toplevel)

.PHONY: help
help:  ## this help section
	@awk 'BEGIN {FS = ":.*##"; printf "\nusage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Docker commands
DOCKER_TAG := latest
LOCAL_IMAGE_NAME := your_project_name:$(DOCKER_TAG)

.PHONY: build
build: ## Build the Docker image locally.
	docker build \
		--tag $(LOCAL_IMAGE_NAME) \
		--file Dockerfile \
		.

.PHONY: run-local
run-local: ## Run the Docker container build from the local Dockerfile.
	docker run \
		--rm \
		$(LOCAL_IMAGE_NAME)
