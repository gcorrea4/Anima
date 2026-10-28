# Anima — coleira inteligente para animais

ESP32 + MPU6050 (movimento) + DS18B20 (temperatura) → Wi-Fi/MQTT → servidor Python com Random Forest → decisão de volta à coleira (buzzer/LED) e notificação no Telegram.

> **Estado real do projeto (leia antes de usar):**
> * O hardware **ainda não foi montado**. O firmware compila e já rodou no **simulador Wokwi**, mas **nunca em placa real**.
> * O modelo foi treinado **só com dados sintéticos**. Métricas e limiares (inclusive o de febre) **não** valem para animais reais até serem recalibrados com dados coletados.
> * Não é um dispositivo médico e não substitui avaliação veterinária.
> * O que foi testado (e o que não foi): [`v2/docs/relatorio_testes.md`](v2/docs/relatorio_testes.md) e [`v2/docs/auditoria_final.md`](v2/docs/auditoria_final.md).

## O que tem no repositório

```
Anima/
├── v2/                      ← o projeto atual (tudo o que você precisa está aqui)
│   ├── firmware/            #   código do ESP32 (+ variante gerada para o Wokwi)
│   ├── ia/                  #   dataset sintético, treino, modelo (.pkl)
│   ├── servidor/            #   servidor MQTT + IA + Telegram, coletor de dados, testes
│   ├── teste_wokwi_cli/     #   testes automáticos no simulador (opcional)
│   ├── docs/                #   guias, relatório de testes, auditoria
│   └── README.md            #   visão técnica detalhada da v2
└── entregas_anteriores/     ← Entregas 1 e 2 (artigos e código antigo), guardadas sem alteração
```

## 1. Instalação (uma vez)

Requisitos: **Python 3.14** (a versão em que tudo foi testado) e git. Para compilar o firmware: arduino-cli (ou Arduino IDE). Para o Wokwi pelo CLI: conta no Wokwi (opcional).

```powershell
git clone https://github.com/gcorrea4/Anima.git
cd Anima
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/Mac: source .venv/bin/activate
pip install -r v2/servidor/requirements-dev.txt
```

As versões estão **fixadas** de propósito: o modelo (`.pkl`) foi treinado com `scikit-learn==1.9.1` e outra versão pode avisar ou falhar ao carregá-lo.

## 2. Conferir que está tudo funcionando (sem hardware, sem internet)

```bash
cd v2/servidor
python consumidor_v2.py --selftest       # fluxo completo do servidor, sem rede → "OK: tudo certo."
python -m pytest tests -q                # 91 testes (~1 min)
python tests/cenarios_e2e.py             # dispositivo simulado + servidor + broker local simulado → 17/17
```

## 3. Rodar o servidor

1. Gere **o seu id de dispositivo** (único; o broker padrão é público e compartilhado):
   ```bash
   python -c "import secrets; print('anima-' + secrets.token_hex(4))"      # ex.: anima-3f9c1a7e
   ```
2. Suba o servidor para esse id:
   ```bash
   cd v2/servidor
   python consumidor_v2.py --id anima-3f9c1a7e
   ```
   Ele assina `anima/<id>/dados`, classifica cada janela de 2 s, publica a decisão em `anima/<id>/decisao`, grava `servidor/logs/decisoes_log.csv` e (se configurado) avisa no Telegram. `Ctrl+C` encerra.

**Segurança (importante):** `--id` é obrigatório. `--todos` (assina todos os dispositivos) é recusado em broker público. O padrão é `broker.hivemq.com`, que é **público, sem senha e sem TLS**: qualquer pessoa pode ler e publicar nos tópicos. Use só dados de teste. Para uso real, rode um broker próprio (ex.: Mosquitto) e configure `ANIMA_MQTT_HOST`, `ANIMA_MQTT_PORT`, `ANIMA_MQTT_USER`, `ANIMA_MQTT_PASS` e `ANIMA_MQTT_TLS=1` em `v2/servidor/.env`.

Opções úteis: `--janelas 3` (janelas consecutivas antes de alertar; padrão 2), `--intervalo-notif 600` (padrão 300 s), `--parado-letargia N`, `--nao-publicar`. Todas: `python consumidor_v2.py --help`.

