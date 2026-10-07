"""
KemetLab Antigravity & EasyCLI Native Account Manager Panel for Streamlit.
Provides Google OAuth login, multi-account pool monitoring, live quota tracking,
and internal CPA server lifecycle control.
"""

from __future__ import annotations

import streamlit as st
from local.cpa.cpa_service import (
    get_cpa_status,
    get_accounts,
    start_antigravity_oauth,
    toggle_account,
    delete_account,
    start_cpa_server,
    stop_cpa_server,
)

def render_cpa_panel(key_suffix: str = "") -> None:
    st.subheader("🌌 إدارة حسابات Antigravity والكوتا (Native EasyCLI)")
    st.caption("تسجيل دخول فوري بحسابات Google، وتوزيع أوتوماتيكي للأحمال والكوتا للنماذج العملاقة بدون أي برامج خارجية.")

    # 1. Server Status & Actions Row
    status = get_cpa_status()
    c1, c2, c3 = st.columns([2, 1, 1])

    with c1:
        if status.get("online"):
            st.success(f"🟢 السيرفر الداخلي متصل ويعمل على البورت {status.get('port')} ({status.get('models_count')} نموذج متاح)")
        else:
            st.error(f"🔴 السيرفر الداخلي متوقف (Port {status.get('port')})")

    with c2:
        if status.get("online"):
            if st.button("🔄 إعادة تشغيل السيرفر", key=f"cpa_restart_{key_suffix}"):
                stop_cpa_server()
                start_cpa_server()
                st.rerun()
        else:
            if st.button("▶️ تشغيل السيرفر الداخلي", key=f"cpa_start_{key_suffix}"):
                start_cpa_server()
                st.rerun()

    with c3:
        if st.button("⚡ تحديث القائمة", key=f"cpa_refresh_{key_suffix}"):
            st.rerun()

    st.divider()

    # 2. Main Login Banner
    login_col1, login_col2 = st.columns([3, 1])
    with login_col1:
        st.markdown(
            "**ربط حساب جديد:** اضغط على الزر لفتح صفحة مصادقة Google الرسمية في المتصفح. "
            "بمجرد الموافقة، يُحفظ الحساب في الحوض المشترك لتوفير كوتا إضافية للتجارب."
        )
    with login_col2:
        if st.button("➕ تسجيل حساب جديد (OAuth)", type="primary", key=f"cpa_login_btn_{key_suffix}"):
            res = start_antigravity_oauth()
            if res.get("status") == "success":
                st.info(res.get("message"))
            else:
                st.error(res.get("message"))

    st.write("")

    # 3. Accounts Pool & Live Quota
    accounts = get_accounts()
    total_accs = len(accounts)
    active_accs = sum(1 for a in accounts if not a.get("disabled") and a.get("status") != "cooldown")
    cooling_accs = sum(1 for a in accounts if a.get("status") == "cooldown")
    disabled_accs = sum(1 for a in accounts if a.get("disabled"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("إجمالي الحسابات", total_accs)
    m2.metric("حسابات نشطة بكامل الكوتا", active_accs)
    m3.metric("حسابات في فترة تبريد (Cooldown)", cooling_accs)
    m4.metric("حسابات معطلة", disabled_accs)

    st.write("")
    st.markdown("#### 👥 حوض الحسابات المسجلة (Accounts Pool)")

    if not accounts:
        st.warning("لا توجد حسابات Antigravity مسجلة حالياً. اضغط على زر 'تسجيل حساب جديد' أعلاه لإضافة أول حساب.")
        return

    for idx, acc in enumerate(accounts):
        email = acc.get("email", "حساب غير معروف")
        is_disabled = acc.get("disabled", False)
        cooldowns = acc.get("cooldowns", [])
        success_cnt = acc.get("success_count", 0)
        failed_cnt = acc.get("failed_count", 0)
        acc_name = acc.get("name", "")

        status_text = "🟢 نشط"
        if is_disabled:
            status_text = "⚪ معطل"
        elif cooldowns:
            status_text = "⏳ تبريد كوتا"

        with st.expander(f"{email} — {status_text} (طلبات ناجحة: {success_cnt})", expanded=not is_disabled):
            col_info, col_act = st.columns([3, 1])

            with col_info:
                st.markdown(f"- **المشروع:** `{acc.get('project_id', 'aicode-consumers')}`")
                st.markdown(f"- **إحصائيات الاستدعاء:** {success_cnt} ناجح / {failed_cnt} فاشل")
                if cooldowns:
                    st.warning("⚠️ الموديلات التالية تحت تبريد الكوتا المؤقت:")
                    for cd in cooldowns:
                        rem_min = max(1, int(cd.get("remaining_seconds", 0) / 60))
                        st.write(f"• `{cd.get('model')}`: متبقي {rem_min} دقيقة (HTTP {cd.get('status_code')})")
                else:
                    st.success("✨ كامل الكوتا متاحة (Gemini 3.8 Flash High, Claude Opus 4.6, Claude Sonnet 4.6).")

            with col_act:
                toggle_lbl = "تفعيل الحساب" if is_disabled else "تعطيل مؤقت"
                if st.button(toggle_lbl, key=f"tgl_{idx}_{key_suffix}"):
                    toggle_account(acc_name, not is_disabled)
                    st.rerun()

                if st.button("🗑️ حذف الحساب", key=f"del_{idx}_{key_suffix}"):
                    delete_account(acc_name)
                    st.rerun()
