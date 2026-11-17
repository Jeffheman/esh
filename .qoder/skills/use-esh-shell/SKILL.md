---
name: use-esh-shell
description: 在 esh 项目中通过串口或 MCP 生成、发送、检查 Shell 命令，或让 IC Agent 读取 LCR/SCR、诊断、准备和执行受控 SCR 写入时使用；显式握手，展示写预览并等待用户明确批准后使用一次性 token，禁止自动重试或回滚；按实际 LINE_BUFF_SIZE 和 MAX_ARG_COUNT 校验完整命令的 ASCII 字节数及参数项数，超限拒绝，不把响应容量当作输入容量。
---

# esh Shell 命令与受控读写约束

## 确认入口和实际限制

- 按框架优先的 IC Agent 目标工作：当前只针对 RISC-V QEMU `virt` 的受控 READ + WRITE，尚未选择实板。不要声称已有运行时 board-profile 参数、I²C/SPI 后端或完整通用芯片插件。
- 检查 Qoder 是否仍连接旧只读 Server；四工具旧连接不代表六工具读写已加载。让使用者重建并重启自己管理的 QEMU/Server、核对 PTY，不擅自执行或声称已经完成迁移。
- 先确认运行中的构建版本。当前 RISC-V QEMU 示例只有一种 Shell 固件 `shell.elf`，始终通过 `ADD_CMD(mcp, ...)` 注册 `mcp`；启动只走正常 `prompt()` / `shell()`，普通命令、`help`、`history` 与 MCP 共用同一固件。迁移旧版本时按 [README 构建与启动](../../../README.md#mcp-build)要求重建固件，由使用者重启自己管理的 QEMU 和 Server 并核对实际新 PTY，不混用新主机与旧固件，不擅自重启进程或批量删除旧产物。
- 从项目根目录的 `shell/shell/shell_config.h`、目标 Makefile 及编译宏确认运行中固件的 `LINE_BUFF_SIZE` 和 `MAX_ARG_COUNT`。不能仅根据源码默认值断定已烧录固件的限制；无法确认时停止直接发送并说明缺少的信息。
- 当前源码默认 `LINE_BUFF_SIZE=32`、`MAX_ARG_COUNT=16`。Shell 命令正文最多 31 个 ASCII 字节，为末尾 NUL 保留一个字节；参数项包含 `argv[0]` 命令名。`mcp` 固件编译时拒绝 `LINE_BUFF_SIZE < 32` 或 `MAX_ARG_COUNT < 6`。
- 不要套用响应的 256 字节（含 LF）容量。固定 MCP 主机校验最终正文最多 31 字节、16 个 argv 项；没有容量自动协商，也不因固件配置更大而向 Agent 开放更大容量。

## 构建与连接同一 Shell

仅在获准构建、启动时从项目根目录执行；MCP 推荐使用 PTY：

```sh
make -B -C examples/emulation/riscv-64
make -C examples/emulation/riscv-64 run QEMU_CONSOLE="-display none -monitor none -serial pty"
```

- 使用该示例生成的 `shell.elf` / `shell.bin`；默认对象缓存为 `objects/`，编译器始终包含生成的 `objects/rpc_board.h`，`platform/rpc` 源码始终参与构建。不要把 `rpc.c` 或 `RPC_*` 名称当作另一个固件构建。
- 将 QEMU 实际输出的 PTY 交给同一 WSL 发行版中的 Qoder MCP Server，不假定 `/dev/pts/3` 固定不变。让 Qoder 管理 stdio Server，不重复启动占用同一端口的 Server。

人工 Shell 使用相同固件：

```sh
make -C examples/emulation/riscv-64
make -C examples/emulation/riscv-64 run
```

- 默认 `run` 使用 `-nographic`，在启动终端交互；上述 `QEMU_CONSOLE` 只把同一固件的 UART 重定向到 PTY，不是固件模式或构建选择，选择终端或 PTY 无需重建。
- 仅在 `-nographic` 下使用 `hello` 打印的 Ctrl+A、X 退出提示。PTY QEMU 应在其启动终端用 Ctrl+C 停止；UART Ctrl+C 只取消未提交输入，不会退出 QEMU。不要擅自停止或重启用户进程。

## 校验最终发送内容

1. 先完成所有替换和编码，包括命令名、请求 ID、地址、数值、前缀及空格，再校验完整正文。
2. 仅生成可打印 ASCII，使用空格分隔参数。拒绝 TAB、ESC、退格、NUL、CR、LF 和非 ASCII；TAB 会触发交互补全，不能当作普通分隔符发送。
3. 不依赖引号、转义、变量展开或命令拼接。esh 按空格拆分参数，不具有主机 Shell 的引号语义；包含空格的字符串不能用引号包装成单个参数。
4. 直接发送前运行本 Skill 的 [scripts/validate_command.py](scripts/validate_command.py)，传入已确认的固件限制。脚本只做校验，不打开串口、不调用 MCP、不执行命令；固定 MCP 工具按下节流程使用主机内置校验，不绕行串口。
5. 仅在脚本退出码为 0 且 `valid` 为 `true` 时继续。必须发送与被校验内容完全相同的正文，传输层只追加一个 LF；不得用 CRLF 或再追加未计入长度的前缀。
6. 超长或参数过多时拒绝发送并报告实际值、上限。不要截断、拆包、删除参数、移除请求 ID 或自动拆成多条命令规避限制；更改命令设计后重新校验。

从项目根目录执行校验示例；32 和 16 仅用于已确认采用默认配置的目标：

```sh
python3 .qoder/skills/use-esh-shell/scripts/validate_command.py \
  --line-buffer-size 32 --max-arg-count 16 'help -l'
python3 .qoder/skills/use-esh-shell/scripts/validate_command.py \
  --line-buffer-size 32 --max-arg-count 16 'mcp 0000000000000001 r lcr'
```

第二条正文为 26 字节、4 个 argv 项。外层单引号只是主机端脚本传参，不是发送内容。脚本通过只表示字节和参数数量符合限制，不表示命令已注册、允许执行或硬件访问安全。esh 不支持引号分组，`echo "a b"` 会被计为三个参数项而不是两个；连续空格仍正常分隔参数，且每个空格计入长度。

固定主机使用以下实际短语法；把最终 16 位小写十六进制 ID 一并计入校验，不发送占位符：

| 正文示例（不含 LF） | 字节数 / argv 项数 | 对应响应 |
| :--- | :--- | :--- |
| `mcp 0000000000000001 h` | 22 / 3 | `HELLO` |
| `mcp 0000000000000002 r lcr` | 26 / 4 | `READ uart0.lcr` |
| `mcp 0000000000000003 t normal` | 29 / 4 | `TEST uart.normal_access` |
| `mcp 0000000000000004 r s` | 24 / 4 | `READ uart0.scr` |
| `mcp 0000000000000001 w s 00 a5` | 30 / 6 | `WRITE uart0.scr` |

将 WRITE 的 expected / desired 限定为各两个小写十六进制字符、不带 `0x`；`s` 是 SCR 别名。此表仅说明传输格式，不授权直接发送写请求。通过 MCP 时让主机用获批 token 绑定的预览生成正文，不手工替换 expected 或改走串口。

拒绝以下旧长形式：正文是 35 个 ASCII 字节，超过默认的 31 字节，而且不是当前短命令语法；不要截断后发送：

```text
mcp 0000000000000001 READ uart0.lcr
```

拒绝旧的 `@ESH1 <ID> HELLO` 请求；`@ESH1` 仅用于响应，不是 Shell 输入协议。不要把人用的 Tab 补全、历史、退格或 CR 提交当作机器正文许可。Shell 内核会整行拒绝溢出或未识别控制字符，并限制 argv 解析与 Tab 补全；这些检查不能代替发送前校验。

## 通过 MCP 使用设备

- 先检查实际工具 schema，确认六工具：`get_device_info`、`read_register`、`read_register_fields`、`run_named_test`、`prepare_register_write`、`execute_register_write`。保留原四个只读工具；两个读取工具仅允许 `uart0.lcr` / `uart0.scr`。不接受任意 Shell 字符串、LSR 或裸地址，不绕过 schema 改走终端/串口。
- 先显式调用 `get_device_info`，确认 `compatible: true`、板型、描述摘要和 `ops=READ,TEST,WRITE`；不隐式 HELLO。握手不兼容时停止硬件访问；保持 `uart.normal_access` 原定义不变。
- 核对 schema 2 清单：LCR 只读、别名 `lcr`；SCR 为 `0x10000007`（virt UART `0x10000000 + 7`）、8 位、别名 `s`，唯一写策略为 `{"mask":"0xff","effect":"stored_value_only","requires_expected":true}`。依据 [QEMU v6.2.0 serial.c](https://gitlab.com/qemu-project/qemu/-/raw/v6.2.0/hw/char/serial.c) 中写 `case 7` 仅设置 `s->scr`、读 `case 7` 返回该值；只把它作为 QEMU 6.2 证据，不推广为真实芯片保证。
- 读取两个无硬件访问的资源 `esh://board/registers` 和 `esh://board/tests` 了解定义；前者镜像 `write_policy`。不要将资源读取当作实际采样。
- 依赖 MCP Server 对最终短命令进行确定性校验并追加一个 LF。固定工具没有暴露完整线缆命令时，不编造正文，也不宣称 Skill 已检查内部传输帧。
- 用户要求只使用 MCP 时，不为运行校验脚本而执行终端命令；依赖工具自身的输入校验。如果接口没有可验证的边界校验，则停止，不改走其他通道。

### 严格执行 prepare → 用户批准 → execute

1. 仅在用户授权的自有专用 QEMU 实例上演示写入，不使用共享硬件或未审查实板。调用 `prepare_register_write` 时只传 `register: "uart0.scr"` 和严格整数 `value`（0..255，不接受 bool、浮点或字符串）；例如 `{"register":"uart0.scr","value":165}`。prepare 只读，不写硬件。
2. 原样展示全部实际预览：`register`、`width`、十六进制 `expected` / `requested`、`board`、`manifest_digest`、`write_policy`、由 32 个小写十六进制字符组成的 `confirmation_token`、`expires_in_seconds: 60`、UTC `expires_at`、`status: "prepared"`。明确说明目标和效果，**请求用户对这次预览的明确批准，然后停止**；不要把最初的实验目标当作批准。
3. 获得批准后才调用 `execute_register_write`，只传该预览实际返回且仍有效的 `confirmation_token`。不生成、修改或猜测 token；不代替用户批准。保留 Qoder 审批：prepare 注解为 `readOnlyHint=true`、`idempotentHint=false`；execute 为 `readOnlyHint=false`、`destructiveHint=true`、`idempotentHint=false`。不宣称实际测试了 Qoder 审批 UI。
4. 按每个设备客户端仅一个待执行计划处理。成功的新 prepare 替换旧计划；重新握手、固件 ERR、在途传输/协议错误或关闭清除计划。本地参数校验失败、无效 token 或未取得请求锁的 BUSY 不清除仍有效的计划，但也不授权继续执行。有效期按单调时钟为 60 秒，UTC 到期时间仅供展示。无效、过期、重放 token 不发送 UART 写请求；过期必须重新 prepare、展示新预览、重新请求批准，不自动续期执行。
5. 让主机在任何 UART 访问前消耗 token；固件读 `before`，比较 expected，不匹配时零写入；匹配时至多一次写入并读回。token 绑定预览，**不是人类批准认证或硬件权限凭据**，串口旁路也不受它约束。
6. 展示实际 `expected`、`requested`、`before`、`value`、`result`、`write_attempted` 布尔值及时间戳；不把 `OK WRITE` 解释为写成功。仅当 `WRITTEN` 后按批准流程再读 SCR，区分执行中的读回与后续采样。将接收时间解释为主机 UTC，不是设备采样时刻。

按以下关系解释 WRITE，不自行修补矛盾响应：

| result | 实际样本关系 | write_attempted |
| :--- | :--- | :--- |
| `PRECONDITION_FAILED` | `before != expected`，`value == before`，零写入 | `false` |
| `VERIFY_FAILED` | `before == expected`，`value != requested`，尝试一次写入 | `true` |
| `WRITTEN` | `before == expected`，`value == requested`，尝试一次写入 | `true` |

使用此响应作为格式示例，不声称它是本次实测；末尾 `\n` 表示 LF：

```text
@ESH1 0000000000000001 OK WRITE reg=uart0.scr width=8 expected=0x00 requested=0xa5 before=0x00 value=0xa5 result=WRITTEN\n
```

遵循 [README 两阶段 MCP 提示词](../../../README.md#mcp-validation)：阶段 1 明确要求 prepare 后停止，阶段 2 只能在用户看到真实预览并明确批准后使用返回的 token 执行及读回。不要将文档里的第二阶段示例当成用户已经批准。

### 保持恢复和诊断边界

- 独占串口，不与人工终端、Inspector 或其他 Server 并发发送。保留 pyserial 排他锁及 WSL1 PTY 上同用户、真实设备路径对应的普通文件锁；不删除锁文件绕过 `PORT_BUSY`，不声称锁能阻止不遵守约定的程序或其他用户。
- 超时、I/O、协议错误或取消后停止，不自动重试、回滚或盲目重复写入；已消耗 token 不恢复。确认连接后显式 `get_device_info`，不自动延续旧计划。将超时视为结果未知，不认定设备没有执行；后续读值也不能证明那次未知写一定执行或未执行。
- 将初次连接或错误后 HELLO 前的 Ctrl+C（`0x03`）交给主机传输层处理：只发送该字节并清理接收缓冲，不用 LF 提交遗留输入。它仅取消未提交的 Shell 输入，不能中断已运行的处理函数，不授权普通正文携带控制字节。
- 接受提示符、回显和 banner 的独立行；让主机仅从行首解析 `@ESH1`，校验 ID、操作和字段，忽略其他完整可打印 ASCII 行。所有行限 256 字节（含 LF），共享绝对超时期限；不伪装响应，遇到噪声、超长或损坏输出停止。
- 使用同次读取解释位域，不把多次调用当作原子快照；仅将 `uart.normal_access` 的 PASS 解释为 DLAB=0，不是发送就绪或芯片整体健康。不把长度校验通过当作写入授权，不声称验证了真实芯片或未经运行的测试。

## 说明约束边界

- 将本项目级 Skill 作为 Agent 行为规则，不作为内存安全防护、访问授权或固件沙箱。保留主机和 Shell 内核的边界检查，不声称 Skill 替代或实现了这些防护，不修改用户权限或审批设置。
- 区分固定 MCP 与直接串口：MCP 仅开放白名单读/诊断及两阶段 SCR 写，不提供任意执行；同一固件仍保留 `help`、`history` 等已注册命令。人工直接串口写请求绕过主机 token，只能在获准的自有专用测试中使用；用户限定 MCP 时绝不建议旁路，不声称 token 是认证或沙箱。
- 实板移植前审查 `initial_setup()` / `platform_init()`、自动命令、`setup()`、空闲 `loop()` 及全部命令的硬件副作用；只读工具也不表示整份固件无副作用。等待实际选板与资料审查后才制定真实寄存器写策略。
- 保持 [verify_serial.py](../../../verify_serial.py) 为只读人工验证入口，没有可选写入开关。仅在获准的自有专用测试环境执行负向检查：`r lsr`、`w x 00 00` 都应为 `UNKNOWN_REGISTER`，零写入；`w lcr` 因参数不足为 `BAD_REQUEST`，未知操作 `x lcr` 才为 `UNSUPPORTED_OP`。不要将拒绝测试当作正常 Agent 使用方式或绕过 MCP 限制。
