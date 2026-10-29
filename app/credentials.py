"""Guarda o token da API protegido pelo sistema operacional.

No Windows o token e cifrado com `CryptProtectData` (DPAPI), amarrado a conta e a
maquina:
- **nao fica em texto claro** no disco (abrir o arquivo no Bloco de Notas nao mostra nada);
- apenas aquela conta, naquela maquina, consegue decifrar;
- copiar o arquivo para outra maquina/usuario **nao funciona** - o que e proposital.

Fora do Windows (a versao de teste em Linux) a ordem e outra:
1. **chaveiro do sistema** (`keyring`, quando instalado) - o segredo nao fica no
   sistema de arquivos;
2. **arquivo com permissao 0600** - sem cifra, protegido so pela permissao do
   arquivo. `protection_label()` diz qual dos dois esta em uso, e a tela mostra
   isso: o usuario nunca deve supor uma protecao que nao existe.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from app.paths import user_data_dir

TOKEN_FILENAME = "token.dat"

# Flags do DPAPI: proibe qualquer janela do sistema durante a operacao.
CRYPTPROTECT_UI_FORBIDDEN = 0x01

# Permissao do arquivo do token no backend sem cifra: so o dono le e escreve.
FILE_MODE = 0o600

# Entrada no chaveiro do sistema (backend POSIX).
KEYRING_SERVICE = "ImportadorCamerasNetBox"
KEYRING_USERNAME = "netbox-token"


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


def _keyring():
    """Modulo `keyring`, se houver um backend que realmente funcione (senao None).

    `keyring.get_keyring()` nao levanta quando nao ha chaveiro: devolve o backend
    `fail`, cujo `set_password` e que falha. Tratar isso como "ha chaveiro" faria a
    tela anunciar uma protecao que nao existe.
    """
    try:
        import keyring  # type: ignore[import-not-found]
        from keyring.backends import fail  # type: ignore[import-not-found]

        backend_ativo = keyring.get_keyring()
    except Exception:
        return None
    if isinstance(backend_ativo, fail.Keyring):
        return None
    return keyring


def dpapi_available() -> bool:
    """True se o DPAPI do Windows esta disponivel nesta maquina."""
    try:
        _crypt32()
    except CredentialError:
        return False
    return True


def keyring_available() -> bool:
    """True se ha chaveiro do sistema utilizavel (backend fora do Windows)."""
    return _keyring() is not None


def backend() -> str:
    """Onde o token e guardado: `dpapi`, `keyring` ou `file`."""
    if dpapi_available():
        return "dpapi"
    if keyring_available():
        return "keyring"
    return "file"


def is_available() -> bool:
    """True se ha protecao do sistema operacional (DPAPI ou chaveiro).

    Falso quando o token so pode ir para um arquivo 0600 - a tela avisa nesse caso.
    """
    return backend() in ("dpapi", "keyring")


def can_store() -> bool:
    """True se da para guardar o token de algum jeito nesta maquina."""
    return True


def protection_label() -> str:
    """Descricao honesta da protecao em uso (vai para a tela)."""
    return {
        "dpapi": "cifrado pelo Windows (DPAPI)",
        "keyring": "chaveiro do sistema",
        "file": f"arquivo com permissao {FILE_MODE:o} (sem cifra)",
    }[backend()]


def token_path() -> Path:
    """Arquivo do token: sempre na pasta de dados do usuario, nunca ao lado do .exe."""
    return user_data_dir() / TOKEN_FILENAME


def protect(text: str) -> bytes:
    """Cifra o texto com a identidade do usuario atual (DPAPI)."""
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


def _token_dir() -> Path:
    """Pasta do token, restrita ao dono (0700 no POSIX)."""
    destino = token_path().parent
    destino.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        try:
            os.chmod(destino, 0o700)
        except OSError:
            pass
    return destino


def _write_file(token: str) -> None:
    """Grava o token num arquivo so do dono (backend `file`)."""
    _token_dir()
    destino = token_path()

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        # Um `token.dat` que fosse link simbolico escreveria em outro arquivo.
        flags |= os.O_NOFOLLOW
    descritor = os.open(destino, flags, FILE_MODE)
    try:
        # `O_CREAT` nao corrige a permissao de um arquivo que ja existia.
        os.fchmod(descritor, FILE_MODE)
        with os.fdopen(descritor, "wb", closefd=False) as handle:
            handle.write(token.encode("utf-8"))
    finally:
        os.close(descritor)


def _read_file() -> str:
    """Le o arquivo do backend `file` (ou decifra o do DPAPI)."""
    bruto = token_path().read_bytes()
    if dpapi_available():
        return unprotect(bruto)
    return bruto.decode("utf-8")


def save_token(token: str) -> Path:
    """Guarda o token pelo melhor backend disponivel."""
    if not token:
        raise CredentialError("Token vazio.")
    destino = token_path()
    destino.parent.mkdir(parents=True, exist_ok=True)

    if dpapi_available():
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(protect(token))
        return destino

    chaveiro = _keyring()
    if chaveiro is not None:
        try:
            chaveiro.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
        except Exception as exc:  # chaveiro sem sessao (ex.: servico parado)
            raise CredentialError(f"O chaveiro do sistema recusou guardar o token: {exc}") from exc
        destino.unlink(missing_ok=True)
        return destino

    _write_file(token)
    return destino


def load_token() -> str:
    """Token guardado, ou "" se nao houver (ou se nao der para decifrar)."""
    chaveiro = _keyring()
    if chaveiro is not None:
        try:
            guardado = chaveiro.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            guardado = None
        if guardado:
            return guardado

    caminho = token_path()
    if not caminho.exists():
        return ""
    try:
        return _read_file()
    except Exception:
        # Contrato deste modulo: nunca derrubar o app por causa do arquivo do token.
        # Um `token.dat` vazio (queda no meio da escrita) ja levantou ValueError aqui.
        return ""


def has_token() -> bool:
    return bool(load_token())


def clear_token() -> None:
    """Esquece o token guardado (usado quando o usuario quer trocar)."""
    chaveiro = _keyring()
    if chaveiro is not None:
        try:
            chaveiro.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            pass
    try:
        token_path().unlink(missing_ok=True)
    except OSError:
        pass
