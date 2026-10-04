MultipleVideoPlayer / GridPlayer Workspace 0.5.5-local4

Windows 10 / 11, 64-bit x86 (x64).
Extract the entire ZIP into a writable folder, then double-click GridPlayerWorkspace.exe.
Do not run inside the ZIP viewer. Keep _internal and libVLC beside the executable.
Python and VLC installations are not required. A single isolated EXE is not this package.

Each cell: drop a video/folder; hover for controls. Left/Right seeks the last hovered
cell (first cell initially). Set seconds in the top row; fractional values are saved.
Hover the timeline for HH:MM:SS.mmm. Hold and drag its handle or track until release.
Seeking outside A/B suspends the loop without deleting markers. The Back to looping
button returns to A. Seeking inside A/B enables the loop again.
Middle-button drag pans cropped video; changing video/display mode resets the pan.
Wheel over video zooms around the pointer (1x-8x). The mode row shows zoom and reset.
Zoom and pan are saved with presets. Drag A above/B below the timeline to edit the loop.
The cell's ... menu edits A/B seconds and steps exact decoded frames while paused.
Frame stepping uses bundled PyAV/FFmpeg and actual timestamps, including VFR.
The focus button shows one cell; press it again or Escape to return to the grid.

Presets and preferences are stored in portable_data beside this executable.
Moving the application preserves settings if this folder is moved with it.
Video paths refer to the original files; those media files are not included.

License: GPL-3.0-or-later for the derived application. See LICENSE-GridPlayer.txt,
THIRD_PARTY_NOTICES.md and licenses/ for credits and component notices.
Modified source: https://github.com/alan52013141314/MultipleVideoPlayer
This local test package is not a signed installer or a public binary Release.
