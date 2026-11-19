**Important disclaimer**:

    This is not an officially supported Google product

# Embedded Shell

**A Terminal like interface over UART.**

- Targeted at embedded systems engineers and researchers who want to explore the hardware by writing small functions that can be triggered from a shell like interface.
- A UART based shell that enables finer control of CPU by allowing functions to be exposed as commands to be triggered from the prompt.
- Low memory footprint of < 4kB

this is a perfect tool for getting up and running with a new board in less than 1 hour.

### Features:
- Low footprint shell implementation.
- Commands with same foot print as `int main(int argc, char* argv[]){}`
- Export function as command using a macro (`ADD_CMD()` available in `shell.h`).
- Supported Languages: **C**, **C++** and **Assembly**.
- Automatic source file discovery
    - `.c`, `.cpp` and `.S` source files in the Project and shell directory are automatically picked for compilation **(No need to modify any Makefile. The build system automatically figrues the source files)**.
- Automatic Header discovery.
    - location for `.h` and `.hpp` files is automatically passed to the compiler for header file lookup.

### Supported Processors/Architectures
`examples/` implements a `hello world` example for the processor variety listed below:
| Architecture             | Processor            | Example Location                             | Board                             |
| :---                     |:--                   |:---                                          |:-                                 |
| ARM v7 A-class 32 bit    |Cortex-a7 (quadcore)  | examples/emulation/armv7A-32-Rpi2            | raspberry pi 2b (Emulated on Qemu)|
| ARM v8 A-class 32 bit    |Cortex-a53            | examples/emulation/armv8A-32-RPi3b           | raspberry pi 3b (Emulated on Qemu)|
| ARM v7 M-class 32 bit    |Cortex-m3             | examples/emulation/armv7M-32                 | mps2-an385 (Emulated on Qemu)     |
| ARM v8 A-class 64 bit    |Cortex-a72            | examples/emulation/armv8A-64                 | virt (Emulated on Qemu)           |
| ARM v8 A-class 64 bit    |Cortex-a72 (quadcore) | examples/emulation/armv8A-64-smp (multicore) | virt (Emulated on Qemu)           |
| ARM v8 M-class 32 bit    |Cortex-m33 (dualcore) | examples/emulation/armv8M-32 (multicore)     | mps3-an524 (Emulated on Qemu)     |
| RISC-V 64 bit            |rv64g                 | examples/emulation/riscv-64                  | virt (Emulated on Qemu)           |
| RISC-V 32 bit (RV32IMAC) |SiFive E31            | examples/physical/hifive                     | hifive1-revb (Physical Board)     |
| ARM v7 M-class 32 bit    |Cortex-m4             | examples/physical/nucleo-f401re              | nucleo-f401re (Physical Board)    |
| ARM v7 M-class 32 bit    |Cortex-m4             | examples/physical/tiva-c                     | tiva-c (Physical Board)           |

## Keil C51 / 8051

The C51 backend uses the same shell, history, Tab completion, `ADD_CMD`, `AUTO_CMD`,
`exec`, help/status, memory commands and memlog implementation. GNU builds remain
unchanged. The example targets an 8052-compatible UART at 9600 baud / 11.0592 MHz
with external XDATA RAM and the LARGE memory model.

For a native µVision project, open
[`examples/emulation/8051-keil/esh-8051.uvproj`](examples/emulation/8051-keil/esh-8051.uvproj),
select `Simulator`, and press F7 to build. No Python or Make is required. The image,
HEX and map are written to `examples/emulation/8051-keil/build/uvision/`.
Use Ctrl+F5 to enter the simulator, open `View > Serial Windows > UART #1`, then
press F5 to run. The simulator maps 64KB of XDATA; a physical board needs suitable
external RAM or a board-specific startup and memory layout.

The native project defines `ESH_UVISION_COMMANDS` and uses `commands_uv.c` for its
command tables. When adding or removing `ADD_CMD`/`AUTO_CMD` registrations, update
that file too; automatic commands belong in both tables. The Python/Make backend
still generates its tables automatically and excludes these native tables.
Native build user/host are `uVision`; Git revisions are `unknown` unless overridden
in the target's C51 definitions. A licensed C51 toolchain is required for the full image.

From the repository root, with Python 3.9+ and a licensed Keil C51 installation:

```shell
python shell/toolchains/keil-c51/build.py --keil-root "E:/DEVSDK/Keil_v5" --project-dir examples/emulation/8051-keil
```

