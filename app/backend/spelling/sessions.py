from typing import Optional

from sqlalchemy.orm import Session

from app.backend import repository, schemas


def create_session(db: Session, payload: schemas.SpellingSessionCreate) -> schemas.SpellingSessionOut:
    return repository.create_spelling_session(db, payload)


def get_session(db: Session, session_id: int) -> Optional[schemas.SpellingSessionOut]:
    return repository.get_spelling_session(db, session_id)

