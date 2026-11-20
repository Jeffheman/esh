# Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("c51_build", ROOT / "shell/toolchains/keil-c51/build.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
SIM_SPEC = importlib.util.spec_from_file_location("c51_simulator", Path(__file__).with_name("run_simulator.py"))
SIMULATOR = importlib.util.module_from_spec(SIM_SPEC)
SIM_SPEC.loader.exec_module(SIMULATOR)


class CommandTableTests(unittest.TestCase):
    def render(self, *contents):
        with tempfile.TemporaryDirectory() as temp:
            files = []
            for index, content in enumerate(contents):
                path = Path(temp) / f"{index}.i"
                path.write_text(content, encoding="utf-8")
                files.append(path)
            return BUILD.command_table(files)

    def test_multiple_units_and_auto_visibility(self):
        result = self.render('const cmd_t code esh_cmd_first = {"first", "help", &first};',
                             'const cmd_t code esh_auto_second = {"second", "help", &second};')
        self.assertIn('extern const cmd_t SHELL_CODE esh_cmd_first;', result)
        self.assertEqual(result.count('&esh_auto_second,'), 2)
        self.assertEqual(result.count('&esh_cmd_first,'), 1)
        self.assertEqual(result.count('&esh_end'), 2)
        self.assertLess(result.index('&esh_cmd_first,'), result.index('&esh_auto_second,'))

    def test_empty_tables_have_sentinel(self):
        result = self.render('#line 1 "file.c" /0\n')
        self.assertEqual(result.count('&esh_end'), 2)
        self.assertNotIn('extern const cmd_t', result)

    def test_descriptor_text_in_string_is_ignored(self):
        result = self.render('const char code text[] = "const cmd_t code esh_cmd_fake =";')
        self.assertNotIn('esh_cmd_fake', result)

    def test_duplicate_symbols_are_rejected(self):
        with self.assertRaises(ValueError):
            self.render('const cmd_t code esh_cmd_f = {};', 'const cmd_t code esh_cmd_f = {};')

    def test_macro_expansion_whitespace(self):
        result = self.render('const\ncmd_t\tcode\n esh_auto_boot\n= {0};')
        self.assertEqual(result.count('&esh_auto_boot,'), 2)


class ToolInvocationTests(unittest.TestCase):
    def test_compiler_uses_response_file(self):
        with tempfile.TemporaryDirectory() as temp:
            response = Path(temp) / "compile.c51"
            with patch.object(BUILD.subprocess, "run", return_value=Mock(returncode=0)) as run:
                BUILD.run(Path("C51.exe"), ["source.c", "LARGE"], response, {})
            run.assert_called_once_with(["C51.exe", "@" + str(response)], env={})

    def test_hex_converter_receives_direct_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            response = Path(temp) / "hex.oh51"
            arguments = [str(Path(temp) / "with spaces.abs"), "HEXFILE(with spaces.hex)"]
            with patch.object(BUILD.subprocess, "run", return_value=Mock(returncode=0)) as run:
                BUILD.run(Path("OH51.exe"), arguments, response, {}, use_response=False)
            run.assert_called_once_with(["OH51.exe", *arguments], env={})

    def test_warning_status_is_not_a_tool_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(BUILD.subprocess, "run", return_value=Mock(returncode=1)):
                BUILD.run(Path("BL51.exe"), [], Path(temp) / "link.bl51", {})

    def test_tool_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(BUILD.subprocess, "run", return_value=Mock(returncode=3)):
                with self.assertRaises(RuntimeError):
                    BUILD.run(Path("BL51.exe"), [], Path(temp) / "link.bl51", {})


MAKE = os.environ.get("MAKE") or shutil.which("make")


@unittest.skipUnless(MAKE, "Set MAKE or install GNU Make to test the Make entry point")
class MakeEntryTests(unittest.TestCase):
    def run_make(self, *arguments, env=None):
        result = subprocess.run([MAKE, "-n", "--no-print-directory", "-C",
                                 str(ROOT / "examples/emulation/8051-keil"),
                                 "compile-only", *arguments],
                                capture_output=True, text=True, env=env, timeout=30)
        diagnostic = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, diagnostic)
        return diagnostic

    def test_default_keeps_full_features(self):
        command = self.run_make()
        self.assertIn("--compile-only", command)
        self.assertNotIn("SHELL_NO_", command)
        self.assertNotIn("SHELL_PRINTF_LITE", command)

    def test_existing_prompt_and_echo_settings_are_forwarded(self):
        command = self.run_make("PROMPT=board", "ECHO_INIT_VALUE=0")
        self.assertIn('--define "__PROMPT__=board"', command)
        self.assertIn('--define "ECHO_INIT_VALUE=0"', command)

    def test_no_unix_tools_are_needed(self):
        env = os.environ.copy()
        env["PATH"] = ""
        command = self.run_make(env=env)
        self.assertNotIn("nproc", command)

    def test_lite_features_survive_custom_command_line_definitions(self):
        command = self.run_make("SHELL_LITE=1", "C51_DEFINES=CUSTOM=1")
        self.assertIn('--define "CUSTOM=1"', command)
        for feature in ("SHELL_PRINTF_LITE", "SHELL_NO_PRINTF_LL", "SHELL_NO_UTILS",
                        "SHELL_NO_HISTORY", "SHELL_NO_TAB_COMPLETE", "SHELL_NO_BIT_UTILS"):
            self.assertIn(f'--define "{feature}"', command)

    def test_explicit_c51_definitions_follow_common_settings(self):
        command = self.run_make("ECHO_INIT_VALUE=0", "C51_DEFINES=ECHO_INIT_VALUE=1")
        self.assertLess(command.index('--define "ECHO_INIT_VALUE=0"'),
                        command.index('--define "ECHO_INIT_VALUE=1"'))


