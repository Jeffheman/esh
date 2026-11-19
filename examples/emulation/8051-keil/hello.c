/* Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0 */
#include "shell.h"

static int hello(int argc, char **argv) {
  int i;
  printf("Hello from esh on Keil C51\n");
  for (i = 1; i < argc; ++i) printf("%s\n", argv[i]);
  return 0;
}

static int boot(int argc, char **argv) {
  SHELL_UNUSED(argc);
  SHELL_UNUSED(argv);
  printf("8051 UART: 9600 baud, 11.0592 MHz, LARGE model\n");
  return 0;
}

ADD_CMD(hello, "Print a greeting and its arguments", hello);
AUTO_CMD(boot, "Print the board configuration", boot);
