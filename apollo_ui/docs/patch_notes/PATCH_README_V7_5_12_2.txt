Apollo 7.5.12.2 — Roadmap Expansion + Future Blueprints + Docs Cleanup

Install over Apollo 7.5.12.1 with Apollo completely closed.

WHAT CHANGED
------------
1. Apollo Roadmap 2.0 now includes the newly planned AI/media/platform/recovery
   features and automatically merges them into an existing persisted roadmap.
2. Machine-readable feature placeholders live under:
      blueprints/future_features/
3. Patch documentation now lives under:
      docs/patch_notes/
4. On first startup, apollo_docs.py migrates old root-level PATCH_NOTES.md and
   PATCH_README*.txt files out of the main script directory.

IMAGE GENERATION PLACEHOLDERS
-----------------------------
The planned chain is now represented internally:
Compute Broker -> Vision Core -> Image Core -> ComfyUI/Diffusers ->
Media Studio -> Edit/Inpaint/Upscale -> Asset Library -> Style/LoRA Manager

These are placeholders only. They do not load models or install dependencies yet.

This patch does not overwrite storage/, workspace/, pending_modules/,
config.json, ui_state.json or modules_state.json.
