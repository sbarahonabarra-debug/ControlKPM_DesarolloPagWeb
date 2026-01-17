import json
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# =========================
# CONFIG + PERSISTENCIA
# =========================
st.set_page_config(page_title="Cronograma Plan 4 (E-Commerce + Marca + SEO)", layout="wide")

STATE_FILE = Path("cronograma_plan4_state.json")

STATUS_OPTIONS = ["Pendiente", "En proceso", "Finalizado", "Atrasado"]

# -------------------------
# TAREAS (3 carriles):
# - Web (cadena principal)
# - Marca (paralelo, por reuniones)
# - SEO (paralelo, depende de algunos hitos web)
# -------------------------
TASKS_DEFAULT = [
    ("Inicio", "t0", "T0 Kickoff + Brief", "", 1),

    # --- WEB (Anexo A / B)
    ("Base técnica", "t1a", "T1A Accesos mínimos (cliente)", "t0", 1),
    ("Base técnica", "t2", "T2 Setup plataforma + SSL base", "t1a", 2),
    ("Base técnica", "t3", "T3 Arquitectura de páginas + navegación", "t2", 2),

    ("Diseño y tienda", "t4", "T4 Diseño UI (home + tienda/producto)", "t3", 3),
    ("Diseño y tienda", "t5", "T5 Catálogo (categorías/atributos/stock)", "t4", 2),
    ("Diseño y tienda", "t6", "T6 Carrito + Checkout (flujo completo)", "t5", 2),

    ("Integraciones", "t7", "T7 Pagos (Webpay y/o Mercado Pago)", "t6", 2),
    ("Integraciones", "t8", "T8 Envíos (métodos y reglas)", "t7", 1),
    ("Integraciones", "t9", "T9 Correos transaccionales", "t8", 1),

    ("Contenido + QA", "t10", "T10 Carga inicial productos (hasta 15)", "t9", 2),
    ("Contenido + QA", "t11", "T11 QA funcional + correcciones", "t10", 2),

    ("Soporte + salida", "t12", "T12 Agente conversacional AI + FAQ base", "t11", 2),
    ("Soporte + salida", "t13", "T13 Capacitación + guía breve", "t12", 1),
    ("Soporte + salida", "t14", "T14 Publicación (Go-Live) + verificación", "t13", 1),

    # --- MARCA (asesoría negocio + identidad, paralelo)
    ("Marca", "m1", "M1 Diagnóstico + propuesta de valor", "t0", 1),
    ("Marca", "m2", "M2 Arquitectura comercial (categorías/tono/naming)", "m1", 1),
    ("Marca", "m3", "M3 Identidad V0 (provisional para avanzar UI)", "m2", 1),
    ("Marca", "m4", "M4 Identidad V1 final (logo+paleta+tipografías)", "m3", 2),

    # (opcional) si quieres trackear “insumos/identidad” sin bloquear el desarrollo web
    ("Marca", "t1b", "T1B Insumos/identidad (en reuniones)", "t0", 2),

    # --- SEO (Anexo C, paralelo)
    ("SEO", "s1", "S1 SEO técnico base (tracking + sitemap/robots)", "t2", 1),
    ("SEO", "s2", "S2 Estructura SEO (keywords + contenidos)", "t3", 1),
    ("SEO", "s3", "S3 On-page (Home + categoría + producto)", "t4", 2),
    ("SEO", "s4", "S4 Post Go-Live (indexación + verificación)", "t14", 1),
]


def default_df() -> pd.DataFrame:
    df = pd.DataFrame(
        TASKS_DEFAULT,
        columns=["Fase", "ID", "Tarea", "Depende_de", "Duración (días hábiles)"]
    )
    df["Estado"] = "Pendiente"
    df["Desviación (días hábiles)"] = 0  # + atraso, - adelanto
    return df


