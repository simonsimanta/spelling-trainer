from datetime import date

from sqlalchemy.orm import Session

from app.backend import repository, schemas


def overview(db: Session, as_of: date) -> schemas.SpellingOverview:
    return repository.get_spelling_overview(db, as_of)


def analytics(db: Session) -> schemas.SpellingAnalyticsOut:
    return repository.get_spelling_analytics(db)


def core5k_overview(db: Session) -> schemas.Core5KOverviewOut:
    return repository.get_core5k_overview(db)


def mode_overview(db: Session) -> schemas.SpellingModesOverviewOut:
    return repository.get_spelling_modes_overview(db)

