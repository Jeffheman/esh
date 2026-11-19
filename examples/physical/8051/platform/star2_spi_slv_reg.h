//=============================================================================
//  Star2 - SPI 从机窗口寄存器 (IRTCC) 定义头文件
//=============================================================================
//  Description:
//    本文件定义 STAR 芯片中经 SPI 从机窗口访问的 IRTCC 寄存器，包含两部分:
//      1) 命令码     : 0x50-0x7F, Spec Table 9-1 (PDF p83-84)
//      2) 功能位定义 : CFG0-CFG16 / STATUS / PENDING / FLASH_MID / FLASH_DID /
//                      ADR / SPI_ADR0-3 / UNKNOWN_CMD, Spec Register 9-12 ~ 9-36
//                      (PDF p90-103)
//
//  IMPORTANT:
//    这些寄存器【不是 SFR，也不是 XSFR】, CPU 不能用 sfr/sbit 直接寻址,
//    必须通过上述 0x50-0x7F 命令码经 SPI 从机窗口间接读写。
//    本文件不依赖 star2.h, 可单独 #include。
//
//  位号依据:
//    一律采用坐标法复核 (page.extract_text(visitor_text=...) 取词元 x/y,
//    以 spec 寄存器表 Position 行 x 为列锚点比对), 脚本见
//      docs/spec/extracted/_bitcheck.py   (通用位号复核)
//      docs/spec/extracted/_cfgbits.py    (CFG 系列 Name 行重建)
//    原因: spec 位表存在两类陷阱, 仅凭抽取文本的行文顺序对齐 bit 会判错位号
//      (a) 未实现位在 Name 行留空        -> 8 列可能只有 6 个名字
//      (b) 多 bit 字段左对齐到 MSB 列    -> 后续列留空
//
//  Split from:  star2.h 第 8 / 8B 节 (2026-10-24 拆分)
//  Base:        spi_spec_STAR_design_specification_v0.04.pdf (2022-06-22, 作者 Curry)
//  Note:        节号沿用拆分前 star2.h 的 8 / 8B, 便于与历史版本逐行对照
//  Full SDCC adaptation from trunk/inc/star2_spi_slv_reg.h.
//=============================================================================

#ifndef STAR2_SPI_SLV_REG_H
#define STAR2_SPI_SLV_REG_H

//=============================================================================
//  8. SPI 从机窗口寄存器命令码 (0x50-0x7F)
//     用于与 SPI SLAVE (GD Domain) 内部寄存器通信
//     Spec: Table 9-1 SPI slave components communication commands
//     注：_WR 即写命令触发操作，_RD 即读命令获取结果
//=============================================================================
// -- 基础配置组 (0x50-0x58) --
#define REG_CFG0_WR        0x50   // 写 CFG0   (Write_CFG,  Register 9-12)
#define REG_CFG0_RD        0x51   // 读 CFG0   (Read_CFG)
#define REG_DID_WR         0x52   // 写 Flash DID (DID_WR, Register 9-30)
#define REG_MID_WR         0x53   // 写 Flash MID (MID_WR, Register 9-29)
#define REG40_CMD_ADR_RD   0x54   // 读 Flash地址+CMD存储 (CMD_STORE, Register 9-32)
#define REG_CFG1_WR        0x55   // 写 CFG1   (Write_CFG1, Register 9-13)
#define REG_CFG1_RD        0x56   // 读 CFG1   (Read_CFG1)
#define REG_CFG2_WR        0x57   // 写 CFG2   (Write_CFG2, Register 9-14)
#define REG_CFG2_RD        0x58   // 读 CFG2   (Read_CFG2)

// -- 状态/特性/保护/待处理 (0x59-0x5E) --
#define REG_FEA_RD         0x59   // 读 Feature (FEA READ, Register 9-??)
#define REG_PRO_RD         0x5a   // 读 Protect (PRO_READ)
#define REG_STA_RD         0x5b   // 读 Status  (STA_READ,  Register 9-30)
#define REG_STA_WR         0x5c   // 写 Status  (STA WRITE, Register 9-30)
#define REG_PND_WR         0x5d   // 写 Pending (PND WRITE, Register 9-31)
#define REG32_SPI_ADR0_RD  0x5e   // 读 SPI 首地址 32bit (SPI_ADR_RD, Register 9-33)

