/* Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef __C51__
#include <stdio.h>
#include <stdlib.h>
#define __attribute__(x)
#define printf esh_printf
#define atoi esh_atoi
#define strlen esh_strlen
#define strcmp esh_strcmp
#define strcpy esh_strcpy
#define memcpy esh_memcpy
#define memset esh_memset
#endif

#define SHELL_STATIC_COMMANDS
#define SHELL_CUSTOM_INITIAL_SETUP
#define SHELL_CUSTOM_SETUP
#define SHELL_CUSTOM_LOOP
#define SHELL_CUSTOM_PREPEND_PROMPT
#define SHELL_CUSTOM_ACTIVE_PROMPT
#ifndef ECHO_INIT_VALUE
#define ECHO_INIT_VALUE 1
#endif
#ifndef __PROMPT__
#define __PROMPT__ test
#endif
#include "shell.h"
#include "memlog.h"

#if defined(SHELL_NO_HISTORY) || defined(SHELL_NO_TAB_COMPLETE) || \
    defined(SHELL_NO_UTILS) || defined(SHELL_NO_BIT_UTILS) || defined(SHELL_PRINTF_LITE)
#error Full shell regression requires all features
#endif
#if defined(SHELL_NO_PRINTF_LL) && !defined(__C51__)
#error Host regression requires native long long formatting
#endif

#ifdef __C51__
static volatile uint32_t xdata native_registers[2];

/* Keep this before the reg32 override to exercise the production XDATA macro. */
static int native_register_access(void) {
  uint16_t address = (uint16_t)native_registers;
  native_registers[0] = 0x12345678UL;
  native_registers[1] = 0;
  reg32(address + sizeof(uint32_t)) = 0x89abcdefUL;
  return reg32(address) == 0x12345678UL && native_registers[1] == 0x89abcdefUL;
}
#endif

static uint32_t test_memory[4];
#undef reg32
#define reg32(addr) test_memory[(unsigned int)(addr) / 4]

#include "../../shell/lib/string/string.c"
#include "../../shell/lib/a2i/a2i.c"
#include "../../shell/lib/printf/printf.c"
#include "../../shell/lib/memlog/memlog.c"
#include "../../shell/lib/utils/utils.c"
#include "../../shell/shell/shell.c"

volatile unsigned int test_checks;
volatile unsigned int test_failures;
volatile unsigned char test_done;
#ifdef __C51__
unsigned char idata test_idata_upper _at_ 0x80;
#endif
static char output[2048];
static unsigned int output_count;
static const char *input;
static int calls;
static int auto_calls;
static int setup_calls;
static int idle_calls;
static int idle_remaining;
static int gate_remaining;
static int inactive_reads;
static int prompt_calls;
static int observed_argc;
static char observed_arg[LINE_BUFF_SIZE];
static uint8_t log_buffer[8];

static void check_at(int condition, unsigned int line_number) {
  ++test_checks;
  if (!condition) {
    ++test_failures;
#ifndef __C51__
    fprintf(stderr, "Failed at line %u\n", line_number);
#else
    (void)line_number;
#endif
  }
}
#define check(condition) check_at((condition), __LINE__)

static void capture(char ch) {
  if (output_count < sizeof(output) - 1) {
    output[output_count++] = ch;
    output[output_count] = '\0';
  }
}

static int feed(void) {
  if (gate_remaining) ++inactive_reads;
  if (idle_remaining) {
    --idle_remaining;
    return -1;
  }
  if (!*input) return -1;
  return (unsigned char)*input++;
}

void initial_setup(void) { platform_init(); }
void platform_init(void) {
  set_read_char(feed);
  set_write_char(capture);
}
void setup(void) { ++setup_calls; }
void loop(void) { ++idle_calls; }
void prepend_prompt(void) {
  ++prompt_calls;
  printf(">");
}
int active_prompt(void) {
  if (gate_remaining) {
    --gate_remaining;
    return 0;
  }
  return 1;
}

static void clear_output(void) {
  output_count = 0;
  output[0] = '\0';
}

static int output_contains(const char *text) {
  unsigned int start;
  unsigned int offset;
  for (start = 0; start < output_count; ++start) {
    offset = 0;
    while (text[offset] && start + offset < output_count &&
           text[offset] == output[start + offset]) ++offset;
    if (!text[offset]) return 1;
  }
  return 0;
}

static int invoke(const char *line) {
  char buffer[160];
  strcpy(buffer, line);
  return exec(buffer);
}

