"""Dual-track progress: production smoke + meta experiments (for dashboard)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from local.dashboard.cycle_metrics import load_baseline, run_improvement_summary, _pct_improve
from local.dashboard.data import load_champion, read_jsonl
from local.dashboard.job_status import read_job_status
from local.orchestrator import promotion


def tail_log(path: Path, max_lines: int = 15) -> str:
    """Return the last max_lines from a log file safely."""
    if not path.is_file():
        return "(لا يوجد ملف سجل بعد)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-max_lines:]
        return "\n".join(tail) or "(فارغ)"
    except Exception as e:
        return f"(تعذر قراءة السجل: {e})"


def _find_dual_track_config(repo_root: Path) -> Path | None:
    repo_root = Path(repo_root).resolve()
    candidates = [
        repo_root.parent / "dashboard_0602_174304" / "logs" / "dual_track.json",
        Path(r"C:\Users\Samer\dashboard_0602_174304") / "logs" / "dual_track.json",
    ]
    for root in (repo_root.parent, Path.home(), repo_root):
        try:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                p = child / "logs" / "dual_track.json"
                if p.is_file():
                    candidates.append(p)
        except PermissionError:
            continue
    for p in candidates:
        if p.is_file():
            return p
    return None


def load_dual_track(repo_root: Path | None = None) -> dict[str, Any] | None:
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    path = _find_dual_track_config(repo_root)
    if not path:
        return None
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg["_config_path"] = str(path)
        return cfg
    except (json.JSONDecodeError, OSError):
        return None


def _meta_progress(meta_run: Path, target_score: float = 50.0) -> dict[str, Any]:
    meta_run = Path(meta_run)
    exp_repo = meta_run  # fallback
    from local.dashboard.dual_track_panel import load_dual_track

    dt = load_dual_track()
    if dt:
        exp_repo = Path(dt.get("experiments_repo", meta_run))

    if (exp_repo / "MISSION_COMPLETE.json").is_file():
        return {
            "resource_score": 0.0,
            "target_score": target_score,
            "execution_pct": 100.0,
            "experiments": 0,
            "keep_count": 0,
            "job_state": "complete",
            "current_cycle": None,
            "stop_reason": "Mission complete: local-only",
            "mission_complete": True,
        }

    initial = 9999.0
    champ = promotion.load_champion_json(meta_run)
    score = float(champ.get("val_loss", initial))
    job = read_job_status(meta_run)
    exps = read_jsonl(meta_run / "logs" / "experiments.jsonl")
    n_keep = sum(1 for e in exps if e.get("outcome") == "KEEP")

    if score >= initial:
        pct = 0.0
    elif score <= target_score:
        pct = 100.0
    else:
        pct = max(0.0, min(100.0, (initial - score) / (initial - target_score) * 100.0))

    return {
        "resource_score": score,
        "target_score": target_score,
        "execution_pct": round(pct, 1),
        "experiments": len(exps),
        "keep_count": n_keep,
        "job_state": job.get("state", "idle"),
        "current_cycle": job.get("current_cycle"),
        "stop_reason": job.get("stop_reason"),
        "autorun_target_pct": job.get("autorun_target_pct"),
    }


def _production_progress(prod_run: Path) -> dict[str, Any]:
    prod_run = Path(prod_run)
    summ = run_improvement_summary(prod_run)
    job = read_job_status(prod_run)
    imp = summ.get("total_improvement_pct") or 0.0
    # Map improvement to execution % (target 99.8% for smoke mission complete)
    target_imp = 99.8
    exec_pct = min(100.0, max(0.0, float(imp) / target_imp * 100.0))

    return {
        **summ,
        "execution_pct": round(exec_pct, 1),
        "improvement_pct": imp,
        "target_improvement_pct": target_imp,
        "job_state": job.get("state", "idle"),
        "current_cycle": job.get("current_cycle"),
        "next_cycle": job.get("next_cycle"),
        "dual_track": job.get("dual_track"),
        "track": job.get("track", "production"),
    }


def dual_track_snapshot(repo_root: Path | None = None) -> dict[str, Any]:
    cfg = load_dual_track(repo_root)
    if not cfg:
        return {"configured": False}

    prod_run = Path(cfg["production_run"])
    meta_run = Path(cfg["meta_run"])
    prod = _production_progress(prod_run)
    meta = _meta_progress(meta_run, float(cfg.get("meta_target_score", 50)))

    # Overall local-readiness: 45% production metric + 55% meta optimization
    overall = round(prod["execution_pct"] * 0.45 + meta["execution_pct"] * 0.55, 1)

    def _last_ts(path: Path) -> str | None:
        if not path.is_file():
            return None
        from datetime import datetime, timezone

        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    prod_log = prod_run / "logs" / "production_autorun.log"
    meta_log = meta_run / "logs" / "meta_agent.log"

    return {
        "configured": True,
        "config_path": cfg.get("_config_path"),
        "production_run": str(prod_run),
        "meta_run": str(meta_run),
        "experiments_repo": cfg.get("experiments_repo"),
        "production": prod,
        "meta": meta,
        "overall_execution_pct": overall,
        "overall_note": (
            f"45%×{prod['execution_pct']} (smoke) + 55%×{meta['execution_pct']} (meta) = {overall}%"
        ),
        "production_last_activity": _last_ts(prod_log),
        "meta_last_activity": _last_ts(meta_log),
        "production_stuck_at_100": prod["execution_pct"] >= 100,
        "meta_needs_improvement": meta["execution_pct"] < 100,
    }


def render_dual_track_panel(repo_root: Path | None = None, *, key_suffix: str = "main") -> None:
    """Dashboard banner: production + meta progress % and live logs."""
    import streamlit as st

    snap = dual_track_snapshot(repo_root)
    if not snap.get("configured"):
        st.warning(
            "لم يُضبط المسار المزدوج بعد. شغّل: `scripts\\bootstrap_dual_track.ps1` "
            "ثم `scripts\\start_dual_track_agents.ps1`"
        )
        return

    prod = snap["production"]
    meta = snap["meta"]
    overall = snap["overall_execution_pct"]

    st.markdown("### 📡 المسار المزدوج — التقدّم الحي")
    c0, c1, c2, c3 = st.columns([2, 1, 1, 1])
    with c0:
        st.progress(min(1.0, overall / 100.0), text=f"تنفيذ إجمالي (جاهزية محلية): **{overall}%**")
        if snap.get("overall_note"):
            st.caption(snap["overall_note"])
        if snap.get("production_stuck_at_100") and snap.get("meta_needs_improvement"):
            complete_path = Path(snap.get("experiments_repo", "")) / "MISSION_COMPLETE.json"
            if complete_path.is_file():
                st.success("✅ **مهمة التجارب اكتملت** — local-only جاهز")
            else:
                st.info(
                    "النسبة الإجمالية **ثابتة** لأن الموديل الأساسي وصل 100% — "
                    "Meta يعمل على نسخة التجارب (local-only)."
                )
    with c1:
        st.metric(
            "الموديل الأساسي (smoke)",
            f"{prod.get('execution_pct', 0)}%",
            delta=f"تحسن {prod.get('improvement_pct', 0):+.2f}%",
        )
    with c2:
        st.metric(
            "Meta (نسخة التجارب)",
            f"{meta.get('execution_pct', 0)}%",
            delta=f"score={meta.get('resource_score', '—')}",
        )
    with c3:
        running = prod.get("job_state") == "running" or meta.get("job_state") == "running"
        st.metric("الحالة", "🟢 يعمل" if running else "⏸️ متوقف/اكتمل")

    d1, d2 = st.columns(2)
    with d1:
        st.caption(
            f"**إنتاج:** `{Path(snap['production_run']).name}` | "
            f"champion={prod.get('current_val_loss', '—')} | "
            f"دورة {prod.get('current_cycle', '—')} | {prod.get('job_state')} | "
            f"آخر نشاط: {snap.get('production_last_activity') or '—'}"
        )
    with d2:
        st.caption(
            f"**تجارب:** `{Path(snap['meta_run']).name}` | "
            f"KEEP={meta.get('keep_count', 0)} | "
            f"دورة {meta.get('current_cycle', '—')} | {meta.get('job_state')} | "
            f"آخر نشاط: {snap.get('meta_last_activity') or '—'}"
        )

    with st.expander("آخر تحديثات السجل (إنتاج + meta)", expanded=running):
        l1, l2 = st.columns(2)
        prod_log = Path(snap["production_run"]) / "logs" / "production_autorun.log"
        meta_log = Path(snap["meta_run"]) / "logs" / "meta_agent.log"
        with l1:
            st.markdown("**سجل الموديل الأساسي**")
            st.code(tail_log(prod_log, 15), language=None)
        with l2:
            st.markdown("**سجل meta / Qwen**")
            st.code(tail_log(meta_log, 15), language=None)

    if running and st.button("🔄 تحديث التقدّم", key=f"dual_refresh_{key_suffix}"):
        st.rerun()