// -- 扩展配置组 CFG3-CFG9 (0x60-0x6D) --
#define REG_CFG3_WR        0x60   // 写 CFG3 (Register 9-15)
#define REG_CFG3_RD        0x61   // 读 CFG3
#define REG_CFG4_WR        0x62   // 写 CFG4 (Register 9-16)
#define REG_CFG4_RD        0x63   // 读 CFG4
#define REG_CFG5_WR        0x64   // 写 CFG5 (Register 9-17)
#define REG_CFG5_RD        0x65   // 读 CFG5
#define REG_CFG6_WR        0x66   // 写 CFG6 (Register 9-18)
#define REG_CFG6_RD        0x67   // 读 CFG6
#define REG_CFG7_WR        0x68   // 写 CFG7 (Register 9-19)
#define REG_CFG7_RD        0x69   // 读 CFG7
#define REG_CFG8_WR        0x6a   // 写 CFG8 (Register 9-20)
#define REG_CFG8_RD        0x6b   // 读 CFG8
#define REG_CFG9_WR        0x6c   // 写 CFG9 (Register 9-21)
#define REG_CFG9_RD        0x6d   // 读 CFG9

// -- 16bit 新窗口 (0x6E-0x70) --
#define REG16_CFG16_WR     0x6E   // 写 CFG16 16bit (Register 9-28, P0_PU/P2_PU)
#define REG16_CFG16_RD     0x6F   // 读 CFG16 16bit
#define REG16_UNKNOWN_RD   0x70   // 读 Unknown CMD 16bit (Register 9-36)

// -- SPI 地址历史 (0x71-0x73) 各 32bit --
#define REG32_SPI_ADR1_RD  0x71   // 读 SPI_ADR1 历史 (Register 9-34)
#define REG32_SPI_ADR2_RD  0x72   // 读 SPI_ADR2 历史 (Register 9-35)
#define REG32_SPI_ADR3_RD  0x73   // 读 SPI_ADR3 历史

// -- 扩展配置组 CFG10-CFG15 (0x74-0x7F) --
#define REG_CFG10_WR       0x74   // 写 CFG10 (Register 9-22)
#define REG_CFG10_RD       0x75   // 读 CFG10
#define REG_CFG11_WR       0x76   // 写 CFG11 (Register 9-23)
#define REG_CFG11_RD       0x77   // 读 CFG11
#define REG_CFG12_WR       0x78   // 写 CFG12 (Register 9-24)
#define REG_CFG12_RD       0x79   // 读 CFG12
#define REG16_CFG13_WR     0x7A   // 写 CFG13 16bit (Register 9-25, RC/唤醒控制)
#define REG16_CFG13_RD     0x7B   // 读 CFG13 16bit
#define REG_CFG14_WR       0x7C   // 写 CFG14 (Register 9-26, ECC/LUT/DS_IO)
#define REG_CFG14_RD       0x7D   // 读 CFG14
#define REG_CFG15_WR       0x7E   // 写 CFG15 (Register 9-27, EN_FEA/EN_PRO)
#define REG_CFG15_RD       0x7F   // 读 CFG15

//=============================================================================
//  8B. SPI 从机窗口寄存器 (IRTCC) 功能位定义
//      Spec: Register 9-12 ~ 9-36 (PDF p90-103)
//      说明: 这些寄存器不是 SFR，只能通过上面的 0x50-0x7F 命令码经 SPI 窗口访问
//            位号一律用坐标法复核（docs/spec/extracted/_bitcheck.py）
//            注意 标记处 = spec 位表与描述文本互相矛盾，已登记差异台账，待设计方确认
//=============================================================================

