"""Dashboard UI: live local agent swarm status."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from local.dashboard.job_status import (
    job_state_label,
    peek_job_running,
    read_job_status,
    should_auto_refresh_agents,
)
from local.orchestrator.agent_registry import LOCAL_AGENTS
from local.orchestrator.agent_tracker import read_live, read_recent_events


_STATUS_AR = {
    "idle": "⏸️ انتظار",
    "working": "🟢 يعمل",
    "done": "✅ انتهى",
    "error": "❌ خطأ",
    "skipped": "⏭️ تخطي",
}

_STATUS_COLOR = {
    "working": "#1b5e20",
    "idle": "#616161",
    "done": "#0d47a1",
    "error": "#b71c1c",
    "skipped": "#e65100",
}


def _parse_ends_at(st: dict) -> datetime | None:
    raw = st.get("ends_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fsm_line_from_log(run_dir: Path) -> str | None:
    log = Path(run_dir) / "logs" / "runner.log"
    if not log.exists():
        return None
    for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]):
        if "[FSM]" in line:
            return line.strip()
    return None


def _agents_file_mtime(run_dir: Path) -> str:
    path = Path(run_dir) / "logs" / "agents_live.json"
    if not path.exists():
        return "لا يوجد ملف وكلاء بعد"
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%H:%M:%S UTC")


def _effective_active(live: dict, job: dict, pid_alive: bool) -> int:
    """Count working agents; if job is live but file lags, trust current_workers."""
    active = int(live.get("active_count") or 0)
    if active > 0:
        return active
    multi = live.get("current_workers") or []
    if multi:
        return len(multi)
    if not pid_alive and job.get("state") != "running":
        return 0
    worker = live.get("current_worker") or job.get("current_agent")
    if worker:
        return 1
    return 0


def _display_status(ag: dict, job: dict, live: dict, pid_alive: bool) -> str:
    """Highlight the worker Streamlit might have missed between 2s polls."""
    status = ag.get("status", "idle")
    if status == "working":
        return status
    if not pid_alive and job.get("state") != "running":
        return status
    worker = live.get("current_worker") or job.get("current_agent")
    if worker and ag.get("id") == worker:
        return "working"
    if ag.get("id") == "orchestrator" and job.get("state") == "running" and pid_alive:
        return "working"
    return status


def render_agents_panel(run_dir: Path, *, key_suffix: str = "main") -> None:
    st.subheader("فريق الوكلاء المحلي")
    live = read_live(run_dir)
    job = read_job_status(run_dir)
    running = should_auto_refresh_agents(run_dir)
    pid_alive = peek_job_running(run_dir)

    total = live.get("total_agents") or len(LOCAL_AGENTS)
    active = _effective_active(live, job, pid_alive)
    cycle = live.get("cycle", job.get("current_cycle", job.get("last_cycle", "—")))
    state = job.get("state", "idle")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("إجمالي الوكلاء", total)
    c2.metric("النشطون الآن", active)
    c3.metric("الدورة الحالية", cycle)
    c4.metric("حالة المهمة", job_state_label(state))

    st.caption(
        f"PID: {job.get('pid', '—')} | {'🟢 العملية حية' if pid_alive else '⚪ لا توجد عملية'} | "
        f"آخر تحديث وكلاء: {_agents_file_mtime(run_dir)}"
    )

    workers_multi = live.get("current_workers") or []
    worker = live.get("current_worker") or job.get("current_agent")
    phase = job.get("current_phase") or ""
    team_count = live.get("team_count")
    if team_count:
        st.caption(f"وضع **الفرق** — {team_count} فرق | نشطون: {len(workers_multi) or active}")
    if running:
        st.info("التحديث التلقائي كل ثانيتين — أو اضغط **تحديث الآن**.")
        if active == 0 and worker:
            name_map = {a["id"]: a["name_ar"] for a in LOCAL_AGENTS}
            st.warning(
                f"**الوكيل النشط:** {name_map.get(worker, worker)} — {phase or 'يعمل...'}"
            )
        log_line = _fsm_line_from_log(run_dir)
        if log_line:
            st.code(log_line, language=None)
    else:
        st.caption(f"الحالة: **{job_state_label(state)}** — اضغط تحديث بعد تشغيل مهمة جديدة.")

    if st.button("🔄 تحديث الآن", key=f"refresh_agents_{key_suffix}"):
        st.rerun()

    if job.get("max_hours"):
        ends = _parse_ends_at(job)
        elapsed = job.get("elapsed_hours")
        cap = f"تشغيل طويل — حتى {job['max_hours']} ساعة"
        if ends:
            cap += f" (ينتهي ~{ends.strftime('%H:%M')} UTC)"
        if elapsed is not None:
            cap += f" | مضى {elapsed:.2f} ساعة"
        total_c = job.get("cycles_total")
        done_c = job.get("cycles_done", 0)
        if total_c:
            cap += f" | دورات: {done_c}/{total_c}"
        st.caption(cap)

    agents = live.get("agents") or []
    if not agents:
        for spec in LOCAL_AGENTS:
            agents.append({**spec, "status": "idle", "detail": "لم يبدأ بعد — انتظر بدء الدورة"})

    core_agents = [a for a in agents if not str(a.get("id", "")).startswith("team:")]
    team_agents = [a for a in agents if str(a.get("id", "")).startswith("team:")]

    if team_agents:
        st.markdown("**الفرق (تشكيل / تفكيك / عمل متوازي)**")
        by_team: dict[str, list] = {}
        for a in team_agents:
            tid = a.get("team_id") or str(a.get("id", "")).split(":")[1]
            by_team.setdefault(tid, []).append(a)
        try:
            from local.orchestrator.team_manager import read_roster, teams_as_list

            roster = {t["id"]: t for t in teams_as_list(read_roster(run_dir))}
        except Exception:
            roster = {}
        for tid, members in by_team.items():
            meta = roster.get(tid, {})
            hyp = (meta.get("hypothesis") or "")[:100]
            working_n = sum(1 for m in members if m.get("status") == "working")
            st.markdown(
                f"**{meta.get('name_ar', tid)}** — {working_n} نشط | _{hyp}_"
            )
            cols_t = st.columns(min(len(members), 3))
            for j, ag in enumerate(members):
                status = _display_status(ag, job, live, pid_alive)
                label = _STATUS_AR.get(status, status)
                color = _STATUS_COLOR.get(status, "#333")
                with cols_t[j % len(cols_t)]:
                    st.markdown(
                        f"<small style='color:{color}'><b>{ag.get('icon','')} {label}</b> — "
                        f"{ag.get('detail','')}</small>",
                        unsafe_allow_html=True,
                    )
        st.markdown("**البنية التحتية (FSM)**")

    display_agents = core_agents if team_agents else agents

    st.markdown(
        """
