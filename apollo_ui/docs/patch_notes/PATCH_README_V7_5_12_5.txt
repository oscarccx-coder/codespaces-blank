Apollo 7.5.12.5 — Voice Training Progress + Responsive Trainer

Install over Apollo 7.5.12.4 with Apollo completely closed.

VOICE IMPRINT PLAY TEST
-----------------------
1. Open Voice Imprint Lab.
2. Select a prepared profile with at least 3 approved/good clips.
3. Click Train Acoustic Neural Signature.
4. You should immediately see:
   - Status: Preparing...
   - Progress bar movement
   - Training epoch X/Y
   - Live loss
   - Elapsed time
5. Apollo's UI should remain usable while training runs.
6. At completion the bar reaches 100%, Status becomes Complete and the profile
   refreshes to signature=yes.

If training fails, the status becomes Error, controls re-enable and the reason is
shown in the output area.

No personal data/storage/workspace files are included in this patch.
