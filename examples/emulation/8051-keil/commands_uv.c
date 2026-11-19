/* Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0 */
/* The Python backend generates its own tables; only the native project uses these. */
#ifdef ESH_UVISION_COMMANDS
#include "shell.h"

#ifndef SHELL_NO_HISTORY
extern const cmd_t SHELL_CODE esh_cmd_show_history;
#endif
extern const cmd_t SHELL_CODE esh_cmd_help;
extern const cmd_t SHELL_CODE esh_cmd_cmd_exec_status;
#ifndef SHELL_NO_UTILS
#ifndef SHELL_NO_BIT_UTILS
extern const cmd_t SHELL_CODE esh_cmd_w32_bit;
extern const cmd_t SHELL_CODE esh_cmd_r32_bit;
#endif
extern const cmd_t SHELL_CODE esh_cmd_r32;
extern const cmd_t SHELL_CODE esh_cmd_w32;
extern const cmd_t SHELL_CODE esh_cmd_read_mem;
#endif
extern const cmd_t SHELL_CODE esh_cmd_hello;
extern const cmd_t SHELL_CODE esh_auto_build_info;
extern const cmd_t SHELL_CODE esh_auto_boot;

static const cmd_t SHELL_CODE esh_end = {0, 0, 0};

cmd_ref const SHELL_CODE esh_commands[] = {
#ifndef SHELL_NO_HISTORY
  &esh_cmd_show_history,
#endif
  &esh_cmd_help,
  &esh_cmd_cmd_exec_status,
#ifndef SHELL_NO_UTILS
#ifndef SHELL_NO_BIT_UTILS
  &esh_cmd_w32_bit,
  &esh_cmd_r32_bit,
#endif
  &esh_cmd_r32,
  &esh_cmd_w32,
  &esh_cmd_read_mem,
#endif
  &esh_cmd_hello,
  &esh_auto_build_info,
  &esh_auto_boot,
  &esh_end
};

cmd_ref const SHELL_CODE esh_auto_commands[] = {
  &esh_auto_build_info,
  &esh_auto_boot,
  &esh_end
};
#endif
