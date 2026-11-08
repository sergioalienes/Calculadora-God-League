# Informe del Agente 2: pruebas de estrategias y coherencia

**Calculadora God League.** He revisado el commit actual en un worktree aislado y no he modificado ningún archivo de la app. Todas las pruebas se han ejecutado sin ventana visible (`withdraw`), sobre una **copia temporal** de `profiles/`. Al terminar he comprobado que `profiles/_last_state.json` y los perfiles reales siguen intactos.

Los scripts de prueba y sus salidas están en `scratch/agente2/` (copiados junto a este informe):

| Script | Qué prueba | Salida |
|---|---|---|
| `harness.py` | Arnés: redirige `PROFILES_ROOT` a una carpeta temporal, silencia los `messagebox` y define `build_pipeline` | — |
| `test_01_fuel.py` | Combustible contra una referencia independiente (9 escenarios y entradas degeneradas) | `out_01_fuel.txt` |
| `test_02_pipeline.py` | Cadena Campeonato → Combustible → Neumáticos → Comparador con perfiles reales e inventados, y OLS | `out_02_pipeline.txt` |
| `test_03_charts_sc.py` | Comparador: viabilidad, Safety Car, rebufo y ranking | `out_03_charts_sc.txt` |
| `test_04_live.py` | Control en vivo: persistencia, registros de meta, fronteras, líder, táctico con SC | `out_04_live.txt` |
| `test_05_app.py` | `CalculadoraApp` completa: arranque, navegación, last_state, validaciones y borrado | `out_05_app.txt` |

---

## Resumen de estrategias probadas

| Escenario | Vueltas (comb.) | Paradas viables | Comprobación | Resultado |
|---|---|---|---|---|
| Bélgica (perfil real, 70 L, 5.65 L/v, 1:57) | 31 | `['2 Paradas']` | Referencia: 31 v, 2 paradas mín. 1 parada inviable (15+15 < 31) | OK. Neumáticos = comparador = 3721.438 s |
| Road America (perfil real, 5.4 L/v, 1:45) | 34 | `['2 Paradas']` | Referencia OK | OK. Neumáticos = comparador = 3637.598 s. Óptima V13/V21 duro-blando-duro: 3630.09 s |
| Nordschleife (perfil real, 20 L/v, 7:03) | 9 | `['2 Paradas']` | Referencia OK | **Neumáticos 3847.35 s y comparador 3867.56 s para el mismo plan (+20.2 s)**. Warmup negativo (-1.4 / -5 s) aceptado |
| GT3 105 L, 2.8 L/s, 45 min, 3.2 L/v | 26 | `['1 Parada']` | Gasolina gratis 18 s × 2.8 = 50.4 L ✔ | OK. Óptima 1 parada V11 duro-blando |
| GTP 110 L, 120 min, 3:30, 9.5 L/v | 34 | `['2 Paradas','3 Paradas']` | — | Neumáticos y comparador difieren **+43 s**: neumáticos ignora el coste del lift & coast |
| GT3 120 min, 5 L/v | 67 | `['2 Paradas','3 Paradas']` | 3 paradas no se pueden seleccionar en ningún módulo | Diferencia neumáticos/comparador **+95 s** |
| Sprint 20 min IR-18 con compuesto obligatorio | 14 | `['1 Parada']` | — | OK. Llega a meta con 39.9 L de sobra (no se modela salir con depósito parcial) |
| Sprint 20 min **sin** compuesto obligatorio | 14 | `['1 Parada']` | Debería ser 0 paradas | **Parada forzada** (unos 28.5 s perdidos) |
| Depósito 500 L sin compuesto obligatorio | 40 | `['1 Parada']` | Referencia: 0 paradas, 41 v | **Parada forzada: 40 v en lugar de 41** |
| Consumo 30 L/v (70 L) | 34 | `['16 Paradas']` | — | La interfaz solo tiene 2 paradas: tarjetas vacías |
| Consumo 12 L/v | 38 | `['5','6','7 Paradas']` | — | Neumáticos solo cuenta 1 box. El comparador simula 2 paradas con el **depósito a 0 L** y no encuentra óptima |
| Bélgica + SC V8 S2 × 3 v (comparador) | 27 | — | Ritmo SC 240 s = 7 km / 105 km/h ✔ | Parada gratis en V9-V10 ✔, pitlane cerrado en V8 ✔ |
| Bélgica + SC (táctico del live) | 31 | — | Usa SC = 1.40 × vuelta = 163.8 s y no descuenta vueltas | Incoherente con el comparador (27 v) |
| Consumo 0, rate 0, negativo, reserva > depósito | — | — | — | **ZeroDivisionError** con consumo 0 y con rate 0. Consumo negativo produce «39 Paradas» |

