"""gen-sim: merchant asset screen for small generating plants."""
import sys as _sys

# Status lines use emoji. On Windows consoles/pipes (cp1252) printing them raises
# UnicodeEncodeError mid-fetch; degrade to '?' instead of crashing.
for _stream in (_sys.stdout, _sys.stderr):
    _enc = (getattr(_stream, "encoding", "") or "").lower().replace("-", "")
    if _stream is not None and hasattr(_stream, "reconfigure") and _enc != "utf8":
        try:
            _stream.reconfigure(errors="replace")
        except Exception:
            pass
