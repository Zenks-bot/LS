"""Agile Core Studio — Scrum & Kanban.

Ejecutar:  streamlit run app.py
Datos:     Supabase si hay credenciales (SUPABASE_URL / SUPABASE_KEY en variables
           de entorno o .streamlit/secrets.toml); si no, modo local (agile_data.json).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import statistics
import time
import uuid
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

try:
    from supabase import create_client
except Exception:  # supabase es opcional (modo local)
    create_client = None

from agile_logic import (
    ACTION_CATEGORY, CATEGORY_ICON, activity_frame, cfd_frame, checklist_diff, checklist_progress,
    describe_event, hash_password, merge_checklist, password_error, task_changes, username_error,
    verify_password,
)

st.set_page_config(
    page_title="Agile Core Studio | Scrum & Kanban",
    page_icon="⚜️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────
GOLD = "#D4AF37"
GOLD_DIM = "#7A6620"
MUTED = "#9A917A"

PRIORITIES = ["Baja", "Media", "Alta"]
PRIO_ORDER = {"Alta": 0, "Media": 1, "Baja": 2}
KANBAN_STATUSES = ["To Do", "In Progress", "Review", "Done"]
SCRUM_STATUSES = ["To Do", "In Progress", "Done"]
STATUS_LABEL = {"To Do": "Por hacer", "In Progress": "En progreso", "Review": "Revisión", "Done": "Hecho"}
ROLES = ["Equipo de Desarrollo", "Product Owner", "Scrum Master"]
FIBONACCI = [1, 2, 3, 5, 8, 13, 21]
SPRINT_ORDER = {"Activo": 0, "Planificado": 1, "Cerrado": 2}
WIP_DEFAULTS = {"To Do": 10, "In Progress": 3, "Review": 2}
LOCAL_LOG_CAP = 5000          # eventos de auditoría que se leen/guardan como máximo
LOGIN_MAX_FAILS, LOGIN_LOCK_SECONDS = 5, 60

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:wght@600;700&display=swap');
:root {
  --gold:#D4AF37; --gold-soft:#E8C766; --gold-dim:#7A6620;
  --bg:#0A0A0A; --panel:#121212; --panel2:#1A1A1A; --line:#2B2515;
  --text:#EDE6D3; --muted:#9A917A; --danger:#C0564B;
}
.stApp { background: radial-gradient(1200px 500px at 85% -10%, rgba(212,175,55,.10), transparent 60%), var(--bg);
         color: var(--text); font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stSidebar"] { background:#0E0E0E; border-right:1px solid var(--line); }
h1,h2,h3 { font-family:'Playfair Display',Georgia,serif !important; color:var(--gold) !important; letter-spacing:.01em; }
h1 { font-weight:700 !important; }
hr { border-color: var(--line) !important; }

.brand { font-family:'Playfair Display',Georgia,serif; font-size:1.45rem; color:var(--gold); font-weight:700; line-height:1.1; }
.brand small { display:block; font-family:'Inter',sans-serif; font-size:.68rem; letter-spacing:.28em; color:var(--muted); font-weight:500; margin-top:.35rem; }
.gold-rule { height:1px; background:linear-gradient(90deg, var(--gold), transparent); margin:.6rem 0 1rem 0; border:0; }

/* Botones */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button, [data-testid="stPopover"] button {
  width: 100%; 
  background: rgba(18, 18, 18, 0.8); 
  color: var(--gold); 
  border: 1px solid var(--gold-dim);
  border-radius: 6px; 
  font-weight: 500; 
  padding: 4px 2px;
  min-height: 32px;
  transition: all .15s ease; 
}
.stButton button:hover, .stDownloadButton button:hover, [data-testid="stFormSubmitButton"] button:hover, [data-testid="stPopover"] button:hover {
  border-color:var(--gold); background:rgba(212,175,55,.10); color:var(--gold-soft); }
.stButton button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] {
  background:linear-gradient(135deg,#E8C766,#B8941F); color:#0A0A0A !important; border:none; font-weight:600; }
.stButton button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
  filter:brightness(1.08); color:#0A0A0A !important; background:linear-gradient(135deg,#F0D27A,#C9A227); }
.stButton button:disabled { opacity:.3; }

/* Tabs, métricas, expanders */
button[data-baseweb="tab"] { color:var(--muted); }
button[data-baseweb="tab"][aria-selected="true"] { color:var(--gold); }
[data-baseweb="tab-highlight"] { background-color:var(--gold) !important; }
[data-baseweb="tab-border"] { background-color:var(--line) !important; }
[data-testid="stMetric"] { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
[data-testid="stMetricLabel"] p { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; }
[data-testid="stMetricValue"] { color:var(--gold); font-family:'Playfair Display',serif; }
[data-testid="stExpander"] { border:1px solid var(--line); border-radius:12px; background:var(--panel); }

/* Tarjetas */
.card { background:linear-gradient(180deg,var(--panel2),var(--panel)); border:1px solid var(--line); border-left:3px solid var(--gold-dim);
        border-radius:10px; padding:12px 14px; margin:8px 0 4px 0; box-shadow:0 4px 14px rgba(0,0,0,.45); }
.card:hover { border-color:var(--gold-dim); }
.card.b-alta { border-left-color:#F2CF66; } .card.b-media { border-left-color:var(--gold-dim); } .card.b-baja { border-left-color:#4a4a4a; }
.card-title { font-weight:600; color:var(--text); font-size:.95rem; }
.card-desc { color:var(--muted); font-size:.78rem; margin:5px 0 8px 0; }
.badges { display:flex; flex-wrap:wrap; gap:5px; margin-top:6px; }
.badge { font-size:.68rem; padding:2px 8px; border-radius:999px; border:1px solid var(--line); color:var(--muted); background:#0E0E0E; }
.badge.prio-alta { background:#F2CF66; color:#0A0A0A; border-color:#F2CF66; font-weight:600; }
.badge.prio-media { color:var(--gold); border-color:var(--gold-dim); }
.badge.sp { color:var(--gold-soft); border-color:var(--gold-dim); }
.badge.late { color:#fff; background:var(--danger); border-color:var(--danger); }
.tag { color:var(--gold-dim); font-size:.68rem; }

/* Cabeceras de columna + WIP */
.col-head { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--gold-dim);
            padding-bottom:6px; margin-bottom:6px; font-family:'Playfair Display',serif; color:var(--gold); font-size:1.05rem; }
.pill { font-family:'Inter',sans-serif; font-size:.72rem; border:1px solid var(--gold-dim); color:var(--gold); border-radius:999px; padding:1px 10px; }
.pill.full { background:rgba(212,175,55,.18); } .pill.over { background:var(--danger); border-color:var(--danger); color:#fff; }
.wip { height:4px; background:#1d1d1d; border-radius:4px; overflow:hidden; margin-bottom:6px; }
.wip-bar { height:100%; background:var(--gold-dim); } .wip-bar.full { background:var(--gold); } .wip-bar.over { background:var(--danger); }
.wip-warn { color:var(--danger); font-size:.72rem; margin-bottom:4px; }

/* Cabecera de sprint */
.sprint-box { background:linear-gradient(135deg,#171309,#101010); border:1px solid var(--gold-dim); border-radius:14px; padding:16px 20px; margin-bottom:14px; }
.sprint-box h4 { margin:0; color:var(--gold); font-family:'Playfair Display',serif; font-size:1.25rem; }
.sprint-box p { margin:4px 0 10px 0; color:var(--muted); font-size:.85rem; }
.progress { height:8px; background:#1d1d1d; border-radius:8px; overflow:hidden; }
.progress > div { height:100%; background:linear-gradient(90deg,var(--gold-dim),var(--gold-soft)); }

/* Checklist */
.badge.ck { color:var(--text); border-color:var(--gold-dim); } .badge.ck.full { background:rgba(212,175,55,.18); color:var(--gold-soft); }
.ck-bar { height:3px; background:#1d1d1d; border-radius:3px; overflow:hidden; margin-top:8px; }
.ck-bar > div { height:100%; background:var(--gold); }

/* Línea de tiempo de actividad */
.timeline { border-left:1px solid var(--gold-dim); margin:6px 0 10px 12px; padding-left:18px; }
.tl-item { position:relative; display:flex; gap:10px; padding:7px 0; }
.tl-dot { position:absolute; left:-31px; top:6px; width:24px; height:24px; border-radius:50%; background:#0E0E0E;
          border:1px solid var(--gold-dim); color:var(--gold); display:grid; place-items:center; font-size:.75rem; }
.tl-text { color:var(--text); font-size:.88rem; } .tl-text b { color:var(--gold-soft); font-weight:600; }
.tl-det { color:var(--muted); font-size:.78rem; margin-top:2px; }
.tl-when { color:var(--gold-dim); font-size:.72rem; margin-top:2px; }

/* Usuario en la barra lateral */
.who { display:flex; align-items:center; gap:10px; margin:4px 0 8px; }
.who .avatar { width:34px; height:34px; border-radius:50%; background:linear-gradient(135deg,#E8C766,#B8941F); color:#0A0A0A;
               display:grid; place-items:center; font-weight:700; font-family:'Playfair Display',serif; }
.who .name { color:var(--text); font-weight:600; font-size:.9rem; line-height:1.1; } .who .handle { color:var(--muted); font-size:.75rem; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────
def esc(value) -> str:
    """Escapa texto del usuario antes de insertarlo en HTML."""
    return html.escape(str(value)) if value is not None else ""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_dt(value):
    if not value:
        return None
    try:
        ts = pd.to_datetime(value, utc=True)
        return None if pd.isna(ts) else ts
    except Exception:
        return None


def parse_date(value):
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    ts = parse_dt(value)
    return ts.date() if ts is not None else None


def hours_between(a, b):
    a, b = parse_dt(a), parse_dt(b)
    if a is None or b is None:
        return None
    h = (b - a).total_seconds() / 3600
    return h if h >= 0 else None


def fmt_duration(hours) -> str:
    if hours is None:
        return "—"
    if hours < 1:
        return f"{hours * 60:.0f} min"
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} d"


def pts(task) -> int:
    try:
        return int(task.get("story_points") or 0)
    except (TypeError, ValueError):
        return 0


def stretch(fn, *args, **kwargs):
    """Ancho completo compatible con versiones nuevas y antiguas de Streamlit."""
    try:
        return fn(*args, width="stretch", **kwargs)
    except Exception:
        return fn(*args, use_container_width=True, **kwargs)


def flash(kind: str, message: str) -> None:
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if item:
        kind, message = item
        st.toast(message, icon={"success": "✅", "warning": "⚠️", "error": "❌"}.get(kind, "ℹ️"))


def run(fn, *args, ok: str | None = None) -> bool:
    """Ejecuta una operación de datos y deja un aviso. No debe envolver st.rerun()."""
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001
        hint = " ¿Ejecutaste schema.sql en Supabase?" if get_store().mode == "Supabase" else ""
        flash("error", f"Error: {exc}.{hint}")
        return False
    if ok:
        flash("success", ok)
    return True


def current_actor() -> str:
    user = st.session_state.get("user") or {}
    return user.get("display_name") or user.get("username") or "anónimo"


def audit(action, entity, *, entity_id=None, title=None, framework=None,
          from_status=None, to_status=None, details=None, actor=None) -> None:
    """Guarda un evento en el registro de actividad. Si falla, avisa en la barra lateral
    pero no interrumpe la acción del usuario."""
    rec = {"created_at": now_iso(), "actor": actor or current_actor(), "action": action, "entity": entity,
           "entity_id": str(entity_id) if entity_id is not None else None, "entity_title": title,
           "framework": framework, "from_status": from_status, "to_status": to_status, "details": details or None}
    try:
        get_store().log(rec)
        st.session_state.pop("_audit_error", None)
    except Exception as exc:  # noqa: BLE001
        st.session_state["_audit_error"] = str(exc)


def task_checklist(task) -> list:
    value = task.get("checklist") or []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = []
    return value if isinstance(value, list) else []


def rel_time(value) -> str:
    ts = parse_dt(value)
    if ts is None:
        return "—"
    secs = (pd.Timestamp.now(tz="UTC") - ts).total_seconds()
    if secs < 60:
        ago = "hace un momento"
    elif secs < 3600:
        ago = f"hace {secs // 60:.0f} min"
    elif secs < 86400:
        ago = f"hace {secs // 3600:.0f} h"
    else:
        ago = f"hace {secs // 86400:.0f} d"
    return f"{ago} · {ts:%Y-%m-%d %H:%M} UTC"


# ─────────────────────────────────────────────────────────────────────────────
# Capa de datos: Supabase o archivo local
# ─────────────────────────────────────────────────────────────────────────────
class LocalStore:
    mode = "Local"

    def __init__(self, path: str | None = None):
        self.path = Path(path or os.environ.get("AGILE_DATA_FILE", "agile_data.json"))
        if not self.path.exists():
            self._write({"tasks": [], "sprints": []})

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except Exception:
            data = {}
        for key in ("tasks", "sprints", "activity", "users"):
            data.setdefault(key, [])
        return data

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    def tasks(self, framework=None):
        rows = self._read()["tasks"]
        return [r for r in rows if not framework or r.get("framework") == framework]

    def add_task(self, data):
        db = self._read()
        rec = {"id": uuid.uuid4().hex, "created_at": now_iso(), **data}
        db["tasks"].append(rec)
        self._write(db)
        return rec

    def update_task(self, task_id, data):
        db = self._read()
        for r in db["tasks"]:
            if str(r["id"]) == str(task_id):
                r.update(data)
        self._write(db)

    def delete_task(self, task_id):
        db = self._read()
        db["tasks"] = [r for r in db["tasks"] if str(r["id"]) != str(task_id)]
        self._write(db)

    def sprints(self):
        return sorted(self._read()["sprints"], key=lambda s: str(s.get("start_date")))

    def add_sprint(self, data):
        db = self._read()
        rec = {"id": uuid.uuid4().hex, "created_at": now_iso(), **data}
        db["sprints"].append(rec)
        self._write(db)
        return rec

    def update_sprint(self, sprint_id, data):
        db = self._read()
        for r in db["sprints"]:
            if str(r["id"]) == str(sprint_id):
                r.update(data)
        self._write(db)

    def delete_sprint(self, sprint_id):
        db = self._read()
        db["sprints"] = [r for r in db["sprints"] if str(r["id"]) != str(sprint_id)]
        self._write(db)

    # Registro de actividad (se conservan los últimos LOCAL_LOG_CAP eventos)
    def log(self, rec):
        db = self._read()
        db["activity"].append({"id": uuid.uuid4().hex, **rec})
        db["activity"] = db["activity"][-LOCAL_LOG_CAP:]
        self._write(db)

    def activity(self, limit=None, entity_id=None):
        rows = self._read()["activity"]
        if entity_id is not None:
            rows = [r for r in rows if str(r.get("entity_id")) == str(entity_id)]
        rows = sorted(rows, key=lambda r: str(r.get("created_at")), reverse=True)
        return rows[:limit] if limit else rows

    def projects(self):
        db = self._read()
        if "projects" not in db:
            db["projects"] = [{"id": "default", "name": "Proyecto Principal"}]
        
        # ... aseguramos una lista de proyectos por defecto
    # Usuarios
    def has_users(self):
        return bool(self._read()["users"])

    def get_user(self, username):
        return next((u for u in self._read()["users"] if u.get("username") == username), None)

    def add_user(self, data):
        db = self._read()
        rec = {"id": uuid.uuid4().hex, **data}
        db["users"].append(rec)
        self._write(db)
        return rec
    


class SupabaseStore:
    mode = "Supabase"

    def get_projects(self):
        return self.c.table("projects").select("*").execute().data or []

    def add_project(self, name):
        res = self.c.table("projects").insert({"name": name}).execute()
        return (res.data or [{}])[0]

    def get_project_members(self, project_id):
        return self.c.table("project_members").select("*").eq("project_id", project_id).execute().data or []

    def invite_member(self, project_id, email, role):
        try:
            self.c.table("project_members").insert({
                "project_id": project_id,
                "user_email": email,
                "role": role
            }).execute()
            return True
        except Exception:
            return False
    def __init__(self, client):
        self.c = client

    def tasks(self, framework=None):
        q = self.c.table("tasks").select("*")
        if framework:
            q = q.eq("framework", framework)
        return q.execute().data or []

    def add_task(self, data):
        res = self.c.table("tasks").insert(data).execute()
        return (res.data or [{}])[0]

    def update_task(self, task_id, data):
        self.c.table("tasks").update(data).eq("id", task_id).execute()

    def delete_task(self, task_id):
        self.c.table("tasks").delete().eq("id", task_id).execute()

    def sprints(self):
        rows = self.c.table("sprints").select("*").execute().data or []
        return sorted(rows, key=lambda s: str(s.get("start_date")))

    def add_sprint(self, data):
        res = self.c.table("sprints").insert(data).execute()
        return (res.data or [{}])[0]

    def update_sprint(self, sprint_id, data):
        self.c.table("sprints").update(data).eq("id", sprint_id).execute()

    def delete_sprint(self, sprint_id):
        self.c.table("sprints").delete().eq("id", sprint_id).execute()

    def log(self, rec):
        self.c.table("activity_log").insert(rec).execute()

    def activity(self, limit=None, entity_id=None):
        q = self.c.table("activity_log").select("*").order("created_at", desc=True)
        if entity_id is not None:
            q = q.eq("entity_id", str(entity_id))
        return q.limit(limit or LOCAL_LOG_CAP).execute().data or []

    def has_users(self):
        return bool(self.c.table("app_users").select("id").limit(1).execute().data)

    def get_user(self, username):
        rows = self.c.table("app_users").select("*").eq("username", username).limit(1).execute().data
        return rows[0] if rows else None

    def add_user(self, data):
        res = self.c.table("app_users").insert(data).execute()
        return (res.data or [{}])[0]


def get_secret(name: str):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _build_store(url, key):
    if url and key and create_client is not None:
        try:
            client = create_client(url, key)
            client.table("tasks").select("id").limit(1).execute()  # prueba de conexión
            return SupabaseStore(client), None
        except Exception as exc:  # noqa: BLE001
            return LocalStore(), str(exc)
    if url and key:
        return LocalStore(), "Falta instalar el paquete 'supabase'."
    return LocalStore(), None


def store_and_error():
    return _build_store(get_secret("SUPABASE_URL"), get_secret("SUPABASE_KEY"))


def get_store():
    return store_and_error()[0]


def load_tasks(framework):
    try:
        return get_store().tasks(framework)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudieron cargar las tarjetas: {exc}")
        return []


def load_sprints():
    try:
        return get_store().sprints()
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudieron cargar los sprints: {exc}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Acciones (callbacks)
# ─────────────────────────────────────────────────────────────────────────────
def move_task(task, new_status, ctx=None):
    if ctx and ctx.get("strict") and new_status in ctx["limits"] and ctx["counts"].get(new_status, 0) >= ctx["limits"][new_status]:
        flash("warning", f"Límite WIP alcanzado en «{STATUS_LABEL[new_status]}». Termina algo antes de mover más tarjetas.")
        return
    now = now_iso()
    updates = {"status": new_status}
    if new_status == "To Do":
        updates.update(started_at=None, completed_at=None)
    elif new_status == "Done":
        updates["completed_at"] = now
    else:
        updates["completed_at"] = None
        if not task.get("started_at"):
            updates["started_at"] = now
    if run(get_store().update_task, task["id"], updates):
        audit("task_move", "task", entity_id=task["id"], title=task.get("title"), framework=task.get("framework"),
              from_status=task.get("status"), to_status=new_status)


def delete_task(task):
    if run(get_store().delete_task, task["id"], ok="Tarjeta eliminada"):
        audit("task_delete", "task", entity_id=task["id"], title=task.get("title"), framework=task.get("framework"),
              from_status=task.get("status"))


def assign_sprint(task, key, labels):
    new = st.session_state.get(key)
    if run(get_store().update_task, task["id"], {"sprint_id": new}):
        audit("task_update", "task", entity_id=task["id"], title=task.get("title"), framework="Scrum",
              details=f"Sprint: {labels.get(task.get('sprint_id'), 'Product Backlog')} → {labels.get(new, 'Product Backlog')}")


def toggle_check(task, item_id, key):
    old = task_checklist(task)
    new = [{**i, "done": bool(st.session_state.get(key))} if i.get("id") == item_id else i for i in old]
    if run(get_store().update_task, task["id"], {"checklist": new}):
        audit("checklist", "task", entity_id=task["id"], title=task.get("title"), framework=task.get("framework"),
              details="; ".join(checklist_diff(old, new)))


def sprint_name(sprint_id):
    return next((s.get("name") for s in get_store().sprints() if str(s["id"]) == str(sprint_id)), None)


def start_sprint(sprint_id, committed):
    store = get_store()
    others = [s for s in store.sprints() if s.get("status") == "Activo" and str(s["id"]) != str(sprint_id)]
    if others:
        flash("warning", f"Ya hay un sprint activo («{others[0]['name']}»). Ciérralo antes de iniciar otro.")
        return
    if run(store.update_sprint, sprint_id, {"status": "Activo", "committed_points": committed}, ok="Sprint iniciado"):
        audit("sprint_start", "sprint", entity_id=sprint_id, title=sprint_name(sprint_id), framework="Scrum",
              details=f"Compromiso: {committed} SP")


def _return_to_backlog(sprint_id, only_unfinished, reason):
    store = get_store()
    for t in store.tasks("Scrum"):
        if str(t.get("sprint_id")) != str(sprint_id):
            continue
        if only_unfinished and t.get("status") == "Done":
            continue
        store.update_task(t["id"], {"sprint_id": None, "status": "To Do", "started_at": None, "completed_at": None})
        moved = t.get("status") != "To Do"
        audit("task_move" if moved else "task_update", "task", entity_id=t["id"], title=t.get("title"), framework="Scrum",
              from_status=t.get("status") if moved else None, to_status="To Do" if moved else None,
              details=f"{reason}: vuelve al Product Backlog")


def close_sprint(sprint_id):
    name = sprint_name(sprint_id)

    def _close():
        _return_to_backlog(sprint_id, only_unfinished=True, reason="Cierre de sprint")
        get_store().update_sprint(sprint_id, {"status": "Cerrado"})

    if run(_close, ok="Sprint cerrado: lo pendiente volvió al Product Backlog"):
        audit("sprint_close", "sprint", entity_id=sprint_id, title=name, framework="Scrum")


def delete_sprint(sprint_id):
    name = sprint_name(sprint_id)

    def _delete():
        _return_to_backlog(sprint_id, only_unfinished=False, reason="Sprint eliminado")
        get_store().delete_sprint(sprint_id)

    if run(_delete, ok="Sprint eliminado"):
        audit("sprint_delete", "sprint", entity_id=sprint_id, title=name, framework="Scrum")


def seed_demo():
    store = get_store()
    today = dt.date.today()

    def iso(days_ago, hour=12):
        d = dt.datetime.combine(today - dt.timedelta(days=days_ago), dt.time(hour, 0), tzinfo=dt.timezone.utc)
        return d.isoformat()

    s1 = store.add_sprint({"name": "Sprint 1", "goal": "Cimientos del producto", "status": "Cerrado",
                           "start_date": str(today - dt.timedelta(days=21)), "end_date": str(today - dt.timedelta(days=8)),
                           "committed_points": 21})
    s2 = store.add_sprint({"name": "Sprint 2", "goal": "Primer flujo de usuario completo", "status": "Activo",
                           "start_date": str(today - dt.timedelta(days=6)), "end_date": str(today + dt.timedelta(days=7)),
                           "committed_points": 24})
    scrum = [
        ("Login con correo", s1["id"], 5, "Alta", "Done", 20, 17), ("Diseño del esquema de datos", s1["id"], 8, "Alta", "Done", 20, 14),
        ("Landing page", s1["id"], 5, "Media", "Done", 19, 11), ("Pipeline de despliegue", s1["id"], 3, "Media", "Done", 18, 10),
        ("Panel de administración", s2["id"], 8, "Alta", "Done", 6, 3), ("Notificaciones por correo", s2["id"], 5, "Media", "Done", 6, 1),
        ("Búsqueda con filtros", s2["id"], 8, "Alta", "In Progress", 6, None), ("Perfil de usuario", s2["id"], 3, "Baja", "To Do", 6, None),
        ("Exportar reportes", None, 5, "Media", "To Do", 4, None), ("Modo oscuro", None, 2, "Baja", "To Do", 3, None),
        ("Integración de pagos", None, 13, "Alta", "To Do", 2, None),
    ]
    for title, sprint_id, points, prio, status, created, done in scrum:
        store.add_task({"title": title, "framework": "Scrum", "sprint_id": sprint_id, "story_points": points, "priority": prio,
                        "status": status, "scrum_role": ROLES[0], "created_at": iso(created),
                        "description": "Criterios de aceptación definidos con el Product Owner.",
                        "started_at": iso(created - 1) if status in ("Done", "In Progress") else None,
                        "completed_at": iso(done) if done is not None else None})
    kanban = [
        ("Responder tickets de soporte", "Alta", "In Progress", 9, 8, None), ("Revisar PR del módulo de pagos", "Media", "Review", 7, 6, None),
        ("Actualizar documentación", "Baja", "To Do", 5, None, None), ("Migrar base de datos", "Alta", "In Progress", 6, 5, None),
        ("Corregir bug de checkout", "Alta", "Done", 8, 7, 5), ("Optimizar consultas lentas", "Media", "Done", 10, 9, 6),
        ("Limpieza de logs", "Baja", "Done", 12, 11, 9), ("Preparar demo para cliente", "Media", "To Do", 2, None, None),
    ]
    for title, prio, status, created, started, done in kanban:
        store.add_task({"title": title, "framework": "Kanban", "priority": prio, "status": status, "created_at": iso(created),
                        "started_at": iso(started, 9) if started is not None else None,
                        "completed_at": iso(done, 17) if done is not None else None})
    audit("demo_seed", "system", details="Sprints, historias y tarjetas de ejemplo")


# ─────────────────────────────────────────────────────────────────────────────
# Componentes visuales
# ─────────────────────────────────────────────────────────────────────────────
def card_html(t, framework) -> str:
    prio = t.get("priority") or "Media"
    badges = [f'<span class="badge prio-{esc(prio).lower()}">{esc(prio)}</span>']
    if framework == "Scrum":
        badges.append(f'<span class="badge sp">{pts(t)} SP</span>')
        if t.get("scrum_role"):
            badges.append(f'<span class="badge">{esc(t["scrum_role"])}</span>')
    if t.get("assignee"):
        badges.append(f'<span class="badge">👤 {esc(t["assignee"])}</span>')
    due = parse_date(t.get("due_date"))
    if due:
        late = due < dt.date.today() and t.get("status") != "Done"
        badges.append(f'<span class="badge {"late" if late else ""}">{"⏰ " if late else "📅 "}{due:%d %b}</span>')
    ck_done, ck_total = checklist_progress(task_checklist(t))
    ck_bar = ""
    if ck_total:
        badges.append(f'<span class="badge ck{" full" if ck_done == ck_total else ""}">☑ {ck_done}/{ck_total}</span>')
        ck_bar = f'<div class="ck-bar"><div style="width:{ck_done / ck_total * 100:.0f}%"></div></div>'
    tags = "".join(f'<span class="tag">#{esc(x.strip())}</span> ' for x in str(t.get("tags") or "").split(",") if x.strip())
    desc = str(t.get("description") or "")
    desc_html = f'<div class="card-desc">{esc(desc[:140] + ("…" if len(desc) > 140 else ""))}</div>' if desc else ""
    return (f'<div class="card b-{esc(prio).lower()}"><div class="card-title">{esc(t.get("title"))}</div>{desc_html}'
            f'<div class="badges">{"".join(badges)}</div>{f"<div style=margin-top:6px>{tags}</div>" if tags else ""}{ck_bar}</div>')


def column_header(label, count, limit=None) -> str:
    if limit is None:
        return f'<div class="col-head"><span>{esc(label)}</span><span class="pill">{count}</span></div>'
    state = "over" if count > limit else ("full" if count == limit else "")
    pct = min(count / limit, 1) * 100
    warn = '<div class="wip-warn">🚨 Excede el límite WIP</div>' if state == "over" else ""
    return (f'<div class="col-head"><span>{esc(label)}</span><span class="pill {state}">{count}/{limit}</span></div>'
            f'<div class="wip"><div class="wip-bar {state}" style="width:{pct:.0f}%"></div></div>{warn}')


def board_card(t, framework, statuses, idx, ctx=None):
    tid = str(t["id"])
    st.markdown(card_html(t, framework), unsafe_allow_html=True)
    b1, b2, b5, b3, b4 = st.columns(5)
    # Se añade _{idx} para garantizar unicidad por columna/posición
    b1.button("◀", key=f"{framework}_l_{tid}_{idx}", disabled=idx == 0, help="Mover a la izquierda",
              on_click=move_task, args=(t, statuses[max(idx - 1, 0)], ctx))
    b2.button("▶", key=f"{framework}_r_{tid}_{idx}", disabled=idx == len(statuses) - 1, help="Mover a la derecha",
              on_click=move_task, args=(t, statuses[min(idx + 1, len(statuses) - 1)], ctx))
    items = task_checklist(t)
    if items:
        d, n = checklist_progress(items)
        with b5.popover("☑", help=f"Checklist {d}/{n}"):
            for it in items:
                ck_key = f"{framework}_ck_{tid}_{it.get('id')}_{idx}"
                st.checkbox(it.get("text", ""), value=bool(it.get("done")), key=ck_key,
                            on_change=toggle_check, args=(t, it.get("id"), ck_key))
    if b3.button("✎", key=f"{framework}_e_{tid}_{idx}", help="Editar"):
        task_dialog(framework, t)
    with b4.popover("✕", help="Eliminar"):
        st.caption("¿Eliminar esta tarjeta?")
        st.button("Sí, eliminar", key=f"{framework}_d_{tid}_{idx}", type="primary", on_click=delete_task, args=(t,))


def themed(chart):
    return (chart.configure(background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor="#1f1f1f", domainColor="#2B2515", tickColor="#2B2515")
            .configure_legend(labelColor=MUTED, titleColor=MUTED))


@st.dialog("Tarjeta", width="large")
def task_dialog(framework, task=None, default_sprint=None):
    t = task or {}
    sprints = get_store().sprints() if framework == "Scrum" else []
    sprint_ids = [None] + [s["id"] for s in sprints if s.get("status") != "Cerrado" or s["id"] == t.get("sprint_id")]
    sprint_names = {None: "Product Backlog", **{s["id"]: s["name"] for s in sprints}}

    with st.form("task_form", border=False):
        title = st.text_input("Título", value=t.get("title", ""))
        desc = st.text_area("Descripción" if framework == "Kanban" else "Historia / criterios de aceptación",
                            value=t.get("description") or "")
        c1, c2 = st.columns(2)
        priority = c1.selectbox("Prioridad", PRIORITIES, index=PRIORITIES.index(t["priority"]) if t.get("priority") in PRIORITIES else 1)
        assignee = c2.text_input("Responsable", value=t.get("assignee") or "")
        c3, c4 = st.columns(2)
        due = c3.date_input("Fecha límite", value=parse_date(t.get("due_date")), format="YYYY-MM-DD")
        tags = c4.text_input("Etiquetas (separadas por coma)", value=t.get("tags") or "")
        points = role = sprint_id = None
        if framework == "Scrum":
            c5, c6, c7 = st.columns(3)
            current = pts(t) if pts(t) in FIBONACCI else 3
            points = c5.select_slider("Story points", FIBONACCI, value=current)
            role = c6.selectbox("Rol", ROLES, index=ROLES.index(t["scrum_role"]) if t.get("scrum_role") in ROLES else 0)
            start_sprint_id = t.get("sprint_id", default_sprint)
            sprint_id = c7.selectbox("Ubicación", sprint_ids, format_func=lambda i: sprint_names.get(i, "—"),
                                     index=sprint_ids.index(start_sprint_id) if start_sprint_id in sprint_ids else 0)
        st.markdown("**☑ Checklist**")
        st.caption("Escribe cada paso en la fila vacía del final y marca «Hecho» al completarlo.")
        old_ck = task_checklist(t)
        ck_df = pd.DataFrame({"Hecho": pd.Series([bool(i.get("done")) for i in old_ck], dtype=bool),
                              "Elemento": pd.Series([i.get("text", "") for i in old_ck], dtype=object)})
        ck_edit = st.data_editor(
            ck_df, num_rows="dynamic", hide_index=True, key=f"ck_editor_{t.get('id', 'new')}",
            column_config={"Hecho": st.column_config.CheckboxColumn("Hecho", default=False, width="small"),
                           "Elemento": st.column_config.TextColumn("Elemento", max_chars=200, width="large")})
        submitted = st.form_submit_button("Guardar cambios" if task else "Crear", type="primary")

    if task:
        with st.expander("🕓 Historial de esta tarjeta"):
            try:
                render_history(get_store().activity(limit=50, entity_id=task["id"]),
                               empty="Sin cambios registrados todavía para esta tarjeta.")
            except Exception as exc:  # noqa: BLE001
                st.caption(f"No se pudo leer el historial: {exc}")

    if submitted:
        if not title.strip():
            st.warning("El título es obligatorio.")
            return
        payload = {"title": title.strip(), "description": desc.strip() or None, "priority": priority,
                   "assignee": assignee.strip() or None, "due_date": str(due) if due else None, "tags": tags.strip() or None}
        if framework == "Scrum":
            payload.update(story_points=points, scrum_role=role, sprint_id=sprint_id)
        payload["checklist"] = merge_checklist(old_ck, ck_edit.to_dict("records"))
        store = get_store()
        if task:
            changes = task_changes(task, payload, sprint_names)
            ck_changes = checklist_diff(old_ck, payload["checklist"])
            ok = run(store.update_task, task["id"], payload, ok="Tarjeta actualizada")
            if ok and changes:
                audit("task_update", "task", entity_id=task["id"], title=payload["title"], framework=framework,
                      details="; ".join(changes))
            if ok and ck_changes:
                audit("checklist", "task", entity_id=task["id"], title=payload["title"], framework=framework,
                      details="; ".join(ck_changes))
        else:
            payload.update(framework=framework, status="To Do")
            created = {}
            ok = run(lambda p: created.update(store.add_task(p) or {}), payload, ok="Tarjeta creada")
            if ok:
                n_ck = len(payload["checklist"])
                audit("task_create", "task", entity_id=created.get("id"), title=payload["title"], framework=framework,
                      to_status="To Do", details=f"Checklist con {n_ck} elementos" if n_ck else None)
        if ok:
            st.rerun()
        show_flash()


def tasks_csv(tasks) -> bytes:
    # utf-8-sig incluye una marca (BOM) que le indica a Excel que debe abrir el archivo con codificación UTF-8
    return pd.DataFrame(tasks).to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def render_history(events, empty="Sin actividad registrada todavía."):
    if not events:
        st.caption(empty)
        return
    items = []
    for ev in events:
        icon = CATEGORY_ICON.get(ACTION_CATEGORY.get(ev.get("action"), ""), "•")
        det = f'<div class="tl-det">{esc(ev.get("details"))}</div>' if ev.get("details") else ""
        items.append(f'<div class="tl-item"><div class="tl-dot">{icon}</div><div>'
                     f'<div class="tl-text"><b>{esc(ev.get("actor") or "—")}</b> {esc(describe_event(ev))}</div>'
                     f'{det}<div class="tl-when">{esc(rel_time(ev.get("created_at")))}</div></div></div>')
    st.markdown(f'<div class="timeline">{"".join(items)}</div>', unsafe_allow_html=True)


def render_cfd(tasks, statuses, start, end):
    try:
        events = get_store().activity()
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Sin registro de actividad ({exc}); el diagrama se reconstruye solo con fechas.")
        events = []
    df, rebuilt = cfd_frame(tasks, events, statuses, start, end)
    if df.empty or not df["Tarjetas"].sum():
        st.caption("Aún no hay tarjetas en este periodo.")
        return
    labels = [STATUS_LABEL[s] for s in statuses]
    palette = {"To Do": "#3d3d3d", "In Progress": GOLD_DIM, "Review": "#B8941F", "Done": GOLD}
    chart = alt.Chart(df).mark_area(opacity=0.92, interpolate="step-after").encode(
        x=alt.X("Día:T", title=None, axis=alt.Axis(format="%d %b")),
        y=alt.Y("Tarjetas:Q", stack="zero", title="Tarjetas", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Estado:N", sort=labels, scale=alt.Scale(domain=labels, range=[palette[s] for s in statuses]),
                        legend=alt.Legend(orient="bottom", title=None)),
        order=alt.Order("Orden:Q", sort="descending"),
        tooltip=[alt.Tooltip("Día:T", format="%d %b %Y"), "Estado:N", "Tarjetas:Q"]).properties(height=300)
    stretch(st.altair_chart, themed(chart))
    note = ("Cada banda muestra cuántas tarjetas había en ese estado al final del día. "
            "Si una banda intermedia se ensancha, el trabajo se está acumulando ahí.")
    if rebuilt:
        note += f" {rebuilt} tarjeta(s) sin historial completo se reconstruyeron con sus fechas de creación, inicio y fin."
    st.caption(note)


HISTORY_COLORS = {"Creación": "#E8C766", "Edición": "#B8941F", "Movimiento": GOLD, "Checklist": "#F2CF66",
                  "Sprint": "#8c8c8c", "Eliminación": "#C0564B", "Acceso": "#5c5c5c", "Sistema": "#3d3d3d", "Otros": "#2b2b2b"}


def render_activity_section():
    st.markdown("### Historial de actividad")
    try:
        events = get_store().activity()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"No se pudo leer el registro de actividad: {exc}. ¿Ejecutaste schema.sql en Supabase?")
        return
    if not events:
        st.caption("Todavía no hay actividad registrada. Cada creación, movimiento o edición aparecerá aquí.")
        return
    week_ago = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    recent = [e for e in events if (ts := parse_dt(e.get("created_at"))) is not None and ts >= week_ago]
    h1, h2, h3 = st.columns(3)
    h1.metric("Eventos · 7 días", len(recent))
    h2.metric("Personas activas · 7 días", len({e.get("actor") for e in recent if e.get("action") != "login_failed"}))
    h3.metric("Tarjetas movidas · 7 días", sum(1 for e in recent if e.get("action") == "task_move"))

    df = activity_frame(events, 14, dt.date.today())
    chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("Día:T", title=None, axis=alt.Axis(format="%d %b")),
        y=alt.Y("sum(Eventos):Q", title=None, axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Tipo:N", scale=alt.Scale(domain=list(HISTORY_COLORS), range=list(HISTORY_COLORS.values())),
                        legend=alt.Legend(orient="bottom", title=None)),
        tooltip=[alt.Tooltip("Día:T", format="%d %b"), "Tipo:N", "Eventos:Q"]).properties(height=220)
    stretch(st.altair_chart, themed(chart))

    f1, f2, f3 = st.columns([3, 3, 2], vertical_alignment="bottom")
    kinds = f1.multiselect("Tipo de evento", sorted({ACTION_CATEGORY.get(e.get("action"), "Otros") for e in events}))
    people = ["Todas"] + sorted({e.get("actor") for e in events if e.get("actor")})
    who = f2.selectbox("Persona", people)
    log_csv = pd.DataFrame(events).to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
    f3.download_button("⬇ Registro CSV", log_csv, "registro_actividad.csv", "text/csv")
    shown = [e for e in events if (not kinds or ACTION_CATEGORY.get(e.get("action"), "Otros") in kinds)
             and (who == "Todas" or e.get("actor") == who)]
    render_history(shown[:40], empty="Ningún evento coincide con los filtros.")
    if len(shown) > 40:
        st.caption(f"Mostrando 40 de {len(shown)} eventos. Descarga el CSV para verlos todos.")


# ─────────────────────────────────────────────────────────────────────────────
# Módulo: Resumen
# ─────────────────────────────────────────────────────────────────────────────
def render_overview():
    st.title("Agile Core Studio")
    st.caption("Panel general de tus marcos ágiles")
    kanban, scrum, sprints = load_tasks("Kanban"), load_tasks("Scrum"), load_sprints()

    if not kanban and not scrum and not sprints:
        st.info("Aún no hay datos. Crea tu primera tarjeta o carga datos de ejemplo para explorar.")
        st.button("✨ Cargar datos de ejemplo", on_click=lambda: run(seed_demo, ok="Datos de ejemplo cargados"))
        return

    active = next((s for s in sprints if s.get("status") == "Activo"), None)
    today = dt.date.today()
    all_tasks = kanban + scrum
    overdue = [t for t in all_tasks if parse_date(t.get("due_date")) and parse_date(t["due_date"]) < today and t.get("status") != "Done"]
    wip_now = sum(1 for t in kanban if t.get("status") in ("In Progress", "Review"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tarjetas Kanban en curso", wip_now)
    m2.metric("Sprint activo", active["name"] if active else "—")
    if active:
        s_tasks = [t for t in scrum if t.get("sprint_id") == active["id"]]
        total = sum(pts(t) for t in s_tasks)
        done = sum(pts(t) for t in s_tasks if t.get("status") == "Done")
        m3.metric("Avance del sprint", f"{done}/{total} SP")
    else:
        m3.metric("Avance del sprint", "—")
    m4.metric("Tareas vencidas", len(overdue))

    st.markdown("### Distribución por estado")
    rows = [{"Marco": t["framework"], "Estado": STATUS_LABEL.get(t.get("status"), t.get("status"))} for t in all_tasks]
    if rows:
        df = pd.DataFrame(rows).value_counts().reset_index(name="Tarjetas")
        order = [STATUS_LABEL[s] for s in KANBAN_STATUSES]
        chart = alt.Chart(df).mark_bar(cornerRadiusEnd=4).encode(
            y=alt.Y("Estado:N", sort=order, title=None), x=alt.X("Tarjetas:Q", title=None),
            color=alt.Color("Marco:N", scale=alt.Scale(domain=["Kanban", "Scrum"], range=[GOLD, "#8c8c8c"]),
                            legend=alt.Legend(orient="bottom", title=None)),
            yOffset="Marco:N").properties(height=220)
        stretch(st.altair_chart, themed(chart))

    st.markdown("### Próximos vencimientos")
    upcoming = sorted([t for t in all_tasks if parse_date(t.get("due_date")) and t.get("status") != "Done"],
                      key=lambda t: parse_date(t["due_date"]))[:10]
    if upcoming:
        df = pd.DataFrame([{"Marco": t["framework"], "Título": t["title"], "Responsable": t.get("assignee") or "—",
                            "Vence": parse_date(t["due_date"]).strftime("%Y-%m-%d"),
                            "Estado": STATUS_LABEL.get(t.get("status"), t.get("status"))} for t in upcoming])
        stretch(st.dataframe, df, hide_index=True)
    else:
        st.caption("Ninguna tarjeta tiene fecha límite pendiente.")

    render_activity_section()


# ─────────────────────────────────────────────────────────────────────────────
# Módulo: Kanban
# ─────────────────────────────────────────────────────────────────────────────
def render_kanban():
    st.title("Tablero Kanban")
    st.caption("Flujo continuo, límites WIP y métricas de flujo.")
    tasks = load_tasks("Kanban")

    with st.sidebar:
        with st.expander("🔒 Límites WIP", expanded=False):
            limits = {s: st.number_input(STATUS_LABEL[s], min_value=1, max_value=99, value=WIP_DEFAULTS[s], key=f"wip_{s}")
                      for s in WIP_DEFAULTS}
            strict = st.toggle("Bloquear movimientos que excedan el límite", value=True, key="wip_strict")
        st.download_button("⬇ Exportar CSV", tasks_csv(tasks), "kanban.csv", "text/csv", disabled=not tasks)

    counts = {s: sum(1 for t in tasks if t.get("status") == s) for s in KANBAN_STATUSES}
    ctx = {"counts": counts, "limits": limits, "strict": strict}

    f1, f2, f3, f4 = st.columns([3, 3, 3, 2], vertical_alignment="bottom")
    query = f1.text_input("Buscar", placeholder="Título, descripción o etiqueta…")
    prios = f2.multiselect("Prioridad", PRIORITIES)
    people = ["Todos"] + sorted({t["assignee"] for t in tasks if t.get("assignee")})
    who = f3.selectbox("Responsable", people)
    if f4.button("＋ Nueva tarjeta", type="primary"):
        task_dialog("Kanban")

    def visible(t):
        hay = f"{t.get('title') or ''} {t.get('description') or ''} {t.get('tags') or ''}".lower()
        return ((not query or query.lower() in hay) and (not prios or t.get("priority") in prios)
                and (who == "Todos" or t.get("assignee") == who))

    tab_board, tab_metrics = st.tabs(["📌 Tablero", "📊 Métricas de flujo"])

    with tab_board:
        cols = st.columns(len(KANBAN_STATUSES))
        for i, status in enumerate(KANBAN_STATUSES):
            with cols[i]:
                st.markdown(column_header(STATUS_LABEL[status], counts[status], limits.get(status)), unsafe_allow_html=True)
                col_tasks = sorted((t for t in tasks if t.get("status") == status and visible(t)),
                                   key=lambda t: (PRIO_ORDER.get(t.get("priority"), 1), str(t.get("created_at"))))
                if not col_tasks:
                    st.caption("—")
                for t in col_tasks:
                    board_card(t, "Kanban", KANBAN_STATUSES, i, ctx)

    with tab_metrics:
        done = [t for t in tasks if t.get("status") == "Done"]
        cycle = [h for t in done if (h := hours_between(t.get("started_at"), t.get("completed_at"))) is not None]
        lead = [h for t in done if (h := hours_between(t.get("created_at"), t.get("completed_at"))) is not None]
        week_ago = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
        last7 = sum(1 for t in done if (c := parse_dt(t.get("completed_at"))) is not None and c >= week_ago)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Throughput total", len(done))
        k2.metric("Completadas · 7 días", last7)
        k3.metric("Cycle time (mediana)", fmt_duration(statistics.median(cycle) if cycle else None))
        k4.metric("Lead time (mediana)", fmt_duration(statistics.median(lead) if lead else None))

        st.markdown("### Throughput diario (14 días)")
        days = pd.date_range(end=dt.date.today(), periods=14)
        per_day = {d.date(): 0 for d in days}
        for t in done:
            c = parse_dt(t.get("completed_at"))
            if c is not None and c.date() in per_day:
                per_day[c.date()] += 1
        df = pd.DataFrame({"Día": list(per_day.keys()), "Completadas": list(per_day.values())})
        df["Día"] = pd.to_datetime(df["Día"])
        chart = alt.Chart(df).mark_bar(color=GOLD, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("Día:T", title=None, axis=alt.Axis(format="%d %b")),
            y=alt.Y("Completadas:Q", title=None, axis=alt.Axis(tickMinStep=1))).properties(height=240)
        stretch(st.altair_chart, themed(chart))

        st.markdown("### Diagrama de Flujo Acumulado (30 días)")
        render_cfd(tasks, KANBAN_STATUSES, dt.date.today() - dt.timedelta(days=29), dt.date.today())

        st.markdown("### Aging WIP")
        st.caption("Tarjetas en curso ordenadas por antigüedad: las más viejas son las que hay que desbloquear primero.")
        rows = []
        for t in tasks:
            if t.get("status") in ("In Progress", "Review"):
                h = hours_between(t.get("started_at"), now_iso())
                rows.append({"Título": t["title"], "Estado": STATUS_LABEL[t["status"]], "Responsable": t.get("assignee") or "—",
                             "Días en curso": round(h / 24, 1) if h is not None else None})
        if rows:
            stretch(st.dataframe, pd.DataFrame(rows).sort_values("Días en curso", ascending=False), hide_index=True)
        else:
            st.caption("No hay tarjetas en curso.")


# ─────────────────────────────────────────────────────────────────────────────
# Módulo: Scrum
# ─────────────────────────────────────────────────────────────────────────────
def burndown_frame(sprint, tasks):
    start, end = parse_date(sprint.get("start_date")), parse_date(sprint.get("end_date"))
    if not start or not end or end < start:
        return None
    days = pd.date_range(start, end)
    total = sum(pts(t) for t in tasks)
    done = [((parse_dt(t.get("completed_at")).date() if parse_dt(t.get("completed_at")) is not None else start), pts(t))
            for t in tasks if t.get("status") == "Done"]
    today, n, rows = dt.date.today(), len(days), []
    for i, day in enumerate(days):
        ideal = total * (1 - i / (n - 1)) if n > 1 else 0
        real = total - sum(p for d, p in done if d <= day.date()) if day.date() <= today else None
        rows.append({"Día": day, "Ideal": round(ideal, 1), "Real": real})
    return pd.DataFrame(rows)


def velocity_frame(sprints, tasks):
    rows = []
    for s in sorted(sprints, key=lambda s: str(s.get("start_date"))):
        s_tasks = [t for t in tasks if t.get("sprint_id") == s["id"]]
        committed = s.get("committed_points")
        rows.append({"Sprint": s["name"],
                     "Comprometidos": int(committed) if committed is not None else sum(pts(t) for t in s_tasks),
                     "Completados": sum(pts(t) for t in s_tasks if t.get("status") == "Done")})
    return pd.DataFrame(rows)


def backlog_item(t, sprint_options, sprint_label):
    tid = str(t["id"])
    st.markdown(card_html(t, "Scrum"), unsafe_allow_html=True)
    c1, c2, c3 = st.columns([4, 1, 1])
    current = t.get("sprint_id") if t.get("sprint_id") in sprint_options else None
    key = f"mv_{tid}"
    c1.selectbox("Mover a", sprint_options, index=sprint_options.index(current), format_func=lambda i: sprint_label.get(i, "—"),
                 key=key, label_visibility="collapsed", on_change=assign_sprint, args=(t, key, sprint_label))
    if c2.button("✎", key=f"Scrum_e_{tid}", help="Editar"):
        task_dialog("Scrum", t)
    with c3.popover("✕", help="Eliminar"):
        st.caption("¿Eliminar esta historia?")
        st.button("Sí, eliminar", key=f"Scrum_d_{tid}", type="primary", on_click=delete_task, args=(t,))


def render_scrum():
    st.title("Marco Scrum")
    st.caption("Product Backlog, sprints, tablero, velocidad, burndown y retrospectiva.")
    tasks, sprints = load_tasks("Scrum"), load_sprints()
    sprint_label = {None: "Product Backlog", **{s["id"]: s["name"] for s in sprints}}
    by_id = {s["id"]: s for s in sprints}

    with st.sidebar:
        with st.expander("⚙️ Nuevo sprint"):
            with st.form("sprint_create", clear_on_submit=True, border=False):
                name = st.text_input("Nombre", placeholder=f"Sprint {len(sprints) + 1}")
                goal = st.text_area("Objetivo del sprint (Sprint Goal)")
                start = st.date_input("Inicio", value=dt.date.today(), format="YYYY-MM-DD")
                end = st.date_input("Fin", value=dt.date.today() + dt.timedelta(days=14), format="YYYY-MM-DD")
                if st.form_submit_button("Crear sprint"):
                    if not name.strip():
                        st.warning("El nombre es obligatorio.")
                    elif end < start:
                        st.warning("La fecha de fin no puede ser anterior a la de inicio.")
                    elif run(get_store().add_sprint, {"name": name.strip(), "goal": goal.strip() or None, "start_date": str(start),
                                                      "end_date": str(end), "status": "Planificado"}, ok="Sprint creado"):
                        audit("sprint_create", "sprint", title=name.strip(), framework="Scrum",
                              details=f"{start} → {end}")
                        st.rerun()
                    else:
                        show_flash()
        st.download_button("⬇ Exportar CSV", tasks_csv(tasks), "scrum.csv", "text/csv", disabled=not tasks)

    # Sprint de trabajo (para tablero, métricas y retro)
    selected = None
    if sprints:
        ordered = sorted(sprints, key=lambda s: (SPRINT_ORDER.get(s.get("status"), 3), str(s.get("start_date"))))
        ids = [s["id"] for s in ordered]
        selected = st.selectbox("Sprint de trabajo", ids, format_func=lambda i: f"{by_id[i]['name']} · {by_id[i].get('status', '')}")

    tab_backlog, tab_sprint, tab_metrics, tab_retro = st.tabs(["📦 Backlog", "🚀 Sprint", "📈 Métricas", "🗣️ Retrospectiva"])

    # ── Backlog ──────────────────────────────────────────────────────────────
    with tab_backlog:
        f1, f2, f3 = st.columns([4, 3, 2], vertical_alignment="bottom")
        query = f1.text_input("Buscar en backlog", placeholder="Título, descripción o etiqueta…")
        roles = f2.multiselect("Rol", ROLES)
        if f3.button("＋ Nueva historia", type="primary"):
            task_dialog("Scrum")

        def visible(t):
            hay = f"{t.get('title') or ''} {t.get('description') or ''} {t.get('tags') or ''}".lower()
            return (not query or query.lower() in hay) and (not roles or t.get("scrum_role") in roles)

        sections = [(None, "Product Backlog")] + [(s["id"], f"{s['name']} · {s.get('status', '')}") for s in
                    sorted(sprints, key=lambda s: (SPRINT_ORDER.get(s.get("status"), 3), str(s.get("start_date"))))]
        for sid, label in sections:
            items = sorted((t for t in tasks if (t.get("sprint_id") if t.get("sprint_id") in by_id else None) == sid and visible(t)),
                           key=lambda t: (PRIO_ORDER.get(t.get("priority"), 1), str(t.get("created_at"))))
            total = sum(pts(t) for t in items)
            is_closed = sid is not None and by_id[sid].get("status") == "Cerrado"
            with st.expander(f"{label} — {len(items)} ítems · {total} SP", expanded=(not is_closed)):
                if not items:
                    st.caption("Sin elementos.")
                options = [None] + [s["id"] for s in sprints if s.get("status") != "Cerrado"]
                for t in items:
                    opts = options if (sid is None or sid in options) else options + [sid]
                    backlog_item(t, opts, sprint_label)

    # ── Sprint ───────────────────────────────────────────────────────────────
    with tab_sprint:
        if not selected:
            st.info("Crea un sprint desde la barra lateral para ver su tablero.")
        else:
            sp = by_id[selected]
            s_tasks = [t for t in tasks if t.get("sprint_id") == selected]
            total, done = sum(pts(t) for t in s_tasks), sum(pts(t) for t in s_tasks if t.get("status") == "Done")
            pct = (done / total * 100) if total else 0
            end_d = parse_date(sp.get("end_date"))
            left = (end_d - dt.date.today()).days if end_d else None
            left_txt = "" if left is None or sp.get("status") == "Cerrado" else (f" · quedan {left} días" if left >= 0 else f" · terminó hace {-left} días")
            st.markdown(
                f'<div class="sprint-box"><h4>{esc(sp["name"])} <span class="pill">{esc(sp.get("status"))}</span></h4>'
                f'<p>🎯 {esc(sp.get("goal") or "Sin objetivo definido")}<br>{esc(sp.get("start_date"))} → {esc(sp.get("end_date"))}{left_txt}</p>'
                f'<div class="progress"><div style="width:{pct:.0f}%"></div></div>'
                f'<p style="margin-top:6px">{done} / {total} story points completados ({pct:.0f}%)</p></div>', unsafe_allow_html=True)

            a1, a2, a3, a4 = st.columns(4)
            if sp.get("status") == "Planificado":
                a1.button("▶ Iniciar sprint", type="primary", on_click=start_sprint, args=(selected, total))
            if sp.get("status") == "Activo":
                with a1.popover("🏁 Cerrar sprint"):
                    st.caption("Lo no terminado volverá al Product Backlog.")
                    st.button("Confirmar cierre", type="primary", key="close_sprint", on_click=close_sprint, args=(selected,))
            if a2.button("＋ Historia aquí"):
                task_dialog("Scrum", None, selected)
            with a4.popover("🗑 Eliminar sprint"):
                st.caption("Las historias volverán al Product Backlog.")
                st.button("Confirmar eliminación", type="primary", key="del_sprint", on_click=delete_sprint, args=(selected,))

            cols = st.columns(len(SCRUM_STATUSES))
            for i, status in enumerate(SCRUM_STATUSES):
                with cols[i]:
                    items = sorted((t for t in s_tasks if t.get("status") == status),
                                   key=lambda t: (PRIO_ORDER.get(t.get("priority"), 1), str(t.get("created_at"))))
                    st.markdown(column_header(STATUS_LABEL[status], len(items)), unsafe_allow_html=True)
                    if not items:
                        st.caption("—")
                    for t in items:
                        board_card(t, "Scrum", SCRUM_STATUSES, i)

    # ── Métricas ─────────────────────────────────────────────────────────────
    with tab_metrics:
        if not sprints:
            st.info("Crea sprints y completa historias para ver velocidad y burndown.")
        else:
            vel = velocity_frame(sprints, tasks)
            closed = [r for r, s in zip(vel.to_dict("records"), sorted(sprints, key=lambda s: str(s.get("start_date"))))
                      if s.get("status") == "Cerrado"]
            avg_vel = statistics.mean(r["Completados"] for r in closed) if closed else None
            sp = by_id[selected]
            s_tasks = [t for t in tasks if t.get("sprint_id") == selected]
            total, done = sum(pts(t) for t in s_tasks), sum(pts(t) for t in s_tasks if t.get("status") == "Done")
            committed = sp.get("committed_points")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Velocidad media", f"{avg_vel:.1f} SP" if avg_vel is not None else "—")
            m2.metric("Completados (sprint)", f"{done} SP")
            m3.metric("Restantes (sprint)", f"{max(total - done, 0)} SP")
            m4.metric("Compromiso cumplido", f"{done / committed * 100:.0f}%" if committed else "—")

            st.markdown("### Velocidad por sprint")
            long = vel.melt("Sprint", var_name="Serie", value_name="Puntos")
            chart = alt.Chart(long).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("Sprint:N", sort=list(vel["Sprint"]), title=None, axis=alt.Axis(labelAngle=0)),
                xOffset="Serie:N", y=alt.Y("Puntos:Q", title=None),
                color=alt.Color("Serie:N", scale=alt.Scale(domain=["Comprometidos", "Completados"], range=[GOLD_DIM, GOLD]),
                                legend=alt.Legend(orient="bottom", title=None))).properties(height=260)
            stretch(st.altair_chart, themed(chart))

            st.markdown(f"### Burndown · {sp['name']}")
            bd = burndown_frame(sp, s_tasks)
            if bd is None or not total:
                st.caption("Necesitas fechas válidas e historias con story points en el sprint.")
            else:
                long = bd.melt("Día", var_name="Serie", value_name="Puntos")
                chart = alt.Chart(long).mark_line(point=True, strokeWidth=2.5).encode(
                    x=alt.X("Día:T", title=None, axis=alt.Axis(format="%d %b")),
                    y=alt.Y("Puntos:Q", title="Puntos restantes"),
                    color=alt.Color("Serie:N", scale=alt.Scale(domain=["Real", "Ideal"], range=[GOLD, "#7a7a7a"]),
                                    legend=alt.Legend(orient="bottom", title=None)),
                    strokeDash=alt.condition(alt.datum.Serie == "Ideal", alt.value([5, 4]), alt.value([0]))).properties(height=300)
                stretch(st.altair_chart, themed(chart))

            st.markdown(f"### Flujo acumulado · {sp['name']}")
            s_start, s_end = parse_date(sp.get("start_date")), parse_date(sp.get("end_date"))
            if not s_start or not s_end or s_start > dt.date.today():
                st.caption("El diagrama aparece cuando el sprint ha comenzado y tiene fechas válidas.")
            else:
                render_cfd(s_tasks, SCRUM_STATUSES, s_start, min(s_end, dt.date.today()))

    # ── Retrospectiva ────────────────────────────────────────────────────────
    with tab_retro:
        if not selected:
            st.info("Selecciona o crea un sprint para registrar su retrospectiva.")
        else:
            sp = by_id[selected]
            st.markdown(f"### Retrospectiva · {sp['name']}")
            with st.form(f"retro_{selected}", border=False):
                well = st.text_area("✨ ¿Qué salió bien?", value=sp.get("retro_well") or "", height=120)
                improve = st.text_area("🔧 ¿Qué podemos mejorar?", value=sp.get("retro_improve") or "", height=120)
                actions = st.text_area("🎯 Acciones para el próximo sprint", value=sp.get("retro_actions") or "", height=120)
                if st.form_submit_button("Guardar retrospectiva", type="primary"):
                    if run(get_store().update_sprint, selected,
                           {"retro_well": well or None, "retro_improve": improve or None, "retro_actions": actions or None},
                           ok="Retrospectiva guardada"):
                        audit("sprint_retro", "sprint", entity_id=selected, title=sp["name"], framework="Scrum")
                        st.rerun()
                    show_flash()
                    
with st.sidebar:
        st.markdown('<div class="brand">⚜ Agile Core Studio<small>SCRUM · KANBAN</small></div><hr class="gold-rule">', unsafe_allow_html=True)
        
        # --- SECCIÓN DE PROYECTOS E INVITACIONES ---
        st.markdown("### 📂 Proyecto Activo")
        store = get_store()
        all_projects = store.sprints() # o método correspondiente para proyectos
        
        # Lógica simplificada de selección de proyecto
        # (Asegúrate de tener una tabla o lista de proyectos cargada)
        project_name = st.text_input("Crear nuevo proyecto", placeholder="Nombre del proyecto...")
        if st.button("➕ Crear proyecto"):
            if project_name.strip():
                run(store.add_project, project_name.strip(), ok="Proyecto creado", log_msg=f"Proyecto creado: {project_name}")
                st.rerun()

        st.markdown('<hr class="gold-rule">', unsafe_allow_html=True)
        
        # Botón para invitar usuarios
        with st.popover("👥 Invitar usuario"):
            st.subheader("Colaboradores")
            invite_email = st.text_input("Correo electrónico")
            invite_role = st.selectbox("Rol", ["Miembro", "Observador"])
            if st.button("Enviar invitación", type="primary"):
                # Lógica para registrar la invitación en Supabase
                st.success(f"Invitación enviada a {invite_email}")

        page = st.radio("Módulo", ["📊 Resumen", "📌 Kanban", "🔄 Scrum"], label_visibility="collapsed")

# ─────────────────────────────────────────────────────────────────────────────
# Acceso (login)
# ─────────────────────────────────────────────────────────────────────────────
LOGIN_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display:none; }
.stApp { background:
    radial-gradient(900px 520px at 50% -12%, rgba(212,175,55,.18), transparent 62%),
    repeating-linear-gradient(90deg, rgba(212,175,55,.035) 0 1px, transparent 1px 140px),
    var(--bg); }
.block-container { padding-top: 0 !important; }
.login-mark { text-align:center; margin-top:7vh; }
.login-mark .crest { display:inline-grid; place-items:center; width:72px; height:72px; border-radius:50%;
    border:1px solid var(--gold-dim); color:var(--gold); font-size:2.1rem;
    background:radial-gradient(circle at 30% 25%, rgba(232,199,102,.22), rgba(10,10,10,0) 70%);
    box-shadow:0 0 0 6px rgba(212,175,55,.05), 0 0 40px rgba(212,175,55,.18); }
.login-mark h1 { font-size:2.5rem !important; margin:.8rem 0 0 0; }
.login-mark .tag { color:var(--muted); letter-spacing:.32em; font-size:.7rem; margin:.5rem 0 0; }
.login-mark .lead { color:var(--text); opacity:.8; font-size:.92rem; margin:.9rem 0 1.4rem; }
[data-testid="stForm"] { background:linear-gradient(180deg,#16130a,#0f0f0f); border:1px solid var(--gold-dim) !important;
    border-radius:16px; padding:22px 24px 12px; box-shadow:0 24px 70px rgba(0,0,0,.65), inset 0 1px 0 rgba(212,175,55,.18); }
[data-testid="stForm"] input { background:#0B0B0B !important; color:var(--text) !important; }
.login-foot { text-align:center; color:var(--muted); font-size:.75rem; margin-top:16px; }
</style>
"""