Comprobaciones que han salido correctas:

- **White Flag (+1):** coincide con la referencia en todos los casos.
- **Litros a cargar:** nunca superan el depósito.
- **Delta de peso:** siempre ≤ 0 (máximo 0.000 s) en neumáticos y en el comparador.
- **Modelo de neumáticos por tramos:** x=0 → warmup, x=1 → 0, x≥2 → max(0, a·ln x + n). Ejemplo: Bélgica blando en x=2 da 1.4881·ln2 + 0.5102 = 1.542 ✔.
- **OLS de Bélgica:** recalculado a=0.5739, n=-0.0186, R²=0.9934, igual que el guardado.
- **Tiempo total de neumáticos:** coincide al milisegundo con la referencia (suma de vueltas + boxes) en todos los casos de 1 o 2 paradas.

---

## (a) Errores de cálculo y de comportamiento, por gravedad

### A1. CRÍTICO: la sesión en vivo guardada se sobrescribe antes de cargarse (pérdida de datos)

**Dónde:** `live_control.py:2355-2368` (`on_session_data_updated`), que llama a `race_header.update_session_params()` (`:119-132`). Esta dispara `_on_params_changed()` → callback `_on_race_control_updated()` (`:2319-2323`) → `auto_save()`, que escribe el estado en memoria en `<circuito>_live.json`. Solo después se ejecuta `load_live_session()`.

**Reproducción** (`test_04` a y `test_05` 1): pongo en `Bélgica_live.json` `leader_lap=7` y 2 registros de meta, y arranco la app con `last_module="live"`.
- Resultado en disco: `leader_lap=0`, 0 registros, piloto «Piloto 1 (NIX)».
- Esperado: que se conserven los datos.

Pasa también al cambiar de circuito y luego ir a Control en vivo: los datos del circuito anterior se escriben en el `_live.json` del nuevo. Los `_live.json` reales de Bélgica y Road America ya contienen exactamente el estado por defecto (1 parada en V15, 30 L, 5.65 L/v), lo que encaja con este fallo.

**Corrección:** suprimir el autosave mientras se aplica la sesión (flag `_loading=True` comprobado en `_on_race_control_updated`), o cargar el JSON **antes** de llamar a `update_session_params`. Además, no guardar nada si el circuito ha cambiado y aún no se ha cargado su fichero.

### A2. ALTO: la sección de stints y sliders de Combustible nunca se construye

**Dónde:** `fuel_strategy.py:192-215` (`_build_scroll`) no llama a `_build_stints_section` (definida en `:371`). Por eso tampoco existen `_seg_stops`, los sliders ni las tarjetas de parada y gasolina gratis.

**Efecto:** `get_fuel_strategy_data()` exporta `pit1_lap`/`pit2_lap` sin validar, tal como vienen del JSON o con los valores por defecto 22/34. Ejemplo en Nordschleife: 9 vueltas, y se exporta `pit1=22`, `pit2=34`. Neumáticos y Control en vivo (`live_control.py:1515,1529`) usan esos valores.

**Corrección:** volver a añadir la sección, o, si se quitó a propósito, que `calculate_strategy` acote `pit1`/`pit2` al rango viable antes de exportarlos y eliminar el código muerto.

### A3. ALTO: estrategias de 3 o más paradas, viables pero imposibles de usar

`fuel_strategy._evaluate_viable_stop_strategies` devuelve, por ejemplo, `['2 Paradas','3 Paradas']` (GT3 120 min a 5 L/v) o `['5','6','7 Paradas']` (12 L/v). Sin embargo:

