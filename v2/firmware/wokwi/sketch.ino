/*
 * Anima v2 - Coleira inteligente (ESP32 + MPU6050 + DS18B20)
 *
 * Mudanças em relação à Entrega 2:
 *  - Amostra o MPU6050 a ~25 Hz e publica, a cada janela de 2 s, ESTATÍSTICAS
 *    (média, desvio padrão e máximo de accel_mag e gyro_mag) + temperatura média.
 *  - Tópicos por dispositivo: publica em anima/<id>/dados e assina anima/<id>/decisao.
 *  - Recebe {"acao":"alerta"|"alerta_leve"|"nenhum"} e aciona buzzer/LED.
 *  - Proteção local de temperatura (> LIMIAR_TEMP_LOCAL_C) independente da rede/IA.
 *  - Wi-Fi e MQTT reconectam sem travar o loop (backoff exponencial).
 *  - DS18B20 = -127 (desconectado) é descartado e sinalizado com "sensor_ok":false.
 *  - Falha de init do MPU6050 é tratada (nova tentativa periódica, "mpu_ok":false).
 *
 * Payload (versao 2), unidades: accel_mag em m/s², gyro_mag em °/s, temperatura em °C:
 *  {"versao":2,"id":"anima-3f9c1a7e","n_amostras":50,
 *   "accel_mag_media":9.81,"accel_mag_std":0.05,"accel_mag_max":9.95,
 *   "gyro_mag_media":1.2,"gyro_mag_std":0.4,"gyro_mag_max":2.5,
 *   "temperatura":38.5,"sensor_ok":true,"mpu_ok":true}
 * Se o DS18B20 falhar na janela inteira: "temperatura":null,"sensor_ok":false.
 * Se o MPU6050 estiver fora: n_amostras=0, sem campos de movimento, "mpu_ok":false.
 * O desvio padrão é populacional (divide por n), igual ao np.std do Python.
 *
 * Observações honestas:
 *  - NÃO foi compilado nem testado em hardware real. Verifique no Wokwi/Arduino IDE.
 *  - mqttClient.connect() ainda bloqueia por até MQTT_TIMEOUT_S segundos a cada
 *    tentativa (limitação do PubSubClient); as tentativas respeitam o backoff.
 *  - Janelas não são enfileiradas: sem rede, a janela é descartada.
 *
 * Edite SOMENTE o config.h (e, para segredos, o config_local.h).
 */

#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <math.h>
#include "config.h"

// ---------- Constantes derivadas ----------
const float RAD_PARA_GRAUS = 57.2958f;                         // 180/PI (mantido da v1)
const unsigned long PERIODO_AMOSTRA_MS = 1000UL / TAXA_AMOSTRAGEM_HZ;  // 40 ms
const unsigned long TEMP_CONVERSAO_MS = 800;                   // DS18B20 12 bits: ~750 ms

// ---------- Objetos ----------
Adafruit_MPU6050 mpu;
OneWire oneWire(PINO_ONE_WIRE);
DallasTemperature tempSensor(&oneWire);
WiFiClient espClient;
PubSubClient mqttClient(espClient);

char topicoDados[64];
char topicoDecisao[64];

// ---------- Estado: MPU ----------
bool mpuOk = false;
unsigned long mpuProximaTentativa = 0;

// ---------- Estado: janela de amostragem ----------
struct Janela {
  uint16_t n;
  double somaA, somaA2, maxA;   // accel_mag
  double somaG, somaG2, maxG;   // gyro_mag
  float  somaT;                 // temperatura (leituras válidas)
  uint8_t nT;                   // quantas leituras válidas de temperatura
  uint8_t falhasT;              // quantas leituras inválidas (-127 etc.)
};
Janela janela;
unsigned long proximaAmostra = 0;
unsigned long inicioJanela = 0;

// ---------- Estado: temperatura ----------
bool tempPendente = false;
unsigned long tempPedidoEm = 0;
bool protecaoTemp = false;      // proteção local acionada

