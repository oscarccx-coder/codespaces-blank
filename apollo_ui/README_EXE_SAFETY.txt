Apollo 7 — Windows EXE trust / SmartScreen

If Windows says "Microsoft Defender SmartScreen prevented an unrecognized app", that usually means the EXE is unsigned or has little reputation. It is not proof of malware.

Apollo 7 includes build_apollo_exe_safer.bat which:
- builds ONEDIR instead of one-file
- disables UPX
- performs a clean PyInstaller build
- embeds version metadata and icon
- creates SHA256.txt

The real publisher-trust fix is to sign Apollo.exe with a genuine code-signing certificate. sign_apollo.ps1 is included, but Apollo cannot invent a trusted certificate.

IMPORTANT: if Microsoft Defender reports a named malware/trojan detection rather than the SmartScreen "unrecognized app" reputation warning, do NOT simply bypass it. Rebuild from this source, update Defender, inspect the detection details, and scan the exact output before running it.
