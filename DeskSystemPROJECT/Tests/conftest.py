"""Shared pytest setup for the Sprint 2 tests."""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = PROJECT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))


@pytest.fixture(scope="session")
def test_database_url():
    """Require a dedicated database so tests cannot erase real project data."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL tests")

    database_name = urlsplit(url).path.lstrip("/")
    if not database_name.endswith("_test"):
        pytest.fail(
            "Safety check: TEST_DATABASE_URL must point to a database whose "
            "name ends in '_test' (for example group7_desksystem_test)."
        )
    return url


@pytest.fixture(scope="session")
def create_test_schema(test_database_url):
    """Create a clean schema in the dedicated test database."""

    migrations = sorted(
        (REPOSITORY_DIR / "database").glob("[0-9][0-9][0-9]_*.sql")
    )

    with psycopg2.connect(test_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DROP TABLE IF EXISTS desk_incidents, "
                "group_operation_desks, group_operations, "
                "cleaning_runs, cleaning_schedule_desks, "
                "cleaning_schedules, desk_commands, desk_errors, "
                "desk_readings, desk CASCADE;"
            )

            for migration in migrations:
                cursor.execute(
                    migration.read_text(encoding="utf-8")
                )


@pytest.fixture
def postgres_test_db(monkeypatch, test_database_url, create_test_schema):
    """Use the test database and clear rows before each test."""

    monkeypatch.setenv("DATABASE_URL", test_database_url)

    with psycopg2.connect(test_database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "TRUNCATE desk_incidents, group_operation_desks, "
                "group_operations, desk_commands, desk_errors, "
                "desk_readings, desk RESTART IDENTITY CASCADE;"
            )


@pytest.fixture
def query_test_db(test_database_url, postgres_test_db):
    """Small helper for inspecting persisted rows in assertions."""
    def query(sql, params=None):
        with psycopg2.connect(test_database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
    return query
