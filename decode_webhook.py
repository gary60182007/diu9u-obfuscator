import base64, sys

XKEY = 90

def decode(encoded: str) -> str:
    raw = base64.b64decode(encoded)
    return "".join(chr(b ^ XKEY) for b in raw)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            print(decode(arg))
    else:
        print("Paste the encoded string (from d1 or d3):")
        s = input("> ").strip()
        if s:
            print("Decoded:", decode(s))
