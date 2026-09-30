"""Central dashboard imports (isolated from run-dir `local/` copies)."""

from __future__ import annotations

from local.dashboard.chat_agent import (
    append_chat_log,
    load_chat_history,
    research_reply,
)
from local.dashboard.agents_panel import render_agents_panel, render_agents_panel_live
from local.dashboard.cycle_metrics import cycle_results_df, run_improvement_summary
from local.dashboard.data import (
    discover_runs,
    experiments_df,
    graph_summary,
    load_champion,
    run_metadata,
    sessions_df,
)
from local.dashboard.executor import (
    create_dashboard_run,
    create_mission_only,
    patch_user_goal,
    start_runner_job,
)
from local.dashboard.issue_report import build_issue_report
from local.dashboard.job_status import is_job_running, read_job_status, repair_stale_job

__all__ = [
    "append_chat_log",
    "load_chat_history",
    "research_reply",
    "render_agents_panel",
    "render_agents_panel_live",
    "cycle_results_df",
    "run_improvement_summary",
    "discover_runs",
    "experiments_df",
    "graph_summary",
    "load_champion",
    "run_metadata",
    "sessions_df",
    "create_dashboard_run",
    "create_mission_only",
    "is_job_running",
    "patch_user_goal",
    "read_job_status",
    "repair_stale_job",
    "start_runner_job",
    "build_issue_report",
]