static void type_line(const char *line) {
  input = line;
  shell();
}

static int sample(int argc, char **argv) {
  ++calls;
  observed_argc = argc;
  observed_arg[0] = '\0';
  if (argc > 1) strcpy(observed_arg, argv[1]);
  return 7;
}

static int autorun(int argc, char **argv) {
  if (argc == 0 && argv == NULL) ++auto_calls;
  return 0;
}

static int nested(int argc, char **argv) {
  char line[] = "sample nested";
  (void)argc;
  (void)argv;
  return exec(line);
}

static int sameprefix(int argc, char **argv) {
  return sample(argc, argv);
}

ADD_CMD(sample, "Capture arguments (100%)", sample);
ADD_CMD(nested, "Execute another command", nested);
ADD_CMD(sameprefix, "Exercise multiple completion matches", sameprefix);
AUTO_CMD(autorun, "Run at startup", autorun);

#ifndef __C51__
static const cmd_t end_command = {NULL, NULL, NULL};
cmd_ref const esh_commands[] = {
  &esh_cmd_show_history, &esh_cmd_help, &esh_cmd_cmd_exec_status,
  &esh_cmd_w32_bit, &esh_cmd_r32_bit, &esh_cmd_r32, &esh_cmd_w32,
  &esh_cmd_read_mem, &esh_cmd_sample, &esh_cmd_nested, &esh_cmd_sameprefix,
  &esh_auto_autorun, &esh_auto_build_info, &end_command
};
cmd_ref const esh_auto_commands[] = {
  &esh_auto_autorun, &esh_auto_build_info, &end_command
};
#endif

