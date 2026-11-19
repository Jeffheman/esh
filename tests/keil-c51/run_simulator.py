# Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


SHELL_CHECKS = 64


def read_result(text, suite):
    if not re.search(r"^ESH_C51_TYPES=1\s*$", text, re.MULTILINE):
        raise RuntimeError("C51 debugger types are missing or incorrect; rebuild with OBJECTEXTEND")
    if not re.search(r"^ESH_C51_SEED=1\s*$", text, re.MULTILINE):
        raise RuntimeError("C51 simulator did not confirm RAM prefill")
    if suite == "smoke":
        match = re.search(r"^ESH_C51_SMOKE result=(\d+) done=(\d+)\s*$", text, re.MULTILINE)
        if not match or tuple(map(int, match.groups())) != (0, 1):
            raise RuntimeError("C51 smoke test did not reach completion with result=0")
    else:
        match = re.search(r"^ESH_C51_SHELL checks=(\d+) failures=(\d+) done=(\d+)\s*$", text, re.MULTILINE)
        if not match:
            raise RuntimeError("C51 shell test did not report completion")
        checks, failures, done = map(int, match.groups())
        if checks != SHELL_CHECKS or failures != 0 or done != 1:
            raise RuntimeError(f"C51 shell requires {SHELL_CHECKS} checks, zero failures and completion; got {checks}/{failures}/{done}")
    return match.group(0).strip()


def startup_address(text):
    match = re.search(r"^\s*CODE\s+([0-9A-F]+)H\s+[0-9A-F]+H\s+UNIT\s+\?C_C51STARTUP\s*$", text, re.MULTILINE)
    if not match:
        raise RuntimeError("BL51 map does not contain the C51 startup segment")
    return int(match.group(1), 16)


def main():
    parser = argparse.ArgumentParser(description="Run an existing test image in the Keil 8051 simulator; never builds a reduced shell")
    parser.add_argument("--keil-root", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--suite", choices=("smoke", "shell"), required=True)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    keil = args.keil_root.resolve()
    if keil.name.lower() == "c51":
        keil = keil.parent
    image = args.image.resolve()
    template = keil / "C51/Examples/HELLO/Hello.uvproj"
    executable = keil / "UV4/UV4.exe"
    memory_map = image.with_suffix(".m51")
    for path in (image, memory_map, template, executable):
        if not path.is_file():
            parser.error(f"Required file not found: {path}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    entry = startup_address(memory_map.read_text(errors="replace"))
    with tempfile.TemporaryDirectory(prefix="esh-c51-sim-", dir=image.parent) as directory:
        work = Path(directory)
        project = work / "test.uvproj"
        ini = work / "test.ini"
        log = work / "simulator.log"
        tree = ET.parse(template)
        target = tree.find("./Targets/Target")
        options = target.find("TargetOption")
        changes = {
            "TargetCommonOption/OutputDirectory": str(image.parent) + "\\",
            "TargetCommonOption/OutputName": image.name,
            "TargetCommonOption/Cpu": "IRAM(0-0xFF) XRAM(0-0xFFFF) IROM(0-0xFFFF) CLOCK(11059200) MODP2",
            "DebugOption/Simulator/RunToMain": "0",
            "DebugOption/Simulator/RestoreBreakpoints": "0",
            "DebugOption/Simulator/RestoreWatchpoints": "0",
            "DebugOption/Simulator/RestoreMemoryDisplay": "0",
            "DebugOption/Simulator/RestoreFunctions": "0",
            "DebugOption/Simulator/RestoreToolbox": "0",
            "DebugOption/Simulator/LimitSpeedToRealTime": "0",
            "DebugOption/SimDlls/InitializationFile": str(ini),
            "Target51/Target51Misc/MemoryModel": "2",
        }
        for path, value in changes.items():
            options.find(path).text = value
        for groups in list(target.findall("Groups")):
            target.remove(groups)
        tree.write(project, encoding="utf-8", xml_declaration=True)
        if args.suite == "smoke":
            seed = ["smoke_upper = 165;", "smoke_zero_value = 165;", "smoke_initialized_value = 0;",
                    'printf("ESH_C51_RAM upper=%u zero=%lu initialized=%lu\\n", smoke_upper, smoke_zero_value, smoke_initialized_value);']
            seeded = "smoke_upper == 165 && smoke_zero_value == 165 && smoke_initialized_value == 0"
            types = "sizeof(smoke_result) == 2 && sizeof(smoke_zero_value) == 4 && sizeof(smoke_initialized_value) == 4 && sizeof(smoke_done) == 1 && sizeof(smoke_upper) == 1"
            stop = "smoke_finished"
            report = 'printf("ESH_C51_SMOKE result=%u done=%u\\n", smoke_result, smoke_done);'
        else:
            seed = ["test_idata_upper = 165;", "test_checks = 165;", "test_failures = 165;", "test_done = 165;"]
            seeded = "test_idata_upper == 165 && test_checks == 165 && test_failures == 165 && test_done == 165"
            types = "sizeof(test_checks) == 2 && sizeof(test_failures) == 2 && sizeof(test_done) == 1 && sizeof(test_idata_upper) == 1"
            stop = "test_finished"
            report = 'printf("ESH_C51_SHELL checks=%u failures=%u done=%u\\n", test_checks, test_failures, test_done);'
        ini.write_text("\n".join([
            "MAP X:0x0000, X:0xFFFF READ WRITE", "LOG >simulator.log",
            "FUNC void SeedRAM(void) {", f'  printf("ESH_C51_TYPES=%u\\n", ({types}));',
            "  memset(X:0x0000, 0xF000, 165);", *seed,
            f'  printf("ESH_C51_SEED=%u\\n", ({seeded}));', "}",
            "FUNC void Report(void) {", "  " + report, "  _break_ = 1;",
            '  exec("LOG OFF");', "}", f'BS C:0x{entry:04X}, 1, "SeedRAM()"',
            f'BS {stop}, 1, "Report()"', "G 0x0000", "",
        ]), encoding="ascii")
        process = subprocess.Popen([str(executable), "-d", str(project), "-t", "Simulator", "-j0", "-sg"], cwd=work)
        try:
            process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            # Breakpoint callbacks cannot execute EXIT; stop only this isolated debugger.
            process.terminate()
            process.wait(timeout=10)
        text = log.read_text(errors="replace") if log.exists() else ""
        result_log = image.with_suffix(".sim.log")
        result_log.write_text(text, encoding="utf-8")
        print(read_result(text, args.suite))
        print(f"Simulator log: {result_log}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
