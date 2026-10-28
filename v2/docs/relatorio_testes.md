# Relatório de testes da v2

Testes **executados** em 2026-10-19, 2026-10-20 e 2026-10-26 (correções da auditoria) (Windows 11, Python 3.14.6, scikit-learn 1.9.1, paho-mqtt 2.1.0, arduino-cli 1.5.2-rc.1,
core esp32:esp32 3.3.12, wokwi-cli 0.29.0). Modelo e dados são **sintéticos**; nenhum teste usou hardware real nem animais.
O que não aparece aqui como "passou" não foi testado (lista completa na seção 9).

## 1. Resumo

| # | Item | Status |
|---|---|---|
| 2 | `pytest tests` (**91 testes**, também em venv limpo a partir dos `requirements-dev.txt`), selftests, cenários de referência, dispositivo simulado × servidor (17 verificações), coletor + retreino | passou |
| 3 | Compilação (ESP32 Dev Module). Em 2026-10-26 só a variante de **hardware** foi recompilada (o `config.h` mudou); a de Wokwi, que difere só por uma linha, **não** foi recompilada depois | passou |
| 4 | Servidor × **broker público real** (HiveMQ): 20 verificações, reconexão | passou (2 execuções) |
| 5 | Firmware no **Wokwi via CLI**: 5 cenários | passou; **reexecutado depois das mudanças do servidor (seção 6)**, todos passaram |
| 6.1 | Telegram **real**: 3 mensagens recebidas no celular (confirmado pelo dono do projeto) | passou (com a versão síncrona do envio) |
| 6.2 | Telegram: falhas (token inválido, chat errado, sem internet) com o envio em segundo plano, no servidor real | passou |
| 6.3 | Telegram em segundo plano: lento (8 s), erro, fila cheia, encerramento limpo | passou (testes automáticos) |
| 6.4 | Intervalo entre notificações por (dispositivo, causa, ação); `alerta_leve` no Telegram; padrão real de 300 s | passou |
| 7 | Varredura de segredos | limpa (re-executada na auditoria de 2026-10-26) |
| 10 | Correções da auditoria (segurança do servidor, requirements, selftest/treino, empacotar.py, executar.py portável, libraries.txt, docs) | aplicadas e testadas; ver seção 10 e `auditoria_final.md` |
| — | Envio **real** ao Telegram pelo caminho novo (assíncrono) | **não testado** (só `getMe` e os modos de falha) |

## 2. Software local

```
python servidor/consumidor_v2.py --selftest      -> "OK: tudo certo."
python servidor/coletar_dados.py --selftest      -> "Selftest do coletor: OK"
python -m pytest servidor/tests -q               -> 91 passed (nenhum aviso com -W default)
python servidor/tests/cenarios_e2e.py            -> 17/17 verificações ok
python firmware/gerar_wokwi.py --check           -> wokwi/ sincronizado.
```

**Testes pytest por arquivo (91):** regra de decisão, debounce e notificador (18); features e descarte (12); modelo v2 real (4);
análise estática do firmware/Wokwi, incluindo GPIO 18 e versões do `libraries.txt` (8); ponta a ponta com processos reais e mini-broker (2);
encerramento limpo com Ctrl+C simulado (1); Telegram em segundo plano, intervalo por causa, `alerta_leve`, isolamento do `.env` (13);
**segurança do servidor** (15); **selftest com offset e guarda do treino** (6); **empacotar.py** (4); **executar.py estático** (8).
A análise estática do firmware **não é execução**.

### 2.1 Cenários de referência (modelos reais)

| Modelo | Entrada | Resultado |
|---|---|---|
| v1 | accel 0/0/9,81, **rotação 0/0/0**, 40,1 °C | `letargico` 46,5% × `febre` 45,5% → **empate; a v1 falha em parado + febre** |
| v2 | parado + 40,1 °C | `febre` 93% |
| v2 + servidor | 2 janelas consecutivas | 1ª: `acao=nenhum` (debounce); 2ª: `acao=alerta`, publicada em `anima/<id>/decisao` |