class UvisionProjectTests(unittest.TestCase):
    def setUp(self):
        self.project = ROOT / "examples/emulation/8051-keil"
        self.target = ET.parse(self.project / "esh-8051.uvproj").find("./Targets/Target")

    def test_native_project_sources_and_memory_settings(self):
        sources = []
        for entry in self.target.findall("./Groups/Group/Files/File"):
            path = (self.project / entry.findtext("FilePath").replace("\\", "/")).resolve()
            self.assertTrue(path.is_file(), path)
            if entry.findtext("FileType") in ("1", "2"):
                sources.append(path)
        expected = [self.project / name for name in ("hello.c", "platform.c", "commands_uv.c")]
        expected += [ROOT / "shell/shell/shell.c", ROOT / "shell/toolchains/keil-c51/startup.a51"]
        expected += list((ROOT / "shell/lib").rglob("*.c"))
        self.assertCountEqual(sources, expected)
        options = self.target.find("TargetOption")
        self.assertEqual(options.findtext("Target51/Target51Misc/MemoryModel"), "2")
        self.assertEqual(options.findtext("Target51/C51/ObjectExtend"), "1")
        self.assertEqual(options.findtext("Target51/C51/IntegerPromotion"), "1")
        self.assertEqual(options.findtext("Target51/C51/WarningLevel"), "1")
        self.assertIn("NOOVERLAY", options.findtext("Target51/Lx51/MiscControls"))
        self.assertEqual(options.findtext("Target51/Lx51/XDataBaseAddress"), "0x0000-0xEFFF")
        self.assertEqual(options.findtext("TargetCommonOption/CreateHexFile"), "1")
        self.assertEqual(options.findtext("DebugOption/Simulator/UseSimulator"), "1")
        for hook in ("BeforeCompile", "AfterMake"):
            for step in ("RunUserProg1", "RunUserProg2"):
                self.assertEqual(options.findtext(f"TargetCommonOption/{hook}/{step}"), "0")
        hook = options.find("TargetCommonOption/BeforeMake")
        self.assertEqual(hook.findtext("RunUserProg1"), "1")
        self.assertEqual(hook.findtext("RunUserProg2"), "0")
        self.assertEqual(hook.findtext("nStopB1X"), "2")
        self.assertIn('--uvision-project "#P"', hook.findtext("UserProg1Name"))
        self.assertIn('--uvision-output "#L"', hook.findtext("UserProg1Name"))
        self.assertIn('--keil-root "$K."', hook.findtext("UserProg1Name"))

    def copy_project(self, directory):
        directory = Path(directory)
        document = ET.parse(self.project / "esh-8051.uvproj")
        target = document.find("./Targets/Target")
        for entry in target.findall("./Groups/Group/Files/File"):
            source = (self.project / entry.findtext("FilePath").replace("\\", "/")).resolve()
            if source.parent == self.project:
                shutil.copy2(source, directory / source.name)
                entry.find("FilePath").text = source.name
            else:
                entry.find("FilePath").text = str(source)
        includes = target.find("TargetOption/Target51/C51/VariousControls/IncludePath")
        includes.text = ";".join(str((self.project / value.replace("\\", "/")).resolve())
                                 for value in includes.text.split(";"))
        hook = target.find("TargetOption/TargetCommonOption/BeforeMake/UserProg1Name")
        hook.text = (f'"{sys.executable}" "{ROOT / "shell/toolchains/keil-c51/build.py"}" '
                     '--uvision-project "#P" --uvision-output "#L" --keil-root "$K."')
        path = directory / "test.uvproj"
        document.write(path, encoding="utf-8", xml_declaration=True)
        return path

    def generate(self, project, target="Simulator", success=True, keil=None):
        command = [sys.executable, str(ROOT / "shell/toolchains/keil-c51/build.py"),
                   "--keil-root", keil or os.environ["KEIL_C51_ROOT"],
                   "--uvision-project", str(project), "--target", target]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0 if success else 2, result.stdout + result.stderr)
        return result.stdout + result.stderr

    @unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to verify native command tables")
    def test_native_tables_match_automatic_registration(self):
        definitions = self.target.findtext("TargetOption/Target51/C51/VariousControls/Define").split(",")
        for feature in (None, "SHELL_NO_HISTORY", "SHELL_NO_UTILS", "SHELL_NO_BIT_UTILS"):
            with self.subTest(feature=feature), tempfile.TemporaryDirectory(prefix="esh uvision table ") as temp:
                project = self.copy_project(temp)
                document = ET.parse(project)
                if feature:
                    element = document.find("./Targets/Target/TargetOption/Target51/C51/VariousControls/Define")
                    element.text += "," + feature
                document.write(project, encoding="utf-8", xml_declaration=True)
                self.assertNotIn("*** WARNING", self.generate(project))
                output = Path(temp) / "build/python"
                command = [sys.executable, str(ROOT / "shell/toolchains/keil-c51/build.py"),
                           "--keil-root", os.environ["KEIL_C51_ROOT"], "--project-dir", str(self.project),
                           "--output-dir", str(output), "--compile-only"]
                for definition in definitions + ([feature] if feature else []):
                    if definition != "ESH_UVISION_COMMANDS":
                        command.extend(["--define", definition])
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("*** WARNING", result.stdout + result.stderr)
                native = (Path(temp) / "build/uvision/commands.inc").read_text()
                generated = (output / "commands.c").read_text()
                self.assertEqual(native, "#define ESH_COMMAND_TABLE_READY 1\n" + generated)

    def test_environment_include_paths_are_expanded(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            with patch.dict(os.environ, {"ProgramFiles(x86)": temp}):
                self.assertEqual(BUILD.uvision_path('{ProgramFiles(x86)}/headers', project), project / "headers")
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "Undefined uVision"):
                BUILD.uvision_path("{MISSING}/headers", project)

    def test_included_files_override_group_exclusion(self):
        for group_value, file_value, included in (("2", "2", True), ("0", "2", False),
                                                   ("1", "2", True), ("2", "0", False), ("0", "1", True)):
            with self.subTest(group=group_value, file=file_value), tempfile.TemporaryDirectory() as temp:
                project = self.copy_project(temp)
                document = ET.parse(project)
                group = document.find("./Targets/Target/Groups/Group")
                common = ET.SubElement(ET.SubElement(group, "GroupOption"), "CommonProperty")
                ET.SubElement(common, "IncludeInBuild").text = group_value
                entry = group.find("Files/File")
                common = ET.SubElement(ET.SubElement(entry, "FileOption"), "CommonProperty")
                ET.SubElement(common, "IncludeInBuild").text = file_value
                document.write(project, encoding="utf-8", xml_declaration=True)
                sources = BUILD.uvision_sources(project, "Simulator", Path(temp))
                self.assertEqual(Path(temp) / "hello.c" in [source for source, _ in sources], included)

    def test_defines_undefines_and_include_order_match_uvision(self):
        with tempfile.TemporaryDirectory() as temp:
            project = self.copy_project(temp)
            document = ET.parse(project)
            target = document.find("./Targets/Target")
            compiler = target.find("TargetOption/Target51/C51")
            controls = compiler.find("VariousControls")
            controls.find("Define").text = 'T_ONLY=11,SHARED=10,DROP_T=1,MSG="two words, a comma"'
            controls.find("Undefine").text = "T_ONLY"
            controls.find("IncludePath").text = "t1;t2"
            group = target.find("Groups/Group")
            group_compiler = ET.SubElement(ET.SubElement(ET.SubElement(group, "GroupOption"), "Group51"), "C51")
            ET.SubElement(group_compiler, "IntegerPromotion").text = "0"
            group_controls = ET.SubElement(group_compiler, "VariousControls")
            ET.SubElement(group_controls, "Define").text = "G_ONLY=22,SHARED=20,DROP_G=1"
            ET.SubElement(group_controls, "Undefine").text = "SHARED"
            ET.SubElement(group_controls, "IncludePath").text = "g1;g2"
            entry = group.find("Files/File")
            file_compiler = ET.SubElement(ET.SubElement(ET.SubElement(entry, "FileOption"), "File51"), "C51")
            ET.SubElement(file_compiler, "IntegerPromotion").text = "2"
            file_controls = ET.SubElement(file_compiler, "VariousControls")
            ET.SubElement(file_controls, "Define").text = "F_ONLY=33,SHARED=30"
            ET.SubElement(file_controls, "Undefine").text = "DROP_T,DROP_G,SHARED,SHARED"
            ET.SubElement(file_controls, "IncludePath").text = "f1;f2"
            document.write(project, encoding="utf-8", xml_declaration=True)
            sources = BUILD.uvision_sources(project, "Simulator", Path(temp))
            arguments = next(controls for source, controls in sources if source.name == "hello.c")
            self.assertIn('DEFINE(T_ONLY=11,MSG="two words, a comma",G_ONLY=22,SHARED=20,F_ONLY=33,SHARED=30,ESH_COMMAND_SCAN)', arguments)
            paths = [Path(temp) / part for part in ("f1", "f2", "g1", "g2", "t1", "t2", "INC")]
            self.assertIn("INCDIR(" + ";".join(map(str, paths)) + ")", arguments)
            self.assertIn("NOINTPROMOTE", arguments)

    @unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to verify scoped compiler settings")
    def test_scoped_macros_and_headers_use_real_c51(self):
        with tempfile.TemporaryDirectory(prefix="esh uvision scopes ") as temp:
            project = self.copy_project(temp)
            document = ET.parse(project)
            target = document.find("./Targets/Target")
            group = target.find("Groups/Group")
            file = group.find("Files/File")
            levels = [target.find("TargetOption/Target51/C51/VariousControls")]
            for parent, option, compiler in ((group, "GroupOption", "Group51"), (file, "FileOption", "File51")):
                node = ET.SubElement(ET.SubElement(ET.SubElement(parent, option), compiler), "C51")
                levels.append(ET.SubElement(node, "VariousControls"))
            for index, controls in enumerate(levels):
                directory = Path(temp) / f"headers {index}"
                directory.mkdir()
                (directory / "scope.h").write_text(f"#define HEADER_LEVEL {index}\n")
                includes = controls.find("IncludePath")
                if includes is None:
                    includes = ET.SubElement(controls, "IncludePath")
                includes.text = str(directory) + (";" + includes.text if includes.text else "")
                defines = controls.find("Define")
                if defines is None:
                    defines = ET.SubElement(controls, "Define")
                defines.text = (defines.text + "," if defines.text else "") + f"LEVEL_{index},DROP_{index}"
                misc = controls.find("MiscControls")
                if misc is None:
                    misc = ET.SubElement(controls, "MiscControls")
                misc.text = f"DEFINE(MISC_{index})"
            ET.SubElement(levels[2], "Undefine").text = "DROP_0,DROP_1"
            document.write(project, encoding="utf-8", xml_declaration=True)
            source = Path(temp) / "hello.c"
            source.write_text(source.read_text() + '\n#include <scope.h>\n'
                              '#if HEADER_LEVEL != 2 || !defined(LEVEL_0) || !defined(LEVEL_1) || !defined(LEVEL_2)\n'
                              '#error scoped options differ\n#endif\n'
                              '#if !defined(MISC_0) || !defined(MISC_1) || !defined(MISC_2)\n'
                              '#error scoped misc controls differ\n#endif\n'
                              '#if defined(DROP_0) || defined(DROP_1) || !defined(DROP_2)\n'
                              '#error scoped undefines differ\n#endif\n')
            self.generate(project)
            self.assertIn("&esh_cmd_hello,", (Path(temp) / "build/uvision/commands.inc").read_text())

    @unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to verify command discovery")
    def test_added_removed_and_conditional_commands(self):
        with tempfile.TemporaryDirectory(prefix="esh uvision commands ") as temp:
            project = self.copy_project(temp)
            source = Path(temp) / "hello.c"
            original = source.read_text()
            (Path(temp) / "commands.h").write_text(
                '#ifdef EXTRA_COMMAND\n'
                'static int extra(int argc, char **argv) { argc = argc; argv = argv; return 0; }\n'
                'ADD_CMD(extra, "extra", extra);\n'
                'AUTO_CMD(extra, "extra", extra);\n'
                '#endif\n', encoding="ascii")
            source.write_text(original + '\n#include "commands.h"\n', encoding="ascii")
            self.generate(project)
            table = Path(temp) / "build/uvision/commands.inc"
            self.assertNotIn("esh_cmd_extra", table.read_text())
            document = ET.parse(project)
            alternative = ET.fromstring(ET.tostring(document.find("./Targets/Target")))
            alternative.find("TargetName").text = "With extra commands"
            alternative.find("TargetOption/Target51/C51/VariousControls/Define").text += ",EXTRA_COMMAND"
            document.find("Targets").append(alternative)
            document.write(project, encoding="utf-8", xml_declaration=True)
            self.generate(project, target="With extra commands")
            self.assertIn("&esh_cmd_extra,", table.read_text())
            self.assertEqual(table.read_text().count("&esh_auto_extra,"), 2)
            timestamp = table.stat().st_mtime_ns
            self.generate(project, target="With extra commands")
            self.assertEqual(table.stat().st_mtime_ns, timestamp)
            source.write_text(original, encoding="ascii")
            self.generate(project, target="With extra commands")
            self.assertNotIn("esh_cmd_extra", table.read_text())
            self.assertNotIn("esh_auto_extra", table.read_text())
            extra_source = Path(temp) / "new_commands.c"
            extra_source.write_text('#include "shell.h"\n#include "commands.h"\n')
            entries = alternative.find("Groups/Group/Files")
            entry = ET.SubElement(entries, "File")
            ET.SubElement(entry, "FileName").text = extra_source.name
            ET.SubElement(entry, "FileType").text = "1"
            ET.SubElement(entry, "FilePath").text = extra_source.name
            document.write(project, encoding="utf-8", xml_declaration=True)
            self.generate(project, target="With extra commands")
            self.assertIn("&esh_cmd_extra,", table.read_text())
            self.assertEqual(table.read_text().count("&esh_auto_extra,"), 2)
            entries.remove(entry)
            document.write(project, encoding="utf-8", xml_declaration=True)
            self.generate(project, target="With extra commands")
            self.assertNotIn("esh_cmd_extra", table.read_text())
            self.assertNotIn("esh_auto_extra", table.read_text())

    @unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to verify C280 suppression")
    def test_unused_callback_parameters_do_not_abort_scan(self):
        with tempfile.TemporaryDirectory(prefix="esh uvision c280 ") as temp:
            project = self.copy_project(temp)
            source = Path(temp) / "hello.c"
            original = source.read_text()
            source.write_text(original + '\nstatic int unused(int argc, char **argv) { return 0; }\n'
                              'ADD_CMD(unused, "unused parameters", unused);\n')
            diagnostic = self.generate(project)
            self.assertNotIn("C280", diagnostic)
            self.assertIn("&esh_cmd_unused,", (Path(temp) / "build/uvision/commands.inc").read_text())

    @unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to verify scan failure handling")
    def test_scan_failures_invalidate_previous_tables(self):
        for failure in ("compiler", "target", "xml", "missing-header", "compile", "duplicate"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix="esh uvision failure ") as temp:
                project = self.copy_project(temp)
                self.generate(project)
                table = Path(temp) / "build/uvision/commands.inc"
                self.assertTrue(table.is_file())
                options = {}
                if failure == "compiler":
                    options["keil"] = temp
                elif failure == "target":
                    options["target"] = "nonexistent"
                elif failure == "xml":
                    project.write_text("<Project>")
                elif failure == "duplicate":
                    source = Path(temp) / "duplicate.c"
                    source.write_text('#include "shell.h"\n'
                                      'static int hello(int argc, char **argv) { argc = argc; argv = argv; return 0; }\n'
                                      'ADD_CMD(duplicate, "duplicate", hello);\n')
                    document = ET.parse(project)
                    entry = ET.SubElement(document.find("./Targets/Target/Groups/Group/Files"), "File")
                    ET.SubElement(entry, "FileName").text = source.name
                    ET.SubElement(entry, "FileType").text = "1"
                    ET.SubElement(entry, "FilePath").text = source.name
                    document.write(project, encoding="utf-8", xml_declaration=True)
                else:
                    source = Path(temp) / "hello.c"
                    extra = {'missing-header': '#include "nonexistent.h"', 'compile': '#error scan must stop'}[failure]
                    source.write_text(source.read_text() + "\n" + extra + "\n")
                diagnostic = self.generate(project, success=False, **options)
                if failure == "duplicate":
                    self.assertIn("Duplicate command descriptor", diagnostic)
                self.assertFalse(table.exists())

    @unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to test native uVision builds")
    def test_native_hook_incremental_rebuild_and_failure_stop(self):
        keil = Path(os.environ["KEIL_C51_ROOT"])
        if keil.name.lower() == "c51":
            keil = keil.parent
        uvision = keil / "UV4/UV4.exe"
        if not uvision.is_file():
            self.skipTest("uVision is not installed")
        with tempfile.TemporaryDirectory(prefix="esh uvision build ") as temp:
            project = self.copy_project(temp)
            output = Path(temp) / "build/uvision"
            output.mkdir(parents=True)
            log = Path(temp) / "build/build.log"

            current_image = output / "esh-8051.hex"
            previous_image_time = None

            def build(target_name="Simulator", destination=output):
                nonlocal current_image, previous_image_time
                current_image = destination / "esh-8051.hex"
                previous_image_time = current_image.stat().st_mtime_ns if current_image.exists() else None
                log.unlink(missing_ok=True)
                result = subprocess.run([str(uvision), "-b", str(project), "-t", target_name,
                                         "-j0", "-o", str(log)], timeout=90)
                return result.returncode, log.read_text(errors="replace")

            def compiled(code, diagnostic):
                self.assertIn("Generated uVision commands", diagnostic)
                self.assertNotIn("*** WARNING", diagnostic)
                self.assertNotIn("error C", diagnostic)
                if code:
                    self.assertIn("FATAL ERROR L250: CODE SIZE LIMIT", diagnostic)
                    self.assertEqual(diagnostic.count("FATAL ERROR"), 1, diagnostic)
                    self.assertEqual(code, 3, diagnostic)
                else:
                    self.assertNotIn("Target not created", diagnostic)
                    self.assertNotIn("FATAL ERROR", diagnostic)
                    self.assertIn("0 Error(s)", diagnostic)
                    self.assertTrue(current_image.is_file())
                    if "linking..." in diagnostic:
                        self.assertNotEqual(current_image.stat().st_mtime_ns, previous_image_time)

            compiled(*build())
            table = output / "commands.inc"
            original_time = table.stat().st_mtime_ns
            code, diagnostic = build()
            compiled(code, diagnostic)
            self.assertEqual(table.stat().st_mtime_ns, original_time)
            self.assertNotIn("compiling commands_uv.c", diagnostic)
            source = Path(temp) / "hello.c"
            original = source.read_text()
            source.write_text(original + '\nstatic int new_command(int argc, char **argv) { '
                              'argc = argc; argv = argv; return 0; }\n'
                              'ADD_CMD(new_command, "new", new_command);\n'
                              'AUTO_CMD(new_command, "new", new_command);\n')
            code, diagnostic = build()
            compiled(code, diagnostic)
            self.assertIn("compiling commands_uv.c", diagnostic)
            self.assertIn("&esh_cmd_new_command,", table.read_text())
            self.assertEqual(table.read_text().count("&esh_auto_new_command,"), 2)
            symbols = (output / "commands_uv.obj").read_bytes().upper()
            self.assertIn(b"ESH_CMD_NEW_COMMAND", symbols)
            self.assertIn(b"ESH_AUTO_NEW_COMMAND", symbols)
            source.write_text(original)
            code, diagnostic = build()
            compiled(code, diagnostic)
            self.assertIn("compiling commands_uv.c", diagnostic)
            self.assertNotIn("esh_cmd_new_command", table.read_text())
            source.write_text(original + '\n#include "nonexistent-command-header.h"\n')
            _, diagnostic = build()
            self.assertIn("Target not created", diagnostic)
            self.assertIn("Command scan failed", diagnostic)
            self.assertNotIn("compiling ", diagnostic)
            self.assertNotIn("linking...", diagnostic)
            self.assertFalse(table.exists())
            source.write_text(original)
            compiled(*build())
            document = ET.parse(project)
            hook = document.find("./Targets/Target/TargetOption/TargetCommonOption/BeforeMake/UserProg1Name")
            working_hook = hook.text
            hook.text = 'esh-missing-python-executable ' + hook.text.split('" ', 1)[1]
            document.write(project, encoding="utf-8", xml_declaration=True)
            _, diagnostic = build()
            self.assertIn("Target not created", diagnostic)
            self.assertNotIn("Generated uVision commands", diagnostic)
            self.assertNotIn("compiling ", diagnostic)
            self.assertNotIn("linking...", diagnostic)
            self.assertTrue(table.is_file())
            hook.text = working_hook
            alternative = ET.fromstring(ET.tostring(document.find("./Targets/Target")))
            alternative.find("TargetName").text = "Additional target"
            document.find("Targets").append(alternative)
            document.write(project, encoding="utf-8", xml_declaration=True)
            _, diagnostic = build(target_name="Additional target")
            self.assertIn("use distinct target output paths", diagnostic)
            self.assertIn("Target not created", diagnostic)
            self.assertNotIn("compiling ", diagnostic)
            self.assertNotIn("linking...", diagnostic)
            self.assertFalse(table.exists())
            additional_output = Path(temp) / "build/additional"
            additional_output.mkdir()
            alternative.find("TargetOption/TargetCommonOption/OutputDirectory").text = str(additional_output) + "\\"
            alternative.find("TargetOption/TargetCommonOption/ListingPath").text = str(additional_output) + "\\"
            alternative.find("TargetOption/Target51/C51/VariousControls/Define").text += ",TARGET_ONLY"
            document.write(project, encoding="utf-8", xml_declaration=True)
            source.write_text(original + '\n#ifdef TARGET_ONLY\n'
                              'static int target_only(int argc, char **argv) { argc = argc; argv = argv; return 0; }\n'
                              'ADD_CMD(target_only, "target", target_only);\n#endif\n')
            compiled(*build(target_name="Additional target", destination=additional_output))
            self.assertIn("&esh_cmd_target_only,", table.read_text())
            self.assertIn(b"ESH_CMD_TARGET_ONLY", (additional_output / "commands_uv.obj").read_bytes().upper())
            compiled(*build())
            self.assertNotIn("esh_cmd_target_only", table.read_text())


