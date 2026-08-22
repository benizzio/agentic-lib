VENV ?= .venv
BOOTSTRAP_PYTHON ?= python3
PYTHON ?= $(VENV)/bin/python
APM ?= apm

.PHONY: setup build check test-build test-validator test-packages test-apm-install audit test validate

setup:
	$(BOOTSTRAP_PYTHON) -m venv "$(VENV)"
	"$(VENV)/bin/python" -m pip install -r requirements-build.txt

build:
	$(PYTHON) scripts/build.py

check:
	$(PYTHON) scripts/build.py --check

test-build:
	$(PYTHON) -m unittest tests.test_build

test-validator:
	$(PYTHON) -m unittest tests.test_validate_json

test-packages:
	$(PYTHON) -m unittest tests.test_validate_packages

test-apm-install:
	$(PYTHON) scripts/test_apm_install.py --apm "$(APM)"

audit:
	$(PYTHON) scripts/validate_packages.py --apm "$(APM)"

test: test-build test-validator test-packages test-apm-install

validate: check test audit