<style>
@keyframes agent-pulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(76,175,80,0.35); }
  50% { box-shadow: 0 0 0 6px rgba(76,175,80,0.15); }
}
</style>
""",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, ag in enumerate(display_agents):
        status = _display_status(ag, job, live, pid_alive)
        label = _STATUS_AR.get(status, status)
        color = _STATUS_COLOR.get(status, "#333")
        pulse = "animation:agent-pulse 1.5s ease-in-out infinite;" if status == "working" else ""
        with cols[i % 2]:
            st.markdown(
                f"""
<div style="border:1px solid #ddd;border-radius:8px;padding:10px;margin-bottom:8px;
border-right:5px solid {color};{pulse}">
<strong>{ag.get('icon', '🤖')} {ag.get('name_ar', ag.get('id'))}</strong><br>
<small>{ag.get('model', '')}</small><br>
<span style="color:{color}"><b>{label}</b></span><br>
<small>{ag.get('detail', '')}</small><br>
<small style="color:#888">{ag.get('role', '')}</small>
</div>
""",
                unsafe_allow_html=True,
            )

    ev_path = Path(run_dir) / "logs" / "team_events.jsonl"
    if ev_path.exists():
        with st.expander("سجل تشكيل/تفكيك الفرق"):
            lines = ev_path.read_text(encoding="utf-8").splitlines()[-15:]
            for line in lines:
                if line.strip():
                    try:
                        st.json(json.loads(line))
                    except json.JSONDecodeError:
                        st.text(line)

    events = read_recent_events(run_dir, limit=20)
    if events:
        st.markdown("**آخر أحداث الوكلاء**")
        edf = pd.DataFrame(events)
        name_map = {a["id"]: a["name_ar"] for a in LOCAL_AGENTS}
        if "agent_id" in edf.columns:
            edf["وكيل"] = edf["agent_id"].map(lambda x: name_map.get(x, x))
        show_cols = [c for c in ["ts", "وكيل", "agent_id", "status", "detail", "cycle"] if c in edf.columns]
        st.dataframe(edf[show_cols].iloc[::-1], use_container_width=True, hide_index=True)

    if running or state == "running":
        if st.button("⏹ إيقاف لطيف (بعد انتهاء الدورة الحالية)", key=f"stop_job_{key_suffix}", type="secondary"):
            from local.dashboard.executor import request_stop_job

            request_stop_job(run_dir)
            st.warning("طُلب الإيقاف — الحالة ستصبح «متوقفة» وليس «اكتملت».")
            st.rerun()


@st.fragment(run_every=timedelta(seconds=2))
def render_agents_panel_live(run_dir: Path, *, key_suffix: str = "agents") -> None:
    """Auto-refresh while job may be running (one fragment per tab — unique keys)."""
    render_agents_panel(run_dir, key_suffix=key_suffix)
