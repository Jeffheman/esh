# 80C51 (MCS-51) example

This example builds with [SDCC](https://sdcc.sourceforge.net/). The UART
platform now uses the Star timer-based **TX-only** driver from
`../trunk/src/uart.c`, replacing the classic 8051 UART. Register definitions
come from the complete `../trunk/inc/star2.h` and
`../trunk/inc/star2_spi_slv_reg.h`, adapted into same-named platform headers
for SDCC: `__sfr`, `__sfr16`, `__sbit`, and `__xdata` accessors. The 16-bit
SFR declarations encode both byte addresses; 32-bit masks use `UL` constants
to avoid overflow with SDCC's 16-bit `int`. SPI window command codes remain
separate from SFR addresses, and disabled reference definitions stay disabled.

- TX uses P40, with `TCTL=0x11`, `TPR=0xB2`, and `TCNT=0`, matching the
  reference's 80 MHz DIE_TEST configuration. Actual baud depends on the clock.
- Initialization waits for `SPI_SLV_REQ.7`, clears CFG8's NF IO sleep and
  core-to-SPI isolation bits, and hands P40 control to the core.
- `uart_getc()` always returns `-1`: interactive commands are unavailable.
- SDCC startup is retained; linker bounds follow trunk's shared-SRAM layout.
  This is **not a bootable, hardware-validated Star firmware port**.
- Standard ucsim C52 UART emulation does not implement these Star peripherals.

## Requirements

- SDCC 4.5 or newer (`sdcc`, `sdnm`, `packihx`).
- Star provides 256 bytes of internal RAM, mapped into its shared SRAM.
  Boot handoff, watchdog handling, and hardware validation remain separate
  integration work.

## Installing SDCC

With root access:

```sh
sudo apt install sdcc sdcc-ucsim
```

Without root, extract the Debian packages into a user prefix and expose them:

```sh
mkdir -p ~/.local/opt/sdcc ~/.local/bin
cd /path/to/debs
for d in sdcc_*.deb sdcc-libraries_*.deb sdcc-ucsim_*.deb; do
    dpkg-deb -x "$d" ~/.local/opt/sdcc
done
ln -sf ~/.local/opt/sdcc/usr/bin/* ~/.local/bin/
```

Then put the include and library directories on the environment (the driver
defaults to `/usr/share/sdcc`):

```sh
export SDCC_INCLUDE=~/.local/opt/sdcc/usr/share/sdcc/include
export SDCC_LIB=~/.local/opt/sdcc/usr/share/sdcc/lib
```

`~/.local/bin` is already on `PATH` through `~/.profile` on most systems.

## Build

```sh
cd examples/physical/8051
make
```

`esh8051.hex` is the Intel HEX image; `esh8051.ihx` is the SDCC intermediate.
The build prints the internal RAM layout and code usage.

The Star TX timer settings are fixed in `platform/uart.c` to match trunk.
The former `F_CPU` and `UART_BAUD` build variables no longer configure UART.

If SDCC is installed outside its configured prefix, point the build at the
matching **stack-auto** libraries:

```sh
make SDCC_LIB=/path/to/sdcc/lib/small-stack-auto \
     SDCC_INCLUDE=/path/to/sdcc/include
```

Do not use `lib/small` here: `--stack-auto` links the reentrant library
variants.

## Star memory layout

The defaults follow `../trunk/Makefile`, `../trunk/inc/stddef.h`, and the
fixed buffers in `../trunk/src/Sspi.c`. CODE, XDATA, and internal RAM share
physical SRAM; they are not independent memory capacities.

| Use | Address range | Size | SDCC configuration |
| --- | --- | --- | --- |
| Internal RAM | `0x00-0xFF` | 256 bytes | `--iram-size 256` |
| Firmware CODE | `0x0000-0x2FFF` | 12 KiB | `--code-loc 0x0000 --code-size 0x3000` |
| Allocatable XDATA | `0x3000-0x3ADF` | 2784 bytes | `--xram-loc 0x3000 --xram-size 0x0AE0` |
| Reserved `datbuf` | `0x3AE0-0x3CFF` | 544 bytes | Excluded from automatic allocation |
| Reserved `botbuf` | `0x3D00-0x3EFF` | 512 bytes | Excluded from automatic allocation |
| Internal RAM backing | `0x3F00-0x3FFF` | 256 bytes | Excluded from CODE/XDATA allocation |

Trunk's XDATA linker range is `0x0000-0x3FFF`, but assigning that whole
16 KiB to SDCC would allow variables to overwrite firmware or reserved data.
The smaller allocatable range avoids those overlaps. SPI cache and retention
RAM are also excluded; `unknown_cmd_buf` at `0x4880-0x4AFF` is not ordinary
XRAM. No trunk buffer objects are added by this configuration.

Trunk places its Keil hardware stack at `0xC0-0xFF` (64 bytes). This build
retains SDCC's automatic stack placement within the same 256-byte IRAM:
`--stack-auto` also puts local variables and parameters on that stack, so the
Keil stack size is not copied. Check the generated `.mem` file for the current
stack start and capacity; capacity is not a runtime stack-usage measurement.

The chip resets into MROM at `0x8000`, but trunk's downloadable firmware is
linked at `0x0000`. `CODE_LOC` therefore stays at zero; this does not implement
the MROM-to-firmware handoff. Memory variables can be overridden in `make`,
but CODE/XDATA ranges must remain disjoint and avoid reserved SRAM. Use a
clean rebuild after changing compiler options.

## Classic 8051 hardware reference (previous driver only)

The following flashing and interactive examples describe the previous classic
8051 driver, not the current Star TX-only build. Do not use the current image
on STC/AT89 parts; their SFRs have different meanings.

Program `esh8051.hex` with the tool for your part, then open the UART at the
configured baud rate. For STC89C52RC, `stcgal` is one option:

```sh
stcgal -P stc89 -p /dev/ttyUSB0 esh8051.hex
```

The boot banner and prompt should appear:

```
Build: [...:...] - [...@...] - ...
8051 help
...
8051 sum 1 2 3
6
```

## Simulating with ucsim (previous driver only)

These commands are retained for the previous classic UART implementation.
They do not validate Star UART: the current build waits for Star SPI-domain
readiness, and C52 UART input/output is not connected to the Star registers.

`sdcc-ucsim` ships `ucsim_51`, an MCS-51 simulator that loads the same Intel
HEX image. With the image built:

```sh
ucsim_51 -t C52 -g -U 0 esh8051.ihx
```

- `-t C52` selects an 8052-class CPU with 256 bytes of internal RAM. Use it
  even for an 8051 build: `-t 51` only provides 128 bytes and `%d` overflows
  the stack at runtime.
- `-g` starts execution after loading the image.
- `-U 0` connects UART0 to stdin/stdout, so the shell prompt is usable
  directly. Press `^x` to reach the simulator control menu.
- The default crystal is 11.0592 MHz, matching the example; override it with
  `-X 12000000` if you built for another clock.

To stop a run started with `-g`, use `^x` from the UART display or run the
simulator under `timeout`. Command sequences can be scripted by piping them
in:

```sh
printf 'hello\rsum 1 2 3\r' | timeout 4 ucsim_51 -t C52 -g -U 0 -q esh8051.ihx
```

### Serial over TCP

File input is consumed as soon as the simulation starts, which is a poor fit
for an interactive shell. For scripted or remote tests, expose the UART on a
TCP port and run the command console on another:

```sh
ucsim_51 -t C52 -g -S 'uart=0,port=5679' -Z 5680 esh8051.ihx
```

Connect with `nc localhost 5679` (or `telnet`) to talk to the shell, and
`telnet localhost 5680` for the simulator console. You can also redirect the
UART to files with `-S 'uart=0,in=input.bin,out=output.bin'`.

### Simulator console

Without `-g` the CPU stays halted, so breakpoints can be set before running:

| Command | Effect |
| :-- | :-- |
| `run [start [stop]]`, `stop` | Start or stop execution |
| `step [n]`, `next` | Step one or more instructions |
| `break 0x0100`, `break x r 0x8000` | Code or memory access breakpoint |
| `clear`, `delete`, `info breakpoints` | Manage breakpoints |
| `state`, `pc [addr]` | CPU state and program counter |
| `di 0 0xff`, `dx 0 0xff`, `ds 0x80 0xff` | Dump IRAM, XRAM and SFRs |
| `dc 0 20`, `disassemble` | Disassemble code memory |
| `reset`, `file "x.hex"`, `check "x.hex"` | Reset, load or verify an image |
| `exec "cmdfile"`, `quit`, `kill` | Run a command script, close console, exit |

Commands passed with `-e` run at startup; `-G` starts the simulation and quits
when the CPU stops, which makes batch debug sessions possible:

```sh
ucsim_51 -t C52 -G -e 'break 0x0000' esh8051.ihx
```

Other useful startup options are `-X freq[k|M]` for the crystal, `-a nr` for
the variable space size, `-w` to make flash writable and `-q` for quiet
output. `-H` lists the supported CPU types. The full simulator manual is
installed as `~/.local/opt/sdcc/usr/share/doc/sdcc-ucsim/index.html` in the
user-prefix layout described above.

## How commands are registered

GCC builds place `ADD_CMD` descriptors in `.cmd_list` and `.auto_list`
sections, and the linker symbols delimit the tables. SDCC supports neither
custom sections nor weak symbols, so the descriptors cannot be collected at
link time. `tools/gen_shell_cmd_table.sh` replaces that mechanism by finding
the descriptors **after compilation**, by symbol name, and emitting an
explicit table.

`make` runs the generator once every source has been compiled, passing all
application and shell objects:

```sh
SDNM=sdnm tools/gen_shell_cmd_table.sh objects/*.rel > objects/shell_cmd_table.c
```

The script then:

1. Lists symbols in every `.rel` file with `sdnm`, discards undefined entries
   (`U`) and sorts the remaining names.
2. Matches `__shell_cmd_*` and `__shell_auto_*`. SDCC prefixes C identifiers
   with an underscore, so the descriptor `_shell_cmd_hello` appears as
   `__shell_cmd_hello`; one underscore is stripped to recover the C name.
3. Writes `objects/shell_cmd_table.c` with one `extern` per descriptor and two
   zero-terminated pointer tables, for example:

```c
extern SHELL_CODE cmd_t _shell_cmd_hello;

SHELL_CODE cmd_t *const shell_cmd_table[] = {
  &_shell_cmd_hello,
  /* ... */
  0
};
```

The generated file is compiled and linked with the other objects. The shell
core walks the tables through `cmd_at()`/`auto_at()`, so `help`, command
dispatch, tab completion and the startup `AUTO_CMD`s all read the same data.

Consequences worth knowing:

- Registration is automatic: add `ADD_CMD`/`AUTO_CMD` and rebuild; there is no
  hand-maintained list.
- Entries are ordered by symbol name, not source order, so `help` prints them
  in that order.
- The script requires at least one `_shell_cmd_*` and one `_shell_auto_*`
  symbol and fails otherwise; `version` in `shell.c` provides the AUTO entry.
- `objects/shell_cmd_table.c` is generated: do not edit it, and `make clean`
  deletes it. Set `SDNM` if `sdnm` is not on `PATH`.

Command descriptors and lookup tables live in flash, so they do not consume
internal RAM.

To add a command, define the function and use the same macros as other
examples:

```c
static int led(int argc, char **argv) {
  /* ... */
  return 0;
}

ADD_CMD(led, "Toggle the LED", led);
```

Add new application sources to the Makefile explicitly, because the SDCC build
does not use the GCC source-discovery makefiles.

## Configuration

The Makefile sets the memory-constrained feature set:

| Define | Effect |
| :--- | :--- |
| `LINE_BUFF_SIZE=12` | 12-character command line |
| `MAX_ARG_COUNT=6` | Up to 5 arguments after the command |
| `SHELL_NO_HISTORY` | No command history buffer |
| `SHELL_NO_PRINTF_LL` | No `long long` support in `printf` |
| `SHELL_NO_UTILS` / `SHELL_NO_BIT_UTILS` | Omit 32-bit register helpers |

`--stack-auto` is required. SDCC cannot call a non-reentrant function through
a pointer with two arguments, so all code, including the SDCC libraries, must
use the reentrant calling convention.

The SDCC build keeps tab completion enabled. Add `-DSHELL_NO_TAB_COMPLETE` to
`DEFINES` if you need more code space.

## Data model on MCS-51

SDCC's `int` is 16 bits on the 8051, unlike the 32-bit hosts used by the other
examples. The shell and libraries are checked against that width:

- Line input stops at `LINE_BUFF_SIZE - 1` characters and extra characters are
  dropped, so the 12-byte buffer cannot overwrite adjacent stack variables.
- `parse_line()` never writes past `MAX_ARG_COUNT` entries.
- `printf` sizes its digit buffer for 16-bit values. With `SHELL_NO_PRINTF_LL`,
  `%d`, `%u` and `%x` cover the full 16-bit range; `LAST_NIBBLE_FIRST_BIT` is
  derived from `sizeof(unsigned int)` instead of assuming 32-bit `int`.
- `atoi()` accepts a sign and saturates at `INT_MAX`/`INT_MIN` instead of
  overflowing. Numeric arguments are therefore limited to -32768..32767; use
  `atoh()` for 32-bit hex values.
- Constant lookup tables (the `printf` hex digits, command descriptors and the
  command table) live in code memory. Only writable state uses internal RAM.

Arithmetic in application commands still happens in 16-bit `int`; check for
overflow in your own commands, for example when summing large values.
