import json
import shutil
from pathlib import Path

import litellm
litellm.suppress_debug_info = True

from .context import Context
from .tool import Tool

DEFAULT_MODEL = "gpt-5.4-nano"
MAX_HISTORY_MESSAGES = 40
DEBUG_DIR = Path("debug_output")


class Agent:
    def __init__(self, context: Context, tools: list[Tool],
                 model: str = DEFAULT_MODEL, api_key: str | None = None,
                 instructions: str | None = None):
        self.context = context
        self.tools = {t.name: t for t in tools}
        self.model = model
        self.api_key = api_key
        self.instructions = instructions
        self._call_count = 0
        if DEBUG_DIR.exists():
            shutil.rmtree(DEBUG_DIR)
        DEBUG_DIR.mkdir()

    def _build_messages(self) -> list[dict]:
        messages = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        ctx = self.context.render_context()
        if ctx:
            messages.append({"role": "system", "content": ctx})
        messages.extend(self.context.chat_history)
        return messages

    def _trim_history(self) -> None:
        """Drop oldest user-turn groups from chat_history when it grows too long."""
        h = self.context.chat_history
        while len(h) > MAX_HISTORY_MESSAGES:
            if not h or h[0]["role"] != "user":
                break
            h.pop(0)
            while h and h[0]["role"] != "user":
                h.pop(0)

    def _write_debug(self, tag: str, data: object) -> None:
        DEBUG_DIR.mkdir(exist_ok=True)
        name = f"{self._call_count:04d}_{tag}.json"
        (DEBUG_DIR / name).write_text(json.dumps(data, indent=2, default=str))

    def chat(self, user_message: str) -> str:
        """Send a user message, run the agentic loop (with tool calls), return final text."""
        self.context.chat_history.append({"role": "user", "content": user_message})
        tool_defs = [t.to_api_dict() for t in self.tools.values()]

        while True:
            self._trim_history()
            self._call_count += 1

            kwargs: dict = dict(
                model=self.model,
                messages=self._build_messages(),
                max_tokens=4096,
            )
            if tool_defs:
                kwargs["tools"] = tool_defs
            if self.api_key:
                kwargs["api_key"] = self.api_key

            self._write_debug("request", {k: v for k, v in kwargs.items() if k != "api_key"})

            response = litellm.completion(**kwargs)

            try:
                self._write_debug("response", response.model_dump())
            except Exception:
                self._write_debug("response", {"raw": str(response)})

            msg = response.choices[0].message
            finish = response.choices[0].finish_reason

            assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            self.context.chat_history.append(assistant_entry)

            if msg.content:
                print(f"[agent] {msg.content}")

            if finish == "stop" or not msg.tool_calls:
                return msg.content or ""

            self.context.agent_reason = msg.content or ""
            tool_results = []
            for tc in msg.tool_calls:
                tool = self.tools.get(tc.function.name)
                try:
                    args = json.loads(tc.function.arguments)
                    if tool:
                        print(f"[tool] {tc.function.name}({tc.function.arguments})")
                        result = tool.execute(self.context, **args)
                    else:
                        raise ValueError(f"unknown tool '{tc.function.name}'")
                except Exception as e:
                    result = f"Error: {e}"
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })
            self.context.chat_history.extend(tool_results)