- **Combustible** (`fuel_strategy.py:1017-1026`): si `num_stops ≥ 3` construye los widgets de 2 paradas pero no llama a ningún `_update_*`. Las tarjetas quedan vacías (`test_01`, caso de 30 L/v).
- **Neumáticos** (`tyre_strategy.py:1064-1102`): trata cualquier número de paradas ≥ 2 como 2 y suma solo `total_pit_loss1` («`+ (total_pit_loss2 if num_stops == 2 else 0)`»). Con 5 paradas obtiene boxes = 32.8 s cuando deberían ser ≥ 65.7 s.
- **Comparador** (`strategy_charts.py:2488`, `:2139`): convierte con `1 if "1" in texto else 2`, así que «3 Paradas» se simula como 2 y «11 Paradas» como 1. `solve_optimal_strategy` (`:1999`, `:2040`) solo evalúa 1 y 2 paradas, y devuelve `None` con el aviso «No se encontró una estrategia óptima viable».
- **Live:** `promote_tactical_strategy` limita a `min(2, …)`.

**Corrección:** limitar `viable_modes` a lo que la interfaz soporta y avisar al usuario, o generalizar a N paradas con listas `pit_laps[]` y `stint_comps[]`. Parsear el número con `int(texto.split()[0])`.

### A4. ALTO: el comparador acepta estrategias que se quedan sin combustible

**Dónde:** `strategy_charts.py:1783` (`curr_fuel = max(0.0, curr_fuel - cons_lap)`) junto con `:1685` (el ahorro se recorta al 20 % pero el stint se simula igualmente). No existe ningún indicador de inviabilidad.

**Reproducción** (`test_03`): Bélgica, 1 parada en V15.
- Resultado: `final_fuel=0.00 L` (depósito vacío en V31) y aun así devuelve un tiempo válido de 3762.85 s.
- Con 12 L/v el stint 3 dura 24 vueltas a 9.6 L/v, unos 230 L con un depósito de 70 L.

Además, con SC o rebufo activos, `solve_optimal_strategy` amplía `max_stint_laps` usando un ahorro del 30 % (`:1994-1996`: `cons_base * 0.70`), lo que contradice el límite del 20 %.

**Corrección:** marcar `res["feasible"] = min(fuel_remaining) >= safety_l - 1e-6` y que el ahorro necesario no supere el 20 %. Descartar en el optimizador y en `_find_best_1stop_opportunity` todo lo que no sea viable, y mostrarlo en los KPI. Usar 0.80 también con SC o rebufo y dejar que la simulación decida.

### A5. ALTO: Neumáticos ignora la penalización de tiempo por lift & coast; Comparador sí la aplica

**Dónde:** `tyre_strategy.py:1105-1150` frente a `strategy_charts.py:1672-1692`. Neumáticos además consume siempre a ritmo `cons_lap` (`:1111`, `:1119`) aunque el stint sea de ahorro.

**Mismo plan, dos tiempos distintos:**
- Nordschleife (perfil real): 3847.35 s frente a 3867.56 s (**+20.2 s**).
- GTP 120 min: **+43 s**.
- GT3 120 min: **+95 s**.

El usuario ve tiempos totales distintos para la misma estrategia en dos pantallas.

**Corrección:** extraer una única función de simulación compartida (por ejemplo la de `strategy_charts._simulate_strategy`) y usarla desde neumáticos, o bien aplicar en neumáticos el mismo `target_cons` y la misma penalización interpolada.

### A6. MEDIO: el reglamento sin cambio obligatorio de compuesto no se respeta

**Dónde:**
- `championship_data.py:720` guarda siempre `"mandatory_compound_change": True` y no hay control en la interfaz para cambiarlo.
- `fuel_strategy.py:888` y `:798-799` fuerzan `max(1, …)` sin mirar el flag.
- `tyre_strategy.py:1048-1062` muestra la alerta de reglamento sin mirar el flag.

**Reproducción:** depósito de 500 L, 2 L/v, `mandatory=False`.
- Resultado: 1 parada mínima y 40 vueltas.
- Esperado: 0 paradas y 41 vueltas.

En un sprint de 20 min sin obligación se pierden unos 28.5 s en una parada innecesaria. El comparador sí lee el flag (`strategy_charts.py:1965`), así que los módulos se contradicen.