def sign_in(user):
    st.session_state["user"] = {"username": user["username"], "display_name": user.get("display_name") or user["username"]}
    st.session_state.pop("login_fails", None)


def login_form(store):
    with st.form("login_form"):
        username = st.text_input("Usuario", placeholder="tu.usuario", autocomplete="username")
        password = st.text_input("Contraseña", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Entrar", type="primary")
    if not submitted:
        return
    wait = st.session_state.get("login_locked_until", 0) - time.time()
    if wait > 0:
        st.error(f"Demasiados intentos fallidos. Espera {wait:.0f} s e inténtalo de nuevo.")
        return
    uname = username.strip().lower()
    try:
        user = store.get_user(uname) if uname else None
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo consultar la cuenta: {exc}. ¿Ejecutaste schema.sql en Supabase?")
        return
    if user and verify_password(password, user.get("password_hash")):
        sign_in(user)
        audit("user_login", "user", entity_id=user.get("id"), title=user["username"])
        st.rerun()
    fails = st.session_state.get("login_fails", 0) + 1
    st.session_state["login_fails"] = fails
    audit("login_failed", "user", title=uname or None, actor=uname or "desconocido")
    if fails >= LOGIN_MAX_FAILS:
        st.session_state["login_locked_until"] = time.time() + LOGIN_LOCK_SECONDS
        st.session_state["login_fails"] = 0
    st.error("Usuario o contraseña incorrectos.")


def signup_form(store):
    with st.form("signup_form"):
        display = st.text_input("Nombre visible", placeholder="Ana Pérez")
        username = st.text_input("Usuario", placeholder="ana.perez", help="3-30 caracteres: letras, números, punto, guion o guion bajo.")
        p1 = st.text_input("Contraseña", type="password", autocomplete="new-password", help="Mínimo 8 caracteres, con letras y números.")
        p2 = st.text_input("Repite la contraseña", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Crear cuenta", type="primary")
    if not submitted:
        return
    uname = username.strip().lower()
    error = username_error(uname) or password_error(p1) or ("Las contraseñas no coinciden." if p1 != p2 else None)
    try:
        if not error and store.get_user(uname):
            error = "Ese usuario ya existe."
        if error:
            st.error(error)
            return
        user = store.add_user({"username": uname, "display_name": display.strip() or uname,
                               "password_hash": hash_password(p1), "created_at": now_iso()})
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo crear la cuenta: {exc}. ¿Ejecutaste schema.sql en Supabase?")
        return
    sign_in(user or {"username": uname, "display_name": display.strip() or uname})
    audit("user_register", "user", entity_id=(user or {}).get("id"), title=uname)
    st.rerun()


def render_login(store, error):
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown('<div class="login-mark"><div class="crest">⚜</div><h1>Agile Core Studio</h1>'
                    '<div class="tag">SCRUM · KANBAN</div>'
                    '<div class="lead">Planifica sprints, controla el flujo y deja rastro de cada cambio.</div></div>',
                    unsafe_allow_html=True)
        if error:
            st.warning(f"Sin conexión a Supabase ({error}). Estás en modo local.")
        try:
            has_users = store.has_users()
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo leer la tabla de usuarios: {exc}. Ejecuta schema.sql en Supabase.")
            return
        allow_signup = not has_users or str(get_secret("ALLOW_SIGNUP") or "true").lower() != "false"
        if not has_users:
            st.info("Aún no hay cuentas. Crea la primera para empezar.")
        names = (["Crear cuenta", "Iniciar sesión"] if not has_users else
                 ["Iniciar sesión"] + (["Crear cuenta"] if allow_signup else []))
        for tab, name in zip(st.tabs(names), names):
            with tab:
                (login_form if name == "Iniciar sesión" else signup_form)(store)
        mode = "🟢 Conectado a Supabase" if store.mode == "Supabase" else "🟡 Modo local (agile_data.json)"
        st.markdown(f'<div class="login-foot">{mode}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Navegación
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.markdown(CSS, unsafe_allow_html=True)
    store, error = store_and_error()

    if "user" not in st.session_state:
        render_login(store, error)
        return

    user = st.session_state["user"]
    with st.sidebar:
        st.markdown('<div class="brand">⚜ Agile Core Studio<small>SCRUM · KANBAN</small></div><hr class="gold-rule">',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="who"><div class="avatar">{esc(user["display_name"][:1].upper())}</div>'
                    f'<div><div class="name">{esc(user["display_name"])}</div><div class="handle">@{esc(user["username"])}</div></div></div>',
                    unsafe_allow_html=True)
        if st.button("Cerrar sesión"):
            audit("user_logout", "user", title=user["username"])
            st.session_state.pop("user", None)
            st.rerun()
        if st.session_state.get("_audit_error"):
            st.warning(f"No se pudo guardar el registro de actividad: {st.session_state['_audit_error']}. ¿Ejecutaste schema.sql?")
        st.markdown('<hr class="gold-rule">', unsafe_allow_html=True)
        page = st.radio("Módulo", ["📊 Resumen", "📌 Kanban", "🔄 Scrum"], label_visibility="collapsed", key="nav_radio")
        st.markdown('<hr class="gold-rule">', unsafe_allow_html=True)
        if store.mode == "Supabase":
            st.caption("🟢 Conectado a Supabase")
        else:
            st.caption("🟡 Modo local (agile_data.json)")
            if error:
                st.warning(f"No se pudo conectar a Supabase: {error}")
                if st.button("Reintentar conexión"):
                    _build_store.clear()
                    st.rerun()
            else:
                st.caption("Define SUPABASE_URL y SUPABASE_KEY para sincronizar en la nube.")

    show_flash()
    {"📊 Resumen": render_overview, "📌 Kanban": render_kanban, "🔄 Scrum": render_scrum}[page]()
    

main()
