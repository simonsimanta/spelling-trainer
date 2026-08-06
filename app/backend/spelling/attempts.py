from concurrent.futures import Future, ThreadPoolExecutor, wait
import logging
from threading import Lock

from sqlalchemy.orm import Session

from app.backend import repository, schemas
from app.backend.db import SessionLocal
from app.backend.spelling import error_analysis


logger = logging.getLogger(__name__)
_enrichment_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spelling-analysis")
_pending_enrichments: set[Future[None]] = set()
_pending_lock = Lock()


def submit_attempt(
    db: Session,
    payload: schemas.SpellingAttemptCreate,
    *,
    defer_ai: bool = False,
) -> schemas.SpellingAttemptResult:
    return repository.submit_spelling_attempt(db, payload, defer_ai=defer_ai)


def enrich_attempt(attempt_id: int) -> None:
    with SessionLocal() as db:
        error_analysis.enrich_attempt_analysis(db, attempt_id)


def _enrichment_done(future: Future[None]) -> None:
    with _pending_lock:
        _pending_enrichments.discard(future)
    error = future.exception()
    if error is not None:
        logger.warning("Spelling analysis enrichment failed: %s", type(error).__name__)


def schedule_enrichment(attempt_id: int) -> None:
    future = _enrichment_executor.submit(enrich_attempt, attempt_id)
    with _pending_lock:
        _pending_enrichments.add(future)
    future.add_done_callback(_enrichment_done)


def wait_for_enrichment(timeout: float = 10.0) -> None:
    with _pending_lock:
        pending = list(_pending_enrichments)
    if pending:
        wait(pending, timeout=timeout)


def submit_correction(
    db: Session, attempt_id: int, payload: schemas.SpellingCorrectionSubmit
) -> schemas.SpellingCorrectionResult:
    return repository.submit_spelling_correction(db, attempt_id, payload)
