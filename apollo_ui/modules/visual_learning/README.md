# Apollo Vision Lab (optional, offline-first)

Apollo Vision Lab appears under Settings > Apps (or the Hub's module apps).

## Set up

1. Start Ollama and download a **vision-enabled** model: `ollama pull qwen2.5vl:3b`.
   Your existing Qwen-Coder text model cannot interpret image pixels.
2. For a USB webcam, activate Apollo's existing virtual environment and run
   `python -m pip install -r requirements_vision.txt` inside `apollo_ui/`.
   Direct image files and HTTPS downloads do not need OpenCV.
3. Open **Vision Lab**, choose **Capture photo**, **Open image file** or **Load web image**.
4. Click **Analyse image** and ask a question. The request goes only to local
   Ollama at 127.0.0.1:11434.
5. Add a subject and click **Save to memory** to make the observation searchable
   through Apollo's existing Research & Training retrieval.
6. If wanted, click **Research topic online + save sources**. This separately uses
   Apollo's existing Research & Training web research (network required).

## Boundaries and privacy

- The camera is opened for a single captured frame then released, not permanently
  streamed. Nothing activates automatically on startup.
- The UI capture button is direct user consent for that individual frame.
- The chat `visual_learning__capture_camera` action is **high-risk and denied by
  default** in Control Centre unless explicitly enabled. AI tools cannot import
  arbitrary local image paths: only images already selected into Vision Lab.
- Files and screenshots selected in the file picker are copied into
  `storage/media/visual_learning`; they do not go to Ollama cloud.
- Direct public HTTPS image URLs are supported (no browser-page scraping, private
  network hosts, credentials, redirects, SVG or more than 8 MB).
- Internet research requires a separate user action and a subject; research results
  go into `storage/training/research/visual`.
- Vision interpretations are *fallible descriptions*, not model-weight training or
  verified scientific facts. Memory notes explicitly identify the image source
  and model and mark the observations unverified.
- Chat image analysis can reference existing image IDs. It cannot see continuous
  real-time video or analyse multiple frames as a video yet.
- Camera hardware and installed Ollama models need testing on the actual PC.
