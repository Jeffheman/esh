/* Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef ESH_PORT_H
#define ESH_PORT_H

#ifdef __C51__
typedef unsigned char uint8_t;
typedef unsigned int uint16_t;
typedef unsigned long uint32_t;
typedef signed long int32_t;
typedef unsigned int uintptr_t;
typedef unsigned char bool;
#define true 1
#define false 0
#define SHELL_CODE code
#define SHELL_REENTRANT reentrant
#define SHELL_WEAK
/* C51 warns on (void)value; self-assignment is optimized away. */
#define SHELL_UNUSED(value) ((value) = (value))
#else
#include <stdint.h>
#include <stdbool.h>
#define SHELL_CODE
#define SHELL_REENTRANT
#define SHELL_WEAK __attribute__((weak))
#define SHELL_UNUSED(value) ((void)(value))
#endif

#endif
