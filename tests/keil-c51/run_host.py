# Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description="Run shared shell regression tests on the host")
    parser.add_argument("--cc", default=None)
    parser.add_argument("--vcvars", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    compiler = args.cc or ("cl" if args.vcvars else None)
    compiler = compiler or next((name for name in ("cc", "gcc", "clang", "cl") if shutil.which(name)), None)
    if not compiler:
        parser.error("No host compiler found; use --cc or --vcvars PATH")
    includes = [root / "shell/shell"] + sorted((root / "shell/lib").iterdir())
    source = Path(__file__).with_name("test_shell.c")
    with tempfile.TemporaryDirectory(prefix="esh-host-") as temp:
        output = Path(temp) / ("test.exe" if os.name == "nt" else "test")
        if Path(compiler).stem.lower() == "cl":
            command = [compiler, "/nologo", "/TC", "/W4", "/Od", str(source),
                       "/Fe:" + str(output), "/Fo:" + str(Path(temp) / "test.obj")]
            command += ["/I" + str(path) for path in includes]
        else:
            command = [compiler, "-std=c99", "-Wall", "-Wextra", "-Wno-unused-parameter",
                       "-fno-builtin", "-g", str(source), "-o", str(output)]
            command += ["-I" + str(path) for path in includes]
        if args.vcvars:
            line = 'call "' + str(args.vcvars.resolve()) + '" >nul && ' + subprocess.list2cmdline(command)
            subprocess.run('cmd.exe /d /s /c "' + line + '"', check=True, cwd=root)
        else:
            subprocess.run(command, check=True, cwd=temp)
        subprocess.run([str(output)], check=True, timeout=30)


if __name__ == "__main__":
    main()