def migrate_df(loaded_df: pd.DataFrame) -> pd.DataFrame:
    """
    Migra un estado guardado (que puede venir con tareas antiguas)
    hacia el set actual (TASKS_DEFAULT), manteniendo:
    - Estado
    - Desviación
    - Duración (si el usuario la ajustó)
    y preservando tareas extra del usuario (si existieran).
    """
    base = default_df()

    # Normaliza columnas esperadas
    if "Desviación (días hábiles)" not in loaded_df.columns:
        loaded_df = loaded_df.copy()
        loaded_df["Desviación (días hábiles)"] = 0

    # Índices por ID
    loaded_by_id = {str(r["ID"]): r for _, r in loaded_df.iterrows()}
    base_ids = set(base["ID"].astype(str).tolist())

    # Copia estado / duración / desviación para IDs que existan en ambos
    for i in range(len(base)):
        tid = str(base.loc[i, "ID"])
        if tid in loaded_by_id:
            r = loaded_by_id[tid]
            # conservar ajustes del usuario
            if "Estado" in r:
                base.loc[i, "Estado"] = str(r["Estado"])
            if "Desviación (días hábiles)" in r:
                try:
                    base.loc[i, "Desviación (días hábiles)"] = int(r["Desviación (días hábiles)"])
                except Exception:
                    base.loc[i, "Desviación (días hábiles)"] = 0
            if "Duración (días hábiles)" in r:
                try:
                    base.loc[i, "Duración (días hábiles)"] = int(r["Duración (días hábiles)"])
                except Exception:
                    pass

    # Si el usuario tenía tareas “custom” que no están en el base, las anexamos
    extras = loaded_df[~loaded_df["ID"].astype(str).isin(base_ids)].copy()
    if not extras.empty:
        needed_cols = ["Fase", "ID", "Tarea", "Depende_de", "Duración (días hábiles)", "Estado", "Desviación (días hábiles)"]
        for c in needed_cols:
            if c not in extras.columns:
                extras[c] = "" if c in ["Fase", "ID", "Tarea", "Depende_de", "Estado"] else 0
        extras = extras[needed_cols]
        base = pd.concat([base, extras], ignore_index=True)

    return base


def load_state():
    if not STATE_FILE.exists():
        return None
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        df = pd.DataFrame(raw["tasks"])

        needed = {"Fase", "ID", "Tarea", "Depende_de", "Duración (días hábiles)", "Estado"}
        if not needed.issubset(set(df.columns)):
            return None

        # retro-compat: si el json anterior no tenía desviación
        if "Desviación (días hábiles)" not in df.columns:
            df["Desviación (días hábiles)"] = 0

        start_iso = raw.get("start_date", date.today().isoformat())
        excludes_weekends = bool(raw.get("excludes_weekends", True))

        # MIGRACIÓN a estructura vigente
        df = migrate_df(df)

        return df, date.fromisoformat(start_iso), excludes_weekends
    except Exception:
        return None