// ---------- Estado: rede ----------
bool wifiTentando = false;
unsigned long wifiIniciouEm = 0, wifiProxima = 0, wifiBackoff = BACKOFF_MIN_MS;
bool wifiEstavaConectado = false;
unsigned long mqttProxima = 0, mqttBackoff = BACKOFF_MIN_MS;

// ---------- Estado: atuador ----------
enum Acao { ACAO_NENHUM, ACAO_ALERTA_LEVE, ACAO_ALERTA };
Acao acaoAtual = ACAO_NENHUM;
unsigned long acaoRecebidaEm = 0;

// ============================================================
// Janela de estatísticas
// ============================================================
void zerarJanela(unsigned long agora) {
  memset(&janela, 0, sizeof(janela));
  inicioJanela = agora;
}

void acumularAmostra(double a, double g) {
  janela.n++;
  janela.somaA += a;  janela.somaA2 += a * a;  if (a > janela.maxA) janela.maxA = a;
  janela.somaG += g;  janela.somaG2 += g * g;  if (g > janela.maxG) janela.maxG = g;
}

double desvioPadrao(double soma, double soma2, uint16_t n) {
  if (n == 0) return 0.0;
  double media = soma / n;
  double var = soma2 / n - media * media;
  return var > 0.0 ? sqrt(var) : 0.0;   // populacional (ddof = 0)
}

// ============================================================
// Temperatura (DS18B20 sem bloquear: pede a conversão e lê depois)
// ============================================================
bool temperaturaValida(float t) {
  // -127 = sensor desconectado (DEVICE_DISCONNECTED_C); 85.0 = valor de power-on
  return t > -100.0f && t < 125.0f && t != 85.0f;
}

void atualizarTemperatura(unsigned long agora) {
  if (!tempPendente) {
    tempSensor.requestTemperatures();     // com setWaitForConversion(false) retorna na hora
    tempPendente = true;
    tempPedidoEm = agora;
  } else if (agora - tempPedidoEm >= TEMP_CONVERSAO_MS) {
    float t = tempSensor.getTempCByIndex(0);
    tempPendente = false;
    if (temperaturaValida(t)) {
      janela.somaT += t;
      janela.nT++;
      // Proteção local com histerese, avaliada a cada leitura válida
      if (t > LIMIAR_TEMP_LOCAL_C) protecaoTemp = true;
      else if (t < LIMIAR_TEMP_LOCAL_C - HISTERESE_TEMP_C) protecaoTemp = false;
    } else {
      janela.falhasT++;
    }
  }
}

// ============================================================
// Amostragem do MPU6050 (~25 Hz, sem delay)
// ============================================================
void iniciarMPU() {
  if (mpu.begin()) {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);   // anti-aliasing p/ amostrar a 25 Hz
    mpuOk = true;
    Serial.println("MPU6050 conectado.");
  } else {
    mpuOk = false;
    Serial.println("ERRO: MPU6050 não encontrado (nova tentativa em breve).");
  }
}

void amostrarMPU(unsigned long agora) {
  if (!mpuOk) {
    if (agora >= mpuProximaTentativa) {
      mpuProximaTentativa = agora + MPU_REINIT_MS;
      iniciarMPU();
    }
    return;
  }
  if ((long)(agora - proximaAmostra) < 0) return;
  proximaAmostra += PERIODO_AMOSTRA_MS;
  if ((long)(agora - proximaAmostra) > 200) proximaAmostra = agora + PERIODO_AMOSTRA_MS;  // recupera atraso

  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);
  double am = sqrt((double)a.acceleration.x * a.acceleration.x +
                   (double)a.acceleration.y * a.acceleration.y +
                   (double)a.acceleration.z * a.acceleration.z);                 // m/s²
  double gm = sqrt((double)g.gyro.x * g.gyro.x + (double)g.gyro.y * g.gyro.y +
                   (double)g.gyro.z * g.gyro.z) * RAD_PARA_GRAUS;               // rad/s -> °/s
  if (isnan(am) || isnan(gm)) return;   // leitura inválida: ignora a amostra
  acumularAmostra(am, gm);
}

