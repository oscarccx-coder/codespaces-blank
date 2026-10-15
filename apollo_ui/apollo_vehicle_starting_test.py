"""Timed, read-only Apollo starting-system test recorder.

Standard OBD-II voltage is the voltage reported by the ECU (PID 42);
ELM327 ATRV is adapter-measured supply voltage. Neither measures starter
current or guarantees fast enough samples to see the minimum cranking voltage.
"""
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from apollo_obd import OBDService, VehicleConnectionError, parse_live_pid, utc_now


def parse_adapter_voltage(reply):
    """Read only a recognizable ATRV-style voltage reply; never infer from garbage."""
    text = reply.decode("ascii", "replace") if isinstance(reply, bytes) else str(reply)
    for line in re.split(r"[\r\n>]+", text):
        match = re.fullmatch(r"\s*(\d{1,2}(?:\.\d{1,3})?)\s*V\s*", line, re.I)
        if match:
            value = float(match.group(1))
            if 0 <= value <= 30:
                return round(value, 3)
    return None


class StartTestControl:
    """UI-safe commands; the reader thread alone touches the serial connection."""

    def __init__(self):
        self.started_at = time.monotonic()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._events = []

    @property
    def stop_requested(self):
        return self._stop.is_set()

    def stop(self):
        self._stop.set()

    def wait(self, seconds):
        return self._stop.wait(max(0.0, seconds))

    def mark_key_turn(self):
        with self._lock:
            event = {
                "event": "key_turn_marked",
                "elapsed_s": round(max(0.0, time.monotonic() - self.started_at), 3),
                "observed_at": utc_now(),
                "note": "Manually marked; timing may not match exact starter engagement.",
            }
            self._events.append(event)
            return dict(event)

    def events(self):
        with self._lock:
            return [dict(item) for item in self._events]


def analyse_starting_test(report):
    """Generate cautious observations, not a claimed failed component diagnosis."""
    samples = report.get("samples", [])
    events = report.get("events", [])
    key_times = [e["elapsed_s"] for e in events if e.get("event") == "key_turn_marked"]
    key_time = key_times[0] if key_times else None
    voltages = [
        (s["elapsed_s"], field, float(s[field]))
        for s in samples
        for field in ("adapter_voltage_v", "ecu_voltage_v")
        if isinstance(s.get(field), (int, float)) and math.isfinite(s[field])
    ]
    adapter_values = [(t, v) for t, f, v in voltages if f == "adapter_voltage_v"]
    ecu_values = [(t, v) for t, f, v in voltages if f == "ecu_voltage_v"]
    # Keep sources separate: ECU voltage and adapter supply voltage can disagree.
    preferred = adapter_values or ecu_values
    source = ("adapter (ATRV)" if adapter_values else
              "ECU (PID 42)" if ecu_values else "unavailable")
    rpm = [float(s["engine_rpm"]) for s in samples
           if isinstance(s.get("engine_rpm"), (int, float))]
    baseline = None
    if preferred:
        before = [v for t, v in preferred if key_time is not None and t < key_time]
        if before:
            baseline = round(sum(before) / len(before), 2)
        elif key_time is None:
            baseline = round(preferred[0][1], 2)
    attempts = (
        [(t, v) for t, v in preferred if key_time <= t <= key_time + 6]
        if key_time is not None else preferred
    )
    minimum = round(min(v for _, v in attempts), 2) if attempts else None
    maximum_rpm = round(max(rpm), 1) if rpm else None
    missing = sum(1 for s in samples if not any(
        s.get(k) is not None for k in ("adapter_voltage_v", "ecu_voltage_v", "engine_rpm")
    ))
    dropouts = sum(1 for s in samples if s.get("errors"))
    issues = []
    observations = []
    if key_time is None:
        issues.append("No key-turn marker: voltage changes cannot be assigned to a starting attempt.")
    if minimum is None:
        observations.append("No valid voltage measurements; starting voltage could not be assessed.")
    elif minimum < 9.6:
        observations.append(
            f"Low voltage observed ({minimum:.2f} V, {source})"
            + (" near the marked start attempt." if key_time is not None else " during this recording.")
        )
        observations.append(
            "Possible weak battery, poor cable/earth connection, or excessive starter load. "
            "This reading does not prove which component failed."
        )
    elif minimum < 11.0:
        observations.append(f"Voltage sag observed: minimum {minimum:.2f} V ({source}).")
    else:
        observations.append(f"Lowest sampled voltage was {minimum:.2f} V ({source}). "
                            "Fast cranking dips may have been missed.")
    if baseline is not None:
        observations.append(f"Approximate sampled pre-test voltage: {baseline:.2f} V ({source}).")
    if maximum_rpm is not None and maximum_rpm >= 500:
        observations.append("Engine-running RPM was observed during the test.")
    elif maximum_rpm is not None and maximum_rpm >= 80:
        observations.append("Engine rotation was reported, but a running engine was not confirmed.")
    else:
        observations.append("Engine rotation was not confirmed by the sampled RPM PID.")
    if not adapter_values:
        issues.append("Adapter supply voltage (ATRV) unavailable; ECU voltage may vanish during cranking.")
    if not ecu_values:
        issues.append("ECU voltage (PID 42) unavailable or unsupported.")
    if missing or dropouts:
        issues.append(f"Some readings were missing: {missing} empty samples; {dropouts} samples with communication errors.")
    if report.get("moving_detected"):
        issues.append("Vehicle movement detected by speed PID; test stopped for safety.")
    issues.append(
        "Standard OBD-II polling is slow and may disconnect during cranking. "
        "No starter current, battery-terminal voltage, or starter engagement was directly measured."
    )
    return {
        "minimum_sampled_voltage_v": minimum,
        "baseline_sampled_voltage_v": baseline,
        "voltage_source": source,
        "max_sampled_rpm": maximum_rpm,
        "samples": len(samples),
        "summary": " ".join(observations),
        "cautions": issues,
        "status": "inconclusive" if minimum is None else "observations_only",
        "next_checks": (
            "Check resting battery voltage with a meter after charging; test voltage "
            "at battery posts during cranking with a suitable fast meter/battery tester; "
            "inspect battery terminals, engine earth strap and starter feed. "
            "A proper starter-current test requires an approved clamp meter."
        ),
    }


