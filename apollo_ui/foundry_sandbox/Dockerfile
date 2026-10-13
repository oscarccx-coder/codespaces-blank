# User-reviewed Foundry sandbox image; build once with Setup/09_SETUP_FOUNDRY_SANDBOX.bat.
# Production generated code runs only inside containers with no network and no Apollo data mounts.
FROM python:3.13-slim
RUN python -m pip install --no-cache-dir "PySide6==6.9.2"
ENV QT_QPA_PLATFORM=offscreen \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1
USER 65534:65534
WORKDIR /work
CMD ["python", "-V"]
