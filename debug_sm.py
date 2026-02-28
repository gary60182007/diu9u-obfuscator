import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

with open('unobfuscator/target1.lua', 'r', encoding='utf-8', errors='replace') as f:
    src = f.read()

print(f"Source length: {len(src)}")

from unobfuscator.passes.state_machine_deobf import (
    _find_decoder, _find_state_var, _find_table_var, _find_init_val,
    _extract_all_states, _follow_state_chain, deobfuscate_state_machine_source
)

decoder_name, shift = _find_decoder(src)
print(f"Decoder: name={decoder_name}, shift={shift}")

tbl_var = _find_table_var(src)
print(f"Table var: {tbl_var}")

state_var = _find_state_var(src, decoder_name) if decoder_name else None
print(f"State var: {state_var}")

init_val = _find_init_val(src, state_var) if state_var else None
print(f"Init val: {init_val}")

if state_var and tbl_var and decoder_name:
    states = _extract_all_states(src, state_var, tbl_var, decoder_name)
    print(f"States extracted: {len(states)}")

    # Find what the init_val state does - look at the raw source near init
    sv = state_var
    # The first branch where state_var < X, look for the initial state's block
    # Find the first append after the while loop starts
    while_idx = src.find('while ' + sv)
    if while_idx < 0:
        while_idx = src.find('while(' + sv)
    if while_idx >= 0:
        first_append_idx = src.find(tbl_var + '[#' + tbl_var + '+1]', while_idx)
        if first_append_idx >= 0:
            context = src[max(while_idx, first_append_idx - 500):first_append_idx + 300]
            print(f"\nFirst append context ({len(context)} chars):")
            print(repr(context[:600]))

    # Check which state values are closest to init_val
    all_keys = sorted(states.keys())
    close_keys = [k for k in all_keys if abs(k - init_val) < 1000000]
    print(f"\nKeys close to init_val ({init_val}): {close_keys[:20]}")

    # Check: does the init state NOT have an append (it's a junk/no-op state)?
    # Find the state transition from init_val
    import re
    sv_esc = re.escape(sv)
    # Look for the exact block that executes when state == init_val (approximately)
    # The binary search structure means the init_val is somewhere in the nested ifs
    # Let's find what the chain would look like if we started from a known state
    if all_keys:
        test_start = all_keys[0]
        test_frags = _follow_state_chain(states, test_start, shift)
        if test_frags:
            print(f"\nTest chain from {test_start}: {len(test_frags)} fragments")
            print(f"First decoded: {test_frags[0][:80]}")
        else:
            print(f"\nTest chain from {test_start} also failed")
            if test_start in states:
                entry = states[test_start]
                print(f"  Entry: encoded={'yes' if entry.get('encoded') else 'no'}, next={entry['next']}")
                print(f"  next in states: {entry['next'] in states}")
else:
    print("Missing vars")
