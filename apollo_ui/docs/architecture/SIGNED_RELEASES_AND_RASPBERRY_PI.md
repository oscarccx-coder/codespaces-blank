# Apollo 7.5.13.3: signed GitHub publishing and Raspberry Pi ARM64

## Status and intended deployment

The GitHub codebase now has a **headless Raspberry Pi ARM64 companion** and
a gated signed-release workflow. This first Pi target intentionally does not
run the full Windows PySide6 dashboard, NVIDIA/CUDA XTTS voice, model training,
or vehicle control. It shares Apollo's local Ollama API client, safe context
settings, persistent SQLite conversation-memory schema and signed update code.
The Pi runs independently using its own local data; sync with the workstation
remains separate, future work.

**Code ready** is not **hardware verified**. GitHub ARM64 runners can validate
software and an ARM64 virtual environment; only a Raspberry Pi 5, actual
Raspberry Pi OS and optional AI HAT+ 2 can validate the final hardware
behaviour/performance.

## Preparing a Raspberry Pi 5

Recommended: Raspberry Pi 5, 64-bit Raspberry Pi OS, Python 3.11+, reliable
power/cooling, at least a few GB free storage for a small model. Pi 5 16 GB
can run a small quantised LLM entirely in system RAM. Running the same 7B
coding model as the RTX 3060 desktop will be substantially slower on the Pi
CPU. Start with a 1B–3B model such as **qwen2.5:3b**. This is not a performance
benchmark: measure actual token speed and memory on the Pi.

On the Pi, after installing **Ollama for Linux ARM64** from the official
publisher and ensuring its service is running:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
git clone https://github.com/oscarccx-coder/codespaces-blank.git ~/Apollo
cd ~/Apollo/apollo_ui
bash pi/install_pi.sh
ollama pull qwen2.5:3b
.venv-pi/bin/python apollo_pi.py --self-test
.venv-pi/bin/python apollo_pi.py --port 8766
```

On a system with Ollama not available as a service, run `ollama serve`
in a separate terminal. The Pi server only uses the local Ollama endpoint;
it does not send prompts to a cloud model or download model weights.

To run Apollo automatically for a logged-in Pi user:

```bash
cd ~/Apollo/apollo_ui
bash pi/install_pi.sh --service
systemctl --user status apollo-pi.service
journalctl --user -u apollo-pi.service -f
```

`systemctl --user` requires an active user session. For always-on services
without login, review and explicitly set up user lingering through your Pi's
administrator. Installer does not silently enable lingering or create a
privileged system-wide service.

## Local authenticated HTTP API

Apollo Pi binds **only to 127.0.0.1:8766**, not to any local or public network
interfaces. A random token is generated at first start in the private file
`storage/state/pi_api_token` (mode 0600). It is not checked into Git.

```bash
cd ~/Apollo/apollo_ui
TOKEN="$(cat storage/state/pi_api_token)"
curl -s http://127.0.0.1:8766/health -H "Authorization: Bearer $TOKEN"
curl -s http://127.0.0.1:8766/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello Apollo, how are the systems?"}'
```

HTTP is **unencrypted**. It is intentionally limited to loopback; do not port
forward it onto the LAN or internet directly. For private remote operation
use SSH local forwarding (`ssh -L 8766:127.0.0.1:8766 pi@raspberrypi.local`)
or a separately authenticated HTTPS service. A phone/mobile integration
requires a secure pairing/TLS design before enabling LAN access.

The Pi edition saves conversations locally, can search existing learned facts
in its SQLite store and keeps a short prior-turn context. There are **no**
autonomous insulin, medication, system commands, ECU writes or GPIO actuators.
Further permissions/devices require explicit designs and tests.

### AI HAT+ 2

The official **AI HAT+ 2** (Hailo-10H) adds an NPU and its own memory for
supported GenAI models. It does **not automatically accelerate** an arbitrary
Ollama/GGUF model or XTTS. Raspberry Pi's documented Hailo-ollama runtime is a
**separate backend** and requires the appropriate supported model and
installation. Apollo's initial `/api/chat` Ollama client does not configure the
Hailo driver or assume it is present. Future support should be an explicit
backend adapter with a compatibility test, not an unverified offload switch.

Official Raspberry Pi documentation:
https://www.raspberrypi.com/documentation/computers/ai.html

## Signed updates on Pi

GitHub Releases publish one **platform-neutral signed source-code ZIP**.
The same signed manifest includes Pi files and the desktop Apollo Python
code; private storage, model weights, voices and virtual environments are
excluded. Pi uses the headless launcher rather than `launch_apollo.pyw`.
This is a source runtime, **not a Raspberry Pi desktop executable**.

The first trusted public-key fingerprint must be verified through an
independent channel, not copied blindly from the same release being trusted.
Download `release_public.pem` from the official GitHub Release, then:

```bash
cd ~/Apollo/apollo_ui
.venv-pi/bin/python pi/update_pi.py \
  --trust-key /path/to/release_public.pem \
  --fingerprint PUT_INDEPENDENTLY_VERIFIED_64_HEX_SHA256_HERE

