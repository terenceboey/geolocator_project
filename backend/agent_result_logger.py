import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_RESULT_DIR = PROJECT_ROOT / "agent_result"


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "agent"


class AgentResultLogger:
    def __init__(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{timestamp}_{uuid4().hex[:8]}"
        self.run_dir = AGENT_RESULT_DIR / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def write(self, agent_name: str, payload: dict) -> None:
        path = self.run_dir / f"{_safe_name(agent_name)}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def relative_run_dir(self) -> str:
        return str(Path("agent_result") / self.run_id)