def save_state(df: pd.DataFrame, start: date, excludes_weekends: bool):
    payload = {
        "start_date": start.isoformat(),
        "excludes_weekends": bool(excludes_weekends),
        "tasks": df.to_dict(orient="records"),
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def init_state():
    loaded = load_state()
    if loaded is None:
        st.session_state["tasks_df"] = default_df()
        st.session_state["start_date"] = date.today()
        st.session_state["excludes_weekends"] = True
        save_state(st.session_state["tasks_df"], st.session_state["start_date"], st.session_state["excludes_weekends"])
    else:
        df, sd, ew = loaded
        st.session_state["tasks_df"] = df
        st.session_state["start_date"] = sd
        st.session_state["excludes_weekends"] = ew


if "tasks_df" not in st.session_state:
    init_state()


# =========================
# REGLAS DE DEPENDENCIA
# =========================
def get_status(df: pd.DataFrame, task_id: str) -> str | None:
    m = df.loc[df["ID"] == task_id, "Estado"]
    return None if m.empty else str(m.iloc[0])


def has_dependents_in_progress_or_done(df: pd.DataFrame, task_id: str) -> bool:
    deps = df[df["Depende_de"] == task_id]
    if deps.empty:
        return False
    return any(deps["Estado"].isin(["En proceso", "Finalizado"]))


def can_set_status(df: pd.DataFrame, task_id: str, new_status: str) -> tuple[bool, str]:
    row = df[df["ID"] == task_id]
    if row.empty:
        return False, "Tarea no encontrada."

    dep = str(row["Depende_de"].iloc[0]).strip()
    current = str(row["Estado"].iloc[0])

    # No avanzar si dependencia no está finalizada
    if dep:
        dep_status = get_status(df, dep)
        if new_status in ["En proceso", "Finalizado", "Atrasado"] and dep_status != "Finalizado":
            return False, f"No puedes marcar esta tarea como '{new_status}' porque depende de '{dep}' y aún no está Finalizado."

    # Si ya hay tareas hijas en proceso/finalizadas, no permitir que esta baje de Finalizado
    if current == "Finalizado" and new_status != "Finalizado":
        if has_dependents_in_progress_or_done(df, task_id):
            return False, "No puedes cambiar esta tarea desde 'Finalizado' porque hay tareas posteriores que ya están En proceso o Finalizado."

    if new_status not in STATUS_OPTIONS:
        return False, "Estado inválido."

    return True, ""


def apply_status(df: pd.DataFrame, task_id: str, new_status: str) -> tuple[pd.DataFrame, bool, str]:
    ok, msg = can_set_status(df, task_id, new_status)
    if not ok:
        return df, False, msg

    idx = df.index[df["ID"] == task_id]
    if len(idx) != 1:
        return df, False, "No se pudo actualizar (ID duplicado o inexistente)."

    df.loc[idx[0], "Estado"] = new_status

    # regla suave: si marcas "Atrasado" y la desviación es 0, setear a +1 por defecto
    if new_status == "Atrasado":
        try:
            if int(df.loc[idx[0], "Desviación (días hábiles)"]) == 0:
                df.loc[idx[0], "Desviación (días hábiles)"] = 1
        except Exception:
            df.loc[idx[0], "Desviación (días hábiles)"] = 1

    return df, True, ""


# =========================
# CÁLCULO DE FECHAS (para mostrar fin de proyecto)
# =========================
def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=sáb, 6=dom


def next_business_day(d: date, exclude_weekends: bool) -> date:
    if not exclude_weekends:
        return d
    while is_weekend(d):
        d += timedelta(days=1)
    return d


def add_business_days(start: date, n: int, exclude_weekends: bool) -> date:
    """
    Devuelve la fecha final al sumar n días hábiles a start.
    Convención: si n=1, termina el mismo día (start).
    """
    start = next_business_day(start, exclude_weekends)
    if n <= 1:
        return start

    d = start
    remaining = n - 1
    while remaining > 0:
        d += timedelta(days=1)
        if exclude_weekends and is_weekend(d):
            continue
        remaining -= 1
    return d


def next_day_after(end_date: date, exclude_weekends: bool) -> date:
    d = end_date + timedelta(days=1)
    return next_business_day(d, exclude_weekends)


def effective_duration(row: pd.Series) -> int:
    base = int(row["Duración (días hábiles)"])
    delta = int(row.get("Desviación (días hábiles)", 0))
    return max(1, base + delta)


def build_schedule(df_in: pd.DataFrame, kickoff: date, exclude_weekends: bool) -> pd.DataFrame:
    """
    Calcula inicio/fin por dependencia, usando duración efectiva (base + desviación).
    Propaga atrasos/adelantos automáticamente.
    """
    df = df_in.copy()
    df["Inicio"] = pd.NaT
    df["Fin"] = pd.NaT
    df["Duración efectiva (días hábiles)"] = df.apply(effective_duration, axis=1)

    by_id = {r["ID"]: i for i, r in df.iterrows()}

    # asume dependencias simples (una por tarea). resuelve por iteraciones.
    unresolved = set(df["ID"].tolist())
    safety = 0

    while unresolved and safety < 999:
        safety += 1
        progressed = False

        for tid in list(unresolved):
            i = by_id[tid]
            dep = str(df.loc[i, "Depende_de"]).strip()

            if tid == "t0":
                start = next_business_day(kickoff, exclude_weekends)
                dur = int(df.loc[i, "Duración efectiva (días hábiles)"])
                end = add_business_days(start, dur, exclude_weekends)
                df.loc[i, "Inicio"] = pd.Timestamp(start)
                df.loc[i, "Fin"] = pd.Timestamp(end)
                unresolved.remove(tid)
                progressed = True
                continue

            if dep:
                if dep in unresolved:
                    continue  # aún no calculamos el dep
                dep_idx = by_id.get(dep)
                if dep_idx is None:
                    # dependencia no existe -> tratar como sin dependencia
                    start = next_business_day(kickoff, exclude_weekends)
                else:
                    dep_end = df.loc[dep_idx, "Fin"]
                    if pd.isna(dep_end):
                        continue
                    start = next_day_after(dep_end.date(), exclude_weekends)
            else:
                start = next_business_day(kickoff, exclude_weekends)

            dur = int(df.loc[i, "Duración efectiva (días hábiles)"])
            end = add_business_days(start, dur, exclude_weekends)

            df.loc[i, "Inicio"] = pd.Timestamp(start)
            df.loc[i, "Fin"] = pd.Timestamp(end)
            unresolved.remove(tid)
            progressed = True

        if not progressed:
            break

    return df


# =========================
# UI
# =========================
st.title("Cronograma Plan 4 — Web + Marca + SEO (Carta Gantt)")
st.caption("Desviación en días hábiles: +N atrasa y propaga el atraso; -N adelanta y propaga el adelanto.")

t1, t2, t3 = st.columns([1.2, 1.2, 2.6])
with t1:
    start_date = st.date_input("Fecha de inicio (Kickoff)", value=st.session_state["start_date"])
with t2:
    excludes_weekends = st.toggle("Excluir fines de semana", value=st.session_state["excludes_weekends"])
with t3:
    if st.button("Resetear cronograma", use_container_width=True):
        st.session_state["tasks_df"] = default_df()
        st.session_state["start_date"] = date.today()
        st.session_state["excludes_weekends"] = True
        save_state(st.session_state["tasks_df"], st.session_state["start_date"], st.session_state["excludes_weekends"])
        st.rerun()

st.session_state["start_date"] = start_date
st.session_state["excludes_weekends"] = excludes_weekends

df = st.session_state["tasks_df"].copy()

# ---- Control didáctico por botones
st.subheader("Control rápido (botones + desviación)")
c1, c2, c3, c4, c5 = st.columns([2.6, 1, 1, 1, 1.2])

with c1:
    task_pick = st.selectbox(
        "Selecciona una tarea",
        options=df["ID"].tolist(),
        format_func=lambda tid: f"{tid} — {df.loc[df['ID']==tid, 'Tarea'].values[0]}",
    )

picked_row = df[df["ID"] == task_pick].iloc[0]
dep = str(picked_row["Depende_de"]).strip()
dep_status = get_status(df, dep) if dep else None

block_advance = bool(dep) and dep_status != "Finalizado"

with c5:
    dev_val = int(picked_row.get("Desviación (días hábiles)", 0))
    dev_new = st.number_input(
        "Desviación (días hábiles)",
        value=dev_val,
        step=1,
        help="Positivo = atraso (empuja el resto). Negativo = adelanto (adelanta el resto).",
    )

# guardar desviación si cambió
if dev_new != dev_val:
    df.loc[df["ID"] == task_pick, "Desviación (días hábiles)"] = int(dev_new)
    st.session_state["tasks_df"] = df
    save_state(df, start_date, excludes_weekends)

with c2:
    if st.button("En proceso", use_container_width=True, disabled=block_advance):
        df2, ok, msg = apply_status(df.copy(), task_pick, "En proceso")
        if ok:
            st.session_state["tasks_df"] = df2
            save_state(df2, start_date, excludes_weekends)
            st.rerun()
        else:
            st.warning(msg)

with c3:
    if st.button("Finalizado", use_container_width=True, disabled=block_advance):
        df2, ok, msg = apply_status(df.copy(), task_pick, "Finalizado")
        if ok:
            st.session_state["tasks_df"] = df2
            save_state(df2, start_date, excludes_weekends)
            st.rerun()
        else:
            st.warning(msg)

with c4:
    if st.button("Atrasado", use_container_width=True, disabled=block_advance):
        df2, ok, msg = apply_status(df.copy(), task_pick, "Atrasado")
        if ok:
            st.session_state["tasks_df"] = df2
            save_state(df2, start_date, excludes_weekends)
            st.rerun()
        else:
            st.warning(msg)

info_cols = st.columns(4)
info_cols[0].metric("Estado actual", str(picked_row["Estado"]))
info_cols[1].metric("Fase", str(picked_row["Fase"]))
info_cols[2].metric("Depende de", dep if dep else "—")
info_cols[3].metric("Estado dependencia", dep_status if dep else "—")

st.divider()

# ---- Tabla editable con validación (dependencias + persistencia)
st.subheader("Tabla de tareas (editable)")
prev_df = st.session_state["tasks_df"].copy()

edited = st.data_editor(
    prev_df,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Estado": st.column_config.SelectboxColumn("Estado", options=STATUS_OPTIONS, required=True),
        "Duración (días hábiles)": st.column_config.NumberColumn("Duración (días hábiles)", min_value=1, step=1),
        "Desviación (días hábiles)": st.column_config.NumberColumn("Desviación (días hábiles)", step=1),
    },
)

