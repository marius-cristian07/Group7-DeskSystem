# Checks SQL parameters and transaction handling in the data repositories.
# Mock connections/cursors replace PostgreSQL; these tests do not write real rows.

import unittest
from unittest.mock import MagicMock, patch

import psycopg2

from DeskSystemPROJECT.Data import database, desk_repository, desk_command_repository
from DeskSystemPROJECT.Tests.fixtures import sample_desk


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        # This is the cursor returned by "with connection.cursor() as cursor".
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = (42,)
        self.connect = self.enterContext(patch.object(database, "get_database_connection", return_value=self.connection))

    def test_snapshot_is_one_transaction_with_ordered_errors(self):
        record = sample_desk()
        self.assertEqual(desk_repository.save_desk(record), 42)
        calls = self.cursor.execute.call_args_list
        self.assertEqual(calls[0].args[1], (record["desk_id"], "DESK 4486", "Desk-O-Matic Co."))
        self.assertEqual(calls[1].args[1], (record["desk_id"], 1320, 0, "Normal", 67, 18, False, False, False, False))
        self.assertEqual([call.args[1] for call in calls[2:]], [
            (42, index, error["time_s"], error["errorCode"])
            for index, error in enumerate(record["lastErrors"])
        ])
        self.connect.assert_called_once()
        self.connection.__exit__.assert_called_once_with(None, None, None)
        self.connection.close.assert_called_once()

    def test_failed_reading_rolls_back_and_closes(self):
        self.cursor.execute.side_effect = [None, psycopg2.Error("write failed")]
        with self.assertRaisesRegex(database.DatabaseError, "Database operation failed"):
            desk_repository.save_desk(sample_desk())
        self.assertIs(self.connection.__exit__.call_args.args[0], psycopg2.Error)
        self.connection.close.assert_called_once()

    def test_identity_has_no_reading(self):
        desk_command_repository.save_desk_identity(sample_desk())
        self.cursor.execute.assert_called_once()
        self.assertNotIn("desk_readings", self.cursor.execute.call_args.args[0])

    def test_command_keeps_requested_height(self):
        self.assertEqual(desk_command_repository.save_command("desk-1", 2000, "accepted"), 42)
        self.assertEqual(self.cursor.execute.call_args.args[1], ("desk-1", 2000, "accepted"))

    def test_invalid_status_does_not_open_a_connection(self):
        with self.assertRaises(ValueError):
            desk_command_repository.save_command("desk-1", 900, "complete")
        self.connect.assert_not_called()

    def test_uncertain_command_can_be_recorded(self):
        self.assertEqual(desk_command_repository.save_command("desk-1", 1000, "unknown"), 42)
        self.assertEqual(self.cursor.execute.call_args.args[1], ("desk-1", 1000, "unknown"))

    def test_desk_exists_handles_missing_row(self):
        self.cursor.fetchone.return_value = None
        self.assertFalse(desk_command_repository.desk_exists("missing"))
        self.connection.close.assert_called_once()
