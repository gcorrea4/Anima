/*
 * Anima v2 - Configuração do firmware (único lugar a editar).
 *
 * Segredos (senha do Wi-Fi, usuário/senha do broker) NÃO devem ficar neste
 * arquivo versionado: crie um "config_local.h" ao lado (ele está no .gitignore)
 * com os #define que quiser sobrescrever. Veja config_local.h.example.
 *
 * A variante do Wokwi é gerada por gerar_wokwi.py: é uma cópia deste arquivo
 * com "#define ANIMA_WOKWI" no topo (Wi-Fi "Wokwi-GUEST", canal 6, sem senha).
 */
#pragma once

#if __has_include("config_local.h")
#include "config_local.h"
#endif

// ---------- Wi-Fi ----------
#ifdef ANIMA_WOKWI
  #define WIFI_SSID_PADRAO     "Wokwi-GUEST"
  #define WIFI_SENHA_PADRAO    ""
  #define WIFI_CANAL_PADRAO    6      // canal da rede virtual do Wokwi
#else
  #define WIFI_SSID_PADRAO     "NOME_DA_SUA_REDE"
  #define WIFI_SENHA_PADRAO    "SENHA_DA_SUA_REDE"   // sobrescreva em config_local.h
  #define WIFI_CANAL_PADRAO    0      // 0 = automático
#endif
#ifndef WIFI_SSID
  #define WIFI_SSID  WIFI_SSID_PADRAO
#endif
#ifndef WIFI_SENHA
  #define WIFI_SENHA WIFI_SENHA_PADRAO
#endif
#ifndef WIFI_CANAL
  #define WIFI_CANAL WIFI_CANAL_PADRAO
#endif

// ---------- MQTT ----------
// ATENÇÃO: broker.hivemq.com é PÚBLICO (qualquer um lê e escreve). Use só com
// dados de teste. Para dados reais, use um broker próprio com usuário/senha.
#ifndef MQTT_BROKER
  #define MQTT_BROKER  "broker.hivemq.com"
#endif
#ifndef MQTT_PORTA
  #define MQTT_PORTA   1883
#endif
#ifndef MQTT_USUARIO
  #define MQTT_USUARIO ""     // vazio = conexão sem autenticação
#endif
#ifndef MQTT_SENHA
  #define MQTT_SENHA   ""
#endif

// Identificador do dispositivo. Tópicos: anima/<id>/dados e anima/<id>/decisao.
// No broker público, use um id SEU, único (gere: python -c "import secrets; print('anima-' + secrets.token_hex(4))") para não
// misturar com o de outras pessoas. Só letras, números, '-' e '_'.
#ifndef ANIMA_ID
  #define ANIMA_ID "anima-TROQUE-ESTE-ID"
  #warning "ANIMA_ID padrao em uso: defina um id UNICO em config_local.h (o broker publico e compartilhado e ids iguais colidem)."
#endif

// ---------- Pinos ----------
#define PINO_ONE_WIRE 4    // DS18B20
#define PINO_ATUADOR  18   // buzzer + LED (mesmo pino). GPIO 5 é pino de strapping; 18 é seguro.
#define PINO_SDA      21   // MPU6050
#define PINO_SCL      22

// ---------- Janela de amostragem ----------
#define TAXA_AMOSTRAGEM_HZ 25      // ~25 Hz
#define JANELA_MS          2000    // estatísticas publicadas a cada 2 s (50 amostras)

// ---------- Temperatura ----------
// IMPORTANTE: o DS18B20 na coleira mede pele/ambiente, não a temperatura
// corporal. Este limiar local (proteção independente da IA/servidor) precisa
// ser recalibrado com dados reais, junto com o offset_coleira do modelo.
#define LIMIAR_TEMP_LOCAL_C   39.5f
#define HISTERESE_TEMP_C      0.3f

// ---------- Atuador ----------
// Se o servidor parar de mandar decisões, o alerta recebido expira (fail-safe).
#define DECISAO_TIMEOUT_MS    15000

// ---------- Reconexão (backoff exponencial) ----------
#define BACKOFF_MIN_MS        2000
#define BACKOFF_MAX_MS        60000
#define WIFI_TENTATIVA_MS     10000   // tempo máximo de uma tentativa de WiFi.begin
#define MQTT_TIMEOUT_S        3       // timeout do socket (o connect() é a única parte bloqueante)
#define MPU_REINIT_MS         10000   // nova tentativa de iniciar o MPU6050 se falhou
