# Anima — Protótipo virtual (Wokwi + IA)

Simula o circuito inteiro no navegador (ESP32 + MPU6050 + DS18B20 + buzzer + LED) e fecha o fluxo
**sensor → ESP32 → Wi-Fi/MQTT → modelo de IA → decisão**, com o mesmo firmware do artigo.

## Arquivos
| Arquivo | Para quê |
|---|---|
| `sketch.ino` | Firmware corrigido (°/s) — só 3 linhas mudam: rede `Wokwi-GUEST`, senha vazia, canal 6 |
| `diagram.json` | Circuito (peças e fios) |
| `libraries.txt` | Bibliotecas do Arduino usadas pelo firmware |
| `consumidor_mqtt.py` | Roda no PC: recebe o JSON do ESP32 e classifica com o `modelo_anima_rf.pkl` |

## Passo a passo
1. Entre em **wokwi.com** (conta gratuita) → **New Project** → **ESP32**.
2. No projeto, substitua o conteúdo de `sketch.ino`, `diagram.json` e `libraries.txt` pelos arquivos desta pasta.
3. Clique em **▶ Start**. No Serial Monitor devem aparecer `Wi-Fi conectado!`, `conectado!` (MQTT) e um JSON a cada 2 s.
4. No PC, coloque `consumidor_mqtt.py` na mesma pasta do `modelo_anima_rf.pkl` e rode:
   ```
   pip install paho-mqtt scikit-learn pandas numpy joblib
   python consumidor_mqtt.py --selftest     # confere o modelo, sem rede
   python consumidor_mqtt.py                # escuta o broker e classifica
   ```
5. Com a simulação rodando, **clique no MPU6050 e no DS18B20** para mudar os valores e ver a classe mudar no terminal.

## Cenários de demonstração
Aceleração em **g**, giroscópio em **°/s** (unidades do painel do Wokwi). Previsões conferidas com o modelo salvo.

| Cenário | MPU6050: accel X / Y / Z | MPU6050: rotation X / Y / Z | DS18B20 | Classe esperada | Ação |
|---|---|---|---|---|---|
| Parado | 0 / 0 / 1 | 0 / 0 / 0 | 37.9 | letárgico (100%) | alerta leve |
| Normal | 0.04 / 0.02 / 1 | 6 / 4 / 5 | 38.6 | normal (92%) | sem alerta |
| Agitado | 0.5 / 0.4 / 1 | 30 / 25 / 20 | 38.7 | agitado (100%) | alerta |
| Febre | 0.03 / 0.02 / 1 | 4 / 3 / 4 | 40.1 | febre (98%) | alerta |

O DS18B20 tem resolução de 0,0625 °C, então 38.6 vira 38.625 (já considerado acima).

**Prova da correção de unidades:** ponha `rotationX = 100` no MPU6050. O `gyro_x` do JSON deve sair ≈ 100
(simulador 100 °/s → biblioteca 1,745 rad/s → firmware ×57,2958 = 100 °/s). Sem a conversão sairia ≈ 1,7.

## Se o Wokwi reclamar de algum fio
Passe o mouse sobre o pino para ver o nome certo, ou ligue manualmente:

| ESP32 | Componente |
|---|---|
| GPIO 21 / GPIO 22 | MPU6050 SDA / SCL |
| 3V3 / GND | VCC / GND de MPU6050 e DS18B20 |
| GPIO 4 | DS18B20 DQ (com resistor de 4,7 kΩ entre DQ e 3V3) |
| GPIO 5 | Buzzer (+) e LED (via 220 Ω); buzzer (−) e LED cátodo no GND |

## O que este protótipo NÃO prova (diga isso na apresentação)
- É simulação: o MPU6050 virtual não tem ruído nem vibração real. Não substitui a validação com hardware físico.
- LED e buzzer do firmware só acendem por **temperatura > 39,5 °C**; a decisão da IA aparece no terminal do consumidor.
  O canal de volta IA → ESP32 continua não implementado (já descrito no artigo). O buzzer do Wokwi pode não soar com nível DC (ele usa `tone()`), por isso há o LED.
- Broker `broker.hivemq.com` é público: qualquer pessoa pode ler ou publicar em `anima/dados`, e o gateway do Wokwi monitora o tráfego. Use só dados de teste.
- `--publicar-decisao` publica a decisão em `anima/decisao`, mas o firmware ainda não assina esse tópico.
- O consumidor descarta leituras de −127 °C (sensor desconectado), cobrindo no lado do PC uma limitação do firmware.

## Texto sugerido para o artigo
"Como o hardware ainda não foi adquirido, foi construído um protótipo virtual no simulador Wokwi, com ESP32, MPU6050, DS18B20,
buzzer e LED, executando o mesmo firmware (alterada apenas a rede Wi-Fi para a rede virtual do simulador). O ESP32 simulado publica
as leituras via MQTT e um consumidor em Python aplica o modelo Random Forest e decide o alerta. Trata-se de simulação, sem ruído
de sensores reais, e não substitui a validação em hardware físico prevista para a Entrega 3."
