# 8====D~~~ diu9u Obfuscator v2.0 ~~~D====8

A Luau-compatible Lua obfuscator with a... *unique* signature style.

Unlike Ironbrew 2, this obfuscator **natively supports Luau syntax** (`+=`, `continue`, string interpolation, etc.) and requires zero compilation — just Python 3.

## Features

| Pass | Description |
|------|-------------|
| **Comment Stripping** | Removes all single-line and multi-line comments |
| **String Encryption** | XOR encryption with random 32-byte key + runtime decoder |
| **Variable Renaming** | Scope-aware local variable renaming with multiple styles |
| **Number Obfuscation** | Replaces numeric literals with arithmetic expressions |
| **Junk Code Injection** | Dead branches with opaque predicates + ASCII art strings |
| **Dispatch Tables** | Fake lookup tables to confuse static analysis |
| **Whitespace Minification** | Compresses output to single-line |
| **Watermark** | Embeds a unique hash per build |

## Naming Styles

| Style | Example | Description |
|-------|---------|-------------|
| `ilI` | `lIl1Il`, `IlI1i1` | Classic obfuscator look (default) |
| `nsfw` | `cock_senpai`, `balls_420` | **The signature style.** 3000+ unique vulgar variable names + ASCII art junk strings like `"8====D"` and `"( . Y . )"` scattered throughout |
| `underscore` | `___1`, `____2` | Underscore spam |
| `hex` | `_1a`, `_2f` | Hex-based names |

## Installation

```bash
# No dependencies required — pure Python 3
git clone https://github.com/gary60182007/diu9u-obfuscator.git
cd diu9u-obfuscator
```

## Usage

```bash
# Basic obfuscation
python obfuscator.py input.lua -o output.lua

# NSFW mode (recommended for maximum psychological damage)
python obfuscator.py input.lua -o output.lua --name-style nsfw

# High junk density
python obfuscator.py input.lua --name-style nsfw --junk-density 0.15

# Reproducible output with seed
python obfuscator.py input.lua --seed 42069 --name-style nsfw

# Disable specific passes
python obfuscator.py input.lua --no-encrypt --no-numbers
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
  --seed N              Random seed for reproducible output
  --watermark TEXT      Watermark text (default: diu9u)
  --junk-density FLOAT  Junk code density 0.0-1.0 (default: 0.05)
  --name-style STYLE    ilI | underscore | hex | nsfw
  --quiet               Suppress stats output
```

## Example Output (NSFW mode)

Before:
```lua
local Players = game:GetService("Players")
local player = Players.LocalPlayer
local health = player.Character:FindFirstChild("Humanoid").Health
print("HP: " .. health)
```

After:
```lua
local cock_senpai;do local _k="...";cock_senpai=function(_s)...end end;do local
balls_420={"8====D","( . Y . )","stop skidding lmaooo"};local cum_69=9998;if
balls_420[cum_69] then error(balls_420[cum_69]) end;end;local dong_uwu=game:
GetService(cock_senpai("\136\203..."))local penis_daddy=dong_uwu.dick_pro if
(type(42)=="string") then local boner_uwu="8=====D~~~";end;local hentai_zone=
penis_daddy.schlong_mega:FindFirstChild(cock_senpai("\152\201...")).chode_slayer
print(cock_senpai("\168\219...")..hentai_zone)
```

## How It Works

1. **Tokenizer**: Full Luau-compatible lexer that handles all syntax including compound assignments, string interpolation, and type annotations
2. **String Encryption**: Each string is XOR'd with a random key and replaced with a call to an injected decoder function
3. **Variable Renaming**: Finds all `local` declarations and function parameters, maps them to generated names
4. **Number Obfuscation**: Replaces number literals with equivalent arithmetic expressions (`42` → `(541-499)`)
5. **Junk Injection**: Inserts dead code blocks using opaque predicates (`math.floor(7.3)==7` is always true) with NSFW ASCII art as string payloads
6. **Minification**: Strips all whitespace and newlines, inserting separators only where syntactically required

## Comparison

| | **diu9u v2** | **Ironbrew 2** | **Luraph** |
|---|---|---|---|
| Luau Support | ✅ | ❌ | ✅ |
| Price | Free | Free | $8-30/mo |
| Dependencies | Python 3 | .NET SDK | Web |
| NSFW Mode | ✅ 8====D | ❌ | ❌ |
| VM Obfuscation | ❌ | ✅ | ✅ |
| Strength | ★★☆☆☆ | ★★★☆☆ | ★★★★★ |
| Fun Factor | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ |

## License

MIT — do whatever you want with it.

## Credits

Made by **diu9u** — if you're reading obfuscated code full of dick jokes, you've already lost.