### 2.2 Dispositivo simulado × servidor (mini-broker local)

`servidor/tests/cenarios_e2e.py`: mini-broker + `consumidor_v2.py` real (`--intervalo-notif 3`) + dispositivo **simulado em Python** (não é o firmware).

| Cenário | Esperado = Obtido |
|---|---|
| parado 38,3 °C / normal 38,5 °C | nenhum — parado (0,97) / normal (0,947) |
| agitado 38,8 °C, 1ª / 2ª janela | nenhum → alerta (0,978) |
| febre com movimento 40,0 °C, 1ª / 2ª | nenhum → alerta (0,946) |
| **parado + febre 40,1 °C**, 1ª / 2ª / 3ª | nenhum → alerta → alerta (0,93) |
| DS18B20 = -127, `sensor_ok=false`, `mpu_ok=false` | sem decisão publicada |
| alerta dentro / após o intervalo de 3 s | 0 / 1 notificação |
| log CSV: descartadas / notificações | 3 / 3 |

As 3 notificações do roteiro são: agitado, febre (**causa diferente**, notifica na hora) e a do fim, após o intervalo. O parado+febre logo
depois da febre (mesma causa, dentro de 3 s) é suprimido (ver 6.4).

### 2.3 Coletor + retreino

Duas sessões simuladas (`parado`, `normal`; 26 payloads cada, um deles -127; `--max-janelas 20`): 20 janelas gravadas, 1 descartada, 3 iniciais ignoradas
por sessão. O CSV real tem todas as colunas do dataset v2 (7 variáveis, `classe`, `origem`) mais metadados (`timestamp, sessao_id, id_dispositivo, animal, observacoes`).
`retreinar.py --real parado.csv normal.csv --sufixo teste_coleta --saida-dir <temp>`: 40 reais + 2400 sintéticos, acurácia 0,957 (origem=real: n=11, 1,0 —
**sem significado estatístico**, amostra fabricada). O modelo oficial ficou intacto (sha1 idêntico) e nada foi escrito em `ia/`.

## 3. Compilação (arduino-cli)

Instalação isolada em `C:\Users\Gabriel\arduino-cli-anima`: core `esp32:esp32` 3.3.12; Adafruit MPU6050 2.2.9, Adafruit Unified Sensor 1.1.15 (+ BusIO 1.17.4),
OneWire 2.3.8, DallasTemperature 4.0.6, PubSubClient 2.8. ArduinoJson **não é usada**.

```
arduino-cli compile --fqbn esp32:esp32:esp32 --warnings all <pasta>
```

| Variante | Flash | RAM (globais) | Erros | Avisos em arquivos do projeto |
|---|---|---|---|---|
| Hardware (`anima_esp32_v2`, buzzer/LED no GPIO 18), 2026-10-26 | 936.912 B (71%) | 48.928 B (14%) | 0 | 1, **intencional**: `#warning` do `ANIMA_ID` padrão (só aparece sem `config_local.h`) |
| Wokwi (`sketch.ino` + `config.h` gerados), 2026-10-19/20 (**não recompilada** em 10-26) | 936.880 B (71%) | 48.928 B (14%) | 0 | 0 |

Os avisos com `--warnings all` vêm da biblioteca **OneWire**, fora do nosso código.

**`gerar_wokwi.py` sem divergência**, por `diff`: `sketch.ino` idêntico; `config.h` com apenas a linha `#define ANIMA_WOKWI 1` (SSID `Wokwi-GUEST`, senha vazia e
canal 6 saem dos blocos `#ifdef ANIMA_WOKWI` do próprio `config.h`); `diagram.json` difere do da Entrega 2 só em `esp:5` → `esp:18` (2 linhas); `libraries.txt` agora vem de `firmware/libraries_wokwi.txt` (versões fixadas + Adafruit BusIO); a cópia da Entrega 2 em `base_entrega2/` segue intocada.

## 4. Broker público real (broker.hivemq.com:1883)

