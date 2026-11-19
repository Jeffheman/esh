# Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0
PYTHON ?= python
PROJECT ?= esh
PROJECT_ROOT ?= $(CURDIR)
C51_BUILD_PATH ?= $(PROJECT_ROOT)/build
C51_DEFINES ?=
C51_BUILD_ARGS ?=
PROMPT ?= esh
ECHO_INIT_VALUE ?= 1

C51_FEATURE_DEFINES :=
ifeq ($(SHELL_LITE),1)
C51_FEATURE_DEFINES += SHELL_PRINTF_LITE SHELL_NO_PRINTF_LL SHELL_NO_UTILS
C51_FEATURE_DEFINES += SHELL_NO_HISTORY SHELL_NO_TAB_COMPLETE SHELL_NO_BIT_UTILS
endif

C51_COMMAND = $(PYTHON) "$(SHELL_ROOT)/toolchains/keil-c51/build.py" \
    --project-dir "$(PROJECT_ROOT)" --output-dir "$(C51_BUILD_PATH)" \
    --name "$(PROJECT)" $(if $(KEIL_C51_ROOT),--keil-root "$(KEIL_C51_ROOT)") \
    --define "__PROMPT__=$(PROMPT)" --define "ECHO_INIT_VALUE=$(ECHO_INIT_VALUE)" \
    $(foreach define,$(C51_DEFINES) $(C51_FEATURE_DEFINES),--define "$(define)") $(C51_BUILD_ARGS)

.DEFAULT_GOAL := all
.PHONY: all compile-only
all:
	$(C51_COMMAND)

compile-only:
	$(C51_COMMAND) --compile-only
