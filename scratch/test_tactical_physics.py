import math
import numpy as np

def test_physics():
    cons_base = 5.65
    tank_cap = 70.0
    safety_l = 2.5
    usable_tank = tank_cap - safety_l
    weight_sens = 0.015
    base_lap_s = 84.5
    pitlane_loss_s = 22.5
    refuel_rate = 12.0
    tyre_change_s = 4.0
    
    saving_curve = [(0.0, 0.0), (cons_base * 0.10, 0.35), (cons_base * 0.20, 0.80)]
    
    def interpolate_saving_penalty(save_per_l: float) -> float:
        if save_per_l <= 0.001:
            return 0.0
        xs = [p[0] for p in saving_curve]
        ys = [p[1] for p in saving_curve]
        if save_per_l <= xs[-1]:
            return float(np.interp(save_per_l, xs, ys))
        dx = xs[-1] - xs[-2]
        dy = ys[-1] - ys[-2]
        slope = dy / max(0.01, dx)
        return float(ys[-1] + slope * (save_per_l - xs[-1]))
    
    print("Saving 0.20 L/v -> penalty:", interpolate_saving_penalty(0.20))
    print("Saving 0.565 L/v (10%) -> penalty:", interpolate_saving_penalty(0.565))
    print("Saving 1.13 L/v (20%) -> penalty:", interpolate_saving_penalty(1.13))
    
    # Check that penalty increases smoothly and realistically
    assert 0.10 < interpolate_saving_penalty(0.20) < 0.20
    assert abs(interpolate_saving_penalty(0.565) - 0.35) < 0.01
    assert abs(interpolate_saving_penalty(1.13) - 0.80) < 0.01
    print("Physics verification PASSED!")

if __name__ == "__main__":
    test_physics()
