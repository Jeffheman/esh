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

## Agent / MCP MVP (RISC-V QEMU)

The Linux host MCP server exposes a read-only interface to the RISC-V QEMU
example. MCP runs over stdio on the host; the firmware uses a bounded ASCII
protocol over UART. The default interactive shell remains available.

### Build and run

Install Python 3.10+, Python venv support, `gcc-riscv64-linux-gnu`,
`g++-riscv64-linux-gnu`, `binutils-riscv64-linux-gnu`, and `qemu-system-misc`.
From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ./host
make -C examples/emulation/riscv-64 MODE=rpc
make -C examples/emulation/riscv-64 MODE=rpc run
```

QEMU prints a PTY path such as `/dev/pts/3`. Configure an MCP client to launch
`.venv/bin/esh-mcp --port /dev/pts/3` using absolute paths to the executable and
port. Alternatively, launch that command from a second terminal to serve MCP
stdio; it is not an interactive terminal UI. The PTY path changes between runs.
Only one server should own a port, and no terminal emulator should share it.
Linux PTYs use a per-user lock file between MCP servers because WSL1 does not
support locking the PTY itself; physical Linux serial ports use pyserial's
exclusive lock. Neither prevents non-cooperating programs from interfering.

Call `get_device_info` first to establish compatibility, then use:

- `read_register(register="uart0.lcr")`
- `read_register_fields(register="uart0.lcr")`
- `run_named_test(test="uart.normal_access")`

Resources `esh://board/registers` and `esh://board/tests` describe the available
registers and diagnostics. The diagnostic checks only that DLAB is clear; PASS
is not a claim of transmit readiness or general device health. LSR is deliberately
not exposed, since reading it can clear UART error indications. MMIO writes,
raw addresses, arbitrary shell commands, reset and flashing are not supported.
This MVP covers QEMU only, not physical-board or external I2C/SPI access.

The versioned descriptor in `host/src/esh_mcp/data/riscv64-virt.json` is packaged
with the server and generates the firmware allowlist during the RPC build. The
handshake compares a SHA-256 digest of the complete canonical descriptor, not
just a manually maintained version string. Restart the server and rebuild the
firmware after changing that descriptor.

### Wire protocol

Each ASCII frame ends with one LF and is at most 256 bytes including LF. Fields
are separated by single spaces. IDs are 16 lowercase hexadecimal characters.
CRLF, control bytes, overlong frames and invalid IDs are discarded; no partial
or truncated request is executed. A subsequent LF restores the frame boundary.

```text
@ESH1 0000000000000001 HELLO
@ESH1 0000000000000001 OK HELLO board=riscv64-virt fw=<revision> map=<digest> ops=READ,TEST
@ESH1 0000000000000002 READ uart0.lcr
@ESH1 0000000000000002 OK READ reg=uart0.lcr width=8 value=0x00
@ESH1 0000000000000003 TEST uart.normal_access
@ESH1 0000000000000003 OK TEST test=uart.normal_access result=PASS reg=uart0.lcr width=8 value=0x00
@ESH1 0000000000000004 READ uart0.lsr
@ESH1 0000000000000004 ERR UNKNOWN_REGISTER
```

Values above are illustrative. `OK` means the operation executed; test results
can still be `FAIL`. Errors include `BAD_REQUEST`, `UNSUPPORTED_OP`,
`UNKNOWN_REGISTER` and `UNKNOWN_TEST`. The server validates response IDs,
operations, fields and value widths and serializes requests. It does not retry
operations automatically. After a timeout, malformed response or I/O failure,
call `get_device_info` again before further reads; a timeout means the result
is unknown, not that execution did not happen. There is no wire checksum or
authentication: use only a trusted local lab connection. Host receive timestamps
are not hardware sampling timestamps.

### Tests and interactive-shell regression

```sh
.venv/bin/python -m unittest discover -s host/tests -v
.venv/bin/python tests/test_manifest.py
make -C examples/emulation/riscv-64 MODE=shell
.venv/bin/python tests/test_qemu_mcp.py
```

The integration suite starts and stops its own QEMU processes, exercises raw
protocol error recovery, connects a real MCP stdio client through the server
and serial PTY, and checks the original shell. Both firmware variants must be
built first. `clean` affects the selected mode only; use `MODE=rpc clean` for
RPC objects. Use `make -B` when changing compiler options such as `OPTIMIZATION`.
Set `ESH_QEMU` to an alternate QEMU executable if needed. Run the
original terminal interface with `make -C examples/emulation/riscv-64 MODE=shell run`;
use Ctrl+A, X to exit that interface or Ctrl+C to stop the RPC QEMU process.

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
