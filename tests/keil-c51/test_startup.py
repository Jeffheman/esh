# Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description="Verify C51 startup tests detect missing IDATA/XDATA clearing")
    parser.add_argument("--keil-root", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    output = Path(__file__).parent / "build/startup-validation"
    output.mkdir(parents=True, exist_ok=True)
    original = (ROOT / "shell/toolchains/keil-c51/startup.a51").read_text()
    cases = (("normal", None), ("no-xdata-clear", "MOVX @DPTR,A"),
             ("no-idata-clear", "MOV @R0,A"))
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=output) as directory:
        fixture = Path(directory)
        board = fixture / "board"
        board.mkdir()
        (board / "SMOKE_CONFIG.H").write_text("#define SMOKE_HEADER_CHECK 1\n", encoding="ascii")
        includes = fixture / "includes"
        includes.mkdir()
        (includes / "ANSWER.INC").write_text("ANSWER EQU 42\n", encoding="ascii")
        helper = fixture / "helper.A51"
        helper.write_text(
            "$INCLUDE(ANSWER.INC)\nNAME SMOKE_HELPER\n"
            "?PR?ASM_PROBE?SMOKE_HELPER SEGMENT CODE\nPUBLIC ASM_PROBE\n"
            "RSEG ?PR?ASM_PROBE?SMOKE_HELPER\nASM_PROBE:\nMOV R7,#ANSWER\nRET\nEND\n", encoding="ascii")
        source = (Path(__file__).parent / "toolchain_smoke.c").read_text()
        if source.count("smoke_result = 0;") != 1:
            raise RuntimeError("Cannot insert the assembly callback assertion")
        source = source.replace("smoke_result = 0;", "smoke_result = 0;\n  if (asm_probe() != 42) smoke_result |= 256;")
        (fixture / "MAIN.C").write_text(
            '#include "SMOKE_CONFIG.H"\n#if SMOKE_HEADER_CHECK != 1\n#error Header discovery failed\n#endif\n'
            'extern unsigned char asm_probe(void);\n' + source, encoding="ascii")
        for name, instruction in cases:
            build = fixture / "build" / name
            command = [sys.executable, str(ROOT / "shell/toolchains/keil-c51/build.py"),
                       "--keil-root", str(args.keil_root.resolve()), "--project-dir", str(fixture),
                       "--standalone", "--output-dir", str(build), "--name", "startup-test"]
            if not instruction:
                command.extend(["--xdata-range", "E000H-EFFFH"])
            if instruction:
                if original.count(instruction) != 1:
                    raise RuntimeError(f"Cannot isolate startup instruction: {instruction}")
                startup = fixture / "STARTUP.A51"
                startup.write_text('$INCLUDE(ANSWER.INC)\n' + original.replace(instruction, "NOP"), encoding="ascii")
                command.extend(["--startup", str(startup)])
            if name == "no-idata-clear":
                helper = helper.rename(fixture / "helper.ASM")
                command.extend(["--source", str(fixture / "MAIN.C"), "--source", str(helper), "--source", str(startup)])
            subprocess.run(command, check=True)
            image = build / "startup-test.abs"
            for suffix in (".abs", ".hex", ".m51"):
                shutil.copyfile(image.with_suffix(suffix), output / (name + suffix))
            shutil.copyfile(build / "startup.lst", output / (name + ".lst"))
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("run_simulator.py")),
                                     "--keil-root", str(args.keil_root.resolve()), "--image", str(image),
                                     "--suite", "smoke", "--timeout", str(args.timeout)],
                                    capture_output=True, text=True, timeout=args.timeout + 30)
            log = image.with_suffix(".sim.log").read_text(encoding="utf-8")
            (output / (name + ".sim.log")).write_text(log, encoding="utf-8")
            expected = 1 if instruction else 0
            marker = rf"^ESH_C51_SMOKE result={expected} done=1\s*$"
            if (result.returncode != expected or not re.search(marker, log, re.MULTILINE)
                    or not re.search(r"^ESH_C51_SEED=1\s*$", log, re.MULTILINE)
                    or not re.search(r"^ESH_C51_TYPES=1\s*$", log, re.MULTILINE)):
                raise RuntimeError(f"Unexpected {name} result: {result.stdout}{result.stderr}\n{log}")
            print(f"{name}: {'missing initialization detected' if instruction else 'passed'}", flush=True)
    print(f"Three startup scenarios verified; logs: {output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
