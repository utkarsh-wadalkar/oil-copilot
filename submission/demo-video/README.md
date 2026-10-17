# Asset Intelligence Copilot demo

Editable Remotion walkthrough based on [the existing script](../demo-script.md). The original script is unchanged. `Demo` is exactly **5:00 at 1920×1080, 30 fps**; the six chapters are also individual Studio compositions.

```powershell
cd submission/demo-video
npm install
npm run dev
```

Open http://localhost:3100/Demo. Chapter timings match the script: 0:00, 0:35, 1:30, 3:15, 4:10, 4:50.

## What this contains

This is an animated editorial walkthrough, **not a recording of a live browser session**. The compliance rows, confirmed spill correction and private-memory examples use the recorded sample-data results in `../evidence/sample-scenarios-report.md` and the dataset's actual repair report/SOP. On-screen labels make the recorded-data mode explicit. The 18-scenario claim refers to the deterministic replay report; it is not presented as a complete live-model evaluation. The architecture reflects the current README/script, including nao being outside the default path.

The preview now includes synthetic narration using the locally installed Microsoft Zira Desktop voice. All six chapters have their own synchronized audio, including when previewed individually. The narration explains the evidence, correction validation, cross-user updates and private recall. The on-screen footer identifies the synthetic voice. For the final challenge, replace it with your own recording as the original script requests, and include the actual end-to-end UI demonstration. Do not describe these illustrated interactions as a screen capture.

Edit `narration.json` to change the spoken explanation. Regenerate on Windows with `powershell -ExecutionPolicy Bypass -File scripts/generate-narration.ps1` (requires Microsoft Zira Desktop, System.Speech and Python). The generator checks that each clip fits its visual beat, then assembles six chapter tracks and a five-minute `public/narration/full-narration.wav`. No API key or paid voice service is used. Chapter audio lives in `public/narration`; the standalone segment files are regeneration intermediates.

If you explicitly want an MP4 after review:

```powershell
npm run render:demo
```

Output: `out/asset-intelligence-demo.mp4` (ignored by Git). Studio also exposes its Render controls. No export is performed automatically.

Validate with `npm run typecheck`, `npm run lint`, and `npm run build`.