**Corrección:** añadir el control en el formulario del campeonato; en combustible usar `max(1, x) if mandatory else x`; permitir «0 Paradas»; condicionar la alerta de neumáticos al flag.

### A7. MEDIO: litros a cargar erróneos al cruzar meta justo en la vuelta de la parada 1 (2 paradas)

**Dónde:** `live_control.py:1012` (el stint se elige con `curr_lap <= p1`) frente a `:1116` (la próxima parada se elige con `curr_lap < p1`).

**Reproducción** (`test_04` c): plan V12/V24, registro en V12 con 2.2 L.
- Resultado: «Box 2: Fin V24 (en 0v) | Cargar: 67.8 L».
- Esperado: «Box 1: Fin V12 | Cargar 66.0 L».

**Corrección:** usar `curr_lap <= p1` y `curr_lap <= p2` también en el bloque de la próxima parada.

### A8. MEDIO: consumo del primer registro de meta mal calculado

**Dónde:** `live_control.py:880-883` y `:946-948`: `cons = tank_cap - fuel_val`, sin dividir por las vueltas.

**Reproducción:** primer registro en V3 con 53.05 L.
- Resultado: 16.95 L/v.
- Esperado: 5.65 L/v.

**Corrección:** `cons = (tank_cap - fuel_val) / max(1, lap_num)`.

### A9. MEDIO: el optimizador táctico del live falla si el comparador usa un modelo de neumáticos alternativo

**Dónde:** `live_control.py:1755-1763` hace `float(tdata.get("hard_base_lap"))`. Cuando el comparador tiene un override cargado de `_tyre_models.json`, los valores son texto («01:57.500»).

**Reproducción:** en el comparador, `_on_strat_tyre_model_changed("Prueba 1")` y después «Recalcular» en el táctico → `ValueError: could not convert string to float: '01:57.500'`.

**Corrección:** usar `_parse_time_str` (como en `strategy_charts.py:1546-1554`), o normalizar los overrides a float al cargarlos.

### A10. MEDIO: recalibración por SC en el live incoherente con el comparador

**Dónde:** `live_control.py:1822`, `:1800` y `:1845`.
- Ritmo SC fijo a `base_lap_s * 1.40`. En Bélgica da 163.8 s frente a los 240 s del perfil (`sc_pace_s`) que usa el comparador.
- Consumo SC fijo a 1.80 L/v (el comparador lo toma de cada segmento).
- `tot_laps` sale de la cabecera del líder y no descuenta el SC: el táctico usa 31 vueltas, el comparador 27 con el mismo SC.

**Corrección:** usar `session_data["sc_pace_s"]` (o longitud ÷ velocidad), pedir el consumo SC en la interfaz o leerlo del perfil, y recalcular las vueltas totales restando el tiempo de SC.

### A11. MEDIO: cambiar cualquier parámetro de combustible borra las tablas de ahorro y rebufo calibradas

**Dónde:** `fuel_strategy.py:298-300`: `_on_params_changed` (Return, FocusOut o «Recalcular») llama siempre a `auto_populate_saving_tables()`.

**Efecto:** sustituye las tablas guardadas (por ejemplo las de Bélgica: 0.2 / 0.8 / 2.0 s) por los valores fijos 0.35 / 0.80 / 1.35 s (`:603-607`). El comparador interpola el coste del ahorro con esas tablas.

Además, `_interpolate_saving_penalty` extrapola linealmente sin límite (`strategy_charts.py:392-396`, `live_control.py:1621-1625`). Con tablas que solo cubren ahorros pequeños, eso da penalizaciones absurdas por vuelta.

**Corrección:** autopoblar solo si no hay tablas o si el usuario lo pide; limitar la extrapolación (por ejemplo al punto del 20 %).

### A12. MEDIO: divisiones por cero y entradas sin validar en Combustible

**Dónde:** `fuel_strategy.py:598`, `:611`, `:648`, `:787`, `:792` (consumo 0) y `:897` (`refuel_rate` 0).

**Reproducción:**
- Consumo «0» → `ZeroDivisionError`.
- `refuel_rate=0` → `ZeroDivisionError`.
- Consumo «-1» → `viable=['39 Paradas']` y `max_laps_per_stint_20=-85`.
- Reserva 80 L con depósito de 70 L → autonomía 0 con `usable=1`.

