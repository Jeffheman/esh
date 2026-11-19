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

#ifndef __H_SHELL_PORT__
#define __H_SHELL_PORT__

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Compiler abstraction used by the shell core.
 *
 * GCC targets collect commands from dedicated ELF sections. SDCC cannot
 * place variables in custom sections or mark symbols weak, so it stores
 * the command descriptors in code memory (__code) under well known names.
 * The 8051 example build generates the lookup tables from those names.
 */
#if defined(__SDCC)

#define SHELL_SDCC 1
#define SHELL_CODE __code
#define SHELL_WEAK
#define SHELL_SECTION(_name)
#define SHELL_OPTIMIZE_O0

#else

#define SHELL_SDCC 0
#define SHELL_CODE
#define SHELL_WEAK __attribute__((weak))
#define SHELL_SECTION(_name) __attribute__((section(_name)))
#define SHELL_OPTIMIZE_O0 __attribute__((optimize("O0")))

#endif

#ifdef __cplusplus
}
#endif

#endif
