# Auditoria final da v2 (somente leitura) + correções aplicadas

> **Atualizado em 2026-10-26:** a auditoria abaixo (somente leitura) foi seguida das correções; veja a seção **"Correções aplicadas"** no final. As tabelas e evidências da auditoria foram mantidas como estavam na data.

Executada em 2026-10-26. **Nada foi alterado no projeto** além deste arquivo (conferido: nenhum arquivo modificado fora dele, nenhum `__pycache__` criado em `v2/`;
as execuções de teste rodaram numa **cópia** de `v2/` sem o `.env`, num venv em pasta temporária).
Antes de começar: nenhuma outra sessão, nenhum processo Python/wokwi/arduino rodando e nenhum arquivo do projeto alterado nos 30 minutos anteriores.
Nenhum valor de token aparece neste relatório (só máscaras).

## Tabela dos 17 itens

| # | Item | Status | Resumo |
|---|---|---|---|
| 1 | Varredura de tokens | **OK** | Telegram e Wokwi só em `v2/servidor/.env`. Histórico de shell **fora** do projeto não foi verificado (ver 16/17). |
| 2 | `.env` e `getMe` | **OK** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` e `WOKWI_CLI_TOKEN` presentes; `getMe` HTTP 200, `@AnimaAlertBot`. |
| 3 | `.gitignore` e zips | **PROBLEMA** | `.gitignore` OK, mas **`v2_para_equipe.zip` não existe mais**; não foi possível listá-lo. A regra de exclusão, simulada, está correta. |
| 4 | Telegram em segundo plano | **OK** | Thread + fila limitada + timeout; teste prova que a decisão não espera. |
| 5 | Intervalo por (dispositivo, causa, ação) | **OK** | Febre logo após agitado notifica; testes passam. |
| 6 | Testes de `alerta_leve` e intervalo (padrão 300 s) | **OK** | Existem e passam. |
| 7 | `relatorio_testes.md` consolidado | **PROBLEMA (menor)** | Sem "outra sessão" nem títulos duplicados; mas cita o zip (que não existe) e há referência cruzada quebrada em `teste_wokwi.md`. |
| 8 | Execução do zero (venv limpo) | **PROBLEMA** | Tudo passou (57 testes), mas **não existe `requirements.txt`** (a premissa do pedido). |
| 9 | Comandos do README / passo a passo | **PROBLEMA** | Funcionam como escritos, exceto: texto desatualizado do Telegram, armadilha do `--selftest` com modelo recalibrado e `executar.py` com caminhos fixos não documentado. |
| 10 | Pino GPIO 18 | **OK** | Só restam menções históricas ao GPIO 5; a Entrega 2 continua com `esp:5`. |
| 11 | Classes | **OK, com correção da premissa** | O modelo v2 tem **4 classes** (`agitado, febre, normal, parado`), não 3. Os docs estão corretos; "letárgico" só aparece como regra do servidor e na coluna da v1. |
| 12 | Tópicos e payload | **OK** | Campos, versão, tópicos e unidades idênticos em firmware, servidor, coletor, testes e docs. |
| 13 | Bibliotecas e recompilação | **OK, com risco** | As duas variantes compilam sem avisos do projeto. `libraries.txt` sem versões fixas e sem BusIO; compilação no editor web do Wokwi **não verificada**. |
| 14 | Arquivos para um projeto novo no Wokwi | **OK** | 4 arquivos completos em `v2/firmware/wokwi/`. |
| 15 | Entrega 2 intacta | **OK** | 20 arquivos sem diferença de tamanho/data. Limite: não existe hash de referência anterior. |
| 16 | Lacunas | ver seção abaixo | |
| 17 | Riscos de demonstração e plano B | ver seção abaixo | |

## Problemas, por ordem de gravidade (nada foi corrigido; abaixo, o que eu corrigiria)

| Gravidade | Problema | O que corrigiria |
|---|---|---|
| **MÉDIA-ALTA** | O servidor sem `--id` assina `anima/+/dados`. No broker público isso processa dados de terceiros, **publica decisões em tópicos de outras pessoas**, e qualquer um pode forjar payloads para disparar notificações no seu Telegram (cada `id` novo tem o seu próprio relógio de intervalo). O estado por dispositivo (`_est`) cresce sem limite. | Exigir `--id` (ou `--todos` explícito) quando o host for o broker público; limitar nº de dispositivos e/ou ignorar ids não autorizados (lista permitida); recomendar broker próprio com usuário/senha. |
| **MÉDIA** | `v2_para_equipe.zip` **sumiu** (a raiz foi modificada em 20/10 às 08:39, depois do último print). O entregável da equipe não existe. | Regenerar o zip (o script de geração existe só no meu diretório temporário; versionar um `empacotar.py` em `v2/`). |
| **MÉDIA** | Sem `requirements.txt`; o README manda `pip install` sem versões. O `.pkl` depende da versão exata do scikit-learn (hoje 1.9.1; funcionou porque `pip` trouxe a mesma). | `requirements.txt` com versões fixas (ao menos `scikit-learn==1.9.1`) e um `requirements-dev.txt` para o pytest. |
| **MÉDIA** | Armadilha do `--selftest`: com um modelo recalibrado (`offset_coleira -4`, exatamente o fluxo do passo a passo, seção 5) o selftest falha em 3 verificações, pois usa temperaturas da escala corporal (38,3 °C vira febre quando o limiar é 35,5). Além disso `treinar_modelo_v2.py` sobrescreve o modelo oficial usado pelos testes. | Fazer o selftest ler o `offset_coleira` do `.meta.json` (ou avisar e pular quando `offset != 0`); `treinar_modelo_v2.py` com `--sufixo` e aviso antes de sobrescrever. |
| **MÉDIA** | `teste_wokwi_cli/executar.py` usa caminhos fixos `C:\Users\Gabriel\...` (arduino-cli e wokwi-cli); há override por variável (`ANIMA_ARDUINO_DIR`, `WOKWI_CLI_EXE`), mas **nenhum doc explica** o executor, a instalação do arduino-cli/core/bibliotecas nem o token. | Documentar o passo a passo (instalar, variáveis, `WOKWI_CLI_TOKEN` no `.env`) e usar `shutil.which` antes dos caminhos fixos. |
| **MÉDIA** | `libraries.txt` do Wokwi sem versões e sem `Adafruit BusIO` (dependência do MPU6050). O Wokwi pode compilar com versões diferentes das testadas (core 3.3.12, MPU6050 2.2.9 etc.). A documentação do Wokwi suporta `Biblioteca@versão`, mas **não diz** se resolve dependências sozinho. | Fixar as versões testadas (`Adafruit MPU6050@2.2.9`, ...) e incluir `Adafruit BusIO@1.17.4`; compilar uma vez no editor web e registrar o resultado. |
| BAIXA | `docs/passo_a_passo.md` (linha 85) ainda diz que, durante as chamadas ao Telegram, "o servidor não processa outras mensagens" (verdade só antes do envio em segundo plano). | Reescrever: envio em segundo plano, decisão nunca espera. |
| BAIXA | `docs/teste_wokwi.md` (linha 3) remete a "relatorio_testes.md, seção 7"; a seção do Wokwi CLI agora é a **5**. | Corrigir a referência. |
| BAIXA | `docs/relatorio_testes.md` §7 diz que o zip "exclui .env, tokens..." sem o zip existir. | Reescrever após regenerar o zip, ou remover a frase. |
| BAIXA | IDs de exemplo compartilhados (`anima-grupoX-01` nos docs, `coleira01` no `config.h` do Wokwi): grupos que copiarem os docs colidem no broker público. | Gerar id aleatório por padrão no Wokwi/CLI e pedir um sufixo único. |
| BAIXA | O servidor não confere `id` do payload com o `id` do tópico (usa o do tópico). | Registrar aviso quando divergirem. |
| BAIXA | 3 `ResourceWarning` (arquivo/loop não fechados) nos testes com `-W default`. | Fechar o arquivo do log no coletor e o loop do mini-broker. |
| INFO | A premissa do pedido ("modelo com 3 classes") não bate: são 4 (`parado` incluída). Nenhum doc está errado por isso. | Nenhuma ação; só atualizar quem usa o "3 classes" como referência. |

## Evidências por item

### 1) Varredura de segredos
Padrões: token de bot do Telegram (`dígitos:35+ caracteres`) e `wok_…`. Lidos 2.450 arquivos: o projeto inteiro, o conteúdo interno de `.docx`/`.zip`, `__pycache__`
(não há mais nenhum) e as pastas temporárias dos testes. Resultado, só caminho e contagem:
```
[telegram] v2\servidor\.env  (1 ocorrência)
[wokwi]    v2\servidor\.env  (1 ocorrência)
```
Nenhum arquivo `*history*`/`ConsoleHost_history.txt` dentro do projeto. **Não verificado de propósito:** o histórico do PowerShell/PSReadLine do usuário
(`%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt`) fica fora do projeto; se você digitou `$env:WOKWI_CLI_TOKEN="..."` no terminal, o valor pode estar lá. Vale conferir e limpar.
O primeiro token do Wokwi (colado no chat) deveria ter sido revogado; **não consigo verificar** se foi.

### 2) `.env` e `getMe`
```
.env existe: True | 158 bytes | chaves: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WOKWI_CLI_TOKEN
TELEGRAM_BOT_TOKEN: <46 car., termina …sSM> formato ok | TELEGRAM_CHAT_ID: definido (10 car.) | WOKWI_CLI_TOKEN: <44 car., termina …e17> formato ok
getMe: HTTP 200 | username: @AnimaAlertBot
```

### 3) `.gitignore` e zip
`.gitignore` (raiz): `.env`, `.env.*`, `**/.env`, `BotFather - token.txt`, `*token*.txt`. `v2/.gitignore`: `.env`, `.env.*`, `!.env.example`, `**/.env`, `*token*.txt`.
Arquivos `*token*` ou `.env` no disco do projeto: só `v2/.env.example` (modelo, sem valores) e `v2/servidor/.env`. A pasta **não é um repositório git**.
`v2_para_equipe.zip`: **inexistente** (`find . -name "*.zip"` não acha nenhum). Simulação em memória da regra de empacotamento (nada gravado):
60 arquivos entrariam, 1 excluído (`v2/servidor/.env`), nenhum dos incluídos tem padrão de token. Falta regenerar o zip para confirmar o conteúdo real.

### 4) Telegram em segundo plano
`servidor/anima_core.py`: `class NotificadorAssincrono` (linha ~300) com `threading.Thread(... daemon=True)`, `collections.deque`, `tamanho_fila` (padrão 20) que faz `popleft()`
do mais antigo quando cheia; o HTTP usa `timeout=(4, 6)` (linha 252). `Pipeline.processar` só chama `self.notificador.enviar(...)`, que enfileira (O(1)).
`consumidor_v2.py`: `NotificadorAssincrono(...)` na linha 107 e `notificador.encerrar(timeout=5.0)` no `finally` do Ctrl+C.
Prova (venv limpo): `test_telegram_lento_nao_atrasa_a_decisao` — 6 alertas com um Telegram que trava (até 8 s) retornam em < 1,5 s, depois as 6 mensagens são entregues. PASSED.
Complementares, todos PASSED: erro/401 sem vazar token, fila cheia (descarta as mais antigas), encerramento limpo e respeitando prazo, Ctrl+C real do processo.

### 5) Intervalo por causa
`Debounce`: `chave = (causa, acao_bruta)`; `causa_do_alerta()` devolve `temperatura_alta` (regra de segurança ou classe febre), `agitado` ou `letargia`.
`test_febre_logo_depois_de_agitacao_notifica_de_novo` (2 notificações: agitado e febre; a mesma causa repetida e o agitado repetido ficam limitados) e
`test_debounce_chave_por_causa_e_acao`: PASSED.

### 6) `alerta_leve` e intervalo configurável
`test_alerta_leve_chega_ao_telegram` (imobilidade prolongada → `alerta_leve` no Telegram com "Alerta leve"), `test_mesma_causa_repetida_e_limitada_pelo_intervalo` (intervalo curto de 2 s com relógio falso),
`test_intervalo_minimo_configuravel_e_padrao_300` (`Debounce().intervalo == 300.0` e o padrão de `--intervalo-notif` == 300): PASSED. Há também `alerta_leve` em `test_decisao_e_debounce.py`.

### 7) Relatório consolidado
`relatorio_testes.md`: 205 linhas, seções 1–9 sem títulos duplicados; nenhuma menção a "outra sessão", "fork" ou `relatorio_telegram` em `v2/` (o arquivo antigo foi removido); pendências na seção 9.
Problemas: §7 cita o zip; `teste_wokwi.md` aponta "seção 7" (agora é a 5).

### 8) Execução do zero
Cópia de `v2/` sem `.env`/caches em pasta temporária; venv novo; instalado **só** o que o README manda
(`pip install paho-mqtt scikit-learn pandas numpy joblib matplotlib requests pytest`; não há `requirements.txt` em `v2/` nem em `servidor/`/`ia/`).
Versões resolvidas: scikit-learn 1.9.1, numpy 2.5.4, pandas 3.1.0, scipy 1.18.1, matplotlib 3.11.2, paho-mqtt 2.1.0, pytest 9.1.1.
```
consumidor_v2.py --selftest   -> "OK: tudo certo." (exit 0)
coletar_dados.py --selftest   -> "Selftest do coletor: OK" (exit 0)
pytest tests -q               -> 57 passed, 3 warnings   (ResourceWarning de arquivo/loop não fechados; nenhum de versão)
tests/cenarios_e2e.py         -> 17/17 verificações ok (exit 0)
carregar o .pkl com -W error  -> sem InconsistentVersionWarning (modelo treinado com a mesma 1.9.1)
```
Observação: o aviso de versão do scikit-learn **não aconteceu porque o pip trouxe a mesma versão do treino**. Com versão diferente no futuro, o `.pkl` pode avisar ou falhar.

### 9) Comandos dos docs
Executados na cópia, na pasta de partida indicada, com o `python` do venv:
* README: `gerar_dataset_v2.py` (2400 janelas), `treinar_modelo_v2.py` (acurácia 0,9396; parado+40,1 °C → febre 0,93), `consumidor_v2.py --selftest`, `pytest` (57): **ok**.
* passo a passo: `gerar_wokwi.py` e `--check`, `consumidor_v2.py --selftest`, `coletar_dados.py --help`, `gerar_dataset_v2.py --offset-coleira -4`,
  `retreinar.py --real ../servidor/dados_reais/*.csv --offset-coleira -4 --peso-real 3` (com CSV real **fabricado**; gerou `modelo_anima_rf_v2_real.pkl`), pytest: **ok**.
* **Não executados** (exigem broker/hardware/token): `consumidor_v2.py --id ...`, `coletar_dados.py` de verdade, o teste real do Telegram, `executar.py` (token/arduino-cli). Também **não executei** `consumidor_v2.py --id anima-grupoX-01` por ser um id de exemplo compartilhado no broker público.
* **Quebrado/desatualizado:**
  * `consumidor_v2.py --modelo ../ia/modelo_anima_rf_v2_real.pkl --selftest` (passo 3 da seção 5 com um modelo de offset -4): **3 FALHA(S)** (parado 38,3 °C → sem alerta; parado+40,1 °C; leitura isolada). Causa: o selftest usa a escala corporal e o limiar do modelo virou 35,5 °C (`temp_seguranca_coleira`).
  * `passo_a_passo.md:85`: "durante elas o servidor não processa outras mensagens" — desatualizado.
  * `executar.py` e o fluxo do Wokwi CLI não estão no passo a passo.
  * `copy .env.example .env` (passo 0) cria `v2/.env`; o servidor lê `v2/.env` **e** `v2/servidor/.env`, e os demais docs falam de `servidor/.env`; funciona, mas é inconsistente.

### 10) Pino do atuador
`PINO_ATUADOR 18` em `anima_esp32_v2/config.h` e `wokwi/config.h`; `esp:18` (2 conexões) em `firmware/wokwi/diagram.json` e `teste_wokwi_cli/diagram.json` (idênticos); `GPIO 18` em README, `hardware.md`, `passo_a_passo.md`, `teste_wokwi.md` e no teste `test_atuador_em_pino_seguro_gpio18`.
Menções restantes a GPIO 5 (todas **históricas/explicativas**): `hardware.md:42` e `config.h:62` (por que foi trocado), `gerar_wokwi.py` (a troca `esp:5`→`esp:18`), `base_entrega2/LEIA-ME.txt`, o teste que protege o original e `relatorio_testes.md`.
`base_entrega2/diagram.json` e `entregas_anteriores/diagram.json` têm `esp:5` e são idênticos (cmp).

### 11) Classes
`features_v2.CLASSES = ["agitado","febre","normal","parado"]` e `modelo.classes_` confirmam **4 classes**. Menções a "letárgico": `comparacao_v1_v2.md` e `comparar_v1_v2.py` (coluna da v1),
`hardware.md`/README/`passo_a_passo.md`/`relatorio_testes.md`/`anima_core.py`/testes (regra opcional `--parado-letargia`, desligada por padrão). Nenhum diz que o modelo v2 prevê "letárgico".

### 12) Tópicos e payload
Chaves do JSON no `.ino` == `FEATURES` + `versao,id,n_amostras,sensor_ok,mpu_ok` (diferença: nada); `"versao":2` no firmware e `VERSAO_PAYLOAD = 2`; o servidor valida `versao`, `mpu_ok`, `sensor_ok`, `n_amostras`.
Tópicos `anima/%s/dados|decisao` (firmware), `anima/<id>/...` (servidor, coletor, README), `anima/{ID}/...` (testes). Tópicos antigos da v1 (`anima/dados`, `anima/decisao`): nenhum uso. Unidades: README e firmware citam `°/s` e `m/s²`; o `57.2958` aparece só no firmware.

### 13) Bibliotecas e compilação
`#include` do `.ino`: Wire, WiFi (core), PubSubClient, Adafruit_MPU6050, Adafruit_Sensor, OneWire, DallasTemperature, math.h. `libraries.txt` do Wokwi: Adafruit MPU6050, Adafruit Unified Sensor, OneWire, DallasTemperature, PubSubClient (**idêntico ao da Entrega 2**). Casam.
Instaladas na compilação: MPU6050 2.2.9, Unified Sensor 1.1.15, BusIO 1.17.4, OneWire 2.3.8, DallasTemperature 4.0.6, PubSubClient 2.8; core esp32 3.3.12.
```
arduino-cli compile --fqbn esp32:esp32:esp32 --warnings all   (cópias em pasta temporária)
Hardware: exit 0 | Sketch 936.896 B (71% de 1.310.720) | RAM 48.928 B (14% de 327.680) | avisos em arquivos do projeto: nenhum (4 avisos, todos da biblioteca OneWire)
Wokwi:    exit 0 | Sketch 936.880 B (71%)                | RAM 48.928 B (14%)                | avisos em arquivos do projeto: nenhum
```

### 14) Arquivos para um projeto novo no Wokwi (`v2/firmware/wokwi/`)
`sketch.ino` (13.252 B), `config.h` (3.381 B; 1ª linha `#define ANIMA_WOKWI 1`), `diagram.json` (1.685 B; JSON válido, 7 peças, todas as conexões referenciam peças existentes; buzzer/LED em `esp:18`, MPU em 21/22, DS18B20 no 4),
`libraries.txt` (80 B). Não há `config_local.h` (opcional via `__has_include`). Atenção: `ANIMA_ID` padrão é `coleira01`; trocar por um id único.
Para o CLI há ainda `v2/teste_wokwi_cli/` (`wokwi.toml`, `diagram.json`, 5 cenários YAML, `executar.py`). **Nesta auditoria o Wokwi CLI não foi reexecutado.**

### 15) Entrega 2 intacta
Os 20 arquivos de `entregas_anteriores/` comparados com a listagem original (tamanho + data), mais `anima_esp32/anima_esp32.ino` (28/09, 6.757 B) e `sketch/sketch.ino` (05/10, 6.839 B): **nenhuma diferença**.
`modelo_anima_rf.pkl`, `diagram.json` e `libraries.txt` têm hash igual ao das cópias em `v2/`. **Limite:** só existia referência de tamanho/data (não há hash antigo dos originais); os arquivos foram
**movidos** de pasta a pedido (de `Anima/` para `Anima/entregas_anteriores/`), sem alteração de conteúdo. O `.docx` da Entrega 2 não está mais na raiz.

## 16) O que NÃO está coberto por nenhum teste
* Hardware real (placa, I2C, DS18B20 real, buzzer, consumo, bateria) e dados reais de animais (modelo, limiares e `offset_coleira` são sintéticos).
* TLS e autenticação MQTT (o código existe, nunca exercitado).
* Reconexão **do dispositivo** (só a do servidor foi testada).
* Fail-safe de 15 s do alerta sem servidor; padrão de pisca do buzzer (só o nível estático do GPIO 18); `alerta_leve` no firmware.
* MPU ausente (`mpu_ok:false`) e DS18B20 desconectado (-127) **no firmware** (só o servidor foi testado com esses payloads).
* Backoff de Wi-Fi/MQTT com a rede caída.
* Envio real ao Telegram pelo caminho assíncrono (só `getMe` e os modos de falha; o envio real foi testado com a versão síncrona); limites de taxa e grupos.
* Latência com carga (só 11 amostras por execução, sem carga); muitos dispositivos simultâneos; perda de mensagens durante quedas.
* Compilação no **editor web** do Wokwi e as versões de biblioteca de lá.
* Os cenários do Wokwi CLI não foram reexecutados nesta auditoria (o último resultado é de 20/10).

**Depende de teste manual no site do Wokwi (`docs/teste_wokwi.md`):** fail-safe de 15 s (linha 7), DS18B20 desconectado (9), MPU ausente e religado (10–11), rede caída (13) e ver o buzzer/LED piscar.

## 17) Riscos de demonstração ao vivo e plano B

| Risco | Plano B |
|---|---|
| Internet/Wi-Fi da sala instável ou bloqueando a porta 1883 | Hotspot do celular; ou rodar tudo **local**: broker Mosquitto no notebook + `ANIMA_MQTT_HOST=127.0.0.1`; no Wokwi, o Private Gateway (plano pago) só se necessário; último recurso: vídeo gravado dos 5 cenários. |
| `broker.hivemq.com` fora do ar ou lento (latência ~410–630 ms medida) | Broker local (Mosquitto) ou outro público; ter o host em variável de ambiente (`ANIMA_MQTT_HOST`) e no `config_local.h`; mostrar o `--selftest` e o `cenarios_e2e.py` (mini-broker, sem rede). |
| Terceiros no broker público (colisão de id, payloads forjados, decisões no tópico da coleira) | Usar id único aleatório, **sempre `--id`**, e broker próprio com senha para a demonstração final. |
| Telegram lento/bloqueado (já não trava o servidor) | A decisão e o buzzer funcionam sem ele; deixar o terminal visível (`[NOTIFICAÇÃO]` sai sempre), ter o celular com dados móveis, ou demonstrar com `TELEGRAM_BOT_TOKEN` vazio ("só terminal"). Testar o bot minutos antes (`getMe`). |
| Token do Telegram/Wokwi inválido ou revogado na hora | Conferir `getMe` antes; ter o token de reserva no `.env` (nunca em slide/print); o CLI do Wokwi tem limite do plano grátis (50 min/30 dias): rodar só o cenário necessário. |
| Wokwi web com biblioteca de versão diferente / simulador lento | Ensaiar o projeto no editor web antes; fixar versões no `libraries.txt`; usar o CLI/vídeo como plano B. |
| Modelo/scikit-learn diferente na máquina da apresentação | Usar a **mesma** máquina/venv do ensaio; fixar versões em `requirements.txt`; levar o `.pkl` e o relatório. |
| Hardware (se levado): I2C/DS18B20 mal conectados, buzzer sem transistor, bateria | Ensaiar em bancada; levar fonte USB; mostrar o Wokwi como alternativa se algo falhar. |

---

## Correções aplicadas (2026-10-26)

Antes de começar: nenhuma outra sessão, nenhum processo e nenhum arquivo alterado nos 30 minutos anteriores. A Entrega 2 não foi tocada (as cópias em `base_entrega2/` e `v1_referencia/` são somente leitura).

| # | Item da auditoria | Status | Como foi corrigido | Como foi verificado |
|---|---|---|---|---|
| 1 | Servidor sem `--id` assinava `anima/+/dados` no broker público | **CORRIGIDO** | `--id` obrigatório; `--todos` explícito; em broker público (lista de hosts conhecidos) `--todos` exige `--aceito-risco-publico`; `"id"` do payload tem de ser igual ao do tópico (também no coletor); `--max-dispositivos` (padrão 20) e estado de debounce limitado (descarta o mais antigo, 16 relógios por dispositivo, 1000 dispositivos) | 15 testes novos em `test_seguranca_servidor.py` (cada modo, CLI com código 2, id forjado, limites, **ponta a ponta com mini-broker**: 3º dispositivo ignorado e id forjado ignorado) + selftest |
| 2 | Sem `requirements.txt` | **CORRIGIDO** | `servidor/requirements.txt` (paho-mqtt 2.1.0, scikit-learn 1.9.1, numpy 2.5.4, scipy 1.18.1, pandas 3.1.0, joblib 1.6.0, requests 2.34.2), `ia/requirements.txt` (+ matplotlib 3.11.2), `servidor/requirements-dev.txt` (+ pytest 9.1.1, pyyaml 6.0.3); README e passo a passo usam `pip install -r` | venv novo: `pip install -r v2/servidor/requirements-dev.txt` → `pip check`: sem conflitos; selftests, `cenarios_e2e` 17/17, pytest todos passaram; `.pkl` carregou com `-W error` sem aviso de versão |
| 3a | `--selftest` quebrava com offset diferente de 0 | **CORRIGIDO** | o selftest lê `offset_coleira` do `.meta.json` do modelo e aplica aos cenários | testes: modelo recalibrado (offset -4) passa; o mesmo modelo com o offset zerado no meta **falha** (contraste); modelo oficial continua passando |
| 3b | O treino sobrescrevia o modelo oficial sem avisar | **CORRIGIDO** | `treinar_modelo_v2.py` ganhou `--saida-dir`, `--sufixo`, `--sim`; `confirmar_sobrescrita` pergunta (ou recusa sem terminal; stdin vazio no Windows tratado); `retreinar.py --sufixo v2` idem | testes (todos os caminhos da guarda) e execução real: sem `--sim` recusa e o **hash do modelo oficial permanece igual** |
| 4 | Zip da equipe sumiu | **CORRIGIDO** | `v2/empacotar.py` (exclusões + varredura de padrões de token no conteúdo; aborta se achar; confere o zip gravado); zip regenerado | 4 testes (árvore falsa com segredos, vazamento aborta sem imprimir valor, `--listar`, simulação no v2 real); zip gerado e listado (72 arquivos, sem `.env`/token/log/cache/build) |
| 5 | `executar.py` com caminhos fixos | **CORRIGIDO** | ferramentas por `--arduino-cli/--wokwi-cli/--arduino-dir`, `ANIMA_ARDUINO_CLI`/`WOKWI_CLI_EXE`/`ANIMA_ARDUINO_DIR` ou PATH; token **só** do ambiente (nunca de arquivo); falha antes de compilar se faltar token/ferramenta; guia novo `docs/wokwi_cli.md` | 8 testes estáticos (sem caminhos de usuário no código, nenhuma leitura de arquivo para o token, precedência das ferramentas, `--help` sem nada, recusa sem token sem compilar, YAML). **O CLI não foi executado** (sem token) |
| 6 | `libraries.txt` sem versões e sem BusIO | **CORRIGIDO (parte local)** | `firmware/libraries_wokwi.txt` (fonte própria da v2) com as versões da compilação local + `Adafruit BusIO@1.17.4`; `gerar_wokwi.py` passou a usá-lo; a cópia da Entrega 2 não mudou | teste estático (versões fixas, cobre os `#include`, BusIO presente, cópia da Entrega 2 intacta); versões conferidas com `arduino-cli lib list` e o Library Manager. **Compilação no editor web do Wokwi: NÃO VERIFICADA** (item 14 do `teste_wokwi.md`) |
| 7a | Passo a passo dizia que o servidor não processa durante o Telegram | **CORRIGIDO** | texto reescrito (segundo plano, decisão nunca espera) | revisão do texto + os testes do Telegram em segundo plano |
| 7b | Referência cruzada quebrada em `teste_wokwi.md` | **CORRIGIDO** | aponta para a seção 5 do relatório e para `wokwi_cli.md` | `grep` |
| 7c | Ids de exemplo compartilhados | **CORRIGIDO** | docs usam `<SEU_ID>` e mostram como gerar; o firmware tem o padrão `anima-TROQUE-ESTE-ID` e emite `#warning` se não for trocado; exemplos do README/coletor/.ino sem `coleira01`/`grupoX` | `grep` sem resquícios; compilação de hardware mostra o `#warning` (único aviso do projeto) |
| 7d | `ResourceWarning` nos testes | **CORRIGIDO** | loop do mini-broker e pipes dos subprocessos fechados | `pytest -W default`: 91 passed, **nenhum aviso**; `cenarios_e2e.py -W default` limpo |
| 7e | README: tabela "O que foi testado" quebrada; `.env.example` mandava pôr o token do Wokwi no `.env` | **CORRIGIDO** | tabela refeita; `.env.example` agora diz que o token do Wokwi **não** vai em arquivo | leitura |
| 8 | Esta seção e o relatório | **FEITO** | `relatorio_testes.md` atualizado (contagens, compilação, token, zip, pendências) | — |

### Verificações finais desta rodada
```
pytest (v2, -W default)                          -> 91 passed, sem avisos
venv limpo (requirements-dev.txt): pytest        -> 91 passed (o teste dos YAML roda com pyyaml); selftests ok; cenarios_e2e 17/17
arduino-cli compile (hardware, --warnings all)   -> exit 0 | 936.912 B (71%) flash | 48.928 B (14%) RAM | 1 aviso do projeto: o #warning intencional do ANIMA_ID
```
A variante **Wokwi** não foi recompilada nesta rodada (opção de menor custo escolhida; ela difere da de hardware só pela linha `#define ANIMA_WOKWI 1` e pelo comentário do `.ino`).

### Ações que continuam com você
1. **Apague a linha `WOKWI_CLI_TOKEN=...` do `v2/servidor/.env`** (o `executar.py` não a lê mais; token só em variável de ambiente). Se o token já foi colado em chat/terminal, revogue-o.
2. Conferir/limpar o histórico do PowerShell (`%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt`) por linhas com `TOKEN`.
3. Compilar a variante Wokwi no **editor web** do Wokwi uma vez e registrar o resultado (item 14 do `teste_wokwi.md`).
4. Reexecutar os 5 cenários do Wokwi CLI com o novo `executar.py` quando tiver o token no ambiente.

### O que continua SEM teste (inalterado)
Hardware real e dados reais de animais; TLS e autenticação MQTT; reconexão **do dispositivo**; fail-safe de 15 s; padrão de pisca do buzzer e `alerta_leve` no firmware; MPU ausente e -127 no firmware;
backoff de Wi-Fi/MQTT com a rede caída; envio real ao Telegram pelo caminho assíncrono (só `getMe` e modos de falha); latência sob carga; compilação no editor web do Wokwi; e, **desta rodada**,
a execução do novo `executar.py` e do `libraries.txt` versionado no Wokwi (só validação estática).