class ProjectDiscoveryTests(unittest.TestCase):
    def test_mixed_sources_headers_and_explicit_selection(self):
        for extension, explicit in ((".A51", False), (".A51", True), (".ASM", False), (".ASM", True)):
            with self.subTest(extension=extension, explicit=explicit), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                project = root / "project"
                project.mkdir()
                source = project / "MAIN.C"
                source.write_text("void main(void) {}", encoding="ascii")
                header = project / "board" / "CONFIG.H"
                header.parent.mkdir()
                header.write_text("#define BOARD 1", encoding="ascii")
                assembly = project / ("helper" + extension)
                assembly.write_text("END\n", encoding="ascii")
                startup = project / "STARTUP.A51"
                startup.write_text("END\n", encoding="ascii")
                include = project / "includes" / "CONSTANT.INC"
                include.parent.mkdir()
                include.write_text("ANSWER EQU 42\n", encoding="ascii")
                for directory in ("build", "objects", ".git"):
                    ignored = project / directory
                    ignored.mkdir()
                    (ignored / "ignored.C").write_text("#error Must not compile", encoding="ascii")
                    (ignored / "ignored.A51").write_text("Must not assemble", encoding="ascii")
                tools = root / "keil" / "BIN"
                tools.mkdir(parents=True)
                for tool in ("C51", "A51", "BL51", "OH51"):
                    (tools / (tool + ".exe")).touch()
                arguments = ["build.py", "--keil-root", str(tools.parent), "--project-dir", str(project),
                             "--startup", str(startup), "--standalone", "--compile-only"]
                if explicit:
                    (project / "unselected.cpp").write_text("#error Must not compile", encoding="ascii")
                    arguments.extend(["--source", str(source), "--source", str(assembly), "--source", str(startup)])

                def fake_run(tool, controls, response, env, use_response=True):
                    for control in controls:
                        if control.startswith("PREPRINT("):
                            Path(control[len("PREPRINT("):-1]).write_text("", encoding="ascii")

                with patch.object(sys, "argv", arguments), patch.object(BUILD, "revision", return_value="test"):
                    with patch.object(BUILD, "run", side_effect=fake_run) as run, redirect_stdout(StringIO()):
                        BUILD.main()
                self.assertEqual(run.call_count, 4)
                controls = next(call.args[1] for call in run.call_args_list if call.args[0].name == "C51.exe")
                self.assertEqual(controls[0], f'"{source}"')
                self.assertIn("OBJECTEXTEND", controls)
                self.assertIn(str(header.parent), next(value for value in controls if value.startswith("INCDIR(")))
                assembly_calls = [call.args for call in run.call_args_list if call.args[0].name == "A51.exe"]
                self.assertEqual([call[1][0] for call in assembly_calls], [f'"{assembly}"', f'"{startup}"'])
                for call in assembly_calls:
                    self.assertIn(str(include.parent), next(value for value in call[1] if value.startswith("INCDIR(")))
                    self.assertFalse(any(value.startswith("PREPRINT(") for value in call[1]))
                    self.assertNotIn("LARGE", call[1])


@unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to test native BL51 diagnostics")
class LinkDiagnosticsTests(unittest.TestCase):
    def test_unresolved_symbol_stops_before_hex_conversion(self):
        with tempfile.TemporaryDirectory(prefix="esh-c51-link-") as temp:
            project = Path(temp)
            (project / "main.c").write_text(
                "extern void missing_function(void);\n"
                "void main(void) { missing_function(); while (1) {} }\n", encoding="ascii")
            command = [sys.executable, str(ROOT / "shell/toolchains/keil-c51/build.py"),
                       "--keil-root", os.environ["KEIL_C51_ROOT"],
                       "--project-dir", str(project), "--standalone"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            diagnostic = result.stdout + result.stderr
            memory_map = (project / "build/esh.m51").read_text(errors="replace")
            self.assertIn("*** WARNING L1: UNRESOLVED EXTERNAL SYMBOL", memory_map)
            self.assertIn("*** WARNING L2: REFERENCE MADE TO UNRESOLVED EXTERNAL", memory_map)
            self.assertEqual(result.returncode, 2, diagnostic)
            self.assertFalse((project / "build/esh.hex").exists())
            self.assertNotIn("Built ", diagnostic)


@unittest.skipUnless(os.environ.get("KEIL_C51_ROOT"), "Set KEIL_C51_ROOT to test native C51 configuration guards")
class FullConfigurationTests(unittest.TestCase):
    def test_full_suite_configuration_and_assertion_count(self):
        cases = ((None, True), ("SHELL_NO_PRINTF_LL", True),
                 ("SHELL_PRINTF_LITE", False), ("SHELL_NO_HISTORY", False),
                 ("SHELL_NO_TAB_COMPLETE", False), ("SHELL_NO_UTILS", False),
                 ("SHELL_NO_BIT_UTILS", False))
        for definition, full in cases:
            with self.subTest(definition=definition), tempfile.TemporaryDirectory(prefix="esh-c51-config-") as temp:
                output = Path(temp) / "build"
                command = [sys.executable, str(ROOT / "shell/toolchains/keil-c51/build.py"),
                           "--keil-root", os.environ["KEIL_C51_ROOT"],
                           "--project-dir", str(Path(__file__).parent),
                           "--source", str(Path(__file__).with_name("test_shell.c")),
                           "--standalone", "--compile-only", "--output-dir", str(output)]
                if definition:
                    command.extend(["--define", definition])
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                diagnostic = result.stdout + result.stderr
                if full:
                    self.assertEqual(result.returncode, 0, diagnostic)
                    source = next(output.glob("*_test_shell.i")).read_text(encoding="utf-8", errors="replace")
                    # Every assertion in run_tests executes once.
                    self.assertEqual(len(re.findall(r"\bcheck_at\(\(", source)), SIMULATOR.SHELL_CHECKS)
                else:
                    self.assertEqual(result.returncode, 2, diagnostic)
                    self.assertIn("Full shell regression requires all features", diagnostic)


class MemoryRangeTests(unittest.TestCase):
    def test_invalid_and_overlapping_ranges_are_rejected_before_build(self):
        cases = (("garbage", "hexadecimal bounds"),
                 ("1000H-0FFFH", "ordered range"),
                 ("0H-10000H", "ordered range"),
                 ("0H-F000H", "reentrant stack reservation"),
                 ("F000H-FFFFH", "reentrant stack reservation"))
        for bounds, message in cases:
            with self.subTest(bounds=bounds), redirect_stderr(StringIO()) as error:
                with patch.object(sys, "argv", ["build.py", "--xdata-range", bounds]):
                    with self.assertRaises(SystemExit) as result:
                        BUILD.main()
                self.assertEqual(result.exception.code, 2)
                self.assertIn(message, error.getvalue())

    def test_board_startup_can_define_its_own_stack_reservation(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stderr(StringIO()) as error:
            arguments = ["build.py", "--xdata-range", "F000H-FFFFH", "--startup", str(Path(temp) / "board.a51"),
                         "--keil-root", temp]
            with patch.object(sys, "argv", arguments), self.assertRaises(SystemExit):
                BUILD.main()
            self.assertIn("Tool not found", error.getvalue())
            self.assertNotIn("stack reservation", error.getvalue())


class SimulatorResultTests(unittest.TestCase):
    def test_smoke_success(self):
        result = SIMULATOR.read_result("ESH_C51_TYPES=1\nESH_C51_SEED=1\nG\nESH_C51_SMOKE result=0 done=1\n", "smoke")
        self.assertEqual(result, "ESH_C51_SMOKE result=0 done=1")

    def test_smoke_failures_and_incomplete_logs_are_rejected(self):
        for text in ("", "ESH_C51_SMOKE result=0 done=0", "ESH_C51_SMOKE result=128 done=1",
                     'printf("ESH_C51_SMOKE result=%u done=%u\\n", smoke_result, smoke_done);',
                     "ESH_C51_SMOKE result=0 done=1 extra"):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                SIMULATOR.read_result("ESH_C51_TYPES=1\nESH_C51_SEED=1\n" + text, "smoke")

    def test_missing_or_incorrect_debug_types_are_rejected(self):
        for prefix in ("", "ESH_C51_TYPES=0\n"):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(RuntimeError, "OBJECTEXTEND"):
                SIMULATOR.read_result(prefix + "ESH_C51_SEED=1\nESH_C51_SMOKE result=0 done=1\n", "smoke")

    def test_startup_address_from_map(self):
        self.assertEqual(SIMULATOR.startup_address("  CODE 0BE6H 009FH UNIT ?C_C51STARTUP\n"), 0x0BE6)

    def test_missing_startup_segment_is_rejected(self):
        with self.assertRaises(RuntimeError):
            SIMULATOR.startup_address("CODE 0BE6H 009FH UNIT ?PR?MAIN\n")

    def test_missing_or_failed_ram_prefill_is_rejected(self):
        for prefix in ("", "ESH_C51_SEED=0\n"):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(RuntimeError, "RAM prefill"):
                SIMULATOR.read_result("ESH_C51_TYPES=1\n" + prefix + "ESH_C51_SMOKE result=0 done=1\n", "smoke")

    def test_shell_success(self):
        result = SIMULATOR.read_result("ESH_C51_TYPES=1\nESH_C51_SEED=1\nESH_C51_SHELL checks=64 failures=0 done=1\n", "shell")
        self.assertIn("failures=0 done=1", result)

    def test_incorrect_shell_assertion_counts_are_rejected(self):
        for checks in (46, 58, 62, 63, 65, 65535):
            with self.subTest(checks=checks), self.assertRaises(RuntimeError):
                SIMULATOR.read_result(
                    f"ESH_C51_TYPES=1\nESH_C51_SEED=1\nESH_C51_SHELL checks={checks} failures=0 done=1\n", "shell")

    def test_shell_failures_and_incomplete_runs_are_rejected(self):
        for text in ("", "ESH_C51_SHELL checks=64 failures=1 done=1",
                     "ESH_C51_SHELL checks=64 failures=0 done=0",
                     "ESH_C51_SHELL checks=0 failures=0 done=1",
                     "ESH_C51_SMOKE result=0 done=1"):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                SIMULATOR.read_result("ESH_C51_TYPES=1\nESH_C51_SEED=1\n" + text, "shell")


if __name__ == "__main__":
    unittest.main()
