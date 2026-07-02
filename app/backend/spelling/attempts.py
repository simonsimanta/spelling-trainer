from sqlalchemy.orm import Session

from app.backend import repository, schemas


def submit_attempt(db: Session, payload: schemas.SpellingAttemptCreate) -> schemas.SpellingAttemptResult:
    return repository.submit_spelling_attempt(db, payload)


def submit_correction(
    db: Session, attempt_id: int, payload: schemas.SpellingCorrectionSubmit
) -> schemas.SpellingCorrectionResult:
    return repository.submit_spelling_correction(db, attempt_id, payload)