validated = edited.copy()
warnings = []

for i in range(len(validated)):
    tid = str(validated.loc[i, "ID"])
    old_status = str(prev_df.loc[i, "Estado"])
    new_status = str(validated.loc[i, "Estado"])

    # asegurar int en desviación
    try:
        validated.loc[i, "Desviación (días hábiles)"] = int(validated.loc[i, "Desviación (días hábiles)"])
    except Exception:
        validated.loc[i, "Desviación (días hábiles)"] = 0

    if new_status != old_status:
        ok, msg = can_set_status(validated, tid, new_status)
        if not ok:
            validated.loc[i, "Estado"] = old_status
            warnings.append(f"{tid}: {msg}")

if warnings:
    for w in warnings[:6]:
        st.warning(w)
    if len(warnings) > 6:
        st.warning(f"Se omitieron {len(warnings)-6} advertencias más.")
else:
    st.session_state["tasks_df"] = validated
    save_state(validated, start_date, excludes_weekends)

# =========================
# SCHEDULE + FECHA FIN PROYECTO
# =========================
schedule_df = build_schedule(st.session_state["tasks_df"], start_date, excludes_weekends)

project_end = schedule_df["Fin"].dropna().max()
project_end_date = project_end.date() if not pd.isna(project_end) else None

m1, m2, m3 = st.columns([1.4, 1.4, 2.2])
m1.metric("Inicio proyecto", start_date.isoformat())
m2.metric("Fin proyecto (ajustado)", project_end_date.isoformat() if project_end_date else "—")
m3.caption("El fin se recalcula con Duración + Desviación por cada hito, y se propaga por dependencias.")

