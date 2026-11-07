"""Debug-gated logging for the BNC."""
_debug_enabled = False


def set_debug(enabled: bool) -> None:
    global _debug_enabled
    _debug_enabled = enabled


def is_debug() -> bool:
    return _debug_enabled


def dlog(fmt: str, *args) -> None:
    if _debug_enabled:
        try:
            print(fmt % args if args else fmt)
        except Exception:
            print(fmt)


def dhook(fmt: str, *args) -> None:
    """Hook-specific debug log."""
    dlog("[Hook] " + fmt, *args)