// ============================================================
// Publicação da janela
// ============================================================
void fecharJanela(unsigned long agora) {
  char buf[400];
  bool sensorOk = janela.nT > 0;
  char temp[16];
  if (sensorOk) snprintf(temp, sizeof(temp), "%.2f", janela.somaT / janela.nT);
  else strcpy(temp, "null");

  int len;
  if (mpuOk && janela.n > 0) {
    len = snprintf(buf, sizeof(buf),
      "{\"versao\":2,\"id\":\"%s\",\"n_amostras\":%u,"
      "\"accel_mag_media\":%.3f,\"accel_mag_std\":%.3f,\"accel_mag_max\":%.3f,"
      "\"gyro_mag_media\":%.3f,\"gyro_mag_std\":%.3f,\"gyro_mag_max\":%.3f,"
      "\"temperatura\":%s,\"sensor_ok\":%s,\"mpu_ok\":true}",
      ANIMA_ID, janela.n,
      janela.somaA / janela.n, desvioPadrao(janela.somaA, janela.somaA2, janela.n), janela.maxA,
      janela.somaG / janela.n, desvioPadrao(janela.somaG, janela.somaG2, janela.n), janela.maxG,
      temp, sensorOk ? "true" : "false");
  } else {
    len = snprintf(buf, sizeof(buf),
      "{\"versao\":2,\"id\":\"%s\",\"n_amostras\":0,\"temperatura\":%s,"
      "\"sensor_ok\":%s,\"mpu_ok\":false}",
      ANIMA_ID, temp, sensorOk ? "true" : "false");
  }
  if (len <= 0 || len >= (int)sizeof(buf)) {
    Serial.println("ERRO: payload maior que o buffer, janela descartada.");
  } else {
    Serial.println(buf);
    if (mqttClient.connected()) mqttClient.publish(topicoDados, buf);
  }
  zerarJanela(agora);
}

// ============================================================
// Decisão recebida do servidor
// ============================================================
// Extrai o valor de "acao" sem biblioteca JSON (formato simples e controlado).
Acao interpretarAcao(const char* json) {
  const char* p = strstr(json, "\"acao\"");
  if (!p) return ACAO_NENHUM;
  p = strchr(p + 6, ':');
  if (!p) return ACAO_NENHUM;
  p = strchr(p, '"');
  if (!p) return ACAO_NENHUM;
  p++;
  if (strncmp(p, "alerta_leve\"", 12) == 0) return ACAO_ALERTA_LEVE;
  if (strncmp(p, "alerta\"", 7) == 0) return ACAO_ALERTA;
  return ACAO_NENHUM;
}

void aoReceberMensagem(char* topico, byte* dados, unsigned int tamanho) {
  char msg[256];
  if (tamanho >= sizeof(msg)) tamanho = sizeof(msg) - 1;
  memcpy(msg, dados, tamanho);
  msg[tamanho] = '\0';
  acaoAtual = interpretarAcao(msg);
  acaoRecebidaEm = millis();
  Serial.print("Decisão recebida: ");
  Serial.println(msg);
}

// ============================================================
// Atuador (buzzer + LED no mesmo pino), sem delay
// ============================================================
void atualizarAtuador(unsigned long agora) {
  if (acaoAtual != ACAO_NENHUM && agora - acaoRecebidaEm > DECISAO_TIMEOUT_MS) {
    acaoAtual = ACAO_NENHUM;   // servidor sumiu: não deixa o alerta preso
  }
  bool ligado = false;
  if (protecaoTemp) {
    ligado = true;                                  // proteção local: contínuo
  } else if (acaoAtual == ACAO_ALERTA) {
    ligado = (agora % 400) < 200;                   // pisca rápido
  } else if (acaoAtual == ACAO_ALERTA_LEVE) {
    ligado = (agora % 1500) < 100;                  // pulso curto a cada 1,5 s
  }
  digitalWrite(PINO_ATUADOR, ligado ? HIGH : LOW);
}

