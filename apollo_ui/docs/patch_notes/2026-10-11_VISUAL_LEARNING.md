# Apollo 8 Vision Lab candidate (11 October 2026)

## Delivered in this development branch

- New **Vision Lab** app in the modular Apps area, with individual user-triggered
  USB-camera photo capture (optional OpenCV).
- Image file import and direct public HTTPS image URLs, copied to
  `storage/media/visual_learning`.
- Local analysis through Ollama's `/api/chat` multimodal image payload using
  a separately installed vision model, default `qwen2.5vl:3b`.
- One-click save of source-linked, explicitly unverified visual notes into
  Research & Training storage, so the existing Chat knowledge retrieval can
  find them later.
- Separate **Research topic online + save sources** action, using the existing
  Research & Training multi-source web search.
- Camera enumeration, camera capture and visual web research are high-risk
  chat tools **denied by default** via Apollo Control Centre. Individual
  human UI clicks still work without granting background camera access.
- File import is only available via the UI file picker: the chat model cannot
  pass arbitrary desktop file paths to Vision Lab.
- Hardware-free tests for image validation, local Ollama requests, URL/IP
  restrictions, memory, research dependency and default permissions.

## Manual setup

Install `ollama pull qwen2.5vl:3b`. Only for a connected USB camera, run
`.venv\\Scripts\\python.exe -m pip install -r requirements_vision.txt` from
`apollo_ui`. No reinstall of XTTS or existing code models is required.

## Limitations

- This is visual observation and retrieval, **not model-weight retraining**.
- Webcam operation is single photos, not live video or persistent monitoring.
- The image downloader requires direct public HTTPS image URLs, not image
  search results pages or arbitrary website screenshots.
- Online source research is keyword-based and separate from interpretation,
  not reverse-image matching.
- There are no cloud API calls for image inference, but the separate
  user-triggered web research stage accesses public websites.
- The computer's camera and Ollama model must be verified on the real machine;
  software CI tests do not substitute for device testing.
- This branch is not a signed stable release.
