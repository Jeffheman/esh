/**
 * Copyright 2026 esh contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 **/

#include <8051.h>

#include "uart.h"

/*
 * Defaults are for a classic 12-clock 8051 running at 11.0592 MHz.
 * Override both values from the make command line if the board differs:
 *   make F_CPU=12000000UL UART_BAUD=9600
 */
#ifndef F_CPU
#define F_CPU 11059200UL
#endif

#ifndef UART_BAUD
#define UART_BAUD 9600
#endif

/* Timer 1 mode 2 reload for SMOD = 0: 256 - F_CPU / (12 * 32 * baud). */
#define UART_RELOAD \
  ((unsigned char)(256 - (F_CPU / 12UL / 32UL / UART_BAUD)))

void uart_init(void) {
  TMOD = (TMOD & 0x0F) | 0x20; /* Timer 1, 8-bit auto-reload. */
  TH1 = UART_RELOAD;
  TL1 = UART_RELOAD;
  TR1 = 1;

  SCON = 0x50; /* Mode 1 (8-bit UART), receiver enabled. */
}

int uart_getc(void) {
  while (!RI) {
  }
  RI = 0;
  return SBUF;
}

void uart_putc(char c) {
  SBUF = c;
  while (!TI) {
  }
  TI = 0;
}
