"""Tela de carregamento: uma acao em andamento, sem decoração concorrente."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.config import NETBOX_URL
from app.loading import Spinner
from app.paths import resource_path
from app.ui.tokens import GAP_LG, GAP_MD, GAP_SM


class LoadingPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LoadingPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)

        self.logo = QLabel()
        self.logo.setFixedSize(46, 46)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(resource_path("app", "assets", "app_icon.png")))
        if not pixmap.isNull():
            self.logo.setPixmap(
                pixmap.scaled(
                    46,
                    46,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(GAP_LG)

        self.spinner = Spinner(self, diameter=64, stroke=4)
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(24)

        self.title = QLabel("Conectando ao NetBox")
        self.title.setObjectName("LoadingTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.server = QLabel(NETBOX_URL)
        self.server.setObjectName("LoadingServer")
        self.server.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.server)

        layout.addSpacing(GAP_MD)
        self.caption = QLabel("Autenticando e descobrindo o ambiente…")
        self.caption.setProperty("faint", "true")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.caption)

        layout.addSpacing(GAP_SM)
        self.hint = QLabel("")
        self.hint.setObjectName("LoadingHint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)

        layout.addStretch(1)

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)

    def set_stage(self, text: str) -> None:
        """Diz o que esta sendo lido (sites, permissoes...), em vez de so girar."""
        self.caption.setText(text)

    def reset(self) -> None:
        self.hint.setText("")
        self.title.setText("Conectando ao NetBox")
        self.caption.setText("Autenticando e descobrindo o ambiente…")

    def apply_theme(self, palette) -> None:
        self.spinner.update()
