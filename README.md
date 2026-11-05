# Familiar

A desktop companion for **Claude Code**. It sits on your desktop, shows what Claude Code is doing in your persona's voice, and keeps an eye on your plan limits and your machine.

- **Live agent state** through Claude Code hooks: thinking, reading, running commands, editing, waiting on you, done. Each activity gets its own mood animation and phrase ("Following the scent…", "Burrowing…").
- **Status footer:** CPU / GPU / RAM load, temperature and power in one table, then your Claude 5-hour and weekly usage with reset times, and tokens used today.
- **Persona packs:** your character, 9 moods × 10 frames, plus the phrases they say. Generate the art with the image provider you choose.
- **Plugins** for anything else you want it to watch (an alert file from your own tooling, for example).

Windows only for now (layered Win32 window). macOS/Linux is on the roadmap below.

## Install

```powershell
git clone <this repo>; cd familiar
pip install -e .
python -m familiar.install      # adds hooks to ~/.claude/settings.json (backs it up first)
pythonw -m familiar             # start it (uses personas/orion until you set your own)
```

`python -m familiar.install --remove` removes only Familiar's hooks.

## The moods

| Mood | When |
|---|---|
| idle | nothing happening |
| think | Claude Code is thinking, reading or searching |
| work | Claude Code is running commands or editing files |
| wait | Claude Code needs your input or permission |
| happy | a task just finished, or you booped it |
| alert | a plugin raised a real problem, or the GPU is hot |
| sad | your Claude 5-hour window is 95%+ used |
| gpu | the GPU is busy (games, renders, local models) |
| sleep | you've been away 10 minutes (2 after 11 PM) |

## Make your own persona

A persona is a folder: `persona.json` + `frames/<mood>_<n>.png`. Frame 0 is the base pose, 1–9 loop.

1. Copy `personas/orion/persona.json` to `personas/<you>/persona.json`. Set `name`, a one-sentence visual `description` of your character, the phrases, and optionally `poses` / `motions` per mood.
2. Put a reference image of your character in the folder and set `"reference"` to its file name.
3. Generate, with the provider you choose:
   ```powershell
   python tools/generate.py personas/<you> --provider gemini   # GEMINI_API_KEY
   python tools/generate.py personas/<you> --provider openai   # OPENAI_API_KEY
   python tools/generate.py personas/<you> --provider manual   # any chat app: it writes the prompts, you paste
   ```
   This makes 10 images: one 3×3 sheet with all 9 base poses (from your reference), then one 3×3 animation sheet per mood (from that mood's base pose, so the character stays on-model). Each sheet is keyed, cut and aligned automatically; reruns skip finished sheets.
4. Check `frames/_strips.png` (every animation) and `frames/_onion.png` (all frames averaged: sharp body = stable, blur = jitter). Regenerate a bad mood with `--only <mood>` after deleting `gen/<mood>.png`.
5. Point Familiar at it: `"persona": "C:/path/to/personas/<you>"` in `~/.familiar/config.json`.

Tips: image models drift, so expect to rerun one or two moods. Some return a different grid (a 2×3 or a repeated cell); `tools/frames.py anim <sheet> <mood> --grid 2x3` handles other grids.

## Config (`~/.familiar/config.json`)

```json
{
  "persona": "C:/Users/you/familiar/personas/orion",
  "stats": true,
  "plugins": {
    "alert_file": {"path": "C:/path/to/ALERT.txt", "meanings": {"disk": {"text": "Disk almost full ({msg})", "alarm": true}}}
  }
}
```

## Data sources

| Footer cell | Source |
|---|---|
| CPU / RAM load, RAM free | `psutil` |
| GPU load, temp, power | `nvidia-smi` (NVIDIA only for now) |
| CPU temp and power | [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) with its Remote Web Server on (port 8085). Windows exposes neither without admin rights; shows "–" otherwise |
| Claude 5h / week | the plan-usage endpoint behind Claude Code's `/usage`, read with the OAuth token Claude Code already stores locally. Read-only, polled every 3 min. This endpoint is not a documented public API and may change |
| Tokens today | summed from your local Claude Code transcripts (`~/.claude/projects`) |

Nothing leaves your machine except that one usage request to Anthropic (and image requests to the provider you pick when generating art).

## Roadmap

- Cross-platform window (Tauri or Qt) so macOS and Linux work
- AMD / Intel GPU stats
- A tiny OpenClaw bridge plugin, so OpenClaw sessions drive the same moods
- Persona gallery

## Layout

```
familiar/app.py        window, mood state machine, menu
familiar/render.py     sprite + bubble + footer drawing (headless-testable)
familiar/sources.py    system stats, Claude usage, tokens today, Claude Code state
familiar/hook.py       Claude Code hook handler (writes ~/.familiar/cc_state.json)
familiar/install.py    adds/removes the hooks
familiar/plugins/      optional watchers
tools/generate.py      art generation (gemini | openai | manual)
tools/frames.py        key, cut, scale and align sheets into frames; previews
personas/orion/        example persona
```
