"""Read-only presentation state for Apollo's home core (no Qt or model calls)."""
from array import array
from dataclasses import dataclass
import math
import sys
import threading
import time
import wave


@dataclass(frozen=True)
class CoreActivity:
    state: str = "idle"
    title: str = "Ready when you are"
    detail: str = "Ask a question. Start an experiment. Build something."
    level: float = 0.0
    level_available: bool = False


def speech_motion_level(level, elapsed, available=False):
    """Preserve measured silence; use a syllabic pulse only without audio data."""
    if available:
        return max(0.0, min(1.0, float(level)))
    syllable = max(0.0, math.sin(elapsed * 4.8))
    return (syllable * (.55 + .45 * math.sin(elapsed * 13.7) ** 2)) ** .6


def resolve_activity(*, listening=False, speech=None, thinking=False,
                     tool="", working=(), error="", muted=False):
    """Use observed work, never infer an activity from a user's prompt."""
    speech = speech or {}
    if listening:
        return CoreActivity("listening", "Listening", "Microphone active · dictating your message")
    if speech.get("playing"):
        return CoreActivity("speaking", "Speaking", "Voice playback active",
                            speech.get("level", 0.0), bool(speech.get("level_available", False)))
    if speech.get("generating"):
        return CoreActivity("voice", "Preparing voice", "Generating speech locally")
    if tool:
        readable = str(tool).replace("__", " · ").replace("_", " ")[:110]
        research = any(word in str(tool).lower() for word in ("research", "search", "fetch", "explore_web"))
        return CoreActivity("researching" if research else "working",
                            "Researching" if research else "Working", readable)
    if thinking:
        return CoreActivity("thinking", "Thinking", "Generating a response with your selected model")
    if working:
        return resolve_activity(tool=working[0])
    if error:
        return CoreActivity("attention", "Needs attention", str(error)[:160])
    return CoreActivity(detail="Voice muted · text replies are available" if muted else CoreActivity().detail)


class PlaybackEnvelope:
    """Small PCM envelope built on the playback worker, sampled without file I/O.

    This follows the WAV playback clock, not the system audio mix. Formats other
    than PCM16 retain playback state and use the core's gentle speaking pulse.
    """
    STEP = 0.05

    def __init__(self):
        self._lock = threading.Lock()
        self._levels = ()
        self._started = 0.0
        self._process = None

    @classmethod
    def read(cls, path):
        levels = []
        try:
            with wave.open(str(path), "rb") as source:
                if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
                    return ()
                frames = max(1, int(source.getframerate() * cls.STEP))
                # Bound analysis to 15 minutes and decimate each block for cost.
                for _ in range(int(900 / cls.STEP)):
                    data = source.readframes(frames)
                    if not data:
                        break
                    samples = array("h", data)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    sample = samples[::max(1, len(samples) // 256)]
                    rms = math.sqrt(sum(float(n) * n for n in sample) / max(1, len(sample))) / 32768
                    levels.append(min(1.0, rms * 5))
        except (OSError, EOFError, ValueError, wave.Error):
            return ()
        return tuple(levels)

    def start(self, process, levels=()):
        with self._lock:
            self._process, self._levels = process, levels
            self._started = time.monotonic()

    def stop(self):
        with self._lock:
            self._process, self._levels = None, ()

    def snapshot(self):
        with self._lock:
            process, levels, started = self._process, self._levels, self._started
        playing = process is not None and process.poll() is None
        index = int(max(0.0, time.monotonic() - started) / self.STEP)
        available = bool(playing and levels)
        # After the bounded envelope ends, hold closed rather than invent speech.
        return {"playing": playing, "level": levels[index] if available and index < len(levels) else 0.0,
                "level_available": available}
