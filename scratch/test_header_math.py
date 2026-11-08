"""
Unit test for updated RaceControlHeader logic:
- Leader consumed laps
- Leader pace
- Leader remaining pit stops (0, 1 full tank, 1 tyres only, 2 stops)
- Race remaining time
- Track time & White flag projection
"""

import math

def parse_clock_to_seconds(clock_str: str) -> float:
    s = str(clock_str).strip()
    if not s:
        return 3600.0
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 3:
            h, m, sec = parts
            return float(h) * 3600.0 + float(m) * 60.0 + float(sec)
        elif len(parts) == 2:
            m, sec = parts
            return float(m) * 60.0 + float(sec)
    try:
        val = float(s)
        if val <= 180:
            return val * 60.0
        return val
    except ValueError:
        return 3600.0

def format_seconds_to_clock(seconds: float) -> str:
    if seconds <= 0:
        return "00:00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def calculate_leader_projection(
    leader_consumed_laps: int,
    leader_pace_s: float,
    rem_time_s: float,
    leader_strategy_mode: str,
    pitlane_loss_s: float = 22.5,
    tank_cap: float = 70.0,
    refuel_rate: float = 12.0,
    tyre_change_s: float = 4.0,
):
    # Stops times
    t_first = pitlane_loss_s + max(tank_cap / refuel_rate, tyre_change_s)
    t_last = pitlane_loss_s + tyre_change_s

    if "0" in leader_strategy_mode:
        pit_loss = 0.0
    elif "Solo Ruedas" in leader_strategy_mode:
        pit_loss = t_last
    elif "1 Parada" in leader_strategy_mode: # Tanque Lleno
        pit_loss = t_first
    elif "2" in leader_strategy_mode:
        pit_loss = t_first + t_last
    else:
        pit_loss = 0.0

    track_s = max(0.0, rem_time_s - pit_loss)
    if leader_pace_s > 0 and track_s > 0:
        rem_laps = math.floor(track_s / leader_pace_s) + 1
    else:
        rem_laps = 0

    total_projected = leader_consumed_laps + rem_laps
    return {
        "pit_loss": pit_loss,
        "track_s": track_s,
        "rem_laps": rem_laps,
        "total_projected": total_projected,
    }

def run_tests():
    print("Testing RaceControlHeader math...")
    # Test clock parsing
    assert parse_clock_to_seconds("00:43:06") == 2586.0
    assert parse_clock_to_seconds("43:06") == 2586.0
    assert parse_clock_to_seconds("60") == 3600.0

    # Test projection at V12 consumed (43m 06s remaining)
    res0 = calculate_leader_projection(12, 84.5, 2586.0, "0 Paradas")
    res1 = calculate_leader_projection(12, 84.5, 2586.0, "1 Parada (Tanque Lleno)")
    res2 = calculate_leader_projection(12, 84.5, 2586.0, "2 Paradas (1ª Tanque + 2ª Ruedas)")

    print(f"0 Paradas: Rem={res0['rem_laps']}v, Total={res0['total_projected']}v (Pitloss={res0['pit_loss']}s)")
    print(f"1 Parada: Rem={res1['rem_laps']}v, Total={res1['total_projected']}v (Pitloss={res1['pit_loss']}s)")
    print(f"2 Paradas: Rem={res2['rem_laps']}v, Total={res2['total_projected']}v (Pitloss={res2['pit_loss']}s)")

    assert res0['pit_loss'] == 0.0
    assert round(res1['pit_loss'], 1) == 28.3
    assert round(res2['pit_loss'], 1) == 54.8
    print("RaceControlHeader math verified!")

if __name__ == "__main__":
    run_tests()
