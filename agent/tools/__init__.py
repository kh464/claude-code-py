from .runtime import ToolRuntime

__all__ = ["ToolRegistry", "ToolRuntime"]


def __getattr__(name: str):
    if name == "ToolRegistry":
        from .registry import ToolRegistry

        return ToolRegistry
    raise AttributeError(name)
