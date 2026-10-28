# Hardware real: compras, ligação e limitações

> Lista de **sugestões** com base no que o simulador usa. Nada foi montado ou testado em bancada. Confira
> compatibilidade e especificações antes de comprar; preços variam e não foram incluídos.

## Lista de compras

| Item | Observação |
|---|---|
| ESP32 DevKit (30 ou 38 pinos, tipo DevKit V1/DevKitC) | O `diagram.json` usa a pinagem do DevKitC. Confirme a posição dos pinos 21/22/4/5 na sua placa. |
| Módulo MPU6050 (GY-521) | I2C, 3,3 V. Já vem com regulador e pull-ups. |
| Sensor DS18B20 **encapsulado à prova d'água** (sonda) | Para ficar em contato com a pele/pelo é melhor a sonda do que o TO-92 nu. |
| Resistor 4,7 kΩ | Pull-up do DS18B20 (DQ → 3V3). |
| Buzzer **ativo** 3–5 V | Ativo = apita só com nível alto, sem gerar frequência. |
| LED vermelho + resistor 220 Ω | Mesmo pino do buzzer, como no diagrama. |
| Transistor NPN (ex.: BC547/2N2222) + resistor 1 kΩ | Recomendado para o buzzer, para não exigir corrente demais do GPIO. |
| Protoboard e jumpers; depois, placa perfurada/soldagem | Solda é muito mais confiável que jumper numa coleira. |
| Bateria Li-ion/LiPo 3,7 V + módulo de carga com proteção (ex.: TP4056 com proteção) | O Wi-Fi contínuo consome muito (ver limitações). |
| Cabo micro-USB/USB-C (conforme a placa) | Programação e testes. |
| Caixa/case e coleira | Fixar a placa firme: movimento solto do módulo vira ruído no acelerômetro. |
| Termômetro clínico veterinário | Para calibrar o `offset_coleira`. |

## Esquema de ligação (igual ao `diagram.json` do Wokwi da v2, `firmware/wokwi/diagram.json`)

| Componente | Pino do componente | Pino do ESP32 |
|---|---|---|
| MPU6050 | VCC | 3V3 |
| | GND | GND |
| | SDA | GPIO 21 |
| | SCL | GPIO 22 |
| DS18B20 | VCC (vermelho) | 3V3 |
| | GND (preto) | GND |
| | DQ (dados) | GPIO 4 **e** 4,7 kΩ até 3V3 |
| Buzzer ativo (+) | | GPIO 18 (idealmente via transistor, veja abaixo) |
| Buzzer (−) | | GND |
| LED (ânodo) | via 220 Ω | GPIO 18 |
| LED (cátodo) | | GND |

Com transistor: GPIO 18 → 1 kΩ → base do NPN; emissor → GND; coletor → buzzer (−); buzzer (+) → 3V3/5V conforme o
buzzer. (Não testado.)

Todos os pinos estão em `config.h` (`PINO_*`). O atuador foi movido do GPIO 5 (pino de *strapping* do ESP32, que pode atrapalhar o boot
se for puxado para o nível errado na inicialização) para o **GPIO 18**. Evite também GPIO 0, 2, 12 e 15 para o atuador.

## Antes de usar em um animal

1. Ligue no protoboard em bancada e rode o firmware com `config_local.h` (Wi-Fi, broker, `ANIMA_ID`).
2. Confira no serial: MPU conectado, janelas com `n_amostras` ≈ 50, temperatura plausível.
3. Calibre o `offset_coleira` e o `LIMIAR_TEMP_LOCAL_C` (veja o passo a passo, seção 5).
4. Teste sem o animal (coleira em uma pessoa ou objeto aquecido de forma segura) antes de colocar num animal.

## Limitações conhecidas

**Modelo e dados**
* O modelo foi treinado **somente com dados sintéticos** definidos à mão. Acurácia de ~94% no teste sintético só
  mede o quão separáveis são as classes que nós mesmos simulamos. Desempenho em animais reais: **desconhecido**.
* O DS18B20 na coleira mede temperatura de **pele/pelo/ambiente**, não a corporal. O limiar de febre (39,5 °C
  corporal) não vale diretamente para a leitura da coleira. Está parametrizado por `offset_coleira`, mas o valor
  correto só virá de calibração com termômetro clínico, e provavelmente varia com clima, pelagem e encaixe.
* A febre é separada quase só pela temperatura (as classes sintéticas são truncadas em 39,5 °C). Na prática o
  limite é nebuloso; exercício, sol e ambiente quente também elevam a leitura (risco de falso alarme).
* `parado` vs. `normal`: janelas em que o animal muda de comportamento no meio da janela são ambíguas (e o gerador
  sintético inclui 15% delas de propósito). Letargia **não** é detectada por janela; só pela regra opcional de
  imobilidade prolongada, não calibrada.
* A orientação da coleira, o tamanho/espécie do animal e o encaixe mudam o sinal. Um único animal não generaliza.
* Sem validação clínica: o sistema **não é um dispositivo médico** e não substitui avaliação veterinária.

**Firmware**
* Compila para ESP32 Dev Module (arduino-cli, core 3.3.12), mas **nunca foi executado**: nem no Wokwi, nem em hardware.
* `mqttClient.connect()` bloqueia até `MQTT_TIMEOUT_S` (3 s) a cada tentativa (limitação do PubSubClient); o resto
  do loop (amostragem, proteção de temperatura) para durante esse intervalo. O backoff espaça as tentativas.
* Sem rede, as janelas são descartadas (não há fila/armazenamento local) e não há relógio/NTP: o `timestamp` vem do
  servidor, não do dispositivo.
* Se o MPU6050 travar o I2C sem erro, a biblioteca pode devolver leituras paradas e o firmware não detecta isso.
* Faixas do MPU: ±8 g e ±500 °/s; movimentos muito bruscos saturam. O filtro de 21 Hz foi escolhido para amostrar a 25 Hz.
* Consumo: Wi-Fi + 25 Hz contínuos, sem *sleep*. A autonomia da bateria em coleira é provavelmente de horas, não dias.
* Sem OTA, sem TLS no firmware (porta 1883, texto puro) e sem autenticação das decisões: **qualquer pessoa que
  publique em `anima/<id>/decisao` num broker público controla o buzzer.**
* Buzzer e LED compartilham o mesmo pino (GPIO 18).

**Servidor**
* Debounce simples: uma janela "nenhum" no meio zera a contagem (alertas intermitentes podem nunca confirmar).
* Telegram: envio real testado (com a versão síncrona) e falhas testadas no envio em segundo plano; limites de taxa e grupos não. O servidor é de processo único,
  sem persistência de estado (reiniciar zera contagens e intervalos).
* Broker padrão público; sem autenticação nem TLS por padrão.
