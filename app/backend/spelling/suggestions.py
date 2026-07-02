from typing import Optional

from sqlalchemy.orm import Session

from app.backend import models, repository, schemas


def list_suggestions(db: Session, status: str = "pending") -> list[models.SpellingSuggestion]:
    return repository.list_spelling_suggestions(db, status=status)


def update_suggestion(
    db: Session, suggestion_id: int, payload: schemas.SpellingSuggestionAction
) -> Optional[models.SpellingSuggestion]:
    return repository.update_spelling_suggestion(db, suggestion_id, payload)

