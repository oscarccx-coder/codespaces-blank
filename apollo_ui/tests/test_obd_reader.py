"""Hardware-free OBD-II parser/serial transport safety and module tests."""
import importlib.util
import types
import unittest
import tempfile
from pathlib import Path

from apollo_vehicle_starting_test import (
    StartTestControl, analyse_starting_test, capture_starting_test,
    parse_adapter_voltage, save_starting_test,
)
from apollo_obd import (
    ALLOWED_COMMANDS, BAUD_RATES, ELM327Session, OBDService,
    VehicleConnectionError, demo_snapshot, parse_dtcs, parse_live_pid,
)


RESPONSES = {
    "ATZ": b"ELM327 v1.5\r>",
    "ATE0": b"OK\r>", "ATL0": b"OK\r>", "ATS0": b"OK\r>",
    "ATH0": b"OK\r>", "ATSP0": b"OK\r>",
    "010C": b"410C06BB\r>", "010D": b"41 0D 28\r>",
    "0105": b"SEARCHING...\r41 05 5A\r>", "010F": b"410F50\r>",
    "0111": b"7E8 03 41 11 80\r>", "0104": b"410480\r>",
    "010B": b"41 0B 65\r>", "0142": b"41423724\r>",
    "03": b"43 01 33 00 00\r>", "07": b"NO DATA\r>",
    "0A": b"4A 00 00\r>", "ATRV": b"12.6V\r>",
}


class FakeAdapter:
    def __init__(self, responses=None, **kwargs):
        self.args = kwargs
        self.responses = RESPONSES if responses is None else responses
        self.queries = []
        self.last = None
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        self.closed = True

    def reset_input_buffer(self):
        pass

    def write(self, payload):
        self.last = payload.decode("ascii").strip()
        self.queries.append(self.last)
        return len(payload)

    def flush(self):
        pass

    def read_until(self, end, size=None):
        if end != b">" or not 0 < size <= 8192:
            raise AssertionError("Unbounded serial read")
        return self.responses.get(self.last, b"")


