"""Live operations view: what's running, how many agents, what each does."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from local.dashboard.dual_track_panel import load_dual_track
from local.dashboard.job_status import job_state_label, peek_job_running, read_job_status
from local.orchestrator.agent_tracker import read_live


_STATUS_AR = {
    "idle": "⏸️ انتظار",
    "working": "🟢 يعمل",
    "done": "✅ انتهى",
    "error": "❌ خطأ",
    "skipped": "⏭️ تخطي",
}


def _log_recent(path: Path, seconds: int = 90) -> bool:
    if not path.is_file():
        return False
    age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    return age < seconds


def _track_label(track_id: str) -> str:
    return {"production": "الموديل الأساسي (smoke)", "meta": "Meta / نسخة التجارب"}.get(
        track_id, track_id
    )


def _collect_working_agents(run_dir: Path, track_id: str) -> list[dict[str, Any]]:
    live = read_live(run_dir)
    job = read_job_status(run_dir)
    pid_alive = peek_job_running(run_dir)
    rows: list[dict[str, Any]] = []

    worker_ids = set(live.get("current_workers") or [])
    if live.get("current_worker"):
        worker_ids.add(live["current_worker"])
    if job.get("current_agent"):
        worker_ids.add(job["current_agent"])

    for ag in live.get("agents") or []:
        status = ag.get("status", "idle")
        if status != "working" and ag.get("id") in worker_ids and (
            pid_alive or job.get("state") == "running"
        ):
            status = "working"
        if status != "working":
            continue
        task = ag.get("detail") or job.get("current_phase") or "—"
        rows.append(
            {
                "المسار": _track_label(track_id),
                "الوكيل": f"{ag.get('icon', '🤖')} {ag.get('name_ar', ag.get('id'))}",
                "النموذج": ag.get("model", "—"),
                "المهمة الآن": task,
                "الدورة": ag.get("cycle", live.get("cycle", "—")),
                "الحالة": _STATUS_AR.get(status, status),
            }
        )

    # Job says running but no working agent in file — synthesize from job_status
    if not rows and job.get("state") == "running":
        phase = job.get("current_phase") or job.get("track") or "تشغيل"
        agent = job.get("current_agent") or "orchestrator"
        rows.append(
            {
                "المسار": _track_label(track_id),
                "الوكيل": agent,
                "النموذج": "—",
                "المهمة الآن": phase,
                "الدورة": job.get("current_cycle", "—"),
                "الحالة": "🟢 يعمل",
            }
        )
    return rows


def _track_status(run_dir: Path, track_id: str, log_hint: Path | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    job = read_job_status(run_dir)
    live = read_live(run_dir)
    pid_alive = peek_job_running(run_dir)
    log_active = _log_recent(log_hint) if log_hint else False
    working = sum(1 for a in (live.get("agents") or []) if a.get("status") == "working")
    if working == 0 and live.get("current_workers"):
        working = len(live["current_workers"])

    state = job.get("state", "idle")
    is_live = pid_alive or state == "running" or log_active or working > 0

    return {
        "track_id": track_id,
        "label": _track_label(track_id),
        "run_dir": str(run_dir),
        "is_live": is_live,
        "job_state": state,
        "job_label": job_state_label(state),
        "pid": job.get("pid"),
        "pid_alive": pid_alive,
        "log_active": log_active,
        "cycle": job.get("current_cycle") or live.get("cycle"),
        "phase": job.get("current_phase") or live.get("job_state"),
        "working_agents": working,
        "total_agents": live.get("total_agents") or len(live.get("agents") or []),
        "stop_reason": job.get("stop_reason"),
    }


def live_ops_snapshot(repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    cfg = load_dual_track(repo_root)
    tracks: list[dict[str, Any]] = []
    all_working: list[dict[str, Any]] = []

    if cfg:
        prod = Path(cfg["production_run"])
        meta = Path(cfg["meta_run"])
        tracks.append(
            _track_status(
                prod,
                "production",
                prod / "logs" / "production_autorun.log",
            )
        )
        tracks.append(
            _track_status(meta, "meta", meta / "logs" / "meta_agent.log")
        )
        all_working.extend(_collect_working_agents(prod, "production"))
        all_working.extend(_collect_working_agents(meta, "meta"))
    else:
        # Fallback: scan common run dirs
        for p in [
            Path(r"C:\Users\Samer\dashboard_0602_174304"),
            Path(r"C:\Users\Samer\meta_qwen_local_0603"),
        ]:
            if p.is_dir() and (p / "champion.json").exists():
                tid = "meta" if "meta_" in p.name else "production"
                tracks.append(_track_status(p, tid, p / "logs" / "runner.log"))
                all_working.extend(_collect_working_agents(p, tid))

    live_tracks = [t for t in tracks if t["is_live"]]
    total_working = len(all_working) if all_working else sum(t["working_agents"] for t in live_tracks)

    return {
        "tracks": tracks,
        "live_track_count": len(live_tracks),
        "total_working_agents": total_working,
        "working_rows": all_working,
        "updated_at": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    }


def render_live_ops_panel(repo_root: Path | None = None, *, key_suffix: str = "ops") -> None:
    import streamlit as st

    snap = live_ops_snapshot(repo_root)
    st.markdown("### 🟢 ماذا يعمل الآن؟")

    c1, c2, c3 = st.columns(3)
    c1.metric("مسارات نشطة", snap["live_track_count"])
    c2.metric("وكلاء يعملون الآن", snap["total_working_agents"])
    c3.metric("آخر تحديث", snap["updated_at"])

    if not snap["tracks"]:
        st.info("لا توجد مهام — شغّل `start_dual_track_agents.ps1`")
        return

    # Track summary cards
    for t in snap["tracks"]:
        icon = "🟢" if t["is_live"] else "⚪"
        st.markdown(
            f"{icon} **{t['label']}** — {t['job_label']} | "
            f"دورة **{t['cycle'] or '—'}** | "
            f"وكلاء نشطون: **{t['working_agents']}** / {t['total_agents']} | "
            f"المرحلة: `{t['phase'] or '—'}`"
        )
        if t.get("stop_reason") and not t["is_live"]:
            st.caption(f"سبب التوقف: {t['stop_reason']}")

    st.markdown("#### الوكلاء النشطون — ماذا يفعل كل واحد؟")
    rows = snap["working_rows"]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.warning(
            "لا يوجد وكيل بحالة «يعمل» الآن — إما انتهت الدورة أو العملية متوقفة. "
            "تحقق من السجلات أو أعد تشغيل المسار."
        )
        with st.expander("كل الوكلاء (آخر حالة محفوظة)"):
            for t in snap["tracks"]:
                live = read_live(Path(t["run_dir"]))
                agents = live.get("agents") or []
                if not agents:
                    continue
                st.markdown(f"**{t['label']}**")
                df = pd.DataFrame(
                    [
                        {
                            "الوكيل": f"{a.get('icon','')} {a.get('name_ar', a.get('id'))}",
                            "الحالة": _STATUS_AR.get(a.get("status"), a.get("status")),
                            "آخر مهمة": a.get("detail", "—"),
                            "الدورة": a.get("cycle"),
                        }
                        for a in agents
                    ]
                )
                st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("🔄 تحديث الوكلاء", key=f"refresh_ops_{key_suffix}"):
        st.rerun()


def render_live_ops_panel_auto(repo_root: Path | None = None, *, key_suffix: str = "ops") -> None:
    """Auto-refresh every 3s while any track is live."""
    from datetime import timedelta

    import streamlit as st

    snap = live_ops_snapshot(repo_root)
    if any(t["is_live"] for t in snap["tracks"]):

        @st.fragment(run_every=timedelta(seconds=3))
        def _auto() -> None:
            render_live_ops_panel(repo_root, key_suffix=key_suffix)

        _auto()
    else:
        render_live_ops_panel(repo_root, key_suffix=key_suffix)
