import sys

# Parse trace to find offset jumps and patterns
reads = []
with open('buffer_trace.txt', 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        parts = line.split(',', 3)
        typ = parts[0]
        offset = int(parts[1])
        if typ == 'str':
            length = int(parts[2])
            reads.append((typ, offset, length))
        else:
            val = parts[2]
            reads.append((typ, offset, val))

print(f"Total reads: {len(reads)}")

# Find large offset jumps (indicating buffer.copy consumed data)
print("\nOffset jumps > 100 bytes:")
prev_offset = 0
for i, entry in enumerate(reads):
    offset = entry[1]
    jump = offset - prev_offset
    if jump > 100:
        print(f"  Read #{i}: offset {prev_offset} -> {offset} (jump={jump})")
        # Show surrounding context
        for j in range(max(0, i-3), min(len(reads), i+3)):
            e = reads[j]
            marker = " >>>" if j == i else "    "
            if e[0] == 'str':
                print(f"  {marker} [{j}] {e[0]} off={e[1]} len={e[2]}")
            else:
                print(f"  {marker} [{j}] {e[0]} off={e[1]} val={e[2]}")
    prev_offset = offset

# Also find the maximum sequential offset reached
print(f"\nOffset progression (sampled):")
max_offset = 0
checkpoints = []
for i, entry in enumerate(reads):
    offset = entry[1]
    if offset > max_offset + 1000:
        checkpoints.append((i, offset))
    max_offset = max(max_offset, offset)

for i, offset in checkpoints:
    print(f"  Read #{i}: first time past offset {offset}")

# Find where offset stops growing (end of sequential reads)
last_increasing = 0
for i in range(1, len(reads)):
    if reads[i][1] > reads[i-1][1]:
        last_increasing = i

print(f"\nLast read that increased offset: #{last_increasing}")
print(f"  {reads[last_increasing]}")
print(f"Final offset: {reads[-1][1]}")

# Check if any reads go back to low offsets (re-reading)
low_reads = [(i, reads[i]) for i in range(len(reads)) if reads[i][1] < 100 and i > 1000]
if low_reads:
    print(f"\nReads going back to low offsets after index 1000:")
    for i, r in low_reads[:10]:
        print(f"  [{i}] {r}")

# r[10] tracks the current offset. Let me track what r[10] would be
# by simulating the sequential reads
print(f"\nSimulating r[10] offset tracking:")
sim_offset = 0
offset_at = {}
for i, entry in enumerate(reads):
    typ, offset = entry[0], entry[1]
    if typ == 'str':
        size = entry[2]
        if offset == sim_offset:
            sim_offset += size
    elif typ == 'u8':
        if offset == sim_offset:
            sim_offset += 1
    elif typ in ('u16', 'i16'):
        if offset == sim_offset:
            sim_offset += 2
    elif typ in ('u32', 'i32', 'f32'):
        if offset == sim_offset:
            sim_offset += 4
    elif typ == 'f64':
        if offset == sim_offset:
            sim_offset += 8
    
    if i % 10000 == 0:
        offset_at[i] = sim_offset

print(f"Simulated final offset: {sim_offset}")
for idx in sorted(offset_at.keys()):
    print(f"  After read #{idx}: simulated offset = {offset_at[idx]}")

# The gap between simulated offset and buffer size tells us how much
# was consumed by buffer.copy (which we didn't trace)
buf_size = 1064652
print(f"\nBuffer size: {buf_size}")
print(f"Simulated end offset: {sim_offset}")
print(f"Gap (consumed by buffer.copy): {buf_size - sim_offset}")
