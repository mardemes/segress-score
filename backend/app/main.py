"""API FastAPI do SEGRESS-Score.

Fluxo: POST /evaluations (PDF) -> extrai e classifica -> status needs_confirmation
-> POST /evaluations/{id}/confirm (usuário confirma/corrige o tipo) -> checks -> done.
"""
from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, llm, pipeline
from .checklist import TYPE_INDEX, load_checklist
from .classify import TYPES
from .scoring import score

log = logging.getLogger('segress')
MAX_BYTES = 25 * 1024 * 1024
FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'
_pool = ThreadPoolExecutor(max_workers=2)

app = FastAPI(title='SEGRESS-Score', version='1.0.0')


def run_async(fn, *args) -> None:
    """Executa em segundo plano; SEGRESS_SYNC=1 executa na hora (testes)."""
    if os.environ.get('SEGRESS_SYNC') == '1':
        fn(*args)
    else:
        _pool.submit(fn, *args)


@app.on_event('startup')
def _startup() -> None:
    db.init()


# ---------- tarefas em segundo plano ----------

def task_analyze(eid: str, forced_type: str | None, auto: bool) -> None:
    try:
        db.update(eid, status='extracting', progress=0.05)
        ev = db.get(eid)
        doc, cls = pipeline.analyze(ev['pdf_path'])
        if not doc.pages or len(doc.text.strip()) < 500:
            db.update(eid, status='failed', error='Não foi possível extrair texto do PDF (arquivo escaneado ou vazio?).')
            return
        db.update(eid, classification=cls, tertiary=cls['tertiary'], progress=0.15)
        if forced_type or (auto and cls['supported']):
            task_check(eid, forced_type or cls['type'], cls['tertiary'])
        else:
            db.update(eid, status='needs_confirmation', study_type=cls['type'])
    except Exception as e:
        log.exception('falha na análise')
        db.update(eid, status='failed', error=f'{type(e).__name__}: {e}')


def task_check(eid: str, study_type: str, tertiary: bool) -> None:
    try:
        db.update(eid, status='checking', study_type=study_type, tertiary=tertiary, progress=0.2)
        ev = db.get(eid)
        doc = pipeline.extract(ev['pdf_path'])

        def progress(done: int, total: int) -> None:
            db.update(eid, progress=0.2 + 0.75 * done / total)

        results = pipeline.run_checks(doc, study_type, tertiary, progress)
        report = score(load_checklist(), results, study_type, tertiary)
        report['llm'] = {'used': llm.available(), 'model': llm.model() if llm.available() else None}
        report['title'] = doc.title
        db.update(eid, results=results, report=report, status='done', progress=1.0, error=None)
    except Exception as e:
        log.exception('falha nas verificações')
        db.update(eid, status='failed', error=f'{type(e).__name__}: {e}')


# ---------- modelos ----------

class Confirm(BaseModel):
    study_type: str = Field(pattern='^(quant|mapping|qual)$')
    tertiary: bool = False


class Override(BaseModel):
    score: float | None = Field(default=None, description='0, 0.5, 1 ou null para remover o ajuste')


def _public(ev: dict) -> dict:
    return {
        'id': ev['id'], 'filename': ev['filename'], 'status': ev['status'], 'progress': round(ev['progress'] or 0, 2),
        'study_type': ev['study_type'], 'tertiary': ev['tertiary'], 'classification': ev.get('classification'),
        'error': ev.get('error'),
    }


def _get_or_404(eid: str) -> dict:
    ev = db.get(eid) if len(eid) == 32 and eid.isalnum() else None
    if not ev:
        raise HTTPException(404, 'Avaliação não encontrada.')
    return ev


# ---------- rotas ----------

@app.get('/health')
def health() -> dict:
    return {'ok': True, 'llm': llm.available(), 'model': llm.model() if llm.available() else None,
            'items': len(load_checklist())}


@app.post('/evaluations', status_code=202)
async def create_evaluation(file: UploadFile = File(...), study_type: str | None = Form(None), auto: bool = Form(False)) -> dict:
    if study_type and study_type not in TYPE_INDEX:
        raise HTTPException(422, f'study_type deve ser um de {list(TYPES)}.')
    eid = uuid.uuid4().hex
    path = db.UPLOAD_DIR / f'{eid}.pdf'
    db.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(path, 'wb') as out:
        head = await file.read(5)
        if not head.startswith(b'%PDF'):
            path.unlink(missing_ok=True)
            raise HTTPException(415, 'O arquivo enviado não é um PDF.')
        out.write(head)
        size = len(head)
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, 'PDF maior que 25 MB.')
            out.write(chunk)
    name = os.path.basename(file.filename or 'artigo.pdf')[:200]
    db.create(eid, name, str(path))
    run_async(task_analyze, eid, study_type, auto)
    return {'id': eid, 'status': 'queued'}


@app.get('/evaluations/{eid}')
def get_evaluation(eid: str) -> dict:
    return _public(_get_or_404(eid))


@app.post('/evaluations/{eid}/confirm', status_code=202)
def confirm(eid: str, body: Confirm) -> dict:
    ev = _get_or_404(eid)
    if ev['status'] in ('queued', 'extracting', 'checking'):
        raise HTTPException(409, 'A avaliação ainda está em andamento.')
    if ev['status'] == 'failed' and not ev.get('classification'):
        raise HTTPException(409, 'A avaliação falhou antes da classificação; envie o PDF novamente.')
    db.update(eid, status='checking', study_type=body.study_type, tertiary=body.tertiary, progress=0.2)
    run_async(task_check, eid, body.study_type, body.tertiary)
    return {'id': eid, 'status': 'checking'}


@app.patch('/evaluations/{eid}/study-type', status_code=202)
def change_type(eid: str, body: Confirm) -> dict:
    return confirm(eid, body)


@app.get('/evaluations/{eid}/report')
def get_report(eid: str) -> dict:
    ev = _get_or_404(eid)
    if ev['status'] != 'done' or not ev.get('report'):
        raise HTTPException(409, f'Relatório indisponível (status: {ev["status"]}).')
    return {**_public(ev), 'report': ev['report']}


@app.patch('/evaluations/{eid}/items/{code}')
def override_item(eid: str, code: str, body: Override) -> dict:
    ev = _get_or_404(eid)
    if ev['status'] != 'done':
        raise HTTPException(409, 'Só é possível ajustar itens de uma avaliação concluída.')
    if body.score is not None and body.score not in (0, 0.5, 1):
        raise HTTPException(422, 'score deve ser 0, 0.5 ou 1.')
    results = ev['results']
    if code not in results:
        raise HTTPException(404, 'Item não avaliado nesta revisão (não se aplica ao tipo de estudo).')
    results[code]['override'] = body.score
    report = score(load_checklist(), results, ev['study_type'], ev['tertiary'])
    report['llm'] = ev['report'].get('llm')
    report['title'] = ev['report'].get('title')
    db.update(eid, results=results, report=report)
    return {**_public(db.get(eid)), 'report': report}


@app.get('/')
def index() -> FileResponse:
    return FileResponse(FRONTEND / 'index.html')


app.mount('/static', StaticFiles(directory=FRONTEND), name='static')
