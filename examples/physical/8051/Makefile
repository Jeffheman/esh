#
# Copyright 2026 esh contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# Build for a classic 80C51 with SDCC.
#
#   make
#   make F_CPU=12000000UL UART_BAUD=19200
#   make SDCC_LIB=/path/to/sdcc/lib/small-stack-auto \
#        SDCC_INCLUDE=/path/to/sdcc/include
#
# --stack-auto is required: SDCC cannot call non-reentrant functions through
# pointers with two arguments. Point SDCC_LIB at the matching
# lib/small-stack-auto directory when overriding it.
#
# The generated firmware is esh8051.hex (Intel HEX) and esh8051.ihx.

SDCC ?= sdcc
PACKIHX ?= packihx
SDNM ?= sdnm

# Optional when SDCC is not installed in its configured prefix.
SDCC_LIB ?=
SDCC_INCLUDE ?=

PROJECT ?= esh8051
PROMPT ?= 8051

F_CPU ?= 11059200UL
UART_BAUD ?= 9600

LINE_BUFF_SIZE ?= 12
MAX_ARG_COUNT ?= 6
# --stack-auto needs room for the shell buffers and printf's division helpers.
# 256 bytes covers 8052-class parts and most 8051 derivatives.
IRAM_SIZE ?= 256

OPTIMIZATION ?= --opt-code-size
SDCC_FLAGS = -mmcs51 --model-small --stack-auto --iram-size $(IRAM_SIZE)
SDCC_FLAGS += $(OPTIMIZATION)

SHELL_ROOT = ../../../shell

BUILD_USER ?= $(shell whoami)
BUILD_HOST ?= $(shell hostname)
SHELL_VERSION ?= $(shell git -C $(SHELL_ROOT)/.. rev-parse --short HEAD 2>/dev/null || echo unknown)
USER_REPO_VERSION ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)

DEFINES = -DECHO_INIT_VALUE=1
DEFINES += -DSHELL_NO_PRINTF_LL
DEFINES += -DSHELL_NO_HISTORY
DEFINES += -DSHELL_NO_UTILS
DEFINES += -DSHELL_NO_BIT_UTILS
DEFINES += -DLINE_BUFF_SIZE=$(LINE_BUFF_SIZE)
DEFINES += -DMAX_ARG_COUNT=$(MAX_ARG_COUNT)
DEFINES += -DF_CPU=$(F_CPU)
DEFINES += -DUART_BAUD=$(UART_BAUD)
DEFINES += -D__PROMPT__=$(PROMPT)
DEFINES += -D__BUILD_USER__=$(BUILD_USER)
DEFINES += -D__BUILD_HOST__=$(BUILD_HOST)
DEFINES += -D__SHELL_VERSION__=$(SHELL_VERSION)
DEFINES += -D__USER_REPO_VERSION__=$(USER_REPO_VERSION)

INCLUDES = -I. -Iplatform -I$(SHELL_ROOT)/shell
INCLUDES += -I$(SHELL_ROOT)/lib/printf
INCLUDES += -I$(SHELL_ROOT)/lib/string
INCLUDES += -I$(SHELL_ROOT)/lib/a2i
INCLUDES += -I$(SHELL_ROOT)/lib/regs
INCLUDES += $(if $(SDCC_INCLUDE),-I$(SDCC_INCLUDE),)

LIB_FLAGS = $(if $(SDCC_LIB),-L$(SDCC_LIB),)

APP_OBJECTS = objects/main.rel objects/platform.rel objects/uart.rel
CORE_OBJECTS = objects/shell.rel objects/string.rel objects/a2i.rel objects/printf.rel
OBJECTS = $(APP_OBJECTS) $(CORE_OBJECTS)
TABLE_SOURCE = objects/shell_cmd_table.c
TABLE_OBJECT = objects/shell_cmd_table.rel

.PHONY: all size clean help
.DELETE_ON_ERROR:

all: $(PROJECT).hex

$(PROJECT).hex: $(PROJECT).ihx
	$(PACKIHX) $< > $@
	@echo
	@echo "=== $(PROJECT).hex ==="
	@cat $(PROJECT).mem

$(PROJECT).ihx: $(OBJECTS) $(TABLE_OBJECT)
	$(SDCC) $(SDCC_FLAGS) $(LIB_FLAGS) $^ -o $@

$(TABLE_SOURCE): $(OBJECTS) tools/gen_shell_cmd_table.sh
	SDNM=$(SDNM) tools/gen_shell_cmd_table.sh $(OBJECTS) > $@

$(TABLE_OBJECT): $(TABLE_SOURCE)
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

objects:
	mkdir -p objects

objects/%.rel: %.c | objects
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

objects/platform.rel: platform/platform.c | objects
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

objects/uart.rel: platform/uart.c | objects
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

objects/shell.rel: $(SHELL_ROOT)/shell/shell.c | objects
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

objects/string.rel: $(SHELL_ROOT)/lib/string/string.c | objects
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

objects/a2i.rel: $(SHELL_ROOT)/lib/a2i/a2i.c | objects
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

objects/printf.rel: $(SHELL_ROOT)/lib/printf/printf.c | objects
	$(SDCC) $(SDCC_FLAGS) $(DEFINES) $(INCLUDES) -c $< -o $@

size: $(PROJECT).ihx
	@cat $(PROJECT).mem

clean:
	rm -rf objects
	rm -f $(PROJECT).hex $(PROJECT).ihx $(PROJECT).mem $(PROJECT).map
	rm -f $(PROJECT).lk $(PROJECT).lst $(PROJECT).sym $(PROJECT).asm

help:
	@echo "make              Build $(PROJECT).hex"
	@echo "make size         Show internal RAM and code usage"
	@echo "make clean        Remove build outputs"
	@echo
	@echo "Overridable: SDCC, PACKIHX, SDNM, SDCC_LIB, SDCC_INCLUDE,"
	@echo "             F_CPU, UART_BAUD, LINE_BUFF_SIZE, MAX_ARG_COUNT"
