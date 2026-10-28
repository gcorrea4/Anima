/*
 * Anima - Coleira Inteligente de Saúde e Segurança para Pets
 * Entrega 1 - Protótipo Inicial
 *
 * Função desta versão:
 *  - Ler dados do acelerômetro/giroscópio (MPU6050) via I2C
 *  - Ler temperatura (DS18B20)
 *  - Conectar o ESP32 ao Wi-Fi em modo estação (station mode),
 *    isto é, o ESP32 se conecta a um roteador já existente,
 *    em vez de criar sua própria rede (modo access point)
 *  - Converter o giroscópio de rad/s para °/s (unidade do dataset de IA)
 *  - Enviar os dados via MQTT para um broker (para posterior
 *    processamento e classificação por IA)
 *
 * Relação com o modelo de camadas (OSI / TCP-IP) visto em aula:
 *  - Camada de acesso à rede (física/enlace): rádio Wi-Fi 2,4 GHz
 *    integrado ao ESP32, usado por WiFi.begin();
 *  - Camada de internet: endereçamento IP obtido via DHCP do
 *    roteador (WiFi.localIP());
 *  - Camada de transporte: conexão TCP estabelecida internamente
 *    pela biblioteca PubSubClient com o broker MQTT;
 *  - Camada de aplicação: protocolo MQTT (mqttClient.publish()),
 *    responsável por formatar e distribuir as mensagens.
 *
 * Observação: nesta etapa (Entrega 1) o objetivo é demonstrar a
 * aquisição de dados e a comunicação IoT. A classificação por IA
 * (normal / letárgico / agitado / possível febre) será treinada
 * separadamente em Python/Colab a partir dos dados coletados aqui,
 * e integrada nas próximas entregas.
 *
 * Hardware:
 *  - ESP32 Dev Kit
 *  - MPU6050 (acelerômetro/giroscópio) - I2C (SDA=21, SCL=22)
 *  - DS18B20 (temperatura) - pino digital (ONE_WIRE_BUS)
 *  - Buzzer/LED (atuador) - pino digital, configurado como saída
 *    (pinMode(BUZZER_PIN, OUTPUT)), seguindo o mesmo padrão de
 *    controle de GPIO visto nos exemplos de LED em aula
 */

#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- CONFIGURAÇÕES (AJUSTAR ANTES DE USAR) ----------
const char* WIFI_SSID     = "NOME_DA_SUA_REDE";
const char* WIFI_PASSWORD = "SENHA_DA_SUA_REDE";

const char* MQTT_BROKER   = "broker.hivemq.com"; // broker público para testes iniciais
const int   MQTT_PORT     = 1883;
const char* MQTT_TOPIC    = "anima/dados";
const char* MQTT_CLIENT_ID = "anima_esp32_01";

// ---------- PINOS ----------
#define ONE_WIRE_BUS 4     // pino do sensor de temperatura DS18B20
#define BUZZER_PIN   5     // pino do buzzer/LED (atuador)

// ---------- OBJETOS ----------
Adafruit_MPU6050 mpu;
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// ---------- UNIDADES DO PAYLOAD ----------
// accel_x/y/z em m/s^2; gyro_x/y/z em graus/segundo (°/s); temperatura em °C.
// A biblioteca Adafruit_MPU6050 entrega o giroscópio em rad/s, por isso a leitura
// é convertida para °/s antes de montar o JSON, para casar com a unidade do
// dataset usado no treinamento do modelo de IA.
const float RAD_TO_DEG_FACTOR = 57.2958; // 180/PI

// ---------- VARIÁVEIS ----------
unsigned long lastRead = 0;
const long READ_INTERVAL = 2000; // leitura a cada 2 segundos

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // Inicializa MPU6050
  Wire.begin();
  if (!mpu.begin()) {
    Serial.println("ERRO: MPU6050 não encontrado. Verifique as conexões.");
  } else {
    Serial.println("MPU6050 conectado com sucesso.");
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  }

  // Inicializa sensor de temperatura
  tempSensor.begin();

  // Conecta ao Wi-Fi
  connectWiFi();

  // Configura MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastRead >= READ_INTERVAL) {
    lastRead = now;
    lerEEnviarDados();
  }
}

void connectWiFi() {
  Serial.print("Conectando ao Wi-Fi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi conectado!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nFalha ao conectar ao Wi-Fi. Tentando novamente no próximo ciclo.");
  }
}

void connectMQTT() {
  Serial.print("Conectando ao broker MQTT...");
  if (mqttClient.connect(MQTT_CLIENT_ID)) {
    Serial.println(" conectado!");
  } else {
    Serial.print(" falhou, rc=");
    Serial.print(mqttClient.state());
    Serial.println(" tentando novamente em breve.");
  }
}

void lerEEnviarDados() {
  // Leitura do acelerômetro/giroscópio
  sensors_event_t a, g, temp_mpu;
  mpu.getEvent(&a, &g, &temp_mpu);

  // Leitura da temperatura corporal (sensor externo)
  tempSensor.requestTemperatures();
  float temperaturaCorporal = tempSensor.getTempCByIndex(0);

  // Converte o giroscópio de rad/s (biblioteca) para °/s (unidade do dataset/modelo)
  float gyroX = g.gyro.x * RAD_TO_DEG_FACTOR;
  float gyroY = g.gyro.y * RAD_TO_DEG_FACTOR;
  float gyroZ = g.gyro.z * RAD_TO_DEG_FACTOR;

  // Monta o payload em JSON simples para envio (gyro_* em °/s)
  String payload = "{";
  payload += "\"accel_x\":" + String(a.acceleration.x, 3) + ",";
  payload += "\"accel_y\":" + String(a.acceleration.y, 3) + ",";
  payload += "\"accel_z\":" + String(a.acceleration.z, 3) + ",";
  payload += "\"gyro_x\":" + String(gyroX, 3) + ",";
  payload += "\"gyro_y\":" + String(gyroY, 3) + ",";
  payload += "\"gyro_z\":" + String(gyroZ, 3) + ",";
  payload += "\"temperatura\":" + String(temperaturaCorporal, 2);
  payload += "}";

  Serial.println(payload);

  // Envia via MQTT (para consumo posterior pelo modelo de IA)
  if (mqttClient.connected()) {
    mqttClient.publish(MQTT_TOPIC, payload.c_str());
  }

  // Alerta local simples de exemplo (temporário nesta etapa):
  // caso a temperatura ultrapasse um limiar, aciona o buzzer.
  // Aqui usamos digitalWrite(pino, HIGH/LOW), o mesmo comando de
  // saída digital estudado em aula para acender/apagar um LED —
  // a diferença é que a decisão de ligar/desligar depende agora
  // de uma leitura de sensor, e não de um delay() fixo.
  // Nas próximas entregas, essa decisão será feita pelo modelo de IA
  // treinado, e não por um limiar fixo como este.
  if (temperaturaCorporal > 39.5) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }
}
