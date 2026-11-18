"""Dashboard reads must recover a moving group even after its warning expires."""

import unittest
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from DeskSystemPROJECT.Domain.group_operations import GroupOperationService
from DeskSystemPROJECT.group_operations_api import get_group_service, router


class DashboardOperationsTests(unittest.TestCase):
    def test_reload_can_discover_warning_dispatch_and_cancelled_result(self):
        workflow = Mock()
        workflow.api.get_desk.return_value = {"state": {"status": "Normal"}}
        clock = Mock(return_value=0)
        # Queue the worker without sending commands, to inspect the dispatch transition.
        service = GroupOperationService(lambda: workflow, clock=clock, spawn=Mock())
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_group_service] = lambda: service
        with TestClient(app) as client:
            path = "/api/group-operations"
            manual = client.post(path, json={"desk_ids": ["desk-a"], "target_position_mm": 1000})
            self.assertEqual(manual.status_code, 201)
            cancelled_id = manual.json()["operation_id"]
            client.post(f"{path}/{cancelled_id}/cancel").raise_for_status()
            scheduled = service.create(["desk-b"], 1200, reason="Scheduled cleaning: raise desks")
            current = client.get(path).json()
            self.assertEqual([op["state"] for op in current], ["pending_warning", "cancelled"])
            self.assertEqual(current[0]["reason"], scheduled.reason)
            self.assertEqual(current[1]["desks"][0]["result"], "cancelled")
            for channel in service.settings.required_channels:
                client.post(f"{path}/{scheduled.operation_id}/acknowledge", json={"channel": channel}).raise_for_status()
            clock.return_value = service.settings.countdown_s
            service.tick()
            self.assertFalse(client.get(path + "/active-warning").json()["warning_active"])
            self.assertEqual(client.get(path).json()[0]["state"], "dispatching")