with st.expander("Ver tabla con fechas calculadas"):
    show = schedule_df[[
        "Fase", "ID", "Tarea", "Depende_de", "Estado",
        "Duración (días hábiles)", "Desviación (días hábiles)", "Duración efectiva (días hábiles)",
        "Inicio", "Fin"
    ]].copy()
    show["Inicio"] = show["Inicio"].dt.date
    show["Fin"] = show["Fin"].dt.date
    st.dataframe(show, use_container_width=True)

# =========================
# GANTT (Mermaid) + ESTILO
# =========================
def status_flag(status: str) -> str:
    if status == "En proceso":
        return "active, "
    if status == "Finalizado":
        return "done, "
    if status == "Atrasado":
        return "crit, "
    return ""


def build_mermaid(df_in: pd.DataFrame, kickoff_iso: str, exclude_weekends: bool) -> str:
    lines = []
    lines.append("gantt")
    lines.append("    title Cronograma Plan 4 (Web + Marca + SEO)")
    lines.append("    dateFormat  YYYY-MM-DD")
    lines.append("    axisFormat  %d-%m")
    if exclude_weekends:
        lines.append("    excludes    weekends")
    lines.append("")

    for fase in df_in["Fase"].unique():
        lines.append(f"    section {fase}")
        subset = df_in[df_in["Fase"] == fase]
        for _, r in subset.iterrows():
            flag = status_flag(str(r["Estado"]))
            tid = str(r["ID"]).strip()
            name = str(r["Tarea"]).strip()
            dep = str(r["Depende_de"]).strip()
            dur_eff = max(1, int(r["Duración (días hábiles)"]) + int(r.get("Desviación (días hábiles)", 0)))

            if tid == "t0":
                lines.append(f"    {name} :{flag}{tid}, {kickoff_iso}, {dur_eff}d")
            else:
                if dep:
                    lines.append(f"    {name} :{flag}{tid}, after {dep}, {dur_eff}d")
                else:
                    lines.append(f"    {name} :{flag}{tid}, {kickoff_iso}, {dur_eff}d")

        lines.append("")
    return "\n".join(lines)


