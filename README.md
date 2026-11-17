**Important disclaimer**:

    This is not an officially supported Google product

# Embedded Shell

**A Terminal like interface over UART.**

- Targeted at embedded systems engineers and researchers who want to explore the hardware by writing small functions that can be triggered from a shell like interface.
- A UART based shell that enables finer control of CPU by allowing functions to be exposed as commands to be triggered from the prompt.
- Low memory footprint of < 4kB

this is a perfect tool for getting up and running with a new board in less than 1 hour.

### Features:
- Low footprint shell implementation.
- Commands with same foot print as `int main(int argc, char* argv[]){}`
- Export function as command using a macro (`ADD_CMD()` available in `shell.h`).
- Supported Languages: **C**, **C++** and **Assembly**.
- Automatic source file discovery
    - `.c`, `.cpp` and `.S` source files in the Project and shell directory are automatically picked for compilation **(No need to modify any Makefile. The build system automatically figrues the source files)**.
- Automatic Header discovery.
    - location for `.h` and `.hpp` files is automatically passed to the compiler for header file lookup.

### Supported Processors/Architectures
`examples/` implements a `hello world` example for the processor variety listed below:
| Architecture             | Processor            | Example Location                             | Board                             |
| :---                     |:--                   |:---                                          |:-                                 |
| ARM v7 A-class 32 bit    |Cortex-a7 (quadcore)  | examples/emulation/armv7A-32-Rpi2            | raspberry pi 2b (Emulated on Qemu)|
| ARM v8 A-class 32 bit    |Cortex-a53            | examples/emulation/armv8A-32-RPi3b           | raspberry pi 3b (Emulated on Qemu)|
| ARM v7 M-class 32 bit    |Cortex-m3             | examples/emulation/armv7M-32                 | mps2-an385 (Emulated on Qemu)     |
| ARM v8 A-class 64 bit    |Cortex-a72            | examples/emulation/armv8A-64                 | virt (Emulated on Qemu)           |
| ARM v8 A-class 64 bit    |Cortex-a72 (quadcore) | examples/emulation/armv8A-64-smp (multicore) | virt (Emulated on Qemu)           |
| ARM v8 M-class 32 bit    |Cortex-m33 (dualcore) | examples/emulation/armv8M-32 (multicore)     | mps3-an524 (Emulated on Qemu)     |
| RISC-V 64 bit            |rv64g                 | examples/emulation/riscv-64                  | virt (Emulated on Qemu)           |
| RISC-V 32 bit (RV32IMAC) |SiFive E31            | examples/physical/hifive                     | hifive1-revb (Physical Board)     |
| ARM v7 M-class 32 bit    |Cortex-m4             | examples/physical/nucleo-f401re              | nucleo-f401re (Physical Board)    |
| ARM v7 M-class 32 bit    |Cortex-m4             | examples/physical/tiva-c                     | tiva-c (Physical Board)           |

# Quick Setup

Execute `./manage -s` or `.scripts/setup` to install all the dependencies.

## Quick Demo

Following is a run of example in `examples/emulation/riscv-64`
```shell
cd examples/emulation/riscv-64
make
make run
```
![Qemu Demo](docs/images/demo.gif)

If you haven't done the `Quick Setup` as noted above, you'll need to install following utilities:

```
sudo apt install -y binutils make binutils-riscv64-linux-gnu gcc-riscv64-linux-gnu g++-riscv64-linux-gnu \
                    qemu-system-riscv64

wget -P ~ https://git.io/.gdbinit

pip3 install pygments
```

Further, gdb based debugging can also be done by running the following commands in two separate terminals:
```
make debug
```
and
```
make gdb
```
![Qemu Debug](docs/images/debug.gif)

You should see similar output as in above visual.

## Agent / MCP MVP (RISC-V QEMU)

<a id="agent-mcp-wiki"></a>

### 方案 WIKI：让 Agent 通过 esh 与底层 IC 对话

本方案将 esh 从人工串口调试入口扩展为 IC Agent 可调用的受控 READ + WRITE 接口：**Agent 负责理解、解释和请求用户批准，主机 MCP Server 负责接口、写预览与传输，固件负责确定性的硬件访问。** IC 不运行大模型，固件也不实现 MCP 或 JSON 解析器。

当前选择是 **框架优先，以 RISC-V QEMU `virt` 验证受控读写；尚未选定真实板卡**，不是已经完成的通用芯片插件平台。此示例只有一种 Shell 固件，默认通过 `ADD_CMD(mcp, ...)` 注册 `mcp`；启动、`help`、`history`、普通命令与 MCP 共用同一份 `shell.elf`。原项目的低内存占用介绍不代表加入 MCP 通信后的固件大小保证。

目录：

