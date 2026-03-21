from pathlib import Path
from typing import Iterable

from agent.state import Requirement


def _field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def export_requirements_snapshot(requirements: Iterable[Requirement], file_path: str = "src/memory/state/requirement.txt") -> None:
    req_list = list(requirements or [])

    lines = ["# Requirements Snapshot", ""]
    if not req_list:
        lines.append("(no requirements)")
    else:
        for req in req_list:
            status = _field(req, "status", "pending")
            status_text = status.value if hasattr(status, "value") else str(status)
            req_id = str(_field(req, "id", ""))
            title = str(_field(req, "title", ""))
            priority = int(_field(req, "priority", 3) or 3)
            description = str(_field(req, "description", ""))
            acceptance_criteria = _field(req, "acceptance_criteria", []) or []
            step_ids = [str(item) for item in (_field(req, "step_ids", []) or [])]

            lines.append(f"- [{status_text}] {req_id}: {title} (P{priority})")
            lines.append(f"  Description: {description}")
            if acceptance_criteria:
                lines.append("  Acceptance Criteria:")
                for i, criterion in enumerate(acceptance_criteria, start=1):
                    lines.append(f"    {i}. {criterion}")
            if step_ids:
                lines.append(f"  Steps: {', '.join(step_ids)}")
            lines.append("")

    output = "\n".join(lines).strip() + "\n"

    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(output, encoding="utf-8")
