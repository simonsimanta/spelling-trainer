from datetime import date

from sqlalchemy import select

from app.backend import models, repository, schemas
from app.backend.db import Base, SessionLocal, engine
from app.backend.spelling import error_analysis, oxford
from scripts import load_oxford_core5k


def _seed() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        repository.seed_defaults(db)


def test_oxford_parser_reads_entries_without_pdf_metadata_tokens() -> None:
    text = """
    The Oxford 3000 is the list of the 3000 most important words to learn in English, from A1 to B2 level.
    a, an indefinite article A1
    abandon v. B2
    academic adj.B1, n. B2
    according to prep. A2
    bank (money) n. A1
    all right adj./adv., exclam. A2
    advanced adj. B1
    """

    assert oxford.extract_terms_from_text(text) == [
        "abandon",
        "academic",
        "bank",
        "advanced",
    ]


def test_diagnostic_excludes_function_words_and_metadata_fragments() -> None:
    _seed()
    with SessionLocal() as db:
        for rank, term in enumerate(("the", "is", "to", "in", "adj", "advanced"), start=1):
            word = repository.create_spelling_word(
                db,
                schemas.SpellingWordCreate(term=term, level="core5k", source="oxford"),
            )
            word.frequency_rank = rank
            word.diagnostic_status = "untested"
            review = repository._ensure_spelling_review(db, word)
            review.due_date = date.today()
        db.commit()

        ranked = repository._diagnostic_candidate_words(db, target_size=50)
        selected = {item.word.term for item in ranked}

    assert {"the", "is", "to", "in", "adj"}.isdisjoint(selected)
    assert "advanced" in selected


def test_diagnostic_ranks_spelling_challenge_above_short_simple_word() -> None:
    _seed()
    with SessionLocal() as db:
        able = repository.create_spelling_word(
            db,
            schemas.SpellingWordCreate(term="able", level="core5k", source="oxford"),
        )
        accommodation = db.scalar(
            select(models.SpellingWord).where(models.SpellingWord.term == "accommodation")
        )
        assert accommodation is not None
        able.frequency_rank = 1
        accommodation.frequency_rank = 500
        able.diagnostic_status = "untested"
        accommodation.diagnostic_status = "untested"
        db.commit()

        ranked = repository._rank_words(
            db,
            [able, accommodation],
            models.SpellingSessionType.diagnostic,
        )

    assert ranked[0].word.term == "accommodation"
    assert ranked[0].score.breakdown["spelling_value"] > ranked[1].score.breakdown["spelling_value"]


def test_transfer_validation_uses_loaded_words_without_reparsing_pdfs(monkeypatch) -> None:
    _seed()
    with SessionLocal() as db:
        db.add(
            models.SpellingWord(
                term="occurrence",
                level="core5k",
                source="oxford",
                mastery_state="new",
            )
        )
        db.commit()
        source_word = db.scalar(
            select(models.SpellingWord).where(models.SpellingWord.term == "necessary")
        )
        assert source_word is not None
        analysis = error_analysis.immediate_analysis("necessary", "necesary")
        monkeypatch.setattr(
            error_analysis,
            "oxford_terms",
            lambda: (_ for _ in ()).throw(AssertionError("Oxford PDFs should not be parsed")),
        )

        validated = error_analysis.validate_transfer_candidates(db, source_word, analysis)

    assert {candidate["term"] for candidate in validated} == {
        "embarrass",
        "accommodation",
        "occurrence",
    }


def test_command_line_oxford_loader_does_not_generate_word_content(monkeypatch, tmp_path) -> None:
    _seed()
    monkeypatch.setattr(
        load_oxford_core5k,
        "extract_terms_from_pdf",
        lambda _path: ["orthography"],
    )

    with SessionLocal() as db:
        stats, terms = load_oxford_core5k.ingest_source(
            "oxford_5000",
            tmp_path / "source.pdf",
            False,
            db,
        )
        word = db.scalar(
            select(models.SpellingWord).where(models.SpellingWord.term == "orthography")
        )
        assert word is not None
        assert word.content_cache is None

    assert stats["created"] == 1
    assert terms == {"orthography"}