1. [目标、边界与架构](#mcp-architecture)
2. [两端职责与源码地图](#mcp-implementation)
3. [MCP 工具、资源与位域解释](#mcp-api)
4. [UART 通信协议与恢复规则](#mcp-protocol)
5. [构建与启动](#mcp-build)
6. [Qoder / WSL 接入](#mcp-qoder)
7. [人工验证、自动测试与排障](#mcp-validation)
8. [安全约束与后续扩展](#mcp-roadmap)

<a id="mcp-architecture"></a>

### 1. 目标、边界与架构

闭环是：显式识别设备 → 读取白名单寄存器/解释位域/执行只读诊断 → 准备 SCR 写预览 → **展示完整预览并停止，等待用户明确批准** → 使用一次性 token 执行比较后写入 → 展示实际读回与结果。不把用户提出实验目标等同于批准某次具体写预览。

```text
Qoder / 其他 MCP 客户端中的 Agent
  │ MCP：工具调用与资源读取，JSON-RPC over stdio
  │ 写入必须先展示预览并获得明确批准
  ▼
主机 MCP Server（Python + 官方 MCP SDK + pyserial）
  ├─ 固定工具参数、设备描述与位域解释
  ├─ 兼容性检查、一次性写计划、请求排队、超时与错误报告
  └─ 本地串口传输
          │ mcp <ID> h / r lcr / r s / t normal / w s <expected> <desired>
          │ @ESH1 响应；QEMU 中由 PTY 承载 UART 字节流
          ▼
esh Shell 固件（RISC-V 裸机，shell.elf）
  ├─ prompt() / shell()：有界输入、参数解析及交互功能
  ├─ ADD_CMD(mcp, ...)：固定操作分发与板级寄存器白名单
  └─ volatile MMIO：读取；比较 expected 后至多一次写入，再读回
          ▼
QEMU virt 16550 UART：LCR（0x10000003，只读）/ SCR（0x10000007，受控读写），均为 8 位
```

| 能力 | 当前范围 |
| :--- | :--- |
| 设备识别 | 板型、构建提交号、寄存器描述摘要、支持操作 |
| 寄存器读取/位域解释 | `uart0.lcr`、`uart0.scr`；每次用同一读值解码位域，禁止任意地址 |
| 受控写入 | 仅 `uart0.scr` 全 8 位；预览、明确批准、一次性 token、固件前置比较与读回 |
| 诊断 | 仅 `uart.normal_access`，检查 DLAB 是否为零，定义不变 |
| MCP 不开放 | LCR 写入、LSR 读取、自由 Shell 命令、复位、烧录 |
| 尚未实现 | 实板适配、运行时 board-profile 参数、I²C/SPI 后端、通用寄存器插件、多设备管理 |

**为什么不包装任意地址或自由 Shell 命令？** 这类入口不能充当受限的机器接口。因此在正常 Shell 中注册白名单 `mcp` 命令，用请求 ID 和独立行的 `@ESH1` 响应区分机器结果与提示符、回显、日志；主机只生成固定命令，不向 Agent 暴露任意 `exec()`。

**这不是固件沙箱或认证机制。** 直接串口客户端仍可使用所有已注册的 Shell 命令，甚至直接提交固件写请求而绕过主机 token；仅在明确获准的自有专用测试环境中进行这种人工验证。用户限定 MCP 时，Agent 不得改走直接串口。移植到实板前必须审查其他命令、自动命令、`setup()` 和空闲 `loop()` 的硬件副作用。

<a id="mcp-implementation"></a>

### 2. 两端职责与源码地图

#### 主机端

| 文件 | 职责 |
| :--- | :--- |
| [host/pyproject.toml](host/pyproject.toml) | Python 包、MCP/pyserial 依赖及 `esh-mcp` 命令入口 |
| [server.py](host/src/esh_mcp/server.py) | 六个 MCP 工具、两个资源、stdio 生命周期；待处理调用上限为 8 |
| [device.py](host/src/esh_mcp/device.py) | 握手检查、读值解码、写预览/token 生命周期、WRITE 结果交叉核验 |
| [transport.py](host/src/esh_mcp/transport.py) | 最终 Shell 命令校验、单请求在途、串口所有权、有界响应行解析、ID 匹配、超时与 Ctrl+C 重新同步 |
| [riscv64-virt.json](host/src/esh_mcp/data/riscv64-virt.json) | schema 2 板级描述：地址、宽度、别名、访问/写策略、位域及诊断定义 |

Server 通过 stdio 与 MCP 客户端通信，stdout 不能混入普通日志，诊断日志走 stderr。同步串口操作在线程中执行，不阻塞 MCP 事件循环；客户端取消调用不能撤回已发到 UART 的操作。

#### 固件端

| 文件 | 职责 |
| :--- | :--- |
| [RISC-V Makefile](examples/emulation/riscv-64/Makefile) | 唯一 Shell 构建、默认 `objects/` 缓存、生成头文件及 QEMU 控制台参数 |
| [riscv64.S](shell/startup/riscv64.S) | 设置并对齐栈；进入 `prompt()` |
| [shell.c](shell/shell/shell.c) | 正常启动、自动命令、`setup()`、交互输入与有界 argv 解析、空闲 `loop()` |
| [shell_config.h](shell/shell/shell_config.h) | 默认 `LINE_BUFF_SIZE=32`、`MAX_ARG_COUNT=16` |
| [rpc.c](examples/emulation/riscv-64/platform/rpc/rpc.c) | 以 `ADD_CMD(mcp, ...)` 注册短命令；分发 `HELLO` / `READ` / `TEST` / `WRITE` 并输出 `@ESH1` 响应 |
| [platform.cpp](examples/emulation/riscv-64/platform/platform.cpp) | 初始化 UART 并绑定字符读写回调 |
| [uart.cpp](examples/emulation/riscv-64/platform/uart/uart.cpp) | 基于 volatile MMIO 的轮询字符收发 |
| [generate_rpc_board.py](tools/generate_rpc_board.py) | 将板级描述生成固件白名单和清单摘要 |

唯一的 Shell 启动路径：

```text
_start → prompt() → initial_setup()（含 platform_init()）
                  → 自动命令 → setup() → 反复 shell()（无输入时调用 loop()）
```

没有独立的 RPC 入口或输入收帧循环。Shell 保留提示符、回显、`help`、`history` 等交互能力，并执行正常启动与空闲钩子；不能把只读 MCP 工具等同于整份固件没有副作用。

#### 两端描述的一致性

构建时从同一 JSON 描述生成 `objects/rpc_board.h`，编译器始终包含该头文件，主机也加载该 JSON。`platform/rpc` 源码始终参与构建，不被忽略；`rpc.c` 文件名和生成器的 `RPC_*` 名称仍用于描述处理函数与白名单，不代表另一个固件构建。握手中的 `map` 为以下规范化数据的 SHA-256：

```python
hashlib.sha256(
    json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()
```

主机要求板型、完整描述摘要以及操作列表 `READ,TEST,WRITE` 匹配，才允许后续读、诊断或受控写操作。`HELLO` 是识别操作，不列入其返回的 `ops`。`fw` 是构建时获取的 Git 提交号，不是 Python 包版本，也不能证明工作区没有未提交修改；描述摘要用于发现定义不一致，不提供身份认证。

schema 2 保留只读 `uart0.lcr`（别名 `lcr`）和原 `uart.normal_access`，增加 8 位 `uart0.scr`（别名 `s`），地址为 `virt` UART 基址 `0x10000000 + 7 = 0x10000007`。SCR 的唯一写策略为：

```json
{"mask":"0xff","effect":"stored_value_only","requires_expected":true}
```

依据是 [QEMU v6.2.0 serial.c](https://gitlab.com/qemu-project/qemu/-/raw/v6.2.0/hw/char/serial.c)：`serial_ioport_write` 的 `case 7` 仅设置 `s->scr`，对应读取 `case 7` 返回该值。这只支持 **QEMU 6.2 的存储值语义**，不是对其他版本、真实 16550 或任意 IC 的安全保证；不能据此将其他寄存器标成可写。

修改描述后，需要重新构建固件并重启 QEMU 和 MCP Server。当前主机工具 schema 和白名单还固定了寄存器/诊断名称，**仅增加 JSON 条目不会自动扩展所有 MCP 工具**；尚无运行时板型选择或通用 I²C/SPI 插件后端。

<a id="mcp-api"></a>

### 3. MCP 工具、资源与位域解释

原四个只读工具保留，两个读取工具增加 SCR；新增 prepare/execute 两个写工作流工具，共六个工具。不要把旧 Server 的四工具 schema 当作当前能力。

| 工具 | 参数 | 结果 |
| :--- | :--- | :--- |
| `get_device_info` | `{}` | 返回 `compatible`、板型、固件版本、摘要、操作列表及不匹配原因 |
| `read_register` | `register` 为 `uart0.lcr` 或 `uart0.scr` | 单次读取，返回 `register`、`width`、`value`、接收时间 |
| `read_register_fields` | `register` 为 `uart0.lcr` 或 `uart0.scr` | 在单次读取结果上增加全部 `fields`，不会逐位域重新读取 |
| `run_named_test` | `{"test":"uart.normal_access"}` | 单次读取，返回诊断结果及该次读取的证据值 |
| `prepare_register_write` | `{"register":"uart0.scr","value":165}` | 只读 SCR 并生成写预览，不写硬件 |
| `execute_register_write` | `{"confirmation_token":"<prepare 返回的 token>"}` | 消耗 token，发送一次条件写请求，返回实际比较/读回结果 |

必须先显式调用 `get_device_info`；没有隐式 HELLO。握手返回 `compatible: false` 时可查看不匹配原因，但后续访问会被拒绝。prepare 的寄存器参数仅接受字面量 `uart0.scr`，`value` 必须是严格整数 0..255（不接受布尔、浮点、字符串或十六进制字符串）。

#### 两阶段写入与批准

prepare 返回完整预览：`register`、`width`、十六进制 `expected` / `requested`、`board`、`manifest_digest` 描述摘要、`write_policy`、由 32 个小写十六进制字符组成的 `confirmation_token`、`expires_in_seconds: 60`、UTC `expires_at`、`status: "prepared"`。它读取当前 SCR 作为 expected，不执行写入。

1. Agent 原样展示完整预览并请求用户对该次具体写入的明确批准，**在批准前停止，不调用 execute**。
2. 用户批准后只提交该预览实际返回的 token，不自行生成 token，不以默认值替换 expected。
3. execute 在任何 UART 访问前消耗一次性 token。固件读取 `before`，仅当它等于 expected 时尝试一次写入并读回，否则零次写入。
4. 展示 `result`、`expected`、`requested`、`before`、`value`、`write_attempted` 布尔值及实际返回的时间戳；不能用请求值代替实际样本，也不能把协议 `OK` 当作写成功。

每个设备客户端仅有一个待执行计划；成功的新 prepare 会替换旧计划，重新握手、固件 ERR、在途传输/协议错误或关闭会清除计划。本地参数校验失败、无效 token 或未取得请求锁的 BUSY 不会清除仍有效的计划，但也不授权继续执行。有效期按单调时钟计算为 60 秒，UTC `expires_at` 仅用于展示。无效、过期或重放 token 不产生 UART 写请求。过期时必须重新 prepare、展示新预览并重新获得批准。

token 只绑定预览，**不是人类批准的认证凭据**。保留 Qoder 工具审批及工具注解：prepare 为 `readOnlyHint=true`、`idempotentHint=false`（会改变计划状态）；execute 为 `readOnlyHint=false`、`destructiveHint=true`、`idempotentHint=false`。注解不是权限控制，也不意味着已经实测 Qoder 审批 UI。禁止自动重试、回滚；取消或超时后禁止盲目重复写入。

两个资源仍不访问硬件：

- `esh://board/registers`：板型、描述摘要、寄存器与位域说明，镜像清单中的 `write_policy`。
- `esh://board/tests`：板型、描述摘要、诊断条件与解释边界。

读取返回示例（只是格式示例，不代表本次实测）：

```json
{
  "register": "uart0.lcr",
  "width": 8,
  "value": "0x00",
  "observed_at": "2026-11-17T07:44:20.805709Z",
  "observed_at_source": "host_utc_after_response"
}
```

数值使用十六进制字符串；位域结果格式为 `{"value":"0x0","width":1,"lsb":7}`。`observed_at` 是主机收到响应后的 UTC 时间，不是硬件采样时间。多次工具调用之间的寄存器状态可能变化，不能视为原子快照。

#### LCR 位域含义

| 位 | 字段 | 含义；当整个 LCR 为 `0x00` 时 |
| :--- | :--- | :--- |
| 1:0 | `word_length` | 数据位数为字段值加 5；此时为 5 位 |
| 2 | `extra_stop_bit` | 额外停止间隔；此时关闭，即一个停止位 |
| 3 | `parity_enabled` | 校验使能；此时关闭 |
| 4 | `even_parity` | 校验使能时选择偶校验；此时校验关闭，不能据此称为奇校验模式 |
| 5 | `stick_parity` | 固定校验位模式；仅在校验使能时有意义 |
| 6 | `break_enabled` | 发送 break；此时关闭 |
| 7 | `divisor_latch_access` | DLAB；此时为零，偏移 0/1 选择普通寄存器而非波特率除数锁存器 |

这些是 QEMU UART 寄存器的语义；PTY 和主机串口配置不能代替真实 UART 电气层或波特率验证。

`uart.normal_access` 的条件是 `(LCR & 0x80) == 0x00`。结果包含 `execution_status: "ok"`、`result: "PASS"` 或 `"FAIL"`、`mask`、`expected` 和同一次读取的 `value`。**请求成功执行不等于诊断通过；PASS 只说明 DLAB 为零，不说明发送就绪、UART 全部正常或芯片整体健康。**

<a id="mcp-protocol"></a>

### 4. UART 通信协议与恢复规则

#### 请求正文与响应行

```text
请求：mcp <request_id> h\n
      mcp <request_id> r lcr\n
      mcp <request_id> r s\n
      mcp <request_id> t normal\n
      mcp <request_id> w s <expected> <desired>\n
成功：@ESH1 <request_id> OK <operation> [key=value...]\n
失败：@ESH1 <request_id> ERR <error_code>\n
```

| Shell 请求正文（不含 LF） | ASCII 字节数 | argv 项数 | 响应操作与含义 |
| :--- | :--- | :--- | :--- |
| `mcp <16位ID> h` | 22 | 3 | `HELLO`：设备识别 |
| `mcp <16位ID> r lcr` | 26 | 4 | `READ`：读取 `uart0.lcr` |
| `mcp <16位ID> r s` | 24 | 4 | `READ`：读取 `uart0.scr` |
| `mcp <16位ID> t normal` | 29 | 4 | `TEST`：执行 `uart.normal_access` |
| `mcp 0000000000000001 w s 00 a5` | 30 | 6 | `WRITE`：expected=`0x00`，requested=`0xa5` |

WRITE 的 expected / desired 必须各为**恰好两个小写十六进制字符，不带 `0x`**，不是自由 mask 写；固件仅接受 SCR 的全掩码 `0xff` 策略。主机 token 不在线缆上传输，而由主机校验、消耗后生成上述短请求。

- ID 固定为 16 个小写十六进制字符。主机在组装完 ID、前缀及所有参数后校验**最终正文**：仅可打印 ASCII，最多 31 字节、16 个 argv 项（含命令名），再追加且仅追加一个 LF；不允许控制字符、CRLF、截断或引号分组。
- 默认 `LINE_BUFF_SIZE=32`（为 NUL 留一字节）、`MAX_ARG_COUNT=16`。`mcp` 固件编译时拒绝 `LINE_BUFF_SIZE < 32` 或 `MAX_ARG_COUNT < 6`；没有容量自动协商，固件增大容量也不会让主机开放更长命令或更多参数。
- 响应继续使用 `@ESH1`，最大 **256 字节，包含 LF**，不是 Shell 输入容量。一次请求对应一个终结响应；同一连接只保持一个请求在途。可信 ID 的可解析语法错误可返回 `BAD_REQUEST`；不要期待无有效 ID 的输入收到关联响应。
- Shell 按空格解析，连续多个空格正常分隔参数；人可以使用 Tab 补全、历史、退格和 CR 提交，但机器命令正文禁止这些控制字节。固件整行拒绝溢出或未识别控制字符，不执行截断前缀；argv 解析和 Tab 补全也有界。
- UART 不再无日志：提示符、回显、启动 banner 都是正常现象。Shell 在命令输出前先发 LF，使响应从行首开始；日志不得伪装或注入以 `@ESH1` 开头的行，也不得插入响应行内部。
- 主机只在行首识别 `@ESH1`，忽略完整、可打印 ASCII 的其他行，不把提示符或回显本身当作错误。**所有接收行**均受 256 字节（含 LF）限制，并共用同一个绝对超时期限；超长、持续噪声或损坏输出仍可使请求失败。

以下相邻两行分别为请求和响应（省略提示符、回显和 banner），`<revision>` / `<digest>` 为占位符。数值仅为格式示例，最后两组是只读验证脚本的拒绝测试，不是 MCP 工具开放的操作：

```text
mcp 0000000000000001 h
@ESH1 0000000000000001 OK HELLO board=riscv64-virt fw=<revision> map=<digest> ops=READ,TEST,WRITE
mcp 0000000000000002 r lcr
@ESH1 0000000000000002 OK READ reg=uart0.lcr width=8 value=0x00
mcp 0000000000000003 t normal
@ESH1 0000000000000003 OK TEST test=uart.normal_access result=PASS reg=uart0.lcr width=8 value=0x00
mcp 0000000000000004 r s
@ESH1 0000000000000004 OK READ reg=uart0.scr width=8 value=0x00
mcp 0000000000000005 r lsr
@ESH1 0000000000000005 ERR UNKNOWN_REGISTER
mcp 0000000000000006 w x 00 00
@ESH1 0000000000000006 ERR UNKNOWN_REGISTER
```

下面仅说明经批准的 SCR 写入线缆格式，不是让 Agent 绕过 MCP token 的指令；直接串口写入仅限获准的自有专用 QEMU 测试。响应末尾的 `\n` 表示一个 LF，不发送字面反斜杠字符：

```text
mcp 0000000000000001 w s 00 a5\n
@ESH1 0000000000000001 OK WRITE reg=uart0.scr width=8 expected=0x00 requested=0xa5 before=0x00 value=0xa5 result=WRITTEN\n
```

| WRITE result | 固件样本关系 | 写入次数 / 主机 `write_attempted` |
| :--- | :--- | :--- |
| `PRECONDITION_FAILED` | `before != expected`，`value == before`（返回前置读值，未再写） | 0 / `false` |
| `VERIFY_FAILED` | `before == expected`，读回 `value != requested` | 尝试 1 次 / `true` |
| `WRITTEN` | `before == expected`，读回 `value == requested` | 尝试 1 次 / `true` |

`OK WRITE` 只表示请求被处理，**必须检查 result**；前置比较不是多主机原子事务，外部访问仍可能在比较后干扰。主机校验样本关系并返回实际样本和接收时间，不承诺写入值持续不变。任何失败或结果未知都不自动重试或回滚。

#### 错误与恢复

| 错误 | 层级及含义 |
| :--- | :--- |
| `BAD_REQUEST` | 固件：字段数或语法不符合要求，例如缺少写参数的 `w lcr` |
| `UNSUPPORTED_OP` | 固件：不支持该操作，例如 `x lcr`，不再是 `w` |
| `UNKNOWN_REGISTER` / `UNKNOWN_TEST` | 固件：符号名不在白名单中；`r lsr`、`w x 00 00` 均为 `UNKNOWN_REGISTER` |
| `ACCESS_DENIED` | 写策略不允许；例如 `w lcr 0 0` 先检查只读权限再解析数值。完整的 `w lcr 00 ff` 正文为 32 字节，会先被默认 Shell 长度检查拒绝 |
| `INVALID_ARGUMENT` / MCP 参数校验错误 | 主机：不允许的参数，未发送硬件操作 |
| `INVALID_CONFIRMATION` / `CONFIRMATION_EXPIRED` | 主机：token 无效/已用或过期，不发送 UART 写请求 |
| `HANDSHAKE_REQUIRED` | 主机：先调用 `get_device_info` |
| `INCOMPATIBLE_DEVICE` | 主机：板型、描述摘要或操作列表不匹配 |
| `BUSY` / `PORT_BUSY` | 主机：调用队列、请求锁或端口所有权争用 |
| `TIMEOUT` / `IO_ERROR` / `PROTOCOL_ERROR` | 主机：超时、串口失败或响应格式异常 |

主机默认超时为 1 秒，可通过 `--timeout` 调整；迟到且 ID 不匹配的响应不会延长等待期限。响应会校验操作名、必填字段、重复字段、寄存器名、数据宽度和数值格式；诊断的 PASS/FAIL 必须与同次读取值一致，WRITE 的 result 必须与 expected、requested、before、value 的关系一致。

发生超时、I/O 或协议错误后，会话及待执行写计划失效，不自动重试，也不让排队中的 READ/TEST/WRITE 自动握手。应先检查设备和连接，再显式调用 `get_device_info`；重新握手也会废弃旧 token，绝不隐式继续旧写计划。初次连接或错误后的重新同步在 HELLO 前只发送 Ctrl+C（字节 `0x03`）并清理接收缓冲，而不是发送 LF，以免提交串口中遗留的半条命令。正常固件 `ERR` 本身不使兼容会话失效，但会使待执行写计划失效。

Shell 的 Ctrl+C 仅取消**尚未提交的输入**，不能中断正在执行的命令处理函数；它是传输层的特殊重同步操作，不是普通命令正文可包含控制字符的许可。

**超时表示结果未知，不表示设备没有执行。** 主机超时或取消调用不会中断固件中的 MMIO 操作，已消耗的 token 不恢复；禁止自动重试、回滚或盲目重复写入。经检查重新握手后可以读取实际状态，但不能由后一次读值倒推出超时请求一定执行或未执行。当前固件也没有通用总线异常恢复或超时驱动框架。

<a id="mcp-build"></a>

### 5. 构建与启动

#### 环境准备

主机要求 Python 3.10+、venv、GNU Make、RISC-V GNU 工具链与 QEMU。Ubuntu 22.04 可按需安装下列软件包；安装会修改系统软件环境，应由使用者确认后执行：

```sh
sudo apt update
sudo apt install -y python3-venv python3-pip make \
  gcc-riscv64-linux-gnu g++-riscv64-linux-gnu \
  binutils-riscv64-linux-gnu qemu-system-misc
```

若使用已解包的本地工具链，先加载其环境，使 `riscv64-linux-gnu-gcc`、`g++`、`ld` 和 `qemu-system-riscv64` 可执行；不要依赖其他机器上的临时目录路径。

#### 推荐：构建 Shell 并通过 PTY 接入 MCP

以下命令均从项目根目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ./host
make -B -C examples/emulation/riscv-64
make -C examples/emulation/riscv-64 run QEMU_CONSOLE="-display none -monitor none -serial pty"
```

构建生成 `examples/emulation/riscv-64/shell.elf` / `shell.bin`，默认对象缓存位于该示例的 `objects/`，生成头文件为 `objects/rpc_board.h`。上述启动命令让 QEMU 使用 `-M virt -bios none -display none -monitor none -serial pty`，仅将同一 `shell.elf` 的 UART 重定向到 PTY，供 MCP Server 连接；这不是固件模式或构建选择。预期输出：

```text
char device redirected to /dev/pts/3 ...
```

记录实际 PTY 并保持 QEMU 运行。该路径可能随重启改变，`/dev/pts/3` 只是示例。

**历史版本迁移：** 旧版曾拆分产物，工作区可能残留 `shell-rpc.elf`、`objects/rpc` 和 `objects/shell`，但当前构建与启动不会选择它们，无需批量删除。迁移时先执行 `make -B -C examples/emulation/riscv-64`，再由使用者重启自己管理的 QEMU 与 MCP Server，核对新进程实际输出的 PTY；不要擅自停止其他进程。新主机不能与旧独立 `rpc_prompt()` 固件混用：旧请求 `@ESH1 <ID> HELLO` 无效，应发送 `mcp <ID> h`；`@ESH1` 仅保留为响应前缀。更新源码或重新生成 ELF 不会替换已运行的固件，也不会自动重启已有 Server。

**读写升级检查：** Qoder 已配置的 esh Server 可能仍在运行旧只读版本，不能仅凭配置存在认定六工具已经加载。若仍只有四工具，由使用者重建固件、重启自己管理的 QEMU 和 MCP Server、核对实际 PTY；本说明不代表已替你执行这些操作或验证了 Qoder UI。旧的 `ops=READ,TEST` 与 schema 2 描述不兼容。

#### MCP Server 启动方式

提供两种等价入口：

```sh
.venv/bin/esh-mcp --port /dev/pts/3
.venv/bin/python -m esh_mcp.server --port /dev/pts/3
```

这是 **stdio Server，不是交互式 Shell**。正常使用应让 Qoder 等 MCP 客户端启动并管理子进程；不要在另一个终端预先运行一份 Server，再让 Qoder 启动第二份。

`--baud` 默认 115200，`--timeout` 默认 1.0 秒。主机不接受网络串口 URL。一个 PTY 只交给一个客户端使用，不能同时连接验证脚本、Inspector、Qoder 或串口终端。

#### 人工 Shell：同一固件，在启动终端交互

```sh
make -C examples/emulation/riscv-64
make -C examples/emulation/riscv-64 run
```

默认 `run` 使用 `-nographic`，可在启动终端输入 `help`、`history`、普通命令和完整的 `mcp` 短命令。它与 MCP 使用同一份 `shell.elf`，始终包含 `mcp`；选择启动终端或 PTY **只改变 QEMU 控制台参数，无需重建固件**。需要 PTY 时在该次 `run` 命令中显式传入上述带引号的 `QEMU_CONSOLE`；人工串口终端和 MCP Server 不能同时占用同一个 PTY。

`hello` 示例打印的 Ctrl+A、X 退出提示适用于 `-nographic`。PTY QEMU 应在其启动终端使用 Ctrl+C 停止；向 UART 发送 Ctrl+C（`0x03`）仅取消尚未提交的输入，不会退出 QEMU。停止或重启仅针对自己管理的进程；修改优化等级等编译选项或需要更新构建提交号时使用 `make -B` 强制重建。

<a id="mcp-qoder"></a>

### 6. Qoder / WSL 接入

**Qoder 可以直接连接 esh MCP，不需要 Inspector，也不需要 Node.js/npm。**

Qoder Desktop 的入口为 **Extensions → Connectors → Add Connector → Add custom MCP → JSON**；IDE 界面通常在 **Settings → MCP → My Servers → Add**。不同版本界面可能略有差异。

下面 JSON 只展示 esh 条目。已有其他 MCP 配置时应合并到 `mcpServers`，不要覆盖整个用户设置，也不需要关闭审批或增加全局自动授权。

#### Windows Qoder → WSL Server

先在 Windows PowerShell 查询发行版名称：

```powershell
wsl -l -q
```

以下为本项目 WSL 工作区的配置示例；将发行版、Linux 用户、项目绝对路径及 PTY 改为实际值：

```json
{
  "mcpServers": {
    "esh": {
      "command": "wsl.exe",
      "args": [
        "-d", "Ubuntu-22.04",
        "-u", "jeff",
        "--exec",
        "/mnt/f/open_source/esh/.venv/bin/python",
        "-m", "esh_mcp.server",
        "--port", "/dev/pts/3"
      ]
    }
  }
}
```

QEMU 与 Server 必须运行在同一个 WSL 发行版中，建议使用同一 Linux 用户。`wsl.exe` 将标准输入输出桥接到 WSL Python；只启动 Python MCP Server，不替你启动 QEMU。

#### MCP 启动器本身运行在 WSL

此时可直接执行 Linux Python，二选一配置，不要重复连接同一 PTY：

```json
{
  "mcpServers": {
    "esh": {
      "command": "/mnt/f/open_source/esh/.venv/bin/python",
      "args": [
        "-m", "esh_mcp.server",
        "--port", "/dev/pts/3"
      ]
    }
  }
}
```

不能仅凭“项目文件在 WSL”就推断 MCP 启动器也在 WSL。Windows 启动器不能直接执行 Linux 路径；若提示 `wsl.exe` 或 Python `ENOENT`，先确认启动位置和路径。

#### 连接成功的三个层次

1. **Server 已启动**：Qoder 能启动子进程，但这还不说明串口可访问。
2. **工具已加载**：当前对话能看到六个 esh 工具，包括 prepare/execute；仍只有四个时检查旧 Server，刷新连接或新开对话。
3. **设备链路成功**：实际调用 `get_device_info` 返回 `compatible: true`。

QEMU 重启且 PTY 改变时，更新 `--port` 并重新连接。只看到 Connector 已安装、后台存在进程或 Agent 文字声称“已连接”，都不能代替实际握手。

#### 项目 Skill：约束命令，不授予权限

项目级 [use-esh-shell Skill](.qoder/skills/use-esh-shell/SKILL.md) 要求 Agent 显式握手、限制 LCR/SCR 读取和 SCR 两阶段写入，展示预览并等待明确批准；同时确认运行固件容量、校验替换完成后的最终字符串，拒绝超长、过多参数及控制字符，不截断、不借用主机 Shell 的引号语义。已有 [validate_command.py](.qoder/skills/use-esh-shell/scripts/validate_command.py) 只校验，不发送或执行命令；例如在确认默认配置后从项目根目录执行：

```sh
python3 .qoder/skills/use-esh-shell/scripts/validate_command.py \
  --line-buffer-size 32 --max-arg-count 16 'mcp 0000000000000001 r lcr'
```

该正文为 26 字节、4 个 argv 项，校验通过；旧长形式 `mcp 0000000000000001 READ uart0.lcr` 为 35 字节，必须拒绝。外层单引号仅用于把完整正文交给主机端校验脚本，不会发送到 esh。

Skill 是 Agent 行为指导，主机和 Shell 内核的边界检查是运行时防护，**都不是硬件操作授权或固件沙箱**。固定 MCP 工具由 Server 再校验实际生成的短命令，不向 Agent 开放任意命令；Agent 不能声称已亲自检查不可见的线缆正文。用户要求只用 MCP 时不得为运行校验脚本而绕行终端或直接串口；保留审批，不更改用户权限设置。人工控制键与专用测试中的故意畸形输入不是正常 Agent 命令的许可。

<a id="mcp-validation"></a>

### 7. 人工验证、自动测试与排障

#### 第一步：验证 Shell 命令与 UART 响应

按[构建与启动](#mcp-build)用 `QEMU_CONSOLE="-display none -monitor none -serial pty"` 启动同一 `shell.elf`，记录实际 PTY；暂时断开 Qoder 的 esh Connector、Inspector 和其他串口客户端。以下 A、B 两种验证方式可任选其一，不能同时占用同一端口，不需要另选固件构建。

##### A. 在交互式 Shell 中逐条输入

用支持该 PTY 的串口终端连接 QEMU 输出的设备路径，设置 115200、关闭终端本地回显、使用 LF 发送行结束符。**PTY 启动时，命令输入位置是串口终端，不是显示 PTY 路径的 QEMU 启动终端，也不是 MCP Server 的标准输入。** 如果只做手工验证，也可按上节使用默认 `make -C examples/emulation/riscv-64 run`，直接在 `-nographic` 启动终端输入下列相同命令；方式 B 和 Qoder 接入则需要 PTY。

先逐条输入普通命令，确认 `help -l` 列表中有 `mcp`：

```text
help -l
hello mcp
history
```

再输入完整的设备识别命令；以下 ID 仅为人工示例，后续每个请求使用不同的 16 位小写十六进制 ID：

```text
mcp 0000000000000001 h
```

应看到带同一 ID 的 `@ESH1 ... OK HELLO` 响应。核对板型、`map` 描述摘要和 `ops=READ,TEST,WRITE` 与主机描述一致后，再逐条执行：

```text
mcp 0000000000000002 r lcr
mcp 0000000000000003 t normal
```

响应格式见[通信协议](#mcp-protocol)。命令正文分别为 22、26、29 字节，均在默认 31 字节限制内；不要输入提示符 `#`、引号或响应行。提示符、回显和响应并存是正常现象；单独输入 `mcp` 不会显示用法，应通过 `help` 查看命令说明。手工方式不会自动完成主机的兼容性与响应校验，不确定时改用方式 B；不要猜测缺失的响应或盲目重发。

结束后先关闭串口终端，再运行脚本或连接 Qoder。若终端无法打开 WSL1 PTY，可使用下面已处理 PTY 锁限制的脚本验证，不要删除锁文件或让多个客户端争用端口。

##### B. 用脚本校验并显示实际收发

保持 QEMU 运行，在另一个 WSL 终端、项目根目录执行：

```sh
.venv/bin/python verify_serial.py --port /dev/pts/3
```

也可通过环境变量指定端口：

```sh
export ESH_PORT=/dev/pts/3
.venv/bin/python verify_serial.py
```

根目录的 [verify_serial.py](verify_serial.py) **保持只读，没有可选写入开关**。它发送与主机相同的短 Shell 命令：`mcp <ID> h`、`mcp <ID> r lcr`、`mcp <ID> t normal`，以及应被拒绝的 `mcp <ID> r lsr`、`mcp <ID> w x 00 00`；后者针对不存在的寄存器，不能产生有效写入。不要再期待 `w lcr` 返回旧版的 `UNSUPPORTED_OP`，它因参数不完整返回 `BAD_REQUEST`；未知操作示例 `x lcr` 才返回 `UNSUPPORTED_OP`。

脚本使用主机的端口锁和命令校验，打印实际 TX/RX，将提示符、回显和 banner 等 Shell 行显示出来但不当作响应；握手不兼容时不继续读取，超时或传输/协议错误后停止。它检查响应字段、诊断与读值的一致性及预期拒绝码；异常、不兼容或诊断 FAIL 返回非零退出码。预期的拒绝响应不等于脚本故障，验证通过也只涵盖这些有限检查，不证明 SCR 写入成功。

| 检查项 | 预期 |
| :--- | :--- |
| HELLO | `OK HELLO`，板型为 `riscv64-virt`，含 `fw` 和 `map` |
| READ LCR | `OK READ reg=uart0.lcr width=8 value=0x..` |
| TEST | 正常 QEMU 初始状态应为 `result=PASS` |
| `r lsr` 拒绝测试 | `ERR UNKNOWN_REGISTER` |
| `w x 00 00` 拒绝测试 | `ERR UNKNOWN_REGISTER`，零次写入 |
| 帧关联 | `@ESH1` 响应从行首开始，ID 与请求一致；提示符、回显和日志在其他行是正常现象 |

#### 第二步：验证 Qoder 工具与自然语言解释

关闭人工串口终端或等待验证脚本退出释放端口后，连接 Qoder 的 esh MCP。人工执行过 `mcp <ID> h` 不会建立新 MCP Server 的握手状态，仍须先调用 `get_device_info`。可以发送：

> 请只使用 esh MCP，不要执行终端命令。先调用 get_device_info；确认 compatible 为 true 后，读取 uart0.lcr 并解释各位域，最后执行 uart.normal_access。请展示实际工具返回值，不要把 PASS 解释为芯片整体健康。

检查实际调用及返回值，而不是只看 Agent 的总结。读取两个 MCP 资源，核对位域说明、SCR 写策略与诊断边界。若 Agent 报告没有 esh 工具，应先检查对话工具可见性，不要让它用终端脚本替代这一步的 MCP 验证。

#### 自有专用 QEMU 的两阶段写入提示词

以下仅用于使用者自己管理的专用 QEMU，不用于共享硬件或尚未审查的实板。先完成上述重建、重启和 PTY 核对；等待用户批准时若超过 60 秒，必须重新预览、重新批准。

**阶段 1：只准备，然后停止。**

> 请只使用 esh MCP，不执行终端命令。这是我自己的专用 QEMU 测试实例，不是共享硬件。先调用 get_device_info；只有 compatible 为 true 且支持 READ,TEST,WRITE 时，读取 uart0.lcr 和 uart0.scr，执行 uart.normal_access，并调用 prepare_register_write，参数为 {"register":"uart0.scr","value":165}。请原样展示全部写预览字段（包括 expected、requested、board、manifest_digest、write_policy、token 和有效期），解释将只写 SCR，并明确请求我批准该预览。到这里停止，不调用 execute，不把这个实验请求视为写入批准。

**阶段 2：用户检查实际预览后，明确批准。**

> 我明确批准上一条实际预览中的 uart0.scr 写入（requested=0xa5），仅限其中的板型、描述摘要和 expected。请使用那次 prepare 实际返回且仍有效的 confirmation_token 调用 execute_register_write 一次，保留 Qoder 审批。展示实际 result、before、value、write_attempted 和时间戳；只有明确返回 WRITTEN 后，再用 read_register 读取 uart0.scr，区分执行读回与这次后续读取。若 token 过期、无效、结果失败、取消或超时，停止并报告，不自动重新准备并执行、不重试、不回滚。

第二段必须由用户在看到真实预览后发出，Agent 不得代替用户生成批准。两阶段须使用同一个仍存活的 MCP Server/设备客户端；重启 Server 或分别启动两个一次性 CLI 会话不能延续内存中的 token。保留 destructive 工具注解及 Qoder 审批；这些提示词不构成已进行实际 Qoder UI 测试的声明。

可选异常验证（仅限获准的自有专用 QEMU）：

- 新 Server 尚未握手时直接读 LCR，应返回 `HANDSHAKE_REQUIRED`。
- 输入 `uart0.lsr` 或裸地址，应在 MCP 参数校验或主机白名单层被拒绝；固定参数下拉框限制输入也属于预期。
- 停止测试用 QEMU 后再次读取，应返回 I/O 错误或超时，不能伪造成功值；后续读取需要重新握手。
- 恢复 QEMU、核对 PTY 并重新连接后，先调用 `get_device_info`，不要自动重复失败操作。

#### 可选：MCP Inspector

Inspector 只是 MCP 调试客户端，不是链路必需组件。若希望在浏览器中手动调用工具，可在具有 npm/npx 的环境运行：

```sh
npm view @modelcontextprotocol/inspector version engines --json
npx -y @modelcontextprotocol/inspector \
  /mnt/f/open_source/esh/.venv/bin/esh-mcp --port /dev/pts/3
```

首次运行会下载软件包；先确认当前 Node.js 满足返回的 `engines`，不要假定 Qoder 内置 Node 包含 npm 或满足最新版要求。以上命令须在能执行 Linux Python、访问该 PTY 的环境中运行。浏览器按终端提示打开本地页面并使用其连接信息；没有自动打开浏览器时可手动打开，不要为了排障关闭认证或将服务暴露到公网。Inspector 与 Qoder 不得同时占用该串口。

#### 自动化回归

从项目根目录执行，确保工具链和 QEMU 在 PATH 中：

```sh
.venv/bin/python -m unittest discover -s host/tests -v
.venv/bin/python tests/test_manifest.py
make -B -C examples/emulation/riscv-64
.venv/bin/python tests/test_qemu_mcp.py
```

- 主机测试覆盖短命令最终校验、Shell 行过滤、响应解析、错误响应、超时、迟到 ID、Ctrl+C 重同步、兼容性拒绝、队列上限、取消和 PTY 所有权。
- 描述生成测试覆盖摘要一致性与受限访问定义。
- 回归只需构建一次。QEMU 集成测试仅使用 `shell.elf`，自行启动/停止专用进程，在同一固件上验证普通 Shell 命令、输入边界与恢复及真实 MCP stdio 工具/资源调用。故意发送超长或畸形输入仅用于自有测试进程的负向测试，不是日常 Agent 操作。
- 可设置 `ESH_QEMU` 指定集成测试使用的 QEMU 可执行文件；它不同于 Makefile 的 `QEMU` 变量。

读写升级的验收还应核对：prepare 零写入、三种 WRITE result 与实际样本一致、前置值改变时零写入、token 过期/重放/重新握手失效、超时或取消后无自动重试；仅在获准的专用 QEMU/主机模拟测试中进行。此处列出的是验证要求，不声明本次测试通过数或 Qoder UI 已实测。

通过 QEMU 测试不代表真实 IC 已验证；主机模拟响应中的 FAIL 分支测试，也不等于在真实设备上制造并验证了故障。

#### 常见问题

| 现象 | 优先检查 |
| :--- | :--- |
| `node` / `npm` 不存在，Inspector 启动失败 | Qoder 直连不需要它们；仅 Inspector 需要另备符合版本要求的 Node/npm |
| MCP 已配置，但当前对话没有六个工具 | 是否仍运行旧四工具 Server；由使用者重建/重启自有 QEMU 和 Server，核对 PTY，刷新连接或新开对话 |
| `compatible: false` | 是否连接正确板型；固件与主机是否使用同一份描述；重建并重启 |
| `PORT_BUSY` | 验证脚本、旧 Server、Inspector 或另一个 Qoder 是否占用端口；断开自己启动的使用者，不要随意删除锁文件 |
| 串口不存在或打开失败 | QEMU 是否运行、PTY 是否变化、WSL 发行版与用户是否正确 |
| `PROTOCOL_ERROR` | 检查超长行、非可打印字符、损坏响应或伪装成 `@ESH1` 的日志；正常提示符/回显/banner 不算错误，修复后显式重新握手 |
| HELLO 超时或提示 `mcp` 未找到 | 当前示例的 Shell 始终包含 `mcp`；确认实际运行的是重建后的 `shell.elf`，由使用者重启自己管理的 QEMU 与 Server，核对实际 PTY 和 `--port`，排除旧固件或错误连接 |
| 手工输入 `mcp` 后没有响应 | 必须带完整 ID 和操作，例如 `mcp 0000000000000001 h`；裸 `mcp` 没有可信 ID，不输出结构化响应，用 `help` 查看用法 |
| 超时后反复 `HANDSHAKE_REQUIRED` | 先修复连接，再显式调用 `get_device_info`；由主机用 Ctrl+C 取消遗留输入，不用 LF 提交、不自动重试 |

<a id="mcp-roadmap"></a>

### 8. 安全约束与后续扩展

#### 当前约束

- 固件的 `mcp` 处理函数和固定主机 MCP 接口只允许已知操作及符号名；这不约束直接串口上的其他已注册 Shell 命令。读取也可能有副作用：例如 LSR 读取可能清除错误标志，因此不通过 MCP 开放；底层 UART 收发驱动仍会轮询 LSR，不能声称整个通信过程从不读取它。
- Shell 内核边界检查与 Skill 校验不构成授权，也不隔离其他串口客户端。Shell 会运行自动命令、`setup()`、空闲 `loop()`；实板适配必须审查这些钩子、平台初始化及全部命令的副作用。当前实现只验证 QEMU，不作物理芯片健康声明。
- Linux 普通串口使用 pyserial 排他锁；WSL1 PTY 不支持直接加锁，使用同用户、真实设备路径对应的普通文件锁协调 MCP Server。两者都不能阻止不遵守锁约定的程序或其他用户干扰。
- 打开串口前设置 DTR/RTS 为关闭，不把握手设计成复位操作；实际硬件和操作系统仍可能在打开端口时产生控制线瞬态，实板需另行验证。
- 协议没有 CRC、认证或加密，仅适合受控本地实验环境；请求 ID 和描述 SHA-256 不能替代这些能力。
- UART 驱动仍有同步等待，主机无法保证从非法 MMIO、设备挂死或所有硬件异常中恢复。
- Agent 应把设备值、描述和日志当作数据，不作为新的执行指令；保留工具调用审批，不开放自由 Shell 或任意地址访问。对写操作必须展示完整预览并等待用户明确批准，token 不能证明人类已批准；不得因 `stored_value_only` 而关闭 destructive 审批。
- SCR 受控写入不提供自动重试、回滚或跨客户端原子性。直接串口不经过 token，必须限制实验环境和串口访问；不要将 MCP 白名单、锁、Skill 或 token 称为沙箱或认证系统。

#### 后续可选方向（未实现）

当前不要求选择实板；先完善受控读写框架。QEMU SCR 的 prepare/execute 已是本阶段范围，后续是迁移和逐项审查，不是宣称通用插件已经完成。

| 阶段 | 建议范围 | 进入下一阶段前的验证 |
| :--- | :--- | :--- |
| 真实板卡适配 | 待用户选定板卡后，定义 UART 电气参数、初始化、可读寄存器与逐寄存器写策略 | 对照手册和独立调试器验证，先只读，再评审可写副作用；QEMU 6.2 证据不能代替芯片资料 |
| 更多寄存器/诊断 | 同步扩展固件白名单、主机工具 schema、位域描述和有界测试 | 明确读后清零、FIFO、W1C、保留位及非原子快照等语义，不套用 SCR 存储值策略 |
| 外部 IC | 新增板级 I²C/SPI 访问后端，明确事务与超时；当前无此后端或运行时 board-profile 参数 | 总线错误、设备缺失、访问副作用的测试 |
| 扩展受控写入 | 将预览、明确批准、前置比较与读回流程移植到经审查的目标，补充审计 | 验证真实副作用及结果未知场景；禁止自动重试、盲目重复和自动回滚 |
| 更复杂链路 | 视需要增加帧校验、身份认证或其他传输 | 校验只解决传输完整性，授权和错误恢复须单独验证 |

这些方向不改变 MVP 的验收原则：**展示实际设备返回值（区分 QEMU 与实板）、解释有明确依据、写前明确批准、遇到异常停止并报告不确定性。**

# Documentation

- To be able to run all the example and create your own project follow the documentation in [docs/](docs/index.md#table-of-contents).
- It also provides details about the internal workings of shell and how to setup your own project.

## Table of contents
| Topic| Description |
| :--- |:---        |
|[How shell Works](docs/shell-working.md)|Explains the working of shell with a flowchart.|
|[Running examples in `example/`](docs/00-setup-examples.md)|Guides on getting started with trying examples. Includes topics like - <br/> - `installing dependences`<br/> - `qemu based targets`<br/> - `physical board based targets`<br/> - `debugging` etc |
|[Setting up new project](docs/01-setting-up-new-project.md)|Details on how to start setting up a new project.|
|[Platform initialization and uart driver](docs/02-platform_init-and-uart-driver.md)|Details the implementation of the `platform_init()` and the relation to the uart driver.|
|[Uart driver](docs/03-uart-driver.md)| Describes implementation and constraint on the uart driver.|
|[User Linker Scripts](docs/04-user-linker-scripts.md)|Guides on how a liner script should be written if the user wants to manually set the memory layout and do the code placement.|
## Contributing

| Topic| Description |
| :--- |:----        |
| [Code of Conduct](docs/code-of-conduct.md) |Guides on the conduct expected while making contributions. |
|[Contributing](docs/contributing.md)|Guidelines on how to contribute to the code on GitHub.|

<hr>

# Source Code Headers

Every file containing source code must include copyright and license
information. This is to help well-intentioned people avoid accidental copying that
doesn't comply with the license.

Apache header:

    Copyright 2021 Google LLC
    
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
    
        https://www.apache.org/licenses/LICENSE-2.0
    
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
