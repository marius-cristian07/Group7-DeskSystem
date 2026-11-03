# Shared PostgreSQL access for the reading and command repositories.
# Use 'with transaction() as cursor' to run related queries together: either all
# queries commit or they roll back on failure, and the connection is always closed.

"""Connection and transaction handling shared by the repositories."""

from contextlib import contextmanager
import os

import psycopg2


class DatabaseError(Exception):
    """The database could not be reached or a query failed."""


def get_database_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise DatabaseError("DATABASE_URL is not set. Add it before saving desk data.")
    try:
        return psycopg2.connect(database_url)
    except psycopg2.Error as error:
        raise DatabaseError(f"Failed to connect to PostgreSQL: {error}") from None


@contextmanager
def transaction():
    connection = get_database_connection()
    try:
        # psycopg commits on success and rolls back on an exception. Closing the
        # connection is separate; its context manager does not do that for us.
        with connection, connection.cursor() as cursor:
            # The repository runs its queries here, inside this transaction.
            yield cursor
    except psycopg2.Error as error:
        raise DatabaseError(f"Database operation failed: {error}") from None
    finally:
        connection.close()
