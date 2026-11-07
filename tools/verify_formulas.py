import re, glob, os, sys
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
norm = lambda s: re.sub(r"\s+", "", s)
pat = re.compile(r"\*\*Source:\*\* `([^`:]+):(\d+)(?:-(\d+))?`\n```python\n(.*?)\n```", re.S)
total = bad = 0
for f in sorted(glob.glob(R + "/docs/formulas/*.md")) + [R + "/docs/GAME_FORMULAS.md"]:
    t = open(f).read()
    for m in pat.finditer(t):
        p, a, b, code = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2)), m.group(4)
        total += 1
        L = open(os.path.join(R, p), encoding="utf-8").read().split("\n")
        lo, hi = max(0, a - 1 - 3), min(len(L), b + 3)
        if norm(code) not in norm("\n".join(L[lo:hi])):
            bad += 1
            print("MISMATCH", os.path.basename(f), p, a, b)
print(f"checked {total} source blocks, {bad} mismatches")
sys.exit(1 if bad else 0)
