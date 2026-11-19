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

/* Star P40 调试输出；等待 SPI 域就绪，使用 TCTL=0x11、TPR=0xB2。 */
void uart_init(void);

/* 此硬件路径仅支持发送；始终返回 -1，表示没有输入。 */
int uart_getc(void);

/* 阻塞至 Star TCTL.3 报告发送完成，再清除完成标志。 */
void uart_putc(char c);

#ifdef __cplusplus
}
#endif

#endif