> **ALERTA:** o HiveMQ público é aberto, **sem autenticação e sem TLS**. Qualquer pessoa pode ler e publicar em qualquer tópico; os tópicos de
> teste (`anima/anima-teste-xxxxxx/...`) poderiam ser lidos ou forjados por terceiros durante o teste. Só dados sintéticos, ID aleatório, **sem Telegram**
> (os testes não carregam o `.env`). O servidor assinou só o tópico do ID de teste, nunca `anima/+/dados`.

```
python servidor/tests/teste_broker_publico.py        -> 20/20 verificações ok (exit 0), executado 2 vezes (todas passaram nas duas)
```
O servidor (processo real) conecta ao broker real **por um proxy TCP local** que o script derruba; dispositivo simulado e ouvinte conectam direto, QoS 1.

| Cenário | Esperado = Obtido | Latência (2ª execução) |
|---|---|---|
| parado, normal, agitado (1ª/2ª), volta ao normal, febre com movimento (1ª/2ª), parado+febre (1ª/2ª/3ª) | classe e ação como na tabela 2.2 | 411–579 ms |
| -127, `sensor_ok=false`, `mpu_ok=false` | sem decisão publicada | - |
| alerta com intervalo vencido / dentro de 3 s / após 3,2 s | 1 / 0 / 1 notificação | - |
| **queda de conexão do servidor** | reconecta e volta a processar | reconexão em **1,4 s** (1ª execução) e **3,2 s** (2ª) |
| log CSV | 18 linhas, 3 descartadas, só o ID de teste | - |

**Latência ida e volta** (dispositivo → broker real → servidor → broker real → ouvinte): 1ª execução mediana **433 ms** (mín 420, máx 631); 2ª execução
mediana **414 ms** (mín 411, máx 579). Varia com a rede e com a carga do broker público. Mensagens publicadas **durante** a queda do servidor são perdidas (QoS 0); o teste só publicou depois.

## 5. Wokwi via CLI (`teste_wokwi_cli/`)

**Instalação:** `wokwi-cli` 0.29.0 do release oficial do GitHub (46,7 MB, sem assinatura digital) em `C:\Users\Gabriel\wokwi-cli-anima`, **sem alterar o PATH**.
**Token:** o CLI exige `WOKWI_CLI_TOKEN` (sem ele: `Missing WOKWI_CLI_TOKEN`, exit 1). **Mudança de 2026-10-26:** o `executar.py` agora lê o token **somente da variável de ambiente**,
nunca de arquivo (nem do `.env`), e nunca o imprime. Os resultados abaixo (2026-10-20) foram obtidos com a versão anterior do script, que também aceitava o `.env`; o novo `executar.py`
(argumentos/variáveis para as ferramentas, sem caminhos fixos) foi validado **só estaticamente** e a parte de execução **não foi reexecutada** (sem token no ambiente). Guia: `docs/wokwi_cli.md`.
O 1º token foi colado no chat; **recomenda-se revogá-lo** em wokwi.com/dashboard/ci. A reexecução usou um token novo.

`python teste_wokwi_cli/executar.py` compila a variante Wokwi com um `ANIMA_ID` aleatório (via `config_local.h` em pasta temporária), copia `build/firmware.bin|elf`,
roda os cenários e confere os números do log serial. O servidor do cenário 05 roda sem carregar o `.env`.

| # | Cenário | Resultado | Relógio |
|---|---|---|---|
| 01 | Boot: `MPU6050 conectado.`, `"versao":2`, `"mpu_ok":true`, `"sensor_ok":true`, GPIO 18 = 0 em repouso; `n_amostras` 40–55, accel 9,807 m/s², gyro 0, temperatura 38,50 | passou | 45 s |
| 02 | `Wi-Fi conectado. IP: 10.13.37.2`; MQTT conectado; o ouvinte no broker **real** recebeu 3 payloads | passou | 38 s |
| 03 | `set-control` DS18B20 → 40,1 °C: **GPIO 18 = 1** (proteção local); volta a 38,5 °C: **GPIO 18 = 0** | passou | 61 s |
| 04 | `set-control` MPU6050: accelZ = 2 g, rotationX = 100 °/s → accel ≈ 19,62 e gyro ≈ 100, **em °/s** | passou | 45 s |
| 05 | Laço: Wokwi → broker real → `consumidor_v2.py` real → decisão no ESP32 simulado (`nenhum`, depois `alerta` com febre 40,1 °C) | passou | 46 s |

