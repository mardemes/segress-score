# SEGRESS-Score

Serviço web que recebe o PDF de uma revisão sistemática de engenharia de software, classifica o tipo
(quantitativa, mapeamento, qualitativa), executa 42 verificações derivadas da Tabela 9 do SEGRESS
(Kitchenham, Madeyski e Budgen, *IEEE TSE* 49(3), 2023) e devolve uma nota de 0 a 100 com a evidência
encontrada em cada item.

> A nota mede a **qualidade do relato**, não a validade científica da revisão. Pesos, limiares de nível e
> regra de teto são propostas iniciais e precisam ser calibrados com avaliadores humanos.

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
| Parcial | sem chave | Itens `R` pontuados por regra; `RL` com nota provisória por regra; `L` ficam "não verificados" e saem do cálculo. Se a cobertura do peso obrigatório for menor que 70%, o nível não é atribuído |

## Fluxo

1. `POST /evaluations` (multipart `file`) extrai o texto e classifica o tipo (status `needs_confirmation`).
2. O usuário confirma ou corrige o tipo: `POST /evaluations/{id}/confirm` `{study_type, tertiary}`.
3. As verificações rodam em segundo plano; `GET /evaluations/{id}` informa status e progresso.
4. `GET /evaluations/{id}/report` devolve nota, nível, nota por seção e os itens com evidência, página e o que falta.
5. `PATCH /evaluations/{id}/items/{code}` `{score}` registra ajuste humano e recalcula a nota.
6. `PATCH /evaluations/{id}/study-type` muda o tipo e reavalia.

Artigos que não parecem revisões sistemáticas (narrativas, opinião, diretrizes) são sinalizados na classificação;
o usuário pode forçar o tipo, ciente de que a nota perde o sentido.

## Escala

- Cada item: 1 (completo), 0,5 (parcial), 0 (ausente). Itens obrigatórios (O) formam a nota-base ponderada por peso (1 a 3);
  opcionais (P) dão até 5 pontos de bônus; não aplicáveis (–) saem do cálculo.
- Teto: item crítico obrigatório (peso 3) com nota 0 limita o nível a C.
- Níveis: A (90–100), B (75–89), C (60–74), D (40–59), E (0–39).
- Estudo terciário: itens 14 e 15 deixam de se aplicar.

O checklist (pesos, aplicabilidade, perguntas e critérios) fica em `backend/app/checklist.yaml`; altere-o sem mexer no código.

## Estrutura

```
backend/app/
  main.py        rotas FastAPI e tarefas em segundo plano
  extract.py     PyMuPDF -> título, resumo, trechos por seção e página
  classify.py    tipo de estudo e se é revisão sistemática (regras + LLM opcional)
  checklist.yaml os 42 itens
  rules.py       verificações por regra
  llm.py         verificação por LLM com saída estruturada e conferência da citação
  pipeline.py    recuperação de trechos e orquestração
  scoring.py     fórmula, teto, níveis, nota por seção
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