//------------------------------------------------------------------------
//  CFG0 (Register 9-12, 命令 0x50/0x51) — GD 控制 / SPI_PWR_CTL  (PDF p90)
//  Name 行 8 位全为 SPI_PWR_CTL；Default = 0b0100_0110, bit7/5 = RO
//------------------------------------------------------------------------
#define CFG0_RPD2M          (1 << 0)   // bit0: VDDSPI CAPLESS LDO 60uA 电流使能
#define CFG0_RPD20U         (1 << 1)   // bit1: VDDSPI CAPLESS LDO 20uA 电流（SPI_CS=0 时自动使能）
#define CFG0_VSPIS_MASK     (0x3 << 2) // bit[3:2]: VDDSPI 输出选择 00=1.2V 01=1.25V 10=1.30V 11=1.35V
#define CFG0_VSPIS_SHIFT    2
#define CFG0_VSPIS(n)       ((n) << CFG0_VSPIS_SHIFT)
#define CFG0_RPD2MIO        (1 << 4)   // bit4: 0.9m 下拉使能（改善瞬态响应）
#define CFG0_RPD8MIO        (1 << 5)   // bit5: 4.3m 下拉使能（改善瞬态响应）
#define CFG0_LVD_EN         (1 << 6)   // bit6: LVD 使能 (1=enable)
#define CFG0_LDO_TESTEN     (1 << 7)   // bit7: LDO 测试使能 (RO)
// 注：p90 描述文本中残留的 SFR_CMT / SFR_SEL（SPI 命令集选择，与 P41 配合）
//     在 spec v0.04 中已删除，不作为 CFG0 的位，此处不提供宏

//------------------------------------------------------------------------
//  CFG1 (Register 9-13, 命令 0x55/0x56) — SPI 配置 1  (PDF p90-91)
//  Default = 0b0000_0010
//------------------------------------------------------------------------
#define CFG1_TST_EN         (1 << 7)   // bit7: CP/FT 测试使能 (0=内部RC RC80M/32, 1=取反的ctl_clk)
#define CFG1_CMP_CLK_TUN_MASK (0x7 << 4) // bit[6:4]: SPI 采样时钟延迟档 (3'b0xx=unit0 … 3'b111=unit4)
#define CFG1_CMP_CLK_TUN_SHIFT 4
#define CFG1_CLK_TUN_MASK   (0xF << 0) // bit[3:0]: SPI 时钟微调 (0000=delay unit0 … 1111=unit15)
#define CFG1_CLK_TUN_SHIFT  0
#define CFG1_CLK_TUN(n)     ((n) << CFG1_CLK_TUN_SHIFT)

//------------------------------------------------------------------------
//  CFG2 (Register 9-14, 命令 0x57/0x58) — SPI 配置 2  (PDF p91)
//  Default = 0b0001_1001
//------------------------------------------------------------------------
#define CFG2_VDDNF_APD_EN   (1 << 6)   // bit6: VDDCORE 掉电时 VDDNF 自动下电使能
#define CFG2_DIS_SPI_CS_PUP (1 << 5)   // bit5: 屏蔽 SPI_CS 自动关断 SPI_CLK 100K 上拉
#define CFG2_VDDNF_EN       (1 << 4)   // bit4: VDDNF 使能 (0=关断, 1=使能；开关间隔≥10us)
#define CFG2_DI_TUNE_MASK   (0x7 << 1) // bit[3:1]: DI/DO/WP/HOLD 输入延迟微调
#define CFG2_DI_TUNE_SHIFT  1
#define CFG2_O_CLK_SEL      (1 << 0)   // bit0: 输出数据切到 SPI_CLK 下降沿 (1=使能，default)