// ============================================================
// Rede não-bloqueante com backoff
// ============================================================
void manterWiFi(unsigned long agora) {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiEstavaConectado) {
      Serial.print("Wi-Fi conectado. IP: ");
      Serial.println(WiFi.localIP());
    }
    wifiEstavaConectado = true;
    wifiTentando = false;
    wifiBackoff = BACKOFF_MIN_MS;
    return;
  }
  if (wifiEstavaConectado) {
    Serial.println("Wi-Fi perdido.");
    wifiEstavaConectado = false;
  }
  if (!wifiTentando) {
    if (agora >= wifiProxima) {
      Serial.print("Conectando ao Wi-Fi: ");
      Serial.println(WIFI_SSID);
      WiFi.disconnect();
      if (WIFI_CANAL > 0) WiFi.begin(WIFI_SSID, WIFI_SENHA, WIFI_CANAL);
      else WiFi.begin(WIFI_SSID, WIFI_SENHA);
      wifiTentando = true;
      wifiIniciouEm = agora;
    }
  } else if (agora - wifiIniciouEm > WIFI_TENTATIVA_MS) {
    wifiTentando = false;
    wifiProxima = agora + wifiBackoff;
    Serial.print("Wi-Fi não conectou; nova tentativa em ms: ");
    Serial.println(wifiBackoff);
    wifiBackoff = min(wifiBackoff * 2, (unsigned long)BACKOFF_MAX_MS);
  }
}

void manterMQTT(unsigned long agora) {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqttClient.connected()) {
    mqttBackoff = BACKOFF_MIN_MS;
    mqttClient.loop();
    return;
  }
  if (agora < mqttProxima) return;
  Serial.print("Conectando ao broker MQTT...");
  bool ok;
  if (strlen(MQTT_USUARIO) > 0) ok = mqttClient.connect(ANIMA_ID, MQTT_USUARIO, MQTT_SENHA);
  else ok = mqttClient.connect(ANIMA_ID);
  if (ok) {
    Serial.println(" conectado!");
    mqttClient.subscribe(topicoDecisao);
    mqttBackoff = BACKOFF_MIN_MS;
  } else {
    Serial.print(" falhou, rc=");
    Serial.println(mqttClient.state());
    mqttProxima = agora + mqttBackoff;
    mqttBackoff = min(mqttBackoff * 2, (unsigned long)BACKOFF_MAX_MS);
  }
}

// ============================================================
void setup() {
  Serial.begin(115200);
  pinMode(PINO_ATUADOR, OUTPUT);
  digitalWrite(PINO_ATUADOR, LOW);

  snprintf(topicoDados, sizeof(topicoDados), "anima/%s/dados", ANIMA_ID);
  snprintf(topicoDecisao, sizeof(topicoDecisao), "anima/%s/decisao", ANIMA_ID);

  Wire.begin(PINO_SDA, PINO_SCL);
  iniciarMPU();
  mpuProximaTentativa = millis() + MPU_REINIT_MS;

  tempSensor.begin();
  tempSensor.setWaitForConversion(false);   // não bloqueia 750 ms a cada leitura

  mqttClient.setServer(MQTT_BROKER, MQTT_PORTA);
  mqttClient.setCallback(aoReceberMensagem);
  mqttClient.setBufferSize(512);
  mqttClient.setSocketTimeout(MQTT_TIMEOUT_S);

  unsigned long agora = millis();
  proximaAmostra = agora + PERIODO_AMOSTRA_MS;
  zerarJanela(agora);

  Serial.print("Anima v2 - id=");
  Serial.println(ANIMA_ID);
}

void loop() {
  unsigned long agora = millis();
  manterWiFi(agora);
  manterMQTT(agora);
  amostrarMPU(agora);
  atualizarTemperatura(agora);
  if (agora - inicioJanela >= JANELA_MS) fecharJanela(agora);
  atualizarAtuador(agora);
}
