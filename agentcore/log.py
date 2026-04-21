"""Compact Markdown transcript logger. One log file per run, in logs/."""
from datetime import datetime
from pathlib import Path

_log_file: Path | None = None


def _ensure_open() -> Path:
    global _log_file
    if _log_file is None:
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _log_file = logs_dir / f"{stamp}.md"
        _log_file.write_text(f"# Session {stamp}\n\n")
    return _log_file


def _append(text: str) -> None:
    _ensure_open().open("a").write(text + "\n")


def userMsg(text: str) -> None:
    _append(f"**User:** {text}\n")


def agentMsg(text: str) -> None:
    _append(f"**Agent:** {text}\n")


def toolUse(name: str, args: str, result: str) -> None:
    _append(f"- **Tool `{name}`** `{args}` → `{result}`\n")


def error(text: str) -> None:
    _append(f"> **Error:** {text}\n")