//------------------------------------------------------------------------
//  CFG3/CFG4/CFG5/CFG6/CFG7/CFG8 (Register 9-15 ~ 9-20)
//  分别控制 P40(SPI_DI) / P42(SPI_CLK) / P43(SPI_HOLD) / P46(SPI_WP)
//           / P47(SPI_DO) / P48(SPI_CS) 的 IO 行为
//  公共位序: bit7=PU  bit6=PU1  bit5=PD  bit4=HD  bit3=HNL  bit2=ENHD  bit1=ENSC  bit0=SELSC
//------------------------------------------------------------------------
#define CFGIO_PU            (1 << 7)   // bit7: 30K 上拉使能
#define CFGIO_PU1           (1 << 6)   // bit6: 10K(CFG3/CFG7) 或 100K(CFG4/CFG5/CFG6/CFG8) 上拉使能
#define CFGIO_PD            (1 << 5)   // bit5: 下拉使能（10K；CFG6 为 1K）
#define CFGIO_HD            (1 << 4)   // bit4: 驱动强度 0=12mA 1=16mA
#define CFGIO_HNL           (1 << 3)   // bit3: 输入迟滞 1=大迟滞
#define CFGIO_ENHD          (1 << 2)   // bit2: slew rate 控制模式下的驱动能力选择
#define CFGIO_ENSC          (1 << 1)   // bit1: slew rate 控制输出模式使能
#define CFGIO_SELSC         (1 << 0)   // bit0: slew rate 控制模式的速率选择
// CFG4 专用 (PDF p92-93): Default = 0b0100_0001
#define CFG4_P40_SEL        (1 << 2)   // bit2: 选择由 P4_CFG 控制 P40 的 oe/dout
#define CFG4_P40_PU         (1 << 1)   // bit1: P40 30K 上拉使能
#define CFG4_P40_PU1        (1 << 0)   // bit0: P40 100K 上拉使能
// CFG5 专用 (PDF p93): Default = 0b0100_0000
//   bit2/1/0 在 CFG5 中为 SEL / SPI_HV_SEL / DISABLE_HOLD
//   （位表中同列的 ENHD/ENSC/SELSC 是 CFG3~CFG8 模板残留，spec v0.04 已删除，不适用于 CFG5）
#define CFG5_SEL            (1 << 2)   // bit2: IO 控制选择 (1=SPI_HOLD 的 IE/OE/CIN 由 spi_slv_cfg2 控制)
#define CFG5_SPI_HV_SEL     (1 << 1)   // bit1: SPI IO 驱动模式 0=大驱动(1.8V) 1=小驱动(3.3V)
#define CFG5_DISABLE_HOLD   (1 << 0)   // bit0: 1/2 线模式下禁止 SPI_HOLD 的 HOLD 功能
// CFG6 专用 (PDF p93): Default = 0b0100_0000
#define CFG6_DISABLE_WP     (1 << 0)   // bit0: 1/2 线模式下禁止 SPI_WP 的 WP 功能
// CFG7 专用 (PDF p94): Default = 0x00（控制 P47）；注意 描述文本又给 P40_DO/P40_OE
#define CFG7_P40_DO         (1 << 1)   // bit1: CFG4[2]=1 时，P40 数据输出由本位控制
#define CFG7_P40_OE         (1 << 0)   // bit0: CFG4[2]=1 时，P40 输出使能由本位控制
// CFG8 专用 (PDF p94): Default = 0b0100_1111（控制 P48）
#define CFG8_CORE_PD_READY  (1 << 1)   // bit1: core_pd_ready，置1时 core→spi 信号被 AND2 阻断（default=1）
#define CFG8_NFIO_SLP       (1 << 0)   // bit0: NFIO_SLP

//------------------------------------------------------------------------
//  CFG9 (Register 9-21, 命令 0x6C/0x6D) — SPI 配置 9  (PDF p95)
//  Default = 0b0110_1011 = 0x6B（bit5 位表无名但 Default=1）
//------------------------------------------------------------------------
#define CFG9_POWER_ON       (1 << 6)   // bit6: 上电标志 (MROM 完成首次 POR 后置1；固件可清0区分冷热上电)
#define CFG9_SPI_CS_GW2     (1 << 4)   // bit4: SPI_CS 去毛刺控制 bit2
#define CFG9_SPI_CS_GW1     (1 << 3)   // bit3: SPI_CS 去毛刺控制 bit1
#define CFG9_SPI_CS_GW0     (1 << 2)   // bit2: SPI_CS 去毛刺控制 bit0
#define CFG9_WDT_RST_EN     (1 << 1)   // bit1: WDT 复位 VDDSPI 域 0=使能 1=禁止（default=1）
#define CFG9_RST_CMD_EN     (1 << 0)   // bit0: SPI HOST RESET 命令复位 CPU 0=使能 1=禁止（default=1）

