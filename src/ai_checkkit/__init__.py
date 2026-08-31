"""ai-checkkit — AI-era Python lint bundle."""

try:
    from ._version import version as __version__
except ImportError:
    try:
        from importlib.metadata import version as _v
        __version__ = _v("ai-checkkit")
    except Exception:
        __version__ = "0.1.1.dev0"

__all__ = ["__version__"]