Alternatively, set `KEIL_C51_ROOT` and run GNU Make in
`examples/emulation/8051-keil`. The C51 Make entry does not require Unix utilities.
The build uses C51, A51, BL51 and OH51, producing
`build/esh.abs`, `build/esh.hex`, compiler listings and a BL51 memory map (the
Makefile names the image `esh-8051`). `--compile-only` explicitly stops before
linking; it is not an execution test. [Keil's C51 evaluation limits](https://www2.keil.com/limits)
restrict both linking and debugging to 2KB, so obtaining a full image from another
machine does not remove the local debugger's limit. Complete full-shell linking
and simulation in an appropriately licensed C51 environment; see
[Keil license management](https://www.keil.com/download/license) for PSN/CID/LIC
activation requirements. Do not use `SHELL_LITE` as a substitute for full-feature
validation.

Integration details:

- Set `TOOLCHAIN = keil-c51` before including `shell/Makefile`, or call the Python
  builder directly. It discovers project `.c`, `.a51`, `.asm` sources and
  `.h`/`.inc` include directories recursively, including uppercase filenames.
  C sources use C51; Keil assembly sources use A51. Repeated `--source` and
  `--include` options select sources and include paths; `--define` sets C
  preprocessor definitions. GNU assembly syntax and C++ are not supported.
  Select a project startup explicitly with `--startup`; it is assembled once,
  even if also found by discovery or listed with `--source`.
  Make accepts `C51_DEFINES` and `C51_BUILD_ARGS`, and forwards the existing
  `PROMPT` and `ECHO_INIT_VALUE` settings (C51 defaults: `esh` and `1`). Explicit
  `C51_DEFINES` can override those values. Opt-in `SHELL_LITE=1` still applies
  when custom definitions are supplied on the Make command line.
- Command tables are generated from **C51-preprocessed output**, honoring feature
  guards and commands in separate translation units. Static command functions
  work without maintaining a second manual registration list. Both command
  descriptors and tables live in CODE memory. Keep command function names unique.
- C51 uses `DEBUG OBJECTEXTEND` so the debugger knows the widths of variables.
  Without extended type information, the debugger can read only one byte of a
  multi-byte test result; the simulator runner rejects such images.
- BL51 `NOOVERLAY` is required because command/UART callbacks are indirect.
  Unresolved external symbols (`L1`/`L2`) stop the build before HEX conversion,
  even though BL51 reports them as warnings and produces an absolute image.
  Callbacks keep their normal `int (int, char **)`, `int (void)` and `void (char)`
  signatures. `exec` and its dispatcher use a reentrant stack to allow a command
  to invoke another command; recursive entry into a non-reentrant user command
  is not supported by C51.
- The provided startup clears IDATA and XDATA `0000H–EFFFH`, initializes the LARGE
  reentrant stack at `FF00H`, then enters the C runtime. BL51 excludes the upper
  4KB from static allocation. Reserve that region for the stack, provide suitable
  RAM, or supply a board-specific `--startup` and matching `--xdata-range`.
  Reversed/out-of-range bounds are rejected; with the default startup, static
  allocation above `EFFFH` is rejected to protect the reentrant stack.
- `r32`, `w32`, `read`, `rb`, `wb` access XDATA, not CODE or SFR space, and reject
  accesses beyond the 16-bit address range. C51 memlog buffers also reside in
  XDATA. These accesses are non-atomic on an 8-bit CPU.
- C51 is C90, with 16-bit `int`, 32-bit `long` and no native `long long` or C++.
  `%d/%u/%x` use `int`; `%ld/%lu/%lx` retain full 32-bit values. `%ll` is rejected
  on C51 instead of silently truncating; GNU builds retain native 64-bit formats.
  Cast variadic string arguments to `const char *` and character/numeric arguments
  to the requested type because C51 memory-specific pointers and constants can
  have different widths. The implementation does not add field-width padding.
- C51 has no GNU weak symbols. Define `SHELL_CUSTOM_SETUP`, `SHELL_CUSTOM_LOOP`,
  `SHELL_CUSTOM_PREPEND_PROMPT`, `SHELL_CUSTOM_ACTIVE_PROMPT` or
  `SHELL_CUSTOM_INITIAL_SETUP` when supplying the corresponding hook.

Shared functional regression tests:

```shell
python tests/keil-c51/test_build.py
python tests/keil-c51/run_host.py
python tests/keil-c51/run_arm.py
python shell/toolchains/keil-c51/build.py --keil-root "E:/DEVSDK/Keil_v5" --project-dir tests/keil-c51 --source tests/keil-c51/test_shell.c --standalone
python tests/keil-c51/run_simulator.py --keil-root "E:/DEVSDK/Keil_v5" --image tests/keil-c51/build/esh.abs --suite shell
```

For MSVC outside a developer prompt, pass `--vcvars ".../vcvars64.bat"` to the
host runner. The ARM runner accepts `--toolchain-prefix` and `--qemu` paths when
those tools are not on PATH. Host tests do not validate the 8051 ABI. Full C51
validation requires a licensed build: the simulator requires exactly 64 assertions,
zero failures and completion, in addition to valid debugger types and RAM prefill.
The host variant has 58 assertions. The full test fixture rejects disabled history,
Tab completion, utilities, bit utilities and `SHELL_PRINTF_LITE` at compile time.
The tests exercise shell behavior, formatting, memory commands and memlog.
Memory-command tests use a bounded array substitute; the C51 fixture additionally
checks the production `reg32` macro against owned XDATA storage for full-width
32-bit reads and writes. Hardware UART/electrical timing still requires a board test.

When GNU Make is on PATH (or `MAKE` names its executable), `test_build.py` also
checks Make configuration forwarding and operation without Unix utilities.
Set `KEIL_C51_ROOT` when running `test_build.py` to additionally compile the full
C51 fixture, check its preprocessed assertion count against `SHELL_CHECKS` in the
simulator runner, and verify rejection of reduced configurations. C51's
`SHELL_NO_PRINTF_LL` remains allowed because its 32-bit formatting is retained.
These native compiler checks do not link or execute the full shell. When changing
the assertions, update the expected count and review coverage rather than lowering
the acceptance threshold to make an incomplete run pass.

A separate, small **toolchain smoke test** also runs within the evaluation license:

```shell
python shell/toolchains/keil-c51/build.py --keil-root "E:/DEVSDK/Keil_v5" --project-dir tests/keil-c51 --source tests/keil-c51/toolchain_smoke.c --standalone --output-dir tests/keil-c51/build/smoke --name toolchain-smoke
python tests/keil-c51/run_simulator.py --keil-root "E:/DEVSDK/Keil_v5" --image tests/keil-c51/build/smoke/toolchain-smoke.abs --suite smoke
```

It verifies C51/A51/BL51/OH51 integration, startup initialization, CODE command
tables, indirect callbacks, the LARGE reentrant stack and native 32-bit XDATA
register reads/writes. It does **not** contain
the shell and cannot replace the full functional test. The Windows simulator
runner uses a temporary copy of the installed `C51/Examples/HELLO/Hello.uvproj`
as a debugger template, leaving the installation unchanged. It requires the
matching `.m51` map to locate `?C_C51STARTUP`. At that startup breakpoint it checks
debugger type widths, poisons XDATA and an upper IDATA byte, and confirms the
prefill before continuing. It logs results at the completion breakpoint and stops
only its own debugger after `--timeout` seconds (default 20). Missing or failing
results produce a nonzero exit code; the log is saved beside the image as
`*.sim.log`.

To verify that the initialization checks detect real failures:

```shell
python tests/keil-c51/test_startup.py --keil-root "E:/DEVSDK/Keil_v5"
```

This builds the independent smoke from mixed uppercase C/A51/ASM and H/INC
fixtures, checks that C receives the expected return value from an assembly
function, and exercises automatic and explicit source selection. It checks three
simulator runs: normal startup must pass; temporary startup copies with either
the XDATA or IDATA clearing instruction replaced by a NOP must fail. Custom
startup include paths and duplicate-startup exclusion are also exercised.
The production startup is never modified. Images, maps, listings and logs are
retained under `tests/keil-c51/build/startup-validation`.

# Quick Setup

Execute `./manage -s` or `.scripts/setup` to install all the dependencies.

## Quick Demo

Following is a run of example in `examples/emulation/riscv-64`
```shell
cd examples/emulation/riscv-64
make
make run
```
![Qemu Demo](docs/images/demo.gif)

If you haven't done the `Quick Setup` as noted above, you'll need to install following utilities:

```
sudo apt install -y binutils make binutils-riscv64-linux-gnu gcc-riscv64-linux-gnu g++-riscv64-linux-gnu \
                    qemu-system-riscv64

wget -P ~ https://git.io/.gdbinit

pip3 install pygments
```

Further, gdb based debugging can also be done by running the following commands in two separate terminals:
```
make debug
```
and
```
make gdb
```
![Qemu Debug](docs/images/debug.gif)

You should see similar output as in above visual.

# Documentation

- To be able to run all the example and create your own project follow the documentation in [docs/](docs/index.md#table-of-contents).
- It also provides details about the internal workings of shell and how to setup your own project.

## Table of contents
| Topic| Description |
| :--- |:---        |
|[How shell Works](docs/shell-working.md)|Explains the working of shell with a flowchart.|
|[Running examples in `example/`](docs/00-setup-examples.md)|Guides on getting started with trying examples. Includes topics like - <br/> - `installing dependences`<br/> - `qemu based targets`<br/> - `physical board based targets`<br/> - `debugging` etc |
|[Setting up new project](docs/01-setting-up-new-project.md)|Details on how to start setting up a new project.|
|[Platform initialization and uart driver](docs/02-platform_init-and-uart-driver.md)|Details the implementation of the `platform_init()` and the relation to the uart driver.|
|[Uart driver](docs/03-uart-driver.md)| Describes implementation and constraint on the uart driver.|
|[User Linker Scripts](docs/04-user-linker-scripts.md)|Guides on how a liner script should be written if the user wants to manually set the memory layout and do the code placement.|
## Contributing

| Topic| Description |
| :--- |:----        |
| [Code of Conduct](docs/code-of-conduct.md) |Guides on the conduct expected while making contributions. |
|[Contributing](docs/contributing.md)|Guidelines on how to contribute to the code on GitHub.|

<hr>

# Source Code Headers

Every file containing source code must include copyright and license
information. This is to help well-intentioned people avoid accidental copying that
doesn't comply with the license.

Apache header:

    Copyright 2021 Google LLC

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
