"""PyQt5 entrypoint to drive Kiwoom REST authentication (Phase 0)."""

from __future__ import annotations

import sys

from PyQt5 import QtWidgets

from src.core.logging_config import configure_logging
from src.ui.auth_window import AuthWindow


def bootstrap() -> None:
    """Initialize logging and start the GUI event loop."""
    configure_logging()
    app = QtWidgets.QApplication(sys.argv)
    window = AuthWindow()
    window.show()
    app.aboutToQuit.connect(window.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    bootstrap()
