from pathlib import Path
c = Path('modules/strategy_charts.py').read_text(encoding='utf-8').splitlines()
for i in range(2224, 2252):
    print(f"{i+1}: {repr(c[i])}")
