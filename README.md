# 8====D~~~ diu9u Obfuscator v3.0 ~~~D====8

A Luau-compatible Lua obfuscator with a... *unique* signature style.

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
| **Multi-Layer Wrapper** | XOR-encrypted loadstring shell — stack multiple layers for maximum pain |
| **Whitespace Minification** | Compresses output to single-line |
| **Watermark** | Embeds a unique hash per build |

## Naming Styles

| Style | Example | Description |
|-------|---------|-------------|
| `ilI` | `lIl1Il`, `IlI1i1` | Classic obfuscator look (default) |
| `nsfw` | `cock_senpai`, `balls_420`, `hentai_zone` | **The signature style.** 3000+ unique vulgar variable names + ASCII art + memes scattered throughout |
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

# NSFW mode (recommended for maximum psychological damage)
python obfuscator.py input.lua -o output.lua --name-style nsfw

# Full protection: NSFW + 2 loadstring layers + high junk
python obfuscator.py input.lua --name-style nsfw --layers 2 --junk-density 0.15

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
  --layers N            Number of loadstring wrapper layers (default: 0)
  --seed N              Random seed for reproducible output
  --watermark TEXT      Watermark text (default: diu9u)
  --junk-density FLOAT  Junk code density 0.0-1.0 (default: 0.05)
  --name-style STYLE    ilI | underscore | hex | nsfw
  --quiet               Suppress stats output
```

## What Makes This Different

### 🍆 NSFW Mode
Every variable becomes a dick joke. `cock_senpai`, `balls_420`, `cum_daddy`, `hentai_zone`. 3000+ unique names.

### 🎭 Meme Junk Strings
Dead code contains strings like:
- `"8====D~~~"`
- `"stop skidding lmaooo"`
- `"deobfuscate this and ur gf leaves u"`
- `"L + ratio + you fell off"`
- `"imagine reading obfuscated code"`
- `"never gonna give you up never gonna let you down"`

### 🍯 Honeypot Code
Fake anti-cheat calls that look real but never execute:
```lua
do local cock69=game:GetService("ReplicatedStorage"):FindFirstChild("BanRemote");
if cock69 and (nil) then cock69:FireServer(game.Players.LocalPlayer.UserId) end end;
```
Wastes reverser time investigating fake remotes.

### 🧅 Multi-Layer Wrapper
Each `--layers` wraps the entire output in XOR-encrypted `loadstring()`. With 2 layers, the reverser has to decrypt twice before seeing any code. With NSFW mode, even the wrapper variables are `smegma_vibes` and `nut_hyper`.

### 🪤 Anti-Deobfuscation Traps
Integrity checks that infinite-loop or crash if the script runs outside Roblox (e.g., in a deobfuscator sandbox).

### 🔍 Fingerprinting
Every build gets a unique UUID + SHA-256 hash. If someone leaks your script, you can trace which build it came from.

## Example Output

```
==================================================

  8====D~~~ diu9u Obfuscator v3.0 ~~~D====8

==================================================
  Original Size...................... 51385
  Naming Style....................... nsfw
  Strings Encrypted.................. 302
  Variables Renamed.................. 227
  Numbers Obfuscated................. 672
  Junk Blocks Injected............... 36
  Honeypots Injected................. 3
  Anti Deobf Traps................... enabled
  Build Id........................... 35169e5bb167
  Loadstring Layers.................. 1
  Output Size........................ 219734
  Size Ratio......................... 427.6%
==================================================
```

## Comparison

| | **diu9u v3** | **Ironbrew 2** | **Luraph** |
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
| VM Obfuscation | ❌ | ✅ | ✅ |
| Strength | ★★★☆☆ | ★★★☆☆ | ★★★★★ |
| Fun Factor | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ |

## License

MIT — do whatever you want with it.

## Credits

Made by **diu9u** — if you're reading obfuscated code full of dick jokes, you've already lost.
