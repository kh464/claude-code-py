class AgentError(Exception):
    """Base exception for the Python tooling agent."""


class InputValidationError(AgentError, ValueError):
    """Tool input failed schema or custom validation."""


class PermissionDeniedError(AgentError, PermissionError):
    """Permission engine denied the tool invocation."""


class ToolExecutionError(AgentError):
    """Tool invocation failed while running tool logic."""


class ToolInterruptedError(AgentError):
    """Tool invocation was interrupted."""


class MCPError(AgentError):
    """MCP transport or invocation failed."""
