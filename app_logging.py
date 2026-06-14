"""Shared logging for compliance verification runs."""

import logging
import sys
from datetime import datetime
from io import StringIO

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

_run_buffer = StringIO()
_run_handler = None
_configured = False


class RunLogHandler(logging.Handler):
    """Capture log records for display in the Streamlit UI."""

    def __init__(self, buffer: StringIO):
        super().__init__()
        self.buffer = buffer
        self.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    def emit(self, record):
        try:
            self.buffer.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


def setup_logging(level=logging.INFO):
    global _configured, _run_handler
    if _configured:
        return logging.getLogger("compliance")

    root = logging.getLogger("compliance")
    root.setLevel(level)
    root.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(console)

    _run_handler = RunLogHandler(_run_buffer)
    _run_handler.setLevel(level)
    root.addHandler(_run_handler)

    _configured = True
    return root


def get_logger(name: str = "compliance"):
    setup_logging()
    if name == "compliance":
        return logging.getLogger("compliance")
    return logging.getLogger(f"compliance.{name}")


def start_run_log():
    """Clear the in-memory log buffer at the start of a verification run."""
    global _run_buffer
    _run_buffer = StringIO()
    if _run_handler is not None:
        _run_handler.buffer = _run_buffer
    logger = get_logger()
    logger.info("=" * 60)
    logger.info("Verification run started at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)


def get_run_log_text() -> str:
    return _run_buffer.getvalue()


def get_run_log_lines() -> list[str]:
    text = get_run_log_text().strip()
    return text.split("\n") if text else []
