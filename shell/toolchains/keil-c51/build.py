# Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0
import argparse
import getpass
import os
import socket
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


COMMAND = re.compile(r"\bconst\s+cmd_t\s+code\s+(esh_(?:cmd|auto)_\w+)\s*=")


def command_table(preprocessed):
    names = []
    for path in preprocessed:
        source = path.read_text(encoding="utf-8", errors="replace")
        source = re.sub(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' ''', '""', source, flags=re.VERBOSE)
        names.extend(COMMAND.findall(source))
    if len(names) != len(set(names)):
        raise ValueError("Duplicate command descriptor: use distinct command functions")
    normal = [name for name in names if name.startswith("esh_cmd_")]
    automatic = [name for name in names if name.startswith("esh_auto_")]
    lines = ['#include "shell.h"']
    lines.extend(f"extern const cmd_t SHELL_CODE {name};" for name in names)
    lines.append("static const cmd_t SHELL_CODE esh_end = {0, 0, 0};")
    for table, entries in (("esh_commands", normal + automatic), ("esh_auto_commands", automatic)):
        lines.append(f"cmd_ref const SHELL_CODE {table}[] = {{")
        lines.extend(f"  &{name}," for name in entries)
        lines.extend(["  &esh_end", "};"])
    return "\n".join(lines) + "\n"


def run(tool, arguments, response, env, use_response=True):
    response.write_text("\n".join(arguments) + "\n", encoding="ascii")
    invocation = ["@" + str(response)] if use_response else arguments
    result = subprocess.run([str(tool), *invocation], env=env)
    if result.returncode > 1 or result.returncode < 0:
        raise RuntimeError(f"{tool.name} failed ({result.returncode}); see {response}")


def uvision_path(value, project):
    def environment(match):
        name = match.group(1)
        if name not in os.environ:
            raise ValueError(f"Undefined uVision environment variable: {name}")
        return os.environ[name]

    value = re.sub(r"\{([^{}]+)\}", environment, value.strip().strip('"'))
    if "$" in value or "#" in value:
        raise ValueError(f"Unsupported uVision path expansion: {value}")
    return (project / value.replace("\\", "/")).resolve()


