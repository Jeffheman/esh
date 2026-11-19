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

#include "star2.h"
#include "star2_spi_slv_reg.h"
#include "uart.h"

/* star2.h 未启用 CFG0 位宏，窗口握手仍按 trunk 的 Sspi.c 实现。 */
#define SPI_SLV_BUSY 0x02

static unsigned char spi_config_read(unsigned char address) {
  unsigned char value;

  SPI_SLV_CFG0 = 0x01;
  SPI_SLV_DAT = address;
  while (SPI_SLV_CFG0 & SPI_SLV_BUSY);
  SPI_SLV_DAT = 0xFF;
  while (SPI_SLV_CFG0 & SPI_SLV_BUSY);
  value = SPI_SLV_DAT;
  SPI_SLV_CFG0 = 0x00;
  return value;
}

static void spi_config_write(unsigned char address, unsigned char value) {
  SPI_SLV_CFG0 = 0x01;
  SPI_SLV_DAT = address;
  while (SPI_SLV_CFG0 & SPI_SLV_BUSY);
  SPI_SLV_DAT = value;
  while (SPI_SLV_CFG0 & SPI_SLV_BUSY);
  SPI_SLV_CFG0 = 0x00;
}

void uart_init(void) {
  while (!(SPI_SLV_REQ & SLREQ_RST_));

  /* CFG8 同时解除 NF IO 休眠与 core→SPI 隔离，不能省略原有上电顺序。 */
  spi_config_write(REG_CFG8_WR, spi_config_read(REG_CFG8_RD) & ~CFG8_NFIO_SLP);
  spi_config_write(REG_CFG8_WR, spi_config_read(REG_CFG8_RD) & ~CFG8_CORE_PD_READY);
  spi_config_write(REG_CFG4_WR, spi_config_read(REG_CFG4_RD) | CFG4_P40_SEL);
  AIPCON = (AIPCON & ~AIP_UART_SEL_MASK) | AIP_UART_CKEN | (0x2 << AIP_UART_SEL_SHIFT);

  /* 沿用 Star 80 MHz DIE_TEST 参数；实际波特率随系统时钟变化。 */
  TCTL = 0x11;
  TPR = 0xB2;
  TCNT = 0;
}

int uart_getc(void) { return -1; }

void uart_putc(char c) {
  SBUF = (unsigned char)c;
  /* SPKS/SPTD 是 TCTL.3 的同一位，写入启动，读取判断完成。 */
  SPKS = 1;
  while (!SPTD);
  SPTD = 0;
}
