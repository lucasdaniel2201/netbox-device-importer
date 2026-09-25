"""Sessao unica com o NetBox, executada em thread dedicada.

O `SessionWorker` e dono de um unico `NetBoxClient` (e da sua sessao HTTP): conectar,
descobrir o ambiente e (mais adiante) importar acontecem todos na mesma thread e
reusam a mesma sessao - sem reconectar entre etapas.

O token vive apenas em memoria: nao e gravado em disco em nenhum momento.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import import_plan, provision, reports  # noqa: E402
from app.netbox_client import NetBoxClient  # noqa: E402


def first_problem(snapshot: dict) -> str:
    """Mensagem curta para quando a descoberta nao conseguiu ler nada.

    Sem isso, a tela dizia "conectado" com tudo vazio (aconteceu de verdade com o
    certificado autoassinado).
    """
    errors = snapshot.get("errors", [])
    if not errors:
        return "Nao foi possivel ler nada do NetBox (sem detalhes)."
    extra = f" (e mais {len(errors) - 1} endpoints com o mesmo problema)" if len(errors) > 1 else ""
    return f"Nao foi possivel ler nada do NetBox. {errors[0]}{extra}"


class SessionWorker(QObject):
    # Sinais de requisicao: emitidos pela UI (main thread) e executados na
    # thread da sessao via conexao enfileirada.
    request_connect = Signal(str, str, bool)  # url, token, verificar certificado
    request_discover = Signal()
    request_save_snapshot = Signal(str)
    request_provision = Signal(object)  # lista de Reference a criar
    request_import = Signal(object)  # ImportPlan
    request_cancel = Signal()
    request_logout = Signal()

    connected = Signal(dict)  # fotografia do ambiente
    connect_failed = Signal(str)
    discovered = Signal(dict)
    discover_failed = Signal(str)
    snapshot_saved = Signal(str)
    snapshot_failed = Signal(str)
    provision_done = Signal(dict)
    provision_failed = Signal(str)
    progress = Signal(int, int, str, str)  # indice, total, device, status
    import_done = Signal(dict)
    import_failed = Signal(str)
    log = Signal(str)
    disconnected = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._client: NetBoxClient | None = None
        self._snapshot: dict | None = None
        self._cancel = False

        self.request_connect.connect(self.connect_netbox)
        self.request_discover.connect(self.discover)
        self.request_save_snapshot.connect(self.save_snapshot)
        self.request_provision.connect(self.provision_references)
        self.request_import.connect(self.run_import)
        self.request_cancel.connect(self.cancel)
        self.request_logout.connect(self.logout)

    # ------------------------------------------------------------------ estado
    @property
    def client(self) -> NetBoxClient | None:
        return self._client

    @property
    def snapshot(self) -> dict | None:
        return self._snapshot

    # ------------------------------------------------------------ acoes (slots)
    @staticmethod
    def _connect_and_discover(url: str, token: str, verify_tls: bool):
        client = NetBoxClient(url, token, verify_tls=verify_tls)
        return client, provision.discover(client)

    @Slot(str, str, bool)
    def connect_netbox(self, url: str, token: str, verify_tls: bool) -> None:
        try:
            client, snapshot = self._connect_and_discover(url, token, verify_tls)
        except Exception as exc:
            self.connect_failed.emit(str(exc))
            return

        # Certificado autoassinado (comum quando o acesso e por IP interno): tenta
        # uma vez aceitando o certificado. Fica registrado no snapshot que a
        # verificacao TLS ficou de fora - nunca escondemos isso.
        if provision.needs_tls_retry(snapshot, verify_tls):
            client.close()
            try:
                client, snapshot = self._connect_and_discover(url, token, False)
            except Exception as exc:
                self.connect_failed.emit(str(exc))
                return

        if not provision.has_environment(snapshot):
            client.close()
            self.connect_failed.emit(first_problem(snapshot))
            return

        self._client = client
        self._snapshot = snapshot
        self.log.emit(
            f"Conectado em {client.base_url} (autenticacao: {client.token_scheme})."
        )
        self.connected.emit(snapshot)

    @Slot()
    def discover(self) -> None:
        client = self._client
        if client is None:
            self.discover_failed.emit("Nao ha sessao conectada.")
            return
        try:
            snapshot = provision.discover(client)
        except Exception as exc:
            self.discover_failed.emit(f"Falha ao consultar o ambiente: {exc}")
            return
        self._snapshot = snapshot
        self.discovered.emit(snapshot)

    @Slot(str)
    def save_snapshot(self, path: str) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            self.snapshot_failed.emit("Nada para salvar: ambiente ainda nao consultado.")
            return
        try:
            destination = provision.save_snapshot(snapshot, path)
        except Exception as exc:
            self.snapshot_failed.emit(f"Nao foi possivel salvar o schema: {exc}")
            return
        self.snapshot_saved.emit(str(destination))

    @Slot(object)
    def provision_references(self, references: list) -> None:
        """Cria as referencias que faltam. Fabricantes antes dos device-types."""
        client = self._client
        snapshot = self._snapshot
        if client is None or snapshot is None:
            self.provision_failed.emit("Sessao desconectada. Conecte novamente.")
            return

        fabricantes = [ref for ref in references if ref.kind == "manufacturer"]
        tipos = [ref for ref in references if ref.kind == "device_type"]
        criados: list[dict] = []

        try:
            for ref in fabricantes:
                obj = provision.create_reference(client, ref.kind, dict(ref.payload))
                criados.append({"kind": ref.kind, "label": ref.label, "id": obj.get("id")})
            if fabricantes:
                provision.refresh_reference_objects(client, snapshot, ("manufacturers",))

            for ref in tipos:
                manufacturer_id = import_plan.find_object_id(
                    snapshot, "manufacturers", ref.manufacturer_name
                )
                if manufacturer_id is None:
                    self.provision_failed.emit(
                        f"Fabricante '{ref.manufacturer_name}' nao encontrado. "
                        "Crie-o antes de repetir."
                    )
                    return
                payload = dict(ref.payload)
                payload["manufacturer"] = manufacturer_id
                obj = provision.create_reference(client, ref.kind, payload)
                criados.append({"kind": ref.kind, "label": ref.label, "id": obj.get("id")})
            if tipos:
                provision.refresh_reference_objects(client, snapshot, ("device_types",))
        except Exception as exc:
            self.provision_failed.emit(f"Falha ao criar referencia: {exc}")
            return

        self.provision_done.emit({"created": criados, "snapshot": snapshot})

    def _apply_network(
        self, client, device, device_id: int | None
    ) -> tuple[list[str], list[str]]:
        """Interface (com o MAC) -> IP vinculado -> primary_ip4.

        Roda **depois** do device existir: no NetBox o IP so se vincula a uma
        interface do device, entao a ordem importa.

        Cada passo e independente de proposito. O caso real: a interface ja existe
        (criada pelo template do device-type) e o PATCH do MAC falha por uma
        validacao que nao e nossa (PoE sem modo). Isso **nao** pode impedir o IP -
        o IP so precisa do id da interface, nao do MAC.

        Retorna (passos_concluidos, problemas).
        """
        partes: list[str] = []
        problemas: list[str] = []

        if device_id is None:
            return partes, ["device sem id; nao da para criar a interface."]

        interface_id = None
        try:
            status, interface_id = provision.upsert_interface(
                client,
                device_id,
                name=device.interface_name or provision.DEFAULT_INTERFACE_NAME,
                mac_address=device.mac,
            )
            partes.append(f"interface {status}")
        except Exception as exc:
            problemas.append(f"interface (MAC): {exc}")

        if interface_id is None:
            # O PATCH falhou, mas a interface existe: sem o id nao ha como vincular o IP.
            interface_id = self._existing_interface_id(client, device_id)
        if interface_id is None:
            problemas.append("IP nao criado: nao ha interface no device para vincular.")
            return partes, problemas

        if device.ip:
            ip_id = None
            try:
                ip_status, ip_id = provision.upsert_ip_address(
                    client,
                    device.ip,
                    interface_id,
                    custom_fields=device.ip_custom_fields,
                    description=device.name,
                )
                partes.append(f"ip {ip_status}")
            except Exception as exc:
                problemas.append(f"ip: {exc}")

            if ip_id is not None:
                try:
                    provision.set_primary_ip4(client, device_id, ip_id)
                    partes.append("primary_ip4 definido")
                except Exception as exc:
                    problemas.append(f"primary_ip4: {exc}")

        return partes, problemas

    @staticmethod
    def _existing_interface_id(client, device_id: int) -> int | None:
        try:
            existentes = client.fetch_all(
                provision.INTERFACE_ENDPOINT, params={"device_id": device_id}
            )
        except Exception:
            return None
        return existentes[0].get("id") if existentes else None

    @Slot(object)
    def run_import(self, plan) -> None:
        """Executa o plano, device a device, gravando o relatorio no fim."""
        client = self._client
        if client is None:
            self.import_failed.emit("Sessao desconectada. Conecte novamente.")
            return
        if not plan.can_import:
            self.import_failed.emit(
                "O plano ainda tem pendencias (referencias a criar ou linhas com erro)."
            )
            return

        self._cancel = False
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        devices = plan.ready_devices
        total = len(devices)

        linhas_log = [f"=== Importacao iniciada em {timestamp} ===", f"Devices: {total}"]
        resultados: list[dict] = []
        contagem = {"created": 0, "updated": 0, "exists": 0, "error": 0}
        contagem_avisos = 0
        cancelado = False

        for indice, device in enumerate(devices, start=1):
            if self._cancel:
                cancelado = True
                linhas_log.append("Execucao cancelada pelo usuario.")
                break

            request_id = ""
            avisos: list[str] = []
            try:
                status, object_id, request_id = provision.upsert_device(
                    client,
                    device.payload(),
                    changelog_message="Importacao via planilha de cameras",
                )
            except Exception as exc:
                status, object_id, message = "error", None, str(exc)
            else:
                message = "ok"
                if device.include_network:
                    partes, avisos = self._apply_network(client, device, object_id)
                    if partes:
                        message = ", ".join(partes)
                    if avisos:
                        # O device esta gravado: rede incompleta e aviso, nao erro.
                        message += " | aviso: " + " | ".join(avisos)

            contagem[status] = contagem.get(status, 0) + 1
            if avisos:
                contagem_avisos += 1
            resultados.append(
                {
                    "row_number": device.row_number,
                    "name": device.name,
                    "site": device.site,
                    "device_type": device.device_type_label,
                    "status": status,
                    "message": message,
                    "warnings": "; ".join(avisos),
                    "request_id": request_id,
                }
            )
            linhas_log.append(f"{status:<8} | {device.name} | {message}")
            self.progress.emit(indice, total, device.name, status)

        # Alguns erros vao no resumo: assim a tela mostra a causa sem abrir o JSON.
        amostras_erro = [
            {"name": item["name"], "message": item["message"]}
            for item in resultados
            if item["status"] == "error"
        ][:3]
        amostras_aviso = [
            {"name": item["name"], "message": item["warnings"]}
            for item in resultados
            if item.get("warnings")
        ][:3]

        summary = {
            "timestamp": timestamp,
            "url": client.base_url,
            "api_version": client.api_version,
            "role": plan.options.role,
            "device_status": plan.options.status,
            "total": total,
            "processed": len(resultados),
            "created": contagem["created"],
            "updated": contagem["updated"],
            "exists": contagem["exists"],
            "errors": contagem["error"],
            "canceled": cancelado,
            "deferred": list(plan.deferred),
            # Registra os valores fixos enviados: nao podem ser invisiveis.
            "custom_fields": dict(plan.custom_fields_used),
            "warnings": contagem_avisos,
            "error_samples": amostras_erro,
            "warning_samples": amostras_aviso,
        }

        try:
            paths = reports.write_reports(timestamp, summary, resultados, linhas_log)
        except Exception as exc:
            self.import_failed.emit(f"Falha ao salvar os relatorios: {exc}")
            return

        summary["report_paths"] = {key: str(value) for key, value in paths.items()}
        self.import_done.emit(summary)

    @Slot()
    def cancel(self) -> None:
        self._cancel = True

    @Slot()
    def logout(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._snapshot = None
        self.disconnected.emit()
