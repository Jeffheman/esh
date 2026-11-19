/**
 * Copyright 2022 Google LLC
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

#include "regs.h"
#include "shell.h"

/*
 * Memory manipulation utilities can be skipped to reduce
 * final binary size. Skip if SHELL_NO_UTILS is defined.
 */
#ifndef SHELL_NO_UTILS
#ifdef __C51__
#define MEM_HEX "%lx"
#define MEM_DEC "%lu"
#define MEM_ARG(value) ((unsigned long)(value))
#else
#define MEM_HEX "%x"
#define MEM_DEC "%u"
#define MEM_ARG(value) ((unsigned int)(value))
#endif
/* Bound decimal arguments before a C51 16-bit int can overflow. */
static uint32_t parse_decimal(const char *str, uint32_t limit) {
#ifdef __C51__
  uint32_t value = 0;

  if (*str == '\0') {
    return limit + 1;
  }
  for (; *str != '\0'; ++str) {
    if (*str < '0' || *str > '9') {
      return limit + 1;
    }
    value = value * 10UL + (uint32_t)(*str - '0');
    if (value > limit) {
      return limit + 1;
    }
  }
  return value;
#else
  (void)limit;
  return (uint32_t)atoi(str);
#endif
}

static int parse_mem_range(const char *str, uint32_t words, uint32_t *addr) {
#ifdef __C51__
  uint32_t digit;

  *addr = 0;
  for (; *str != '\0'; ++str) {
    if (*str >= '0' && *str <= '9') {
      digit = *str - '0';
    } else if (*str >= 'a' && *str <= 'f') {
      digit = *str - 'a' + 10;
    } else if (*str >= 'A' && *str <= 'F') {
      digit = *str - 'A' + 10;
    } else {
      continue;
    }
    /* Match atoh's parsing, but reject overflow before shifting. */
    if (*addr > 0xfffUL) {
      goto invalid_range;
    }
    *addr = (*addr << 4) | digit;
  }

  /* Check the final byte too, without overflowing words * 4. */
  if (words > (0x10000UL - *addr) / 4UL) {
    goto invalid_range;
  }
  return 0;

invalid_range:
  printf("Error: Address or memory range exceeds C51 xdata\n");
  return -1;
#else
  (void)words;
  *addr = atoh(str);
  return 0;
#endif
}

int r32(int argc, char *argv[]) SHELL_REENTRANT {
  uint32_t addr;
  uint32_t value;

  if (argc < 2) {
    printf("Usage: %s <address> (in hex)\n", argv[0]);
    return -1;
  }
  if (parse_mem_range(argv[1], 1, &addr) != 0) {
    return -1;
  }

  value = reg32(addr);

  printf("0x" MEM_HEX ": 0x" MEM_HEX "\n", MEM_ARG(addr), MEM_ARG(value));
  return 0;
}

int w32(int argc, char *argv[]) SHELL_REENTRANT {
  uint32_t addr;
  uint32_t value;

  if (argc < 3) {
    printf("Usage: %s <address> (in hex) <value> (in hex)\n", argv[0]);
    return -1;
  }
  if (parse_mem_range(argv[1], 1, &addr) != 0) {
    return -1;
  }
  value = atoh(argv[2]);
  reg32(addr) = value;

  return 0;
}

int read_mem(int argc, char *argv[]) SHELL_REENTRANT {
  uint32_t addr;
  uint32_t length;
  uint32_t i;
  uint32_t value;

  if (argc < 3) {
    printf("Usage: %s <address> (in hex) <num_words> (in decimal)\n", argv[0]);
    return -1;
  }

  length = parse_decimal(argv[2], 0x4000UL);
  if (parse_mem_range(argv[1], length, &addr) != 0) {
    return -1;
  }

  for (i = 0; i < length; i++) {
    value = reg32(addr);
    printf("0x" MEM_HEX ": 0x" MEM_HEX "\n", MEM_ARG(addr), MEM_ARG(value));

    addr += 4;
  }

  return 0;
}

#ifndef SHELL_NO_BIT_UTILS
int w32_bit(int argc, char *argv[]){
  uint32_t addr;
  uint32_t bit_loc;
  uint32_t bit_val;
  uint32_t mask;
  uint32_t value;

  if (argc < 4) {
    goto usage;
  }

  bit_loc = parse_decimal(argv[2], 31);
  bit_val = parse_decimal(argv[3], 1);

  if (bit_loc > 31) {
    printf("Error: Invalid bit location argument\n");
    goto usage;
  }

  if (bit_val != 0 && bit_val != 1) {
    printf("Error: Invalid bit value argument\n");
    goto usage;
  }
  if (parse_mem_range(argv[1], 1, &addr) != 0) {
    return -1;
  }

  mask = (uint32_t)1 << bit_loc;
  value = reg32(addr);
  if (bit_val != 0) {
    value |= mask;
  } else {
    value &= ~mask;
  }
  reg32(addr) = value;

  return 0;
usage:
  printf("Usage: %s <address_in_hex(32-bits)> <bit_location_in_decimal(0 to 31)> <bit_value(0 or 1)>\n", argv[0]);
  return -1;
}

int r32_bit(int argc, char *argv[]){
  uint32_t addr;
  uint32_t bit_loc;
  uint32_t value;
  uint32_t bit_val;

  if (argc < 3) {
    goto usage;
  }

  bit_loc = parse_decimal(argv[2], 31);

  if (bit_loc > 31) {
    printf("Error: Invalid bit location argument\n");
    goto usage;
  }
  if (parse_mem_range(argv[1], 1, &addr) != 0) {
    return -1;
  }

  value = reg32(addr);
  bit_val = (value >> bit_loc) & (uint32_t)1;
  printf("Bit " MEM_DEC " @ 0x" MEM_HEX ": " MEM_DEC "\n", MEM_ARG(bit_loc),
         MEM_ARG(addr), MEM_ARG(bit_val));
  return 0;

usage:
  printf("Usage: %s <address_in_hex(32-bits)> <bit_location_in_decimal(0 to 31)\n", argv[0]);
  return -1;
}

ADD_CMD(wb, "write a bit to memory location", w32_bit);
ADD_CMD(rb, "read a bit to memory location", r32_bit);
#endif /* SHELL_NO_BIT_UTILS */

ADD_CMD(r32, "reads a 32 bit memory location", r32);
ADD_CMD(w32, "writes a 32 bit value to a memory location", w32);
ADD_CMD(read, "Reads number of bytes from memory", read_mem);
#endif /* SHELL_NO_UTILS */
