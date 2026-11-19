//=============================================================================
//  Star2 Chip Register Definition Header
//  Description: 基于 STAR_design_specification_v0.04 重构
//                - 按功能模块分组，标注对应 spec 寄存器编号
//                - 补充缺失的 sbit 位定义
//                - 位定义统一使用位移表达式
//                - 保持与原有 star.h 的地址完全兼容
//                - 需要IC设计人员核实寄存器
//  Original:    star.h (Version 1.0.0, 5-23-2022)
//  Author:      Jeff
//  Date:        10-18-2026
//  Full SDCC adaptation from trunk/inc/star2.h.
//=============================================================================

#ifndef STAR2_H
#define STAR2_H

//=============================================================================
//  通用外部 SFR 地址访问宏
//=============================================================================
#define XSFR_ADDR(addr) (*((volatile unsigned char __xdata *)(addr)))

//=============================================================================
//  1. SPI 从机 DMA 寄存器 (XSFR: 0xC001-0xC007)
//     Spec: Register 9-5 ~ 9-10
//=============================================================================
#define SPI_SLV_DMA_ADRH   XSFR_ADDR(0xc001)  // DMA SRAM 起始地址高字节
#define SPI_SLV_DMA_ADRL   XSFR_ADDR(0xc002)  // DMA SRAM 起始地址低字节
#define SPI_SLV_DMA_CNTH   XSFR_ADDR(0xc003)  // DMA 传输长度高字节
#define SPI_SLV_DMA_CNTL   XSFR_ADDR(0xc004)  // DMA 传输长度低字节（写触发DMA）
#define SPI_SLV_MEM_ADRH   XSFR_ADDR(0xc005)  // DMA CACHE 起始地址高字节（含CACHE_SEL）
#define SPI_SLV_MEM_ADRL   XSFR_ADDR(0xc006)  // DMA CACHE 起始地址低字节

//=============================================================================
//  2. 芯片 ID 寄存器 (XSFR: 0xC008-0xC00A)
//     Spec: Register 3-38 ~ 3-40 (Star 移至 XSFR，SFR 原址复用于其他寄存器)
//=============================================================================
#define CHIPDCN            XSFR_ADDR(0xc008)  // DCN ID（只读）
#define CHIPIDL            XSFR_ADDR(0xc009)  // 芯片 ID 低字节（只读: 0x1D）
#define CHIPIDH            XSFR_ADDR(0xc00A)  // 芯片 ID 高字节（只读: 0x00）

//=============================================================================
//  3. 电源控制寄存器 (XSFR: 0xC00B-0xC00C)
//     Spec: Register 5-6 ~ 5-7
//=============================================================================
#define PWR_CTL0           XSFR_ADDR(0xc00B)  // 带隙/1.8V/下拉 控制  (Register 5-6)
#define PWR_CTL1           XSFR_ADDR(0xc00C)  // VBIAS/VCORE/VDDCORE 压控 (Register 5-7)

// PWR_CTL0 位定义 (Register 5-6)  —— BGOE/V18S/RPDPMIO 三位在 spec 中均被删除线划掉 (p50 位表 + p51 描述)
//#define PWR_BGOE           (1 << 5)   // bit5: Bandgap output enable  [spec 删除线 p50/51]
//#define PWR_V18S_MASK      (0x3 << 3) // bit[4:3]: 1.8V output voltage (00=1.75V..11=1.95V)  [spec 删除线 p50/51]
//#define PWR_V18S_SHIFT     3
//#define PWR_RPDPMIO        (1 << 2)   // bit2: 20uA pull down for CAPLESS phase margin  [spec 位表删除线: PWR_CTRL0 p50/51, 2026-10-25]
#define PWR_RPD8MIO        (1 << 1)   // bit1: 4.3m pull down for transient response
#define PWR_RPD2MIO        (1 << 0)   // bit0: 0.9m pull down for transient response

// PWR_CTL1 位定义 (Register 5-7)
//#define PWR_VBIAS_MASK     (0x3 << 5) // bit[7:5]: BGBUF output trimming  [spec 删除线 p51]
//#define PWR_VBIAS_SHIFT    5
#define PWR_VCORES_MASK    (0x3 << 3) // bit[4:3]: VDDCORE voltage (00=1.20V..11=1.35V)
#define PWR_VCORES_SHIFT   3
#define PWR_RPD20U         (1 << 2)   // bit2: 20uA pull down for CAPLESS mode (0=enable)
                                      //       (2026-10-24 按 spec PDF p51 坐标 x=356.2 修正，原为 bit3，差异台账 #11)
#define PWR_RPD5M2         (1 << 1)   // bit1: 5m pull down 2
#define PWR_RPD5M1         (1 << 0)   // bit0: 5m pull down 1

//=============================================================================
//  4. GPIO 控制寄存器 (XSFR: 0xC010-0xC01F)
//     Spec: Register 6-2 ~ 6-21
//=============================================================================
// -- 上拉控制 --
#define P0PLP              XSFR_ADDR(0xc010)  // Port0 30K 上拉 (Register 6-2)
//#define P1PLP           XSFR_ADDR(0xc011)  // Port1 30K 上拉 (Register 6-3, Star 未使用)
#define P2PLP              XSFR_ADDR(0xc012)  // Port2 30K 上拉 (Register 6-4)
#define P4PLP              XSFR_ADDR(0xc013)  // Port4 30K 上拉 (Register 6-5)
//#define P4PLP1          XSFR_ADDR(0xc014)  // Port4 10K 上拉选择 (Register 6-6, Star 未使用)

// -- 驱动能力 --
#define P0DSHB             XSFR_ADDR(0xc015)  // Port0 驱动能力高字节 (Register 6-15)
#define P0DSLB             XSFR_ADDR(0xc016)  // Port0 驱动能力低字节 (Register 6-16)
//#define P1DSHB          XSFR_ADDR(0xc017)  // Port1 驱动能力高字节 (Register 6-17)
//#define P1DSLB          XSFR_ADDR(0xc018)  // Port1 驱动能力低字节 (Register 6-18)
#define P2DSHB             XSFR_ADDR(0xc019)  // Port2 驱动能力高字节 (Register 6-??)
#define P2DSLB             XSFR_ADDR(0xc01a)  // Port2 驱动能力低字节 (Register 6-??)

