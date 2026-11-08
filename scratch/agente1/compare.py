"""Compara dos volcados de baseline.py (tolerancia numérica 1e-9, claves '_*' ignoradas).
Uso: python scratch/agente1/compare.py antes.json despues.json
"""
import sys
import json

TOL = 1e-9
diffs = []


def cmp(a, b, path="$"):
    if isinstance(a, dict) and isinstance(b, dict):
        ka = {k for k in a if not k.startswith("_")}
        kb = {k for k in b if not k.startswith("_")}
        for k in sorted(ka | kb):
            if k not in a or k not in b:
                diffs.append(f"{path}.{k}: clave solo en {'antes' if k in a else 'despues'}")
                continue
            cmp(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: longitud {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            cmp(x, y, f"{path}[{i}]")
    elif isinstance(a, bool) or isinstance(b, bool):
        if a != b:
            diffs.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a - b) > TOL * max(1.0, abs(a), abs(b)):
            diffs.append(f"{path}: {a!r} != {b!r} (diff {abs(a - b):.3e})")
    elif a != b:
        diffs.append(f"{path}: {a!r} != {b!r}")


a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
cmp(a, b)
if diffs:
    print(f"DIFERENCIAS: {len(diffs)}")
    for d in diffs[:60]:
        print("  ", d)
    sys.exit(1)
print("IDENTICOS (tolerancia 1e-9)")
