# Roteiro de teste manual no Wokwi

> **Status:** 5 cenários já foram executados no Wokwi via CLI (`teste_wokwi_cli/`, ver `relatorio_testes.md`, seção 5; guia em `wokwi_cli.md`): boot, payload,
> Wi-Fi/MQTT, `set-control` do DS18B20/MPU6050, GPIO 18 e laço com o servidor. **Continuam pendentes aqui** as linhas 7 (fail-safe de 15 s), 9 (fio do DS18B20
> removido), 10–11 (MPU ausente/religado) e 13 (rede caída), além de ver o buzzer/LED piscar. O texto original segue abaixo.
> O que já se sabe: as duas variantes **compilam** para ESP32 Dev Module com o `arduino-cli` (ver `relatorio_testes.md`).
> Este roteiro serve para você executar e preencher. Os resultados "esperados" abaixo são previsões a partir do
> código, não observações.

## Preparação

1. Em https://wokwi.com crie um projeto novo **ESP32** (não reaproveite o projeto antigo, para não misturar arquivos).
2. Substitua/crie os 4 arquivos com o conteúdo de `v2/firmware/wokwi/`: `sketch.ino`, `config.h` (botão de novo arquivo),
   `diagram.json`, `libraries.txt`. Se mudou o firmware, rode antes `python v2/firmware/gerar_wokwi.py`.
3. Em `config.h`, troque `ANIMA_ID` pelo **seu** id único (gere com `python -c "import secrets; print('anima-' + secrets.token_hex(4))"`; abaixo, `<SEU_ID>`).
   O padrão `anima-TROQUE-ESTE-ID` colide com o de qualquer pessoa. O broker `broker.hivemq.com` é público; use só dados de teste.
4. No terminal, com o mesmo id:
   ```bash
   cd v2/servidor
   python consumidor_v2.py --id <SEU_ID>
   ```
5. Inicie a simulação (▶) e abra o Serial Monitor.

Dica de conexão: o diagrama usa o buzzer e o LED no **GPIO 18** (não mais o 5).

## Como mexer nos sensores

* **MPU6050:** clique no componente durante a simulação. Os campos de aceleração (g) e rotação (°/s) são **constantes**:
  não geram ruído nem variação. Por isso o desvio padrão da janela fica ≈ 0 e o modelo tende a ver "parado". Só dá para
  ver `normal`/`agitado` de verdade mudando valores manualmente no meio da simulação, ou publicando payloads simulados (`v2/servidor/tests/cenarios_e2e.py`).
* **DS18B20:** clique no componente e ajuste o slider de temperatura.
* Para simular **sensor desconectado** (-127): apague o fio entre `temp1:DQ` e `esp:4` (ou o do `r1`) durante a simulação.
* Para simular **MPU ausente**: apague os fios SDA/SCL do `imu1` e reinicie a simulação.

## Roteiro (preencha a coluna "Obtido")

| # | Ação no Wokwi | Esperado no Serial Monitor | Esperado no servidor | Obtido | OK? |
|---|---|---|---|---|---|
| 1 | Iniciar, valores padrão (accel 0/0/1 g, rotação 0, temp 38,5) | `MPU6050 conectado.`, `Wi-Fi conectado. IP: ...`, `Conectando ao broker MQTT... conectado!`, depois um JSON a cada ~2 s | mensagens `PARADO (~9x%)`, `final=nenhum` | | |
| 2 | Conferir o JSON | `"versao":2`, `"id":"<seu id>"`, `n_amostras` ≈ 50, `accel_mag_media` ≈ 9.8, `accel_mag_std` ≈ 0, `gyro_mag_media` ≈ 0, `temperatura` ≈ 38.5, `sensor_ok:true`, `mpu_ok:true` | — | | |
| 3 | DS18B20 → 38,3 (normal) | `temperatura` ≈ 38.3 | `PARADO`, `final=nenhum`, LED apagado | | |
| 4 | DS18B20 → **40,1** (parado + febre) | JSON com `temperatura` ≈ 40.1 | 1ª janela: `FEBRE`, `bruta=alerta final=nenhum`; 2ª janela: `final=alerta` + `[NOTIFICAÇÃO]` | | |
| 5 | (mesmo estado do 4) | `Decisão recebida: {"acao": "alerta", ...}` após a 2ª janela | publica em `anima/<id>/decisao` | | |
| 6 | (mesmo estado do 4) observar o LED | LED **aceso contínuo**: a proteção local (> 39,5 °C) tem prioridade sobre o padrão do servidor e atua desde a 1ª leitura (≈ 1 s) | — | | |
| 7 | Parar o servidor (Ctrl+C) com temp 38,5; antes, deixe chegar um `alerta` | LED pisca rápido (alerta do servidor) e **apaga sozinho ~15 s** depois da última decisão (fail-safe) | servidor parado | | |
| 8 | Servidor parado, DS18B20 → 40,1 | LED aceso contínuo em ≈ 1 s (proteção local independente); volta a apagar quando a temp cair abaixo de 39,2 | — | | |
| 9 | Remover o fio do DS18B20 | JSON com `"temperatura":null,"sensor_ok":false` | `leitura descartada - sensor_ok=false`; nenhuma decisão publicada | | |
| 10 | Reiniciar sem os fios SDA/SCL do MPU | `ERRO: MPU6050 não encontrado (nova tentativa em breve).`; JSON com `n_amostras:0`, `"mpu_ok":false` | `leitura descartada - mpu_ok=false` | | |
| 11 | Religar os fios do MPU (sem reiniciar) | em até ~10 s: `MPU6050 conectado.` e as janelas voltam ao normal | decisões voltam | | |
| 12 | Mudar rotação para valores altos (ex.: 200/200/200) e aceleração (ex.: 1/1/1,5), temp 38,5 | `gyro_mag_media` e `accel_mag_media` mudam | anote a classe e a confiança (**não há previsão confiável**: valores constantes não existem no treino sintético) | | |
| 13 | Derrubar a rede (se possível, parar/reiniciar a simulação com broker indisponível) | mensagens de reconexão sem travar a amostragem; `Wi-Fi não conectou; nova tentativa em ms: ...` com intervalos crescentes | — | | |
| 14 | **Compilar no editor web do Wokwi** com o `libraries.txt` desta pasta (versões fixas + BusIO). Clique em ▶ e veja se compila | compila sem erro; anote as versões que o Wokwi realmente instalou (o CLI usa o binário local, não o compilador do site) | `Adafruit BusIO` resolvido sozinho ou exigido? | | |

## O que anotar se algo falhar

* Mensagem exata do Serial Monitor (copie/cole).
* Se o erro é de **compilação** (o Wokwi usa seu próprio toolchain/versões de bibliotecas, que podem diferir das usadas no teste local:
  ESP32 core 3.3.12, Adafruit MPU6050 2.2.9, OneWire 2.3.8, DallasTemperature 4.0.6, PubSubClient 2.8).
* Se o Wokwi não encontrar `config_local.h`: é esperado, ele é opcional (`__has_include`).
* Se a conexão Wi-Fi demorar: o canal 6 e o SSID `Wokwi-GUEST` vêm de `config.h` quando `ANIMA_WOKWI` está definido.
