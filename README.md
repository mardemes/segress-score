# SEGRESS-Score

Serviço web que recebe o PDF de uma revisão sistemática de engenharia de software, classifica o tipo
(quantitativa, mapeamento, qualitativa), avalia os 28 itens da Tabela 9 do SEGRESS
(Kitchenham, Madeyski e Budgen, *IEEE TSE* 49(3), 2023) e devolve uma nota de 0 a 100 com a evidência
encontrada em cada item.

> A avaliação mede a **qualidade do relato**, não a validade científica da revisão.

## Executar

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # opcional, habilita o modo completo
export LLM_MODEL=claude-sonnet-4-6  # opcional, modelo usado nos itens
uvicorn app.main:app --port 8000
# abra http://localhost:8000
```

Com Docker: `docker compose up --build` (porta 8000; dados em `./data`).

### Modos de operação

| Modo | Condição | Comportamento |
| --- | --- | --- |
| Completo | `ANTHROPIC_API_KEY` definida | Itens `RL` e `L` são julgados pelo LLM, com citação literal conferida no texto |
| Parcial | sem chave | Itens `R` pontuados por regra; `RL` com nota provisória por regra; `L` ficam "não verificados" e saem do cálculo. Se menos de 70% dos pontos obrigatórios forem verificados, a classificação fica indeterminada |

## Fluxo

1. `POST /evaluations` (multipart `file`) extrai o texto e classifica o tipo (status `needs_confirmation`).
2. O usuário confirma ou corrige o tipo: `POST /evaluations/{id}/confirm` `{study_type, practice}`.
3. As verificações rodam em segundo plano; `GET /evaluations/{id}` informa status e progresso.
4. `GET /evaluations/{id}/report` devolve classificação, score, pontos, falhas críticas e os 28 itens com justificativa, evidência, página e o que falta.
5. `PATCH /evaluations/{id}/items/{code}` `{score}` registra ajuste humano do item (code = 1 a 27 ou opening) e recalcula.
6. `PATCH /evaluations/{id}/study-type` muda o tipo e reavalia.

Artigos que não parecem revisões sistemáticas (narrativas, opinião, diretrizes) são sinalizados na classificação;
o usuário pode forçar o tipo, ciente de que a nota perde o sentido.

## Como a avaliação é feita

- **28 itens** da Tabela 9 do SEGRESS: os 27 do PRISMA 2020 mais o item "Opening" da Introdução. Os itens 10, 13, 16, 20, 23 e 24
  são verificados pelos seus subitens (43 verificações no total).
- **Aplicabilidade por tipo de estudo**, conforme a Tabela 9: revisão quantitativa/mista, mapeamento sistemático (também estudos
  terciários sobre métodos de pesquisa) e revisão qualitativa. Os itens 14 e 15 não se aplicam a estudos que investigam práticas
  de pesquisa em ES.
- **Cada item:** Sim = 1, Parcial = 0,5, Não = 0, a pontuação usada por Kitchenham et al. (2009) nos critérios DARE em estudos
  terciários de ES. Item com subitens: Sim se todos os subitens obrigatórios são atendidos, Não se nenhum, Parcial nos demais casos.
  Informação ausente conta como Não.
- **Peso 2** nos 10 itens críticos (5, 6, 7, 8, 11, 13, 15, 16, 22, 23), que correspondem às informações essenciais da Tabela 2 do
  SEGRESS (Budgen et al., 2018); peso 1 nos demais.
- **Score** (0–100) = pontos obtidos ÷ pontos possíveis nos itens obrigatórios. Itens opcionais aparecem, mas não entram no score.
- **Classificação** pela regra do AMSTAR 2 (Shea et al., BMJ 2017): falha crítica = item crítico com Não; fraqueza = item não
  crítico com Não. Ótimo: nenhuma falha crítica e até 1 fraqueza; Bom: nenhuma falha crítica e 2 ou mais fraquezas; Ruim: 1 falha
  crítica; Muito ruim: 2 ou mais. Os autores do AMSTAR 2 desaconselham somar notas para a classificação geral, por isso o score
  é um complemento para comparar artigos, e a classificação vem da regra de falhas críticas.
- Cada item traz a justificativa, os subitens, a citação literal do artigo com a página e o que falta. O avaliador pode ajustar
  o veredito de qualquer item.

O checklist (itens, subitens, aplicabilidade, perguntas e critérios) fica em `backend/app/checklist.yaml`.

## Estrutura

```
backend/app/
  main.py        rotas FastAPI e tarefas em segundo plano
  extract.py     PyMuPDF -> título, resumo, trechos por seção e página
  classify.py    tipo de estudo e se é revisão sistemática (regras + LLM opcional)
  checklist.yaml os 28 itens e os 43 subitens
  rules.py       verificações por regra
  llm.py         verificação por LLM com saída estruturada e conferência da citação
  pipeline.py    recuperação de trechos e orquestração
  scoring.py     pontos por item, score e classificação AMSTAR 2
  db.py          SQLite
backend/tests/   pytest (nota, regras, pipeline com LLM simulado, API ponta a ponta)
frontend/        página única (upload, confirmação de tipo, relatório)
```

## Limitações conhecidas e próximos passos

- Extração só com PyMuPDF; artigos de duas colunas ou escaneados (sem OCR) podem sair truncados. GROBID é o próximo passo.
- Tarefas em segundo plano usam um pool de threads no processo. Para produção, troque por Celery + Redis e SQLite por PostgreSQL.
- Sem autenticação nem limite de uso; adicione antes de expor publicamente. O PDF enviado é tratado como dado não confiável
  (o prompt manda ignorar instruções contidas no artigo), mas isso não elimina o risco de injeção de prompt.
- Material suplementar fora do PDF (protocolo, dados) não é lido.
- Falta validar a nota contra avaliadores humanos (30 a 50 revisões, kappa por item); sem isso, não use a nota para decisões reais.
- Os itens 2, 4 e outros marcados `RL` no YAML usam regra + LLM; o desenho original previa `R+L` também para 8, 13c e 17, que nesta versão são só LLM.

## Versão web sem servidor (`web/`)

`web/segress-score.html` roda inteira no navegador: lê o PDF com pdf.js (com barra de progresso), aplica as regras e a avaliação em JavaScript, mostra as recomendações de melhoria e exporta um relatório em PDF (pdfmake)
e, quando publicada como página no Claude, usa o próprio Claude da página para julgar os itens que exigem leitura
(sem chave de API; o uso conta na cota do Claude de quem avalia). Gere-a a partir do checklist com `python web/build.py`.
