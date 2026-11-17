/* Copyright 2026 The esh Authors; SPDX-License-Identifier: Apache-2.0 */

#include "shell.h"
#include "shell_config.h"
#include "rpc_board.h"

extern int (*__read_char__)(void);
extern void (*__write_char__)(char);
extern void initial_setup(void);

#define RPC_FRAME_SIZE 256

static void write_text(const char *text) {
  while (*text) __write_char__(*text++);
}

static void write_byte(uint8_t value) {
  static const char digits[] = "0123456789abcdef";
  write_text("0x");
  __write_char__(digits[value >> 4]);
  __write_char__(digits[value & 15]);
}

static int valid_id(const char *id) {
  if (strlen(id) != 16) return FALSE;
  for (int i = 0; i < 16; i++) {
    if (!((id[i] >= '0' && id[i] <= '9') ||
          (id[i] >= 'a' && id[i] <= 'f'))) return FALSE;
  }
  return TRUE;
}

static void reply_prefix(const char *id, const char *status) {
  write_text("@ESH1 ");
  write_text(id);
  __write_char__(' ');
  write_text(status);
}

static void error_reply(const char *id, const char *code) {
  reply_prefix(id, "ERR ");
  write_text(code);
  __write_char__('\n');
}

static void write_sample(const rpc_register_t *reg, uint8_t value) {
  write_text(" reg=");
  write_text(reg->name);
  write_text(" width=8 value=");
  write_byte(value);
  __write_char__('\n');
}

static void dispatch(char *line) {
  char *tokens[5];
  int count = 1;
  int malformed = FALSE;
  tokens[0] = line;

  for (char *p = line; *p; p++) {
    if (*p == ' ') {
      *p = '\0';
      if (p == line || p[1] == ' ' || p[1] == '\0') malformed = TRUE;
      if (count < 5) tokens[count++] = p + 1;
      else malformed = TRUE;
    }
  }

  if (count < 2 || strcmp(tokens[0], "@ESH1") || !valid_id(tokens[1])) return;
  const char *id = tokens[1];
  if (malformed || count < 3 || count > 4) {
    error_reply(id, "BAD_REQUEST");
    return;
  }

  if (!strcmp(tokens[2], "HELLO")) {
    if (count != 3) {
      error_reply(id, "BAD_REQUEST");
      return;
    }
    reply_prefix(id, "OK HELLO board=" RPC_BOARD_ID " fw=" SHELL_VERSION
                     " map=" RPC_MAP_ID " ops=READ,TEST\n");
  } else if (!strcmp(tokens[2], "READ")) {
    if (count != 4) {
      error_reply(id, "BAD_REQUEST");
      return;
    }
    for (unsigned int i = 0; i < RPC_REGISTER_COUNT; i++) {
      if (!strcmp(tokens[3], rpc_registers[i].name)) {
        uint8_t value = *rpc_registers[i].address;
        reply_prefix(id, "OK READ");
        write_sample(&rpc_registers[i], value);
        return;
      }
    }
    error_reply(id, "UNKNOWN_REGISTER");
  } else if (!strcmp(tokens[2], "TEST")) {
    if (count != 4) {
      error_reply(id, "BAD_REQUEST");
      return;
    }
    for (unsigned int i = 0; i < RPC_TEST_COUNT; i++) {
      if (!strcmp(tokens[3], rpc_tests[i].name)) {
        const rpc_test_t *test = &rpc_tests[i];
        const rpc_register_t *reg = &rpc_registers[test->register_index];
        uint8_t value = *reg->address;
        reply_prefix(id, "OK TEST test=");
        write_text(test->name);
        write_text((value & test->mask) == test->expected ?
                   " result=PASS" : " result=FAIL");
        write_sample(reg, value);
        return;
      }
    }
    error_reply(id, "UNKNOWN_TEST");
  } else {
    error_reply(id, "UNSUPPORTED_OP");
  }
}

void rpc_prompt(void) {
  initial_setup();
  char frame[RPC_FRAME_SIZE];
  unsigned int used = 0;
  int discard = FALSE;

  while (TRUE) {
    int value = __read_char__();
    if (value == -1) continue;
    if (value == '\n') {
      if (!discard && used) {
        frame[used] = '\0';
        dispatch(frame);
      }
      used = 0;
      discard = FALSE;
    } else if (!discard) {
      if (value < 0x20 || value > 0x7e || used >= RPC_FRAME_SIZE - 1) {
        discard = TRUE;
      } else {
        frame[used++] = (char)value;
      }
    }
  }
}