//------------------------------------------------------------------------
//  CFG10 (Register 9-22, 命令 0x74/0x75) — 命令集使能  (PDF p95-96)
//  Default = 0x00
//------------------------------------------------------------------------
#define CFG10_BLK_ERS_WR    (1 << 7)   // bit7: 擦除期间允许 program load/random（覆盖 OIP 与 CFG12[0]）
#define CFG10_BLK_ERS_RD    (1 << 6)   // bit6: 擦除期间允许 cache read（覆盖 OIP 与 CFG12[0]）
#define CFG10_WINBOND       (1 << 4)   // bit4: 使能 Winbond 命令集 (0xA1/0xA5、0x05、0x01、LUT-F)
#define CFG10_NF_CACHE_RW   (1 << 3)   // bit3: 使能 cache read(0x31)/last page read(0x3F)/cache prog(0x15)
#define CFG10_READ_UID      (1 << 2)   // bit2: 使能 read UID (0x4B)
#define CFG10_INDV_BLK_LCK  (1 << 1)   // bit1: 使能独立块锁命令 (0x36/0x39/0x3D/0x7E/0x98) 与 WPS 位
#define CFG10_IGNORE_UNKNOW (1 << 0)   // bit0: 收到未知命令时是否向 CPU 发请求

//------------------------------------------------------------------------
//  CFG11 (Register 9-23, 命令 0x76/0x77) — Feature 表使能  (PDF p96-97)
//  Default = 0b0001_1000 = 0x18
//------------------------------------------------------------------------
#define CFG11_EN_ECCS2      (1 << 7)   // bit7: 使能 ECCS2（feature 0xC0 bit6）
#define CFG11_EN_FEA_F0     (1 << 6)   // bit6: 使能 0xF0 地址与 ECCSE[1:0]（0xF0 bit5-4）
#define CFG11_EN_FEA_D0     (1 << 5)   // bit5: 使能 0xD0 地址与 DS_IO[1:0]（0xD0 bit6-5）
#define CFG11_EN_QE         (1 << 4)   // bit4: 使能 QE 位（0xB0 bit0；禁能则始终接受 4 线命令）
#define CFG11_EN_INV_CMP    (1 << 3)   // bit3: 使能 INV/CMP 位（0xA0 bit7/bit6）
#define CFG11_WRAP_RD_MASK  (0x7 << 0) // bit[2:0]: Cache 大小与 wrap 读选项
#define CFG11_WRAP_RD_SHIFT 0
//   000: cache=2112 无 wrap / 001: cache=2176 无 wrap / 01x: reserved
//   100: 2112 wrap(2112/2048/64/16) / 101: 2176 wrap(2176/2048/64/16) / 110: 2176 only / 111: reserved
#define CFG11_WRAP_RD(n)    ((n) << CFG11_WRAP_RD_SHIFT)

//------------------------------------------------------------------------
//  CFG12 (Register 9-24, 命令 0x78/0x79) — SPI 配置 12  (PDF p97-98)
//  Default = 0b1100_0010 = 0xC2
//------------------------------------------------------------------------
#define CFG12_P17_PU        (1 << 7)   // bit7: P17 上拉使能
#define CFG12_TX_AT_POSEDGE (1 << 6)   // bit6: TX 在上升沿发送
#define CFG12_EN_FEA_REQ    (1 << 5)   // bit5: 收到 set feature(0xB0) 时向 CPU 发请求
#define CFG12_EN_PRO_REQ    (1 << 4)   // bit4: 收到 set feature(0xA0) 时向 CPU 发请求
#define CFG12_F_READ_ID_ADR (1 << 3)   // bit3: read ID(0x9F) 第二字节作地址(1) 还是 dummy(0)
#define CFG12_EN_FEA_90     (1 << 2)   // bit2: 使能 0x90 地址，ECC_EN 由 0xB0 bit4 移到 0x90 bit4
#define CFG12_UNWR_RGN_RST  (1 << 1)   // bit1: program load 后未写区域的 cache 读值 1=输出 0xFF
#define CFG12_IGNORE_OIP    (1 << 0)   // bit0: busy(OIP=1) 期间是否接受非 get feature/read ID/reset 命令

