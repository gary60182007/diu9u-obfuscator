# 8====D~~~ diu9u Obfuscator v5.1 ~~~D====8

**English** | [中文](#中文版)

A Luau-compatible Lua obfuscator with **Bytecode VM**, **VM Nesting**, **Anti-Debug**, **Control Flow Flattening**, **Instruction Fusion**, **Operand Encoding**, **Dual-Path Dispatch**, **VM Polymorphism**, **Register Remapping**, **Constant Pool Splitting**, **GC Anti-Tamper**, NSFW signature style, and zero dependencies.

Unlike Ironbrew 2, this obfuscator **natively supports Luau syntax** (`+=`, `continue`, `type`, if-then-else expressions, string interpolation, type annotations, etc.) and requires zero compilation — just Python 3.

---

## Features

| Pass | Description |
|------|-------------|
| **Bytecode VM** ⭐ | Full AST parser → custom bytecode compiler → VM interpreter generator. Handler table splitting, control flow flattening, multi-round encryption, opaque predicates, decoy handlers |
| **Prototype Field Randomization** ⭐ NEW | All prototype field names (`c`, `k`, `p`, `np`, `va`, `mr`, `ck`, `uv`) replaced with random names each build — defeats pattern matching |
| **Instruction Operand Encoding** ⭐ NEW | Per-prototype random keys encode all instruction operands — no plaintext operands in instruction tables |
| **Instruction Fusion** ⭐ NEW | 10 superoperators — common 2-instruction sequences merged into compound opcodes (LOADK+LOADK, GETGLOBAL+CALL, MOVE+RETURN, MOVE+MOVE, LOADNIL+LOADNIL, NOT+JMPIF, GETTABLE+GETTABLE, LOADK+SETTABLE, LOADK+ADD) |
| **Register Remapping** ⭐ NEW | Per-prototype random offset + local register permutation — register indices no longer correlate to source variable order |
| **Constant Pool Splitting** ⭐ NEW | Constants scattered across 2-4 randomly-named sub-tables with redirect map — no single constant table to dump |
| **GC Anti-Tamper** ⭐ NEW | `newproxy` sentinel with `__gc` metamethod monitors handler table integrity — silently corrupts execution if handlers are removed |
| **Helper Function Inlining** ⭐ NEW | 40% of handlers randomly inline `gr`/`sr`/`rk` helper calls — breaks uniform call pattern matching |
| **Dual-Path Dispatch** ⭐ NEW | Handlers split between table lookup and inline if-elseif branches in the main loop — reversers can't extract all handlers from the table alone |
| **VM Main Loop Polymorphism** ⭐ NEW | 3 structurally different dispatch loop patterns (while, recursive, repeat-until) randomly selected per build |
| **VM Nesting** ⭐ | Multi-layer VM virtualization — VM output is re-compiled into another VM with independent opcode maps and encryption keys |
| **Anti-Debug** ⭐ NEW | GC timing detection, debug library neutralization, callstack depth verification, environment integrity checks — silent corruption instead of crash |
| **Control Flow Flattening** ⭐ NEW | State-machine dispatcher inside handler bodies — linearizes control flow, defeats pattern matching |
| **Multi-Round Encryption** ⭐ NEW | 3-round XOR with per-round key derivation replaces simple XOR — each round uses a different derived key |
| **Opaque Predicates** ⭐ NEW | Dead branches with mathematically false conditions injected inside handlers |
| **Handler Mutation** ⭐ NEW | Equivalent instruction patterns randomized each build (`+1` → `+(2-1)`, `==0` → `<1`) |
| **String Encoding** ⭐ NEW | VM internal string literals encoded with per-string XOR keys — no plaintext in output |
| **Decoy Handlers** | Fake opcode handlers that look real but are never called, confusing static analysis |
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
2. **Compiled** to a custom 52-opcode register-based instruction set (with upvalue/closure support, including 10 fused superoperators)
3. **Wrapped** in a generated Lua VM interpreter that executes the bytecode at runtime

The VM interpreter features:
- **Handler table splitting** — each opcode is a separate closure in a randomized table (no if-elseif chain)
- **Dual-path dispatch** — handlers split between table and inline if-elseif branches in the main loop
- **VM loop polymorphism** — 3 structurally different dispatch patterns (while/recursive/repeat-until) per build
- **Prototype field randomization** — all field names randomized, no fixed `proto.c`/`proto.k` in output
- **Instruction operand encoding** — per-prototype random offset keys, decoded at dispatch time
- **Instruction fusion** — 10 superoperators: LOADK+LOADK, GETGLOBAL+CALL, MOVE+RETURN, MOVE+MOVE, LOADNIL+LOADNIL, NOT+JMPIF/JMPIFNOT, GETTABLE+GETTABLE, LOADK+SETTABLE, LOADK+ADD
- **Register remapping** — per-prototype random offset + local permutation of singleton registers
- **Constant pool splitting** — constants scattered across 2-4 sub-tables with redirect indirection
- **GC anti-tamper** — `newproxy` sentinel with `__gc` checks handler table count, silently corrupts on tampering
- **Helper function inlining** — 40% of handlers randomly inline helper calls to break patterns
- **Control flow flattening** — multi-line handlers wrapped in state-machine dispatchers with shuffled states
- **Opaque predicates** — dead branches with always-false conditions injected between real statements
- **Handler code mutation** — equivalent expressions randomized each build (`~=0` → `>0`, `+1` → `+(2-1)`)
- **Multi-round encryption** — 3-round XOR with per-round derived keys (not simple single-pass XOR)
- **String encoding** — VM internal strings encoded with per-string XOR keys at build time
- **Arithmetic/comparison sub-functions** — operations routed through randomized indirect call graph
- **Per-prototype constant encryption** — XOR key per prototype, runtime decode on first load
- **Randomized opcodes** — opcode IDs shuffled every build, extra junk opcodes added
- **4-10 decoy handlers** — fake handlers that look real but are never called
- **Runtime integrity counter** — periodic type checks on handler table during execution

```
Source → [AST] → [Bytecode: 52 opcodes, registers, upvalues]
  → [Inject junk NOPs] → [Fuse instructions] → [Remap registers]
  → [Shuffle opcodes] → [Encode operands] → [Randomize field names]
  → [Split constant pool] → [3-round XOR encrypt]
  → [Generate handlers] → [Inline helpers] → [Flatten control flow]
  → [Inject opaque predicates] → [Mutate code patterns] → [Encode strings]
  → [Split dual-path dispatch] → [Select loop pattern] → [Add decoys]
  → [Inject anti-debug] → Output: self-contained polymorphic Lua VM
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

| | **diu9u v5.1** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau Support | ✅ Full | ❌ | ✅ |
| Price | Free | Free | $8-30/mo |
| Dependencies | Python 3 | .NET SDK | Web |
| Bytecode VM | ✅ 52 opcodes | ✅ | ✅ |
| Handler Table Splitting | ✅ | ❌ | ✅ |
| Dual-Path Dispatch | ✅ Table + inline | ❌ | ❌ |
| VM Loop Polymorphism | ✅ 3 patterns | ❌ | ❌ |
| Instruction Fusion | ✅ 10 superops | ❌ | ✅ |
| Register Remapping | ✅ Offset + swap | ❌ | ✅ |
| Constant Pool Splitting | ✅ 2-4 sub-tables | ❌ | ✅ |
| GC Anti-Tamper | ✅ __gc sentinel | ❌ | ✅ |
| Operand Encoding | ✅ Per-prototype | ❌ | ✅ |
| Field Randomization | ✅ | ❌ | ✅ |
| Helper Inlining | ✅ 40% random | ❌ | ❌ |
| Control Flow Flattening | ✅ State-machine | ❌ | ✅ |
| VM Nesting | ✅ | ❌ | ✅ |
| Multi-Round Encryption | ✅ 3-round derived | ❌ | ✅ |
| Constant Encryption | ✅ Per-prototype | ❌ | ✅ |
| Anti-Debug | ✅ 5 checks | ❌ | ✅ |
| Opaque Predicates | ✅ In-handler | ❌ | ✅ |
| Handler Mutation | ✅ | ❌ | ❌ |
| String Encoding | ✅ Per-string key | ❌ | ✅ |
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

# 8====D~~~ diu9u 混淆器 v5.1 ~~~D====8

[English](#8d-diu9u-obfuscator-v42-d8) | **中文**

兼容 Luau 的 Lua 混淆器，拥有 **字节码虚拟机**、**VM 嵌套**、**反调试**、**控制流平坦化**、**指令融合**、**操作数编码**、**双路径调度**、**VM 多态**、**寄存器重映射**、**常量池分裂**、**GC 防篡改**、NSFW 签名风格，零依赖。

与 Ironbrew 2 不同，本混淆器**原生支持 Luau 语法**（`+=`、`continue`、`type`、if-then-else 表达式、字符串插值、类型注解等），无需编译 — 只需 Python 3。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| **字节码虚拟机** ⭐ | 完整 AST 解析器 → 自定义字节码编译器 → VM 解释器生成器。Handler 表分裂、控制流平坦化、多轮加密、不透明谓词、诱饵处理器 |
| **原型字段名随机化** ⭐ 新功能 | 所有原型字段名（`c`、`k`、`p`、`np`、`va`、`mr`、`ck`、`uv`）每次构建替换为随机名 — 击败模式匹配 |
| **指令操作数编码** ⭐ 新功能 | 每个原型随机密钥编码所有指令操作数 — 指令表中无明文操作数 |
| **指令融合** ⭐ 新功能 | 10 个超级操作码 — 常见 2 指令序列融合为复合操作码（LOADK+LOADK、GETGLOBAL+CALL、MOVE+RETURN、MOVE+MOVE、LOADNIL+LOADNIL、NOT+JMPIF、GETTABLE+GETTABLE、LOADK+SETTABLE、LOADK+ADD） |
| **寄存器重映射** ⭐ 新功能 | 每个原型随机偏移 + 单例寄存器局部置换 — 寄存器索引不再对应源码变量顺序 |
| **常量池分裂** ⭐ 新功能 | 常量分散到 2-4 个随机命名的子表 + 重定向映射 — 无法一次性转储单个常量表 |
| **GC 防篡改** ⭐ 新功能 | `newproxy` 哨兵 + `__gc` 元方法监控 handler 表完整性 — 删除 handler 时静默破坏执行 |
| **辅助函数内联** ⭐ 新功能 | 40% 的 handler 随机内联 `gr`/`sr`/`rk` 辅助函数调用 — 打破统一调用模式 |
| **双路径调度** ⭐ 新功能 | Handler 分布在表查找和主循环内联 if-elseif 分支之间 — 逆向者无法仅从表中提取所有 handler |
| **VM 主循环多态** ⭐ 新功能 | 3 种结构不同的调度循环模式（while、递归、repeat-until）每次构建随机选择 |
| **VM 嵌套** ⭐ | 多层 VM 虚拟化 — VM 输出重新编译为另一个 VM，独立操作码映射和加密密钥 |
| **反调试** ⭐ 新功能 | GC 计时检测、debug 库中和、调用栈深度验证、环境完整性检查 — 静默破坏而非崩溃 |
| **控制流平坦化** ⭐ 新功能 | Handler 内部状态机调度器 — 线性化控制流，击败模式匹配 |
| **多轮加密** ⭐ 新功能 | 3 轮 XOR + 每轮密钥派生，替代简单 XOR — 每轮使用不同的派生密钥 |
| **不透明谓词** ⭐ 新功能 | 在 handler 内部注入数学上永远为假的死分支 |
| **Handler 变异** ⭐ 新功能 | 每次构建随机化等价指令模式（`+1` → `+(2-1)`、`==0` → `<1`） |
| **字符串编码** ⭐ 新功能 | VM 内部字符串用独立 XOR 密钥编码 — 输出中无明文 |
| **诱饵处理器** | 看起来像真的但永远不会被调用的假操作码处理器，干扰静态分析 |
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
2. **编译** — 编译为自定义 52 操作码寄存器式指令集（含 10 个融合超级操作码，支持 upvalue/闭包）
3. **包装** — 生成一个 Lua VM 解释器，在运行时执行字节码

VM 解释器特点：
- **Handler 表分裂** — 每个操作码是随机化表中的独立闭包（无 if-elseif 链）
- **双路径调度** — handler 分布在表和主循环内联 if-elseif 分支之间
- **VM 循环多态** — 3 种结构不同的调度模式（while/递归/repeat-until）每次构建随机选择
- **原型字段随机化** — 所有字段名随机化，输出中无固定 `proto.c`/`proto.k`
- **指令操作数编码** — 每个原型随机偏移密钥，调度时解码
- **指令融合** — 10 个超级操作码：LOADK+LOADK、GETGLOBAL+CALL、MOVE+RETURN、MOVE+MOVE、LOADNIL+LOADNIL、NOT+JMPIF/JMPIFNOT、GETTABLE+GETTABLE、LOADK+SETTABLE、LOADK+ADD
- **寄存器重映射** — 每个原型随机偏移 + 单例寄存器局部置换
- **常量池分裂** — 常量分散到 2-4 个子表 + 重定向间接访问
- **GC 防篡改** — `newproxy` 哨兵 + `__gc` 检查 handler 表数量，篡改时静默破坏
- **辅助函数内联** — 40% 的 handler 随机内联辅助调用以打破模式
- **控制流平坦化** — 多行 handler 用状态机调度器包装，状态随机打乱
- **不透明谓词** — 在真实语句之间注入永远为假的死分支
- **Handler 变异** — 每次构建随机化等价表达式（`~=0` → `>0`、`+1` → `+(2-1)`）
- **多轮加密** — 3 轮 XOR + 每轮派生密钥（非简单单次 XOR）
- **字符串编码** — VM 内部字符串用独立 XOR 密钥编码
- **算术/比较子函数** — 操作通过随机化间接调用图路由
- **原型级常量加密** — 每个原型独立 XOR 密钥，首次加载时解码
- **随机化操作码** — 每次构建操作码 ID 随机打乱 + 垃圾操作码
- **4-10 个诱饵处理器** — 看起来像真的但永远不会被调用
- **运行时完整性计数器** — 定期检查 handler 表类型

```
源码 → [AST] → [字节码: 52 操作码, 寄存器, upvalue]
  → [注入垃圾 NOP] → [融合指令] → [重映射寄存器]
  → [打乱操作码] → [编码操作数] → [随机化字段名]
  → [分裂常量池] → [3 轮 XOR 加密]
  → [生成 handler] → [内联辅助函数] → [平坦化控制流]
  → [注入不透明谓词] → [变异代码模式] → [编码字符串]
  → [分裂双路径调度] → [选择循环模式] → [添加诱饵]
  → [注入反调试] → 输出: 自包含多态 Lua VM
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

| | **diu9u v5.1** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau 支持 | ✅ 完整 | ❌ | ✅ |
| 价格 | 免费 | 免费 | $8-30/月 |
| 依赖 | Python 3 | .NET SDK | Web |
| 字节码 VM | ✅ 52 操作码 | ✅ | ✅ |
| Handler 表分裂 | ✅ | ❌ | ✅ |
| 双路径调度 | ✅ 表 + 内联 | ❌ | ❌ |
| VM 循环多态 | ✅ 3 种模式 | ❌ | ❌ |
| 指令融合 | ✅ 10 超级操作码 | ❌ | ✅ |
| 寄存器重映射 | ✅ 偏移 + 置换 | ❌ | ✅ |
| 常量池分裂 | ✅ 2-4 子表 | ❌ | ✅ |
| GC 防篡改 | ✅ __gc 哨兵 | ❌ | ✅ |
| 操作数编码 | ✅ 原型级 | ❌ | ✅ |
| 字段随机化 | ✅ | ❌ | ✅ |
| 辅助函数内联 | ✅ 40% 随机 | ❌ | ❌ |
| 控制流平坦化 | ✅ 状态机 | ❌ | ✅ |
| VM 嵌套 | ✅ | ❌ | ✅ |
| 多轮加密 | ✅ 3轮派生 | ❌ | ✅ |
| 常量加密 | ✅ 原型级 | ❌ | ✅ |
| 反调试 | ✅ 5项检查 | ❌ | ✅ |
| 不透明谓词 | ✅ Handler 内 | ❌ | ✅ |
| Handler 变异 | ✅ | ❌ | ❌ |
| 字符串编码 | ✅ 独立密钥 | ❌ | ✅ |
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