1. `set-control` funciona no DS18B20 (`temp1`/`temperature`) e no MPU6050. Limitação: o DS18B20 aceita -55…125 °C, então **-127 não dá para simular** por `set-control`.
2. A rede `Wokwi-GUEST` dá internet no CLI. 3. O MQTT chega ao broker real.

**Reexecução (2026-10-20, depois das mudanças do servidor):** 01 passou (6 verificações numéricas); 02 (3 payloads no broker real), 03 (GPIO 18 = 1 a 40,1 °C e = 0 a 38,5 °C), 04 (accel 19,613 m/s², gyro 100,000 °/s) e 05 (decisões `nenhum` e `alerta` recebidas do servidor novo, 3 linhas no log) passaram. Relógio por cenário: 32–42 s.
Na 1ª tentativa dessa rodada, todos deram `API Error: Unauthorized`: o valor no `.env` era a linha inteira do PowerShell (`$env:WOKWI_CLI_TOKEN="wok_..."`) em vez do token puro; corrigido o `.env` (o código estava certo).

Uso do plano grátis: ≈ 4 min de relógio nos 5 cenários (por rodada), mais uma rodada de 110 s que deu timeout por **erro do meu YAML** (ordem das mensagens do serial), corrigido.
No Wokwi os valores do MPU são constantes (desvio ≈ 0): `normal`/`agitado` não aparecem por esse caminho.

## 6. Telegram

