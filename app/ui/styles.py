"""Folha de estilos unica, gerada a partir dos tokens.

Nao existe `setStyleSheet` espalhado pelas telas: todo o visual vem daqui. Os
componentes escolhem um `objectName` (ou uma propriedade dinamica, como
`kind`/`state`) e o estilo correspondente ja existe.

Por que `Template` e nao f-string: a folha tem centenas de chaves `{}` do proprio
QSS, e uma f-string exigiria duplicar todas. Com `$token`, um token desconhecido
falha na hora com KeyError em vez de virar um `$` perdido no CSS.
"""

from __future__ import annotations

from string import Template

from app.ui.tokens import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_DISPLAY,
    FONT_H1,
    FONT_H2,
    FONT_H3,
    FONT_SMALL,
    RADIUS,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    SIDEBAR_WIDTH,
    Palette,
)

_QSS = Template(
    """
* {
    font-family: $UI_FONT;
}
QWidget {
    color: $text;
    font-size: ${font_body}px;
}
QMainWindow, QDialog, QStackedWidget, QWidget#AppRoot, QWidget#PageArea {
    background: $bg;
}
QLabel {
    background: transparent;
    color: $text;
}
QLabel[muted="true"] {
    color: $text_muted;
}
QLabel[faint="true"] {
    color: $text_faint;
}

/* ------------------------------------------------------------- sidebar */
QFrame#Sidebar {
    background: $bg_elevated;
    border: none;
    border-right: 1px solid $border;
}
QLabel#BrandName {
    color: $text;
    font-size: ${font_h3}px;
    font-weight: 700;
}
QLabel#BrandVersion {
    color: $text_faint;
    font-size: ${font_caption}px;
    font-weight: 600;
}
QLabel#NavSection {
    color: $text_faint;
    font-size: 10px;
    font-weight: 700;
    padding: 0 4px;
}
QPushButton#NavItem {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: ${radius}px;
    color: $text_muted;
    font-size: ${font_body}px;
    font-weight: 600;
    padding: 9px 12px;
    text-align: left;
    outline: none;
}
QPushButton#NavItem:hover {
    background: $surface_hi;
    color: $text;
}
QPushButton#NavItem:checked {
    background: $accent_soft;
    border-left: 3px solid $accent;
    color: $accent;
    padding-left: 9px;
}
QPushButton#NavItem:focus {
    border-left: 3px solid $accent_border;
}
QLabel#ConnectionDot {
    background: $text_faint;
    border-radius: 4px;
}
QLabel#ConnectionDot[connected="true"] {
    background: $success;
}
QFrame#ConnectionCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
}
QLabel#ConnectionTitle {
    color: $text;
    font-size: ${font_small}px;
    font-weight: 700;
}
QLabel#ConnectionText {
    color: $text_muted;
    font-size: ${font_caption}px;
}

/* -------------------------------------------------------------- header */
QFrame#AppHeader {
    background: $bg;
    border: none;
    border-bottom: 1px solid $border;
}
QLabel#PageTitle {
    color: $text;
    font-size: ${font_h1}px;
    font-weight: 700;
}
QLabel#PageSubtitle {
    color: $text_muted;
    font-size: ${font_small}px;
}
QLabel#Breadcrumb {
    color: $text_faint;
    font-size: ${font_caption}px;
    font-weight: 600;
}
QLabel#ConnectionBadge {
    background: $surface;
    border: 1px solid $border;
    border-radius: 999px;
    color: $text_muted;
    font-size: ${font_caption}px;
    font-weight: 600;
    padding: 5px 11px;
}
QLabel#ConnectionBadge[connected="true"] {
    background: $success_soft;
    border-color: $success;
    color: $success;
}
QLabel#ConnectionBadge[tls="false"] {
    background: $warning_soft;
    border-color: $warning;
    color: $warning;
}
QPushButton#Avatar {
    background: $accent_soft;
    border: 1px solid $accent_border;
    border-radius: 16px;
    color: $accent;
    font-size: ${font_caption}px;
    font-weight: 700;
    padding: 0;
}

/* --------------------------------------------------------------- cards */
QFrame#DropArea {
    background: $surface_alt;
    border: 1px dashed $border_strong;
    border-radius: ${radius_lg}px;
}
QFrame#DropArea:hover {
    background: $surface;
    border-color: $accent;
}
QFrame#Card {
    background: $surface;
    border: 1px solid $border;
    border-radius: ${radius_lg}px;
}
QFrame#Card[tone="flat"] {
    background: $surface_alt;
}
QFrame#Card[tone="accent"] {
    background: $accent_soft;
    border-color: $accent_border;
}
QLabel#CardTitle {
    color: $text;
    font-size: ${font_h3}px;
    font-weight: 700;
}
QLabel#CardSubtitle {
    color: $text_muted;
    font-size: ${font_small}px;
}
QLabel#FieldLabel {
    color: $text_muted;
    font-size: ${font_caption}px;
    font-weight: 700;
}
QLabel#Mono {
    color: $text_muted;
    font-family: "JetBrains Mono", "Cascadia Mono", monospace;
    font-size: ${font_caption}px;
}
QFrame#Divider {
    background: $border;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QFrame#StatTile {
    background: $surface;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
}
QLabel#StatLabel {
    color: $text_muted;
    font-size: ${font_caption}px;
    font-weight: 700;
}
QLabel#StatValue {
    color: $text;
    font-size: 24px;
    font-weight: 700;
}
QLabel#StatHint {
    color: $text_faint;
    font-size: ${font_caption}px;
}
QLabel#EmptyTitle {
    color: $text;
    font-size: ${font_h3}px;
    font-weight: 700;
}
QLabel#EmptyText {
    color: $text_muted;
    font-size: ${font_small}px;
}

/* -------------------------------------------------------------- botoes */
QPushButton {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: ${radius}px;
    color: $text;
    font-size: ${font_body}px;
    font-weight: 600;
    padding: 8px 14px;
    outline: none;
}
QPushButton:hover {
    background: $surface_hi;
    border-color: $accent_border;
}
QPushButton:pressed {
    background: $surface_alt;
}
QPushButton:disabled {
    background: $surface_alt;
    border-color: $border;
    color: $disabled_text;
}
QPushButton:focus {
    border-color: $accent;
}
QPushButton#primaryButton {
    background: $accent;
    border: 1px solid $accent;
    color: $on_accent;
    font-weight: 700;
}
QPushButton#primaryButton:hover {
    background: $accent_hover;
    border-color: $accent_hover;
}
QPushButton#primaryButton:pressed {
    background: $accent_pressed;
    border-color: $accent_pressed;
}
QPushButton#primaryButton:focus {
    border: 2px solid $text;
    padding: 7px 13px;
}
QPushButton#primaryButton:disabled {
    background: $surface_hi;
    border-color: $border;
    color: $disabled_text;
}
QPushButton#dangerButton {
    background: transparent;
    border: 1px solid $danger;
    color: $danger;
}
QPushButton#dangerButton:hover {
    background: $danger_soft;
}
QPushButton#dangerButton:disabled {
    background: transparent;
    border-color: $border;
    color: $disabled_text;
}
QPushButton#ghostButton {
    background: transparent;
    border: 1px solid transparent;
    color: $text_muted;
    padding: 6px 10px;
}
QPushButton#ghostButton:hover {
    background: $surface_hi;
    color: $text;
}
QPushButton#ghostButton:disabled {
    background: transparent;
    color: $disabled_text;
}
QPushButton#linkButton {
    background: transparent;
    border: none;
    color: $accent;
    font-weight: 600;
    padding: 2px 0;
    text-align: left;
}
QPushButton#linkButton:hover {
    color: $accent_hover;
    text-decoration: underline;
}
QToolButton#iconButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: ${radius}px;
    padding: 0;
    outline: none;
}
QToolButton#iconButton:hover {
    background: $surface_hi;
    border-color: $border;
}
QToolButton#iconButton:pressed {
    background: $surface_alt;
}
QToolButton#iconButton:checked {
    background: $accent_soft;
    border-color: $accent_border;
}
QToolButton#iconButton:disabled {
    background: transparent;
}
QToolButton#iconButton::menu-indicator {
    image: none;
}

/* ------------------------------------------------------ formularios */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: ${radius}px;
    color: $text;
    font-size: ${font_body}px;
    padding: 8px 11px;
    selection-background-color: $accent;
    selection-color: $on_accent;
    outline: none;
}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
    border-color: $text_faint;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: $accent;
    background: $surface;
}
QLineEdit:disabled, QComboBox:disabled {
    background: $surface_alt;
    border-color: $border;
    color: $disabled_text;
}
QLineEdit[error="true"] {
    border-color: $danger;
}
QLineEdit#SearchInput {
    padding-left: 32px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid $text_muted;
    width: 0;
    height: 0;
    margin-right: 10px;
}
QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: ${radius}px;
    color: $text;
    padding: 4px;
    selection-background-color: $accent_soft;
    selection-color: $text;
    outline: none;
}
QCheckBox, QRadioButton {
    color: $text;
    font-size: ${font_body}px;
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    background: $surface;
    border: 1px solid $border_strong;
}
QCheckBox::indicator {
    border-radius: 4px;
}
QRadioButton::indicator {
    border-radius: 8px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: $accent;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: $accent;
    border-color: $accent;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background: $surface_alt;
    border-color: $border;
}

/* ---------------------------------------------------------- segmentado */
QFrame#Segmented {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: ${radius}px;
}
QPushButton#Segment {
    background: transparent;
    border: 1px solid transparent;
    border-radius: ${radius_sm}px;
    color: $text_muted;
    font-size: ${font_small}px;
    font-weight: 600;
    padding: 5px 12px;
}
QPushButton#Segment:hover {
    color: $text;
}
QPushButton#Segment:checked {
    background: $surface_hi;
    border-color: $accent_border;
    color: $text;
}

/* -------------------------------------------------------------- tabela */
QTableWidget, QTreeWidget, QTableView {
    background: $surface;
    alternate-background-color: $surface_alt;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
    color: $text;
    gridline-color: $grid;
    outline: none;
    selection-background-color: $accent_soft;
    selection-color: $text;
}
QTableWidget::item, QTreeWidget::item, QTableView::item {
    border-bottom: 1px solid $grid;
    padding: 8px 10px;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QTableView::item:selected {
    background: $accent_soft;
    color: $text;
}
QTableWidget::item:hover, QTreeWidget::item:hover {
    background: $surface_hi;
}
QHeaderView::section {
    background: $surface_alt;
    border: none;
    border-bottom: 1px solid $border;
    color: $text_muted;
    font-size: ${font_caption}px;
    font-weight: 700;
    padding: 9px 10px;
}
QTableCornerButton::section {
    background: $surface_alt;
    border: none;
    border-bottom: 1px solid $border;
}
QTreeWidget::branch {
    background: transparent;
}

/* ------------------------------------------------------------ progresso */
QProgressBar {
    background: $surface_hi;
    border: none;
    border-radius: 4px;
    max-height: 8px;
    min-height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background: $accent;
    border-radius: 4px;
}
QLabel#ProgressText {
    color: $text_muted;
    font-size: ${font_small}px;
}

/* --------------------------------------------------------------- badges */
QLabel#Badge {
    border: 1px solid transparent;
    border-radius: 999px;
    font-size: ${font_caption}px;
    font-weight: 700;
    padding: 2px 9px;
}
QLabel#Badge[kind="success"] {
    background: $success_soft;
    border-color: $success;
    color: $success;
}
QLabel#Badge[kind="warning"] {
    background: $warning_soft;
    border-color: $warning;
    color: $warning;
}
QLabel#Badge[kind="danger"], QLabel#Badge[kind="error"] {
    background: $danger_soft;
    border-color: $danger;
    color: $danger;
}
QLabel#Badge[kind="info"] {
    background: $info_soft;
    border-color: $info;
    color: $info;
}
QLabel#Badge[kind="neutral"] {
    background: $surface_hi;
    border-color: $border;
    color: $text_muted;
}
QLabel#Badge[outline="true"] {
    background: transparent;
}

/* ---------------------------------------------------------------- banner */
QFrame#Banner {
    border: 1px solid $border;
    border-radius: ${radius_md}px;
    background: $surface_alt;
}
QFrame#Banner[kind="info"] {
    background: $info_soft;
    border-color: $info;
}
QFrame#Banner[kind="success"] {
    background: $success_soft;
    border-color: $success;
}
QFrame#Banner[kind="warning"] {
    background: $warning_soft;
    border-color: $warning;
}
QFrame#Banner[kind="danger"] {
    background: $danger_soft;
    border-color: $danger;
}
QLabel#BannerTitle {
    color: $text;
    font-size: ${font_small}px;
    font-weight: 700;
}
QLabel#BannerText {
    color: $text_muted;
    font-size: ${font_small}px;
}

/* --------------------------------------------------------------- stepper */
QLabel#StepDot {
    border: 1px solid $border_strong;
    border-radius: 13px;
    background: $surface_hi;
    color: $text_faint;
    font-size: ${font_caption}px;
    font-weight: 700;
}
QLabel#StepDot[state="current"] {
    background: $accent_soft;
    border-color: $accent;
    color: $accent;
}
QLabel#StepDot[state="done"] {
    background: $accent;
    border-color: $accent;
    color: $on_accent;
}
QLabel#StepLabel {
    color: $text_faint;
    font-size: ${font_small}px;
    font-weight: 600;
}
QLabel#StepLabel[state="current"] {
    color: $text;
}
QLabel#StepLabel[state="done"] {
    color: $text_muted;
}
QFrame#StepLine {
    background: $border;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QFrame#StepLine[done="true"] {
    background: $accent;
}

/* ---------------------------------------------------------------- login */
QFrame#LoginBrand {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 $bg_elevated, stop:0.55 $bg, stop:1 $accent_soft);
    border: none;
    border-right: 1px solid $border;
}
QLabel#LoginBrandTitle {
    color: $text;
    font-size: ${font_display}px;
    font-weight: 700;
}
QLabel#LoginBrandTagline {
    color: $text_muted;
    font-size: 14px;
}
QLabel#FeatureTitle {
    color: $text;
    font-size: ${font_small}px;
    font-weight: 700;
}
QLabel#FeatureText {
    color: $text_muted;
    font-size: ${font_caption}px;
}
QLabel#LoginFooter {
    color: $text_faint;
    font-size: ${font_caption}px;
}
QLabel#AuthTitle {
    color: $text;
    font-size: ${font_h2}px;
    font-weight: 700;
}
QLabel#AuthSubtitle {
    color: $text_muted;
    font-size: ${font_small}px;
}
QLabel#InlineError {
    color: $danger;
    font-size: ${font_small}px;
    font-weight: 600;
}
QFrame#AuthCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: 16px;
}

/* ------------------------------------------------------------ carregando */
QWidget#LoadingPage {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $bg, stop:1 $bg_elevated);
}
QLabel#LoadingTitle {
    color: $text;
    font-size: ${font_h2}px;
    font-weight: 700;
}
QLabel#LoadingServer {
    color: $text_muted;
    font-size: ${font_small}px;
}
QLabel#LoadingHint {
    color: $text_faint;
    font-size: ${font_small}px;
}

/* ------------------------------------------------------------ diversos */
QToolTip {
    background: $surface_hi;
    border: 1px solid $border_strong;
    border-radius: ${radius_sm}px;
    color: $text;
    font-size: ${font_small}px;
    padding: 5px 8px;
}
QMenu {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: ${radius}px;
    color: $text;
    padding: 4px;
}
QMenu::item {
    background: transparent;
    border-radius: ${radius_sm}px;
    padding: 6px 20px 6px 12px;
}
QMenu::item:selected {
    background: $accent_soft;
}
QMenu::separator {
    background: $border;
    height: 1px;
    margin: 4px 8px;
}
QMessageBox {
    background: $surface;
}
QMessageBox QLabel {
    color: $text;
}
QMessageBox QPushButton {
    min-width: 84px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    margin: 2px;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: $border_strong;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: $text_faint;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: $border_strong;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: $text_faint;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QAbstractScrollArea::corner {
    background: transparent;
    border: none;
}
QSplitter::handle {
    background: $border;
}
"""
)


def build_qss(palette: Palette, font_family: str) -> str:
    """Monta o QSS aplicando os tokens da paleta e a fonte da marca."""
    valores = {k: v for k, v in palette.__dict__.items()}
    valores.update(
        {
            "UI_FONT": f'"{font_family}", "Segoe UI", "Inter", sans-serif',
            "font_display": FONT_DISPLAY,
            "font_h1": FONT_H1,
            "font_h2": FONT_H2,
            "font_h3": FONT_H3,
            "font_body": FONT_BODY,
            "font_small": FONT_SMALL,
            "font_caption": FONT_CAPTION,
            "radius_sm": RADIUS_SM,
            "radius": RADIUS,
            "radius_md": RADIUS_MD,
            "radius_lg": RADIUS_LG,
            "sidebar_width": SIDEBAR_WIDTH,
        }
    )
    return _QSS.substitute(valores)