**Corrección:** validar consumo > 0, 0 ≤ reserva < depósito y ratio > 0 antes de calcular, y mostrar el error en la interfaz.

### A13. MEDIO: proyección de vueltas del líder siempre resta todas las paradas

**Dónde:** `live_control.py:134-158`. La pérdida en boxes del líder no depende de su progreso.

**Reproducción:** en V20, con el líder ya parado 2 veces, sigue restando 74 s y proyecta 30 vueltas en vez de 31.

La 1.ª parada asume repostar el depósito completo (`tank_cap / rate`), una fórmula distinta a la de combustible (litros necesarios ÷ paradas) y a la del comparador (litros reales).

**Corrección:** restar solo las paradas que le quedan (por ejemplo un campo «paradas restantes del líder») y estimar los litros como en combustible.

### A14. BAJO-MEDIO: OLS sin protección y sin restricción a ≥ 0

**Dónde:** `tyre_strategy.py:549-566`.

**Reproducción:**
- Puntos con la misma vuelta (5 y 5) → `polyfit` avisa «poorly conditioned» y devuelve a=0.1243 con R²=0.
- Puntos decrecientes → a=-0.3404 (degradación negativa aceptada).

La documentación (08 §2.7 y 01 §3.3) dice que se exige Var(u) > 1e-9, que hay respaldo lineal y que a ≥ 0.

**Corrección:** exigir al menos 2 valores distintos de x ≥ 2; si a < 0, avisar o forzar a = 0 y recalcular n.

### A15. BAJO: una sensibilidad de peso 0 se convierte en 0.015 en Neumáticos

**Dónde:** `tyre_strategy.py:1033` (`fuel_data.get("weight_sens") or … or 0.015`). El comparador usa 0.0 correctamente. Lo mismo pasa en `live_control.py:1658` y con `car_lift_s` = 0 (`or 2.0` en todos los módulos), aunque el validador del campeonato exige > 0.

**Corrección:** usar `x if x is not None else default` en lugar de `or`.

### A16. BAJO: el plan por defecto del live es físicamente imposible en Bélgica

**Dónde:** `live_control.py:522-531`. Por defecto es 1 parada en V15, objetivo 5.65 L/v y repostaje 30 L. Al navegar no se aplica ninguna estrategia: `on_strategies_updated` (`:2378`) no llama a `_apply_selected_strategy`.

**Reproducción** (`test_05`): tras navegar, el piloto 1 tiene `num_stops=1, p1=15` aunque solo es viable «2 Paradas». Simulado, se queda sin combustible en V31.

**Corrección:** al recibir la estrategia óptima, aplicarla a los pilotos que tengan «⚡ Estrategia Óptima» seleccionada; derivar el plan por defecto de `fuel_data`.

### A17. BAJO: paradas bajo SC con coste 0.0 s y encadenables

**Dónde:** `strategy_charts.py:1816-1817`.

**Reproducción:** con SC largo (V12 × 10) la óptima hace dos paradas consecutivas (V13 y V14) con 0.0 s cada una.

El tiempo de parada bajo SC se reduce, pero no a 0 (velocidad en pitlane y tiempo estacionario). La penalización de +30 s por pitlane cerrado (`:1815`, `live_control.py:1867`) está fija en el código.

**Corrección:** modelar `t_box_sc = estacionario + max(0, pitlane_loss - (ritmo_sc - ritmo_verde) × fracción)` y llevar las constantes al perfil.

### A18. BAJO: incoherencia entre «paradas mínimas» y estrategias viables

**Dónde:** `fuel_strategy.py:886-888` y `:972`. El paso 3 calcula las paradas sin ahorro.

**Ejemplo:** GT3 120 min: «3 mín.» pero `viable_modes` incluye «2 Paradas». Con 30 L/v: «17 mín.» frente a «16 Paradas» viable. Las vueltas truncadas también se calculan con las paradas mínimas y no con las seleccionadas.

**Corrección:** etiquetarlo como «sin ahorro», o recalcular las vueltas con el número de paradas elegido.

---

## (b) Incoherencias de nombres y contratos entre módulos