.venv-pi/bin/python pi/update_pi.py --check --channel stable
bash pi/update_pi.sh --channel stable
```

The update wrapper stops the `apollo-pi.service` **if running**,
installs only signature-verified file paths, runs the health check and
rolls back file changes on health check failure, then restarts the service.
Do not run two manually launched Apollo Pi processes during an update.
This does not claim zero downtime or restore ongoing HTTP requests.
`pi/update_pi.py --apply` refuses to run without the offline
wrapper's explicit opt-in flag.

## GitHub Actions release automation

File: `.github/workflows/apollo-signed-release.yml`

1. Create a **persistent Ed25519 release key** on a trusted local development
   machine using the existing `apollo_ui/tools/publish_github_release.py`
   (without `--publish`). This creates a key in ignored
   `apollo_ui/storage/updates/keys/release_private.pem`. Never upload
   the private key to Git or a chat message. Back it up securely outside GitHub.
2. In the repository's **Settings → Secrets and variables → Actions**, create
   repository secret `APOLLO_RELEASE_PRIVATE_PEM` whose value is the
   complete contents of the private PEM (including BEGIN/END lines).
   Do not store it as a repository variable.
3. Calculate SHA-256 over the **public PEM file's bytes**, e.g.
   `python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('storage/updates/keys/release_public.pem').read_bytes()).hexdigest())"`
   from `apollo_ui`. Independently record/verify the 64-hex result,
   then create the **repository variable**
   `APOLLO_RELEASE_PUBLIC_SHA256` with that exact value.
   Apollo refuses to publish if the key changes unexpectedly.
4. In **Settings → Environments**, configure `apollo-releases` with
   appropriate trusted reviewers/deployment permissions if your GitHub plan
   supports it. Manual stable always requires the Actions dispatch confirmation
   phrase `PUBLISH`. Configure reviewers for extra control.
5. Under **Actions → Publish signed Apollo Release → Run workflow**, select
   `main`, choose **beta** or **stable**, and type `PUBLISH`.
   The job re-checks exact current main commit, validates the code, verifies
   package signatures/hashes and publishes `apollo-VERSION.zip`,
   `release_public.pem` and `SHA256SUMS.txt`. Tags:
   `vVERSION-beta` and `vVERSION`.
   Existing releases are never replaced.
6. **Optional automatic beta** after a passing main-branch regression run:
   create repository variable `APOLLO_AUTO_BETA=true`. Default is OFF.
   Beta will publish each **new version** after the tests pass, using the same
   pinned key. Stable remains manual.

### Security boundaries

- No unsigned or randomly re-keyed updates published by Actions.
- Signing secret is available only in the actual release job, not in PR tests.
- A successful PR alone never triggers publishing. CI must run on the repo's
  own `main` branch. Draft/pre-release beta is separate from stable.
- The workflow never auto-installs updates on a person's workstation.
- Pi and desktop import/pin the public key **only after independent fingerprint
  verification**; GitHub is the delivery mechanism, not the identity authority.
- Neither GitHub private signing keys nor local XTTS models are uploaded to
  public release assets.
- Publishing cannot run until owner configures the required secret/variable.
- Releases are code-only: a native executable installer, complete Pi GUI and
  tested AI HAT 2 acceleration are separate future milestones.
