# 8====D~~~ diu9u Obfuscator v4.2 ~~~D====8

**English** | [中文](#中文版)

A Luau-compatible Lua obfuscator with **Bytecode VM**, **VM Nesting**, **Anti-Debug**, NSFW signature style, and zero dependencies.

Unlike Ironbrew 2, this obfuscator **natively supports Luau syntax** (`+=`, `continue`, `type`, if-then-else expressions, string interpolation, type annotations, etc.) and requires zero compilation — just Python 3.

---

## Features

| Pass | Description |
|------|-------------|
| **Bytecode VM** ⭐ | Full AST parser → custom bytecode compiler → VM interpreter generator. Handler table splitting, randomized opcodes, junk NOPs, XOR-encrypted prototypes, anti-debug, decoy handlers |
| **VM Nesting** ⭐ NEW | Multi-layer VM virtualization — VM output is re-compiled into another VM with independent opcode maps and encryption keys |
| **Anti-Debug** ⭐ NEW | GC timing detection, debug library neutralization, callstack depth verification, environment integrity checks — silent corruption instead of crash |
| **Decoy Handlers** ⭐ NEW | Fake opcode handlers that look real but are never called, confusing static analysis |
| **Comment Stripping** | Removes all single-line and multi-line comments |
| **String Encryption** | XOR encryption with random 32-byte key + runtime decoder |
| **Variable Renaming** | Local variable renaming with multiple styles (ilI, nsfw, hex, underscore) |
| **Number Obfuscation** | Replaces numeric literals with arithmetic expressions |
| **Junk Code Injection** | Dead branches with opaque predicates + 80+ meme/ASCII art strings |
| **Dispatch Tables** | Fake lookup tables to confuse static analysis |
| **Honeypot Code** | Fake anti-cheat remotes, fake ban functions, fake HTTP calls that never execute |
| **Anti-Deobfuscation Traps** | Environment integrity checks that crash non-Roblox runners |
| **Fingerprinting** | Unique per-build ID + SHA-256 hash for leak tracking |
| **Multi-Layer Wrapper** | XOR-encrypted loadstring shell — stack multiple layers |
| **Chunk-VM** | Splits code into individually encrypted chunks with a dispatch loop + dead chunks |
| **Metamethod Proxy** | Hides table access behind metatables with junk operations |
| **String VM** | Mini stack-based string decoder with randomized opcodes per build |
| **Whitespace Minification** | Compresses output to single-line |
| **Watermark** | Embeds a unique hash per build |

## Naming Styles

| Style | Example | Description |
|-------|---------|-------------|
| `ilI` | `lIl1Il`, `IlI1i1` | Classic obfuscator look (default) |
| `nsfw` | `cock_senpai`, `balls_420`, `hentai_zone` | **The signature style.** 3000+ unique vulgar variable names + ASCII art + memes |
| `underscore` | `___1`, `____2` | Underscore spam |
| `hex` | `_1a`, `_2f` | Hex-based names |

## Installation

```bash
git clone https://github.com/gary60182007/diu9u-obfuscator.git
cd diu9u-obfuscator
```

No dependencies — pure Python 3.

## Usage

```bash
# Basic obfuscation
python obfuscator.py input.lua -o output.lua

# NSFW mode
python obfuscator.py input.lua -o output.lua --name-style nsfw

# Bytecode VM (strongest protection — AST→bytecode→VM interpreter)
python obfuscator.py input.lua --bytecode-vm --name-style nsfw

# Bytecode VM + 2-layer VM nesting (VM inside VM)
python obfuscator.py input.lua --bytecode-vm --bytecode-vm-layers 2 --name-style nsfw

# Bytecode VM + loadstring layers (maximum protection)
python obfuscator.py input.lua --bytecode-vm --layers 2 --name-style nsfw

# Chunk-VM mode (split into encrypted chunks + dispatch)
python obfuscator.py input.lua --vm --name-style nsfw

# Maximum Chunk-VM: VM + 2 loadstring layers + high junk + 10 dead chunks
python obfuscator.py input.lua --vm --layers 2 --junk-density 0.15 --dead-chunks 10 --name-style nsfw

# Reproducible output with seed
python obfuscator.py input.lua --seed 42069 --name-style nsfw

# Disable specific passes
python obfuscator.py input.lua --no-encrypt --no-honeypots --no-traps
```

## All Options

```
positional arguments:
  input                    Input Lua/Luau file

options:
  -o, --output             Output file (default: <input>_obf.lua)
  --no-rename              Disable variable renaming
  --no-encrypt             Disable string encryption
  --no-junk                Disable junk code injection
  --no-numbers             Disable number obfuscation
  --no-minify              Disable whitespace minification
  --no-honeypots           Disable honeypot code injection
  --no-traps               Disable anti-deobfuscation traps
  --bytecode-vm            Enable Bytecode-VM (AST→bytecode→VM interpreter, strongest)
  --bytecode-vm-layers N   Number of nested VM layers (default: 1, each layer is independent)
  --bytecode-junk-ops N    Number of junk NOP instructions per prototype (default: 15)
  --vm                     Enable Chunk-VM (split into encrypted chunks + dispatcher)
  --dead-chunks N          Number of dead chunks in VM mode (default: 5)
  --layers N               Number of loadstring wrapper layers (default: 0)
  --seed N                 Random seed for reproducible output
  --watermark TEXT         Watermark text (default: diu9u)
  --junk-density FLOAT     Junk code density 0.0-1.0 (default: 0.05)
  --name-style STYLE       ilI | underscore | hex | nsfw
  --quiet                  Suppress stats output
```

## What Makes This Different

### 🧠 Bytecode VM (`--bytecode-vm`)
The strongest protection mode. Your Lua/Luau source is:
1. **Parsed** into an AST by a full recursive descent parser with Pratt expression parsing
2. **Compiled** to a custom 42-opcode register-based instruction set (with upvalue/closure support)
3. **Wrapped** in a generated Lua VM interpreter that executes the bytecode at runtime

The VM interpreter features:
- **Handler table splitting** — each opcode is a separate closure in a randomized table (no if-elseif chain)
- **Arithmetic/comparison sub-functions** — operations routed through randomized indirect call graph
- **Per-prototype constant encryption** — XOR key per prototype, runtime decode on first load
- **Randomized opcodes** — opcode IDs shuffled every build, extra junk opcodes added
- **Junk NOP injection** — fake instructions with correct jump offset fixups
- **XOR-encrypted prototype data** — loaded via `loadstring`
- **4-10 decoy handlers** — fake handlers that look real but are never called
- **Runtime integrity counter** — periodic type checks on handler table during execution

```
Source → [AST] → [Bytecode: 42 opcodes, registers, upvalues]
  → [Shuffle opcodes] → [Inject junk NOPs] → [XOR encrypt per-prototype]
  → [Generate handler table with decoys + sub-functions]
  → [Inject anti-debug checks] → Output: self-contained Lua VM
```

51KB source → 2.7MB output with `--bytecode-vm --name-style nsfw --layers 1`

### 🔒 VM Nesting (`--bytecode-vm-layers N`) — NEW
The VM output is fed back through the compiler recursively. With 2 layers, the inner VM's Lua code runs inside an outer VM — the reverser must defeat **two independent VMs** with different opcode maps, handler layouts, and encryption keys.

51KB → 3.9MB with `--bytecode-vm-layers 2 --name-style nsfw`

### 🛡️ Anti-Debug — NEW
Five silent checks injected before VM bootstrap:
1. **GC timing** — `os.clock()` before/after `collectgarbage`, detects debugger pauses >0.5s
2. **Debug library neutralization** — clears `debug.sethook()`, inspects `debug.getinfo` for C-level callers
3. **Environment integrity** — verifies `string.byte`, `string.char`, `table.concat`, `type`, `tostring`, `loadstring` are real functions
4. **Callstack depth anomaly** — detects abnormal stack depth (>150 frames)
5. **Silent corruption** — instead of crashing, corrupts the XOR decryption key, causing cryptic failures later

This is much harder to bypass than a simple `error()` check — the reverser sees a random Lua error that doesn't point to the anti-debug code.

### 🖥️ Chunk-VM (`--vm`)
Splits the entire script into individually encrypted chunks, each with its own XOR key and random ID. A dispatch loop decrypts and executes them in order via `loadstring()`. Dead chunks (fake encrypted junk code) are mixed in to waste reverser time. This is **statement-level virtualization** — the reverser must decrypt every chunk individually to reconstruct the original flow.

```
Source → [chunk_38291] [chunk_71045] [chunk_55823] [DEAD_99281] [chunk_12440] [DEAD_67102] ...
           ↓ XOR key A   ↓ XOR key B   ↓ XOR key C   (never runs)   ↓ XOR key D   (never runs)
```

### 🧮 String VM
A mini stack-based virtual machine with **randomized opcodes per build** (PUSH, XOR, CONCAT, REVERSE). Strings are decoded through VM instruction sequences instead of simple XOR. Each build gets different opcode values, so generic deobfuscators can't pattern-match the decoder.

### 🔮 Metamethod Proxy
Injects tables wrapped in metatables (`__index`, `__newindex`) with junk operations. Confuses static analysis tools that try to track table accesses.

### 🍆 NSFW Mode
Every variable becomes a dick joke. `cock_senpai`, `balls_420`, `fap_vibes`, `rule34_bruh`. 3000+ unique names. Even the VM interpreter uses names like `wank_based`.

### 🎭 Meme Junk Strings
Dead code contains strings like:
- `"8====D~~~"`
- `"stop skidding lmaooo"`
- `"deobfuscate this and ur gf leaves u"`
- `"L + ratio + you fell off"`
- `"never gonna give you up never gonna let you down"`

### 🍯 Honeypot Code
Fake anti-cheat calls that look real but never execute. Wastes reverser time investigating non-existent remotes.

### 🧅 Multi-Layer Wrapper
Each `--layers` wraps the entire output in XOR-encrypted `loadstring()`. Stack with `--bytecode-vm` or `--vm` for maximum pain.

### 🪤 Anti-Deobfuscation Traps
Environment integrity checks that infinite-loop or crash outside Roblox.

### 🔍 Fingerprinting
Every build gets a unique UUID + SHA-256 hash for leak tracking.

### 📝 Luau Syntax Coverage
Full support for Luau-specific syntax:
- `continue` statement
- Compound operators (`+=`, `-=`, `*=`, `/=`, `%=`, `^=`, `..=`)
- `type` / `export type` declarations (skipped gracefully)
- Type annotations on locals, for-loops, function params/returns
- If-then-else expressions (Luau ternary: `if cond then val1 else val2`)
- Backtick string interpolation (decomposed to concatenation)
- Numeric literal underscores (`1_000_000`)

## Example Output

```
==================================================

  8====D~~~ diu9u Obfuscator v4.2 ~~~D====8

==================================================
  Original Size...................... 51385
  Naming Style....................... nsfw
  Strings Encrypted.................. 302
  Variables Renamed.................. 227
  Numbers Obfuscated................. 672
  Junk Blocks Injected............... 42
  Honeypots Injected................. 2
  String Vm.......................... enabled
  Metamethod Proxy................... enabled
  Anti Deobf Traps................... enabled
  Build Id........................... bac3c5860a3b
  Bytecode Vm........................ enabled
  Bytecode Junk Ops.................. 15
  Loadstring Layers.................. 1
  Output Size........................ 2735214
  Size Ratio......................... 5323.0%
==================================================
```

51KB → 2.7MB with Bytecode VM + Anti-Debug + NSFW + 1 loadstring layer.

## Comparison

| | **diu9u v4.2** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau Support | ✅ Full | ❌ | ✅ |
| Price | Free | Free | $8-30/mo |
| Dependencies | Python 3 | .NET SDK | Web |
| Bytecode VM | ✅ | ✅ | ✅ |
| Handler Table Splitting | ✅ | ❌ | ✅ |
| VM Nesting | ✅ | ❌ | ✅ |
| Constant Encryption | ✅ Per-prototype | ❌ | ✅ |
| Anti-Debug | ✅ 5 checks | ❌ | ✅ |
| Decoy Handlers | ✅ | ❌ | ❌ |
| NSFW Mode | ✅ 8====D | ❌ | ❌ |
| Meme Strings | ✅ 80+ | ❌ | ❌ |
| Honeypot Code | ✅ | ❌ | ❌ |
| Anti-Deobf Traps | ✅ | ❌ | ✅ |
| Multi-Layer Wrapper | ✅ | ❌ | ✅ |
| Fingerprinting | ✅ | ❌ | ✅ |
| Chunk-VM | ✅ | ❌ | ❌ |
| String VM | ✅ | ❌ | ❌ |
| Metamethod Proxy | ✅ | ❌ | ❌ |
| Strength | ★★★★★ | ★★★☆☆ | ★★★★★ |
| Fun Factor | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ |

## License

MIT — do whatever you want with it.

## Credits

Made by **diu9u** — if you're reading obfuscated code full of dick jokes, you've already lost.

---

<a id="中文版"></a>

# 8====D~~~ diu9u 混淆器 v4.2 ~~~D====8

[English](#8d-diu9u-obfuscator-v42-d8) | **中文**

兼容 Luau 的 Lua 混淆器，拥有 **字节码虚拟机**、**VM 嵌套**、**反调试**、NSFW 签名风格，零依赖。

与 Ironbrew 2 不同，本混淆器**原生支持 Luau 语法**（`+=`、`continue`、`type`、if-then-else 表达式、字符串插值、类型注解等），无需编译 — 只需 Python 3。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| **字节码虚拟机** ⭐ | 完整 AST 解析器 → 自定义字节码编译器 → VM 解释器生成器。Handler 表分裂、随机化操作码、垃圾 NOP、XOR 加密原型、反调试、诱饵处理器 |
| **VM 嵌套** ⭐ 新功能 | 多层 VM 虚拟化 — VM 输出重新编译为另一个 VM，独立操作码映射和加密密钥 |
| **反调试** ⭐ 新功能 | GC 计时检测、debug 库中和、调用栈深度验证、环境完整性检查 — 静默破坏而非崩溃 |
| **诱饵处理器** ⭐ 新功能 | 看起来像真的但永远不会被调用的假操作码处理器，干扰静态分析 |
| **注释剥离** | 移除所有单行和多行注释 |
| **字符串加密** | XOR 加密 + 随机 32 字节密钥 + 运行时解码器 |
| **变量重命名** | 局部变量重命名，支持多种风格（ilI、nsfw、hex、underscore） |
| **数字混淆** | 将数字字面量替换为算术表达式 |
| **垃圾代码注入** | 带不透明谓词的死代码分支 + 80+ 条 meme/ASCII art 字符串 |
| **调度表** | 伪造查找表以干扰静态分析 |
| **蜜罐代码** | 伪造反作弊远程调用、伪造封禁函数、伪造 HTTP 请求（永远不会执行） |
| **反反混淆陷阱** | 环境完整性检查，在非 Roblox 环境下崩溃 |
| **指纹追踪** | 每次构建唯一 ID + SHA-256 哈希，用于泄漏追踪 |
| **多层包装** | XOR 加密的 loadstring 外壳 — 可叠加多层 |
| **Chunk-VM** | 将代码拆分为独立加密的块 + 调度循环 + 死块 |
| **元方法代理** | 通过元表隐藏表访问，附带垃圾操作 |
| **字符串虚拟机** | 迷你栈式字符串解码器，每次构建使用随机操作码 |
| **空白压缩** | 将输出压缩为单行 |
| **水印** | 嵌入每次构建的唯一哈希 |

## 命名风格

| 风格 | 示例 | 说明 |
|------|------|------|
| `ilI` | `lIl1Il`, `IlI1i1` | 经典混淆器风格（默认） |
| `nsfw` | `cock_senpai`, `balls_420`, `hentai_zone` | **招牌风格。** 3000+ 个独特的粗俗变量名 + ASCII art + meme |
| `underscore` | `___1`, `____2` | 下划线刷屏 |
| `hex` | `_1a`, `_2f` | 十六进制命名 |

## 安装

```bash
git clone https://github.com/gary60182007/diu9u-obfuscator.git
cd diu9u-obfuscator
```

零依赖 — 纯 Python 3。

## 用法

```bash
# 基本混淆
python obfuscator.py input.lua -o output.lua

# NSFW 模式
python obfuscator.py input.lua -o output.lua --name-style nsfw

# 字节码虚拟机（最强保护 — AST→字节码→VM 解释器）
python obfuscator.py input.lua --bytecode-vm --name-style nsfw

# 字节码虚拟机 + 2层 VM 嵌套（VM 套 VM）
python obfuscator.py input.lua --bytecode-vm --bytecode-vm-layers 2 --name-style nsfw

# 字节码虚拟机 + loadstring 层（极致保护）
python obfuscator.py input.lua --bytecode-vm --layers 2 --name-style nsfw

# Chunk-VM 模式（拆分加密块 + 调度）
python obfuscator.py input.lua --vm --name-style nsfw

# 极致 Chunk-VM：VM + 2 层 loadstring + 高密度垃圾 + 10 个死块
python obfuscator.py input.lua --vm --layers 2 --junk-density 0.15 --dead-chunks 10 --name-style nsfw

# 使用种子生成可复现输出
python obfuscator.py input.lua --seed 42069 --name-style nsfw

# 禁用特定 pass
python obfuscator.py input.lua --no-encrypt --no-honeypots --no-traps
```

## 所有选项

```
位置参数:
  input                    输入 Lua/Luau 文件

选项:
  -o, --output             输出文件（默认: <input>_obf.lua）
  --no-rename              禁用变量重命名
  --no-encrypt             禁用字符串加密
  --no-junk                禁用垃圾代码注入
  --no-numbers             禁用数字混淆
  --no-minify              禁用空白压缩
  --no-honeypots           禁用蜜罐代码注入
  --no-traps               禁用反反混淆陷阱
  --bytecode-vm            启用字节码虚拟机（AST→字节码→VM 解释器，最强）
  --bytecode-vm-layers N   嵌套 VM 层数（默认: 1，每层独立）
  --bytecode-junk-ops N    每个原型中的垃圾 NOP 指令数（默认: 15）
  --vm                     启用 Chunk-VM（拆分加密块 + 调度器）
  --dead-chunks N          VM 模式中的死块数量（默认: 5）
  --layers N               loadstring 包装层数（默认: 0）
  --seed N                 随机种子，用于可复现输出
  --watermark TEXT         水印文字（默认: diu9u）
  --junk-density FLOAT     垃圾代码密度 0.0-1.0（默认: 0.05）
  --name-style STYLE       ilI | underscore | hex | nsfw
  --quiet                  隐藏统计输出
```

## 核心特色

### 🧠 字节码虚拟机 (`--bytecode-vm`)
最强保护模式。你的 Lua/Luau 源码会经历：
1. **解析** — 完整的递归下降解析器 + Pratt 表达式解析，生成 AST
2. **编译** — 编译为自定义 42 操作码寄存器式指令集（支持 upvalue/闭包）
3. **包装** — 生成一个 Lua VM 解释器，在运行时执行字节码

VM 解释器特点：
- **Handler 表分裂** — 每个操作码是随机化表中的独立闭包（无 if-elseif 链）
- **算术/比较子函数** — 操作通过随机化间接调用图路由
- **原型级常量加密** — 每个原型独立 XOR 密钥，首次加载时运行时解码
- **随机化操作码** — 每次构建操作码 ID 随机打乱 + 垃圾操作码
- **4-10 个诱饵处理器** — 看起来像真的但永远不会被调用
- **运行时完整性计数器** — 定期检查 handler 表类型

```
源码 → [AST] → [字节码: 42 操作码, 寄存器, upvalue]
  → [打乱操作码] → [注入垃圾 NOP] → [原型级 XOR 加密]
  → [生成 handler 表 + 诱饵 + 子函数]
  → [注入反调试检查] → 输出: 自包含 Lua VM
```

51KB 源码 → 2.7MB 输出（`--bytecode-vm --name-style nsfw --layers 1`）

### 🔒 VM 嵌套 (`--bytecode-vm-layers N`) — 新功能
VM 输出递归重新编译。2 层时，内层 VM 的 Lua 代码在外层 VM 内执行 — 逆向者必须击败**两个独立的 VM**，各有不同的操作码映射、handler 布局和加密密钥。

51KB → 3.9MB（`--bytecode-vm-layers 2 --name-style nsfw`）

### 🛡️ 反调试 — 新功能
VM 启动前注入 5 项静默检查：
1. **GC 计时** — `collectgarbage` 前后计时，检测调试器暂停 >0.5s
2. **debug 库中和** — 清除 `debug.sethook()`，检查 `debug.getinfo` C 层调用者
3. **环境完整性** — 验证 `string.byte`、`table.concat`、`loadstring` 等是真实函数
4. **调用栈异常** — 检测异常栈深度（>150 帧）
5. **静默破坏** — 不崩溃，而是破坏 XOR 解密密钥，产生难以追踪的错误

### 🖥️ Chunk-VM (`--vm`)
将整个脚本拆分为独立加密的块，每个块有自己的 XOR 密钥和随机 ID。调度循环通过 `loadstring()` 按顺序解密执行。死块（伪造的加密垃圾代码）混入其中浪费逆向者时间。这是**语句级虚拟化** — 逆向者必须逐个解密每个块才能还原原始逻辑。

### 🧮 字符串虚拟机
迷你栈式虚拟机，**每次构建使用随机操作码**（PUSH、XOR、CONCAT、REVERSE）。字符串通过 VM 指令序列解码，而非简单的 XOR。每次构建的操作码值不同，通用反混淆器无法模式匹配解码器。

### 🍆 NSFW 模式
每个变量都变成荤段子。`cock_senpai`、`balls_420`、`fap_vibes`、`rule34_bruh`。3000+ 个独特名称。连 VM 解释器都用 `wank_based` 这样的名字。

### 🍯 蜜罐代码
伪造的反作弊调用，看起来像真的但永远不会执行。浪费逆向者时间去调查不存在的远程事件。

### 🪤 反反混淆陷阱
环境完整性检查，在 Roblox 之外运行时会无限循环或崩溃。

### 🔍 指纹追踪
每次构建获得唯一 UUID + SHA-256 哈希，用于泄漏追踪。

### 📝 Luau 语法覆盖
完整支持 Luau 特有语法：
- `continue` 语句
- 复合赋值运算符（`+=`、`-=`、`*=`、`/=`、`%=`、`^=`、`..=`）
- `type` / `export type` 声明（优雅跳过）
- 局部变量、for 循环、函数参数/返回值的类型注解
- if-then-else 表达式（Luau 三元：`if cond then val1 else val2`）
- 反引号字符串插值（分解为拼接）
- 数字下划线（`1_000_000`）

## 输出示例

```
==================================================

  8====D~~~ diu9u Obfuscator v4.2 ~~~D====8

==================================================
  Original Size...................... 51385
  Naming Style....................... nsfw
  Strings Encrypted.................. 302
  Variables Renamed.................. 227
  Numbers Obfuscated................. 672
  Junk Blocks Injected............... 42
  Honeypots Injected................. 2
  String Vm.......................... enabled
  Metamethod Proxy................... enabled
  Anti Deobf Traps................... enabled
  Build Id........................... bac3c5860a3b
  Bytecode Vm........................ enabled
  Bytecode Junk Ops.................. 15
  Loadstring Layers.................. 1
  Output Size........................ 2735214
  Size Ratio......................... 5323.0%
==================================================
```

51KB → 2.7MB，使用字节码 VM + 反调试 + NSFW + 1 层 loadstring。

## 对比

| | **diu9u v4.2** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau 支持 | ✅ 完整 | ❌ | ✅ |
| 价格 | 免费 | 免费 | $8-30/月 |
| 依赖 | Python 3 | .NET SDK | Web |
| 字节码 VM | ✅ | ✅ | ✅ |
| Handler 表分裂 | ✅ | ❌ | ✅ |
| VM 嵌套 | ✅ | ❌ | ✅ |
| 常量加密 | ✅ 原型级 | ❌ | ✅ |
| 反调试 | ✅ 5项检查 | ❌ | ✅ |
| 诱饵处理器 | ✅ | ❌ | ❌ |
| NSFW 模式 | ✅ 8====D | ❌ | ❌ |
| Meme 字符串 | ✅ 80+ | ❌ | ❌ |
| 蜜罐代码 | ✅ | ❌ | ❌ |
| 反反混淆陷阱 | ✅ | ❌ | ✅ |
| 多层包装 | ✅ | ❌ | ✅ |
| 指纹追踪 | ✅ | ❌ | ✅ |
| Chunk-VM | ✅ | ❌ | ❌ |
| 字符串 VM | ✅ | ❌ | ❌ |
| 元方法代理 | ✅ | ❌ | ❌ |
| 强度 | ★★★★★ | ★★★☆☆ | ★★★★★ |
| 趣味性 | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ |

## 许可证

MIT — 随便用。

## 致谢

由 **diu9u** 制作 — 如果你正在阅读满是荤段子的混淆代码，你已经输了。
