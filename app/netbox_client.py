"""Cliente REST do NetBox.

O NetBox e API-first: tudo e feito por JSON sobre HTTP com um token no header
`Authorization`. Nada de scraping, CSRF ou HTML.

Decisoes confirmadas na instancia (Community v4.3.6):
- header `Authorization: Token <token>`; instancias 4.5+ usam `Bearer <key>.<tok>`.
  Aqui comeca com `Token` e, se a primeira recusa for de autenticacao, tenta
  `Bearer` uma vez e trava no que funcionou.
- a barra no final e obrigatoria (`/api/dcim/devices/`); sem ela o NetBox responde 302.
- paginacao: sem `limit`, a API devolve so a primeira pagina (padrao 50). O
  `fetch_all` percorre o campo `next` com `limit=MAX_PAGE_SIZE` (1000).
- erro em lote NAO diz qual item falhou no 4.3.6 (isso e v4.7+), por isso quem
  chama deve validar antes e escrever item a item.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import requests
import urllib3

DEFAULT_TIMEOUT = 30
MAX_PAGE_SIZE = 1000
TOKEN_SCHEMES = ("Token", "Bearer")
RATE_LIMIT_STATUS = 429
AUTH_STATUS = (401, 403)


class NetBoxError(RuntimeError):
    """Erro de comunicacao ou de validacao com o NetBox."""


class NetBoxTLSError(NetBoxError):
    """Certificado TLS nao validado (tipicamente autoassinado).

    E um tipo proprio porque quem chama precisa distinguir "o certificado barrou"
    de qualquer outro erro - e nao pode depender de procurar texto em ingles numa
    mensagem que nos mesmos traduzimos.
    """


class NetBoxConnectionError(NetBoxError):
    """Nao deu para falar com o servidor (rede, DNS, timeout, porta fechada).

    Serve para a descoberta desistir cedo: sem isso, um servidor fora do ar faria
    o app tentar ~26 endpoints, um timeout em cada, travando a tela de carregamento.
    """


TLS_ERROR_MARKERS = (
    "certificate verify failed",
    "certificate_verify_failed",
    "self-signed certificate",
)


def is_tls_error(exc: Exception) -> bool:
    """True se a excecao crua e de certificado TLS nao validado."""
    texto = str(exc).lower()
    return any(marker in texto for marker in TLS_ERROR_MARKERS)


def describe_transport_error(exc: Exception, base_url: str = "") -> str:
    """Traduz erro de rede/TLS numa mensagem curta e acionavel.

    A mensagem crua do `requests` (SSLConnectionPool...) nao diz ao usuario o que
    fazer - e o caso mais comum aqui e certificado autoassinado em IP interno.
    """
    texto = str(exc)
    lowered = texto.lower()
    if any(marker in lowered for marker in TLS_ERROR_MARKERS):
        # Sem instrucao de tela: o app ja repete a conexao sem verificar (session.py).
        return "o certificado TLS do NetBox nao foi validado (certificado autoassinado)."
    if "sslerror" in lowered:
        return "falha de TLS ao falar com o NetBox; confira o certificado e a URL."
    if isinstance(exc, requests.exceptions.ConnectTimeout) or "timed out" in lowered:
        return f"tempo esgotado ao conectar em {base_url or 'NetBox'}; confira a rede."
    if isinstance(exc, requests.exceptions.ConnectionError) or "max retries exceeded" in lowered:
        return (
            f"nao foi possivel conectar em {base_url or 'NetBox'}; "
            "confira a URL, a rede e se o servidor esta no ar."
        )
    return texto[:300]


def normalize_base_url(base_url: str) -> str:
    """Deixa a URL base sem barra final e com esquema (https por padrao)."""
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise ValueError("Informe a URL do NetBox.")
    if "://" not in url:
        url = "https://" + url
    return url


def normalize_path(path: str) -> str:
    """Garante caminho iniciando com '/' e terminando em '/' (exigencia da API)."""
    if "://" in path:
        return path
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") + "/"


def detail_path(path: str, object_id: Any) -> str:
    """Caminho de detalhe (`/api/dcim/devices/123/`) a partir do caminho de lista."""
    return normalize_path(path).rstrip("/") + f"/{object_id}/"


def describe_error(status_code: int, payload: Any, text: str = "") -> str:
    """Transforma a resposta de erro do NetBox numa mensagem legivel.

    O NetBox responde `{"detail": "..."}` para erros gerais e
    `{"campo": ["mensagem"], ...}` para erros de validacao.
    """
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        parts: list[str] = []
        for field, value in payload.items():
            if isinstance(value, (list, tuple)):
                parts.append(f"{field}: {'; '.join(str(item) for item in value)}")
            else:
                parts.append(f"{field}: {value}")
        if parts:
            return " | ".join(parts)
    if isinstance(payload, list):
        return " | ".join(str(item) for item in payload)
    cleaned = (text or "").strip()
    if cleaned.startswith("<"):
        # O NetBox devolve a pagina HTML do app quando o caminho nao existe na API
        # (nao um JSON de erro). Sem isso, o log fica com um HTML gigante.
        return f"resposta HTML (endpoint indisponivel nesta versao?) - HTTP {status_code}"
    if cleaned:
        return cleaned[:300]
    return f"HTTP {status_code}"


class NetBoxClient:
    """Sessao HTTP reaproveitada contra a API do NetBox."""

    def __init__(
        self,
        base_url: str,
        token: str,
        verify_tls: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.token = (token or "").strip()
        if not self.token:
            raise ValueError("Informe o token da API do NetBox.")
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.session = requests.Session()

        self.api_version = ""
        self.last_request_id = ""

        self._scheme_index = 0
        self._scheme_locked = False

        # Certificado autoassinado (comum quando o NetBox roda por IP interno) gera
        # aviso a cada requisicao; silencia so quando o usuario assumiu o risco.
        if not verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ------------------------------------------------------------------ helpers
    @property
    def token_scheme(self) -> str:
        """Esquema de autenticacao em uso (`Token` ou `Bearer`)."""
        return TOKEN_SCHEMES[self._scheme_index]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"{self.token_scheme} {self.token}",
            "Accept": "application/json",
        }

    def _full_url(self, path: str) -> str:
        if "://" in path:
            return path
        return self.base_url + normalize_path(path)

    def _capture_headers(self, response: requests.Response) -> None:
        self.api_version = response.headers.get("API-Version", self.api_version)
        request_id = response.headers.get("X-Request-ID")
        if request_id:
            self.last_request_id = request_id

    def _try_next_scheme(self) -> bool:
        """Troca `Token` por `Bearer` (ou vice-versa) apenas uma vez, antes de travar."""
        if self._scheme_locked:
            return False
        if self._scheme_index + 1 < len(TOKEN_SCHEMES):
            self._scheme_index += 1
            return True
        return False

    @staticmethod
    def _retry_delay(response: requests.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return min(float(header), 30.0)
        return min(float(2**attempt), 30.0)

    # ------------------------------------------------------------------- HTTP
    def _send(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> requests.Response:
        """Envia a requisicao tratando rate limit (429) e troca de esquema de token."""
        attempts = 0
        while True:
            attempts += 1
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=self._headers(),
                    timeout=self.timeout,
                    verify=self.verify_tls,
                )
            except requests.exceptions.RequestException as exc:
                # Rede/TLS: mensagem curta e acionavel, nao o dump do requests.
                mensagem = describe_transport_error(exc, self.base_url)
                if is_tls_error(exc):
                    raise NetBoxTLSError(mensagem) from exc
                raise NetBoxConnectionError(mensagem) from exc
            self._capture_headers(response)

            if response.status_code == RATE_LIMIT_STATUS and attempts <= 4:
                time.sleep(self._retry_delay(response, attempts))
                continue
            if response.status_code in AUTH_STATUS and self._try_next_scheme():
                continue
            return response

    def _raise_for_status(self, response: requests.Response, method: str, target: str) -> None:
        if response.ok:
            self._scheme_locked = True
            return
        try:
            payload = response.json()
        except ValueError:
            payload = None
        message = describe_error(response.status_code, payload, response.text)
        hint = ""
        if response.status_code in AUTH_STATUS:
            hint = (
                " Verifique o token (valor correto e 'write enabled' para gravar) "
                "e se a URL aponta para o NetBox certo."
            )
        raise NetBoxError(f"{method} {target} -> HTTP {response.status_code}: {message}{hint}")

    def _json(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        response = self._send(method, url, params=params, json=json)
        self._raise_for_status(response, method, self._label(url))
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _label(url: str) -> str:
        """Caminho (sem host) para aparecer nas mensagens de erro."""
        parsed = urlparse(url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Requisicao JSON generica contra a API."""
        return self._json(method, self._full_url(path), params=params, json=json)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def options(self, path: str) -> Any:
        """OPTIONS do endpoint: schema autoritativo da instancia (campos/obrigatorios)."""
        return self.request("OPTIONS", path)

    def status(self) -> dict[str, Any]:
        """`/api/status/` - versao do NetBox e plugins instalados."""
        return self.request("GET", "/api/status/")

    def fetch_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Percorre todas as paginas e devolve a lista completa.

        Sem `limit` a API devolve apenas a primeira pagina (padrao 50): este metodo
        fixa `limit=MAX_PAGE_SIZE` e segue o campo `next`.
        """
        query: dict[str, Any] = {"limit": MAX_PAGE_SIZE}
        query.update(params or {})

        data = self._json("GET", self._full_url(path), params=query)
        if isinstance(data, list):
            return list(data)

        results: list[dict[str, Any]] = list(data.get("results", []))
        next_url = data.get("next")
        while next_url:
            page = self._json("GET", next_url)
            if not isinstance(page, dict):
                break
            results.extend(page.get("results", []))
            next_url = page.get("next")
        return results

    def count(self, path: str, **filters: Any) -> int | None:
        """Total de objetos sem baixar a lista (`limit=1` + campo `count`)."""
        data = self.request("GET", path, params={"limit": 1, **filters})
        if isinstance(data, dict):
            return data.get("count")
        if isinstance(data, list):
            return len(data)
        return None

    def get_or_none(self, path: str, **filters: Any) -> dict[str, Any] | None:
        """Busca por chave unica: 0 resultados -> None; mais de 1 -> erro.

        A API nao tem "criar ou atualizar": este metodo e a base da idempotencia
        (GET -> PATCH se existe, POST se nao).
        """
        data = self.request("GET", path, params={"limit": 2, **filters})
        results = data.get("results", []) if isinstance(data, dict) else list(data)
        total = data.get("count", len(results)) if isinstance(data, dict) else len(results)
        if total == 0:
            return None
        if total > 1 or len(results) > 1:
            raise NetBoxError(
                f"Mais de um objeto em {normalize_path(path)} para {filters}: "
                f"{total} encontrados (a chave precisa ser unica)."
            )
        return results[0]

    # ------------------------------------------------------------------ escrita
    def create(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, json=payload)

    def update(
        self, path: str, object_id: Any, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self.request("PATCH", detail_path(path, object_id), json=payload)

    def delete(self, path: str, object_id: Any) -> None:
        self.request("DELETE", detail_path(path, object_id))

    def bulk_create(self, path: str, payloads: list[dict[str, Any]]) -> Any:
        """POST de uma lista JSON.

        No 4.3.6 e tudo-ou-nada: se um item falhar, nada e criado e a resposta nao
        diz qual item falhou. Prefira criar item a item quando precisar isolar falhas.
        """
        return self.request("POST", path, json=list(payloads))

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass
