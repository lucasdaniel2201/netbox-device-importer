"""Configuracao fixa deste deployment.

O servidor e sempre o mesmo, entao fica no codigo em vez de na tela. Se um dia
mudar, muda-se aqui e gera-se um executavel novo.

NAO coloque token nem senha aqui: o token e guardado por `app/credentials.py`.
"""

from typing import Any

NETBOX_URL = "https://192.168.90.123"

# Campos personalizados que o NetBox exige e que o app envia sempre.
#
# O que estiver declarado aqui **vence**. Para os campos obrigatorios que ninguem
# declarou, o app usa o valor que ja existe num objeto do NetBox - porque a API nao
# expoe as opcoes dos campos `select` (`choices` vem vazio) e chutar um valor
# "obvio" da 400 ("Escolha X e invalida para o conjunto de escolhas").
#
# Os valores efetivamente enviados aparecem no resumo do plano e no relatorio.
CUSTOM_FIELDS: dict[str, dict[str, Any]] = {
    # Booleano: True = "e validavel?" (o valor que todo device do NetBox ja usa).
    "dcim.device": {"Validavel": True},
    # Em branco de proposito: o valor de `add_to_zabbix` vem de um IP existente.
    # Se um dia souber o valor certo (Admin -> Custom Fields -> "Adicionar ao
    # zabbix?" -> Escolhas), declare aqui para fixar.
    "ipam.ipaddress": {},
}
