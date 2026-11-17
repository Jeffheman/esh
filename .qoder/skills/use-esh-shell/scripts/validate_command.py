# Copyright 2026 esh contributors
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

import argparse
import json


def validate(command, line_buffer_size, max_arg_count):
    if line_buffer_size < 2 or max_arg_count < 1:
        return {"valid": False, "error": "Require line_buffer_size >= 2 and max_arg_count >= 1"}
    if any(not 0x20 <= ord(char) <= 0x7E for char in command):
        return {"valid": False, "error": "Use printable ASCII only; exclude control bytes and line endings"}

    command_bytes = len(command.encode("ascii"))
    argument_count = len([token for token in command.split(" ") if token])
    result = {
        "command_bytes": command_bytes,
        "max_command_bytes": line_buffer_size - 1,
        "argument_count": argument_count,
        "max_arg_count": max_arg_count,
    }
    errors = []
    if argument_count == 0:
        errors.append("Command is empty")
    if command_bytes > line_buffer_size - 1:
        errors.append("Command exceeds input buffer capacity")
    if argument_count > max_arg_count:
        errors.append("Command exceeds argument capacity")
    return {"valid": not errors, **result, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Check esh Shell command bounds without sending or executing it")
    parser.add_argument("--line-buffer-size", type=int, required=True,
                        help="confirmed LINE_BUFF_SIZE of the target firmware")
    parser.add_argument("--max-arg-count", type=int, required=True,
                        help="confirmed MAX_ARG_COUNT, including the command name")
    parser.add_argument("command", help="complete command body, without its final LF")
    args = parser.parse_args()
    result = validate(args.command, args.line_buffer_size, args.max_arg_count)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
