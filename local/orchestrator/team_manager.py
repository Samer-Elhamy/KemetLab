"""Local team roster — form, split, merge (Phase 2/4 from AutoScientists plan)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROSTER_PATH = "teams/roster.md"
EVENTS_PATH = "logs/team_events.jsonl"

# Default hypotheses for smoke / optimization (4 parallel teams = 12 agent roles)
DEFAULT_TEAMS: list[dict[str, Any]] = [
    {
        "id": "lr_team",
        "name_ar": "فريق معدل التعلم",
        "hypothesis": "خفض lr وضبط decay يقلّل val_loss",
        "prediction": "تجارب lr الموزونة تحقق KEEP",
        "falsification": "3 دورات متتالية DISCARD بنفس الاتجاه",
    },
    {
        "id": "width_team",
        "name_ar": "فريق العرض والتعقيد",
        "hypothesis": "زيادة hidden_dim و colsample تحسّن التعميم",
        "prediction": "سعة تمثيلية أكبر → KEEP",
        "falsification": "رفض مراجعات متكرر لاقتراحات العرض",
    },
    {
        "id": "depth_team",
        "name_ar": "فريق العمق والشجرة",
        "hypothesis": "زيادة عمق الشجرة والتفاعلات المركبة تقلّل الفقد",
        "prediction": "max_depth و steps مدروسة → KEEP",
        "falsification": "ركود val_loss لـ 3 دورات",
    },
    {
        "id": "ensemble_team",
        "name_ar": "فريق الدمج والهندسة",
        "hypothesis": "دمج النماذج المتنوعة (CatBoost, XGB, LGBM) يرفع الـ AUC",
        "prediction": "Ensemble blending يحقق طفرة في مقياس التقييم → KEEP",
        "falsification": "عدم تفوق الـ blend على أفضل نموذج مفرد",
    },
]


def _roster_file(focus_root: Path) -> Path:
    return Path(focus_root).resolve() / ROSTER_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    return fm, body


def read_roster(focus_root: Path) -> dict[str, Any]:
    path = _roster_file(focus_root)
    if not path.exists():
        return {"teams": {}}
    fm, _body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    return fm if isinstance(fm, dict) else {"teams": {}}


def write_roster(focus_root: Path, teams: dict[str, Any], *, note: str = "") -> None:
    focus_root = Path(focus_root).resolve()
    path = _roster_file(focus_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = note or "# Team roster (local)\n"
    content = "---\n" + yaml.dump({"teams": teams}, allow_unicode=True, sort_keys=False) + "---\n\n" + body
    path.write_text(content, encoding="utf-8")


def _log_team_event(focus_root: Path, event: dict[str, Any]) -> None:
    path = Path(focus_root).resolve() / EVENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**event, "ts": _now()}, ensure_ascii=False) + "\n")


def ensure_team_workspaces(focus_root: Path, team_id: str, hypothesis: str) -> Path:
    """Per-team queue/strategy like main AutoScientists team workspace."""
    base = Path(focus_root).resolve() / "teams" / team_id
    base.mkdir(parents=True, exist_ok=True)
    queue = base / "queue.md"
    if not queue.exists():
        queue.write_text(
            f"---\npending: []\nclaims: {{}}\n---\n\n# Queue — {team_id}\n",
            encoding="utf-8",
        )
    strat = base / "strategy.md"
    if not strat.exists():
        strat.write_text(
            f"---\nhypothesis: {json.dumps(hypothesis, ensure_ascii=False)}\n---\n\n# Strategy\n",
            encoding="utf-8",
        )
    return base


def teams_as_list(roster: dict[str, Any]) -> list[dict[str, Any]]:
    raw = roster.get("teams") or {}
    out = []
    for tid, meta in raw.items():
        if not isinstance(meta, dict):
            continue
        out.append(
            {
                "id": tid,
                "name_ar": meta.get("name_ar", tid),
                "hypothesis": meta.get("hypothesis", ""),
                "prediction": meta.get("prediction", ""),
                "falsification": meta.get("falsification", ""),
                "members": meta.get("members", ["analyst", "reviewer", "gpu"]),
                "formed_at": meta.get("formed_at"),
            }
        )
    return out


def seed_default_teams(focus_root: Path) -> dict[str, Any]:
    teams: dict[str, Any] = {}
    for t in DEFAULT_TEAMS:
        tid = t["id"]
        teams[tid] = {
            "name_ar": t["name_ar"],
            "hypothesis": t["hypothesis"],
            "prediction": t["prediction"],
            "falsification": t["falsification"],
            "members": ["analyst", "reviewer", "gpu"],
            "formed_at": _now(),
            "workspace": f"teams/{tid}",
        }
        ensure_team_workspaces(focus_root, tid, t["hypothesis"])
    write_roster(focus_root, teams, note="# فرق محلية — تشكيل افتراضي (3 فرق متوازية)\n")
    _log_team_event(focus_root, {"action": "seed", "teams": list(teams.keys())})
    return {"teams": teams}


def load_or_seed_roster(focus_root: Path) -> list[dict[str, Any]]:
    roster = read_roster(focus_root)
    teams = teams_as_list(roster)
    if len(teams) < 2:
        roster = seed_default_teams(focus_root)
        teams = teams_as_list(roster)
    for t in teams:
        ensure_team_workspaces(focus_root, t["id"], t.get("hypothesis", ""))
    return teams


def _read_recent_outcomes(focus_root: Path, n: int = 5) -> list[str]:
    path = Path(focus_root).resolve() / "logs" / "experiments.jsonl"
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
    return [str(r.get("outcome", "")).upper() for r in rows[-n:]]


def should_reform_teams(focus_root: Path, cycle: int) -> tuple[bool, str]:
    """Discuss/reform like Phase 2 + team reform in ROLE-ANALYST."""
    if cycle == 1:
        return True, "تشكيل أولي للفرق"
    if cycle % 4 == 0:
        return True, "إعادة تشكيل دورية"
    outcomes = _read_recent_outcomes(focus_root, 5)
    if len(outcomes) >= 3 and all(o == "DISCARD" for o in outcomes[-3:]):
        return True, "ركود — 3 تجارب DISCARD متتالية"
    return False, ""


def reform_teams(focus_root: Path, cycle: int, reason: str) -> list[dict[str, Any]]:
    """
    Split / merge / rotate hypotheses (local heuristic; no AnonAPI).
    Returns new team list.
    """
    focus_root = Path(focus_root).resolve()
    old = load_or_seed_roster(focus_root)
    outcomes = _read_recent_outcomes(focus_root, 3)

    new_teams: dict[str, Any] = {}
    if "ركود" in reason or (outcomes and all(o == "DISCARD" for o in outcomes)):
        # Split: replace one team with two narrower hypotheses
        for i, t in enumerate(DEFAULT_TEAMS):
            suffix = f"_c{cycle}" if i == 0 else ""
            tid = t["id"] + suffix if suffix else t["id"]
            if suffix and tid in new_teams:
                tid = f"{t['id']}_alt"
            new_teams[tid] = {
                "name_ar": t["name_ar"] + (f" (دورة {cycle})" if suffix else ""),
                "hypothesis": t["hypothesis"] + f" — إعادة تشكيل: {reason[:60]}",
                "prediction": t["prediction"],
                "falsification": t["falsification"],
                "members": ["analyst", "reviewer", "gpu"],
                "formed_at": _now(),
                "workspace": f"teams/{tid}",
                "reformed_from": t["id"],
            }
            ensure_team_workspaces(focus_root, tid, new_teams[tid]["hypothesis"])
    else:
        # Rotate / refresh hypotheses while keeping 3 teams
        pool = old[:3] if len(old) >= 3 else DEFAULT_TEAMS
        for i, t in enumerate(pool):
            base = DEFAULT_TEAMS[i % len(DEFAULT_TEAMS)]
            tid = (t.get("id") if isinstance(t, dict) else None) or base["id"]
            if not re.match(r"^[a-z0-9_]+$", tid):
                tid = base["id"]
            new_teams[tid] = {
                "name_ar": (t.get("name_ar") if isinstance(t, dict) else None) or base["name_ar"],
                "hypothesis": base["hypothesis"],
                "prediction": base["prediction"],
                "falsification": base["falsification"],
                "members": ["analyst", "reviewer", "gpu"],
                "formed_at": _now(),
                "workspace": f"teams/{tid}",
            }
            ensure_team_workspaces(focus_root, tid, new_teams[tid]["hypothesis"])

    write_roster(focus_root, new_teams, note=f"# إعادة تشكيل — دورة {cycle}\n\n{reason}\n")
    _log_team_event(
        focus_root,
        {
            "action": "reform",
            "cycle": cycle,
            "reason": reason,
            "old": [t["id"] for t in old],
            "new": list(new_teams.keys()),
        },
    )
    return teams_as_list({"teams": new_teams})


def team_agent_id(team_id: str, role: str) -> str:
    return f"team:{team_id}:{role}"


def build_team_agent_specs(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dashboard agents: 3 roles × N teams."""
    icons = {"analyst": "🧪", "reviewer": "🔍", "gpu": "⚙️"}
    names = {"analyst": "محلل", "reviewer": "مراجع", "gpu": "تدريب GPU"}
    specs = []
    for team in teams:
        tid = team["id"]
        tname = team.get("name_ar", tid)
        hyp = (team.get("hypothesis") or "")[:80]
        for role in ("analyst", "reviewer", "gpu"):
            specs.append(
                {
                    "id": team_agent_id(tid, role),
                    "team_id": tid,
                    "team_name_ar": tname,
                    "name_ar": f"{tname} — {names[role]}",
                    "name_en": f"{tid}/{role}",
                    "icon": icons[role],
                    "model": "qwen35custom" if role != "gpu" else "train.py",
                    "role": hyp or role,
                }
            )
    return specs
