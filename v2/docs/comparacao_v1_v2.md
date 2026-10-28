# Comparação modelo v1 × v2

> **Todos os números abaixo vêm de dados sintéticos.** Nada foi validado em hardware nem em animais reais.
> As métricas de v1 e v2 usam datasets diferentes (leitura instantânea × estatísticas de janela) e
> **não são comparáveis diretamente**; a tabela de cenários é a comparação mais honesta disponível.

| | v1 (Entrega 2) | v2 |
|---|---|---|
| Entrada | 1 leitura instantânea (9 variáveis) | janela de 2 s a 25 Hz: média/desvio/máx de accel_mag e gyro_mag + temperatura (7 variáveis) |
| Classes | normal, letargico, agitado, febre | parado, normal, agitado, febre |
| Acurácia no teste sintético | 0.9625 | 0.9396 |
| Hiperparâmetros | RF 200 árvores, prof. 8, seed 42 | iguais |

## Cenários explícitos

| Cenário | v1: classe | v1: probabilidades | v2: classe | v2: probabilidades |
|---|---|---|---|---|
| Parado, temperatura normal (38,3 °C) | letargico | letargico=100% | parado | parado=97%, febre=3% |
| Movimento normal (38,6 °C) | normal | normal=92%, febre=4%, agitado=3% | normal | normal=95%, parado=3%, febre=2% |
| Agitado (38,8 °C) | normal | normal=93%, febre=3%, agitado=3% | agitado | agitado=98%, febre=2% |
| Movimento normal + febre (40,1 °C) | febre | febre=98%, normal=2% | febre | febre=95%, normal=5% |
| PARADO + FEBRE (40,1 °C) | letargico | letargico=46%, febre=46%, normal=8% | febre | febre=93%, parado=7% |

Teste explícito v2 (parado + 40,1 °C): **febre** (febre=93%, parado=7%).

## Observações

- Os cenários da v2 são valores escolhidos à mão, coerentes com o gerador sintético; não são medições.
- Para a v1 cada cenário é UMA leitura instantânea escolhida por mim (ex.: 'agitado' com giroscópio de ~15 °/s, que o v1 vê como normal). Uma única leitura de um animal agitado pode cair em qualquer ponto; isso ilustra a fragilidade da leitura instantânea, mas não prova que o v1 erra em geral.
- A v1 não tinha a combinação *parado + febre* no treino; veja a linha correspondente acima para o comportamento real do pkl da v1.
- A v2 separa febre quase só pela temperatura por construção do gerador (classes truncadas em 39,5 °C). Com dados reais, esse limite será nebuloso.
- A confusão remanescente da v2 é entre *parado* e *normal*, causada pelas janelas 'mistas' do gerador (mudança de comportamento no meio da janela).
- O modelo v1 e os arquivos da Entrega 2 não foram alterados.