//------------------------------------------------------------------------
//  CFG13 (Register 9-25, 命令 0x7A/0x7B) — 16bit 电源/RC/唤醒控制  (PDF p98-99)
//  Default = 0x0704（[15:8]=0b0000_0111, [7:0]=0b0000_0100）
//------------------------------------------------------------------------
#define CFG13_PWR_OFF_SW      (1U << 15) // bit15: 软关机开关 (WO；1=使能 soft-off 计数)
#define CFG13_CNT_SEL_MASK    (0x3 << 12) // bit[13:12]: 掉电计数 01=512us 10=1ms 11=2ms
#define CFG13_CNT_SEL_SHIFT   12
#define CFG13_MST_LDO_WK_SEL  (1 << 11) // bit11: 核 LDO 唤醒源 0=spi_cs 引脚 1=特定 SPI 请求命令
#define CFG13_RC_WK_SEL       (1 << 10) // bit10: RC80M 唤醒源 0=spi_cs 引脚 1=特定 SPI 请求命令
#define CFG13_RC_RST_ENB      (1 << 9)  // bit9:  RC 复位控制 0=assert 1=release
#define CFG13_RC_EN_AO        (1 << 8)  // bit8:  RC always-on 模式 0=禁 1=使能
#define CFG13_RC_TRIM_MASK    (0x1F << 3) // bit[7:3]: RC 振荡频率微调 5'h0_0000≈80M … 5'b1_1111≈114M
#define CFG13_RC_TRIM_SHIFT   3
#define CFG13_RC_HF           (1 << 2)  // bit2: RC 高频模式 0≈10M 1≈80M（default=1）
#define CFG13_P_OFF_LP_CLR    (1 << 1)  // bit1: 掉电计数期间清除 RC 低速模式（写1脉冲）
#define CFG13_RC_WK_CLR       (1 << 0)  // bit0: RC 唤醒后清除唤醒状态（写1脉冲）

//------------------------------------------------------------------------
//  CFG14 (Register 9-26, 命令 0x7C/0x7D) — ECC/驱动强度  (PDF p99)
//  Default = 0x00
//------------------------------------------------------------------------
#define CFG14_LUT_FULL      (1 << 5)   // bit5: LUT-F（spec 位表写作 "LUT-F"，疑为 LUT full / BBM LUT 满）
#define CFG14_ECCS2         (1 << 4)   // bit4: ECCS2
#define CFG14_ECCSE_MASK    (0x3 << 2) // bit[3:2]: ECCSE[1:0] 页读后 ECC 附加结果（映射到 feature 0xF0 bit5-4）
#define CFG14_ECCSE_SHIFT   2
#define CFG14_DS_IO_MASK    (0x3 << 0) // bit[1:0]: DS_IO[1:0] SPI 引脚驱动强度（映射到 feature 0xD0 bit6-5）
#define CFG14_DS_IO_SHIFT   0
#define CFG14_DS_IO(n)      ((n) << CFG14_DS_IO_SHIFT)

//------------------------------------------------------------------------
//  CFG15 (Register 9-27, 命令 0x7E/0x7F) — Feature/Protect 位写权限  (PDF p100)
//  Default = 0x00；bit[7:5] = Reserved
//  注意 固件 Sspi.c:1857/1979 用 CFG15 bit5/bit6 作"休眠后 VDDSPI 电压控制 2bit"，
//    但 spec 标 bit7..5 为 Reserved → 差异台账 #6
//------------------------------------------------------------------------
#define CFG15_EN_FEA_BIT3   (1 << 4)   // bit4: 允许 SPI host 写 / CPU 读 feature 0xB0 bit3
#define CFG15_EN_FEA_BIT2   (1 << 3)   // bit3: 同上，0xB0 bit2
#define CFG15_EN_FEA_BIT1   (1 << 2)   // bit2: 同上，0xB0 bit1
#define CFG15_EN_PRO_BIT6   (1 << 1)   // bit1: 允许 SPI host 写 / CPU 读 protect 0xA0 bit6
#define CFG15_EN_PRO_BIT0   (1 << 0)   // bit0: 同上，0xA0 bit0

//------------------------------------------------------------------------
//  CFG16 (Register 9-28) — 16bit 上拉控制  (PDF p100)
//  注意 spec 有 Register 9-28，但 Table 9-1 未给 0x6E/0x6F 命令码（从 0x6D 直接跳到 0x70）
//------------------------------------------------------------------------
#define CFG16_P2_PU_MASK    0xFF00     // bit[15:8]: P20~P27 上拉使能（default 0xFF）
#define CFG16_P0_PU_MASK    0x00FF     // bit[7:0]:  P00~P07 上拉使能（default 0xFF）

