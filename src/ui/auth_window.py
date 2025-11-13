"""PyQt5 GUI for entering Kiwoom credentials and fetching REST tokens."""

from __future__ import annotations

import json
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from src.api.kiwoom_client import KiwoomRESTClient
from src.core.exceptions import ConfigurationError
from src.core.logging_config import get_logger
from src.core.settings import AppSettings, get_settings
from src.services.notifier import ConsoleNotifier


class AuthWindow(QtWidgets.QWidget):
    """Minimal window to collect credentials and call Kiwoom REST APIs."""

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings or get_settings()
        self.logger = get_logger("ui.auth")
        self.notifier = ConsoleNotifier(logger=self.logger)
        self.client: Optional[KiwoomRESTClient] = None

        self.setWindowTitle("Kiwoom REST 인증")
        self.setMinimumWidth(480)
        self._build_ui()
        self._ensure_client()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()

        self.app_key_input = QtWidgets.QLineEdit()
        self.app_key_input.setPlaceholderText("App Key (app_sky)")
        form.addRow("App Key", self.app_key_input)

        self.sec_key_input = QtWidgets.QLineEdit()
        self.sec_key_input.setPlaceholderText("Secret Key (sec_key)")
        self.sec_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("Secret Key", self.sec_key_input)

        self.account_input = QtWidgets.QLineEdit()
        self.account_input.setPlaceholderText("계좌번호 (예: 12345678-01)")
        form.addRow("계좌번호", self.account_input)

        self.env_combo = QtWidgets.QComboBox()
        self.env_combo.addItem("모의투자 (Paper)", userData="paper")
        self.env_combo.addItem("실전투자 (Live)", userData="live")
        self.env_combo.currentIndexChanged.connect(self._handle_env_change)
        default_index = 0 if self.settings.mode != "live" else 1
        self.env_combo.setCurrentIndex(default_index)
        form.addRow("환경", self.env_combo)

        layout.addLayout(form)

        button_row = QtWidgets.QHBoxLayout()
        self.token_button = QtWidgets.QPushButton("접근 토큰 발급")
        self.token_button.clicked.connect(self.handle_get_token)
        button_row.addWidget(self.token_button)

        self.account_button = QtWidgets.QPushButton("계좌 정보 조회")
        self.account_button.clicked.connect(self.handle_get_account)
        self.account_button.setEnabled(False)
        button_row.addWidget(self.account_button)

        layout.addLayout(button_row)

        self.status_label = QtWidgets.QLabel("토큰 상태: 미발급")
        layout.addWidget(self.status_label)

        self.log_console = QtWidgets.QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QtGui.QFont("Consolas", 10))
        layout.addWidget(self.log_console)

    def _handle_env_change(self) -> None:
        self.settings.mode = self.env_combo.currentData()
        self._append_log(f"환경이 {self.settings.mode} 로 전환되었습니다.")
        self._ensure_client()

    def handle_get_token(self) -> None:
        app_key = self.app_key_input.text().strip()
        sec_key = self.sec_key_input.text().strip()
        account = self.account_input.text().strip()

        if not app_key or not sec_key:
            self._append_log("App Key와 Secret Key는 필수입니다.", error=True)
            return

        if not self._ensure_client():
            return

        assert self.client is not None
        self.client.update_credentials(app_sky=app_key, sec_key=sec_key, account_no=account)
        self._append_log("Kiwoom REST 인증 요청 중...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            token = self.client.authenticate(force=True)
            expiry = self.client.token_expiry.isoformat() if self.client.token_expiry else "알 수 없음"
            self.status_label.setText("토큰 상태: 발급 완료")
            self.account_button.setEnabled(True)
            self._append_log(f"토큰 발급 성공: {token[:6]}*** (만료: {expiry})")
        except Exception as exc:  # pylint: disable=broad-except
            self.status_label.setText("토큰 상태: 실패")
            self.account_button.setEnabled(False)
            self._append_log(f"토큰 발급 실패: {exc}", error=True)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def handle_get_account(self) -> None:
        self._append_log("계좌 정보 조회 중...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            account_data = self.client.get_account_overview()
            pretty = json.dumps(account_data, indent=2, ensure_ascii=False)
            self._append_log(f"계좌 정보:\n{pretty}")
        except Exception as exc:  # pylint: disable=broad-except
            self._append_log(f"계좌 조회 실패: {exc}", error=True)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _append_log(self, message: str, *, error: bool = False) -> None:
        color = "red" if error else "black"
        self.log_console.appendHtml(f'<span style="color:{color}">{message}</span>')
        if error:
            self.logger.error(message)
        else:
            self.logger.info(message)

    def _ensure_client(self) -> bool:
        """Ensure Kiwoom REST client exists so GUI can continue even if config is missing."""
        try:
            self.client = KiwoomRESTClient(settings=self.settings, logger=self.logger, notifier=self.notifier)
            return True
        except ConfigurationError as exc:
            self.client = None
            self._append_log(f"클라이언트 초기화 실패: {exc}", error=True)
            return False
