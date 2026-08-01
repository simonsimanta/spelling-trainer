"""Harden the Supabase Data API boundary and index foreign keys."""

from typing import Sequence, Union

from alembic import op


revision: str = "20260801_0010"
down_revision: Union[str, None] = "20260730_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PUBLIC_TABLES = (
    "alembic_version",
    "learner_profile",
    "app_settings",
    "spelling_words",
    "spelling_word_content",
    "spelling_word_sources",
    "spelling_reviews",
    "spelling_sessions",
    "spelling_session_items",
    "spelling_attempts",
    "spelling_suggestions",
    "spelling_patterns",
    "spelling_word_patterns",
    "spelling_confusion_groups",
    "spelling_confusion_group_words",
    "spelling_user_pattern_stats",
    "spelling_audio_manifest",
    "spelling_feedback_cache",
    "activity_events",
    "achievements",
)

DATA_API_ROLES = ("anon", "authenticated", "service_role")
BROWSER_ROLES = ("anon", "authenticated")
DENY_POLICY = "deny_browser_data_api"

FOREIGN_KEY_INDEXES = (
    ("ix_activity_events_word_id", "activity_events", ["word_id"]),
    ("ix_spelling_attempts_word_id", "spelling_attempts", ["word_id"]),
    ("ix_spelling_confusion_group_words_word_id", "spelling_confusion_group_words", ["word_id"]),
    ("ix_spelling_suggestions_word_id", "spelling_suggestions", ["word_id"]),
    ("ix_spelling_word_patterns_pattern_id", "spelling_word_patterns", ["pattern_id"]),
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _roles(roles: tuple[str, ...]) -> str:
    return ", ".join(f'"{role}"' for role in roles)


def upgrade() -> None:
    for index_name, table_name, columns in FOREIGN_KEY_INDEXES:
        op.create_index(index_name, table_name, columns, unique=False)

    if not _is_postgresql():
        return

    browser_roles = _roles(BROWSER_ROLES)
    data_api_roles = _roles(DATA_API_ROLES)

    for table_name in PUBLIC_TABLES:
        op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{DENY_POLICY}" ON public."{table_name}" '
            f"AS RESTRICTIVE FOR ALL TO {browser_roles} USING (false) WITH CHECK (false)"
        )

    op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA public FROM {data_api_roles}")
    op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {data_api_roles}")
    op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {data_api_roles}")
    op.execute(f"REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM {data_api_roles}")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")

    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        f"REVOKE ALL PRIVILEGES ON TABLES FROM {data_api_roles}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        f"REVOKE ALL PRIVILEGES ON SEQUENCES FROM {data_api_roles}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        f"REVOKE ALL PRIVILEGES ON FUNCTIONS FROM {data_api_roles}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
    )


def downgrade() -> None:
    if _is_postgresql():
        browser_roles = _roles(BROWSER_ROLES)
        data_api_roles = _roles(DATA_API_ROLES)

        op.execute(f"GRANT USAGE ON SCHEMA public TO {data_api_roles}")
        op.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {data_api_roles}")
        op.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {data_api_roles}")
        op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {data_api_roles}, PUBLIC")

        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT ALL PRIVILEGES ON TABLES TO {data_api_roles}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT ALL PRIVILEGES ON SEQUENCES TO {data_api_roles}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT ALL PRIVILEGES ON FUNCTIONS TO {data_api_roles}"
        )
        op.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            "GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
        )

        for table_name in reversed(PUBLIC_TABLES):
            op.execute(f'DROP POLICY "{DENY_POLICY}" ON public."{table_name}"')
            op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')

    for index_name, table_name, _ in reversed(FOREIGN_KEY_INDEXES):
        op.drop_index(index_name, table_name=table_name)
