"""Tokens do design system: cores, espacamento, raios e tipografia.

Um token e um valor com nome. Nenhuma tela deve escrever uma cor literal: quando
o valor muda, muda aqui e vale para o app inteiro. Dois temas completos (escuro e
claro) implementam o mesmo conjunto de campos, entao um componente escrito contra
`Palette` funciona nos dois sem saber qual esta ativo.

A paleta escura parte de grafite (fundo) com superficies levemente mais claras,
bordas discretas e um unico acento azul. A clara inverte a logica sem inverter a
hierarquia: fundo cinza-azulado muito claro, superficies brancas, mesmas bordas
relativas. As cores semanticas trocam de tom entre os temas porque verde/ambar/
vermelho legiveis sobre grafite nao sao legiveis sobre branco.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Palette:
    """Conjunto completo de cores de um tema."""

    mode: str
    # superficies
    bg: str
    bg_elevated: str
    surface: str
    surface_alt: str
    surface_hi: str
    overlay: str
    shadow: str
    # bordas
    border: str
    border_strong: str
    grid: str
    # texto
    text: str
    text_muted: str
    text_faint: str
    disabled_text: str
    # acento
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    accent_border: str
    on_accent: str
    # semanticas
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    info: str
    info_soft: str

    @property
    def is_dark(self) -> bool:
        return self.mode == "dark"

    def kind_color(self, kind: str) -> str:
        """Cor de destaque de um estado semantico."""
        return {
            "success": self.success,
            "warning": self.warning,
            "danger": self.danger,
            "error": self.danger,
            "info": self.info,
            "neutral": self.text_muted,
        }.get(kind, self.text_muted)

    def kind_soft(self, kind: str) -> str:
        """Fundo suave correspondente ao estado (usado em badges)."""
        return {
            "success": self.success_soft,
            "warning": self.warning_soft,
            "danger": self.danger_soft,
            "error": self.danger_soft,
            "info": self.info_soft,
            "neutral": self.surface_hi,
        }.get(kind, self.surface_hi)

    def replace(self, **changes: str) -> Palette:
        """Copia com campos trocados (usado para derivar temas)."""
        validos = {field.name for field in fields(self)}
        return Palette(**{**self.__dict__, **{k: v for k, v in changes.items() if k in validos}})


DARK = Palette(
    mode="dark",
    bg="#0B0F14",
    bg_elevated="#0E141C",
    surface="#121A24",
    surface_alt="#0F1720",
    surface_hi="#18222E",
    overlay="rgba(5, 9, 14, 0.72)",
    shadow="rgba(0, 0, 0, 0.45)",
    border="#1E2936",
    border_strong="#2B3A4B",
    grid="#1A2431",
    text="#E8EEF5",
    text_muted="#9AAABD",
    text_faint="#67788B",
    disabled_text="#4C5C6E",
    accent="#4C9BFF",
    accent_hover="#6FB2FF",
    accent_pressed="#3B82E0",
    accent_soft="#152A44",
    accent_border="#27476E",
    on_accent="#061222",
    success="#3DD68C",
    success_soft="#102A22",
    warning="#F2B84B",
    warning_soft="#2E2412",
    danger="#F87171",
    danger_soft="#2F1618",
    info="#5B9DFF",
    info_soft="#14233A",
)

LIGHT = Palette(
    mode="light",
    bg="#F4F6FA",
    bg_elevated="#FFFFFF",
    surface="#FFFFFF",
    surface_alt="#F8FAFC",
    surface_hi="#EEF2F7",
    overlay="rgba(244, 246, 250, 0.80)",
    shadow="rgba(16, 24, 40, 0.12)",
    border="#E3E8EF",
    border_strong="#C9D3E0",
    grid="#E8EDF3",
    text="#101828",
    text_muted="#55637A",
    text_faint="#7C8AA0",
    disabled_text="#A3AEBE",
    accent="#1F6FD0",
    accent_hover="#1A5FB4",
    accent_pressed="#15509A",
    accent_soft="#E8F1FC",
    accent_border="#BBD6F5",
    on_accent="#FFFFFF",
    success="#0E8A5F",
    success_soft="#E4F5EE",
    warning="#A96A00",
    warning_soft="#FDF3E2",
    danger="#C0392B",
    danger_soft="#FCEBE9",
    info="#2563EB",
    info_soft="#E8EEFD",
)

PALETTES: dict[str, Palette] = {"dark": DARK, "light": LIGHT}
DEFAULT_MODE = "dark"

# --------------------------------------------------------------- espacamento
# Escala de 4px. Use SPACE[index] em vez de numeros soltos: mantem o ritmo
# vertical e horizontal igual em todas as telas.
SPACE = (0, 4, 8, 12, 16, 20, 24, 32, 40, 48)
GAP_XS, GAP_SM, GAP_MD, GAP_LG, GAP_XL = 4, 8, 12, 16, 24

# ------------------------------------------------------------------- raios
RADIUS_SM = 6
RADIUS = 8
RADIUS_MD = 10
RADIUS_LG = 14

# --------------------------------------------------------------- tipografia
# Tamanhos em px. A hierarquia e curta de proposito: display -> titulo ->
# subtitulo -> corpo -> legenda. Peso e cor carregam a enfase, nao o tamanho.
FONT_DISPLAY = 28
FONT_H1 = 22
FONT_H2 = 17
FONT_H3 = 14
FONT_BODY = 13
FONT_SMALL = 12
FONT_CAPTION = 11

# ------------------------------------------------------------------ metricas
SIDEBAR_WIDTH = 248
HEADER_HEIGHT = 76
CONTENT_MAX_WIDTH = 1180
