# 8====D~~~ diu9u Obfuscator v6.0 ~~~D====8

**English** | [中文](#中文版)

A Luau-compatible Lua obfuscator with **Bytecode VM**, **VM Nesting**, **Anti-Debug**, **Control Flow Flattening**, **25+ Fused Instructions**, **Operand Encoding**, **5-Mode Polymorphic Dispatch**, **Register Remapping**, **Constant Pool Splitting**, **GC Anti-Tamper**, **Dynamic Instruction Fusion**, **Steganographic Watermarking**, **LZSS Compression**, NSFW signature style, and zero dependencies.

Unlike Ironbrew 2, this obfuscator **natively supports Luau syntax** (`+=`, `continue`, `type`, if-then-else expressions, string interpolation, type annotations, etc.) and requires zero compilation — just Python 3.

> **Note:** The obfuscation engine is **closed-source**. This repository is a public showcase with obfuscated output examples. For access to the core engine, join the Discord: **discord.gg/BzDz9bmKDP**

---

## Features

| Pass | Description |
|------|-------------|
| **Bytecode VM** ⭐ | Full AST parser → custom bytecode compiler → VM interpreter generator. 67 opcodes, handler table splitting, control flow flattening, multi-round encryption, opaque predicates, decoy handlers |
| **Dynamic Instruction Fusion** ⭐ NEW | Runtime-generated compound opcodes beyond the static 25+ superoperators — unique fused sequences per build that don't exist in any opcode table |
| **25+ Fused Instructions** ⭐ | Static superoperators — common multi-instruction sequences merged into compound opcodes (LOADK+LOADK, GETGLOBAL+CALL, MOVE+RETURN, GETTABLE+GETTABLE, SETTABLE+LOADK, ADD+LOADK, EQ+JMP+LOADBOOL, and 18+ more) |
| **5-Mode Polymorphic Dispatch** ⭐ NEW | Five structurally different VM dispatch loop patterns randomly selected per build — while, recursive, repeat-until, and 2 additional hybrid modes |
| **Prototype Field Randomization** ⭐ | All prototype field names replaced with random names each build — defeats pattern matching |
| **Instruction Operand Encoding** ⭐ | Per-prototype random keys encode all instruction operands — no plaintext operands in instruction tables |
| **Register Remapping** ⭐ | Per-prototype random offset + local register permutation — register indices no longer correlate to source variable order |
| **Constant Pool Splitting** ⭐ | Constants scattered across 2-4 randomly-named sub-tables with redirect map — no single constant table to dump |
| **GC Anti-Tamper** ⭐ | `newproxy` sentinel with `__gc` metamethod monitors handler table integrity — silently corrupts execution if handlers are removed |
| **Helper Function Inlining** ⭐ | 40% of handlers randomly inline `gr`/`sr`/`rk` helper calls — breaks uniform call pattern matching |
| **Dual-Path Dispatch** ⭐ | Handlers split between table lookup and inline if-elseif branches in the main loop — reversers can't extract all handlers from the table alone |
| **VM Nesting** ⭐ | Multi-layer VM virtualization — VM output is re-compiled into another VM with independent opcode maps and encryption keys |
| **Anti-Debug** ⭐ | GC timing detection, debug library neutralization, callstack depth verification, environment integrity checks — silent corruption instead of crash |
| **Control Flow Flattening** ⭐ | State-machine dispatcher inside handler bodies — linearizes control flow, defeats pattern matching |
| **Multi-Round Encryption** ⭐ | 3-round XOR with per-round key derivation + byte rotation replaces simple XOR — each round uses a different derived key |
| **LZSS Compression** ⭐ NEW | Binary serialized bytecode is LZSS compressed before encryption — smaller output, additional layer of obfuscation |
| **Base91 Encoding** ⭐ NEW | Compressed+encrypted payload encoded in Base91 for safe Lua string embedding |
| **Opaque Predicates** ⭐ | Dead branches with mathematically false conditions injected inside handlers |
| **Handler Mutation** ⭐ | Equivalent instruction patterns randomized each build (`+1` → `+(2-1)`, `==0` → `<1`) |
| **String Encoding** ⭐ | VM internal string literals encoded with per-string XOR keys — no plaintext in output |
| **Steganographic Watermark** ⭐ NEW | Invisible fingerprinting baked into every build — invisible to decompilers, survives code reformatting |
| **Decoy Handlers** | Fake opcode handlers + 5-15 extra junk opcodes per build that look real but are never called |
| **Honeypot Code** | Fake anti-cheat remotes, fake ban functions, fake HTTP calls that never execute |
| **Anti-Deobfuscation Traps** | Environment integrity checks that crash non-Roblox runners |
| **Fingerprinting** | Unique per-build ID + SHA-256 hash for leak tracking |
| **Multi-Layer Wrapper** | Compressed+encrypted loadstring shell — stack multiple layers |
| **Decompiler Traps** ⭐ NEW | Specially crafted code patterns that crash or confuse Lua decompilers |
| **Whitespace Minification** | Compresses output to single-line |
| **Watermark** | Embeds a unique hash per build |

## Naming Styles

| Style | Example | Description |
|-------|---------|-------------|
| `ilI` | `lIl1Il`, `IlI1i1` | Classic obfuscator look |
| `nsfw` | `cock_senpai`, `balls_420`, `hentai_zone` | **The signature style.** 3000+ unique vulgar variable names + ASCII art + memes |
| `underscore` | `___1`, `____2` | Underscore spam |
| `hex` | `_1a`, `_2f` | Hex-based names |

## Access

The obfuscation engine is closed-source. This repo contains:
- `obfuscated/` — sample obfuscated outputs as showcase
- `obfuscate_scripts.py` — CLI stub (requires core engine)

For access to the core engine, join: **[discord.gg/BzDz9bmKDP](https://discord.gg/BzDz9bmKDP)**

## Usage (with core engine)

```bash
python obfuscator.py input.lua -o output.lua
python obfuscator.py input.lua --vm-layers 2 --junk-ops 20
python obfuscator.py input.lua --name-style ilI --no-traps
python obfuscator.py input.lua --target lua51
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--junk-ops` | `15` | Junk NOP instructions per prototype |
| `--vm-layers` | `1` | Nested VM layers (more = stronger, larger output) |
| `--name-style` | `nsfw` | Variable naming: `nsfw`, `ilI`, `underscore`, `hex` |
| `--seed` | — | Random seed for reproducible output |
| `--watermark` | `diu9u` | Embedded watermark text |
| `--no-traps` | — | Disable anti-deobfuscation traps |
| `--no-header` | — | Omit header comment |
| `--no-compress` | — | Skip compression wrapper |
| `--target` | `luau` | Target: `luau`, `lua51`, `lua52`, `lua53`, `lua54`, `luajit` |

## What Makes This Different

### 🧠 Bytecode VM
The strongest protection mode. Your Lua/Luau source is:
1. **Parsed** into an AST by a full recursive descent parser with Pratt expression parsing
2. **Compiled** to a custom **67-opcode** register-based instruction set (with upvalue/closure support, including 25+ fused superoperators + dynamic fusion)
3. **Serialized** to binary (varint/zigzag encoding), LZSS compressed, multi-round encrypted
4. **Wrapped** in a generated polymorphic Lua VM interpreter that executes the bytecode at runtime

The VM interpreter features:
- **67 opcodes** — 42 base + 25+ fused superoperators + dynamic fusion opcodes unique per build
- **Handler table splitting** — each opcode is a separate closure in a randomized table
- **Dual-path dispatch** — handlers split between table and inline if-elseif branches
- **5-mode polymorphic dispatch** — 5 structurally different loop patterns per build
- **Dynamic instruction fusion** — runtime-generated compound opcodes beyond static superoperators
- **25+ static fused instructions** — LOADK+LOADK, GETGLOBAL+CALL, MOVE+RETURN, EQ+JMP+LOADBOOL, GETTABLE+GETTABLE, SETTABLE+LOADK, ADD+LOADK, MOVE+CALL, and many more
- **Prototype field randomization** — all field names randomized, no fixed `proto.c`/`proto.k` in output
- **Instruction operand encoding** — per-prototype random offset keys, decoded at dispatch time
- **Register remapping** — per-prototype random offset + local permutation
- **Constant pool splitting** — constants scattered across 2-4 sub-tables with redirect indirection
- **GC anti-tamper** — `newproxy` sentinel with `__gc` checks handler table count
- **Helper function inlining** — 40% of handlers randomly inline helper calls
- **Control flow flattening** — multi-line handlers wrapped in state-machine dispatchers
- **Opaque predicates** — dead branches with always-false conditions
- **Handler code mutation** — equivalent expressions randomized each build
- **Multi-round encryption** — 3-round XOR with per-round derived keys + key derivation via salt/rotation/multiplication
- **LZSS compression** — binary bytecode compressed before encryption
- **Base91 encoding** — compact payload encoding for Lua string safety
- **String encoding** — VM internal strings encoded with per-string XOR keys
- **Per-prototype constant encryption** — XOR key per prototype, runtime decode on first load
- **Randomized opcodes** — opcode IDs shuffled every build + 5-15 extra junk opcodes
- **Decoy handlers** — fake handlers that look real but are never called
- **Decompiler traps** — code patterns that crash Lua decompilers
- **Anti-debug bootstrap** — 5 silent checks before VM execution (GC timing, debug library, environment, callstack, sentinel)

```
Source → [Tokenize] → [AST] → [Bytecode: 67 opcodes, registers, upvalues]
  → [Inject junk NOPs] → [Static fusion: 25+ superops] → [Dynamic fusion]
  → [Remap registers] → [Shuffle opcodes + add junk opcodes]
  → [Binary serialize (varint/zigzag)] → [LZSS compress] → [3-round XOR encrypt]
  → [Base91 encode] → [Control flow flatten decode pipeline]
  → [Generate handlers] → [Inline helpers] → [Flatten control flow]
  → [Inject opaque predicates] → [Mutate code patterns] → [Encode strings]
  → [Split dual-path dispatch] → [Select from 5 loop patterns] → [Add decoys]
  → [Inject anti-debug + decompiler traps] → Output: self-contained polymorphic Lua VM
```

### 🔒 VM Nesting (`--vm-layers N`)
The VM output is fed back through the compiler recursively. With 2 layers, the inner VM's Lua code runs inside an outer VM — the reverser must defeat **two independent VMs** with different opcode maps, handler layouts, and encryption keys.

### 🛡️ Anti-Debug
Five silent checks injected before VM bootstrap:
1. **GC timing** — `os.clock()` before/after `collectgarbage`, detects debugger pauses >0.5s
2. **Debug library neutralization** — inspects `debug.getinfo` for C-level callers
3. **Environment integrity** — verifies `string.byte`, `string.char`, `table.concat`, `type`, `tostring`, `loadstring` are real functions
4. **Callstack depth anomaly** — detects abnormal stack depth (>150 frames)
5. **Silent corruption** — instead of crashing, corrupts the XOR decryption key, causing cryptic failures later

This is much harder to bypass than a simple `error()` check — the reverser sees a random Lua error that doesn't point to the anti-debug code.

### 🍆 NSFW Mode
Every variable becomes a dick joke. `cock_senpai`, `balls_420`, `fap_vibes`, `rule34_bruh`. 3000+ unique names. Even the VM interpreter uses names like `wank_based`.

### 🍯 Honeypot Code
Fake anti-cheat calls that look real but never execute. Wastes reverser time investigating non-existent remotes.

### 🧅 Multi-Layer Wrapper
Each `--vm-layers` wraps the entire output in LZSS-compressed, multi-round encrypted bytecode. Each layer has independent opcode maps, register mappings, and encryption keys.

### 🪤 Anti-Deobfuscation Traps
Environment integrity checks that infinite-loop or crash outside Roblox.

### 🔍 Fingerprinting + Steganographic Watermark
Every build gets a unique UUID + SHA-256 hash for leak tracking. Watermarks are steganographically embedded and survive code reformatting.

### 📝 Luau Syntax Coverage
Full support for Luau-specific syntax:
- `continue` statement
- Compound operators (`+=`, `-=`, `*=`, `/=`, `%=`, `^=`, `..=`)
- `type` / `export type` declarations (skipped gracefully)
- Type annotations on locals, for-loops, function params/returns
- If-then-else expressions (Luau ternary: `if cond then val1 else val2`)
- Backtick string interpolation (decomposed to concatenation)
- Numeric literal underscores (`1_000_000`)

## REST API

The obfuscator includes a Flask-based REST API for programmatic access:

```bash
curl -X POST http://localhost:8080/api/v1/obfuscate \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"source": "print(42)", "options": {"name_style": "nsfw", "junk_ops": 15}}'
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/obfuscate` | POST | Obfuscate Lua source code |
| `/api/v1/info` | GET | Server info and supported options |
| `/api/v1/health` | GET | Health check |

## Comparison

| | **diu9u v6.0** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau Support | ✅ Full | ❌ | ✅ |
| Price | Free | Free | $8-30/mo |
| Dependencies | Python 3 | .NET SDK | Web |
| Bytecode VM | ✅ 67 opcodes | ✅ | ✅ |
| Fused Instructions | ✅ 25+ static + dynamic | ❌ | ✅ |
| Handler Table Splitting | ✅ | ❌ | ✅ |
| Dual-Path Dispatch | ✅ Table + inline | ❌ | ❌ |
| VM Loop Polymorphism | ✅ 5 modes | ❌ | ❌ |
| Dynamic Fusion | ✅ Per-build unique | ❌ | ❌ |
| Register Remapping | ✅ Offset + swap | ❌ | ✅ |
| Constant Pool Splitting | ✅ 2-4 sub-tables | ❌ | ✅ |
| GC Anti-Tamper | ✅ __gc sentinel | ❌ | ✅ |
| Operand Encoding | ✅ Per-prototype | ❌ | ✅ |
| Field Randomization | ✅ | ❌ | ✅ |
| Helper Inlining | ✅ 40% random | ❌ | ❌ |
| Control Flow Flattening | ✅ State-machine | ❌ | ✅ |
| VM Nesting | ✅ | ❌ | ✅ |
| Multi-Round Encryption | ✅ 3-round + key derivation | ❌ | ✅ |
| LZSS Compression | ✅ | ❌ | ❌ |
| Constant Encryption | ✅ Per-prototype | ❌ | ✅ |
| Anti-Debug | ✅ 5 checks | ❌ | ✅ |
| Opaque Predicates | ✅ In-handler | ❌ | ✅ |
| Handler Mutation | ✅ | ❌ | ❌ |
| String Encoding | ✅ Per-string key | ❌ | ✅ |
| Steganographic Watermark | ✅ | ❌ | ❌ |
| Decompiler Traps | ✅ | ❌ | ❌ |
| Decoy Handlers | ✅ | ❌ | ❌ |
| NSFW Mode | ✅ 8====D | ❌ | ❌ |
| Meme Strings | ✅ 80+ | ❌ | ❌ |
| Honeypot Code | ✅ | ❌ | ❌ |
| Anti-Deobf Traps | ✅ | ❌ | ✅ |
| REST API | ✅ | ❌ | ✅ |
| Strength | ★★★★★ | ★★★☆☆ | ★★★★★ |
| Fun Factor | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ |

## License

MIT — do whatever you want with it.

## Credits

Made by **diu9u** — if you're reading obfuscated code full of dick jokes, you've already lost.

Discord: **[discord.gg/BzDz9bmKDP](https://discord.gg/BzDz9bmKDP)**

---

<a id="中文版"></a>

# 8====D~~~ diu9u 混淆器 v6.0 ~~~D====8

[English](#8d-diu9u-obfuscator-v60-d8) | **中文**

兼容 Luau 的 Lua 混淆器，拥有 **字节码虚拟机**、**VM 嵌套**、**反调试**、**控制流平坦化**、**25+ 融合指令**、**操作数编码**、**5 模式多态调度**、**寄存器重映射**、**常量池分裂**、**GC 防篡改**、**动态指令融合**、**隐写术水印**、**LZSS 压缩**、NSFW 签名风格，零依赖。

与 Ironbrew 2 不同，本混淆器**原生支持 Luau 语法**（`+=`、`continue`、`type`、if-then-else 表达式、字符串插值、类型注解等），无需编译 — 只需 Python 3。

> **注意：** 混淆引擎为**闭源**。此仓库为公开展示，包含混淆后的输出示例。获取核心引擎请加入 Discord：**discord.gg/BzDz9bmKDP**

---

## 功能一览

| 功能 | 说明 |
|------|------|
| **字节码虚拟机** ⭐ | 完整 AST 解析器 → 自定义字节码编译器 → VM 解释器生成器。67 个操作码、Handler 表分裂、控制流平坦化、多轮加密、不透明谓词、诱饵处理器 |
| **动态指令融合** ⭐ 新功能 | 运行时生成的复合操作码，超越静态 25+ 超级操作码 — 每次构建产生任何操作码表中都不存在的独特融合序列 |
| **25+ 融合指令** ⭐ | 静态超级操作码 — 常见多指令序列融合为复合操作码（LOADK+LOADK、GETGLOBAL+CALL、MOVE+RETURN、EQ+JMP+LOADBOOL、GETTABLE+GETTABLE、SETTABLE+LOADK、ADD+LOADK 等 18+ 种） |
| **5 模式多态调度** ⭐ 新功能 | 五种结构不同的 VM 调度循环模式每次构建随机选择 — while、递归、repeat-until 及 2 种混合模式 |
| **原型字段名随机化** ⭐ | 所有原型字段名每次构建替换为随机名 — 击败模式匹配 |
| **指令操作数编码** ⭐ | 每个原型随机密钥编码所有指令操作数 — 指令表中无明文操作数 |
| **寄存器重映射** ⭐ | 每个原型随机偏移 + 局部置换 — 寄存器索引不再对应源码变量顺序 |
| **常量池分裂** ⭐ | 常量分散到 2-4 个随机命名的子表 + 重定向映射 |
| **GC 防篡改** ⭐ | `newproxy` 哨兵 + `__gc` 元方法监控 handler 表完整性 |
| **辅助函数内联** ⭐ | 40% 的 handler 随机内联辅助函数调用 — 打破统一调用模式 |
| **双路径调度** ⭐ | Handler 分布在表查找和主循环内联 if-elseif 分支之间 |
| **VM 嵌套** ⭐ | 多层 VM 虚拟化 — VM 输出重新编译为另一个 VM，独立操作码映射和加密密钥 |
| **反调试** ⭐ | GC 计时检测、debug 库中和、调用栈深度验证、环境完整性检查 — 静默破坏而非崩溃 |
| **控制流平坦化** ⭐ | Handler 内部状态机调度器 — 线性化控制流 |
| **多轮加密** ⭐ | 3 轮 XOR + 每轮密钥派生 + 字节旋转 |
| **LZSS 压缩** ⭐ 新功能 | 二进制序列化的字节码在加密前进行 LZSS 压缩 — 更小输出，额外混淆层 |
| **Base91 编码** ⭐ 新功能 | 压缩+加密后的载荷用 Base91 编码以安全嵌入 Lua 字符串 |
| **不透明谓词** ⭐ | 在 handler 内部注入数学上永远为假的死分支 |
| **Handler 变异** ⭐ | 每次构建随机化等价指令模式 |
| **字符串编码** ⭐ | VM 内部字符串用独立 XOR 密钥编码 |
| **隐写术水印** ⭐ 新功能 | 每次构建嵌入不可见指纹 — 反编译器不可见，代码重新格式化后仍然存在 |
| **诱饵处理器** | 伪操作码处理器 + 每次构建 5-15 个额外垃圾操作码 |
| **蜜罐代码** | 伪造反作弊远程调用、伪造封禁函数（永远不会执行） |
| **反反混淆陷阱** | 环境完整性检查，在非 Roblox 环境下崩溃 |
| **反编译器陷阱** ⭐ 新功能 | 特制代码模式使 Lua 反编译器崩溃或混乱 |
| **指纹追踪** | 每次构建唯一 ID + SHA-256 哈希 |

## 命名风格

| 风格 | 示例 | 说明 |
|------|------|------|
| `ilI` | `lIl1Il`, `IlI1i1` | 经典混淆器风格 |
| `nsfw` | `cock_senpai`, `balls_420`, `hentai_zone` | **招牌风格。** 3000+ 个独特名称 + ASCII art + meme |
| `underscore` | `___1`, `____2` | 下划线刷屏 |
| `hex` | `_1a`, `_2f` | 十六进制命名 |

## 获取

混淆引擎为闭源。此仓库包含：
- `obfuscated/` — 混淆后的输出示例展示
- `obfuscate_scripts.py` — CLI 入口（需要核心引擎）

获取核心引擎请加入：**[discord.gg/BzDz9bmKDP](https://discord.gg/BzDz9bmKDP)**

## 用法（需核心引擎）

```bash
python obfuscator.py input.lua -o output.lua
python obfuscator.py input.lua --vm-layers 2 --junk-ops 20
python obfuscator.py input.lua --name-style ilI --no-traps
python obfuscator.py input.lua --target lua51
```

## 核心特色

### 🧠 字节码虚拟机
最强保护模式。你的 Lua/Luau 源码会经历：
1. **解析** — 完整的递归下降解析器 + Pratt 表达式解析，生成 AST
2. **编译** — 编译为自定义 **67 操作码**寄存器式指令集（含 25+ 融合超级操作码 + 动态融合，支持 upvalue/闭包）
3. **序列化** — 二进制序列化（varint/zigzag 编码），LZSS 压缩，多轮加密
4. **包装** — 生成多态 Lua VM 解释器，在运行时执行字节码

```
源码 → [分词] → [AST] → [字节码: 67 操作码, 寄存器, upvalue]
  → [注入垃圾 NOP] → [静态融合: 25+ 超级操作码] → [动态融合]
  → [重映射寄存器] → [打乱操作码 + 添加垃圾操作码]
  → [二进制序列化 (varint/zigzag)] → [LZSS 压缩] → [3 轮 XOR 加密]
  → [Base91 编码] → [控制流平坦化解码管线]
  → [生成 handler] → [内联辅助函数] → [平坦化控制流]
  → [注入不透明谓词] → [变异代码模式] → [编码字符串]
  → [分裂双路径调度] → [5 种循环模式中随机选择] → [添加诱饵]
  → [注入反调试 + 反编译器陷阱] → 输出: 自包含多态 Lua VM
```

### 🔒 VM 嵌套 (`--vm-layers N`)
VM 输出递归重新编译。2 层时，内层 VM 的 Lua 代码在外层 VM 内执行 — 逆向者必须击败**两个独立的 VM**，各有不同的操作码映射、handler 布局和加密密钥。

### 🛡️ 反调试
VM 启动前注入 5 项静默检查：
1. **GC 计时** — `collectgarbage` 前后计时，检测调试器暂停 >0.5s
2. **debug 库中和** — 检查 `debug.getinfo` C 层调用者
3. **环境完整性** — 验证 `string.byte`、`table.concat`、`loadstring` 等是真实函数
4. **调用栈异常** — 检测异常栈深度（>150 帧）
5. **静默破坏** — 不崩溃，而是破坏 XOR 解密密钥，产生难以追踪的错误

### 🍆 NSFW 模式
每个变量都变成荤段子。`cock_senpai`、`balls_420`、`fap_vibes`、`rule34_bruh`。3000+ 个独特名称。连 VM 解释器都用 `wank_based` 这样的名字。

### 📝 Luau 语法覆盖
完整支持 Luau 特有语法：
- `continue` 语句
- 复合赋值运算符（`+=`、`-=`、`*=`、`/=`、`%=`、`^=`、`..=`）
- `type` / `export type` 声明
- 类型注解
- if-then-else 表达式（Luau 三元）
- 反引号字符串插值
- 数字下划线（`1_000_000`）

## 对比

| | **diu9u v6.0** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau 支持 | ✅ 完整 | ❌ | ✅ |
| 价格 | 免费 | 免费 | $8-30/月 |
| 字节码 VM | ✅ 67 操作码 | ✅ | ✅ |
| 融合指令 | ✅ 25+ 静态 + 动态 | ❌ | ✅ |
| Handler 表分裂 | ✅ | ❌ | ✅ |
| 双路径调度 | ✅ 表 + 内联 | ❌ | ❌ |
| VM 循环多态 | ✅ 5 种模式 | ❌ | ❌ |
| 动态融合 | ✅ 每次构建独特 | ❌ | ❌ |
| 寄存器重映射 | ✅ 偏移 + 置换 | ❌ | ✅ |
| 常量池分裂 | ✅ 2-4 子表 | ❌ | ✅ |
| GC 防篡改 | ✅ __gc 哨兵 | ❌ | ✅ |
| LZSS 压缩 | ✅ | ❌ | ❌ |
| 操作数编码 | ✅ 原型级 | ❌ | ✅ |
| 控制流平坦化 | ✅ 状态机 | ❌ | ✅ |
| VM 嵌套 | ✅ | ❌ | ✅ |
| 多轮加密 | ✅ 3 轮 + 密钥派生 | ❌ | ✅ |
| 反调试 | ✅ 5 项检查 | ❌ | ✅ |
| 隐写术水印 | ✅ | ❌ | ❌ |
| 反编译器陷阱 | ✅ | ❌ | ❌ |
| NSFW 模式 | ✅ 8====D | ❌ | ❌ |
| REST API | ✅ | ❌ | ✅ |
| 强度 | ★★★★★ | ★★★☆☆ | ★★★★★ |
| 趣味性 | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ |

## 许可证

MIT — 随便用。

## 致谢

由 **diu9u** 制作 — 如果你正在阅读满是荤段子的混淆代码，你已经输了。

Discord：**[discord.gg/BzDz9bmKDP](https://discord.gg/BzDz9bmKDP)**
