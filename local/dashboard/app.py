"""
AutoScientists Local Dashboard + Research Chat (qwen35custom).

Run: streamlit run local/dashboard/app.py  →  http://localhost:8501
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.dashboard.chat_agent import (
    append_chat_log,
    load_chat_history,
    research_reply,
)
from local.dashboard.data import (
    discover_runs,
    experiments_df,
    graph_summary,
    load_champion,
    run_metadata,
    sessions_df,
)


def _sidebar_run_dir() -> Path | None:
    st.header("التجربة / Run")
    custom = st.text_input(
        "مسار يدوي",
        placeholder=r"C:\Users\Samer\qwen_test",
        key="custom_run_path",
    )
    runs = discover_runs(template_dir=_REPO)
    run_options = [str(r) for r in runs]
    if custom.strip():
        cp = Path(custom.strip())
        if cp.is_dir() and str(cp.resolve()) not in run_options:
            run_options = [str(cp.resolve())] + run_options
    if not run_options:
        st.warning("لا توجد تجارب. شغّل: `python launch.py NAME --task task-smoke-local --run`")
        return None
    selected = st.selectbox("مجلد التجربة", run_options, key="run_select")
    return Path(selected)


def _render_metrics_tab(run_dir: Path) -> None:
    meta = run_metadata(run_dir)
    champ = load_champion(run_dir)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Champion val_loss",
        f"{champ.get('val_loss', 0):.4f}" if isinstance(champ.get("val_loss"), (int, float)) else "—",
    )
    c2.metric("Direction", champ.get("direction", "minimize"))
    c3.metric("Runtime", meta.get("runtime", "local"))
    c4.metric("Task", meta.get("task_type", "—"))

    exp_df = experiments_df(run_dir)
    st.subheader("التجارب")
    if exp_df.empty:
        st.info("لا تجارب بعد.")
    else:
        k = (exp_df["outcome"] == "KEEP").sum() if "outcome" in exp_df.columns else 0
        st.caption(f"KEEP: {k} | DISCARD: {len(exp_df) - k}")
        if "val_loss" in exp_df.columns and "cycle" in exp_df.columns:
            st.line_chart(exp_df.sort_values("cycle").set_index("cycle")["val_loss"], height=200)
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
        "اكتب **فكرتك الأساسية** — يجيب من سجلات التجربة (champion، تجارب، graph) عبر **qwen35custom**"
    )

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


def main() -> None:
    st.set_page_config(
        page_title="AutoScientists",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("AutoScientists")
    st.caption("لوحة المتابعة + **شات بحث** محلي (qwen35custom) — http://localhost:8501")

    with st.sidebar:
        run_dir = _sidebar_run_dir()
        st.divider()
        st.markdown("**تشغيل تجربة:**")
        st.code("python launch.py NAME --task task-smoke-local --run", language=None)

    if run_dir is None:
        st.stop()

    tab_chat, tab_dash = st.tabs(["💬 بحث / Chat", "📊 لوحة المتابعة"])

    with tab_chat:
        _render_chat_tab(run_dir)

    with tab_dash:
        _render_metrics_tab(run_dir)


if __name__ == "__main__":
    main()
