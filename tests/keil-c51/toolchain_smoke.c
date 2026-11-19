/* Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0 */
#include "shell.h"

volatile unsigned int smoke_result;
volatile unsigned char smoke_done;
unsigned char idata smoke_upper _at_ 0x80;
volatile uint32_t smoke_initialized_value = 0x12345678UL;
volatile uint32_t smoke_zero_value;

static int callback(int argc, char **argv) {
  if (argc != 1 || argv[0][0] != 'o' || argv[0][1] != 'k') return -1;
  return 7;
}

static int boot_callback(int argc, char **argv) {
  return argc == 0 && argv == 0 ? 3 : -1;
}

ADD_CMD(smoke, "Check the C51 callback ABI", callback);
AUTO_CMD(boot, "Check automatic registration", boot_callback);

static int dispatch(int depth) SHELL_REENTRANT {
  char argument[] = "ok";
  char *arguments[1];
  int result;
  arguments[0] = argument;
  result = esh_commands[0]->command(1, arguments);
  if (depth != 0) result += dispatch(depth - 1);
  if (arguments[0][0] != 'o' || arguments[0][1] != 'k') return -1;
  return result;
}

void smoke_finished(void) {
  while (1) {}
}

void main(void) {
  smoke_result = 0;
  if (smoke_upper != 0 || smoke_zero_value != 0) smoke_result |= 1;
  if (smoke_initialized_value != 0x12345678UL) smoke_result |= 2;
  if (esh_commands[0]->command_name[0] != 's') smoke_result |= 4;
  if (esh_commands[1] != esh_auto_commands[0]) smoke_result |= 8;
  if (esh_commands[2]->command_name != 0) smoke_result |= 16;
  if (esh_auto_commands[1]->command_name != 0) smoke_result |= 32;
  if (esh_auto_commands[0]->command(0, 0) != 3) smoke_result |= 64;
  if (dispatch(2) != 21) smoke_result |= 128;
  if (reg32((uint16_t)&smoke_initialized_value) != 0x12345678UL) smoke_result |= 512;
  reg32((uint16_t)&smoke_zero_value) = 0x89abcdefUL;
  if (smoke_zero_value != 0x89abcdefUL) smoke_result |= 1024;
  smoke_done = 1;
  smoke_finished();
}