mermaid_txt = build_mermaid(st.session_state["tasks_df"], start_date.isoformat(), excludes_weekends)

html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    body {{
      margin: 0; padding: 0; background: transparent;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    }}
    .wrap {{ padding: 10px; }}
    .card {{
      background: white;
      border-radius: 18px;
      padding: 14px 14px 6px 14px;
      box-shadow: 0 18px 50px rgba(2, 8, 23, 0.08);
      border: 1px solid rgba(2, 8, 23, 0.06);
    }}
    .legend {{
      display:flex; gap:10px; flex-wrap: wrap;
      padding: 6px 4px 12px 4px;
      font-size: 12px; color: rgba(15, 23, 42, 0.75);
      align-items:center;
    }}
    .pill {{
      display:flex; gap:8px; align-items:center;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(2, 8, 23, 0.08);
      background: rgba(248, 250, 252, 0.9);
      font-weight: 600;
    }}
    .dot {{ width: 10px; height: 10px; border-radius: 999px; }}
    .mermaid svg {{ width: 100%; height: auto; }}
    .mermaid .task rect {{ rx: 7px; ry: 7px; }}
    .mermaid .taskText {{ font-weight: 600; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="legend">
        <span class="pill"><span class="dot" style="background:#94A3B8"></span>Pendiente</span>
        <span class="pill"><span class="dot" style="background:#3B82F6"></span>En proceso</span>
        <span class="pill"><span class="dot" style="background:#22C55E"></span>Finalizado</span>
        <span class="pill"><span class="dot" style="background:#EF4444"></span>Atrasado</span>
        <span class="pill"><span class="dot" style="background:#F59E0B"></span>Hoy</span>
      </div>

      <div class="mermaid">
{mermaid_txt}
      </div>
    </div>
  </div>

  <script>
    mermaid.initialize({{
      startOnLoad: true,
      theme: "base",
      securityLevel: "loose",
      themeVariables: {{
        fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
        primaryColor: "#F8FAFC",
        primaryTextColor: "#0F172A",
        primaryBorderColor: "rgba(2, 8, 23, 0.10)",
        lineColor: "rgba(2, 8, 23, 0.12)",
        textColor: "#0F172A",

        taskTextColor: "#0F172A",
        taskTextOutsideColor: "#0F172A",

        activeTaskColor: "#3B82F6",
        activeTaskBorderColor: "#2563EB",
        activeTaskTextColor: "#0B1220",

        doneTaskColor: "#22C55E",
        doneTaskBorderColor: "#16A34A",
        doneTaskTextColor: "#0B1220",

        critTaskColor: "#EF4444",
        critTaskBorderColor: "#DC2626",
        critTaskTextColor: "#0B1220",
      }},
      gantt: {{
        barHeight: 22,
        barGap: 10,
        topPadding: 35,
        leftPadding: 240,
        rightPadding: 20,
        gridLineStartPadding: 30,
        fontSize: 12,
        numberSectionStyles: 2,
        todayMarker: {{
          stroke: "#F59E0B",
          strokeWidth: "2px",
          shape: "dashed"
        }}
      }}
    }});
  </script>
</body>
</html>
"""

st.subheader("Carta Gantt (visual)")
components.html(html, height=760, scrolling=True)

with st.expander("Ver Mermaid (texto)"):
    st.code(mermaid_txt, language="text")