// -- 噪声限制 --
#define P0HNL              XSFR_ADDR(0xc01b)  // Port0 噪声限制选择 (Register 6-19)
//#define P1HNL           XSFR_ADDR(0xc01c)  // Port1 噪声限制选择 (Register 6-20)
#define P2HNL              XSFR_ADDR(0xc01d)  // Port2 噪声限制选择 (Register 6-??)
#define P4HNL              XSFR_ADDR(0xc01e)  // Port4 噪声限制选择 (Register 6-21)
#define P4HD               XSFR_ADDR(0xc01f)  // Port4 高驱动能力控制 (Register 6-14)

//=============================================================================
//  5. UART 寄存器 (XSFR: 0xC027-0xC02B)
//     Spec: Register 15-1 ~ 15-5
//=============================================================================
#define UARTSTA            XSFR_ADDR(0xc027)  // UART 状态         (Register 15-2)
#define UARTCON            XSFR_ADDR(0xc028)  // UART 控制         (Register 15-1)
#define UARTBAUD           XSFR_ADDR(0xc029)  // 波特率 低字节     (Register 15-3)
#define UARTBAUDH          XSFR_ADDR(0xc02a)  // 波特率 高字节     (Register 15-4)
#define UARTDATA           XSFR_ADDR(0xc02b)  // UART 数据         (Register 15-5)

//=============================================================================
//  6. MBIST 寄存器 (XSFR: 0xC02C-0xC02E)
//     Spec: Register 14-1 ~ 14-2
//=============================================================================
#define MBISTCON0          XSFR_ADDR(0xc02c)  // SRAM MBIST 控制      (Register 14-1)
#define MBISTCON1          XSFR_ADDR(0xc02d)  // SRAM MBIST 控制1     (Register 14-??)
#define MBISTTCNT          XSFR_ADDR(0xc02e)  // MBIST 测试计数        (Register 14-??)

//=============================================================================
//  7. GPIO 调度/选择控制寄存器 (XSFR: 0xC030-0xC039)
//     Spec: Register 6-1 P48_CTL,  Star 扩展
//=============================================================================
// -- Port0 调度控制 --
#define P0_SCHD_EN         XSFR_ADDR(0xc030)  // Port0 调度使能
#define P0_SC_EN           XSFR_ADDR(0xc031)  // Port0 扫描使能
#define P0_SC_SEL          XSFR_ADDR(0xc032)  // Port0 扫描选择

// -- Port1 调度控制 --
#define P1_SCHD_EN         XSFR_ADDR(0xc033)  // Port1 调度使能
#define P1_SC_EN           XSFR_ADDR(0xc034)  // Port1 扫描使能
#define P1_SC_SEL          XSFR_ADDR(0xc035)  // Port1 扫描选择

// -- Port2 调度控制 --
#define P2_SCHD_EN         XSFR_ADDR(0xc036)  // Port2 调度使能
#define P2_SC_EN           XSFR_ADDR(0xc037)  // Port2 扫描使能
#define P2_SC_SEL          XSFR_ADDR(0xc038)  // Port2 扫描选择

// -- P48/P4 控制 --
#define P48_CTL            XSFR_ADDR(0xc039)  // P48/P40 方向/上拉/下拉/驱动 (Register 6-1)
#define WDTCON             XSFR_ADDR(0xc03a)  // 看门狗控制 (Register 17-1)

//=============================================================================
//  8. SPI 从机窗口寄存器 (IRTCC) 命令码与功能位定义  ->  见 star2_spi_slv_reg.h
//
//     2026-10-24 拆分: 命令码 0x50-0x7F 与 CFG0~CFG16 / STATUS / PENDING /
//     FLASH_MID / FLASH_DID / ADR / SPI_ADR0~3 / UNKNOWN_CMD 位定义已全部移出
//     到独立头文件 inc/star2_spi_slv_reg.h。
//
//     注意 本文件不再 #include 它 —— 需要用到的模块请显式包含:
//           #include "star2_spi_slv_reg.h"
//
//     注意 包含前请注意: 老头文件 star.h 已定义 47 个同名命令码宏
//       (REG_CFG0_WR / REG_CFG9_RD / REG_PND_WR ...), 二者取值逐一核对一致,
//       GCC 下重复定义不告警, 但 Keil C51 未实测。经 com.h -> star.h 的
//       模块若再包含本头, 会触发这 47 处宏重定义, 建议先清理 star.h。
//=============================================================================

//=============================================================================
//  9. SFR 寄存器 (直接寻址 0x80-0xFF)
//     均以 sfr 声明，可按字节或位寻址（地址被 8 整除者可位寻址）
//=============================================================================

//=============================================================================
//  9.1  CPU & DPTR 寄存器 (0x80-0x85)
//        Spec: Register 3-1 ~ 3-6
//=============================================================================
__sfr __at(0x80) DPCTL;   // 数据指针控制      (Register 3-1)
__sfr __at(0x81) SP;   // 栈指针 (默认80h)  (Register 3-2)
__sfr __at(0x82) DP0L;   // DPTR0 低字节      (Register 3-3)
__sfr __at(0x83) DP0H;   // DPTR0 高字节      (Register 3-4)
// SDCC __sfr16 requires a high/low SFR address pair, not just the low-byte address.
__sfr16 __at(0x8382) DPTR0;   // DPTR0 16位访问
__sfr __at(0x84) DP1L;   // DPTR1 低字节      (Register 3-5)
__sfr __at(0x85) DP1H;   // DPTR1 高字节      (Register 3-6)
__sfr16 __at(0x8584) DPTR1;   // DPTR1 16位访问

//=============================================================================
//  9.2  BCH ECC 编解码器 (0x86-0x8F)
//        Spec: Register 10-1 ~ 10-6 (BCH Codec)
//=============================================================================
__sfr __at(0x86) BXADR0;   // BCH DMA XDATA 地址低字节
__sfr __at(0x87) BXADR1;   // BCH DMA XDATA 地址高字节
__sfr16 __at(0x8786) BXADR;   // BCH DMA XDATA 地址 16bit
__sfr __at(0x88) BCTL0;   // BCH 控制 0
__sfr __at(0x89) BCTL1;   // BCH 控制 1
__sfr __at(0x8A) BDATA0;   // BCH 数据 0
__sfr __at(0x8B) BDATA1;   // BCH 数据 1
__sfr __at(0x8C) BLGTH0;   // BCH DMA 长度低字节
__sfr __at(0x8D) BLGTH1;   // BCH DMA 长度高字节
__sfr __at(0x8E) AIPCON;   // AIP 控制 (Register 3-7: NAND IO 电压/UART/NAND8bit选择)
__sfr __at(0x8F) BERRCNT;   // BCH 错误计数 (Spec: 此位 Star 新增, 取代 SPI_CNT 位)

