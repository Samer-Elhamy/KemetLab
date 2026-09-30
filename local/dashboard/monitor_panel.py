"""UI: post-cycle monitor report (runs automatically after each cycle)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from local.dashboard.cycle_monitor import (
    HISTORY_JSONL,
    MONITOR_DIR,
    REPORT_MD,
    list_monitor_history,
    load_monitor_report,
    run_cycle_monitor,
)


def render_cycle_monitor_panel(run_dir: Path, *, key_suffix: str = "main") -> None:
    run_dir = Path(run_dir).resolve()
    report = load_monitor_report(run_dir)
    md_path = run_dir / "logs" / REPORT_MD
    job = {}
    job_path = run_dir / "logs" / "job_status.json"
    if job_path.exists():
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    st.subheader("متابع الدورة (تلقائي)")
    st.caption(
        "عملية **منفصلة** تُشغَّل بعد **كل دورة كاملة** — النتيجة في "
        f"`logs/{MONITOR_DIR}/` و `logs/cycle_monitor.json`."
    )

    last_mon = job.get("last_cycle_monitor")
    if last_mon:
        c = last_mon.get("cycle", "—")
        if last_mon.get("ok"):
            st.success(f"آخر متابع: الدورة **{c}** — ✅ نجح ({last_mon.get('passed', '—')} فحص)")
        elif last_mon.get("skipped"):
            st.info(f"آخر متابع: الدورة **{c}** — تخطي")
        else:
            st.warning(
                f"آخر متابع: الدورة **{c}** — ❌ فشل {last_mon.get('failed', '?')} فحص"
            )

    if not report:
        st.info("لم يُنفَّذ الفحص بعد — سيظهر هنا بعد اكتمال أول دورة.")
        cycle_n = int(job.get("last_cycle") or job.get("cycles_done") or 1)
        if st.button("تشغيل المتابع الآن", key=f"run_monitor_manual_{key_suffix}"):
            with st.spinner("جاري الفحص..."):
                summary = run_cycle_monitor(run_dir, cycle=cycle_n)
            st.session_state["monitor_flash"] = summary
            st.rerun()
        return

    ok = bool(report.get("ok"))
    cycle_n = report.get("cycle", "—")
    if ok:
        st.success(
            f"✅ الدورة **{cycle_n}**: {report.get('passed')} فحص ناجح"
            + (f" | {report.get('warnings')} تحذير" if report.get("warnings") else "")
        )
    else:
        st.error(
            f"❌ الدورة **{cycle_n}**: {report.get('failed')} فشل من "
            f"{report.get('passed', 0) + report.get('failed', 0)}"
        )

    exp = report.get("experiment") or {}
    if exp.get("val_loss") is not None:
        st.caption(
            f"تجربة: **{exp.get('outcome')}** | val_loss=**{exp.get('val_loss')}** | "
            f"مزوّد LLM: `{report.get('llm_provider', '—')}`"
        )

    failed = [c for c in report.get("checks", []) if c.get("status") == "fail"]
    if failed:
        with st.expander("تفاصيل الأخطاء", expanded=True):
            for c in failed:
                st.markdown(f"- **{c['name']}**: {c.get('detail', '')}")

    with st.expander("كل فحوصات الدورة الحالية", expanded=not ok):
        for c in report.get("checks", []):
            icon = {"ok": "✅", "fail": "❌", "warn": "⚠️"}.get(c.get("status"), "?")
            st.markdown(f"{icon} `{c['name']}` — {c.get('detail', '')}")

    hist = list_monitor_history(run_dir, limit=15)
    if hist:
        with st.expander("سجل المتابعات السابقة"):
            st.dataframe(pd.DataFrame(hist).iloc[::-1], use_container_width=True, hide_index=True)

    per_dir = run_dir / "logs" / MONITOR_DIR
    if per_dir.is_dir():
        files = sorted(per_dir.glob("cycle_*.json"), reverse=True)[:8]
        if files:
            with st.expander("تقارير أرشيف حسب الدورة"):
                pick = st.selectbox(
                    "اختر دورة",
                    files,
                    format_func=lambda p: p.stem,
                    key=f"pick_monitor_{key_suffix}",
                )
                if pick:
                    st.json(json.loads(pick.read_text(encoding="utf-8")))

    if md_path.exists():
        with st.expander("تقرير Markdown (آخر دورة)"):
            st.markdown(md_path.read_text(encoding="utf-8"))

    c1, c2 = st.columns(2)
    with c1:
        if st.button("إعادة فحص آخر دورة", key=f"rerun_monitor_{key_suffix}"):
            with st.spinner("..."):
                run_cycle_monitor(run_dir, cycle=int(report.get("cycle", 1)))
            st.rerun()
    with c2:
        hist_path = run_dir / "logs" / HISTORY_JSONL
        if hist_path.exists():
            st.caption(f"السجل: `{hist_path.name}`")
