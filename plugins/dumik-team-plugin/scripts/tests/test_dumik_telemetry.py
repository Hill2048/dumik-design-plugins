import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import dumik_telemetry as mod


class DumikTelemetryTests(unittest.TestCase):
    def test_build_payload_has_expected_feishu_schema(self):
        payload = mod.build_payload(event="invoke", skill="d-image-director", mode="repair-prepare-single", host="antigravity")
        self.assertEqual(payload["event"], "invoke")
        self.assertEqual(payload["skill"], "d-image-director")
        self.assertEqual(payload["mode"], "repair-prepare-single")
        self.assertEqual(payload["host"], "antigravity")
        self.assertEqual(len(payload["device_id"]), 12)
        self.assertTrue(payload["plugin_version"])
        self.assertIn("T", payload["timestamp"])

    def test_suppressed_under_pytest_and_env_flag(self):
        with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "some_test"}):
            self.assertFalse(mod.report_event_async(event="invoke", skill="d-init"))
            self.assertEqual(mod.send_event_sync(event="invoke", skill="d-init")["status"], "suppressed")

        with mock.patch.dict(os.environ, {"DUMIK_TELEMETRY_DISABLED": "1"}, clear=False):
            os.environ.pop("PYTEST_CURRENT_TEST", None)
            self.assertFalse(mod.report_event_async(event="invoke", skill="d-init"))

    def test_async_spawns_detached_subprocess_when_not_suppressed(self):
        with mock.patch.dict(os.environ, {}, clear=False) as env_copy:
            env_copy.pop("PYTEST_CURRENT_TEST", None)
            env_copy.pop("DUMIK_TELEMETRY_DISABLED", None)
            with mock.patch.object(mod.subprocess, "Popen") as popen_mock:
                ok = mod.report_event_async(event="invoke", skill="d-project-pipeline", mode="status", host="antigravity")
                self.assertTrue(ok)
                popen_mock.assert_called_once()
                args = popen_mock.call_args[0][0]
                self.assertIn("--send-now", args)
                self.assertIn("d-project-pipeline", args)
                self.assertIn("status", args)


if __name__ == "__main__":
    unittest.main()
