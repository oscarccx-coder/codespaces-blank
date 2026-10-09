"""Ollama context/RAM profiles for Apollo.

Ollama itself schedules model layers between VRAM and system RAM. These
profiles tune *context*, processing batch and model residency only; Apollo
does not fake a VRAM expansion or preallocate arbitrary GB of RAM.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelMemoryProfile:
    label: str
    num_ctx: int
    num_batch: int
    keep_alive: str

PROFILES = {
    "balanced": ModelMemoryProfile("Balanced (recommended)", 8192, 256, "5m"),
    "expanded": ModelMemoryProfile("More Context (RAM-assisted)", 16384, 128, "10m"),
    "large": ModelMemoryProfile("Large Context (experimental)", 32768, 64, "5m"),
}


def normalize_profile(name):
    return name if isinstance(name, str) and name in PROFILES else "balanced"


def resolved_options(config):
    cfg = dict(config or {})
    preset = PROFILES[normalize_profile(cfg.get("memory_profile"))]
    try:
        ctx = int(cfg.get("num_ctx", preset.num_ctx))
    except (TypeError, ValueError):
        ctx = preset.num_ctx
    ctx = min(32768, max(1024, ctx))
    try:
        batch = int(cfg.get("num_batch", preset.num_batch))
    except (TypeError, ValueError):
        batch = preset.num_batch
    batch = min(512, max(16, batch))
    keep = str(cfg.get("keep_alive", preset.keep_alive))
    if keep not in {"0", "1m", "5m", "10m", "15m"}:
        keep = preset.keep_alive
    return {"num_ctx": ctx, "num_batch": batch, "keep_alive": keep}


def memory_advice(available_gib, total_gib, selected):
    """Advisory only. Do not silently mutate user settings or offload layers."""
    profile = PROFILES[normalize_profile(selected)]
    if available_gib is None:
        return "Check RAM/VRAM availability before applying large-context settings."
    if available_gib < 4:
        return "Low free RAM: Balanced is safer; close other heavy programs before increasing context."
    if profile.num_ctx >= 32768 and (total_gib or 0) < 24:
        return "Large context can exceed memory capacity. Prefer Balanced."
    if profile.num_ctx >= 16384:
        return "Larger context requires additional KV cache; actual speed and RAM use depend on the model and Ollama scheduling."
    return "Balanced context reduces memory pressure and typically keeps more model layers on the GPU."
