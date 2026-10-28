# Anima — Módulo de Inteligência Artificial (Entrega 2)

## Contexto e transparência

O hardware físico (ESP32, MPU6050, DS18B20) ainda não foi adquirido pelo
grupo. Para cumprir o requisito da Entrega 2 de ter uma **primeira versão
funcional da IA**, foi gerado um **dataset sintético**, fisiologicamente
plausível, que simula as leituras que o sensor produziria em cada estado
comportamental do pet. O modelo foi treinado e validado sobre esses dados
reais (sintéticos, mas processados de verdade — não são números inventados
para o relatório). Assim que os componentes forem adquiridos (previsto
para a Entrega 3), os dados sintéticos serão substituídos por leituras
reais e o modelo será retreinado com o mesmo pipeline.

## Como rodar (em ordem)

```bash
pip install pandas numpy scikit-learn matplotlib seaborn joblib

python 01_gerar_dataset.py        # gera dataset_anima_sintetico.csv
python 02_treinar_modelo.py       # treina e avalia o modelo, salva modelo_anima_rf.pkl
python 03_gerar_graficos.py       # gera os gráficos (matriz de confusão, etc.)
python 04_exemplo_inferencia.py   # simula o uso do modelo em "produção"
```

## O que cada dado significa

| Etapa | O quê | Para quê |
|---|---|---|
| Dados usados | accel_x/y/z, gyro_x/y/z, temperatura (+ magnitudes derivadas) | Mesmas variáveis que o ESP32 publica via MQTT |
| Tratamento | Cálculo de magnitude do vetor (accel_mag, gyro_mag); divisão treino/teste estratificada (80/20) | Enriquecer o modelo com relações não lineares entre eixos e evitar viés de classe |
| Algoritmo | Random Forest (200 árvores, profundidade máx. 8) | Bom desempenho com poucas features, interpretável, leve |
| Treinamento | `RandomForestClassifier.fit()` sobre 1.600 amostras | Ajustar o modelo aos padrões de cada classe |
| Entradas do modelo em uso | 1 leitura do sensor (payload MQTT) | Simula o que o ESP32 enviaria a cada 2 segundos |
| Saída do modelo | Uma classe: normal / letárgico / agitado / febre + probabilidade | Decide se e qual alerta disparar |
| Resultado no sistema | Aciona buzzer local e/ou notificação no app conforme a classe e a confiança | Fecha o ciclo sensor → IA → decisão → atuação |

## Resultados obtidos (reais, não estimados)

- **Acurácia no conjunto de teste:** 96,25%
- **F1-score (macro):** 0,9627
- Ver `classification_report.txt` para o detalhamento por classe
- Ver `grafico_matriz_confusao.png` para os erros do modelo (poucos, e concentrados entre "normal" e "agitado" — esperado, já que são estados mais próximos)
- Ver `grafico_feature_importance.png`: a temperatura e a magnitude do giroscópio são as variáveis mais decisivas — consistente com a lógica clínica do problema
- Ver `grafico_dispersao_classes.png` para uma visualização de como as classes se separam no espaço de features

## Arquivos gerados

- `dataset_anima_sintetico.csv` — dataset completo (2.000 amostras, 500 por classe)
- `modelo_anima_rf.pkl` — modelo treinado, pronto para ser carregado por um serviço consumidor de MQTT
- `classification_report.txt` — métricas detalhadas
- `feature_importances.csv` — importância de cada variável
- `grafico_*.png` — gráficos para uso direto no artigo
- `04_exemplo_inferencia.py` — mostra o modelo classificando 3 cenários novos e decidindo a ação do sistema

## Limitação declarada

Os dados de treinamento são sintéticos. A distribuição estatística foi
definida com base em literatura de acelerometria animal e em suposições
razoáveis (ex: temperatura de referência ~38,5°C para cães/gatos), mas
**não substitui dados reais**. A acurácia de 96% reflete a separabilidade
dos dados sintéticos gerados, e é esperado que caia (o que é normal e
será discutido na Entrega 3) quando o modelo for testado com dados reais,
mais ruidosos e com sobreposição maior entre classes.
