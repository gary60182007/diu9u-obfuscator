# 8====D~~~ diu9u Obfuscator v4.0 ~~~D====8

A Luau-compatible Lua obfuscator with **Chunk-VM**, NSFW signature style, and zero dependencies.

Unlike Ironbrew 2, this obfuscator **natively supports Luau syntax** (`+=`, `continue`, string interpolation, etc.) and requires zero compilation — just Python 3.

## Features

| Pass | Description |
|------|-------------|
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

# VM mode (Chunk-VM + encrypted dispatch)
python obfuscator.py input.lua --vm --name-style nsfw

# Maximum protection: VM + 2 loadstring layers + high junk + 10 dead chunks
python obfuscator.py input.lua --vm --layers 2 --junk-density 0.15 --dead-chunks 10 --name-style nsfw

# Reproducible output with seed
python obfuscator.py input.lua --seed 42069 --name-style nsfw

# Disable specific passes
python obfuscator.py input.lua --no-encrypt --no-honeypots --no-traps
```

## All Options

```
positional arguments:
  input                 Input Lua/Luau file

options:
  -o, --output          Output file (default: <input>_obf.lua)
  --no-rename           Disable variable renaming
  --no-encrypt          Disable string encryption
  --no-junk             Disable junk code injection
  --no-numbers          Disable number obfuscation
  --no-minify           Disable whitespace minification
  --no-honeypots        Disable honeypot code injection
  --no-traps            Disable anti-deobfuscation traps
  --vm                  Enable Chunk-VM (split into encrypted chunks + dispatcher)
  --dead-chunks N       Number of dead chunks in VM mode (default: 5)
  --layers N            Number of loadstring wrapper layers (default: 0)
  --seed N              Random seed for reproducible output
  --watermark TEXT      Watermark text (default: diu9u)
  --junk-density FLOAT  Junk code density 0.0-1.0 (default: 0.05)
  --name-style STYLE    ilI | underscore | hex | nsfw
  --quiet               Suppress stats output
```

## What Makes This Different

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
Every variable becomes a dick joke. `cock_senpai`, `balls_420`, `fap_vibes`, `rule34_bruh`. 3000+ unique names. Even the VM dispatcher uses names like `wank_based`.

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
Each `--layers` wraps the entire output in XOR-encrypted `loadstring()`. Stack with `--vm` for maximum pain.

### 🪤 Anti-Deobfuscation Traps
Environment integrity checks that infinite-loop or crash outside Roblox.

### 🔍 Fingerprinting
Every build gets a unique UUID + SHA-256 hash for leak tracking.

## Example Output

```
==================================================

  8====D~~~ diu9u Obfuscator v4.0 ~~~D====8

==================================================
  Original Size...................... 51385
  Naming Style....................... nsfw
  Strings Encrypted.................. 302
  Variables Renamed.................. 227
  Numbers Obfuscated................. 672
  Junk Blocks Injected............... 56
  Honeypots Injected................. 4
  String Vm.......................... enabled
  Metamethod Proxy................... enabled
  Anti Deobf Traps................... enabled
  Build Id........................... b215e8565a3b
  Chunk Vm........................... enabled
  Dead Chunks........................ 5
  Loadstring Layers.................. 1
  Output Size........................ 853875
  Size Ratio......................... 1661.7%
==================================================
```

51KB → 854KB with VM + 1 layer. The reverser sees nothing but encrypted byte arrays.

## Comparison

| | **diu9u v4** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau Support | ✅ | ❌ | ✅ |
| Price | Free | Free | $8-30/mo |
| Dependencies | Python 3 | .NET SDK | Web |
| NSFW Mode | ✅ 8====D | ❌ | ❌ |
| Meme Strings | ✅ 80+ | ❌ | ❌ |
| Honeypot Code | ✅ | ❌ | ❌ |
| Anti-Deobf Traps | ✅ | ❌ | ✅ |
| Multi-Layer Wrapper | ✅ | ❌ | ✅ |
| Fingerprinting | ✅ | ❌ | ✅ |
| Chunk-VM | ✅ | ❌ | ❌ |
| String VM | ✅ | ❌ | ❌ |
| Metamethod Proxy | ✅ | ❌ | ❌ |
| Bytecode VM | ❌ | ✅ | ✅ |
| Strength | ★★★★☆ | ★★★☆☆ | ★★★★★ |
| Fun Factor | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ |

## License

MIT — do whatever you want with it.

## Credits

Made by **diu9u** — if you're reading obfuscated code full of dick jokes, you've already lost.
