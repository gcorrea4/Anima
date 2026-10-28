# Testes no Wokwi pelo CLI (`teste_wokwi_cli/`)

Roda o firmware v2 compilado no simulador Wokwi, sem abrir o navegador, e confere o Serial, os pinos e (no cenário 05) o laço com o servidor.
Isto **não substitui** o teste no editor web nem em hardware real: o CLI executa o binário compilado aqui (arduino-cli), não o compilador do site.

## O que é preciso

| Item | Como obter |
|---|---|
| Python 3.14 (testado) e `pip install -r v2/servidor/requirements-dev.txt` | veja o passo a passo, seção 0 |
| **arduino-cli** com o core `esp32:esp32` 3.3.12 | https://arduino.github.io/arduino-cli/ ; depois `arduino-cli core install esp32:esp32@3.3.12` (índice: `https://espressif.github.io/arduino-esp32/package_esp32_index.json`) |
| Bibliotecas nas versões testadas | `arduino-cli lib install "Adafruit MPU6050@2.2.9" "Adafruit Unified Sensor@1.1.15" "Adafruit BusIO@1.17.4" "OneWire@2.3.8" "DallasTemperature@4.0.6" "PubSubClient@2.8.0"` (a lista fixa está em `v2/firmware/libraries_wokwi.txt`) |
| **wokwi-cli** | https://docs.wokwi.com/wokwi-ci/cli-installation (o release do GitHub é um executável único; conferido: versão 0.29.0) |
| **Token do Wokwi** | https://wokwi.com/dashboard/ci (precisa de conta) |
| Internet | o cenário 02 e o 05 usam o broker público; o plano grátis do Wokwi tem **50 min por 30 dias e 5 min por sessão** |

Nenhum caminho é fixo no script. Ele procura as ferramentas, nesta ordem, em: argumento → variável de ambiente → PATH.

| Ferramenta | Argumento | Variável de ambiente | Se nenhum dos dois |
|---|---|---|---|
| arduino-cli | `--arduino-cli CAMINHO` | `ANIMA_ARDUINO_CLI` (ou `<ANIMA_ARDUINO_DIR>/bin/arduino-cli`) | procura `arduino-cli` no PATH |
| wokwi-cli | `--wokwi-cli CAMINHO` | `WOKWI_CLI_EXE` | procura `wokwi-cli` no PATH |
| instalação isolada do arduino-cli (subpastas `data/`, `user/`, `dl/`) | `--arduino-dir PASTA` | `ANIMA_ARDUINO_DIR` | usa a configuração padrão do arduino-cli |

## O token do Wokwi: SOMENTE variável de ambiente

* O `executar.py` lê o token **apenas** da variável `WOKWI_CLI_TOKEN`. **Nunca** de arquivo (nem do `.env`), e nunca o imprime nem grava
  (a saída do CLI passa por um filtro que o mascara).
* Defina na sessão do terminal, sem deixar o valor no histórico:
  * PowerShell: `$env:WOKWI_CLI_TOKEN = Read-Host "Token do Wokwi"`
  * bash: `read -rs WOKWI_CLI_TOKEN && export WOKWI_CLI_TOKEN`
* Evite digitar `$env:WOKWI_CLI_TOKEN="wok_..."` direto: o PSReadLine guarda a linha em `ConsoleHost_history.txt`.
* Se colar o token num chat, print ou arquivo por engano, **revogue-o** em wokwi.com/dashboard/ci e gere outro.
* Sem o token, `python executar.py --so-build` ainda compila e prepara tudo.

## Uso

```bash
python v2/teste_wokwi_cli/executar.py --help
python v2/teste_wokwi_cli/executar.py --so-build             # compila e prepara build/ (sem token, sem wokwi-cli)
python v2/teste_wokwi_cli/executar.py 01                     # só o cenário 01
python v2/teste_wokwi_cli/executar.py                        # os 5 cenários (≈ 4–6 min de relógio; a compilação leva 1–2 min)
python v2/teste_wokwi_cli/executar.py --arduino-dir ~/arduino-isolado --wokwi-cli ~/bin/wokwi-cli
```

O script: confere `firmware/wokwi/` (`gerar_wokwi.py --check`), compila a variante Wokwi com um `ANIMA_ID` aleatório (via `config_local.h` numa pasta temporária),
copia `build/firmware.bin|elf` e o `diagram.json` (GPIO 18) para `teste_wokwi_cli/`, roda `scenarios/*.yaml` e confere os números do log serial.
`build/` é ignorado pelo git e fica fora do pacote da equipe (`empacotar.py`).

| Cenário | O que verifica | Rede |
|---|---|---|
| 01 | boot, MPU6050, payload v2, números (accel ≈ 9,81 m/s², gyro ≈ 0, 38,5 °C), GPIO 18 em repouso | não |
| 02 | Wi-Fi `Wokwi-GUEST` e MQTT no broker **real**; um ouvinte externo recebe os payloads | sim |
| 03 | `set-control` do DS18B20 (40,1 °C) e proteção local: GPIO 18 = 1; volta a 38,5 °C: GPIO 18 = 0 | não |
| 04 | `set-control` do MPU6050 (2 g em Z, 100 °/s em X): accel ≈ 19,6 m/s² e gyro ≈ 100 (°/s) | não |
| 05 | laço completo: Wokwi → broker real → `consumidor_v2.py` (iniciado pelo script, só para o id do teste, **sem `.env`**) → decisão no ESP32 | sim |

Limites conhecidos: o DS18B20 só aceita -55…125 °C no `set-control`, então -127 (desconectado) não dá para simular; os valores do MPU no Wokwi são constantes
(desvio ≈ 0); buzzer/LED só têm o nível estático do GPIO 18 conferido (não o padrão de pisca). O que falta está em `docs/teste_wokwi.md` e em `docs/relatorio_testes.md`.

## Se algo falhar

| Mensagem | Causa provável |
|---|---|
| `WOKWI_CLI_TOKEN não está no ambiente` | variável não definida na sessão atual (é por terminal/sessão) |
| `API Error: Unauthorized` | token inválido, revogado, truncado ou com texto extra (por exemplo, a linha inteira `$env:...="wok_..."` colada como valor) |
| `arduino-cli não encontrado` / `wokwi-cli não encontrado` | ferramenta fora do PATH: use os argumentos/variáveis da tabela |
| `compilação falhou` | core ou bibliotecas não instalados nas versões acima |
| timeout em `wait-serial` | a ordem das mensagens do firmware mudou; confira `scenarios/*.yaml` |
