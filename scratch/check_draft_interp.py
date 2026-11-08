import json
from pathlib import Path
import numpy as np

p_fuel = Path('profiles/God League/Road America_fuel.json')
data = json.loads(p_fuel.read_text(encoding='utf-8'))

saving_rows = data['fuel_saving_rows']
draft_rows = data['draft_rows']

print('fuel_saving_rows:', saving_rows)
print('draft_rows:', draft_rows)

pts_saving = [(0.0, 0.0)] + [(abs(r['delta_l']), abs(r['delta_s'])) for r in saving_rows]
pts_draft = [(0.0, 0.0)] + [(abs(r['delta_l']), abs(r['delta_s'])) for r in draft_rows]

pts_saving.sort(key=lambda p: p[0])
pts_draft.sort(key=lambda p: p[0])

print('pts_saving:', pts_saving)
print('pts_draft:', pts_draft)

def interp(x, pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if x <= xs[-1]:
        return float(np.interp(x, xs, ys))
    else:
        dx = xs[-1] - xs[-2]
        dy = ys[-1] - ys[-2]
        slope = dy / max(0.001, dx)
        return float(ys[-1] + slope * (x - xs[-1]))

test_savings = [0.05, 0.10, 0.20, 0.30, 0.40, 0.45]
print('\nComparacion de perdida de tiempo (s) segun ahorro necesario (L/v):')
print(f'{"Ahorro (L/v)":<15} | {"Sin Rebufo (fuel_saving)":<25} | {"Con Rebufo (draft_rows)":<25}')
print('-'*70)
for s in test_savings:
    pen_s = interp(s, pts_saving)
    pen_d = interp(s, pts_draft)
    print(f'{s:<15.2f} | {pen_s:<25.4f} | {pen_d:<25.4f}')
