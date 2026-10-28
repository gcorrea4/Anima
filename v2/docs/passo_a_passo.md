# Passo a passo para o grupo

Comandos em PowerShell/terminal, a partir da pasta `v2/`. O firmware compila e já rodou no simulador Wokwi (pelo CLI), mas **nunca em hardware real**
— se algo falhar, anote a mensagem de erro (veja `docs/teste_wokwi.md`).

## 0. Preparar o ambiente Python

```bash
pip install -r servidor/requirements-dev.txt     # versões FIXADAS (inclui pytest e a IA); testado com Python 3.14
copy .env.example servidor\.env                  # Linux/Mac: cp .env.example servidor/.env   (depois edite servidor/.env)
python -c "import secrets; print('anima-' + secrets.token_hex(4))"     # gera o SEU id único: use-o abaixo no lugar de <SEU_ID>
```

> **Use sempre um id só seu** (`<SEU_ID>`, por exemplo `anima-3f9c1a7e`). O broker padrão é público e compartilhado: ids de exemplo copiados dos
> docs colidem com os de outras pessoas. O `servidor/requirements.txt` fixa o `scikit-learn==1.9.1` porque o `.pkl` foi treinado com ele.

## 1. Rodar no Wokwi

1. Abra o projeto (https://wokwi.com/projects/477095234339984385) ou crie um novo ESP32 com os mesmos componentes.
2. Se alterou o firmware, regenere a variante do Wokwi: `python firmware/gerar_wokwi.py`.
3. No Wokwi, substitua o conteúdo de `sketch.ino`, `config.h`, `diagram.json` e `libraries.txt` pelos arquivos de
   `firmware/wokwi/` (crie `config.h` com o botão de novo arquivo). O `libraries.txt` já fixa as versões usadas na compilação local
   (inclui o `Adafruit BusIO`); **compilar no editor web do Wokwi precisa ser conferido manualmente** (veja `docs/teste_wokwi.md`).
4. **Mude o `ANIMA_ID` no `config.h`** para o seu id único (`<SEU_ID>`, gerado na seção 0). O firmware tem o padrão `anima-TROQUE-ESTE-ID` e **avisa na
   compilação** (`#warning`) se você esquecer; esse padrão colidiria com o de qualquer outra pessoa no broker público. Use o mesmo id no servidor (`--id <SEU_ID>`).
5. Inicie a simulação. O monitor serial deve mostrar "Wi-Fi conectado", "conectado!" (MQTT) e um JSON a cada 2 s.
6. Para provocar situações: clique no MPU6050 e altere aceleração/rotação durante a simulação; clique no DS18B20
   e mude a temperatura (ex.: 40,1 para o cenário *parado + febre*). Os valores do MPU no Wokwi são constantes,
   então o desvio padrão da janela fica ~0 (parece "parado"); varie-os manualmente para ver outros estados.
7. O GPIO 18 aciona o buzzer e o LED: `alerta` pisca rápido, `alerta_leve` dá um pulso a cada 1,5 s, e temperatura
   local > 39,5 °C mantém ligado contínuo (proteção independente do servidor).

## 2. Rodar o servidor

```bash
cd servidor
python consumidor_v2.py --selftest          # confere o fluxo sem rede (usa o offset_coleira do modelo carregado)
python consumidor_v2.py --id <SEU_ID>       # --id é OBRIGATÓRIO (ou --todos, veja abaixo)
```

Opções úteis: `--janelas 3` (janelas consecutivas antes de alertar; padrão 2), `--intervalo-notif 600`,
`--limiar-confianca 0.6`, `--temp-seguranca 39.5`, `--parado-letargia 0`, `--nao-publicar`, `--log arquivo.csv`.
O log vai para `servidor/logs/decisoes_log.csv`.

**Modo de assinatura e segurança.** Sem `--id` (e sem `--todos`) o servidor **não inicia**. `--todos` assina `anima/+/dados` (todos os dispositivos) e só deve ser usado em broker próprio/local;
em broker **público** (broker.hivemq.com, test.mosquitto.org, broker.emqx.io...) ele é recusado, a menos que você confirme com `--aceito-risco-publico`, porque o servidor processaria dados
de terceiros, publicaria decisões em tópicos de outras pessoas e qualquer um poderia forjar payloads para disparar notificações no seu Telegram. Medidas adicionais: o campo `"id"` do payload
precisa ser igual ao id do tópico (senão a mensagem é ignorada e registrada); `--todos` aceita no máximo `--max-dispositivos` dispositivos distintos (padrão 20, os demais são ignorados);
o estado de debounce é limitado (descarta o dispositivo mais antigo).

Variáveis de ambiente (ou `.env`): `ANIMA_MQTT_HOST/PORT/USER/PASS/TLS`, `ANIMA_TELEGRAM_TOKEN`,
`ANIMA_TELEGRAM_CHAT_ID`. **O broker padrão é público; não use dados reais.**

Como funciona a decisão: o modelo classifica cada janela; `febre` ou `agitado` com confiança ≥ 0,6 geram `alerta`;
temperatura ≥ limiar de segurança (39,5 °C + `offset_coleira`) gera `alerta` mesmo que o modelo discorde; só depois
de N janelas consecutivas com a mesma ação a decisão é publicada e a notificação é enviada.
Notificações: no máximo uma por (dispositivo, **causa**, ação) a cada `--intervalo-notif` segundos (padrão **300**). A causa é `temperatura_alta`
(regra de segurança ou classe febre), `agitado` ou `letargia`; então uma febre logo depois de uma agitação notifica na hora, e a mesma causa repetida fica limitada.
O envio ao Telegram roda em **segundo plano** (fila de até `--fila-telegram` mensagens, 20 por padrão; se encher, descarta a mais antiga; timeout curto de 4 s + 6 s):
a decisão publicada nunca espera o Telegram. O resultado de cada envio vai para o log (`envio_telegram`: `enviado` / `erro: ...` / `descartado: ...`), sem o token.
Ctrl+C encerra limpo (tenta esvaziar a fila por até 5 s).

**Testes automáticos nunca devem usar o `.env` real:** o servidor carrega o `.env` sozinho, então os testes definem `ANIMA_SEM_DOTENV=1` (senão mandariam mensagens
de teste ao seu Telegram de verdade). Se você criar um teste novo que sobe `consumidor_v2.py`, faça o mesmo.

## 3. Criar o bot do Telegram e ligar ao servidor

1. No Telegram, procure **@BotFather**, envie `/newbot`, escolha nome e usuário (terminado em `bot`).
2. Ele devolve o **token**. Trate como senha: não publique, não coloque em código, não mande em chat/print/relatório.
3. Abra uma conversa com o seu bot, aperte **Iniciar** e envie uma mensagem. Para grupo, adicione o bot e escreva nele.
4. Crie `v2/servidor/.env` (ele é ignorado pelo git; o modelo está em `v2/.env.example`) com:
   ```
   TELEGRAM_BOT_TOKEN=<token do BotFather>
   TELEGRAM_CHAT_ID=<id do chat>
   ```
   (os nomes antigos `ANIMA_TELEGRAM_TOKEN` / `ANIMA_TELEGRAM_CHAT_ID` continuam aceitos). Nada de aspas nem espaços ao redor do `=`.
5. Validar o token e descobrir o chat id **sem expor o token** (o script abaixo só imprime o username e o final do id):
   ```python
   import re, requests
   tok = re.search(r"TELEGRAM_BOT_TOKEN=(\S+)", open("v2/servidor/.env").read()).group(1)
   me = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=15).json()["result"]; print("@" + me["username"])
   up = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=15).json()["result"]
   print({(u["message"]["chat"]["id"]) for u in up if "message" in u})   # este é o seu chat id (guarde só no .env)
   ```
   Se `getUpdates` vier vazio, envie outra mensagem ao bot e tente de novo (pode demorar alguns segundos; webhook ativo também bloqueia o `getUpdates`).
   Cuidado: **não** cole a URL `https://api.telegram.org/bot<TOKEN>/...` em chats, prints ou issues.
6. Ao iniciar, o servidor imprime `Telegram: ATIVO`. Sem as variáveis ele só imprime no terminal.
7. Teste real (mini-broker local, dispositivo simulado): `python servidor/tests/teste_telegram_real.py`
   (use `--falha token_invalido|chat_errado|sem_internet` para os casos de falha).

Formato da mensagem recebida: dispositivo, ação, classe com confiança, temperatura da coleira, motivo e horário.

Falhas do Telegram nunca derrubam o servidor: ele continua classificando e publicando decisões, e a coluna `telegram` do
log CSV (`servidor/logs/decisoes_log.csv`) registra `enviado`, `desativado` ou `erro: ...` (por exemplo `HTTP 401 Unauthorized`,
`HTTP 400 Bad Request: chat not found`, `ConnectionError`), sempre sem o token. As chamadas ao Telegram rodam **em segundo plano** com timeout de 4 s (conexão) + 6 s (leitura): um Telegram lento ou fora do ar
não atrasa nem bloqueia a classificação, e a decisão publicada em `anima/<id>/decisao` nunca espera o envio.

Se o token vazar, gere outro no @BotFather (`/revoke`) e atualize o `.env`.

## 4. Coletar dados reais (quando houver hardware)

```bash
cd servidor
python coletar_dados.py --id <SEU_ID> --rotulo parado --animal Thor --obs "dormindo no sofá, coleira solta"
python coletar_dados.py --id <SEU_ID> --rotulo normal --animal Thor --max-janelas 300
```

* Rótulos: `parado`, `normal`, `agitado`, `febre`. **Uma sessão = um rótulo**; mudou o comportamento, nova sessão.
* Cada CSV fica em `servidor/dados_reais/` com `timestamp, sessao_id, id_dispositivo, animal, observacoes`, as 7
  variáveis do modelo, `classe` e `origem=real` — as mesmas colunas do dataset v2, então dá para concatenar.
* Leituras inválidas (-127, sensor_ok=false, MPU fora) são descartadas e contadas. As 3 primeiras janelas de cada
  sessão são ignoradas (`--descartar-iniciais`).
* **Nunca provoque febre ou estresse num animal.** Use o rótulo `febre` apenas se um veterinário/termômetro clínico
  confirmou. Anote também a temperatura retal/clínica em `--obs` para calibrar o offset.
* Colete de vários animais e em várias situações (cômodos, horários, tipos de coleira); senão o modelo decora um
  único animal.
* Com broker público, os dados são visíveis a todos. Use broker próprio.

## 5. Retreinar

1. Calibre o offset: compare a temperatura da coleira com a clínica (veja `docs/hardware.md`). Se a coleira lê, por
   exemplo, ~4 °C a menos, use `offset_coleira = -4` e regenere o sintético com a mesma escala:
   ```bash
   cd ia
   python gerar_dataset_v2.py --offset-coleira -4
   ```
   (ou edite `params_sinteticos.json`). Atualize também `LIMIAR_TEMP_LOCAL_C` no `config.h`.
2. Retreine combinando sintético + real:
   ```bash
   python retreinar.py --real ../servidor/dados_reais/*.csv --offset-coleira -4 --peso-real 3
   ```
   Gera `modelo_anima_rf_v2_real.pkl` (+ `.meta.json`), relatório, matriz de confusão e importância. Não sobrescreve
   o modelo sintético. `--so-real` ignora o sintético. **Guarda contra sobrescrita:** `treinar_modelo_v2.py` e `retreinar.py --sufixo v2` pedem
   confirmação (ou `--sim`) antes de sobrescrever o modelo **oficial** (`ia/modelo_anima_rf_v2.pkl`, usado pelos testes); sem terminal e sem `--sim` eles recusam.
   Para treinar sem tocar no oficial: `python treinar_modelo_v2.py --dataset <csv> --offset-coleira -4 --saida-dir <pasta>`.
3. Rode o servidor com o novo modelo: `python consumidor_v2.py --modelo ../ia/modelo_anima_rf_v2_real.pkl`
   (o limiar de segurança vem do `.meta.json`; sobrescreva com `--temp-seguranca` se calibrou outro valor). O `--selftest` também lê o `offset_coleira`
   do `.meta.json` do modelo carregado e aplica aos cenários, então funciona com modelos recalibrados: `python consumidor_v2.py --modelo ../ia/modelo_anima_rf_v2_real.pkl --selftest`.
4. Cuidado ao ler as métricas: o split é aleatório por janela, e janelas vizinhas da mesma sessão aparecem em treino
   e teste, o que **infla** a acurácia. Para uma avaliação honesta, separe sessões/animais inteiros para teste.

## 6. Testes

```bash
cd servidor
python -m pytest tests -q
python ../firmware/gerar_wokwi.py --check     # wokwi/ em dia com a fonte
```

## 7. Wokwi pelo CLI

`python teste_wokwi_cli/executar.py` roda 5 cenários no simulador (precisa de arduino-cli, wokwi-cli e do token do Wokwi **só em variável de ambiente**).
Instalação, variáveis, uso e limites: [wokwi_cli.md](wokwi_cli.md).

## 8. Pacote para a equipe

```bash
python empacotar.py              # gera ../v2_para_equipe.zip e lista os arquivos
python empacotar.py --listar     # só mostra o que entraria (nada é gravado)
```
Exclui `.env`, tokens, logs, dados reais coletados, caches e `build/`; varre o conteúdo e **aborta** se achar padrão de token (Telegram/Wokwi). Detalhes no cabeçalho do script.
