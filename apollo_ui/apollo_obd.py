"""Read-only ELM327-compatible OBD-II vehicle diagnostics.

Communication is limited to a hard-coded allowlist: AT interface setup,
mode 01 live PIDs and modes 03/07/0A DTC reads. This module contains NO
Service 04 (clear codes), ECU writes, actuator tests, flashing or raw-command
escape hatches. Never use a computer-based diagnostic screen while driving.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import re

MAX_REPLY = 8192
READ_TIMEOUT = 2.0
BAUD_RATES = (9600, 38400, 57600, 115200)
SETUP_COMMANDS = ("ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0")

# OBD service 01 formulas. Only approved PIDs are exposed to the transport.
SENSORS = {
    "010C": ("Engine speed", "rpm", 2, lambda v: (v[0] * 256 + v[1]) / 4),
    "010D": ("Vehicle speed", "km/h", 1, lambda v: v[0]),
    "0105": ("Coolant temperature", "°C", 1, lambda v: v[0] - 40),
    "010F": ("Intake air temperature", "°C", 1, lambda v: v[0] - 40),
    "0111": ("Throttle position", "%", 1, lambda v: 100 * v[0] / 255),
    "0104": ("Calculated engine load", "%", 1, lambda v: 100 * v[0] / 255),
    "010B": ("Intake manifold pressure", "kPa", 1, lambda v: v[0]),
    "0142": ("Control module voltage", "V", 2, lambda v: (v[0] * 256 + v[1]) / 1000),
}
DTC_MODES = {"03": "stored", "07": "pending", "0A": "permanent"}
ALLOWED_COMMANDS = frozenset((*SETUP_COMMANDS, "ATI", *SENSORS, *DTC_MODES))
PROBLEMS = ("NO DATA", "UNABLE TO CONNECT", "BUS INIT", "CAN ERROR",
            "STOPPED", "BUS ERROR", "BUFFER FULL", "ERROR")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _response_payloads(reply, marker):
    """Locate matching service/PID bytes despite echo, spaces and CAN headers.

    Handles ELM327's common single-frame hex output, including 7E8 header
    prefixes. Multi-frame ISO-TP assemblies are deliberately NOT guessed.
    """
    marker = marker.upper()
    data = reply.decode("ascii", errors="ignore") if isinstance(reply, bytes) else str(reply)
    output = []
    for line in re.split(r"[\r\n>]+", data.upper()):
        line = line.strip()
        if not line or line.startswith(("SEARCHING", "ELM", "AT", "OK", "NO DATA", "CAN ERROR")):
            continue
        # ELM prints hexadecimal bytes with or without spaces/colons.
        compact = re.sub(r"[\s:]", "", line)
        if not re.fullmatch(r"[0-9A-F]+", compact):
            continue
        index = compact.find(marker)
        if index < 0:
            continue
        # Response bytes start at the first matching service/PID marker.
        after = compact[index + len(marker):]
        if len(after) >= 2 and len(after) % 2 == 0:
            output.append(bytes.fromhex(after))
    return output


def parse_live_pid(command, reply):
    """Return decoded measurement or None if PID is unavailable/malformed."""
    label, unit, required, convert = SENSORS[command]
    payloads = _response_payloads(reply, "41" + command[2:])
    for payload in payloads:
        if len(payload) >= required:
            value = convert(payload[:required])
            if isinstance(value, float):
                value = round(value, 2)
            return {"name": label, "value": value, "unit": unit, "pid": command[2:]}
    return None


def _decode_dtc(first, second):
    # SAE J2012: 2 bits for P/C/B/U, then two bits for leading digit.
    family = "PCBU"[(first >> 6) & 3]
    number = (first >> 4) & 3
    return f"{family}{number:X}{first & 15:X}{second >> 4:X}{second & 15:X}"


def parse_dtcs(reply, mode):
    if mode not in DTC_MODES:
        raise ValueError("Unsupported DTC query")
    codes, seen = [], set()
    for payload in _response_payloads(reply, {"03": "43", "07": "47", "0A": "4A"}[mode]):
        for offset in range(0, len(payload) - 1, 2):
            first, second = payload[offset:offset + 2]
            if (first, second) == (0, 0):
                continue
            code = _decode_dtc(first, second)
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def _reply_problem(reply):
    text = reply.decode("ascii", errors="replace") if isinstance(reply, bytes) else str(reply)
    upper = text.upper()
    return next((name for name in PROBLEMS if name in upper), None)


class VehicleConnectionError(RuntimeError):
    """Adapter/vehicle cannot be read; never substitute simulated values."""


class ELM327Session:
    def __init__(self, serial_port):
        self.port = serial_port

    def request(self, command):
        if command not in ALLOWED_COMMANDS:
            raise PermissionError("Only fixed read-only OBD-II queries are permitted.")
        self.port.reset_input_buffer()
        payload = (command + "\r").encode("ascii")
        self.port.write(payload)
        self.port.flush()
        reply = self.port.read_until(b">", size=MAX_REPLY)
        if not reply or b">" not in reply:
            raise VehicleConnectionError(f"OBD adapter timed out responding to {command}.")
        if b"?" in reply:
            raise VehicleConnectionError(f"OBD adapter rejected {command}.")
        return reply

    def prepare(self):
        for command in SETUP_COMMANDS:
            self.request(command)


class OBDService:
    """One short-lived serial session per scan; no open background device handle."""

    def __init__(self, serial_factory=None, ports_factory=None):
        self._serial_factory = serial_factory
        self._ports_factory = ports_factory

    def _serial_dependencies(self):
        if self._serial_factory is not None and self._ports_factory is not None:
            return self._serial_factory, self._ports_factory
        try:
            import serial
            import serial.tools.list_ports
        except ImportError as exc:
            raise RuntimeError("pyserial is missing. Run: python -m pip install pyserial") from exc
        return self._serial_factory or serial.Serial, self._ports_factory or serial.tools.list_ports.comports

    def list_ports(self):
        _, enumerate_ports = self._serial_dependencies()
        return [
            {"port": str(port.device), "description": str(port.description)}
            for port in enumerate_ports()
        ]

    @contextmanager
    def connect(self, port, baud=38400):
        factory, _ = self._serial_dependencies()
        available = {item["port"] for item in self.list_ports()}
        if not isinstance(port, str) or port not in available:
            raise ValueError("Choose an available serial/Bluetooth COM port from Apollo's device list.")
        if type(baud) is not int or baud not in BAUD_RATES:
            raise ValueError("Supported OBD adapter speeds: 9600, 38400, 57600 or 115200 baud.")
        try:
            with factory(port=port, baudrate=baud, timeout=READ_TIMEOUT,
                         write_timeout=READ_TIMEOUT) as serial_port:
                session = ELM327Session(serial_port)
                session.prepare()
                yield session
        except (ValueError, PermissionError, VehicleConnectionError):
            raise
        except (OSError, TimeoutError) as exc:
            raise VehicleConnectionError(f"Adapter connection failed: {exc}") from exc
        except Exception as exc:
            # pyserial raises serial.SerialException, a platform-dependent type.
            raise VehicleConnectionError(f"Could not communicate with OBD adapter: {exc}") from exc

    def snapshot(self, port=None, baud=38400, demo=False):
        if demo:
            return demo_snapshot()
        values, unavailable, problems = {}, [], {}
        with self.connect(port, baud) as adapter:
            for command in SENSORS:
                try:
                    reply = adapter.request(command)
                    value = parse_live_pid(command, reply)
                    if value is None:
                        unavailable.append(command)
                        if _reply_problem(reply):
                            problems[command] = _reply_problem(reply)
                    else:
                        values[command] = value
                except VehicleConnectionError as exc:
                    unavailable.append(command)
                    problems[command] = str(exc)
        return {
            "source": "vehicle", "simulated": False, "observed_at": utc_now(),
            "port": port, "sensors": values, "unsupported_pids": unavailable,
            "problems": problems, "message": (
                "No supported sensor data returned; confirm ignition and ELM327 compatibility."
                if not values else "Read-only vehicle data. Do not use while driving."
            ),
        }

    def read_codes(self, port=None, baud=38400, demo=False):
        if demo:
            return demo_fault_codes()
        codes, unavailable = {}, {}
        with self.connect(port, baud) as adapter:
            for mode, name in DTC_MODES.items():
                try:
                    response = adapter.request(mode)
                    problem = _reply_problem(response)
                    codes[name] = parse_dtcs(response, mode)
                    if problem:
                        unavailable[name] = problem
                except VehicleConnectionError as exc:
                    codes[name] = []
                    unavailable[name] = str(exc)
        return {
            "source": "vehicle", "simulated": False, "observed_at": utc_now(),
            "port": port, "codes": codes, "unavailable": unavailable,
            "message": "Read only. No codes were erased and no ECU settings were changed.",
        }


def demo_snapshot():
    return {
        "source": "demo", "simulated": True, "observed_at": utc_now(),
        "port": None, "sensors": {
            "010C": {"name": "Engine speed", "value": 820, "unit": "rpm", "pid": "0C"},
            "010D": {"name": "Vehicle speed", "value": 0, "unit": "km/h", "pid": "0D"},
            "0105": {"name": "Coolant temperature", "value": 86, "unit": "°C", "pid": "05"},
            "010F": {"name": "Intake air temperature", "value": 23, "unit": "°C", "pid": "0F"},
            "0111": {"name": "Throttle position", "value": 13.7, "unit": "%", "pid": "11"},
            "0104": {"name": "Calculated engine load", "value": 17.3, "unit": "%", "pid": "04"},
            "010B": {"name": "Intake manifold pressure", "value": 32, "unit": "kPa", "pid": "0B"},
            "0142": {"name": "Control module voltage", "value": 13.8, "unit": "V", "pid": "42"},
        },
        "unsupported_pids": [], "problems": {},
        "message": "DEMO ONLY: simulated values, not obtained from a vehicle.",
    }


def demo_fault_codes():
    return {
        "source": "demo", "simulated": True, "observed_at": utc_now(),
        "port": None, "codes": {
            "stored": ["P0133"], "pending": [], "permanent": [],
        },
        "unavailable": {},
        "message": "DEMO ONLY: fictional example trouble code; no vehicle connected.",
    }