### 6.1 Teste real (bot `@AnimaAlertBot`)
O token e o chat id estão só em `v2/servidor/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; os nomes `ANIMA_TELEGRAM_*` continuam aceitos). `getMe` respondeu HTTP 200;
`getUpdates` achou 1 chat privado. Envio real de 3 alertas (parado+febre, agitado, febre com movimento): log `telegram=enviado` nos 3 e **3 mensagens recebidas no
celular, confirmadas pelo dono do projeto**. O texto inclui dispositivo, ação (com o efeito na coleira), classe e confiança, temperatura da coleira, motivo e horário.
Esse envio real foi feito com a versão **síncrona**. Na etapa de fechamento, `getMe` voltou a responder 200 com o token atual do `.env` (46 caracteres, conferido só por máscara).

### 6.2 Falhas, com o envio em segundo plano (servidor real)
`python servidor/tests/teste_telegram_real.py --falha <modo>` (nenhuma mensagem chega ao celular nesses modos):

| Modo | Resultado |
|---|---|
| `token_invalido` | `HTTP 401 Unauthorized`; servidor classificou todas as janelas; token ausente da saída e do log |
| `chat_errado` | `HTTP 400 Bad Request: chat not found`; idem |
| `sem_internet` (proxy HTTP inexistente) | `ProxyError`; idem (rede realmente desligada ou timeout longo **não** exercitados) |

### 6.3 Telegram em segundo plano
A chamada à API era síncrona (até ~10 s por notificação numa falha lenta). Agora `NotificadorAssincrono` (`anima_core.py`) enfileira e uma thread envia, com timeout de
4 s (conexão) + 6 s (leitura), **fila limitada (padrão 20, `--fila-telegram`) que descarta a mais antiga quando enche**. A decisão publicada em `anima/<id>/decisao` só enfileira
(O(1)) e nunca espera. Cada envio gera uma linha no log CSV (`acao_bruta=envio_telegram`, coluna `telegram` = `enviado` | `erro: ...` | `descartado: ...`), sem o token. No Ctrl+C o servidor
desconecta e tenta esvaziar a fila por até 5 s; o que sobra é descartado e registrado.

Testes automáticos (`tests/test_telegram_async.py`, `tests/test_encerramento.py`):
* **Telegram lento (simulado 8 s)**: 6 decisões voltam em < 1,5 s; as 6 mensagens são entregues depois. Conferido que, com o notificador síncrono antigo, o mesmo cenário
  atrasaria as decisões proporcionalmente (3 alertas com 1 s de atraso: 3,0 s).
* **Erro** (exceção com o token na mensagem; HTTP 401): log `erro: RuntimeError` / `erro: HTTP 401 Unauthorized`, token ausente do log e da saída.
* **Fila cheia**: com `tamanho_fila=2` e envio travado, 5 mensagens → 2 descartadas (as mais antigas), entregues `msg-1, msg-4, msg-5`; log com 2 `descartado: fila cheia`.
* **Encerramento**: fila esvaziada quando dá tempo; com Telegram travado respeita o prazo (0,5 s) e descarta o resto; após encerrar, `enviar` descarta sem travar.
  Processo real: Ctrl+C simulado (`interrupt_main`) termina com código 0, imprime `Encerrando...` e `Encerrado. Telegram: ...`, sem traceback.
* Sem credenciais: nada é enfileirado; log `desativado`.

### 6.4 Intervalo entre notificações e `alerta_leve`
Regra: no máximo uma notificação por **(dispositivo, causa, ação)** a cada `--intervalo-notif` (padrão **300 s**, verificado em teste que lê o padrão do parser e de `Debounce()`).
Causa = `temperatura_alta` (regra de segurança ou classe febre), `agitado`, `letargia`. Assim, febre logo depois de agitação notifica na hora; a mesma causa repetida fica limitada.
Testes: causa diferente notifica; mesma causa repetida limitada com intervalo curto (2 s, relógio falso) e vence no instante exato; `alerta_leve` (imobilidade prolongada) chega ao Telegram com o texto
"Alerta leve" / "aviso leve na coleira"; escalonamento leve → alerta continua notificando na hora.

## 7. Segredos
* **Varredura** (arquivos do projeto, conteúdo interno de `.docx`/`.zip`, logs e pastas temporárias dos testes; padrões de token de bot do Telegram e `wok_...` do Wokwi; só caminhos e contagens, nunca valores):
  o token do Telegram existe **somente** em `v2/servidor/.env` (1 ocorrência); **nenhum token do Wokwi** em arquivos. O arquivo `BotFather - token.txt` da raiz foi movido para o `.env` e apagado.
* `.gitignore` (raiz e `v2/`): `.env`, `**/.env`, `*token*.txt`, `config_local.h`, `__pycache__/`, `servidor/logs/`, `servidor/dados_reais/`, `teste_wokwi_cli/build/`.
  A pasta **não é um repositório git**, então `git check-ignore` não pôde ser usado; a proteção só vale quando virar repositório.
* O primeiro token do Wokwi foi colado no chat e continua visível no histórico; **revogue-o**. Política atual: o token do Wokwi vai **só em variável de ambiente**. O `servidor/.env` do autor ainda tem uma linha `WOKWI_CLI_TOKEN` (de antes da mudança): **apague-a** (o `executar.py` não a lê mais).
* O zip da equipe é gerado por `v2/empacotar.py` (exclui `.env`, tokens, logs, dados reais, caches e `build/`; varre o conteúdo e **aborta** se achar padrão de token). Em 2026-10-26 o arquivo antigo havia sumido; foi regenerado (72 arquivos) e conferido.

## 8. Bugs e incidentes encontrados

| Problema | Causa | Correção |
|---|---|---|
| **Testes automáticos mandaram mensagens reais ao Telegram** (≥ 9 mensagens de teste detectadas nos logs, de execuções de `cenarios_e2e.py` e do cenário 05 do Wokwi, e possivelmente do pytest) | o `consumidor_v2.py` carrega o `servidor/.env` sozinho e os testes só removiam as variáveis `ANIMA_TELEGRAM_*`, não `TELEGRAM_*` | `ANIMA_SEM_DOTENV=1` faz `carregar_env` não ler o `.env`; aplicado em todos os testes que sobem o servidor; teste de regressão; conferido que o log passa a mostrar `desativado` |
| `gerar_wokwi.py` normalizava CRLF→LF (o `config.h` inteiro divergia no `diff`) | leitura/gravação normalizavam quebras de linha | leitura/escrita byte-fiel |
| Teste ponta a ponta intermitente sob carga | o servidor leva > 15 s para importar sklearn com a CPU ocupada | prazos de inicialização de 120 s; estável sob carga forte |
| `API Error: Unauthorized` em todos os cenários do Wokwi na reexecução | o `.env` tinha a linha `$env:WOKWI_CLI_TOKEN="wok_..."` inteira como valor (66 caracteres, em vez de `wok_` + 44) | extraído só o token; os 5 cenários passaram |
| Meu cenário 01 do Wokwi esperava as mensagens na ordem errada | `MPU6050 conectado.` é impresso antes de `Anima v2 - id=` | YAML corrigido (o firmware estava certo) |
| Expectativas erradas em checagens do intervalo mínimo (broker real e local) | tempo acumulado dos cenários e a regra antiga | checagens reescritas; regra por causa (6.4) |
| Um trecho do patch do Ctrl+C não foi aplicado e passou despercebido | `replace` sem verificar | o teste de encerramento limpo pegou; corrigido |

## 9. O que continua SEM teste
* **Wokwi CLI depois das correções de 2026-10-26:** o novo `executar.py`, o `libraries.txt` com versões e o `config.h` com o id padrão novo **não foram reexecutados** no simulador (sem token); só testes estáticos.
* **Compilação no editor web do Wokwi** com o `libraries.txt` de versões fixas (item 14 do `teste_wokwi.md`).
* **Hardware real**: nenhuma placa/sensor; comportamento elétrico real (I2C, ruído, DS18B20 real, buzzer, consumo, bateria) não foi observado.
* **TLS** e autenticação MQTT (o código existe, nunca foi exercitado).
* **Reconexão do dispositivo** (só a do servidor foi testada) e perda de mensagens durante a queda.
* **Fail-safe de 15 s** do alerta sem servidor.
* **Padrão de pisca do buzzer** (só o nível estático do GPIO 18 foi checado) e o `alerta_leve` no firmware.
* **MPU ausente** (`mpu_ok:false`) e DS18B20 desconectado (`-127`, `sensor_ok:false`) **no firmware** (só o servidor foi testado com esses payloads).
* **Backoff de Wi-Fi/MQTT com a rede caída**.
* **Dados reais de animais**: modelo, limiares e `offset_coleira` são sintéticos/arbitrários; o retreino só foi exercitado com amostra fabricada.
* **Envio real ao Telegram pelo caminho assíncrono** (só `getMe` e os modos de falha), limites de taxa, mensagens longas e grupos; rede realmente desligada.
* Parte do roteiro manual [teste_wokwi.md](teste_wokwi.md) (itens 7, 9–11, 13, 14).
* Versões das bibliotecas no editor web do Wokwi; autonomia de bateria; precisão do DS18B20 na coleira.

## 10. Correções da auditoria (2026-10-26)
Resumo; o detalhe (item → status → como foi verificado) está em [auditoria_final.md](auditoria_final.md).
* **Servidor:** `--id` obrigatório; `--todos` recusado em broker público sem `--aceito-risco-publico`; `id` do payload precisa ser igual ao do tópico; limite de dispositivos e de estado.
* **Reprodutibilidade:** `servidor/requirements.txt`, `requirements-dev.txt` e `ia/requirements.txt` com versões fixadas (`scikit-learn==1.9.1`); instalação conferida em venv limpo (`pip check` sem conflitos).
* **Selftest e treino:** o `--selftest` aplica o `offset_coleira` do modelo; `treinar_modelo_v2.py`/`retreinar.py --sufixo v2` não sobrescrevem o modelo oficial sem confirmação.
* **Pacote:** `empacotar.py` (varredura de tokens + exclusões) e o zip regenerado. **Wokwi CLI:** `executar.py` portável e token só do ambiente. **Wokwi:** `libraries.txt` com versões e BusIO.
* **Docs e testes:** passo a passo, ids únicos por pessoa, referência cruzada, `ResourceWarning` zerados (91 testes sem avisos).