//------------------------------------------------------------------------
//  STATUS (Register 9-30 STATUS, 命令 0x5B 读 / 0x5C 写)  (PDF p101)
//------------------------------------------------------------------------
#define STA_MEM_CLK_SEL     (1 << 7)   // bit7: SPI cache 存储器时钟选择
#define STA_POWER_FLAG      (1 << 6)   // bit6: 电源标志
#define STA_ECCS1           (1 << 5)   // bit5: ECC 状态 [1]
#define STA_ECCS0           (1 << 4)   // bit4: ECC 状态 [0]
#define STA_P_FAIL          (1 << 3)   // bit3: 编程失败
#define STA_E_FAIL          (1 << 2)   // bit2: 擦除失败
#define STA_WEL             (1 << 1)   // bit1: 写使能锁存 (RO，由 SPI HOST 写)
#define STA_OIP             (1 << 0)   // bit0: 忙标志 (RO)

//------------------------------------------------------------------------
//  PENDING (Register 9-31, 命令 0x5D 写) — 全部 WO，回读恒 0  (PDF p102)
//------------------------------------------------------------------------
#define PND_MST_PWR_OFF_DIS (1 << 7)   // bit7: 禁止自动掉电（写0=计数后自动 soft-off，写1=手动）
#define PND_MST_PWR_OFF     (1 << 6)   // bit6: 允许进入掉电（写1后检测 SPI CS 高电平）
#define PND_OIP_CLR         (1 << 5)   // bit5: 清 SPI HOST 时钟域 OIP（须先清 REQ_OIP_CLR 再置本位）
#define PND_OTP_PRT_SET     (1 << 4)   // bit4: 置 OTP_PRT
#define PND_PRO_CLR         (1 << 3)   // bit3: 清 PROTECT 变更中断请求
#define PND_FEA_CLR         (1 << 2)   // bit2: 清 FEATURE 变更中断请求
#define PND_WEL_CLR         (1 << 1)   // bit1: 清 WEL
#define PND_REQ_OIP_CLR     (1 << 0)   // bit0: 清 page read/program execute/block erase/reset 中断请求

//------------------------------------------------------------------------
//  FLASH_MID (Reg 9-29, 0x53 写) / FLASH_DID (Reg 9-30, 0x52 写)  (PDF p101)
//  8bit W/R：配置供 SPI host 读取的 flash MID / DID
//------------------------------------------------------------------------
//  命令 0x54 ({Flash_ADR_RD, CMD_STORE}) 返回 5 字节：
//    - FLASH_ADR (Reg 9-32)：flash 操作的 block/page 地址（24bit）
//    - CMD_STORE：最近一条命令的存储值
//------------------------------------------------------------------------

//------------------------------------------------------------------------
//  SPI_ADR / SPI_ADR1 / SPI_ADR2 / SPI_ADR3 (Reg 9-31 / 9-33 / 9-34 / 9-35)
//  命令 0x5E / 0x71 / 0x72 / 0x73，各 4 字节，全部 RO  (PDF p102-103)
//  记录 SPI PROGRAM 操作的起始/结束地址与类型（SPI_ADRn 为 SPI_ADRn-1 的历史）
//------------------------------------------------------------------------
// SDCC int is 16-bit; UL preserves 32-bit shifts and mask complements.
#define SPIADR_PRPL_MASK    (0x3UL << 30) // bit[31:30]: 00=random program load 01=program load 1X=page read
#define SPIADR_PRPL_SHIFT   30
#define SPIADR_DAT_ALL_FF   (1UL << 29)   // bit29: 本次 program 命令的数据全为 0xFF
#define SPIADR_END_ADR_MASK (0xFFFUL << 16) // bit[27:16]: SPI PROGRAM 结束地址 (12bit)
#define SPIADR_END_ADR_SHIFT 16
#define SPIADR_ST_ADR_MASK  0xFFFFUL    // bit[15:0]:  SPI PROGRAM 起始地址 (16bit)
#define SPIADR_ST_ADR_SHIFT 0

//------------------------------------------------------------------------
//  UNKNOWN_CMD (Register 9-36, 命令 0x70)  (PDF p103)
//------------------------------------------------------------------------
#define UNKCMD_PARAM_MASK   0xFF00     // bit[15:8]: 该命令的参数字节数 (0~40)
#define UNKCMD_OPCODE_MASK  0x00FF     // bit[7:0]:  未知/扩展命令的操作码

#endif  /* STAR2_SPI_SLV_REG_H */