// AIPCON 位定义 (Register 3-7)
#define AIP_NFIO_CMT        (1 << 7)   // bit7: NAND IO 电压 (0=硬件自动, 1=NFIO_SEL选择)
#define AIP_NFIO_SEL        (1 << 6)   // bit6: NAND IO 电压选择 (0=1.8V CAPLESS, 1=3.3V)
#define AIP_UART_CKEN       (1 << 5)   // bit5: UART 时钟使能 (1=使能)
#define AIP_NF8B_SEL_MASK   (0x3 << 3) // bit[4:3]: 8bit NAND Flash 引脚映射选择
#define AIP_NF8B_SEL_SHIFT  3
#define AIP_UART_SEL_MASK   (0x3 << 1) // bit[2:1]: UART TX 引脚选择 (00=P14, 10=P40, x1=SPI_HOLD)
#define AIP_UART_SEL_SHIFT  1
#define AIP_BORBEN          (1 << 0)   // bit0: BORB 使能 (0=使能BOR复位, 1=禁止BOR)

//=============================================================================
//  9.3  NAND Flash 控制器 (0x90-0x9E)
//        Spec: Register 8-1 ~ 8-14
//=============================================================================
__sfr __at(0x90) SFLAG;   // SDC 状态标志 (Register 11-6)
__sfr __at(0x91) NCEE;   // NAND Flash CE 使能 (Register 8-5)
__sfr __at(0x92) NMCTL;   // NAND Flash 模式控制 (Register 8-6)
__sfr __at(0x93) NTCTL0;   // NAND Flash 时序控制 0 (Register 8-7)
__sfr __at(0x94) NPCTL;   // NAND Flash 协议控制 (Register 8-8)
__sfr __at(0x95) NXADR0;   // NAND DMA 起始地址低字节 (Register 8-9)
__sfr __at(0x96) NXADR1;   // NAND DMA 起始地址高字节 (Register 8-10)
__sfr16 __at(0x9695) NXADR;   // NAND DMA 起始地址 16bit
__sfr __at(0x97) NACMD1;   // NAND After-Data CMD1 (Register 8-11)
__sfr __at(0x98) NTCTL1;   // NAND Flash 时序控制 1 (Register 8-12)
__sfr __at(0x99) NPGSZ0;   // NAND Flash 页大小低字节 (Register 8-13)
__sfr __at(0x9A) NPGSZ1;   // NAND Flash 页大小高字节 (Register 8-14)
__sfr16 __at(0x9A99) NPGSZ;   // NAND Flash 页大小 16bit
// 注：NFIFO0~NFIFO7共享 4 个物理 SFR (0x9B-0x9E)，高4字节复用低4字节
__sfr __at(0x9B) NFIFO0;   // NAND FIFO 0 (Register 8-1)
__sfr __at(0x9C) NFIFO1;   // NAND FIFO 1 (Register 8-2)
__sfr __at(0x9D) NFIFO2;   // NAND FIFO 2 (Register 8-3)
__sfr __at(0x9E) NFIFO3;   // NAND FIFO 3 (Register 8-4)
__sfr __at(0x9B) NFIFO4;   // NAND FIFO 4（复用 NFIFO0）
__sfr __at(0x9C) NFIFO5;   // NAND FIFO 5（复用 NFIFO1）
__sfr __at(0x9D) NFIFO6;   // NAND FIFO 6（复用 NFIFO2）
__sfr __at(0x9E) NFIFO7;   // NAND FIFO 7（复用 NFIFO3）

// NCEE 位定义 (Register 8-5)
#define NCE_NF_HV           (1 << 7)   // bit7: NAND IO电压 (1=3.3V, 0=1.8V)
#define NCE_VDDCORE_EN      (1 << 6)   // bit6: VDDCORE不关断
#define NCE_NFVDD_EN        (1 << 5)   // bit5: NFVDD不关断
#define NCE_NWE_OUT_SEL     (1 << 4)   // bit4: NWE输出选择
#define NCE_NCE1E           (1 << 1)   // bit1: NCE1 使能
#define NCE_NCE0E           (1 << 0)   // bit0: NCE0 使能

// NMCTL 位定义 (Register 8-6)
#define NMC_LATSEL1         (1 << 7)   // bit7: RE 数据采样选择[1]
#define NMC_LATSEL0         (1 << 6)   // bit6: RE 数据采样选择[0]
#define NMC_NRBS1           (1 << 5)   // bit5: NAND RB 选择 (0x=NRB0, 1x=不关心)
#define NMC_NCEACT          (1 << 3)   // bit3: CE active 使能
#define NMC_MODE            (1 << 0)   // bit0: NAND x8/x16 模式 (0=x8,1=x16)

// NTCTL0 位定义 (Register 8-7, 0x93, 默认值 0xFF)
#define NTC_NWEHW_MASK      (0x3 << 6) // bit[7:6]: NWE 高电平周期 (00=1..11=4 cycles)
#define NTC_NWEHW_SHIFT     6
#define NTC_NWELW_MASK      (0x3 << 4) // bit[5:4]: NWE 低电平周期 (00=1..11=4 cycles)
#define NTC_NWELW_SHIFT     4
#define NTC_NREHW_MASK      (0x3 << 2) // bit[3:2]: NRE 高电平周期 (00=1..11=4 cycles)
#define NTC_NREHW_SHIFT     2
#define NTC_NRELW_MASK      (0x3 << 0) // bit[1:0]: NRE 低电平周期 (00=1..11=4 cycles)
#define NTC_NRELW_SHIFT     0

// NPCTL 位定义 (Register 8-8)
#define NPC_NACMD1E         (1 << 7)   // bit7: After-Data-Command 1 使能
#define NPC_NADRE_MASK      (0x7 << 4) // bit[6:4]: 地址字节数 (0=无地址..7=7字节)
#define NPC_NADRE_SHIFT     4
#define NPC_NADRE(n)        ((n) << NPC_NADRE_SHIFT)  // 例: NPC_NADRE(3)=3字节地址
#define NPC_NWRE            (1 << 3)   // bit3: NAND 写数据使能
#define NPC_NRDE            (1 << 2)   // bit2: NAND 读数据使能
#define NPC_NBCMD1E         (1 << 1)   // bit1: Before-Data-CMD1 使能
#define NPC_NCMD0E          (1 << 0)   // bit0: Command 0 使能

