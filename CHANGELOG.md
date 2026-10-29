# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o [versionamento semântico](https://semver.org/lang/pt-BR/). A versão do aplicativo vive em três arquivos mantidos em sincronia: `app/version.py` (lido pelo Python), `instalador.iss` (lido pelo Inno Setup) e `version_info.txt` (lido pelo Windows). O teste `tests/test_version.py` falha se algum deles divergir dos outros dois.

## [1.1.0] - 2026-10-29

### Adicionado

- **Módulo de links IP**: uma parte própria do app para documentar o enlace de internet de cada site numa planilha só. Cada linha vira o prefixo do bloco público (escopo no site), o prefixo do bloco LAN, o `ipam.ip-address` do roteador na interface WAN e, **quando o device ainda não existir no site, o próprio device** — criando fabricante e device-type que faltarem.
- Planilha modelo de links (`modelo_links_netbox.xlsx`), com as colunas Site, Device, Bloco público, Interface, IP do link, Bloco LAN, Papel do prefixo, Adicionar ao Zabbix, Descrição e Fornecedor/chamado, e listas suspensas de Site e Papel alimentadas pelo NetBox.
- Validação de CIDR antes do envio: o bloco é normalizado para a rede (`...241/30` vira `...240/30`), o IP do link tem de pertencer ao bloco, rede/broadcast de /30 ou maior são recusados, e bloco ou IP repetido em duas linhas é erro nas duas.
- IP do link em branco é deduzido do bloco (primeiro utilizável em /30, o segundo endereço em /31), sempre com aviso no plano: nada é inventado em silêncio.
- Escrita idempotente do prefixo (`GET` por `prefix` → `POST`/`PATCH`), com o vínculo do site no formato da instância: `scope_type`/`scope_id` na 4.3+, `site` nas anteriores, decidido pelo `OPTIONS` do endpoint.
- Interface do link procurada **pelo nome** (`wan1` por padrão) e criada se faltar; `primary_ip4` só é definido quando o device ainda não tem um, para não trocar em silêncio o IP de gerência do roteador.
- Relatórios próprios da importação de links (`netbox-links-<data-hora>.log/.json/.csv`), com o `X-Request-ID` de cada escrita.
- Versão executável em Linux a partir do código-fonte (`tools/rodar_linux.sh`), para testar planilhas sem gerar o `.exe`: cria o `.venv`, instala as dependências e abre o app; `--testes` roda a suíte.
- Cofre do token com backend por plataforma: DPAPI no Windows, chaveiro do sistema (`keyring`) quando existir e, na falta dele, arquivo com permissão `0600`. A tela mostra qual proteção está em uso.

### Alterado

- Os testes de janela e de caminhos passam a rodar também no Linux (a suíte inteira roda lá; 429 testes).
- A pasta de dados do usuário segue o XDG no Linux (`$XDG_DATA_HOME` ou `~/.local/share/ImportadorNetBox`).

## [1.0.1] - 2026-09-28

### Alterado

- Publica a 1.0.1 para fechar o ciclo da verificação de atualizações: um app 1.0.0 instalado passa a avisar que existe a 1.0.1 e oferece o botão de baixar o instalador. Os binários da 1.0.0 foram gerados antes de a verificação de atualizações existir, então quem baixou a Release antiga não tinha o recurso.
- Atualiza a linha de copyright do `LICENSE` para o nome completo do autor.

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

[1.1.0]: https://github.com/lucasdaniel2201/netbox-device-importer/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/lucasdaniel2201/netbox-device-importer/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/lucasdaniel2201/netbox-device-importer/releases/tag/v1.0.0
