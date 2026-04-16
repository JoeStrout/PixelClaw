# Backward-compatibility shim — new code should import from agentcore.context directly.
from .context import Context as Workspace  # noqa: F401