//=============================================================================
//  9.4  SPI Slave 寄存器 (0x9F, 0xA2, 0xBB-0xBD)
//        Spec: Register 9-1 ~ 9-4, 9-11
//=============================================================================
__sfr __at(0x9F) SPI_SLV_CFG0;   // SPI Slave 控制 0 (Register 9-1: DMA/通信控制)
__sfr __at(0xA2) SPI_SLV_REQ;   // SPI Slave 请求状态 (Register 9-11, Star: 原P1HNL位移至XSFR)
__sfr __at(0xBB) SPI_SLV_CFG1;   // SPI Slave 控制 1 (Register 9-2: 中断使能)
__sfr __at(0xBC) SPI_SLV_CFG2;   // SPI Slave 控制 2 (Register 9-3: P44/P45/波特率/时钟)
__sfr __at(0xBD) SPI_SLV_DAT;   // SPI Slave 通信数据 (Register 9-4: SPI_CTL_DAT)

// SPI_SLV_CFG0 位定义 (Register 9-1) —— [spec p85 整个位表删除线, 标题标注 "no use? mark by curry", 2026-10-25]
//   注意 但固件 Sspi.c 大量使用 SPI_SLV_CFG0 做 DMA 控制, 此处仅按 spec 注释留痕, 实际以固件为准
//#define SCDMA_DMA_PND       (1 << 7)   // bit7: DMA传输完成标志 (RO, 1=完成)
//#define SCDMA_CLR_PND       (1 << 6)   // bit6: 清除DMA标志 (WO, 写1清除)
//#define SCDMA_DMA_IE        (1 << 5)   // bit5: DMA中断使能 (#12中断)
//#define SCDMA_DMA_EN        (1 << 4)   // bit4: DMA使能
//#define SCDMA_DMA_INOUT     (1 << 3)   // bit3: DMA方向 (0=SPI->SRAM, 1=SRAM->SPI)
//#define SCDMA_TST_EN        (1 << 2)   // bit2: CP测试使能
//#define SCDMA_DONE          (1 << 1)   // bit1: 通信完成标志 (1=进行中, 0=完成)
//#define SCDMA_CS            (1 << 0)   // bit0: 串行通信使能

// SPI_SLV_CFG1 位定义 (Register 9-2: SPI 中断使能)
#define SCFG1_P_OFF_IE      (1 << 7)   // bit7: 断电请求中断使能
#define SCFG1_UNKWN_IE      (1 << 6)   // bit6: 未知命令中断使能
#define SCFG1_PRO_IE        (1 << 5)   // bit5: 保护写请求中断使能
#define SCFG1_FEA_IE        (1 << 4)   // bit4: 特性写请求中断使能
#define SCFG1_RESET_IE      (1 << 3)   // bit3: 复位请求中断使能
#define SCFG1_BE_IE         (1 << 2)   // bit2: 块擦除请求中断使能
#define SCFG1_PP_IE         (1 << 1)   // bit1: 页编程请求中断使能
#define SCFG1_PR_IE         (1 << 0)   // bit0: 页读取请求中断使能

// SPI_SLV_CFG2 位定义 (Register 9-3)
#define SCFG2_P44_DIN        (1 << 7)   // bit7: P44输出数据 (SPI_HOLD, BYPASS=1时有效)
#define SCFG2_P45_DIN        (1 << 6)   // bit6: P45输出数据 (SPI_WP, BYPASS=1时有效)
#define SCFG2_P44_OE         (1 << 5)   // bit5: P44输出使能
#define SCFG2_P45_OE         (1 << 4)   // bit4: P45输出使能
#define SCFG2_BAUD_MASK      (0x3 << 2) // bit[3:2]: 核↔gd_spi通信时钟分频 (00=/4, 01=/8, 1x=/16)
#define SCFG2_BAUD_SHIFT     2
#define SCFG2_BAUD(n)        ((n) << SCFG2_BAUD_SHIFT)
#define SCFG2_SLV_CLK_DIV    (1 << 1)   // bit1: Cache DMA时钟分频 (0=/1, 1=/2, 不可逆切换)
#define SCFG2_SLV_CK_EN      (1 << 0)   // bit0: SPI Slave模块时钟门控 (0=使能, 1=门控)

// SPI_SLV_REQ 位定义 (Register 9-11, 源码 stddef.h MSG_* 常量与 bit 位一一对应)
#define SLREQ_RST_          (1 << 7)   // bit7: SPI Slave 上电复位完成 (RO, 1=完成, 不触发中断需轮询)
#define SLREQ_UNKNOWN       (1 << 6)   // bit6: 未知命令请求 (RO, 主机发无法处理的CMD时置位)
#define SLREQ_PRO           (1 << 5)   // bit5: 保护修改请求 (RO, SET FEATURE 修改PROTECT时置位)
#define SLREQ_FEA           (1 << 4)   // bit4: 特性修改请求 (RO, SET FEATURE 修改FEATURE时置位)
#define SLREQ_RESET         (1 << 3)   // bit3: 复位请求 (RO, 主机发RESET命令时置位)
#define SLREQ_BLOCK_ERASE   (1 << 2)   // bit2: 块擦除请求 (RO, 主机发BLOCK_ERASE命令时置位)
#define SLREQ_PAGE_PROG     (1 << 1)   // bit1: 页编程请求 (RO, 主机发PROGRAM EXECUTE时置位)
#define SLREQ_PAGE_READ     (1 << 0)   // bit0: 页读取请求 (RO, 主机发PAGE_READ命令时置位)

//=============================================================================
//  9.5  电源 & 时钟控制 (0xA0-0xA1, 0xA7-0xAA 部分)
//        Spec: Register 5-1 ~ 5-5
//=============================================================================
__sfr __at(0xA0) PCTL;   // 电源控制  (Register 5-1: SRAM_CE/SDCKE/BCKE/NCKE/INTBK/PD/IDLE)
__sfr __at(0xA1) CCTL;   // 时钟控制  (Register 5-2)
__sfr __at(0xB4) RCCTL;   // RC 时钟控制 0    (Register 5-3)
__sfr __at(0xFF) RCCTL1;   // RC 时钟控制 1    (Register 5-4)

