/**
 * Copyright 2021 Google LLC
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

#include "printf.h"
#include <stdarg.h>

extern void (*__write_char__)(char c);

#ifndef SHELL_PRINTF_LITE
#if !defined(SHELL_NO_PRINTF_LL) && !defined(__C51__)
typedef long long signed int print_signed_t;
typedef long long unsigned int print_unsigned_t;
#elif defined(__C51__)
typedef signed long print_signed_t;
typedef unsigned long print_unsigned_t;
#else
typedef signed int print_signed_t;
typedef unsigned int print_unsigned_t;
#endif

static const char SHELL_CODE hextable[] = "0123456789ABCDEF";

static void outstr(const char *str) {
  while (*str != '\0') {
    __write_char__(*str++);
  }
}

static bool printf_numbers(char fmt, va_list *args, int l_count) {
  char num[MAX_DIGITS];
  int num_len = 0;
  print_signed_t signed_value;
  print_unsigned_t value;
  unsigned int base;

  if (fmt != 'd' && fmt != 'u' && fmt != 'x' && fmt != 'X') {
    outstr("\nprintf-error\n");
    return false;
  }
  if (fmt == 'd') {
    if (l_count == 0) {
      signed_value = va_arg(*args, int);
#if !defined(SHELL_NO_PRINTF_LL) || defined(__C51__)
    } else if (l_count == 1) {
      signed_value = va_arg(*args, long int);
#ifndef __C51__
    } else if (l_count == 2) {
      signed_value = va_arg(*args, long long int);
#endif
#endif
    } else {
      return false;
    }
    value = (print_unsigned_t)signed_value;
    if (signed_value < 0) {
      __write_char__('-');
      value = (print_unsigned_t)0 - value;
    }
  } else {
    if (l_count == 0) {
      value = va_arg(*args, unsigned int);
#if !defined(SHELL_NO_PRINTF_LL) || defined(__C51__)
    } else if (l_count == 1) {
      value = va_arg(*args, unsigned long int);
#ifndef __C51__
    } else if (l_count == 2) {
      value = va_arg(*args, unsigned long long int);
#endif
#endif
    } else {
      return false;
    }
  }

  base = (fmt == 'x' || fmt == 'X') ? 16 : 10;
  do {
    num[num_len++] = hextable[value % base];
    value /= base;
  } while (value != 0);
  while (num_len > 0) {
    __write_char__(num[--num_len]);
  }
  return true;
}

int printf(const char *fmt, ...) {
  va_list args;
  int l_count;
  int result = 0;
  va_start(args, fmt);

  while (*fmt) {
    if (*fmt != '%') {
      __write_char__(*fmt++);
      continue;
    }
    ++fmt;
    while ((*fmt >= '0' && *fmt <= '9') || *fmt == '-') ++fmt;
    if (*fmt == '\0') {
      result = -1;
      break;
    }
    if (*fmt == '%') {
      __write_char__('%');
    } else if (*fmt == 'c' || *fmt == 'C') {
      __write_char__((char)va_arg(args, int));
    } else if (*fmt == 's' || *fmt == 'S') {
      outstr(va_arg(args, const char *));
    } else {
      l_count = 0;
      while (*fmt == 'l' && l_count < 2) {
        ++l_count;
        ++fmt;
      }
      if (!printf_numbers(*fmt, &args, l_count)) {
        result = -1;
        break;
      }
    }
    ++fmt;
  }
  va_end(args);
  return result;
}
#else
int printf(const char *fmt, ...) {
  while (*fmt != '\0') {
    __write_char__(*fmt++);
  }
  return 0;
}
#endif