## 4. Rodar o firmware no Wokwi (simulador no navegador)

1. Gere o seu id (passo 3.1).
2. Em https://wokwi.com crie um projeto **ESP32** novo e cole os 4 arquivos de `v2/firmware/wokwi/`: `sketch.ino`, `config.h`, `diagram.json`, `libraries.txt`.
3. No `config.h` do Wokwi, troque `ANIMA_ID` pelo seu id (o padrão `anima-TROQUE-ESTE-ID` colide com o de todo mundo).
4. Em outro terminal: `python consumidor_v2.py --id <seu id>`. Aperte ▶ no Wokwi.
5. Clique no DS18B20 e ponha **40,1 °C**: a 2ª janela consecutiva vira `alerta` e o buzzer/LED (GPIO 18) aciona. O Serial Monitor mostra `Decisão recebida: ...`.

Os arquivos de `v2/firmware/wokwi/` são **gerados** a partir de `v2/firmware/anima_esp32_v2/`. Se mudar o firmware: `python v2/firmware/gerar_wokwi.py`. Roteiro completo de testes manuais: [`v2/docs/teste_wokwi.md`](v2/docs/teste_wokwi.md).

## 5. Notificação no Telegram (opcional)

1. No Telegram, fale com **@BotFather**, `/newbot`, e guarde o token. Mande uma mensagem ao seu bot e descubra o `chat id` (passo a passo em [`v2/docs/passo_a_passo.md`](v2/docs/passo_a_passo.md), seção 3).
2. Crie o arquivo **`v2/servidor/.env`** (ele é ignorado pelo git) a partir do modelo:
   ```powershell
   copy v2\.env.example v2\servidor\.env          # Linux/Mac: cp v2/.env.example v2/servidor/.env
   ```
   e preencha `TELEGRAM_BOT_TOKEN=` e `TELEGRAM_CHAT_ID=` (sem aspas nem espaços). Sem isso, o servidor só imprime os alertas no terminal.
3. Ao iniciar, o servidor imprime `Telegram: ATIVO`.

Nunca commite o `.env`, nunca cole o token em chat/print. Se vazar, revogue no @BotFather (`/revoke`).
⚠️ `python v2/servidor/tests/teste_telegram_real.py` **manda mensagens de verdade** para o seu Telegram; os modos `--falha token_invalido|chat_errado|sem_internet` não mandam nada.

## 6. Compilar e gravar o firmware na placa

Ainda **não testado em hardware**. Ligações e lista de compras: [`v2/docs/hardware.md`](v2/docs/hardware.md) (MPU6050 em GPIO 21/22, DS18B20 no GPIO 4 com resistor de 4,7 kΩ, buzzer/LED no **GPIO 18**).

```bash
# uma vez: core e bibliotecas nas versões testadas
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32@3.3.12
arduino-cli lib install "Adafruit MPU6050@2.2.9" "Adafruit Unified Sensor@1.1.15" "Adafruit BusIO@1.17.4" "OneWire@2.3.8" "DallasTemperature@4.0.6" "PubSubClient@2.8.0"

# configuração SUA (Wi-Fi, broker, id): copie e edite; o config_local.h é ignorado pelo git
copy v2\firmware\anima_esp32_v2\config_local.h.example v2\firmware\anima_esp32_v2\config_local.h

arduino-cli compile --fqbn esp32:esp32:esp32 v2/firmware/anima_esp32_v2
```

Sem `config_local.h` a compilação funciona, mas emite um `#warning` (o `ANIMA_ID` padrão colide no broker público): é proposital. Para gravar na placa, `arduino-cli upload -p <PORTA> --fqbn esp32:esp32:esp32 v2/firmware/anima_esp32_v2` (a porta aparece em `arduino-cli board list`). Na Arduino IDE, abra a pasta `anima_esp32_v2` e instale as mesmas bibliotecas.

O limiar de temperatura do firmware (`LIMIAR_TEMP_LOCAL_C`) e o `offset_coleira` do modelo **precisam ser recalibrados** com termômetro clínico: o DS18B20 na coleira mede pele/ambiente, não a temperatura corporal.