def uvision_sources(project_file, target_name, keil, target_output=None):
    project = project_file.parent
    targets = ET.parse(project_file).findall("./Targets/Target")
    if target_output is not None:
        matches = []
        for entry in targets:
            common = entry.find("TargetOption/TargetCommonOption")
            output = uvision_path(common.findtext("OutputDirectory", ""), project) / common.findtext("OutputName", "")
            if output.resolve() == target_output.resolve():
                matches.append(entry)
        if len(matches) != 1:
            raise ValueError(f"Expected one uVision target for {target_output}; use distinct target output paths")
        target = matches[0]
    else:
        target = next((entry for entry in targets if entry.findtext("TargetName") == target_name), None)
        if target is None:
            raise ValueError(f"uVision target not found: {target_name}")
    options = target.find("TargetOption")
    if target.findtext("ToolsetNumber") != "0x0" or options.findtext("Target51/Target51Misc/MemoryModel") != "2":
        raise ValueError("esh command registration requires a C51 LARGE-model target")
    compiler = options.find("Target51/C51")
    sources = []
    for group in target.findall("Groups/Group"):
        group_included = group.findtext("GroupOption/CommonProperty/IncludeInBuild", "1")
        for entry in group.findall("Files/File"):
            included = entry.findtext("FileOption/CommonProperty/IncludeInBuild", "2")
            if (group_included if included == "2" else included) == "0":
                continue
            if entry.findtext("FileType") != "1":
                continue
            source = uvision_path(entry.findtext("FilePath", ""), project)
            if source.suffix.lower() != ".c" or not source.is_file():
                raise ValueError(f"C51 requires an existing C source: {source}")
            layers = [node for node in (compiler, group.find("GroupOption/Group51/C51"),
                                         entry.find("FileOption/File51/C51")) if node is not None]
            definitions = []
            suppressed = set()
            includes = []
            promotion = "1"
            for level, layer in enumerate(layers):
                values = layer.findtext("VariousControls/Define", "")
                definitions.extend(re.findall(r'''(?:[^,\s"']+|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')+''', values))
                if level:
                    for name in re.split(r"[,\s]+", layer.findtext("VariousControls/Undefine", "").strip()):
                        # uVision suppresses the first matching record, including an already suppressed one.
                        index = next((i for i, value in enumerate(definitions) if value.partition("=")[0] == name), None)
                        if index is not None:
                            suppressed.add(index)
                paths = layer.findtext("VariousControls/IncludePath", "")
                includes = [uvision_path(value, project) for value in paths.split(";") if value.strip()] + includes
                if layer.findtext("IntegerPromotion") in ("0", "1"):
                    promotion = layer.findtext("IntegerPromotion")
            definitions = [value for index, value in enumerate(definitions) if index not in suppressed]
            controls = ["LARGE", "OBJECTEXTEND", "INCDIR(" + ";".join(map(str, includes + [keil / "INC"])) + ")",
                        "NOINTPROMOTE" if promotion == "0" else "INTPROMOTE",
                        "DEFINE(" + ",".join(definitions + ["ESH_COMMAND_SCAN"]) + ")"]
            warning = compiler.findtext("WarningLevel", "2")
            if warning in ("0", "1", "2", "3"):
                controls.append(f"WARNINGLEVEL({warning})")
            for layer in layers:
                misc = layer.findtext("VariousControls/MiscControls", "").strip()
                if misc:
                    controls.append(misc)
            sources.append((source, controls))
    if not sources:
        raise ValueError("No enabled C sources in uVision target")
    root = Path(__file__).resolve().parents[2]
    # Keep core/library registrations ahead of application commands, as in the Python backend.
    order = {path: index for index, path in enumerate([root / "shell/shell.c", *sorted((root / "lib").rglob("*.c"))])}
    return sorted(sources, key=lambda item: order.get(item[0], len(order)))


def generate_uvision_commands(project_file, target_name, keil_root, target_output=None):
    project_file = project_file.resolve()
    table = project_file.parent / "build/uvision/commands.inc"
    try:
        if not keil_root:
            raise ValueError("Pass --keil-root for the uVision C51 toolchain")
        keil = keil_root.resolve()
        if (keil / "C51/BIN/C51.exe").is_file():
            keil /= "C51"
        compiler = keil / "BIN/C51.exe"
        if not compiler.is_file():
            raise ValueError(f"Tool not found: {compiler}")
        sources = uvision_sources(project_file, target_name, keil, target_output)
        output = table.parent / "command-scan"
        output.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["C51INC"] = str(keil / "INC")
        preprocessed = []
        for index, (source, controls) in enumerate(sources):
            stem = f"{index:03d}_{source.stem}"
            pp = output / (stem + ".i")
            pp.unlink(missing_ok=True)
            response = output / (stem + ".c51")
            arguments = [f'"{source}"', *controls, "NOOBJECT", "NOPRINT", f'PREPRINT({pp})']
            response.write_text("\n".join(arguments) + "\n", encoding="ascii")
            result = subprocess.run([str(compiler), "@" + str(response)], cwd=project_file.parent, env=env)
            # Missing includes are only warnings in C51; accepting them could omit commands.
            if result.returncode != 0 or not pp.is_file():
                raise RuntimeError(f"Command scan failed ({result.returncode}); see {response}")
            preprocessed.append(pp)
        content = "#define ESH_COMMAND_TABLE_READY 1\n" + command_table(preprocessed)
        if not table.is_file() or table.read_text(encoding="ascii") != content:
            with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=table.parent, delete=False) as temp:
                temporary = Path(temp.name)
                temp.write(content)
            try:
                temporary.replace(table)
            finally:
                temporary.unlink(missing_ok=True)
        print(f"Generated uVision commands for {target_name or target_output} from {len(sources)} C sources: {table}")
    except Exception:
        table.unlink(missing_ok=True)
        raise


