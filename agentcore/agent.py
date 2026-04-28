import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import litellm
litellm.suppress_debug_info = True

from .context import Context
from .tool import Tool
from . import log

DEFAULT_MODEL = "gpt-5.4-nano"
MAX_HISTORY_MESSAGES = 40
DEBUG_DIR = Path("debug_output")


def _is_vision_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("image", "vision", "multimodal", "unsupported content type"))


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
        self._use_vision = True
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

        if self._use_vision:
            thumbnail = self.context.render_thumbnail()
            if thumbnail:
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]["role"] == "user":
                        messages[i] = {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": messages[i]["content"]},
                                {"type": "image_url", "image_url": {
                                    "url": f"data:image/png;base64,{thumbnail}",
                                    "detail": "low",
                                }},
                            ],
                        }
                        break

        return messages

    def _call_llm(self, **kwargs) -> object:
        try:
            return litellm.completion(**kwargs)
        except Exception as e:
            if self._use_vision and _is_vision_error(e):
                print("[agent] Vision not supported by this model; disabling.", flush=True)
                self._use_vision = False
                kwargs["messages"] = self._build_messages()
                return litellm.completion(**kwargs)
            raise

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
        log.userMsg(user_message)
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

            ctx_chars = len(json.dumps(kwargs["messages"], default=str))
            print(f"[llm] {datetime.now().strftime('%H:%M:%S')}  →  "
                  f"{len(kwargs['messages'])} messages, {ctx_chars:,} chars", flush=True)
            _t0 = time.monotonic()

            response = self._call_llm(**kwargs)

            elapsed = time.monotonic() - _t0
            usage = getattr(response, "usage", None)
            if usage:
                print(f"[llm] {datetime.now().strftime('%H:%M:%S')}  ←  "
                      f"{usage.prompt_tokens:,} prompt + {usage.completion_tokens:,} completion tokens  "
                      f"({elapsed:.1f}s)", flush=True)
            else:
                print(f"[llm] {datetime.now().strftime('%H:%M:%S')}  ←  "
                      f"response received  ({elapsed:.1f}s)", flush=True)

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
                log.agentMsg(msg.content)

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
                    log.error(str(e))
                log.toolUse(tc.function.name, tc.function.arguments, str(result))
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })
            self.context.chat_history.extend(tool_results)