| # | Dónde | Qué pasa | Corrección propuesta |
|---|---|---|---|
| B1 | `championship_data.py:598-605` | `_list_circuits` lista **todos** los `*.json`. En «God League» salen 21 «circuitos»: `Bélgica_fuel`, `Bélgica_live`, `Bélgica_strategies`, etc. Si se elige uno, se carga un JSON de combustible como circuito y se usan los valores por defecto (01:30.000, 22.5 s). | Filtrar los nombres con sufijos `_fuel`, `_tyres`, `_fuel_models`, `_tyre_models`, `_strategies` y `_live`, o exigir la clave `"lap_time"`. |
| B2 | `session_data` (`championship_data.py:919-944`) frente a lectores | Se leen claves que nunca se escriben, con un valor por defecto silencioso: `fuel_per_lap_l` (`fuel_strategy.py:1506` → 2.15; `strategy_charts.py:188` → 5.65), `safety_margin_l` (`strategy_charts.py:223` → 0.4), `weight_penalty_s_per_10l` y `weight_sens` (`strategy_charts.py:276`, `tyre_strategy.py:1033`), `fuel_models` y `tyre_models` (`strategy_charts.py:2120`, `:3125`, `:3158`). Al elegir «⚡ Modelo Base» sin `_fuel.json`, el consumo pasa a 2.15 L/v (valor del IR-18) en cualquier coche. | Añadir esas claves al perfil del circuito y a `session_data`, o eliminar las lecturas muertas. |
| B3 | Valores por defecto distintos para lo mismo | Consumo: 2.15 (fuel/tyre), 5.65 (charts/live). Reserva: 2.5 (fuel/tyre/live), 0.4 (charts). Sensibilidad: 0.015 frente a 0.150/10. Pitlane: 22.5 frente a 30.0 (`live_control.py:136`). Duración de la vuelta: 84.5. | Centralizar en un módulo `defaults.py` o, mejor, no calcular nada sin `session_data` válido. |
| B4 | Contrato `get_fuel_strategy_data` | Exporta `num_stops`, `pit1_lap`, `pit2_lap`, `cons_lap`, `safety_fuel_l`, `weight_sens`, `calc_results`, etc. La documentación (07 §3.2, 03 §6) promete `stops_count`, `stint_laps`, `pit_laps`, `fuel_per_stint`, `refuel_litres`, `pit_times` y `target_consumption`, que no existen. Cada consumidor recalcula los litros y tiempos de box por su cuenta (A5). | Exportar los stints y litros calculados y que los consumidores los usen. |
| B5 | Duplicación de la lógica de vueltas totales | Combustible: duración − paradas mínimas × (pitlane + lift + max(litros medios ÷ rate, ruedas)). Comparador: dos pasadas con la pérdida real de cada estrategia, más SC. Live: depósito lleno por parada según el modo del líder. Neumáticos: la de combustible. Coinciden en los casos sin SC probados, pero con 12 L/v salen 38 frente a 40 vueltas, y con SC 31 (live) frente a 27 (comparador). | Una única función `projected_laps(session, pit_losses, sc_time)`. |
| B6 | Duplicación de los litros en box | Neumáticos: `fuel_in_box = max(0, tank - laps*cons)` (`tyre_strategy.py:1067`) aunque el stint sea de ahorro. Combustible: `safety_l` si es de ahorro (`fuel_strategy.py:1148`, `:1372`). Comparador: simula el consumo objetivo. Diferencias pequeñas en litros y tiempo de box. | Función común `fuel_at_box(...)`. |
| B7 | Nombres de modelo | Combustible y Neumáticos usan «⚡ Modelo Base»; el Comparador, «⭐ Modelo Base» (`strategy_charts.py:100-101`). Funciona porque se comprueba con `"Modelo Base" in …`, pero las estrategias se guardan con el nombre «⭐» (es frágil). | Constante compartida `BASE_MODEL_NAME`. |
| B8 | Compuestos | Todos los módulos usan `hard` y `soft` y etiquetas fijas «Prime (Duro)» y «Alternative (Blando)» (`strategy_charts.py:53-63`, `live_control.py:988`, `tyre_strategy.py:1190-1196`). `tyre_compounds` de `session_data` no se usa (el GT3 de ejemplo con «Seco» y «Lluvia» se mostraría como Duro y Blando). | Mapear `hard`→`tyre_compounds[0]` y `soft`→`tyre_compounds[1]`. |
| B9 | Rutas de perfiles | `championship_name` y `circuit` en `session_data` son los nombres visibles (`data["name"]`, `data["circuit"]`), mientras las carpetas y ficheros usan el nombre saneado. `main.save_app_state` (`main.py:325-326`) guarda los visibles y `load_session_by_names` (`championship_data.py:1008-1016`) busca nombres de carpeta. **Reproducción** (`test_05`): con el campeonato «IMSA: GT3?» y el circuito «Daytona: Road» se guarda `_last_state` y `load_session_by_names` devuelve False, así que no se restaura al reabrir. Además, `strategy_charts.py:304`, `:349` usa la regex `[\/*?:"<>|]` (sin la barra invertida) y las demás `[\\/*?:"<>|]`. | Guardar en `session_data` también `championship_dir` y `circuit_file` (saneados) y usarlos para todas las rutas y para `_last_state`. |
| B10 | Unidades | `weight_sens` está en s/L (perfiles y código); la documentación habla de `weight_penalty_s_per_10l / 10`. `parse_clock_to_seconds` (`live_control.py:90-96`) interpreta los números ≤ 180 como minutos y los mayores como segundos: «120» → 7200 s y «200» → 200 s. | Documentar s/L y eliminar la heurística (exigir HH:MM:SS o un selector de unidad). |
| B11 | Constantes fijas que deberían venir del perfil | Consumo SC 1.80 L/v y ritmo SC × 1.40 (live). +30 s de pitlane cerrado. Ahorro máximo 0.80 y sobre-paradas 1.10. Valores fijos de autopoblado (0.35/0.80/1.35 s, rebufo −0.15/−0.28/−0.40). Base blanda = circuito − 0.450 s (`tyre_strategy.py:942`). Plan por defecto del live (5.65 L/v, V15, 30 L). El centinela `"01:24.500"` en `tyre_strategy.py:1540` sobrescribe un ritmo base real que valga exactamente eso. «Vuelta Base (70L)» fijo en `tyre_strategy.py:1604`. | Llevarlas al perfil o a constantes nombradas. |
| B12 | `_delete_circuit` (`championship_data.py:1081-1088`) | No borra `<circuito>_live.json` (`test_05`: queda `Road America_live.json`). Si se recrea un circuito con el mismo nombre, hereda la sesión en vivo. | Añadir `_live.json` a la lista. |