__sfr __at(0xA7) IPE;   // 中断优先级使能1 (Register 3-8)
__sfr __at(0xA8) IE;   // 中断使能       (Register 3-9)
__sfr __at(0xA9) IP;   // 中断优先级     (Register 3-11)
__sfr __at(0xAA) CMPCTL;   // 比较控制 0 (Register 12-1)
__sfr __at(0xAB) CMPFIFO;   // 比较 FIFO  (Register 12-6)
__sfr __at(0xAC) CMPDMAMT;   // 比较 DMA 数量 (Register 12-4)
__sfr __at(0xAD) CMPSTADR;   // 比较起始地址  (Register 12-3)
__sfr __at(0xAE) CMPCTL1;   // 比较控制 1 (Register 12-2)
__sfr __at(0xAF) SPIDMACNT;   // SPI DMA 计数 (Register 13-5)

// CCTL 位定义 (Register 5-2, 默认值 0x03)
#define CCTL_SDRST_         (1 << 7)   // bit7: SD 控制器复位 (0=复位, 1=释放)
#define CCTL_NRST_          (1 << 6)   // bit6: NAND Flash 控制器复位 (0=复位, 1=释放)
#define CCTL_BRST_          (1 << 5)   // bit5: BCH ECC 复位 (0=复位, 1=释放)
#define CCTL_MROM_CE        (1 << 4)   // bit4: MROM 片选 (0=使能, 1=关闭)
#define CCTL_TSCKIE         (1 << 3)   // bit3: 测试时钟输入选择 (0=RC时钟, 1=TEST时钟)
#define CCTL_HPEN           (1 << 2)   // bit2: RC 高频模式 (0=10MHz, 1=70MHz)
#define CCTL_TCKE           (1 << 1)   // bit1: Timer 时钟使能 (默认1=使能)
#define CCTL_SCKDIVE        (1 << 0)   // bit0: RC 时钟2分频 (0=直通, 1=÷2, 默认1)

// RCCTL 位定义 (Register 5-3, 0xB4)
#define RCCTL_RCOE          (1 << 7)    // bit7: RC 输出使能 (0=不输出, 1=输出到P10)
#define RCCTL_RCDIS         (1 << 6)    // bit6: RC disable/reset 模式延迟
#define RCCTL_RCES          (1 << 5)    // bit5: RC sleep使能 (0=sleep时使能, 1=sleep时禁止)
//#define RCCTL_RCTRIM_MASK   (0x1F << 0) // bit[4:0]: RC 频率微调 (5'h00=~80M .. 5'h1F=~114M)  [spec 位表删除线: RCCTL p48 位名 + p49 描述, 2026-10-25]
//#define RCCTL_RCTRIM_SHIFT  0

// RCCTL1 位定义 (Register 5-4, 0xFF, 默认值 0x01)
#define RCCTL1_RC_O_SEL     (1 << 2)   // bit2: RC输出选择 (0=系统高速RC到P10, 1=RC2M VDDSPI域)
//#define RCCTL1_RC_TST_EN    (1 << 1)   // bit1: RC测试模式 (0=禁止, 1=输出RC测试值到P45)  [spec 位表删除线: RCCTL1 p49 位名+描述, 2026-10-25]
#define RCCTL1_RST_MODE     (1 << 0)   // bit0: RC快速复位模式 (0=使能~30ns恢复PD, 1=禁止, sleep~30uA)

// SPIDMACNT 位定义 (Register 13-5, 全8-bit WO计数器, 公式: Nbyte = (SPIDMACNT+1)*4)
#define SDCNT_MASK          0xFF       // bit[7:0]: 传输计数 (写此寄存器即触发DMA)

//=============================================================================
//  9.6  Timer & Serial Port (0xB0-0xB3)
//        Spec: Register 7-1 ~ 7-4
//=============================================================================
__sfr __at(0xB0) TCTL;   // 定时器控制   (Register 7-1)
__sfr __at(0xB1) TCNT;   // 定时器计数值 (Register 7-2)
__sfr __at(0xB2) TPR;   // 定时器周期   (Register 7-3)
__sfr __at(0xB3) SBUF;   // 串口 RX/TX 缓冲 (Register 7-4)

//=============================================================================
//  9.7  中断 & 唤醒控制 (0x8E, 0xA7-0xA9, 0xBE-0xBF)
//        Spec: Register 3-7 ~ 3-13
//=============================================================================
__sfr __at(0xB5) EXINTR;   // 外部中断/唤醒控制      (Register 5-5)
__sfr __at(0xB6) SPIDMASPH;   // SPI DMA 源地址高字节
__sfr __at(0xB7) R8;   // 通用寄存器 R8          (Register 3-15)
__sfr __at(0xB9) WKFLAG;   // 唤醒标志 (Smart Idle)  (Register 3-13)
__sfr __at(0xBA) EXINTR1;   // 外部中断控制 1 (Star新增, Register 5-5续)
__sfr __at(0xBE) IE1;   // 中断使能 1     (Register 3-10)
__sfr __at(0xBF) IP1;   // 中断优先级 1   (Register 3-12)

// EXINTR 位定义 (Register 5-5)
#define EXI_SD_MODE         (1 << 7)   // bit7: SD模式指示 (RO, 0=选SPI APP, 1=BYPASS=3.3V选SD APP)
#define EXI_STDLY_SEL_MASK  (0x3 << 5) // bit[6:5]: 唤醒后时钟/复位延迟 (bit6=RO, bit5=R/W)
#define EXI_STDLY_SEL_SHIFT 5          //     1=~40us, 0=~10us @50MHz, bit6由PWR_CTRL1[5]决定
#define EXI_STDLY_SEL(n)    ((n) << EXI_STDLY_SEL_SHIFT)
#define EXI_WKPS1           (1 << 4)   // bit4: 掉电请求唤醒使能 (1=无论WKPS值均允许掉电请求唤醒)
//#define EXI_WK_PND          (1 << 3)   // bit3: 唤醒待处理 (RO, 1=唤醒事件发生, 写0清除, 写1无效)  [spec 位表删除线: EXINTR p49 位名 + p50 描述, 2026-10-25]
#define EXI_WKEN            (1 << 2)   // bit2: 唤醒使能 (0=禁止, 1=使能)
#define EXI_WKEDG           (1 << 1)   // bit1: 唤醒边沿选择 (0=上升沿, 1=下降沿)
//#define EXI_WKPS            (1 << 0)   // bit0: 唤醒引脚选择[0] (已废弃, 合并到CFG13[11])  [spec 位表删除线: p49 位名 + p50 描述 "deleted and merged with MST_LDO_WK_SEL of CFG13[11]", 2026-10-25]