## 7. Coletar dados reais e retreinar (quando houver hardware)

```bash
cd v2/servidor
python coletar_dados.py --id <seu id> --rotulo parado --animal Thor --obs "dormindo no sofá"     # rótulos: parado|normal|agitado|febre
cd ../ia
python retreinar.py --real ../servidor/dados_reais/*.csv --offset-coleira -4 --peso-real 3
python ../servidor/consumidor_v2.py --modelo modelo_anima_rf_v2_real.pkl --id <seu id>
```

Uma sessão = um rótulo. **Nunca provoque febre num animal**: use o rótulo `febre` só com confirmação veterinária. Treinar/retreinar **não sobrescreve o modelo oficial** sem confirmação (`--sim`) — ele é usado pelos testes. Detalhes e cuidados (split por sessão, offset): [`v2/docs/passo_a_passo.md`](v2/docs/passo_a_passo.md), seções 4 e 5.

## 8. Testar o firmware no Wokwi pelo terminal (opcional)

`python v2/teste_wokwi_cli/executar.py` roda 5 cenários no simulador (boot, rede/MQTT, febre e GPIO 18, MPU6050, laço com o servidor). Precisa de arduino-cli, wokwi-cli e do **token do Wokwi apenas em variável de ambiente**:

```powershell
$env:WOKWI_CLI_TOKEN = Read-Host "Token do Wokwi"      # não deixa o valor no histórico do terminal
python v2/teste_wokwi_cli/executar.py --help
```
Guia completo: [`v2/docs/wokwi_cli.md`](v2/docs/wokwi_cli.md). O plano grátis do Wokwi tem 50 min por 30 dias.

## 9. Empacotar para a equipe

```bash
python v2/empacotar.py          # gera v2_para_equipe.zip (sem .env, tokens, logs, caches) e lista os arquivos
```
O script varre o conteúdo e **aborta** se achar padrão de token. O zip não é versionado.

## Segredos e git

* **Nunca** commite: `v2/servidor/.env`, `config_local.h`, tokens. Estão no `.gitignore`; conferido que nenhum está rastreado nem no histórico (1 commit).
* O token do Wokwi só vai em variável de ambiente; o do Telegram, só no `v2/servidor/.env`.
* O repositório está no GitHub (`gcorrea4/Anima`): confira se ele é **público** — o código, o modelo e os artigos ficam visíveis. Dados reais de animais coletados (`v2/servidor/dados_reais/`) são ignorados pelo git.

## Problemas comuns

| Sintoma | Causa / solução |
|---|---|
| `ERRO: informe --id <dispositivo>` | o servidor exige `--id` (veja o passo 3) |
| `--todos ... broker público é perigoso` | use `--id`, ou um broker próprio; só use `--aceito-risco-publico` se entender o risco |
| Aviso de versão do scikit-learn ao carregar o `.pkl` | instale pelas versões fixadas: `pip install -r v2/servidor/requirements-dev.txt` |
| Servidor sem notificação no Telegram | `v2/servidor/.env` ausente ou com nomes errados (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`); ele avisa `Telegram: não configurado` |
| Nada chega ao servidor | id diferente entre firmware e `--id`; ou o `"id"` do payload não confere com o do tópico (a mensagem é ignorada) |
| `--selftest` falha com modelo recalibrado | confira o `offset_coleira` no `.meta.json` do modelo carregado (o selftest o aplica) |
| `API Error: Unauthorized` no Wokwi CLI | token inválido/revogado, ou com texto extra (cole só `wok_...`) |

## Para saber mais

[`v2/README.md`](v2/README.md) (contrato do payload, estrutura, tabela de testes) · [`v2/docs/passo_a_passo.md`](v2/docs/passo_a_passo.md) · [`v2/docs/hardware.md`](v2/docs/hardware.md) · [`v2/docs/relatorio_testes.md`](v2/docs/relatorio_testes.md) · [`v2/docs/auditoria_final.md`](v2/docs/auditoria_final.md) · [`v2/docs/comparacao_v1_v2.md`](v2/docs/comparacao_v1_v2.md)