class AdapterTests(unittest.TestCase):
    def make_service(self, responses=None):
        adapters = []

        def open_adapter(**kwargs):
            adapter = FakeAdapter(responses=responses, **kwargs)
            adapters.append(adapter)
            return adapter

        ports = lambda: [types.SimpleNamespace(device="COM7", description="Test ELM327")]
        return OBDService(serial_factory=open_adapter, ports_factory=ports), adapters

    def test_standard_pid_decoding(self):
        self.assertEqual(parse_live_pid("010C", "41 0C 06 BB\r>")["value"], 430.75)
        self.assertEqual(parse_live_pid("010D", "410D28>")["value"], 40)
        self.assertEqual(parse_live_pid("0105", "41 05 5A\r>")["value"], 50)
        self.assertEqual(parse_live_pid("0142", "41 42 37 24\r>")["value"], 14.12)
        self.assertIsNone(parse_live_pid("010C", "NO DATA\r>"))
        self.assertIsNone(parse_live_pid("010C", "410C06\r>"))
        self.assertEqual(parse_live_pid("0111", "7E8 03 41 11 80\r>")["value"], 50.2)

    def test_dtc_decoding_and_deduplication(self):
        self.assertEqual(parse_dtcs("43 01 33 00 00\r>", "03"), ["P0133"])
        self.assertEqual(parse_dtcs("43 01 33\r43 01 33\r>", "03"), ["P0133"])
        self.assertEqual(parse_dtcs("47 C1 02\r>", "07"), ["U0102"])
        self.assertEqual(parse_dtcs("NO DATA\r>", "0A"), [])
        with self.assertRaises(ValueError):
            parse_dtcs("44 00 00", "04")

    def test_snapshot_is_real_data_and_commands_are_allowlisted(self):
        service, adapters = self.make_service()
        result = service.snapshot("COM7", baud=38400)
        self.assertFalse(result["simulated"])
        self.assertEqual(result["source"], "vehicle")
        self.assertEqual(result["sensors"]["010C"]["value"], 430.75)
        self.assertEqual(len(result["sensors"]), 8)
        self.assertTrue(adapters[0].closed)
        self.assertEqual(set(adapters[0].queries), set(ALLOWED_COMMANDS - {"03", "07", "0A", "ATI", "ATRV"}))
        self.assertFalse(any(x in adapters[0].queries for x in ("04", "08", "2E", "27", "34")))

    def test_fault_code_reads_never_clear_or_program(self):
        service, adapters = self.make_service()
        data = service.read_codes("COM7")
        self.assertEqual(data["codes"]["stored"], ["P0133"])
        self.assertEqual(data["codes"]["pending"], [])
        self.assertEqual(data["codes"]["permanent"], [])
        self.assertEqual(adapters[0].queries[-3:], ["03", "07", "0A"])
        self.assertNotIn("04", adapters[0].queries)

    def test_explicit_demo_never_opens_hardware(self):
        service, adapters = self.make_service()
        self.assertTrue(service.snapshot(demo=True)["simulated"])
        self.assertTrue(service.read_codes(demo=True)["simulated"])
        self.assertTrue(demo_snapshot()["simulated"])
        self.assertEqual(adapters, [])

    def test_port_and_baud_must_be_approved(self):
        service, adapters = self.make_service()
        for port in ("COM8", "", "socket://evil.example:4000", "/etc/passwd"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                service.snapshot(port)
        for baud in (0, True, 115201, "38400"):
            with self.subTest(baud=baud), self.assertRaises(ValueError):
                service.snapshot("COM7", baud=baud)
        self.assertEqual(adapters, [])

    def test_serial_connection_timeout_is_not_turned_into_demo(self):
        data = dict(RESPONSES)
        data["010C"] = b""
        service, adapters = self.make_service(data)
        result = service.snapshot("COM7")
        self.assertFalse(result["simulated"])
        self.assertIn("010C", result["unsupported_pids"])
        self.assertIn("timed out", result["problems"]["010C"])
        self.assertTrue(adapters[0].closed)

    def test_adapter_init_timeout_raises(self):
        data = dict(RESPONSES)
        data["ATZ"] = b""
        service, adapters = self.make_service(data)
        with self.assertRaises(VehicleConnectionError):
            service.read_codes("COM7")
        self.assertTrue(adapters[0].closed)

    def test_arbitrary_or_mutating_requests_are_rejected(self):
        reader = ELM327Session(FakeAdapter())
        for unsafe in ("04", "2701", "2E00", "010C\r04", "ATSH7E0", "ATMA", "0902"):
            with self.subTest(unsafe=unsafe), self.assertRaises(PermissionError):
                reader.request(unsafe)
        self.assertEqual(reader.port.queries, [])

    def test_vehicle_module_contract_does_not_expose_ecu_writes(self):
        module_path = Path(__file__).resolve().parents[1] / "modules" / "vehicle_diagnostics" / "module.py"
        spec = importlib.util.spec_from_file_location("apollo_test_obd_module", module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        instance = mod.Module({"base_dir": str(Path(__file__).resolve().parents[1]), "validation": True})
        self.assertTrue(instance.self_test())
        tools = {t["name"] for t in instance.tools()}
        self.assertEqual(tools, {"obd_list_ports", "obd_live_snapshot", "obd_fault_codes", "obd_demo",
                                 "obd_starting_history", "obd_latest_starting_test"})
        sample = instance.run("obd_demo", {})
        self.assertTrue(sample["snapshot"]["simulated"])
        with self.assertRaises(KeyError):
            instance.run("obd_clear_codes", {"port": "COM7"})



class StartingSystemTests(AdapterTests):
    def test_atrv_voltage_parser_rejects_unsupported_responses(self):
        self.assertEqual(parse_adapter_voltage(b"ATRV\r12.48V\r>"), 12.48)
        self.assertEqual(parse_adapter_voltage("14.1 V\r>"), 14.1)
        for text in ("NO DATA", "ERROR", "ATRV", "123.00V", "12.4 A"):
            with self.subTest(text=text):
                self.assertIsNone(parse_adapter_voltage(text))

    def test_low_voltage_is_not_claimed_as_proven_starter_failure(self):
        report = {
            "samples": [
                {"elapsed_s": 0.1, "adapter_voltage_v": 12.6, "ecu_voltage_v": 12.5,
                 "engine_rpm": 0, "errors": {}},
                {"elapsed_s": 2.1, "adapter_voltage_v": 8.7, "ecu_voltage_v": None,
                 "engine_rpm": None, "errors": {"engine_rpm": "NO DATA"}},
            ],
            "events": [{"event": "key_turn_marked", "elapsed_s": 1}],
            "moving_detected": False,
        }
        a = analyse_starting_test(report)
        self.assertEqual(a["minimum_sampled_voltage_v"], 8.7)
        self.assertEqual(a["baseline_sampled_voltage_v"], 12.6)
        self.assertIn("Possible weak battery", a["summary"])
        self.assertIn("does not prove", a["summary"])
        self.assertEqual(a["status"], "observations_only")

    def test_no_ecu_response_cannot_be_called_a_good_battery(self):
        report = {"samples": [
            {"elapsed_s": 1, "adapter_voltage_v": None, "ecu_voltage_v": None,
             "engine_rpm": None, "errors": {"ecu_voltage_v": "timeout"}},
        ], "events": [], "moving_detected": False}
        a = analyse_starting_test(report)
        self.assertEqual(a["status"], "inconclusive")
        self.assertIsNone(a["minimum_sampled_voltage_v"])
        self.assertIn("No valid voltage", a["summary"])

    def test_capture_uses_only_allowlisted_read_requests(self):
        service, adapters = self.make_service()
        control = StartTestControl()
        control.mark_key_turn()
        # Stop after the first complete sample to keep tests hardware-free and fast.
        result = capture_starting_test(
            "COM7", duration_s=5, service=service, control=control,
            on_sample=lambda sample: control.stop(), interval_s=0.2,
        )
        self.assertEqual(len(result["samples"]), 1)
        self.assertEqual(result["samples"][0]["adapter_voltage_v"], 12.6)
        self.assertEqual(result["samples"][0]["ecu_voltage_v"], 14.12)
        self.assertEqual(result["samples"][0]["engine_rpm"], 430.75)
        self.assertTrue(adapters[0].closed)
        self.assertEqual(result["events"][0]["event"], "key_turn_marked")
        self.assertNotIn("04", adapters[0].queries)
        self.assertTrue(set(adapters[0].queries).issubset(ALLOWED_COMMANDS))
        self.assertFalse(result["simulated"])

    def test_bad_port_fails_without_fabricated_data(self):
        service, _ = self.make_service()
        with self.assertRaises(ValueError):
            capture_starting_test("COM9", service=service, duration_s=5)
        with self.assertRaises(ValueError):
            capture_starting_test("COM7", service=service, duration_s=400)

    def test_history_handles_empty_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(starting_test_history(folder), [])
            self.assertFalse(latest_starting_test(folder)["available"])

    def test_report_saved_locally(self):
        report = {"type": "starting_system_test", "samples": [], "analysis": {}}
        with tempfile.TemporaryDirectory() as folder:
            target = save_starting_test(report, folder)
            self.assertTrue(target.exists())
            self.assertIn("starting_tests", str(target))
            self.assertEqual(len(starting_test_history(folder)), 1)
            self.assertTrue(latest_starting_test(folder)["available"])
            self.assertEqual(__import__("json").loads(target.read_text())["type"],
                             "starting_system_test")

if __name__ == "__main__":
    unittest.main()
