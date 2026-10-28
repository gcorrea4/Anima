# Anima v2

Evolução da Entrega 2 (coleira inteligente: ESP32 + MPU6050 + DS18B20 → Wi-Fi/MQTT → Random Forest → alerta).
Os arquivos das Entregas 1 e 2 foram guardados, sem alterações, em `../entregas_anteriores/`. O `v2` é autossuficiente: usa cópias somente leitura em
`firmware/base_entrega2/` (diagram.json e libraries.txt) e `ia/v1_referencia/` (modelo e relatório da v1).

> **Honestidade sobre o estado do projeto:** o hardware ainda não foi comprado. O firmware v2 **compila** (ESP32 Dev Module,
> as duas variantes) e **roda no simulador Wokwi** (wokwi-cli), mas **nunca foi executado em placa real**. O modelo foi treinado e avaliado **só com dados sintéticos**;
> as métricas não dizem nada sobre animais reais. O que foi de fato executado e testado está na seção
> [O que foi testado](#o-que-foi-testado).

## O que mudou em relação à Entrega 2

| | Entrega 2 | v2 |
|---|---|---|
| Dado enviado | 1 leitura instantânea a cada 2 s | estatísticas de uma janela de 2 s amostrada a ~25 Hz (média, desvio e máximo de `accel_mag` e `gyro_mag` + temperatura média) |
| Tópicos | `anima/dados` | `anima/<id>/dados` (publica) e `anima/<id>/decisao` (assina) |
| Atuador | limiar fixo local (> 39,5 °C) | comando do servidor (`alerta` / `alerta_leve` / `nenhum`) **+** limiar local mantido como proteção independente |
| Robustez | `delay` e laços bloqueantes | Wi-Fi/MQTT com backoff sem travar o loop, DS18B20 assíncrono, -127 descartado, falha do MPU6050 tratada |
| Classes | normal, letárgico, agitado, febre | **parado**, normal, agitado, febre (veja a nota abaixo) |
| Servidor | imprime a classe | publica a decisão, exige N janelas consecutivas, intervalo mínimo entre notificações **por (dispositivo, causa, ação)**, Telegram **em segundo plano** (fila limitada, nunca atrasa a decisão), log CSV |
| Temperatura | escala corporal fixa | faixa por classe + `offset_coleira` configuráveis (a coleira não mede temperatura corporal) |

**Nota sobre "letárgico":** numa janela de 2 s, um animal letárgico e um animal dormindo são indistinguíveis
(ambos imóveis). Em vez de fingir que o modelo separa os dois, a v2 classifica `parado` e oferece uma regra
opcional no servidor (`--parado-letargia N`, **desligada por padrão**) que gera alerta leve após N janelas
`parado` seguidas. O valor de N precisa ser calibrado com dados reais.

## Estrutura

```
v2/
├── README.md, .env.example, .gitignore, empacotar.py   # empacotar.py gera o zip da equipe sem segredos
├── firmware/
│   ├── anima_esp32_v2/        # fonte única: .ino + config.h (+ config_local.h.example)
│   ├── libraries_wokwi.txt    # bibliotecas com versões fixadas (fonte do libraries.txt do Wokwi)
│   ├── gerar_wokwi.py         # gera wokwi/ a partir da fonte (Wi-Fi Wokwi-GUEST, canal 6)
│   ├── wokwi/                 # sketch.ino, config.h, diagram.json, libraries.txt (GERADOS)
│   └── base_entrega2/         # cópias somente leitura do diagram.json (GPIO 5) e libraries.txt da Entrega 2
├── ia/
│   ├── features_v2.py         # variáveis e classes (contrato único)
│   ├── params_sinteticos.json # temperatura por classe, offset_coleira, níveis de movimento
│   ├── gerar_dataset_v2.py    # dataset sintético por simulação do sinal bruto a 25 Hz
│   ├── treinar_modelo_v2.py   # treino + relatório + matriz de confusão + importância
│   ├── retreinar.py           # sintético + dados reais
│   ├── comparar_v1_v2.py      # gera docs/comparacao_v1_v2.md
│   ├── requirements.txt       # (inclui o do servidor) + matplotlib
│   ├── v1_referencia/         # cópias somente leitura do modelo e relatório da v1
│   └── modelo_anima_rf_v2.pkl (+ .meta.json, relatórios, gráficos)
├── servidor/
│   ├── consumidor_v2.py       # MQTT → IA → decisão → publica / Telegram / log
│   ├── coletar_dados.py       # grava CSV rotulado para retreino
│   ├── anima_core.py          # validação, regra, debounce, notificação, log, segurança
│   ├── requirements.txt, requirements-dev.txt   # versões fixadas (scikit-learn==1.9.1)
│   └── tests/                 # pytest (inclui ponta a ponta com mini-broker local)
├── teste_wokwi_cli/           # 5 cenários no simulador via wokwi-cli (executar.py, scenarios/*.yaml)
└── docs/
    ├── passo_a_passo.md       # Wokwi, servidor, Telegram, coleta, retreino, pacote
    ├── wokwi_cli.md           # como rodar os testes do Wokwi pelo CLI (token só em variável de ambiente)
    ├── hardware.md            # lista de compras, ligação, limitações conhecidas
    ├── relatorio_testes.md    # o que foi executado, com saídas reais
    ├── auditoria_final.md     # auditoria somente leitura + correções aplicadas
    ├── teste_wokwi.md         # roteiro manual para preencher
    └── comparacao_v1_v2.md
```

## Início rápido (sem hardware)

```bash
pip install -r v2/servidor/requirements-dev.txt     # versões fixadas (Python 3.14; scikit-learn==1.9.1, a do modelo)

cd v2/ia
python gerar_dataset_v2.py      # opcional: já existe um dataset gerado
python treinar_modelo_v2.py     # opcional: já existe um modelo; pede confirmação antes de sobrescrever o oficial (--sim confirma)

cd ../servidor
python consumidor_v2.py --selftest      # fluxo completo sem rede
python -m pytest tests -q               # testes automatizados
python consumidor_v2.py --id <SEU_ID>   # servidor de verdade: --id obrigatório (gere o seu: veja o passo a passo, seção 0)
```

Para rodar com o simulador, veja [docs/passo_a_passo.md](docs/passo_a_passo.md).

## Contrato do payload (versão 2)

Tópico `anima/<id>/dados`, JSON. `accel_mag` em m/s², `gyro_mag` em °/s, `temperatura` em °C, desvio padrão populacional:

```json
{"versao":2,"id":"anima-3f9c1a7e","n_amostras":50,
 "accel_mag_media":9.81,"accel_mag_std":0.05,"accel_mag_max":9.95,
 "gyro_mag_media":1.2,"gyro_mag_std":0.4,"gyro_mag_max":2.5,
 "temperatura":38.5,"sensor_ok":true,"mpu_ok":true}
```

* DS18B20 sem leitura válida na janela: `"temperatura":null,"sensor_ok":false` (o servidor descarta).
* MPU6050 fora: `"n_amostras":0,"mpu_ok":false`, sem campos de movimento (o servidor descarta).

Tópico `anima/<id>/decisao`: `{"acao":"alerta"|"alerta_leve"|"nenhum","classe":...,"confianca":...,"motivo":...,"ts":...}`.
O firmware só lê `acao`; se nenhuma decisão chegar por 15 s, o alerta expira.

## Segurança e privacidade

* **`broker.hivemq.com` é público**: qualquer pessoa pode ler o que você publica e **publicar na sua decisão
  (inclusive acionar o buzzer da coleira)**. Use só para testes, com um id único, e nunca com dados reais.
  Para uso real, suba um broker próprio (ex.: Mosquitto) com usuário/senha e TLS (`ANIMA_MQTT_TLS=1`).
* **Servidor:** `--id` é obrigatório; `--todos` (assina `anima/+/dados`) é recusado em broker público sem `--aceito-risco-publico`; o `"id"` do payload precisa ser igual
  ao id do tópico; `--todos` limita o número de dispositivos e o estado guardado. Use ids únicos (`<SEU_ID>`), nunca os de exemplo.
* Segredos (token do Telegram, senha do broker) ficam em variáveis de ambiente ou no `.env` (ignorado pelo git). O **token do Wokwi só em variável de ambiente**, nunca em arquivo.
  No firmware, senhas vão em `config_local.h` (também ignorado). Nunca commite esses arquivos.
* O token do Telegram nunca é impresso nem gravado em log pelo servidor.

## O que foi testado

| Item | Como | Resultado |
|---|---|---|
| Regras, debounce por causa, Telegram em segundo plano (lento/erro/fila cheia/encerramento), `alerta_leve`, isolamento do `.env` | pytest (57 testes no total) | passou |
| Modelo v2 (`parado` + 40,1 °C → febre → alerta após 2 janelas) | pytest + selftest | passou (sintético) |
| Servidor e coletor ponta a ponta | pytest com mini-broker MQTT local, processos reais e dispositivo simulado em Python | passou |
| Wokwi sincronizado com a fonte, contrato do payload, tópicos, ausência de `delay`, GPIO 18 | pytest estático sobre o `.ino` | passou — não é execução |
| Compilação das duas variantes (arduino-cli, esp32:esp32:esp32) | `arduino-cli compile --warnings all` | passou, sem avisos nos arquivos do projeto |
| Servidor × broker público real (HiveMQ), com reconexão | `servidor/tests/teste_broker_publico.py` | 20/20 |
| Firmware no simulador Wokwi (5 cenários, via CLI) | `teste_wokwi_cli/executar.py` | passou |
| Cenários ponta a ponta com dispositivo simulado | `python servidor/tests/cenarios_e2e.py` | 17/17 |
| Telegram real (3 mensagens no celular) e modos de falha | `servidor/tests/teste_telegram_real.py` | passou |
| Segurança do servidor (`--id`/`--todos`, broker público, id do payload, limites), selftest com offset, guarda do treino, empacotamento, `executar.py` portável | pytest | passou |

**Não testado:** hardware real, TLS, reconexão do dispositivo, fail-safe de 15 s do alerta, padrão de pisca do buzzer, MPU ausente e backoff com rede caída
**no firmware**, envio real ao Telegram pelo caminho em segundo plano (só falhas), e **qualquer dado de animal real**. Lista completa e saídas reais em
[docs/relatorio_testes.md](docs/relatorio_testes.md); roteiro manual em [docs/teste_wokwi.md](docs/teste_wokwi.md).

Veja as limitações em [docs/hardware.md](docs/hardware.md#limitações-conhecidas).
