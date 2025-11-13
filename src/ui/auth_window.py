"""PyQt5 GUI for entering Kiwoom credentials and fetching REST tokens."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from src.api.kiwoom_client import KiwoomRESTClient
from src.core.exceptions import ConfigurationError, KiwoomAPIError
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
        self.setMinimumWidth(720)
        self.token_ready = False
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
        self.account_input.textChanged.connect(self._update_account_button_state)
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

        summary_group = QtWidgets.QGroupBox("계좌 요약")
        summary_layout = QtWidgets.QVBoxLayout(summary_group)
        self.cash_label = QtWidgets.QLabel("예수금: - / 평가금액: - / 손익: -")
        summary_layout.addWidget(self.cash_label)

        self.holdings_table = QtWidgets.QTableWidget(0, 5)
        self.holdings_table.setHorizontalHeaderLabels(["종목", "수량", "평균단가", "현재가", "평가손익"])
        self.holdings_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        summary_layout.addWidget(self.holdings_table)
        layout.addWidget(summary_group)

        self.log_console = QtWidgets.QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QtGui.QFont("Consolas", 10))
        layout.addWidget(self.log_console)
        self._update_account_button_state()

    def _handle_env_change(self) -> None:
        self.settings.mode = self.env_combo.currentData()
        self._append_log(f"환경이 {self.settings.mode} 로 전환되었습니다.")
        self._ensure_client()

    def handle_get_token(self) -> None:
        app_key = self.app_key_input.text().strip()
        sec_key = self.sec_key_input.text().strip()
        account = self.account_input.text().strip()
        account_digits = self._account_digits()

        if not app_key or not sec_key:
            self._append_log("App Key와 Secret Key는 필수입니다.", error=True)
            return

        if not self._ensure_client():
            return

        assert self.client is not None
        normalized_account = account_digits or account
        self.client.update_credentials(app_sky=app_key, sec_key=sec_key, account_no=normalized_account)
        self._append_log("Kiwoom REST 인증 요청 중...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            token = self.client.authenticate(force=True)
            expiry = self.client.token_expiry.isoformat() if self.client.token_expiry else "알 수 없음"
            self.status_label.setText("토큰 상태: 발급 완료")
            self.token_ready = True
            self._update_account_button_state()
            self._append_log(f"토큰 발급 성공: {token[:6]}*** (만료: {expiry})")
        except Exception as exc:  # pylint: disable=broad-except
            self.status_label.setText("토큰 상태: 실패")
            self.token_ready = False
            self._update_account_button_state()
            self._append_log(f"토큰 발급 실패: {exc}", error=True)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def handle_get_account(self) -> None:
        digits = self._account_digits()
        if len(digits) < 8:
            self._append_log("계좌번호는 최소 8자리 이상 입력해야 합니다.", error=True)
            return
        if self.client is None:
            self._append_log("먼저 토큰을 발급해 주세요.", error=True)
            return

        self.client.settings.credentials.account_no = digits
        self._append_log("계좌 정보 조회 중...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            account_data = self.client.get_account_overview()
            summary = self._parse_account_summary(account_data)
            self._render_account_summary(summary)
            pretty = json.dumps(account_data, indent=2, ensure_ascii=False)
            self._append_log(f"계좌 정보:\n{pretty}")
        except KiwoomAPIError as exc:
            self._append_log(f"계좌 조회 실패: {self._format_api_error(exc)}", error=True)
            self._clear_account_summary()
        except Exception as exc:  # pylint: disable=broad-except
            self._append_log(f"계좌 조회 실패: {exc}", error=True)
            self._clear_account_summary()
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

    def _account_digits(self) -> str:
        return "".join(ch for ch in self.account_input.text() if ch.isdigit())

    def _update_account_button_state(self) -> None:
        digits = self._account_digits()
        enabled = self.client is not None and self.token_ready and len(digits) >= 8
        self.account_button.setEnabled(enabled)

    def _format_api_error(self, exc: KiwoomAPIError) -> str:
        if exc.payload:
            try:
                payload_json = json.loads(exc.payload)
                message = payload_json.get("message") or payload_json.get("msg")
                error = payload_json.get("error")
                if message:
                    return f"{exc.status_code or ''} {message}".strip()
                if error:
                    return f"{exc.status_code or ''} {error}".strip()
            except json.JSONDecodeError:
                pass
        return str(exc)

    @staticmethod
    def _parse_account_summary(account_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Kiwoom account response into a simple structure."""
        holdings = account_data.get("output1") or account_data.get("output") or account_data.get("stk_acnt_evlt_prst") or []
        summary_items = account_data.get("output2") or account_data.get("summary")
        if not summary_items and account_data.get("raw_pages"):
            first_page = account_data["raw_pages"][0]
            summary_items = first_page.get("output2") or first_page.get("summary")
        summary_info = summary_items[0] if isinstance(summary_items, list) and summary_items else summary_items or {}

        def to_int(value: Any) -> int:
            try:
                return int(str(value).replace(",", ""))
            except (ValueError, TypeError):
                return 0

        raw_pages = account_data.get("raw_pages") or []
        first_page = raw_pages[0] if raw_pages else {}

        def extract_numeric(*keys: str) -> int:
            for key in keys:
                if summary_info and key in summary_info:
                    return to_int(summary_info[key])
                if key in account_data:
                    return to_int(account_data[key])
                if raw_pages:
                    for page in raw_pages:
                        if key in page:
                            return to_int(page[key])
            return 0

        parsed_holdings = []
        for item in holdings:
            parsed_holdings.append(
                {
                    "symbol": item.get("pdno") or item.get("ISU_SRT_CD") or item.get("symbol", "-"),
                    "name": item.get("prdt_name") or item.get("ISU_ABBRV") or "",
                    "quantity": to_int(item.get("hldg_qty") or item.get("ORD_QTY") or item.get("qty")),
                    "avg_price": float(item.get("pchs_avg_pric") or item.get("avg_prc") or 0),
                    "current_price": float(item.get("prpr") or item.get("now_prc") or 0),
                    "pl": to_int(item.get("evlu_pfls_smtl_amt") or item.get("unrealized") or 0),
                }
            )

        cash = extract_numeric(
            "dnca_tot_amt",
            "cash",
            "dnca_tot",
            "prsm_dpst_aset_amt",
            "entr",
            "d2_entra",
            "prsm_dpst_aset_amt",
        )
        if cash == 0 and first_page:
            cash = to_int(first_page.get("prsm_dpst_aset_amt") or first_page.get("entr") or first_page.get("d2_entra"))

        evaluation = extract_numeric("scts_evlu_amt", "evaluation", "aset_evlt_amt", "tot_est_amt", "aset_evlt_amt")
        if evaluation == 0 and first_page:
            evaluation = to_int(first_page.get("aset_evlt_amt") or first_page.get("tot_est_amt"))

        pl_value = extract_numeric("evlu_pfls_smtl_amt", "profit", "lspft_amt", "tdy_lspft_amt", "lspft")
        if pl_value == 0 and first_page:
            pl_value = to_int(first_page.get("lspft_amt") or first_page.get("tdy_lspft"))

        return {
            "cash": cash,
            "evaluation": evaluation,
            "pl": pl_value,
            "holdings": parsed_holdings,
        }

    def _render_account_summary(self, summary: Dict[str, Any]) -> None:
        cash_fmt = f"{summary['cash']:,}" if summary["cash"] else "-"
        eval_fmt = f"{summary['evaluation']:,}" if summary["evaluation"] else "-"
        pl_fmt = f"{summary['pl']:,}" if summary["pl"] else "-"
        self.cash_label.setText(f"예수금: {cash_fmt} / 평가금액: {eval_fmt} / 손익: {pl_fmt}")

        holdings = summary["holdings"]
        self.holdings_table.setRowCount(len(holdings))
        for row, item in enumerate(holdings):
            display_symbol = f"{item['symbol']} ({item['name']})" if item["name"] else item["symbol"]
            values = [
                display_symbol,
                f"{item['quantity']:,}",
                f"{item['avg_price']:.2f}",
                f"{item['current_price']:.2f}",
                f"{item['pl']:,}",
            ]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                cell.setFlags(cell.flags() ^ QtCore.Qt.ItemIsEditable)
                self.holdings_table.setItem(row, col, cell)
        if not holdings:
            self.holdings_table.setRowCount(0)

    def _clear_account_summary(self) -> None:
        self.cash_label.setText("예수금: - / 평가금액: - / 손익: -")
        self.holdings_table.setRowCount(0)

    def shutdown(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("Failed to close Kiwoom client: %s", exc)
            finally:
                self.client = None

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        self.shutdown()
        super().closeEvent(event)
