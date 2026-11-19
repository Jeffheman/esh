# Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0
import argparse
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time


def main():
    parser = argparse.ArgumentParser(description="Build the unchanged ARM example and test its GNU command registration in QEMU")
    parser.add_argument("--toolchain-prefix", default="arm-none-eabi-")
    parser.add_argument("--qemu", default="qemu-system-arm")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    project = root / "examples/emulation/armv7M-32"
    includes = [root / "shell/shell", *(root / "shell/lib").iterdir(), project / "platform/uart"]
    gcc = args.toolchain_prefix + "gcc"
    with tempfile.TemporaryDirectory(prefix="esh-arm-") as temp:
        work = Path(temp)
        objects = []
        sources = sorted((root / "shell").rglob("*.c")) + sorted(project.rglob("*.c"))
        for index, source in enumerate(sources):
            obj = work / f"{index}.o"
            subprocess.run([gcc, "-mcpu=cortex-m3", "-mthumb", "-Og", "-ffreestanding",
                            "-fno-builtin", "-g", "-c", str(source), "-o", str(obj),
                            "-DECHO_INIT_VALUE=1", "-D__PROMPT__=arm", "-DSTACK_START=0x3FFFF",
                            "-DSHELL_NO_PRINTF_LL", *["-I" + str(path) for path in includes]], check=True)
            objects.append(obj)
        startup = work / "startup.o"
        subprocess.run([gcc, "-march=armv7-m", "-c", str(root / "shell/startup/cortex-m.S"),
                        "-o", str(startup)], check=True)
        objects.append(startup)
        image = work / "shell.elf"
        subprocess.run([gcc, "-mcpu=cortex-m3", "-mthumb", "-nostdlib", *map(str, objects),
                        "-T" + str(root / "shell/scatter/one-seg.ld"), "-Wl,--defsym,__RAM_BASE__=0",
                        "-Wl,--defsym,__RAM_SIZE__=0x4000", "-lgcc", "-o", str(image)], check=True)
        proc = subprocess.Popen([args.qemu, "-M", "mps2-an385", "-cpu", "cortex-m3",
                                 "-display", "none", "-monitor", "none", "-serial", "stdio",
                                 "-kernel", str(image)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        received = queue.Queue()

        def read_output():
            while True:
                byte = proc.stdout.read(1)
                received.put(byte)
                if not byte:
                    return

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        transcript = bytearray()

        def wait_for(expected):
            chunk = bytearray()
            deadline = time.monotonic() + 15
            while expected not in chunk:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"Timed out waiting for {expected!r}: {chunk!r}")
                try:
                    byte = received.get(timeout=remaining)
                except queue.Empty as error:
                    raise RuntimeError(f"Timed out waiting for {expected!r}: {chunk!r}") from error
                if not byte:
                    raise RuntimeError(f"QEMU exited early: {transcript!r}")
                chunk.extend(byte)
                transcript.extend(byte)
            return bytes(chunk)

        def command(line, expected):
            for char in line.encode("ascii"):
                byte = bytes([char])
                proc.stdin.write(byte)
                proc.stdin.flush()
                wait_for(byte)
            proc.stdin.write(b"\n")
            proc.stdin.flush()
            response = wait_for(b"arm ")
            if expected not in response:
                raise AssertionError(f"{line!r}: expected {expected!r}, got {response!r}")

        try:
            wait_for(b"arm ")
            command("hello world", b"hello world ")
            command("help -l", b"history")
            command("w32 20001000 ffffffff", b"arm ")
            command("wb 20001000 31 0", b"arm ")
            command("r32 20001000", b"0x20001000: 0x7FFFFFFF")
            command("wb 20001000 31 1", b"arm ")
            command("rb 20001000 31", b"Bit 31 @ 0x20001000: 1")
            command("hello repeat", b"hello repeat ")
            command("missing", b"command not found")
            command("status", b"-1")
            print("ARM GNU/QEMU: 10 command checks passed")
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            reader.join(timeout=2)


if __name__ == "__main__":
    main()
