/* Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0 */
#include <REG52.H>
#include "shell.h"

static int uart_getchar(void) {
  unsigned char ch;
  if (!RI) return -1;
  ch = SBUF;
  RI = 0;
  return ch;
}

static void uart_putchar(char ch) {
  if (ch == '\n') {
    while (!TI) {}
    TI = 0;
    SBUF = '\r';
  }
  while (!TI) {}
  TI = 0;
  SBUF = ch;
}

void platform_init(void) {
  SCON = 0x50;
  TMOD = (TMOD & 0x0f) | 0x20;
  PCON &= 0x7f;
  TH1 = 0xfd;
  TL1 = 0xfd;
  TR1 = 1;
  TI = 1;
  set_read_char(uart_getchar);
  set_write_char(uart_putchar);
}

void main(void) {
  prompt();
}
