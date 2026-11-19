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

#ifndef __H_8051_UART__
#define __H_8051_UART__

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Configure the on-chip UART for 8N1 at UART_BAUD. Timer 1 in mode 2
 * generates the baud clock, so timer 0 remains available to the application.
 */
void uart_init(void);

/**
 * @brief Polling byte input.
 *
 * Blocks until a byte is received, then clears RI.
 */
int uart_getc(void);

/**
 * @brief Polling byte output.
 *
 * Blocks until the transmit buffer is free, then clears TI.
 */
void uart_putc(char c);

#ifdef __cplusplus
}
#endif

#endif
