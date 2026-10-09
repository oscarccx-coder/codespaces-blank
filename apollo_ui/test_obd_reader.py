"""Hardware-free OBD-II parser/serial transport safety and module tests."""
import importlib.util
import types
import unittest
from pathlib import Path

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
    "0A": b"4A 00 00\r>",
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
        self.assertEqual(parse_live_pid("0142", "41 42 37 24\r>")["value"], 14.116)
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
        self.assertEqual(set(adapters[0].queries), set(ALLOWED_COMMANDS - {"03", "07", "0A", "ATI"}))
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
        module_path = Path(__file__).parent / "modules" / "vehicle_diagnostics" / "module.py"
        spec = importlib.util.spec_from_file_location("apollo_test_obd_module", module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        instance = mod.Module({"base_dir": str(Path(__file__).parent), "validation": True})
        self.assertTrue(instance.self_test())
        tools = {t["name"] for t in instance.tools()}
        self.assertEqual(tools, {"obd_list_ports", "obd_live_snapshot", "obd_fault_codes", "obd_demo"})
        sample = instance.run("obd_demo", {})
        self.assertTrue(sample["snapshot"]["simulated"])
        with self.assertRaises(KeyError):
            instance.run("obd_clear_codes", {"port": "COM7"})


if __name__ == "__main__":
    unittest.main()
