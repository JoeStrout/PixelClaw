import anthropic

from .context import Context
from .tool import Tool

MODEL = "claude-opus-4-6"


class Agent:
    def __init__(self, workspace: Context, tools: list[Tool]):
        self.workspace = workspace
        self.tools = {t.name: t for t in tools}
        self._client = anthropic.Anthropic()

    def chat(self, user_message: str) -> str:
        """Send a user message, run the agent loop (including tool calls), and return the final text reply."""
        self.workspace.chat_history.append({"role": "user", "content": user_message})

        while True:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=4096,
                tools=[t.to_api_dict() for t in self.tools.values()],
                messages=self.workspace.chat_history,
            )
            self.workspace.chat_history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool = self.tools.get(block.name)
                        if tool:
                            try:
                                result = tool.execute(self.workspace, **block.input)
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": str(result),
                                })
                            except Exception as e:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": f"Error: {e}",
                                    "is_error": True,
                                })
                        else:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Error: unknown tool '{block.name}'",
                                "is_error": True,
                            })
                self.workspace.chat_history.append({"role": "user", "content": tool_results})
