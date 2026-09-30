"""Post-first-cycle health checks — runs as a separate monitor task."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_JSON = "cycle_monitor.json"
REPORT_MD = "cycle_monitor_report.md"
MONITOR_DIR = "cycle_monitors"
HISTORY_JSONL = "cycle_monitor_history.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(name: str, ok: bool, detail: str = "", *, warn: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "warn": warn and ok,
        "status": "ok" if ok else ("warn" if warn else "fail"),
        "detail": detail,
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def run_cycle_monitor(focus_root: Path, *, cycle: int = 1) -> dict[str, Any]:
    """
    Verify mission artifacts after the first FSM cycle.
    Returns summary dict; writes logs/cycle_monitor.json + report markdown.
    """
    focus_root = Path(focus_root).resolve()
    checks: list[dict[str, Any]] = []

    # --- Core files ---
    for rel in (
        "task/TASK.md",
        "champion.json",
        "logs/experiments.jsonl",
        "logs/job_status.json",
        "logs/agents_live.json",
        "RUNTIME",
    ):
        p = focus_root / rel
        checks.append(_check(f"file:{rel}", p.exists(), str(p) if p.exists() else "مفقود"))

    # --- Baseline (not placeholder 999) ---
    baseline_p = focus_root / "logs" / "baseline.json"
    if baseline_p.exists():
        try:
            bl = json.loads(baseline_p.read_text(encoding="utf-8"))
            v = float(bl.get("val_loss", 999))
            src = str(bl.get("source", ""))
            bad = v >= 900 or src in ("bootstrap", "placeholder", "default")
            checks.append(
                _check(
                    "baseline_measured",
                    not bad,
                    f"val_loss={v} source={src}",
                    warn=not bad and v > 50,
                )
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            checks.append(_check("baseline_measured", False, str(exc)))
    else:
        checks.append(_check("baseline_measured", False, "logs/baseline.json مفقود"))

    # --- Experiment for this cycle ---
    exps = _read_jsonl(focus_root / "logs" / "experiments.jsonl")
    cycle_rows = [r for r in exps if int(r.get("cycle", -1)) == cycle]
    checks.append(
        _check(
            "experiment_logged",
            len(cycle_rows) >= 1,
            f"دورة {cycle}: {len(cycle_rows)} سجل/سجلات",
        )
    )
    if cycle_rows:
        row = cycle_rows[-1]
        checks.append(
            _check(
                "experiment_fields",
                "val_loss" in row and "outcome" in row,
                f"outcome={row.get('outcome')} val_loss={row.get('val_loss')}",
            )
        )

    # --- Champion JSON ---
    champ_p = focus_root / "champion.json"
    if champ_p.exists():
        try:
            champ = json.loads(champ_p.read_text(encoding="utf-8"))
            checks.append(
                _check(
                    "champion_valid",
                    "val_loss" in champ and isinstance(champ.get("params"), dict),
                    f"val_loss={champ.get('val_loss')}",
                )
            )
        except json.JSONDecodeError as exc:
            checks.append(_check("champion_valid", False, str(exc)))

    # --- Graph DB ---
    gdb = focus_root / "logs" / "graph.db"
    if not gdb.exists():
        gdb = focus_root / "graph.db"
    if gdb.exists():
        try:
            conn = sqlite3.connect(str(gdb))
            cur = conn.execute("SELECT COUNT(*) FROM nodes")
            n_nodes = cur.fetchone()[0]
            conn.close()
            checks.append(_check("graph_db", n_nodes > 0, f"nodes={n_nodes}"))
        except sqlite3.Error as exc:
            checks.append(_check("graph_db", False, str(exc)))
    else:
        checks.append(_check("graph_db", False, "graph.db مفقود"))

    # --- Sessions log ---
    sess = _read_jsonl(focus_root / "logs" / "sessions.jsonl")
    checks.append(
        _check(
            "sessions_logged",
            any(int(s.get("cycle", -1)) == cycle for s in sess),
            f"إجمالي جلسات: {len(sess)}",
        )
    )

    # --- Agents live (teams mode) ---
    live_p = focus_root / "logs" / "agents_live.json"
    if live_p.exists():
        try:
            live = json.loads(live_p.read_text(encoding="utf-8"))
            agents = live.get("agents") or []
            team_agents = [a for a in agents if str(a.get("id", "")).startswith("team:")]
            checks.append(
                _check(
                    "agents_live",
                    len(agents) >= 7,
                    f"وكلاء={len(agents)} فرق={len(team_agents)} mode={live.get('mode')}",
                )
            )
            if live.get("mode") == "teams":
                checks.append(
                    _check(
                        "team_mode_roster",
                        (focus_root / "teams" / "roster.md").exists(),
                        f"team_count={live.get('team_count')}",
                    )
                )
        except json.JSONDecodeError as exc:
            checks.append(_check("agents_live", False, str(exc)))

    # --- LLM provider (cloud vs mock) ---
    mock = os.environ.get("LOCAL_MOCK_LLM", "").lower() in ("1", "true", "yes")
    checks.append(
        _check(
            "not_mock_mode",
            not mock,
            "MOCK معطّل — استدعاء حقيقي" if not mock else "LOCAL_MOCK_LLM=1 — وهمي",
        )
    )
    log_p = focus_root / "logs" / "runner.log"
    log_tail = log_p.read_text(encoding="utf-8", errors="replace")[-20000:] if log_p.exists() else ""
    if log_tail:
        if "[OpenRouter]" in log_tail:
            checks.append(_check("llm_openrouter", True, "سجل يحتوي [OpenRouter]"))
        elif "[Gemini]" in log_tail:
            checks.append(_check("llm_gemini", True, "سجل يحتوي [Gemini]"))
        elif "[qwen35custom] MOCK" in log_tail:
            checks.append(_check("llm_real", False, "MOCK في السجل"))
        else:
            checks.append(
                _check("llm_trace", True, "Ollama/FSM في السجل", warn=True)
            )

    # --- Runner log FSM markers (optional — only when started from dashboard) ---
    if log_p.exists():
        tail = log_tail
        has_fsm = "[FSM]" in tail or "teams=" in tail or "[MONITOR]" in tail
        checks.append(
            _check(
                "runner_log_fsm",
                has_fsm,
                "سطر FSM/teams في السجل" if has_fsm else "لا علامة FSM",
                warn=not has_fsm,
            )
        )
    else:
        checks.append(
            _check("runner_log_fsm", True, "لا runner.log (تشغيل مباشر — مقبول)", warn=True)
        )

    # --- Job status coherence ---
    job_p = focus_root / "logs" / "job_status.json"
    has_cycle_exp = len(cycle_rows) >= 1
    if job_p.exists():
        try:
            job = json.loads(job_p.read_text(encoding="utf-8"))
            done = int(job.get("cycles_done") or 0)
            checks.append(
                _check(
                    "job_status_cycles",
                    done >= 1 or has_cycle_exp,
                    f"state={job.get('state')} cycles_done={done}",
                )
            )
        except json.JSONDecodeError as exc:
            checks.append(_check("job_status_cycles", False, str(exc)))
    else:
        checks.append(
            _check(
                "job_status_cycles",
                has_cycle_exp,
                "لا job_status — يُحدَّث من لوحة التحكم",
                warn=has_cycle_exp,
            )
        )

    # --- Team workspaces (if roster) ---
    roster_p = focus_root / "teams" / "roster.md"
    if roster_p.exists():
        try:
            from local.orchestrator.team_manager import teams_as_list, read_roster

            teams = teams_as_list(read_roster(focus_root))
            teams_n = len(teams)
            checks.append(_check("teams_roster", teams_n >= 2, f"فرق={teams_n}"))
            missing_ws = [
                t["id"]
                for t in teams
                if not (focus_root / "teams" / t["id"] / "queue.md").exists()
            ]
            checks.append(
                _check(
                    "team_workspaces",
                    len(missing_ws) == 0,
                    "كل الفرق لها queue" if not missing_ws else f"ناقص: {missing_ws}",
                )
            )
        except Exception as exc:
            checks.append(_check("teams_roster", False, str(exc)))

    failed = [c for c in checks if c["status"] == "fail"]
    warned = [c for c in checks if c["status"] == "warn"]
    passed = [c for c in checks if c["status"] == "ok"]

    exp_row = cycle_rows[-1] if cycle_rows else {}
    summary = {
        "ts": _now(),
        "focus_root": str(focus_root),
        "cycle": cycle,
        "ok": len(failed) == 0,
        "passed": len(passed),
        "failed": len(failed),
        "warnings": len(warned),
        "checks": checks,
        "team_mode": os.environ.get("LOCAL_TEAM_MODE", "1"),
        "llm_provider": os.environ.get("LOCAL_LLM_PROVIDER", "auto"),
        "experiment": {
            "outcome": exp_row.get("outcome"),
            "val_loss": exp_row.get("val_loss"),
            "exp_id": exp_row.get("exp_id"),
        },
    }
    _write_reports(focus_root, summary)
    return summary


def _report_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# تقرير متابعة الدورة {summary.get('cycle', 1)}",
        "",
        f"- **الوقت:** {summary.get('ts')}",
        f"- **النتيجة:** {'✅ ناجح' if summary.get('ok') else '❌ يوجد أخطاء'}",
        f"- **نجح:** {summary.get('passed')} | **فشل:** {summary.get('failed')} | **تحذير:** {summary.get('warnings')}",
    ]
    exp = summary.get("experiment") or {}
    if exp.get("val_loss") is not None:
        lines.append(
            f"- **تجربة الدورة:** outcome={exp.get('outcome')} val_loss={exp.get('val_loss')}"
        )
    lines.extend(["", "## الفحوصات", ""])
    icon = {"ok": "✅", "fail": "❌", "warn": "⚠️"}
    for c in summary.get("checks", []):
        lines.append(
            f"- {icon.get(c['status'], '?')} **{c['name']}** — {c.get('detail', '')}"
        )
    return "\n".join(lines) + "\n"


def _write_reports(focus_root: Path, summary: dict[str, Any]) -> None:
    logs = focus_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    cycle = int(summary.get("cycle", 1))
    per_dir = logs / MONITOR_DIR
    per_dir.mkdir(parents=True, exist_ok=True)

    body = json.dumps(summary, ensure_ascii=False, indent=2)
    md = _report_markdown(summary)

    # Latest (dashboard reads this)
    (logs / REPORT_JSON).write_text(body, encoding="utf-8")
    (logs / REPORT_MD).write_text(md, encoding="utf-8")

    # Per-cycle archive
    tag = f"cycle_{cycle:04d}"
    (per_dir / f"{tag}.json").write_text(body, encoding="utf-8")
    (per_dir / f"{tag}.md").write_text(md, encoding="utf-8")

    # History
    with (logs / HISTORY_JSONL).open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": summary.get("ts"),
                    "cycle": cycle,
                    "ok": summary.get("ok"),
                    "passed": summary.get("passed"),
                    "failed": summary.get("failed"),
                    "experiment": summary.get("experiment"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def load_monitor_report(focus_root: Path) -> dict[str, Any] | None:
    path = Path(focus_root).resolve() / "logs" / REPORT_JSON
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def monitor_already_ok(focus_root: Path, cycle: int = 1) -> bool:
    per = (
        Path(focus_root).resolve()
        / "logs"
        / MONITOR_DIR
        / f"cycle_{int(cycle):04d}.json"
    )
    if per.exists():
        try:
            rep = json.loads(per.read_text(encoding="utf-8"))
            return bool(rep.get("ok"))
        except json.JSONDecodeError:
            pass
    rep = load_monitor_report(focus_root)
    if not rep:
        return False
    return bool(rep.get("ok")) and int(rep.get("cycle", 0)) == cycle


def list_monitor_history(focus_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    path = Path(focus_root).resolve() / "logs" / HISTORY_JSONL
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows[-limit:]


def launch_cycle_monitor(
    focus_root: Path,
    cycle: int,
    *,
    template_dir: Path,
    log_path: Path | None = None,
    wait: bool = True,
    timeout_sec: float = 90.0,
) -> dict[str, Any]:
    """
    Spawn run_monitor.py as a separate process (after each completed cycle).
    """
    import subprocess
    import sys

    template_dir = Path(template_dir).resolve()
    focus_root = Path(focus_root).resolve()

    python = sys.executable
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = template_dir / rel.replace("/", os.sep)
        if candidate.exists():
            python = str(candidate)
            break

    script = template_dir / "local" / "dashboard" / "run_monitor.py"
    cmd = [python, str(script), "--focus-root", str(focus_root), "--cycle", str(cycle)]
    if log_path:
        cmd.extend(["--log-file", str(log_path)])

    print(f"[MONITOR] launching separate check cycle={cycle}", flush=True)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(template_dir),
            env={
                **os.environ,
                "PYTHONPATH": str(template_dir) + os.pathsep + os.environ.get("PYTHONPATH", ""),
                "PYTHONUNBUFFERED": "1",
            },
            capture_output=not wait,
            text=True,
            timeout=timeout_sec if wait else None,
        )
        rep = load_monitor_report(focus_root) or {}
        return {
            "launched": True,
            "exit_code": proc.returncode,
            "ok": bool(rep.get("ok")),
            "passed": rep.get("passed"),
            "failed": rep.get("failed"),
            "report": str(focus_root / "logs" / REPORT_JSON),
        }
    except subprocess.TimeoutExpired:
        return {"launched": True, "ok": False, "error": "انتهت مهلة المتابع"}
    except OSError as exc:
        return {"launched": False, "ok": False, "error": str(exc)}


def launch_first_cycle_monitor(
    focus_root: Path,
    cycle: int,
    *,
    template_dir: Path,
    log_path: Path | None = None,
    wait: bool = True,
    timeout_sec: float = 90.0,
) -> dict[str, Any]:
    """Alias for launch_cycle_monitor."""
    return launch_cycle_monitor(
        focus_root,
        cycle,
        template_dir=template_dir,
        log_path=log_path,
        wait=wait,
        timeout_sec=timeout_sec,
    )
