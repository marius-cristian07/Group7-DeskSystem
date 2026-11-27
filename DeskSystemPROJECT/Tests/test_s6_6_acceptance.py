"""S6-6 cross-component acceptance checks using deterministic fakes.

These tests do not contact the simulator, move desks, or connect to PostgreSQL.
The real PostgreSQL persistence tests live in test_s6_2_persistence.py and require
TEST_DATABASE_URL pointing to a disposable database ending in ``_test``.
"""

import unittest
from unittest.mock import Mock

from DeskSystemPROJECT.Domain.desk_faults import classify_faults, movement_outcome
from DeskSystemPROJECT.Domain.review_workflow import ReviewWorkflow


class FaultAcceptanceTests(unittest.TestCase):
    def test_fault_matrix_is_conservative_and_deterministic(self):
        healthy = {"status": "Normal", "position_mm": 1000, "speed_mms": 0}
        self.assertEqual(classify_faults(healthy).classification, "healthy")
        self.assertEqual(classify_faults(None).classification, "unavailable")

        for flag, code in (
            ("isAntiCollision", "collision"),
            ("isPositionLost", "position_lost"),
            ("isOverloadProtectionUp", "overload_up"),
            ("isOverloadProtectionDown", "overload_down"),
        ):
            with self.subTest(flag=flag):
                state = {**healthy, flag: True}
                result = classify_faults(state)
                self.assertEqual(result.classification, "faulty")
                self.assertIn(code, result.faults)
                self.assertEqual(movement_outcome(state, 1000), "desk_error")

    def test_at_target_is_not_clean_success_when_fault_is_present(self):
        state = {
            "status": "Normal", "position_mm": 1000, "speed_mms": 0,
            "isAntiCollision": True,
        }
        self.assertEqual(movement_outcome(state, 1000), "desk_error")

    def test_unreachable_or_unknown_reading_is_not_healthy(self):
        for status in ("", "unknown", "offline", "unreachable"):
            with self.subTest(status=status):
                self.assertTrue(classify_faults({"status": status}).blocks_movement)


class ReviewAcceptanceTests(unittest.TestCase):
    def test_resolving_review_records_evidence_but_never_moves_desk(self):
        repository = Mock()
        repository.get_review_context.return_value = {
            "reviewable": True, "status": "needs_review", "desk_ids": ["desk-a"],
        }
        repository.resolve_run.return_value = {
            "record_id": 55,
            "recorded_at": "2026-11-27T12:00:00+00:00",
            "resolved": {"cleaning_runs": [12], "group_operations": ["op-1"],
                         "desk_incidents": [4]},
        }

        workflow_factory = Mock()
        desk_workflow = Mock()
        workflow_factory.return_value = desk_workflow
        desk_workflow.base_url = "http://simulator.test"
        desk_workflow.api_key = "test-key"
        desk_workflow.api.get_desk.return_value = {
            "state": {"status": "Normal", "position_mm": 1000, "speed_mms": 0},
        }
        desk_workflow.readings.save_desk.return_value = 9
        group_service = Mock()

        review = ReviewWorkflow(workflow_factory, group_service=group_service,
                               repository=repository)
        result = review.resolve_run(
            12, "inspected_ok", "Inspected the desks and confirmed they are safe.", "manager-test",
        )

        self.assertEqual(result["record_id"], 55)
        self.assertEqual(result["resolved"]["cleaning_runs"], [12])
        repository.resolve_run.assert_called_once()
        group_service.note_review_resolved.assert_called_once_with(["op-1"])
        # ReviewWorkflow is read-only with respect to movement; only desk reads are used.
        desk_workflow.api.get_desk.assert_called_once()
        desk_workflow.request_height.assert_not_called()
        self.assertIn("No movement command was sent", result["message"])

    def test_acknowledgement_is_not_resolution(self):
        repository = Mock()
        repository.acknowledge_incident.return_value = {
            "acknowledged_at": "2026-11-27T12:00:00+00:00",
            "recorded_at": "2026-11-27T12:00:00+00:00", "record_id": 56,
        }
        review = ReviewWorkflow(Mock(), repository=repository)
        result = review.acknowledge_incident(4, "Seen and assigned for inspection", "manager-test")
        repository.acknowledge_incident.assert_called_once_with(
            4, "Seen and assigned for inspection", "manager-test",
        )
        self.assertIn("not resolved", result["message"])
        self.assertIn("still blocks automatic starts", result["message"])


if __name__ == "__main__":
    unittest.main()