def capture_starting_test(port, baud=38400, duration_s=30, *, service=None,
                          control=None, on_sample=None, interval_s=0.5,
                          vehicle_profile="Other OBD-II vehicle"):
    """Collect bounded readings in one adapter session. Caller runs in a worker thread.

    Every sample records missing data explicitly; there is no demonstration-data fallback.
    """
    if type(duration_s) is not int or not 5 <= duration_s <= 120:
        raise ValueError("Starting test must last between 5 and 120 seconds.")
    if not isinstance(interval_s, (int, float)) or not 0.2 <= interval_s <= 5:
        raise ValueError("Polling interval out of range.")
    service = service or OBDService()
    control = control or StartTestControl()
    report = {
        "schema_version": 1,
        "type": "starting_system_test",
        "source": "vehicle",
        "simulated": False,
        "port": port,
        "vehicle_profile": str(vehicle_profile)[:80],
        "started_at_utc": utc_now(),
        "planned_duration_s": duration_s,
        "read_only": True,
        "samples": [],
        "events": [],
        "moving_detected": False,
    }
    with service.connect(port, baud) as adapter:
        index = 0
        while not control.stop_requested and time.monotonic() - control.started_at < duration_s:
            sample = {
                "observed_at": utc_now(),
                "elapsed_s": round(time.monotonic() - control.started_at, 3),
                "adapter_voltage_v": None,
                "ecu_voltage_v": None,
                "engine_rpm": None,
                "vehicle_speed_kmh": None,
                "errors": {},
            }
            # Prioritize voltage first; the extra speed PID is polled less frequently.
            commands = [("ATRV", "adapter_voltage_v"), ("0142", "ecu_voltage_v"),
                        ("010C", "engine_rpm")]
            if index % 6 == 0:
                commands.append(("010D", "vehicle_speed_kmh"))
            for command, field in commands:
                if control.stop_requested:
                    break
                try:
                    reply = adapter.request(command)
                    value = (parse_adapter_voltage(reply) if command == "ATRV"
                             else parse_live_pid(command, reply))
                    if isinstance(value, dict):
                        value = value["value"]
                    if value is None:
                        sample["errors"][field] = "No supported reading in response"
                    else:
                        sample[field] = value
                except VehicleConnectionError as exc:
                    sample["errors"][field] = str(exc)
            report["samples"].append(sample)
            if on_sample is not None:
                on_sample(dict(sample))
            if sample["vehicle_speed_kmh"] is not None and sample["vehicle_speed_kmh"] > 0:
                report["moving_detected"] = True
                control.stop()
            index += 1
            control.wait(max(0, interval_s - (time.monotonic() -
                                             (control.started_at + sample["elapsed_s"]))))
    report["events"] = control.events()
    report["finished_at_utc"] = utc_now()
    report["actual_duration_s"] = round(time.monotonic() - control.started_at, 2)
    report["analysis"] = analyse_starting_test(report)
    return report


def save_starting_test(report, base_dir):
    """Persist a finished local test atomically, never into the Git repository's code."""
    if not isinstance(report, dict) or report.get("type") != "starting_system_test":
        raise ValueError("Not a starting-system report.")
    folder = Path(base_dir) / "storage" / "reports" / "vehicle_diagnostics" / "starting_tests"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = folder / f"start-test-{stamp}.json"
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def starting_test_history(base_dir, limit=10):
    """Return recent local start-test summaries to Apollo chat without ECU access."""
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("History limit must be 1 through 30.")
    folder = Path(base_dir) / "storage" / "reports" / "vehicle_diagnostics" / "starting_tests"
    result = []
    for path in sorted(folder.glob("start-test-*.json"), reverse=True)[:limit * 2]:
        try:
            if path.stat().st_size > 2_000_000:
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict) or report.get("type") != "starting_system_test":
                continue
            analysis = report.get("analysis") or {}
            result.append({
                "file": path.name,
                "started_at_utc": report.get("started_at_utc"),
                "vehicle_profile": report.get("vehicle_profile"),
                "duration_s": report.get("actual_duration_s"),
                "minimum_sampled_voltage_v": analysis.get("minimum_sampled_voltage_v"),
                "voltage_source": analysis.get("voltage_source"),
                "max_sampled_rpm": analysis.get("max_sampled_rpm"),
                "summary": analysis.get("summary"),
                "status": analysis.get("status"),
                "sample_count": len(report.get("samples", [])),
            })
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if len(result) >= limit:
            break
    return result


def latest_starting_test(base_dir):
    """Return the latest readable completed report or an explicit absence status."""
    history = starting_test_history(base_dir, limit=1)
    if not history:
        return {"available": False, "message": "No recorded starting-system tests yet."}
    filename = history[0]["file"]
    # Name comes from a constrained local glob, not from external tool input.
    path = Path(base_dir) / "storage" / "reports" / "vehicle_diagnostics" / "starting_tests" / filename
    report = json.loads(path.read_text(encoding="utf-8"))
    return {"available": True, "report": report}