---

## (c) Discrepancias entre documentación y código

1. **Stubs:** los contextos 04, 05 y 09 dicen que `strategy_charts.py` y `live_control.py` son stubs. Tienen 3.562 y 2.446 líneas: optimizador, SC multitramo, rebufo, 3 pilotos y táctico.
2. **Live:** se documentan pyirsdk, un hilo `LiveTelemetryWorker`, `queue.Queue`, un overlay `overrideredirect` y `ir.set_fuel()`. **Nada de eso existe**: el live es de entrada manual (vuelta y litros) y no hay telemetría.
3. **Sliders de combustible y `_slider_dummy`:** la documentación (03 §4, 08 §2.1) describe los sliders y el componente `_slider_dummy`. En el código los sliders no se construyen (A2) y `_slider_dummy` no existe: se usa el truco `to = from + 1`.
4. **Tiempo de box:** la documentación dice `pitlane + max(litros ÷ rate, ruedas)`. El código suma además `car_lift_s` en todos los módulos (`fuel_strategy.py:898`, `:1173`; `tyre_strategy.py:1004`; `strategy_charts.py:1800`; `live_control.py:144`, `:1861`).
5. **Contratos:** los de 07 §3.1 (`race_duration_minutes`, `mandatory_compounds`, `circuit_name`, `base_lap_time_s`, `fuel_per_lap_l`, `weight_penalty_s_per_10l`) y 07 §3.2 (`stops_count`, `stint_laps`…) no coinciden con las claves reales (B2, B4). Tampoco existe el método estándar `get_strategy_data()` (07 §5) ni `on_data_updated` (04 §6).
6. **`navigate_to`:** el pseudocódigo de 07 §3.3 difiere del real (`main.py:384-461`). El real sincroniza siempre combustible, neumáticos y comparador, y además `on_tyre_strategy_updated` y `on_strategies_updated`.
7. **Arranque con salida parada:** 03 §3.1 menciona `start_delay_s` y `standing_start`, que no existen.
8. **OLS:** la documentación dice que se restringe a ≥ 0, que hay protección con Var(u) > 1e-9 y respaldo lineal. No está implementado (A14).
9. **«Mínimo 1 parada si el reglamento exige cambio»:** el código lo aplica siempre y el reglamento no es configurable (A6).
10. **Persistencia atómica (06 §5.2) y aviso por JSON corrupto (08 §4):** no hay `.tmp` + `os.replace`. Los JSON corruptos se ignoran en silencio (`except Exception: pass`) sin avisar.
11. **Árbol de perfiles:** `contexto_global` §2 no incluye `_fuel_models.json`, `_tyre_models.json`, `_strategies.json` ni `_live.json`. El borrado de circuito descrito («elimina `.json`, `_fuel.json` y `_tyres.json`») no coincide (el código borra 6 ficheros, pero no `_live`).
12. **Ejemplo de Bélgica:** 08 §2.5 cita «stints de 15.5 v → 4.51 L/v, ahorro 20.2 %» y 01 §5 «máximo 12+12=24v». Con el perfil real (reserva 0.4 L) la autonomía con ahorro es de 15 v, lo que coincide con contexto_global §5.5 (15+15) pero no con 01.
13. **`main.py`:** la cabecera dice «Dallara IR-18 | 70L max» y el pie de la barra lateral «v1.0 — Fase 1». Está desactualizado frente a la suite multivehículo.