// EXINTR1 位定义 (Register 5-5续, Star新增)
#define EXI1_NF_DET         (1 << 7)   // bit7: NAND IO电压检测 (RO, 0=1.8V, 1=3.3V)
#define EXI1_POWER_OFF_REQ  (1 << 6)   // bit6: 掉电请求 (RO, SPI CS长时间高触发, SPI_CS低自动清除)
// bit[5:0]: spec 仅标注 R/W 但未文档化具体功能

// IE1 位定义 (Register 3-10)
#define IE1_WDTIE           (1 << 4)   // bit4: 看门狗中断使能
#define IE1_UARTINTEN       (1 << 3)   // bit3: UART 中断使能
#define IE1_ONFINTEN        (1 << 2)   // bit2: OneNAND Flash 中断使能 (Star 已移除ONF)
#define IE1_GD_DMA_INTEN    (1 << 1)   // bit1: GD SPI DMA 中断使能
#define IE1_GD_INTEN        (1 << 0)   // bit0: GD SPI Slave 中断使能

// IP1 位定义 (Register 3-12)
#define IP1_WDTINT          (1 << 4)   // bit4: 看门狗中断优先级
#define IP1_UARTINT         (1 << 3)   // bit3: UART 中断优先级
#define IP1_ONFINT          (1 << 2)   // bit2: OneNAND Flash 中断优先级
#define IP1_GD_DMA_INT      (1 << 1)   // bit1: GD SPI DMA 中断优先级
#define IP1_GD_INT          (1 << 0)   // bit0: GD SPI Slave 中断优先级

// IPE 位定义 (Register 3-8)
#define IPE_SPIIP           (1 << 7)   // bit7: SPI 中断优先级控制
#define IPE_SPIP            (1 << 6)   // bit6: 串口中断优先级控制
#define IPE_TMRIP           (1 << 5)   // bit5: 定时器中断优先级控制
#define IPE_EXIP            (1 << 4)   // bit4: 端口唤醒中断优先级控制
#define IPE_SPIIE           (1 << 3)   // bit3: SPI 中断使能
#define IPE_SPIE            (1 << 2)   // bit2: 串口中断使能
#define IPE_TMRIE           (1 << 1)   // bit1: 定时器中断使能
#define IPE_EXIE            (1 << 0)   // bit0: 端口唤醒中断使能

//=============================================================================
//  9.8  SPI 主模式 (0xA3-0xA5, 0xAF, 0xB6, 0xB8, 0xCC-0xCD)
//        Spec: Register 13-1 ~ 13-5
//=============================================================================
__sfr __at(0xB8) SPICON;   // SPI 主模式控制 (Register 13-1)
__sfr __at(0xA3) SPICON1;   // SPI 控制 1  (Register 13-2)
__sfr __at(0xA4) SPIBUF;   // SPI 数据缓冲 (Register 13-4)
__sfr __at(0xA5) SPIBAUD;   // SPI 波特率   (Register 13-3)
__sfr __at(0xCC) SPIDMASPL;   // SPI DMA 源地址低字节 (Register ??)

// SPICON 位定义 (Register 13-1, 地址 0xB8)
#define SPIC_SPIPND         (1 << 7)   // bit7: SPI 传输完成标志 (RO, 1=完成, 写SPIBUF自动清除)
#define SPIC_HSMODE         (1 << 6)   // bit6: 高速模式 (1=使能, baudrate=0时不计分频)
#define SPIC_SPIRT          (1 << 5)   // bit5: TX/RX选择 (2-wire或DMA模式, 0=TX, 1=RX)
#define SPIC_SPIWS          (1 << 4)   // bit4: 2线/3线模式 (0=3线全双工, 1=2线半双工)
// bit3: reserved
#define SPIC_SPIEDGE        (1 << 2)   // bit2: 采样边沿 (SPIIDST=0:0=下降沿/1=上升沿; SPIIDST=1取反)
#define SPIC_SPIIDST        (1 << 1)   // bit1: SPI时钟空闲电平 (0=低, 1=高)
#define SPIC_SPIEN          (1 << 0)   // bit0: SPI 模块使能 (0=禁止, 1=使能)

// SPICON1 位定义 (Register 13-2, 地址 0xA3)
#define SPIC1_FASTX         (1 << 4)   // bit4: 普通模式快速发送使能 (写1字节即触发发送, 不用此功能须=0)
#define SPIC1_ODDDIV        (1 << 3)   // bit3: 奇分频使能 (不用此功能须=0)
#define SPIC1_SAMPSEL       (1 << 2)   // bit2: 接收采样边沿 (0=第一边沿, 1=第二边沿, HS模式不支持)
#define SPIC1_DBWIDTH_MASK  (0x3 << 0) // bit[1:0]: 数据总线宽度 (00=1bit, 01=2bit, 1x=4bit)
#define SPIC1_DBWIDTH_SHIFT 0
#define SPIC1_DBWIDTH(n)    ((n) << SPIC1_DBWIDTH_SHIFT)

