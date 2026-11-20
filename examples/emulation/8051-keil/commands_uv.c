/* Copyright 2026 esh contributors. SPDX-License-Identifier: Apache-2.0 */
#if defined(ESH_UVISION_COMMANDS) && !defined(ESH_COMMAND_SCAN)
#include "build/uvision/commands.inc"
#ifndef ESH_COMMAND_TABLE_READY
#error The uVision pre-build command registration step must succeed
#endif
#endif
