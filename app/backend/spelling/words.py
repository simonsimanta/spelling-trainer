from typing import Optional

from sqlalchemy.orm import Session

from app.backend import models, repository, schemas


def list_words(db: Session, level: Optional[str] = None) -> list[models.SpellingWord]:
    normalized_level = None if level in {None, "", "all"} else level
    return repository.list_spelling_words(db, level=normalized_level)


def create_word(db: Session, payload: schemas.SpellingWordCreate) -> models.SpellingWord:
    return repository.create_spelling_word(db, payload)