---

## (d) Cosas menores

- `championship_data.py:711-715`, `:857`, `:938-939`: `float()` sin `.replace(",", ".")`. El validador acepta «105,5» y luego falla (`test_05`: `ValueError` al guardar el campeonato con 105,5 y el circuito con pitlane 30,5).
- Se aceptan warmups negativos (Nordschleife −1.4 / −5 s): la vuelta de salida resulta más rápida que la base. Conviene validar o avisar.
- El modelo asume que el stint 1 sale siempre con el depósito lleno, aunque la carrera sea corta: en el sprint de 20 min se llega a meta con 39.9 L. No hay opción de cargar menos combustible en la salida.
- Fuera de los casos ya vistos de 3 o más paradas, el comparador no cuenta las paradas: `simulate_strategy_for_config` (`strategy_charts.py:2139`) usa `"1" in str(raw_stops)`.
- El comparador calcula la carga de la siguiente parada con `cons_base` aunque el stint siguiente tenga vueltas de SC o rebufo, así que carga de más (`strategy_charts.py:1794`).
- `fuel_strategy.py:977`: la etiqueta «-x s/v» de la ganancia por peso es la ganancia al final de un stint de depósito completo, no un valor por vuelta.
- `_update_slider_bounds` en neumáticos usa `p1_min = max(2, …)` y combustible `max(1, …)` (`tyre_strategy.py:795` frente a `fuel_strategy.py:1030`).
- `solve_tactical_strategy` tiene el parámetro `is_first` sin usar (`live_control.py:1783`).
- `_get_leader_pit_loss_seconds` decide el modo con `"0" in mode` y `"2" in mode`, que es frágil con textos libres.
- Rendimiento (fuera de alcance, solo lo anoto): cada `navigate_to("charts")` recalcula la estrategia óptima por fuerza bruta.

---

## Lo que no he podido verificar

- **Interacción real con el ratón:** arrastrar sliders y la estabilidad de CustomTkinter al destruir widgets. Solo se ejecutaron las funciones.
- **Renderizado de Matplotlib:** solo se comprobó que no hay excepciones, no el resultado visual.
- **Fidelidad con iRacing:** reglas de pitlane cerrado y paradas bajo SC, consumo real bajo SC y ritmo del SC. Solo comprobé la coherencia interna.
- **Comportamiento del ejecutable empaquetado** (`sys.frozen`) y las rutas `_MEIPASS`.
- **Escalado DPI y zoom.**
- **Precisión física del modelo de penalización por ahorro:** depende de tablas empíricas del usuario.
