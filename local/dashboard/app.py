"""
AutoScientists Local Dashboard + Research Chat (qwen35custom).

Run: streamlit run local/dashboard/app.py  →  http://localhost:8501
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit may start with cwd != repo root — bootstrap before `import local`
_app_file = Path(__file__).resolve()
_repo_guess = _app_file.parents[2]
if (_repo_guess / "launch.py").is_file() and (_repo_guess / "task-smoke-local" / "TASK.md").is_file():
    _repo_root = _repo_guess
else:
    _repo_root = _app_file.parents[2]
_rs = str(_repo_root)
if _rs not in sys.path:
    sys.path.insert(0, _rs)

import pandas as pd
import streamlit as st

from local.dashboard.repo_root import ensure_repo_on_syspath

_REPO = ensure_repo_on_syspath()

_IMPORT_ERROR: BaseException | None = None
try:
    from local.dashboard._imports import (
        append_chat_log,
        build_issue_report,
        create_dashboard_run,
        create_mission_only,
        cycle_results_df,
        discover_runs,
        experiments_df,
        graph_summary,
        is_job_running,
        load_champion,
        load_chat_history,
        patch_user_goal,
        read_job_status,
        repair_stale_job,
        render_agents_panel,
        render_agents_panel_live,
        research_reply,
        run_improvement_summary,
        run_metadata,
        sessions_df,
        start_runner_job,
    )
    from local.dashboard.missions import list_mission_summaries, mission_summary
except ImportError as exc:
    _IMPORT_ERROR = exc


def _render_cursor_inbox_banner(run_dir: Path | None = None, *, error: BaseException | None = None) -> None:
    """Show how to continue in this Cursor chat after auto-saved AGENT_INBOX.md."""
    from local.dashboard.cursor_inbox import INBOX_FILENAME, load_pending, report_dashboard_error

    if error is not None:
        info = report_dashboard_error(error, repo_root=_REPO, run_dir=run_dir, source="auto_capture")
    else:
        info = load_pending(_REPO) or {}

    st.error("حدث خطأ في لوحة التحكم — تم حفظه لمساعد Cursor.")
    st.markdown(
        f"**لنفس محادثة Cursor (هنا):** افتح الشات واكتب الرسالة أدناه، "
        f"أو ارفق `@{INBOX_FILENAME}`."
    )
    prompt = info.get("prompt") if isinstance(info, dict) else None
    if not prompt and isinstance(info, dict):
        prompt = info.get("prompt")
    if not prompt:
        from local.dashboard.cursor_inbox import _chat_prompt

        prompt = _chat_prompt(_REPO)
    st.code(prompt, language=None)
    inbox = _REPO / INBOX_FILENAME
    st.caption(f"الملف: `{inbox}` — تم تحديثه تلقائياً.")
    st.info(
        "لا يمكن للداشبورد الكتابة داخل شات Cursor مباشرة (قيود Streamlit). "
        "الملف `AGENT_INBOX.md` = «إرسال» للمساعد في **هذه** المحادثة عند لصق الرسالة أو كتابة «تم»."
    )


def _render_job_banner(run_dir: Path, *, key_suffix: str = "main") -> None:
    from local.dashboard.job_status import job_state_label, peek_job_running, should_auto_refresh_agents

    stt = read_job_status(run_dir)
    state = stt.get("state", "idle")
    done = stt.get("cycles_done", 0)
    total = stt.get("cycles_total", "?")

    if should_auto_refresh_agents(run_dir):
        st.info(f"⏳ {job_state_label('running')} — دورات منفّذة: {done}/{total}")
        if stt.get("log"):
            st.caption(f"سجل: `{stt['log']}`")
        if st.button("تحديث الحالة", key=f"refresh_job_{key_suffix}"):
            st.rerun()
    elif state == "complete":
        st.success(f"✅ {job_state_label('complete')} ({done}/{total} دورات)")
        mon = stt.get("last_cycle_monitor") or stt.get("first_cycle_monitor")
        if mon and mon.get("launched"):
            cyc = mon.get("cycle", done)
            if mon.get("ok"):
                st.caption(f"متابع الدورة {cyc}: ✅ كل الفحوصات نجحت")
            elif not mon.get("skipped"):
                st.caption(f"متابع الدورة {cyc}: ❌ راجع تبويب التشغيل → متابع الدورة")
        summ = run_improvement_summary(run_dir)
        if summ.get("executed") and summ.get("total_improvement_pct") is not None:
            st.caption(
                f"تحسن عن خط الأساس الحقيقي: **{summ['total_improvement_pct']:+.2f}%** "
                f"({summ['baseline_val_loss']:.4f} → {summ['current_val_loss']:.4f})"
            )
    elif state == "stopped":
        st.warning(
            f"⏹️ {job_state_label('stopped')} — نُفّذ {done} من {total} دورات. "
            "يمكنك **متابعة** نفس المهمة من الشريط الجانبي."
        )
    elif state == "stale":
        st.warning(f"⚠️ {job_state_label('stale')} — {stt.get('error', '')}")
        if not peek_job_running(run_dir) and st.button("إصلاح والمتابعة", key=f"fix_stale_{key_suffix}"):
            from local.dashboard.job_status import repair_stale_job

            repair_stale_job(run_dir)
            st.rerun()
    elif state == "error":
        st.error(f"فشل التنفيذ: {stt.get('error', 'unknown')}")


def _render_agent_issue_panel(run_dir: Path | None) -> None:
    """Send diagnostics to Cursor via AGENT_INBOX.md (this chat)."""
    from local.dashboard.cursor_inbox import INBOX_FILENAME, report_dashboard_error

    st.divider()
    st.markdown("**🛠 إرسال للمساعد (نفس شات Cursor)**")
    st.caption(f"يحفظ `{INBOX_FILENAME}` — الصق الرسالة في **هذه** المحادثة")

    note = st.text_area(
        "ما المشكلة؟",
        height=80,
        placeholder="مثال: زر التنفيذ لا يعمل / ImportError ...",
        key="issue_user_note",
        label_visibility="collapsed",
    )

    job = read_job_status(run_dir) if run_dir else {}
    show_urgent = job.get("state") in ("error", "stale")

    if st.button(
        "📨 إرسال لهذه المحادثة",
        use_container_width=True,
        type="primary" if show_urgent else "secondary",
        key="send_issue_cursor",
    ):
        try:
            if note.strip():
                info = report_dashboard_error(
                    RuntimeError(note),
                    repo_root=_REPO,
                    run_dir=run_dir,
                    user_note=note,
                    source="user_report",
                )
            else:
                _, prompt = build_issue_report(run_dir, note, repo_root=_REPO)
                info = {"prompt": prompt, "inbox_path": str(_REPO / INBOX_FILENAME)}
            st.session_state["cursor_issue_prompt"] = info.get("prompt", "")
            st.session_state["cursor_issue_path"] = info.get("inbox_path", "")
            st.success("تم الحفظ — ارجع لشات Cursor والصق الرسالة أدناه.")
        except Exception as exc:
            report_dashboard_error(exc, repo_root=_REPO, run_dir=run_dir, source="report_button_failed")
            st.error(str(exc))

    pending = (_REPO / ".cursor" / "dashboard_pending.json")
    if pending.exists():
        st.caption("يوجد بلاغ محفوظ — الصق في الشات:")

    if prompt := st.session_state.get("cursor_issue_prompt"):
        st.code(prompt, language=None)
    if path := st.session_state.get("cursor_issue_path"):
        st.caption(f"ملف: `{path}`")


def _render_execute_tab(run_dir: Path | None) -> Path | None:
    """Run FSM — new mission or resume saved mission (keeps champion/graph)."""
    from local.dashboard.runtime_panel import render_runtime_health_panel

    render_runtime_health_panel(run_dir, key_suffix="execute")

    st.subheader("تشغيل المهمة (FSM حقيقي)")
    mode = st.session_state.get("mission_mode", "resume" if run_dir else "new")
    if mode == "resume" and run_dir:
        summ = mission_summary(run_dir)
        st.info(
            f"**متابعة مهمة محفوظة:** {summ['title']} | champion={summ.get('champion_val_loss')} | "
            f"الدورة التالية: **{summ['next_cycle']}** | حالة: {summ['job_state']}"
        )
        st.caption("البيانات القديمة (تجارب، graph، champion) **لن تُمسح** — يُضاف دورات جديدة فقط.")
    else:
        st.caption("مهمة **جديدة** = مجلد منفصل — يمكنك العودة للمهام القديمة من الشريط الجانبي.")

    flash = st.session_state.get("execute_flash")
    if flash:
        level = flash.get("level", "info")
        if level == "success":
            st.success(flash["text"])
        elif level == "warning":
            st.warning(flash["text"])
        else:
            st.error(flash["text"])
        if st.button("إخفاء الرسالة", key="dismiss_execute_flash"):
            del st.session_state["execute_flash"]
            st.rerun()

    active = run_dir
    if active:
        repair_stale_job(active)
        jst = read_job_status(active)
        if jst.get("state") in ("running", "stale", "error"):
            st.caption(f"حالة المهمة: **{jst.get('state')}** | PID: {jst.get('pid', '—')}")

    if active and st.button("إصلاح حالة عالقة", key="execute_repair"):
        if repair_stale_job(active):
            st.session_state["execute_flash"] = {
                "level": "success",
                "text": "تم إصلاح الحالة — جرّب التشغيل مرة أخرى.",
            }
        else:
            st.session_state["execute_flash"] = {"level": "warning", "text": "لا توجد حالة عالقة."}
        st.rerun()

    with st.form("fsm_execute_form", clear_on_submit=False, border=True):
        st.markdown("**إعدادات التشغيل**")
        goal = st.text_area(
            "مهمتك / هدف البحث",
            height=100,
            placeholder="مثال: قلّل val_loss بخفض lr إلى 0.02",
        )
        use_default_goal = st.checkbox("هدف افتراضي إن كان الحقل فارغاً", value=True)
        run_mode = st.radio(
            "مدة التشغيل",
            ["دورات محددة", "ساعات طويلة (مستمر)", "ساعات + حد أقصى للدورات"],
            horizontal=True,
        )
        c1, c2, c3 = st.columns(3)
        cycles = 1
        max_hours = 0.0
        with c1:
            if run_mode == "دورات محددة":
                cycles = int(st.number_input("عدد الدورات", min_value=1, max_value=5000, value=1))
                max_hours = 0.0
            elif run_mode == "ساعات طويلة (مستمر)":
                max_hours = float(st.number_input("ساعات", min_value=0.5, max_value=72.0, value=8.0, step=0.5))
                cycles = 0
            else:
                max_hours = float(st.number_input("ساعات", min_value=0.5, max_value=72.0, value=8.0, step=0.5))
                cycles = int(st.number_input("أقصى دورات", min_value=1, max_value=5000, value=200))
        with c2:
            pause_sec = float(st.number_input("استراحة بين الدورات (ث)", min_value=0.0, max_value=120.0, value=2.0))
        with c3:
            task_bundle = st.selectbox("قالب المهمة (جديدة فقط)", ["task-smoke-local"])
        mission_title = ""
        if st.session_state.get("mission_mode") == "new":
            mission_title = st.text_input("اسم المهمة (اختياري)", placeholder="مثال: خفض-val-loss-v2")

        col_run, col_save = st.columns(2)
        with col_run:
            submitted = st.form_submit_button("▶ ابدأ / تابع التنفيذ", type="primary", use_container_width=True)
        with col_save:
            save_only = st.form_submit_button("💾 حفظ مهمة جديدة فقط", use_container_width=True)

    if submitted or save_only:
        st.toast("جاري المعالجة...", icon="🚀")
        effective_goal = goal.strip()
        if not effective_goal and use_default_goal:
            effective_goal = "تحسين val_loss عبر ضبط lr و hidden_dim و steps"
        if not effective_goal:
            st.session_state["execute_flash"] = {
                "level": "warning",
                "text": "اكتب المهمة أو فعّل الهدف الافتراضي.",
            }
        else:
            try:
                target = active
                is_new = st.session_state.get("mission_mode") == "new" or target is None
                if is_new:
                    target = create_dashboard_run(
                        effective_goal,
                        title=mission_title or None,
                        template_dir=_REPO,
                        task_bundle=task_bundle,
                    )
                    st.session_state["run_select"] = str(target.resolve())
                    st.session_state["mission_mode"] = "resume"
                    active = target
                elif effective_goal:
                    patch_user_goal(target, effective_goal)

                if save_only and not submitted:
                    st.session_state["execute_flash"] = {
                        "level": "success",
                        "text": f"تم حفظ المهمة `{target}` بدون تشغيل — اخترها من الشريط الجانبي لاحقاً.",
                    }
                    st.session_state["run_select"] = str(target.resolve())
                    st.rerun()

                if not submitted:
                    st.rerun()

                res = start_runner_job(
                    target,
                    cycles=cycles,
                    max_hours=max_hours,
                    pause_seconds=pause_sec,
                    goal=effective_goal,
                    update_goal=bool(effective_goal),
                )
                st.session_state["last_start_result"] = res
                if res.get("ok"):
                    dur = (
                        f"{max_hours} ساعة"
                        if max_hours > 0 and cycles == 0
                        else f"{max_hours} ساعة / {cycles} دورة"
                        if max_hours > 0
                        else f"{cycles} دورة"
                    )
                    resume_note = ""
                    if res.get("resume"):
                        resume_note = f" (متابعة من الدورة {res.get('cycle_start')})"
                    st.session_state["execute_flash"] = {
                        "level": "success",
                        "text": (
                            f"✅ بدأ التشغيل — {dur}{resume_note} | PID **{res.get('pid')}** | "
                            f"`{target}` — راقب تبويب **الوكلاء**."
                        ),
                    }
                else:
                    msg = res.get("error", "لم يبدأ")
                    if res.get("log_tail"):
                        msg += f"\n\nآخر السجل:\n```\n{res['log_tail'][-600:]}\n```"
                    st.session_state["execute_flash"] = {"level": "warning", "text": msg}
            except Exception as exc:
                st.session_state["execute_flash"] = {"level": "error", "text": str(exc)}
        st.rerun()

    if last := st.session_state.get("last_start_result"):
        with st.expander("آخر نتيجة زر التشغيل", expanded=not last.get("ok")):
            st.json(last)

    if active:
        from local.dashboard.job_status import should_auto_refresh_agents

        if should_auto_refresh_agents(active):
            render_agents_panel_live(active, key_suffix="execute_live")
        else:
            render_agents_panel(active, key_suffix="execute")
        with st.expander("آخر سطور من سجل التشغيل"):
            log_p = active / "logs" / "runner.log"
            if log_p.exists():
                tail = log_p.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
                st.code("\n".join(tail) or "(فارغ)", language=None)
            else:
                st.caption("لا يوجد سجل بعد.")

        from local.dashboard.monitor_panel import render_cycle_monitor_panel

        render_cycle_monitor_panel(active, key_suffix="execute")
    return active


def _sidebar_run_dir() -> Path | None:
    st.header("المهام المحفوظة")
    st.caption("كل مهمة = مجلد مستقل — champion وتجارب وgraph محفوظين.")

    mode = st.radio(
        "الوضع",
        ["متابعة مهمة قديمة", "مهمة جديدة"],
        index=0 if st.session_state.get("mission_mode", "resume") == "resume" else 1,
        key="mission_mode_radio",
    )
    st.session_state["mission_mode"] = "new" if mode == "مهمة جديدة" else "resume"

    missions = list_mission_summaries(_REPO)
    # Prefer production run from dual-track config
    from local.dashboard.dual_track_panel import load_dual_track
    from local.dashboard.missions import mission_summary

    dt = load_dual_track(_REPO)
    if dt and st.session_state.get("mission_mode") == "resume":
        prod_path = str(Path(dt["production_run"]).resolve())
        if prod_path not in [m["path"] for m in missions]:
            missions.insert(0, mission_summary(Path(prod_path)))
        elif missions:
            missions.sort(
                key=lambda m: 0 if m["path"] == prod_path else 1,
            )
        if not st.session_state.get("run_select"):
            st.session_state["run_select"] = prod_path

    if missions:
        labels = [
            f"{m['title']} | loss={m.get('champion_val_loss', '—')} | دورات={m['cycles_done']} | {m['job_state']}"
            for m in missions
        ]
        paths = [m["path"] for m in missions]
        idx = 0
        if prev := st.session_state.get("run_select"):
            try:
                idx = paths.index(prev)
            except ValueError:
                idx = 0
        if st.session_state.get("mission_mode") == "resume":
            pick = st.selectbox("اختر مهمة", range(len(labels)), format_func=lambda i: labels[i], index=idx)
            st.session_state["run_select"] = paths[pick]
            return Path(paths[pick])
    else:
        st.info("لا مهام بعد — اختر «مهمة جديدة» وأنشئ واحدة.")

    custom = st.text_input("مسار يدوي", placeholder=r"C:\Users\Samer\...", key="custom_run_path")
    if custom.strip():
        cp = Path(custom.strip())
        if cp.is_dir():
            st.session_state["run_select"] = str(cp.resolve())
            return cp.resolve()

    if st.session_state.get("mission_mode") == "new":
        return None
    return None


def _render_cycle_results(run_dir: Path) -> None:
    """Per-cycle table with improvement percentages."""
    summ = run_improvement_summary(run_dir)
    st.subheader("نتائج كل دورة")

    if not summ.get("executed"):
        st.info("لم تُنفَّذ أي دورة FSM بعد — ابدأ من تبويب «تشغيل مهمة».")
        return

    st.caption(
        f"خط الأساس = **{summ.get('baseline_note', 'تدريب فعلي')}** "
        f"(params: {summ.get('baseline_params', {})}) — ليس الرقم 999 الافتراضي القديم."
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("خط الأساس (تدريب فعلي)", f"{summ['baseline_val_loss']:.4f}")
    m2.metric("Champion الحالي", f"{summ['current_val_loss']:.4f}")
    imp = summ.get("total_improvement_pct")
    m3.metric("التحسن الحقيقي", f"{imp:+.2f}%" if imp is not None else "—")
    m4.metric("دورات منفّذة", f"{summ['cycles_completed']} (KEEP: {summ['keep_count']})")
    if imp is not None and imp < 0:
        st.warning(
            "الـ champion الحالي **أسوأ** من خط الأساس — التجارب لم تحسّن بعد، أو المعاملات المقترحة أضعف."
        )

    cdf = cycle_results_df(run_dir)
    display = cdf.copy()
    if not display.empty:
        for col in ("improve_vs_baseline_pct", "improve_vs_prev_champion_pct"):
            if col in display.columns:
                display[col] = display[col].apply(
                    lambda x: f"{x:+.2f}%" if x is not None and pd.notna(x) else "—"
                )
        if "val_loss" in display.columns:
            display["val_loss"] = display["val_loss"].map(lambda x: f"{float(x):.6f}")

        st.dataframe(
            display[
                [
                    c
                    for c in [
                        "cycle",
                        "val_loss",
                        "outcome",
                        "improve_vs_baseline_pct",
                        "improve_vs_prev_champion_pct",
                        "champion_after",
                        "lr",
                        "hidden_dim",
                        "steps",
                    ]
                    if c in display.columns
                ]
            ].rename(
                columns={
                    "cycle": "دورة",
                    "val_loss": "val_loss",
                    "outcome": "نتيجة",
                    "improve_vs_baseline_pct": "تحسن عن خط الأساس",
                    "improve_vs_prev_champion_pct": "تحسن عن الدورة السابقة",
                    "champion_after": "champion بعد الدورة",
                    "lr": "lr",
                    "hidden_dim": "hidden",
                    "steps": "steps",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        if "val_loss" in cdf.columns and "cycle" in cdf.columns:
            chart_df = cdf.set_index("cycle")[["val_loss", "champion_after"]].astype(float)
            st.line_chart(chart_df, height=220)


def _render_metrics_tab(run_dir: Path) -> None:
    meta = run_metadata(run_dir)
    champ = load_champion(run_dir)

    _render_cycle_results(run_dir)

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Champion val_loss",
        f"{champ.get('val_loss', 0):.4f}" if isinstance(champ.get("val_loss"), (int, float)) else "—",
    )
    c2.metric("Direction", champ.get("direction", "minimize"))
    c3.metric("Runtime", meta.get("runtime", "local"))
    c4.metric("Task", meta.get("task_type", "—"))

    exp_df = experiments_df(run_dir)
    st.subheader("سجل التجارب (تفصيلي)")
    if exp_df.empty:
        st.info("لا تجارب بعد.")
    else:
        k = (exp_df["outcome"] == "KEEP").sum() if "outcome" in exp_df.columns else 0
        st.caption(f"KEEP: {k} | DISCARD: {len(exp_df) - k}")
        st.dataframe(exp_df, use_container_width=True, hide_index=True)

    st.subheader("FSM Sessions")
    sess_df = sessions_df(run_dir)
    if not sess_df.empty:
        st.dataframe(sess_df, use_container_width=True, hide_index=True)

    st.subheader("Graph-RAG")
    gdf = graph_summary(run_dir)
    if not gdf.empty:
        st.bar_chart(gdf.set_index("kind")["count"], height=180)

    with st.expander("Champion params"):
        st.json(champ.get("params", champ))


def _render_chat_tab(run_dir: Path) -> None:
    st.subheader("وكيل البحث المحلي")
    st.caption(
        "محادثة من الأدلة المحلية — فعّل «نفّذ دورة FSM» لتنفيذ المطلوب وليس النصيحة فقط"
    )
    run_fsm_on_send = st.checkbox("نفّذ دورة FSM عند الإرسال", value=True, key="chat_run_fsm")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = load_chat_history(run_dir)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("مسح المحادثة", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()
    with col_b:
        use_stream = st.checkbox("بث مباشر (مثل Cursor)", value=True)

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    placeholder_examples = (
        "مثال: أريد تقليل val_loss بتعديل معدل التعلم دون زيادة الخطوات..."
    )
    if user_input := st.chat_input(placeholder_examples):
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        append_chat_log(run_dir, "user", user_input)

        with st.chat_message("user"):
            st.markdown(user_input)

        if run_fsm_on_send and user_input.strip():
            if is_job_running(run_dir):
                st.warning("تشغيل قيد التنفيذ — انتظر أو حدّث من تبويب التشغيل.")
            else:
                patch_user_goal(run_dir, user_input)
                start_runner_job(run_dir, cycles=1, max_hours=0, goal=user_input)
                st.info("🚀 بدأت دورة FSM — بعد الانتهاء حدّث الصفحة لرؤية النتائج.")

        with st.chat_message("assistant"):
            if use_stream:
                reply_text = st.write_stream(
                    research_reply(run_dir, user_input, st.session_state.chat_messages, stream=True)
                )
            else:
                with st.spinner("qwen35custom يفكّر..."):
                    reply_text = research_reply(
                        run_dir, user_input, st.session_state.chat_messages, stream=False
                    )
                st.markdown(reply_text)

        st.session_state.chat_messages.append({"role": "assistant", "content": reply_text})
        append_chat_log(run_dir, "assistant", reply_text)


def _main_ui() -> None:
    st.title("KemetLab")
    st.caption("لوحة المتابعة + **شات بحث** محلي — KemetLab Architecture — http://localhost:8501")

    from local.dashboard.dual_track_panel import render_dual_track_panel
    from local.dashboard.live_ops_panel import render_live_ops_panel_auto

    render_live_ops_panel_auto(_REPO, key_suffix="top")
    render_dual_track_panel(_REPO, key_suffix="top")

    with st.sidebar:
        run_dir = _sidebar_run_dir()
        _render_agent_issue_panel(run_dir)
        st.divider()
        st.markdown("**سطر أوامر (اختياري):**")
        st.code("python launch.py NAME --task task-smoke-local --run", language=None)

    tab_now, tab_run, tab_missions, tab_agents, tab_chat, tab_dash, tab_antigravity = st.tabs(
        ["🟢 الآن", "🚀 تشغيل", "📋 المهام", "👥 الوكلاء", "💬 بحث", "📊 النتائج", "🌌 حسابات Antigravity"]
    )

    with tab_now:
        from local.dashboard.live_ops_panel import render_live_ops_panel_auto
        from local.dashboard.dual_track_panel import load_dual_track, render_dual_track_panel
        from local.dashboard.agents_panel import render_agents_panel, render_agents_panel_live
        from local.dashboard.job_status import should_auto_refresh_agents

        render_live_ops_panel_auto(_REPO, key_suffix="tab_now")
        st.divider()
        render_dual_track_panel(_REPO, key_suffix="tab_now")

        cfg = load_dual_track(_REPO)
        if cfg:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**وكلاء الموديل الأساسي**")
                prod = Path(cfg["production_run"])
                if should_auto_refresh_agents(prod):
                    render_agents_panel_live(prod, key_suffix="now_prod")
                else:
                    render_agents_panel(prod, key_suffix="now_prod")
            with c2:
                st.markdown("**وكلاء Meta (تجارب)**")
                meta = Path(cfg["meta_run"])
                if should_auto_refresh_agents(meta):
                    render_agents_panel_live(meta, key_suffix="now_meta")
                else:
                    render_agents_panel(meta, key_suffix="now_meta")
        elif run_dir:
            st.divider()
            st.markdown(f"**تفاصيل مهمة:** `{run_dir.name}`")
            if should_auto_refresh_agents(run_dir):
                render_agents_panel_live(run_dir, key_suffix="now_tab")
            else:
                render_agents_panel(run_dir, key_suffix="now_tab")

    with tab_run:
        run_dir = _render_execute_tab(run_dir) or run_dir

    with tab_missions:
        st.subheader("كل المهام المحفوظة")
        ms = list_mission_summaries(_REPO)
        if ms:
            df = pd.DataFrame(ms)
            show = df[
                ["title", "folder", "champion_val_loss", "cycles_done", "next_cycle", "job_state", "goal"]
            ]
            st.dataframe(show, use_container_width=True, hide_index=True)
            st.caption("لتشغيل مهمة قديمة: الشريط الجانبي → متابعة مهمة قديمة → اختر → ابدأ/ تابع.")
        else:
            st.info("لا مهام محفوظة بعد.")

    if run_dir is None:
        with tab_agents:
            st.info("أنشئ مهمة جديدة من الشريط الجانبي أو تبويب «تشغيل».")
        with tab_chat:
            st.info("أنشئ مهمة جديدة أولاً.")
        with tab_dash:
            st.info("أنشئ مهمة جديدة أولاً.")
        if st.session_state.get("mission_mode") != "new":
            st.stop()

    if run_dir:
        _render_job_banner(run_dir, key_suffix="global")

    with tab_agents:
        if run_dir:
            from local.dashboard.job_status import should_auto_refresh_agents

            if should_auto_refresh_agents(run_dir):
                render_agents_panel_live(run_dir, key_suffix="agents_tab")
            else:
                render_agents_panel(run_dir, key_suffix="agents_tab")
        else:
            st.info("اختر أو أنشئ مهمة أولاً.")

    with tab_chat:
        if run_dir:
            _render_chat_tab(run_dir)
        else:
            st.info("اختر مهمة من الشريط الجانبي.")

    with tab_dash:
        if run_dir:
            _render_metrics_tab(run_dir)
        else:
            st.info("اختر مهمة من الشريط الجانبي.")

    with tab_antigravity:
        from local.dashboard.cpa_panel import render_cpa_panel
        render_cpa_panel(key_suffix="app_tab")


def main() -> None:
    st.set_page_config(
        page_title="KemetLab",
        page_icon="⚗️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if _IMPORT_ERROR is not None:
        _render_cursor_inbox_banner(error=_IMPORT_ERROR)
        st.stop()

    try:
        _main_ui()
    except Exception as exc:
        run_sel = st.session_state.get("run_select")
        run_path = Path(run_sel) if run_sel else None
        _render_cursor_inbox_banner(run_dir=run_path, error=exc)
        st.stop()


if __name__ == "__main__":
    main()
