#
# Copyright 2021 Google LLC
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

TOOLCHAIN_PREFIX   ?= riscv64-linux-gnu-

STARTUP            = riscv64
RAM_BASE_PHYSICAL  = 0x80000000
RAM_SIZE           = 0x4000000

QEMU ?= qemu-system-riscv64
QEMU_CONSOLE ?= -nographic
PYTHON ?= python3

# MANDATORY:
#     Provide relative path to shell/ from current directory
#     Only Variable should be set above this line
SHELL_ROOT=../../../shell
-include $(SHELL_ROOT)/Makefile
# ^^ Do not move the above line. All user targets to be defined below this line!

GCC_FLAGS += -mcmodel=medany -fno-pie -fno-pic -msmall-data-limit=0
ASM_FLAGS += -fno-pie -fno-pic

RPC_MANIFEST = ../../../host/src/esh_mcp/data/riscv64-virt.json
RPC_GENERATOR = ../../../tools/generate_rpc_board.py
# Prefer the current manifest header over headers left in old build directories.
INCLUDES := -I$(BUILD_PATH) $(INCLUDES)

$(BUILD_PATH)/rpc_board.h: $(RPC_MANIFEST) $(RPC_GENERATOR) | $(BUILD_PATH)
	$(PYTHON) $(RPC_GENERATOR) $(RPC_MANIFEST) $@

$(OBJS): $(BUILD_PATH)/rpc_board.h

# ------------------------ User targets below this line ------------------------
### run: Launches QEMU and loads the project binary on it
run: $(PROJECT).elf
	@$(QEMU) -M virt $(QEMU_CONSOLE) -bios none -kernel $(PROJECT).elf

### debug: Qemu with GDB server. To be executed before 'make gdb'
debug:
	@echo Please use \"make gdb\" in another terminal to attach gdb.
	@echo Use \"cltr+a,x\" to quit qemu debug
	@$(QEMU) -S -M virt $(QEMU_CONSOLE) -bios none\
	 -kernel $(PROJECT).elf -gdb tcp::1234

### gdb: Launches GDB and connects to qemu. To be executed after 'make debug'
gdb:
	@gdb-multiarch $(PROJECT).elf -ex "target remote localhost:1234"