//=============================================================================
//  9.9  SD 控制器 (0xCD-0xEC, 0x90, 0xED-0xEF)
//        Spec: Register 11-1 ~ 11-30
//=============================================================================
__sfr __at(0xCD) SHCTL;   // SD 主机控制          (Register 11-7)
__sfr __at(0xCE) SR1CTL;   // SD 响应控制 1        (Register 11-8)
__sfr __at(0xCF) SSTA;   // SD 卡状态            (Register 11-9)
__sfr __at(0xD1) SDODLY;   // SD 数据 TX 延迟       (Register 11-10)
__sfr __at(0xD2) SRCA0;   // SD RCA 低字节         (Register 11-11)
__sfr __at(0xD3) SRCA1;   // SD RCA 高字节         (Register 11-12)
__sfr __at(0xD4) SDXADR0;   // SD 数据 DMA 地址低   (Register 11-14)
__sfr __at(0xD5) SDXADR1;   // SD 数据 DMA 地址高   (Register 11-15)
__sfr __at(0xD6) SRXADR0;   // SD 命令 DMA 地址低   (Register 11-16)
__sfr __at(0xD7) SRXADR1;   // SD 命令 DMA 地址高   (Register 11-17)
__sfr __at(0xDC) SDICTL;   // SD 数据 RX 配置      (Register 11-4)
__sfr __at(0xDD) SDOTK;   // SD 数据 TX 令牌(SPI模式) (Register 11-13)
__sfr __at(0xDE) SRDL0;   // SD 响应 DMA 长度低   (Register 11-18)
__sfr __at(0xDF) SRDL1;   // SD 响应 DMA 长度高   (Register 11-19)
__sfr __at(0xE1) SDDL0;   // SD 数据 DMA 长度低   (Register 11-20)
__sfr __at(0xE2) SDDL1;   // SD 数据 DMA 长度高   (Register 11-21)
__sfr __at(0xE3) SCCTL;   // SD 命令控制          (Register 11-2)
__sfr __at(0xE4) SRDCTL;   // SD 响应 DMA 控制     (Register 11-22)
__sfr __at(0xE5) SDOCTL;   // SD 数据 TX 配置      (Register 11-5)
__sfr __at(0xE6) SINDX;   // SD 命令索引          (Register 11-23)
__sfr __at(0xE7) SRCTL;   // SD 响应控制          (Register 11-3)
__sfr __at(0xE8) SPND;   // SD 待处理标志        (Register 11-1)
__sfr __at(0xE9) SARG0;   // SD 命令参数 0        (Register 11-24)
__sfr __at(0xEA) SARG1;   // SD 命令参数 1        (Register 11-25)
__sfr __at(0xEB) SARG2;   // SD 命令参数 2        (Register 11-26)
__sfr __at(0xEC) SARG3;   // SD 命令参数 3        (Register 11-27)

// Star 修改: 以下三位从原 ONF 控制器位移至 SD/SPI 扩展寄存器
__sfr __at(0xED) SPI_CNT;   // SPI 模式时钟计数 (Register 11-30)
__sfr __at(0xEE) MEM_CACHE_SEL;   // Memory Cache 时钟选择 (Register 9-30 STATUS bit7)
__sfr __at(0xEF) SDLASTCMD;   // SD 最后命令索引/HCS (Register 11-29)

//=============================================================================
//  9.10  通用 IO 寄存器 (0xF3-0xFF)
//         Spec: Register 6-7 ~ 6-14
//=============================================================================
__sfr __at(0xF3) P0;   // Port0 数据寄存器 (Register 6-7)
__sfr __at(0xF4) P1;   // Port1 数据寄存器 (Register 6-8, 含P17控制位)
__sfr __at(0xF5) P2;   // Port2 数据寄存器 (Register 6-9)
__sfr __at(0xF7) P4;   // Port4 数据寄存器 (Register 6-10, SD 引脚只读)
__sfr __at(0xFC) P0DIR;   // Port0 方向控制   (Register 6-11, 0=输出,1=输入)
__sfr __at(0xFD) P1DIR;   // Port1 方向控制   (Register 6-12)
__sfr __at(0xFE) P2DIR;   // Port2 方向控制   (Register 6-13)


//=============================================================================
//  9.11  通用寄存器 R00-R43 (0xC0-0xC8, 0xD8, 0xE0, 0xF0, 0xF8, 0xB7)
//         Spec: Register 3-16 ~ 3-37, 3-15 (R8)
//=============================================================================
__sfr __at(0xC0) R00;   // 通用寄存器 00 (Register 3-16)
__sfr __at(0xC1) R01;   // 通用寄存器 01 (Register 3-17)
__sfr __at(0xC2) R02;   // 通用寄存器 02 (Register 3-18)
__sfr __at(0xC3) R03;   // 通用寄存器 03 (Register 3-19)
__sfr __at(0xC4) R40;   // 通用寄存器 40 (Register 3-34)
__sfr __at(0xC5) R41;   // 通用寄存器 41 (Register 3-35)
__sfr __at(0xC6) R42;   // 通用寄存器 42 (Register 3-36)
__sfr __at(0xC7) R43;   // 通用寄存器 43 (Register 3-37)
__sfr __at(0xC8) R10;   // 通用寄存器 10 (Register 3-20)
__sfr __at(0xC9) R11;   // 通用寄存器 11 (Register 3-21)
__sfr __at(0xCA) R12;   // 通用寄存器 12 (Register 3-22)
__sfr __at(0xCB) R13;   // 通用寄存器 13 (Register 3-23)
__sfr __at(0xD8) R20;   // 通用寄存器 20 (Register 3-24)
__sfr __at(0xD9) R21;   // 通用寄存器 21 (Register 3-25)
__sfr __at(0xDA) R22;   // 通用寄存器 22 (Register 3-26)
__sfr __at(0xDB) R23;   // 通用寄存器 23 (Register 3-27)
__sfr __at(0xE0) ACC;   // 累加器 ACC    (Register 3-28)
__sfr __at(0xF0) B;   // B 寄存器      (Register 3-29)
__sfr __at(0xD0) PSW;   // 程序状态字   (Register 3-14)
__sfr __at(0xF8) R30;   // 通用寄存器 30 (Register 3-30)
__sfr __at(0xF9) R31;   // 通用寄存器 31 (Register 3-31)
__sfr __at(0xFA) R32;   // 通用寄存器 32 (Register 3-32)
__sfr __at(0xFB) R33;   // 通用寄存器 33 (Register 3-33)

// 注：以下为 spec 中属于 SFR 空间但 star.h 中部分移至 XSFR 的寄存器
// CHIP_IDH(0xBB)/CHIP_IDL(0xBA)/CHIP_DCN(0xB9) → 移至 XSFR 0xC00A/0xC009/0xC008
//  原 SFR 地址 0xB9复用于WKFLAG, 0xBA复用于EXINTR1, 0xBB复用于SPI_SLV_CFG1
// P1HNL/P1PLP/P1DSHB/P1DSLB → 移至 XSFR 但当前固件未使用(已注释)
// SDLASTCMD(0xEF)/MEM_CACHE_SEL(0xEE)/SPI_CNT(0xED) → Star 新定义，替代原 ONF 寄存器

//=============================================================================
//=============================================================================
//  SFR 位寻址定义 (sbit)
//  注：仅地址能被 8 整除的 SFR 支持位寻址（C51 规范）
//      位地址 = SFR 基址 + 位偏移
//=============================================================================

