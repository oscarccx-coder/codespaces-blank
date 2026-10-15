"""Windows/offscreen smoke tests for the real PySide6 vehicle-starting UI."""
import tempfile
import unittest

from PySide6.QtWidgets import QApplication, QPushButton, QComboBox, QLabel

from apollo_vehicle_starting_test import save_starting_test
from modules.vehicle_diagnostics.module import Module


class VehicleStartingWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_starting_controls_exist_and_saved_report_opens(self):
        class OfflineService:
            def list_ports(self):
                return []

        with tempfile.TemporaryDirectory() as folder:
            module = Module({"base_dir": folder})
            module.service = OfflineService()
            page = module.build_ui()
            try:
                buttons = {b.text(): b for b in page.findChildren(QPushButton)}
                self.assertIn("Start Starting-System Test", buttons)
                self.assertIn("Mark Key Turn", buttons)
                self.assertIn("Stop & Analyse", buttons)
                self.assertIn("Load Latest Test", buttons)
                self.assertFalse(buttons["Start Starting-System Test"].isEnabled())
                self.assertFalse(buttons["Mark Key Turn"].isEnabled())
                self.assertFalse(buttons["Stop & Analyse"].isEnabled())
                self.assertTrue(buttons["Load Latest Test"].isEnabled())
                selectors = page.findChildren(QComboBox)
                self.assertTrue(any(
                    c.findText("Ford Fiesta (2008)") >= 0 for c in selectors
                ))
                report = {
                    "type": "starting_system_test",
                    "source": "vehicle", "simulated": False, "samples": [],
                    "analysis": {
                        "minimum_sampled_voltage_v": 9.2,
                        "baseline_sampled_voltage_v": 12.6,
                        "voltage_source": "adapter (ATRV)",
                        "max_sampled_rpm": 0,
                        "samples": 0,
                        "status": "observations_only",
                        "summary": "Voltage sag, cause unconfirmed.",
                        "cautions": [],
                    },
                }
                save_starting_test(report, folder)
                buttons["Load Latest Test"].click()
                self.app.processEvents()
                labels = [l.text() for l in page.findChildren(QLabel)]
                self.assertTrue(any("Loaded saved starting-system report" in text
                                    for text in labels), labels)
                self.assertFalse(any("Report could not be saved" in text
                                     for text in labels), labels)
            finally:
                page.close()
                page.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
