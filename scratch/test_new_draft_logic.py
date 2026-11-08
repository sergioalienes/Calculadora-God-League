import numpy as np

# Road America Modelo 1
cons_base = 5.4
usable_tank = 70.0 - 0.4 # 69.6 L
pts_saving = [(0.0, 0.0), (0.05, 0.01), (0.45, 0.4), (0.9, 2.0)]
pts_draft = [(0.0, 0.0), (0.05, 0.01), (0.45, 0.02)]

def interp(x, pts):
    if x <= 0.0001:
        return 0.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if x <= xs[-1]:
        return float(np.interp(x, xs, ys))
    else:
        dx = xs[-1] - xs[-2]
        dy = ys[-1] - ys[-2]
        slope = dy / max(0.001, dx)
        return float(ys[-1] + slope * (x - xs[-1]))

def calc_stint(st_len, n_draft):
    n_green = st_len - n_draft
    f_needed = st_len * cons_base
    excess = max(0.0, f_needed - usable_tank)
    
    max_draft_l = pts_draft[-1][0] # 0.45 L/v
    
    if excess <= 0.0:
        save_draft = max_draft_l if n_draft > 0 else 0.0
        t_pen_draft = interp(save_draft, pts_draft)
        save_green = 0.0
        t_pen_green = 0.0
    else:
        if n_green == 0:
            save_draft = min(0.20 * cons_base, excess / n_draft)
            t_pen_draft = interp(save_draft, pts_draft)
            save_green = 0.0
            t_pen_green = 0.0
        elif n_draft == 0:
            save_draft = 0.0
            t_pen_draft = 0.0
            save_green = min(0.20 * cons_base, excess / n_green)
            t_pen_green = interp(save_green, pts_saving)
        else:
            # Both draft and green
            # Priority to draft saving
            cap_draft = n_draft * max_draft_l
            if excess <= cap_draft:
                save_draft = excess / n_draft
                t_pen_draft = interp(save_draft, pts_draft)
                save_green = 0.0
                t_pen_green = 0.0
            else:
                save_draft = max_draft_l
                t_pen_draft = interp(save_draft, pts_draft)
                rem_excess = excess - cap_draft
                save_green = min(0.20 * cons_base, rem_excess / n_green)
                t_pen_green = interp(save_green, pts_saving)
                
    fuel_burned = n_draft * (cons_base - save_draft) + n_green * (cons_base - save_green)
    return {
        'excess': excess,
        'save_draft': save_draft,
        't_pen_draft': t_pen_draft,
        'save_green': save_green,
        't_pen_green': t_pen_green,
        'fuel_burned': fuel_burned
    }

print("=== Caso 1: Stint de 14 vueltas SIN REBUFO (p1=14) ===")
r1 = calc_stint(14, 0)
print(f"Excess: {r1['excess']:.2f}L | Save green: {r1['save_green']:.4f}L/v | Pen green: {r1['t_pen_green']:.4f}s | Burned: {r1['fuel_burned']:.2f}L")

print("\n=== Caso 2: Stint de 14 vueltas con REBUFO V3-V12 (10 vueltas) ===")
r2 = calc_stint(14, 10)
print(f"Excess: {r2['excess']:.2f}L | Save draft: {r2['save_draft']:.4f}L/v | Pen draft: {r2['t_pen_draft']:.4f}s | Save green: {r2['save_green']:.4f}L/v | Pen green: {r2['t_pen_green']:.4f}s | Burned: {r2['fuel_burned']:.2f}L")

print("\n=== Caso 3: Stint de 14 vueltas con REBUFO V5-V10 (6 vueltas) ===")
r3 = calc_stint(14, 6)
print(f"Excess: {r3['excess']:.2f}L | Save draft: {r3['save_draft']:.4f}L/v | Pen draft: {r3['t_pen_draft']:.4f}s | Save green: {r3['save_green']:.4f}L/v | Pen green: {r3['t_pen_green']:.4f}s | Burned: {r3['fuel_burned']:.2f}L")
