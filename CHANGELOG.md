# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o [versionamento semântico](https://semver.org/lang/pt-BR/). A versão do aplicativo vive em três arquivos mantidos em sincronia: `app/version.py` (lido pelo Python), `instalador.iss` (lido pelo Inno Setup) e `version_info.txt` (lido pelo Windows). O teste `tests/test_version.py` falha se algum deles divergir dos outros dois.

## [Não publicado]

## [1.0.0] - 2026-09-25

### Adicionado

- App desktop em Python + PySide6 que documenta câmeras e switches no NetBox via API REST (JSON sobre HTTP com token de API), sem scraping.
- Login por token de API: a URL do servidor é fixa no código e só o token é informado na tela. O token guardado fica cifrado pelo DPAPI do Windows, amarrado à conta e à máquina do usuário; com token guardado o login é pulado, e o botão "Esquecer token guardado" apaga o token local. O cabeçalho mostra quem é o dono do token.
- Descoberta do ambiente ao conectar: sites, papéis, tipos de device, fabricantes, contagens, custom fields e o que o token pode fazer em cada endpoint, com resumo na tela, painel "Detalhes técnicos (avançado)", opção de salvar o schema em JSON e botões "Atualizar" e "Sair".
- Geração da planilha modelo (`modelo_cameras_netbox.xlsx`) com as listas suspensas de Site e Papel preenchidas a partir do NetBox.
- Importação de planilhas `.xlsx` e `.csv`, com validação linha a linha e plano de importação antes do envio; referências ausentes (fabricante, device-type) só são criadas com confirmação explícita; botão de importar bloqueado enquanto houver linha com erro, referência pendente ou campo obrigatório sem valor; barra de progresso por device, botão de cancelar e resumo final com amostras dos erros e o caminho do relatório.
- Idempotência na escrita: cada objeto passa por `GET` antes de `POST` (criar) ou `PATCH` (atualizar); rodar a mesma planilha de novo não duplica nada.
- Suporte aos custom fields obrigatórios da instância (`Validavel` no device e `add_to_zabbix` no IP address), com o valor do campo `select` descoberto por amostragem de um IP existente.
- Rede em passos independentes (interface, depois IP, depois `primary_ip4`): falha em um passo vira aviso e o device permanece gravado. O IP é opcional e, sem ele, o `primary_ip4` não é definido.
- Todo device gravado com status `active`, que não vem da planilha.
- Relatórios de cada importação em `reports/`: log com uma linha por device, JSON com resumo e o `X-Request-ID` de cada escrita, e CSV com o resultado por linha.
- Reconexão aceitando o certificado quando o NetBox é acessado por IP interno com certificado autoassinado, decisão registrada no schema do ambiente.
- Verificação de atualizações ao abrir: o app conhece a própria versão (`app/version.py`) e consulta a última Release publicada numa thread própria, sem travar a interface. Havendo versão mais nova, aparece um aviso com o número da versão e o botão **Baixar e instalar**, que baixa o instalador em streaming, mostra o progresso e o abre para o Inno Setup fazer o upgrade por cima. A consulta automática falha em silêncio quando não há internet; a falha de um download pedido pelo usuário aparece na tela. Como essa é a única parte do app que baixa e executa um binário, a URL só é aceita se for HTTPS de um host do GitHub.
- Teste que falha se a versão divergir entre `app/version.py`, `instalador.iss` e `version_info.txt` (`tests/test_version.py`).
- CI no GitHub Actions (`.github/workflows/tests.yml`): suíte de testes em Windows (Python 3.12 e 3.14) e lint com Ruff em Linux.
- Distribuição em dois binários na Release: instalador Inno Setup 6 por usuário (sem administrador, atalho no Menu Iniciar, desinstalador, atualizável por cima) e executável portátil, gerado pelo PyInstaller como arquivo único, sem console, com ícone e metadados de versão.
- Suíte de 345 testes com `unittest` (apenas stdlib, roda sem rede) cobrindo a leitura e validação da planilha, o plano de importação, o cliente HTTP, o provisionamento, a sessão, a verificação de atualizações, o download do instalador, as credenciais, os caminhos e partes da interface.
- Tema escuro na identidade do NetBox, fonte Inter, notificações toast e tela de carregamento com spinner.

### Alterado

- Relatórios e log de erros passam para `%LOCALAPPDATA%\ImportadorNetBox` quando a pasta ao lado do executável não é gravável.

[Não publicado]: https://github.com/lucasdaniel2201/netbox-device-importer/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lucasdaniel2201/netbox-device-importer/releases/tag/v1.0.0