//------------------------------------------------------------------------
//  DPCTL (0x80) — 数据指针控制  (Register 3-1)
//------------------------------------------------------------------------
__sbit __at(0x87) DPID1;   // DPTR1 自动增/减方向 (0=增,1=减)
__sbit __at(0x86) DPID0;   // DPTR0 自动增/减方向 (0=增,1=减)
__sbit __at(0x85) DPAST;   // 自动 DPTR 切换使能
__sbit __at(0x84) DPAID;   // 自动 DPTR 增/减使能
__sbit __at(0x83) CHEND;   // 大小端切换 (0=小端,1=大端)
__sbit __at(0x82) ASHF;   // 算数移位模式 (ROTR32)
__sbit __at(0x81) LSHF;   // 逻辑移位模式 (ROTR32)
__sbit __at(0x80) DPSEL;   // DPTR 选择 (0=DPTR0,1=DPTR1)

//------------------------------------------------------------------------
//  NTCTL1 (0x98) — NAND Flash 时序控制 1 (Register 8-12)
//------------------------------------------------------------------------
__sbit __at(0x9F) NTSKD;  // NAND 任务完成标志 (1=完成,写0清除)
__sbit __at(0x9E) NWBDLY2;  // WB 下降沿等待周期 [2]
__sbit __at(0x9D) NWBDLY1;  // WB 下降沿等待周期 [1]
__sbit __at(0x9C) NWBDLY0;  // WB 下降沿等待周期 [0]
__sbit __at(0x9B) NPTDLY1;  // NAND 保持时间 [1] (spec: NHLD1)
__sbit __at(0x9A) NPTDLY0;  // NAND 保持时间 [0] (spec: NHLD0)
__sbit __at(0x99) NSTP1;  // NAND 建立时间 [1]
__sbit __at(0x98) NSTP0;  // NAND 建立时间 [0]

//------------------------------------------------------------------------
//  PCTL (0xA0) — 电源控制  (Register 5-1)
//------------------------------------------------------------------------
__sbit __at(0xA7) SRAM_CE_;    // SRAM 片选使能 (0=使能,1=关闭) (spec: SRAM_CE_)
__sbit __at(0xA6) SDCKE;    // SD 时钟使能 (1=使能)
__sbit __at(0xA5) BCKE;    // BCH 时钟使能 (spec: BCKE)
__sbit __at(0xA4) BDCKE;    // NAND Flash 时钟使能
__sbit __at(0xA3) NCKE;    // Timer/Serial/IO 时钟使能
__sbit __at(0xA2) INTBK;    // 中断反馈
__sbit __at(0xA1) PD;    // 掉电模式 (1=进入, RC 低功耗+门控)
__sbit __at(0xA0) IDLE;    // IDLE 模式 (1=CPU暂停,中断唤醒)

//------------------------------------------------------------------------
//  IE (0xA8) — 中断使能  (Register 3-9)
//------------------------------------------------------------------------
__sbit __at(0xAF) EA;      // 全局中断使能
__sbit __at(0xAE) BSIE;      // ECC Step1 中断使能
__sbit __at(0xAD) BIE;      // ECC 中断使能
__sbit __at(0xAC) NFIE;      // NAND Flash 中断使能
__sbit __at(0xAB) SDOIE;      // SD 数据输出中断使能
__sbit __at(0xAA) SDIIE;      // SD 数据输入中断使能
__sbit __at(0xA9) SDRIE;      // SD 响应中断使能
__sbit __at(0xA8) SDCIE;      // SD 命令中断使能

//------------------------------------------------------------------------
//  TCTL (0xB0) — 定时器控制  (Register 7-1)
//------------------------------------------------------------------------
__sbit __at(0xB7) TOF;    // 定时器溢出标志 (1=溢出)
__sbit __at(0xB6) TPSR2;    // 预分频选择 [2]
__sbit __at(0xB5) TPSR1;    // 预分频选择 [1]
__sbit __at(0xB4) TPSR0;    // 预分频选择 [0]
__sbit __at(0xB3) SPKS;    // UART TX 启动 (写1启动发送)
__sbit __at(0xB3) SPTD;    // UART TX 完成标志 (1=完成)

//------------------------------------------------------------------------
//  PSW (0xD0) — 程序状态字  (Register 3-14)
//------------------------------------------------------------------------
__sbit __at(0xD7) CY;    // 进位标志
__sbit __at(0xD6) AC;    // 辅助进位标志
__sbit __at(0xD5) EC;    // 扩展进位标志 (Star 扩展)
__sbit __at(0xD4) RS1;    // 寄存器组选择 [1]
__sbit __at(0xD3) RS0;    // 寄存器组选择 [0]
__sbit __at(0xD2) OV;    // 溢出标志
__sbit __at(0xD1) EZ;    // 零标志 (Star名称, 标准8051为F0/Z)
__sbit __at(0xD0) P;    // 奇偶标志

//------------------------------------------------------------------------
//  SFLAG (0x90) — SDC 状态标志  (Register 11-6)
//------------------------------------------------------------------------
__sbit __at(0x97) SBYST;  // 忙命令接收中 (1=接收)
__sbit __at(0x96) SDIST;  // SD DMA 数据无效 (1=无效)
__sbit __at(0x95) SSTAINV;  // SSTA 无效 (1=无效)
__sbit __at(0x94) SCEND;  // 命令结束 (1=结束)
__sbit __at(0x93) SDCRC;  // SD 数据 CRC 错误 (1=错误)
__sbit __at(0x92) SRPSTS;  // 无响应/CMD CRC错误/状态机无效 (1=异常)
__sbit __at(0x91) SRCAST;  // RCA 匹配 (1=匹配)
__sbit __at(0x90) SCCRC;  // CMD CRC 错误 (1=错误)

//------------------------------------------------------------------------
//  SPND (0xE8) — SD 待处理标志  (Register 11-1)
//------------------------------------------------------------------------
__sbit __at(0xEF) SPIMODE;   // SPI 模式指示
__sbit __at(0xEB) SDOPND;   // SD 数据输出待处理
__sbit __at(0xEA) SDIPND;   // SD 数据输入待处理
__sbit __at(0xE9) SRPND;   // SD 响应待处理
__sbit __at(0xE8) SCPND;   // SD 命令待处理

#endif  /* STAR2_H */
