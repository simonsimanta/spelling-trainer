from typing import Optional

from sqlalchemy.orm import Session

from app.backend import models, repository, schemas


def list_words(db: Session, level: Optional[str] = None) -> list[models.SpellingWord]:
    normalized_level = None if level in {None, "", "all"} else level
    return repository.list_spelling_words(db, level=normalized_level)


def create_word(db: Session, payload: schemas.SpellingWordCreate) -> models.SpellingWord:
    return repository.create_spelling_word(db, payload)


def list_managed_words(
    db: Session,
    *,
    query: str = "",
    category: str = "all",
    mastery_state: str = "",
    diagnostic_status: str = "",
    sort: str = "term",
    direction: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> schemas.SpellingWordManagementPage:
    return repository.list_managed_spelling_words(
        db,
        query=query,
        category=category,
        mastery_state=mastery_state,
        diagnostic_status=diagnostic_status,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )


def update_word(
    db: Session,
    word_id: int,
    payload: schemas.SpellingWordUpdate,
) -> models.SpellingWord:
    return repository.update_personal_spelling_word(db, word_id, payload)


def apply_action(
    db: Session,
    word_id: int,
    payload: schemas.SpellingWordAction,
) -> schemas.SpellingWordActionResult:
    return repository.apply_spelling_word_action(db, word_id, payload.action)
