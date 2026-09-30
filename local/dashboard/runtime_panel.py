"""Dashboard: Ollama / GPU / mock-mode status."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from local.llm.runtime_health import (
    load_health_report,
    mock_mode_enabled,
    run_ollama_ps_cli,
    run_runtime_health,
    save_health_report,
)


def render_runtime_health_panel(run_dir: Path | None = None, *, key_suffix: str = "rt") -> dict:
    st.subheader("حالة Ollama و GPU")
    from local.llm.ollama_client import _llm_provider

    provider = _llm_provider()
    if provider != "ollama":
        st.info(f"مزوّد LLM الحالي: **{provider}** (سحابي — لا يحتاج GPU محلي)")

    mock = mock_mode_enabled()
    if mock:
        st.error(
            "**وضع MOCK مفعّل** (`LOCAL_MOCK_LLM=1`) — qwen **لا يعمل** والـ GPU لن يُستخدم للذكاء الاصطناعي. "
            "أزل المتغير من البيئة وأعد تشغيل اللوحة."
        )
        if st.button("تعطيل MOCK في هذه الجلسة", key=f"clear_mock_{key_suffix}"):
            import os

            os.environ.pop("LOCAL_MOCK_LLM", None)
            st.session_state.pop("last_runtime_health", None)
            st.rerun()

    if st.button("فحص الآن", key=f"health_check_{key_suffix}"):
        with st.spinner("جاري فحص Ollama و PyTorch..."):
            report = run_runtime_health(quick_probe=False)
            if run_dir:
                save_health_report(run_dir, report)
        st.session_state["last_runtime_health"] = report
        st.rerun()

    report = st.session_state.get("last_runtime_health")
    if run_dir and not report:
        report = load_health_report(run_dir)
    if not report:
        report = run_runtime_health(quick_probe=True)

    if report.get("ready_for_real_run"):
        st.success(report.get("summary_ar", "جاهز"))
    elif report.get("mock_mode"):
        st.warning(report.get("summary_ar", ""))
    else:
        st.error(report.get("summary_ar", "غير جاهز"))

    c1, c2 = st.columns(2)
    with c1:
        oll = report.get("ollama", {})
        st.markdown("**Ollama**")
        st.write("متصل:" if oll.get("reachable") else "غير متصل:", oll.get("reachable"))
        missing = report.get("missing_models") or []
        if missing:
            st.code("ollama pull " + "\nollama pull ".join(missing))
    with c2:
        pt = report.get("pytorch", {})
        st.markdown("**train.py (PyTorch)**")
        st.write("CUDA:", pt.get("cuda_available"))
        if pt.get("device_name"):
            st.caption(pt["device_name"])

    ps = report.get("ollama_ps", {})
    if ps.get("using_vram"):
        st.info(
            f"موديلات محمّلة في VRAM: {ps.get('count')} "
            f"(~{(ps.get('vram_bytes') or 0) // (1024 * 1024)} MB) — راقب **ollama.exe** في Task Manager → GPU"
        )
    else:
        st.caption(
            "لا موديل في VRAM الآن — طبيعي قبل Propose. أثناء الدورة ابحث عن **ollama.exe** وليس python.exe."
        )

    probe = report.get("generate_probe")
    if probe and not probe.get("skipped"):
        if probe.get("ok"):
            st.caption(f"اختبار توليد ({probe.get('model')}): ناجح")
        else:
            st.caption(f"اختبار توليد فشل: {probe.get('error', '')[:200]}")

    with st.expander("ollama ps (CLI)"):
        st.code(run_ollama_ps_cli() or "(فارغ)")

    return report