void run_tests(void) {
  char line[LINE_BUFF_SIZE];
  int count;
  int old_calls;
  int i;
#ifdef __C51__
  check(test_idata_upper == 0);
  check(native_register_access());
#endif
  initial_setup();
  exec_auto_cmds();
  setup();
  check(auto_calls == 1 && setup_calls == 1);
  clear_output();
  check(invoke("help") == 0 && output_contains("Capture arguments (100%)"));
  clear_output();
  check(invoke("help -l") == 0 && output_contains("sample\n") &&
        output_contains("autorun\n") && !output_contains("Capture arguments"));
  check(get_function_addr("sample") == sample);
  check(get_function_addr("autorun") == autorun);
  check(get_function_addr("absent") == NULL);
  check(invoke("sample one two") == 7);
  check(observed_argc == 3 && strcmp(observed_arg, "one") == 0);
  check(invoke(" \t sample\targ  ") == 7 && observed_argc == 2);
  check(invoke("nested") == 7 && strcmp(observed_arg, "nested") == 0);
  clear_output();
  invoke("status");
  check(strcmp(output, "7\n") == 0);
  check(invoke("not-a-command") == -1);
  old_calls = calls;
  invoke(" \t ");
  check(calls == old_calls);
  check(invoke("sample a b c d e f g h i j k l m n o p q") == -1);
  clear_output();
  invoke("history");
  check(output_count == 0);

  type_line("sample first\n");
  type_line("sample second\n");
  type_line("\033[A\n");
  check(strcmp(observed_arg, "second") == 0);
  type_line("sample third\n");
  type_line("\033[A\033[A\n");
  check(strcmp(observed_arg, "second") == 0);
  old_calls = calls;
  type_line("\033[A\033[B\n");
  check(calls == old_calls);
  old_calls = idle_calls;
  count = prompt_calls;
  idle_remaining = 2;
  gate_remaining = 3;
  type_line("sample idle\n");
  check(idle_calls == old_calls + 2 && strcmp(observed_arg, "idle") == 0);
  check(gate_remaining == 0 && inactive_reads == 0);
  check(prompt_calls == count + 1);
  __echo = 0;
  clear_output();
  type_line("sample quiet\n");
  check(strcmp(output, ">" PROMPT "\n") == 0);
  __echo = 1;
  type_line("sample a\033[Cb\033[Dc\n");
  check(strcmp(observed_arg, "abc") == 0);
  type_line("sample carriage\r");
  check(strcmp(observed_arg, "carriage") == 0);
  type_line("sample ab\bc\n");
  check(strcmp(observed_arg, "ac") == 0);
  type_line("\b\177sample x\n");
  check(strcmp(observed_arg, "x") == 0);
  type_line("samp\t value\n");
  check(strcmp(observed_arg, "value") == 0);
  type_line("sample 1234567890123456789012345678901234567890\n");
  check(strlen(observed_arg) == LINE_BUFF_SIZE - 8);
  for (i = 0; i < 10; ++i) type_line("sample wrap\n");
  check(total_num_commands <= 2 * NUM_HISTORY_ENTRIES);
  memset(line, 0, sizeof(line));
  strcpy(line, "hel");
  count = 3;
  handle_tab(line, &count);
  check(strcmp(line, "help") == 0 && count == 4);
  strcpy(line, "sam");
  count = 3;
  handle_tab(line, &count);
  check(strcmp(line, "sam") == 0 && count == 3);
  strcpy(line, "zz");
  count = 2;
  handle_tab(line, &count);
  check(strcmp(line, "zz") == 0 && count == 2);

  clear_output();
  printf("%d %u %x", -32767, 65535U, 0xabcdU);
  check(strcmp(output, "-32767 65535 ABCD") == 0);
  clear_output();
  printf("%ld %lu", (-2147483647L - 1L), 4294967295UL);
  check(strcmp(output, "-2147483648 4294967295") == 0);
  clear_output();
  printf("%lx %s %c %%", 0x80000000UL, (const char *)"ok", (int)'Z');
  check(strcmp(output, "80000000 ok Z %") == 0);
  check(printf("%") == -1);
  clear_output();
  printf("%d %u %X", 0, 0U, 0U);
  check(strcmp(output, "0 0 0") == 0);
  clear_output();
  printf("%d %08x", (-32767 - 1), 1U);
  check(strcmp(output, "-32768 1") == 0);
  clear_output();
  printf("%S %C", (const char *)"caps", (int)'Q');
  check(strcmp(output, "caps Q") == 0);
  clear_output();
  check(printf("%q") == -1 && strcmp(output, "\nprintf-error\n") == 0);
#ifdef __C51__
  check(printf("%lld", 0L) == -1);
#else
  clear_output();
  printf("%lld %llu", (-9223372036854775807LL - 1LL), 18446744073709551615ULL);
  check(strcmp(output, "-9223372036854775808 18446744073709551615") == 0);
#endif
  check(atoh("0xFEDCBA98") == 0xfedcba98UL && atoi("1234") == 1234);
  check(invoke("w32 0 ffffffff") == 0 && test_memory[0] == 0xffffffffUL);
  check(invoke("wb 0 31 0") == 0 && test_memory[0] == 0x7fffffffUL);
  check(invoke("wb 0 31 1") == 0 && test_memory[0] == 0xffffffffUL);
  clear_output();
  check(invoke("rb 0 31") == 0);
  check(strcmp(output, "Bit 31 @ 0x0: 1\n") == 0);
  check(invoke("wb 0 32 0") == -1);
  check(invoke("wb 0 1 2") == -1);
  clear_output();
  check(invoke("r32 0") == 0);
  check(strcmp(output, "0x0: 0xFFFFFFFF\n") == 0);
  clear_output();
  check(invoke("read 0 1") == 0);
  check(strcmp(output, "0x0: 0xFFFFFFFF\n") == 0);
#ifdef __C51__
  check(invoke("w32 10000 1") == -1);
  check(invoke("r32 fffd") == -1);
  check(invoke("read 0 65536") == -1);
  check(invoke("wb 0 65536 0") == -1);
#endif
  memlog_init(log_buffer, sizeof(log_buffer), INP_OUT);
  memlog_putc('a');
  check(log_buffer[0] == 'a');
  check(memlog_getc() == -1);
  log_buffer[4] = 'b';
  check(memlog_getc() == 'b' && log_buffer[4] == 0);
  memlog_init(log_buffer, sizeof(log_buffer), OUT);
  for (i = 0; i < 9; ++i) memlog_putc((char)('a' + i));
  check(log_buffer[0] == 'i' && log_buffer[7] == 'h');
  memlog_init(log_buffer, sizeof(log_buffer), NONE);
  memlog_putc('z');
  check(log_buffer[0] == 'i' && memlog_getc() == -1);
  test_done = 1;
}

#ifdef __C51__
void test_finished(void) {
  while (1) {}
}

void main(void) {
  run_tests();
  test_finished();
}
#else
#undef printf
int main(void) {
  run_tests();
  printf("%u checks, %u failures\n", test_checks, test_failures);
  return test_failures ? 1 : 0;
}
#endif
