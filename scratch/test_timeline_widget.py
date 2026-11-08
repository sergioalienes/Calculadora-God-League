import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.stdout.reconfigure(encoding='utf-8')

import tkinter as tk
import customtkinter as ctk

def test_enhanced_timeline():
    app = ctk.CTk()
    app.geometry("450x250")
    app.title("Enhanced Timeline Test")

    colors = {
        "bg_primary": "#0A0A0A",
        "bg_secondary": "#131313",
        "sidebar_bg": "#111111",
        "border": "#222222",
        "text_primary": "#FFFFFF",
        "text_secondary": "#888888",
        "accent": "#F26419",
        "accent_hover": "#FF7A33",
        "success": "#51CF66",
        "warning": "#FFA94D",
        "danger": "#FF453A",
    }

    container = ctk.CTkFrame(app, fg_color=colors["bg_primary"], corner_radius=8, border_width=1, border_color=colors["border"])
    container.pack(fill="x", padx=10, pady=10)

    # Header
    head_f = ctk.CTkFrame(container, fg_color="transparent")
    head_f.pack(fill="x", padx=6, pady=(4, 2))
    ctk.CTkLabel(head_f, text="📊 ESTRATEGIA COMPARADA", font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=colors["accent"]).pack(side="left")
    
    btn_apply = ctk.CTkButton(head_f, text="🚀 Aplicar", width=58, height=18, corner_radius=4,
                              fg_color=colors["accent"], hover_color=colors["accent_hover"],
                              font=ctk.CTkFont(family="Segoe UI", size=8, weight="bold"))
    btn_apply.pack(side="right", padx=(4, 0))

    lbl_laps = ctk.CTkLabel(head_f, text="V16 / 20", font=ctk.CTkFont(family="Segoe UI Mono", size=9, weight="bold"), text_color=colors["text_secondary"])
    lbl_laps.pack(side="right")

    canvas = tk.Canvas(container, height=82, bg="#0E0E0E", highlightthickness=0)
    canvas.pack(fill="x", padx=6, pady=(0, 6))

    def render_timeline(tot_laps=20, curr_lap=16,
                        plan_stops=1, plan_p1=15, plan_p2=0, plan_c1="hard", plan_c2="soft", plan_c3="soft",
                        tac_active=True, tac_stops=1, tac_p1=13, tac_p2=0, tac_c1="hard", tac_c2="soft", tac_c3="soft",
                        sc_active=True, sc_start=13, sc_end=15):
        canvas.delete("all")
        W = canvas.winfo_width()
        if W <= 10:
            W = 410
        H = 82

        x_start = 42
        x_end = W - 14
        w_avail = max(10, x_end - x_start)
        tot_laps = max(1, tot_laps)

        comp_colors = {
            "hard": {"fill": "#252C36", "border": "#ADB5BD", "text": "#FFFFFF", "name": "Duro"},
            "soft": {"fill": "#82181A", "border": "#FF6B6B", "text": "#FFFFFF", "name": "Blando"},
        }

        # ── Fila 1: PLAN ASIGNADO ──
        canvas.create_text(6, 17, text="PLAN", anchor="w", fill="#888888", font=("Segoe UI", 8, "bold"))
        y1, y2 = 7, 27

        def get_stints(stops, p1, p2, c1, c2, c3):
            if stops == 0 or p1 <= 0 or p1 >= tot_laps:
                return [(0, tot_laps, c1)]
            elif stops == 1:
                p1_c = min(tot_laps, max(1, p1))
                return [(0, p1_c, c1), (p1_c, tot_laps, c2)]
            else:
                p1_c = min(tot_laps - 2, max(1, p1))
                p2_c = min(tot_laps, max(p1_c + 1, p2))
                return [(0, p1_c, c1), (p1_c, p2_c, c2), (p2_c, tot_laps, c3)]

        # Dibujar Stints del Plan
        plan_stints = get_stints(plan_stops, plan_p1, plan_p2, plan_c1, plan_c2, plan_c3)
        for s_start, s_end, s_comp in plan_stints:
            xs = x_start + (s_start / tot_laps) * w_avail
            xe = x_start + (s_end / tot_laps) * w_avail
            cfg = comp_colors.get(s_comp, comp_colors["hard"])
            canvas.create_rectangle(xs, y1, xe, y2, fill=cfg["fill"], outline=cfg["border"], width=1)
            # Texto
            mid_x = (xs + xe) / 2
            st_len = s_end - s_start
            if (xe - xs) > 35:
                label = f"{cfg['name']} ({st_len}v)"
            elif (xe - xs) > 18:
                label = f"{cfg['name'][0]}"
            else:
                label = ""
            if label:
                canvas.create_text(mid_x, (y1 + y2) / 2, text=label, fill=cfg["text"], font=("Segoe UI", 7, "bold"))

        # Marcas de parada en Plan
        if plan_stops >= 1 and 0 < plan_p1 < tot_laps:
            xp1 = x_start + (plan_p1 / tot_laps) * w_avail
            canvas.create_line(xp1, y1 - 2, xp1, y2 + 2, fill="#FF453A", width=2)
        if plan_stops == 2 and 0 < plan_p2 < tot_laps:
            xp2 = x_start + (plan_p2 / tot_laps) * w_avail
            canvas.create_line(xp2, y1 - 2, xp2, y2 + 2, fill="#FF453A", width=2)

        # ── Fila 2: TÁCTICA O REAL ──
        y3, y4 = 34, 54
        if tac_active:
            canvas.create_text(6, 44, text="TÁCT", anchor="w", fill=colors["warning"], font=("Segoe UI", 8, "bold"))
            tac_stints = get_stints(tac_stops, tac_p1, tac_p2, tac_c1, tac_c2, tac_c3)

            for s_start, s_end, s_comp in tac_stints:
                xs = x_start + (s_start / tot_laps) * w_avail
                xe = x_start + (s_end / tot_laps) * w_avail
                cfg = comp_colors.get(s_comp, comp_colors["hard"])
                canvas.create_rectangle(xs, y3, xe, y4, fill=cfg["fill"], outline=colors["warning"], width=1)
                mid_x = (xs + xe) / 2
                st_len = s_end - s_start
                if (xe - xs) > 35:
                    label = f"{cfg['name']} ({st_len}v)"
                elif (xe - xs) > 18:
                    label = f"{cfg['name'][0]}"
                else:
                    label = ""
                if label:
                    canvas.create_text(mid_x, (y3 + y4) / 2, text=label, fill=cfg["text"], font=("Segoe UI", 7, "bold"))

            # Franja SC si aplica
            if sc_active and sc_start < tot_laps:
                x_sc_s = x_start + (sc_start / tot_laps) * w_avail
                x_sc_e = x_start + (min(tot_laps, sc_end) / tot_laps) * w_avail
                canvas.create_rectangle(x_sc_s, y3 + 1, x_sc_e, y4 - 1, fill="#554400", outline="#FFD43B", width=1)
                if (x_sc_e - x_sc_s) > 20:
                    canvas.create_text((x_sc_s + x_sc_e) / 2, (y3 + y4) / 2, text="SC", fill="#FFD43B", font=("Segoe UI", 7, "bold"))

            # Marcas de parada Táctica
            if tac_stops >= 1 and 0 < tac_p1 < tot_laps:
                xt1 = x_start + (tac_p1 / tot_laps) * w_avail
                canvas.create_line(xt1, y3 - 2, xt1, y4 + 2, fill=colors["warning"], width=2)
                sc_badge = "🟡" if (sc_active and sc_start <= tac_p1 <= sc_end) else "⚡"
                canvas.create_text(xt1, y3 - 2, text=f"{sc_badge}V{tac_p1}", anchor="s", fill=colors["warning"], font=("Segoe UI", 6, "bold"))

            if tac_stops == 2 and 0 < tac_p2 < tot_laps:
                xt2 = x_start + (tac_p2 / tot_laps) * w_avail
                canvas.create_line(xt2, y3 - 2, xt2, y4 + 2, fill=colors["warning"], width=2)
                canvas.create_text(xt2, y3 - 2, text=f"⚡V{tac_p2}", anchor="s", fill=colors["warning"], font=("Segoe UI", 6, "bold"))
        else:
            canvas.create_text(6, 44, text="REAL", anchor="w", fill=colors["success"], font=("Segoe UI", 8, "bold"))
            # Mostrar la misma distribución pero con progreso completado
            for s_start, s_end, s_comp in plan_stints:
                xs = x_start + (s_start / tot_laps) * w_avail
                xe = x_start + (s_end / tot_laps) * w_avail
                cfg = comp_colors.get(s_comp, comp_colors["hard"])
                canvas.create_rectangle(xs, y3, xe, y4, fill="#181818", outline="#333333", width=1)
                # Tramo completado
                if curr_lap > s_start:
                    comp_end = min(curr_lap, s_end)
                    xc_end = x_start + (comp_end / tot_laps) * w_avail
                    canvas.create_rectangle(xs, y3, xc_end, y4, fill=cfg["fill"], outline=colors["success"], width=1)
                mid_x = (xs + xe) / 2
                canvas.create_text(mid_x, (y3 + y4) / 2, text=cfg["name"], fill="#AAAAAA", font=("Segoe UI", 7))

        # ── Eje de Vueltas / Regla Inferior ──
        y_axis = 64
        canvas.create_line(x_start, y_axis, x_end, y_axis, fill="#2C2C2C", width=1)
        canvas.create_text(x_start, y_axis + 8, text="0", anchor="c", fill="#666666", font=("Segoe UI Mono", 7))
        canvas.create_text(x_end, y_axis + 8, text=f"V{tot_laps}", anchor="c", fill="#666666", font=("Segoe UI Mono", 7))

        # ── Cursor de Vuelta Actual Neón ──
        if 0 <= curr_lap <= tot_laps:
            xc = x_start + (curr_lap / tot_laps) * w_avail
            canvas.create_line(xc, 3, xc, y_axis + 1, fill=colors["accent"], width=2)
            canvas.create_polygon(xc - 3, 2, xc + 3, 2, xc, 6, fill=colors["accent"])
            canvas.create_text(xc, y_axis + 8, text=f"▲V{curr_lap}", anchor="c", fill=colors["accent"], font=("Segoe UI Mono", 7, "bold"))

    app.update()
    render_timeline()
    print("Enhanced timeline test passed.")
    app.destroy()

if __name__ == "__main__":
    test_enhanced_timeline()