def revision(directory):
    if not shutil.which("git"):
        return "unknown"
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=directory,
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main():
    parser = argparse.ArgumentParser(description="Build a full-featured esh image with Keil C51/BL51")
    parser.add_argument("--keil-root", type=Path, default=os.environ.get("KEIL_C51_ROOT"))
    parser.add_argument("--uvision-project", type=Path, help="Generate native command tables from a uVision project")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--target", help="uVision target name for standalone command generation")
    selection.add_argument("--uvision-output", type=Path, help="Select the active uVision target using its #L output path")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--name", default="esh")
    parser.add_argument("--xdata-range", default="0000H-0EFFFH", help="BL51 static XDATA allocation, excluding the reentrant stack")
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--include", type=Path, action="append", default=[])
    parser.add_argument("--define", action="append", default=[])
    parser.add_argument("--standalone", action="store_true", help="Sources already contain the shell implementation (tests)")
    parser.add_argument("--startup", type=Path, default=Path(__file__).with_name("startup.a51"))
    parser.add_argument("--compile-only", action="store_true", help="Compile all sources and tables, but do not claim a linked image")
    args = parser.parse_args()
    if args.uvision_project:
        generate_uvision_commands(args.uvision_project, args.target, args.keil_root, args.uvision_output)
        return
    if args.target or args.uvision_output:
        parser.error("--target/--uvision-output requires --uvision-project")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", args.name):
        parser.error("--name must be a simple output filename without directories")
    if not re.fullmatch(r"[0-9A-Fa-f]+[Hh]-[0-9A-Fa-f]+[Hh]", args.xdata_range):
        parser.error("--xdata-range must use BL51 hexadecimal bounds, for example 0000H-0EFFFH")
    xdata_start, xdata_end = (int(bound[:-1], 16) for bound in args.xdata_range.split("-"))
    if not 0 <= xdata_start <= xdata_end <= 0xFFFF:
        parser.error("--xdata-range must be an ordered range within 0000H-FFFFH")
    if args.startup.resolve() == Path(__file__).with_name("startup.a51").resolve() and xdata_end > 0xEFFF:
        parser.error("--xdata-range overlaps the default reentrant stack reservation; supply a matching --startup")
    root = Path(__file__).resolve().parents[2]
    project = args.project_dir.resolve()
    output = (args.output_dir or project / "build").resolve()
    if args.keil_root:
        keil = args.keil_root.resolve()
        if (keil / "C51/BIN/C51.exe").exists():
            keil /= "C51"
    else:
        compiler = shutil.which("C51") or shutil.which("C51.exe")
        if not compiler:
            parser.error("Set KEIL_C51_ROOT or pass --keil-root pointing to Keil or its C51 directory")
        keil = Path(compiler).resolve().parents[1]
    tools = {name: keil / "BIN" / (name + ".exe") for name in ("C51", "A51", "BL51", "OH51")}
    for tool in tools.values():
        if not tool.is_file():
            parser.error(f"Tool not found: {tool}")
    project_files = sorted(path for path in project.rglob("*")
                           if path.is_file() and not path.is_relative_to(output)
                           and not {".git", "build", "objects"}.intersection(path.relative_to(project).parts))
    if not args.source and any(path.suffix.lower() in (".cpp", ".cxx", ".cc") for path in project_files):
        parser.error("C51 cannot compile C++; specify C/A51 --source files or port the project to C")
    source_extensions = (".c", ".a51", ".asm")
    sources = [path.resolve() for path in args.source] if args.source else [path for path in project_files if path.suffix.lower() in source_extensions]
    sources = [path for path in sources if path != args.startup.resolve()]
    if not sources:
        parser.error("No project sources found")
    if not args.standalone:
        sources = [root / "shell/shell.c", *sorted((root / "lib").rglob("*.c")), *sources]
    if any(path.suffix.lower() not in source_extensions or not path.is_file() for path in sources):
        parser.error("C51/A51 requires existing .c, .a51 or .asm sources; C++ and GNU assembly are not supported")
    output.mkdir(parents=True, exist_ok=True)
    includes = [root / "shell", *sorted((root / "lib").iterdir()), project,
                *sorted({path.parent for path in project_files if path.suffix.lower() in (".h", ".inc")}),
                *args.include, keil / "INC"]
    include_control = 'INCDIR(' + ';'.join(str(path.resolve()) for path in dict.fromkeys(includes)) + ')'
    definitions = {"ECHO_INIT_VALUE": "1", "__PROMPT__": "esh",
                   "__BUILD_USER__": re.sub(r"[^A-Za-z0-9_]", "_", getpass.getuser()),
                   "__BUILD_HOST__": re.sub(r"[^A-Za-z0-9_]", "_", socket.gethostname()),
                   "__SHELL_VERSION__": revision(root), "__USER_REPO_VERSION__": revision(project)}
    for definition in args.define:
        key, separator, value = definition.partition("=")
        definitions[key] = value if separator else None
    definitions = [key + ("=" + value if value is not None else "") for key, value in definitions.items()]
    # C51 has no per-warning-number switch; WARNINGLEVEL(1) drops the level-2
    # C280 (unreferenced command-callback parameters) while still reporting
    # missing includes (C318), macro redefinition (C317) and other diagnostics.
    controls = ["LARGE", "DEBUG", "OBJECTEXTEND", "OPTIMIZE(8,SPEED)", "INTPROMOTE", "WARNINGLEVEL(1)",
                include_control, "DEFINE(" + ",".join(definitions) + ")"]
    env = os.environ.copy()
    env["C51INC"] = str(keil / "INC")
    env["C51LIB"] = str(keil / "LIB")
    objects = []
    preprocessed = []
    for index, source in enumerate(sources):
        stem = f"{index:03d}_{source.stem}"
        obj = output / (stem + ".obj")
        if source.suffix.lower() == ".c":
            pp = output / (stem + ".i")
            run(tools["C51"], [f'"{source}"', *controls,
                              f'OBJECT({obj})', f'PRINT({output / (stem + ".lst")})',
                              f'PREPRINT({pp})'], output / (stem + ".c51"), env)
            preprocessed.append(pp)
        else:
            run(tools["A51"], [f'"{source}"', include_control,
                              f'OBJECT({obj})', f'PRINT({output / (stem + ".lst")})'],
                output / (stem + ".a51.args"), env)
        objects.append(obj)
    table = output / "commands.c"
    table.write_text(command_table(preprocessed), encoding="ascii")
    table_object = output / "commands.obj"
    run(tools["C51"], [f'"{table}"', *controls, f'OBJECT({table_object})',
                      f'PRINT({output / "commands.lst"})'], output / "commands.c51", env)
    objects.append(table_object)
    startup_object = output / "startup.obj"
    run(tools["A51"], [f'"{args.startup.resolve()}"', include_control, f'OBJECT({startup_object})',
                      f'PRINT({output / "startup.lst"})'], output / "startup.a51.args", env)
    objects.insert(0, startup_object)
    if args.compile_only:
        print(f"Compiled {len(objects)} objects; linking and execution were NOT verified.")
        return
    image = output / (args.name + ".abs")
    memory_map = output / (args.name + ".m51")
    run(tools["BL51"], [",\n".join(f'"{obj}"' for obj in objects), f'TO "{image}"',
                       "NOOVERLAY", "RAMSIZE(256)", f"XDATA({xdata_start:05X}H-{xdata_end:05X}H)",
                       f'PRINT({memory_map})'], output / "link.bl51", env)
    # BL51 still produces an image when unresolved symbols are reported as warnings.
    if re.search(r"^\s*\*\*\* WARNING L[12]:", memory_map.read_text(errors="replace"), re.MULTILINE):
        raise RuntimeError(f"BL51 reported unresolved external symbols; see {memory_map}")
    run(tools["OH51"], [str(image), f'HEXFILE({output / (args.name + ".hex")})'],
        output / "hex.oh51", env, use_response=False)
    print(f"Built {image} and {output / (args.name + '.hex')}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, ET.ParseError) as error:
        print(error, file=sys.stderr)
        sys.exit(2)
