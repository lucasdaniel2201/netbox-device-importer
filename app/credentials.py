"""Guarda o token da API protegido pelo Windows (DPAPI).

O token e cifrado com `CryptProtectData`, amarrado a conta do Windows e a maquina:
- **nao fica em texto claro** no disco (abrir o arquivo no Bloco de Notas nao mostra nada);
- apenas aquela conta, naquela maquina, consegue decifrar;
- copiar o arquivo para outra maquina/usuario **nao funciona** - o que e proposital.

Se o DPAPI nao estiver disponivel, nao gravamos de forma alguma: `save_token`
levanta `CredentialError` e o app volta a pedir o token a cada abertura. Guardar
em texto claro seria pior do que nao guardar.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

from app.paths import user_data_dir

TOKEN_FILENAME = "token.dat"

# Flags do DPAPI: proibe qualquer janela do sistema durante a operacao.
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class CredentialError(RuntimeError):
    """Nao foi possivel proteger ou recuperar o token."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    """Monta o DATA_BLOB e devolve o buffer junto, para ele nao ser coletado."""
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _crypt32():
    try:
        biblioteca = ctypes.windll.crypt32  # type: ignore[attr-defined]
    except AttributeError as exc:  # fora do Windows
        raise CredentialError("DPAPI indisponivel: protecao do Windows nao encontrada.") from exc

    biblioteca.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    biblioteca.CryptProtectData.restype = wintypes.BOOL
    biblioteca.CryptUnprotectData.argtypes = list(biblioteca.CryptProtectData.argtypes)
    biblioteca.CryptUnprotectData.restype = wintypes.BOOL
    return biblioteca


def is_available() -> bool:
    """True se da para proteger/recuperar tokens nesta maquina."""
    try:
        _crypt32()
    except CredentialError:
        return False
    return True


def token_path() -> Path:
    """Arquivo do token: sempre na pasta de dados do usuario, nunca ao lado do .exe."""
    return user_data_dir() / TOKEN_FILENAME


def protect(text: str) -> bytes:
    """Cifra o texto com a identidade do usuario atual."""
    entrada, _manter_entrada = _blob(text.encode("utf-8"))
    saida = _DataBlob()
    ok = _crypt32().CryptProtectData(
        ctypes.byref(entrada), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(saida)
    )
    if not ok:
        raise CredentialError("O Windows recusou cifrar o token.")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


def unprotect(data: bytes) -> str:
    """Decifra o que foi gravado por `protect` (so na mesma conta/maquina)."""
    entrada, _manter_entrada = _blob(data)
    saida = _DataBlob()
    ok = _crypt32().CryptUnprotectData(
        ctypes.byref(entrada), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(saida)
    )
    if not ok:
        raise CredentialError("O Windows nao conseguiu decifrar o token guardado.")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


def save_token(token: str) -> Path:
    """Cifra e grava o token. Levanta CredentialError se nao der para proteger."""
    if not token:
        raise CredentialError("Token vazio.")
    destino = token_path()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(protect(token))
    return destino


def load_token() -> str:
    """Token guardado, ou "" se nao houver (ou se nao der para decifrar)."""
    caminho = token_path()
    if not caminho.exists():
        return ""
    try:
        return unprotect(caminho.read_bytes())
    except (CredentialError, OSError):
        return ""


def has_token() -> bool:
    return bool(load_token())


def clear_token() -> None:
    """Esquece o token guardado (usado quando o usuario quer trocar)."""
    try:
        token_path().unlink(missing_ok=True)
    except OSError:
        pass
