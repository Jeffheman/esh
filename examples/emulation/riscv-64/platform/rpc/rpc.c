/* Copyright 2026 The esh Authors; SPDX-License-Identifier: Apache-2.0 */

#include "shell.h"
#include "shell_config.h"
#include "rpc_board.h"

extern void (*__write_char__)(char);

#if LINE_BUFF_SIZE < 32 || MAX_ARG_COUNT < 6
#error "The mcp command requires LINE_BUFF_SIZE >= 32 and MAX_ARG_COUNT >= 6"
#endif

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

static int parse_byte(const char *text, uint8_t *value) {
  if (strlen(text) != 2) return FALSE;
  uint8_t parsed = 0;
  for (int i = 0; i < 2; i++) {
    unsigned int digit;
    if (text[i] >= '0' && text[i] <= '9') digit = text[i] - '0';
    else if (text[i] >= 'a' && text[i] <= 'f') digit = text[i] - 'a' + 10;
    else return FALSE;
    parsed = (uint8_t)((parsed << 4) | digit);
  }
  *value = parsed;
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

static int mcp_command(int argc, char **argv) {
  if (argc < 2 || !valid_id(argv[1])) return -1;
  const char *id = argv[1];
  if (argc < 3 || argc > 6) {
    error_reply(id, "BAD_REQUEST");
    return -1;
  }

  if (!strcmp(argv[2], "h")) {
    if (argc != 3) {
      error_reply(id, "BAD_REQUEST");
      return -1;
    }
    reply_prefix(id, "OK HELLO board=" RPC_BOARD_ID " fw=" SHELL_VERSION
                     " map=" RPC_MAP_ID " ops=READ,TEST,WRITE\n");
    return 0;
  } else if (!strcmp(argv[2], "r")) {
    if (argc != 4) {
      error_reply(id, "BAD_REQUEST");
      return -1;
    }
    for (unsigned int i = 0; i < RPC_REGISTER_COUNT; i++) {
      if (!strcmp(argv[3], rpc_registers[i].alias)) {
        uint8_t value = *rpc_registers[i].address;
        reply_prefix(id, "OK READ");
        write_sample(&rpc_registers[i], value);
        return 0;
      }
    }
    error_reply(id, "UNKNOWN_REGISTER");
  } else if (!strcmp(argv[2], "t")) {
    if (argc != 4) {
      error_reply(id, "BAD_REQUEST");
      return -1;
    }
    for (unsigned int i = 0; i < RPC_TEST_COUNT; i++) {
      if (!strcmp(argv[3], rpc_tests[i].alias)) {
        const rpc_test_t *test = &rpc_tests[i];
        const rpc_register_t *reg = &rpc_registers[test->register_index];
        uint8_t value = *reg->address;
        reply_prefix(id, "OK TEST test=");
        write_text(test->name);
        write_text((value & test->mask) == test->expected ?
                   " result=PASS" : " result=FAIL");
        write_sample(reg, value);
        return 0;
      }
    }
    error_reply(id, "UNKNOWN_TEST");
  } else if (!strcmp(argv[2], "w")) {
    if (argc != 6) {
      error_reply(id, "BAD_REQUEST");
      return -1;
    }
    for (unsigned int i = 0; i < RPC_REGISTER_COUNT; i++) {
      const rpc_register_t *reg = &rpc_registers[i];
      if (strcmp(argv[3], reg->alias)) continue;
      if (reg->write_address == NULL) {
        error_reply(id, "ACCESS_DENIED");
        return -1;
      }
      uint8_t expected, requested;
      if (!parse_byte(argv[4], &expected) || !parse_byte(argv[5], &requested)) {
        error_reply(id, "BAD_REQUEST");
        return -1;
      }

      uint8_t before = *reg->address;
      uint8_t value = before;
      const char *result = "PRECONDITION_FAILED";
      if (before == expected) {
        *reg->write_address = requested;
        __asm__ volatile ("fence iorw, iorw" ::: "memory");
        value = *reg->address;
        result = value == requested ? "WRITTEN" : "VERIFY_FAILED";
      }

      reply_prefix(id, "OK WRITE reg=");
      write_text(reg->name);
      write_text(" width=8 expected=");
      write_byte(expected);
      write_text(" requested=");
      write_byte(requested);
      write_text(" before=");
      write_byte(before);
      write_text(" value=");
      write_byte(value);
      write_text(" result=");
      write_text(result);
      __write_char__('\n');
      return before == expected && value == requested ? 0 : -1;
    }
    error_reply(id, "UNKNOWN_REGISTER");
  } else {
    error_reply(id, "UNSUPPORTED_OP");
  }
  return -1;
}

ADD_CMD(mcp, "Diagnostics: mcp <16 lowercase hex ID> h|r lcr|r s|t normal|w s ee vv",
        mcp_command);
