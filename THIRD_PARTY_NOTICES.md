# Third-party credits and licenses

Updated: 2026-10-04. MultipleVideoPlayer is a modified GridPlayer workspace. It is not an official GridPlayer release; no upstream endorsement is implied.

## GridPlayer and local modifications

- Original project: [GridPlayer — vzhd1701 and contributors](https://github.com/vzhd1701/gridplayer).
- Baseline: v0.5.5, commit `da2a649fcbcb8f1ab945353f090befca53f8725f`.
- Source: `VideoPlayer/src`. The original [README and attributions](VideoPlayer/src/README.md#attributions), author metadata, copyright notices, translations and [GPL text](VideoPlayer/src/LICENSE) are retained.
- GridPlayer declares `GPL-3.0-or-later` in its metadata. The GridPlayer-derived application and this project's original integration code are distributed under GPL-3.0-or-later; see [LICENSE](LICENSE). Separately licensed components and artwork retain their own terms.
- Modifications on 2026-09-30: six-to-twelve-cell workspace, spans, presets, per-cell display/audio settings, folder playlists, hover overlays, click-to-seek, volume popup, portable startup, version title and packaging. Publication documentation/repository setup: 2026-10-01. These are local changes, not upstream changes; see the local PR documents and Git history.

## Retained code and artwork

Additional modifications on 2026-10-04 (0.5.5-local3): configurable arrow-key seeking, millisecond timeline preview, continuous scrubbing, suspended/resumable A/B loops, bounded middle-button video panning and portable package instructions. See PR-007.

| Component | Credit / source | Terms and retained notice |
|---|---|---|
| Python VLC bindings, `gridplayer/vlc_player/vlc.py` | VideoLAN team; Olivier Aubert, Jean Brouwers, Geoff Salmon; [python-vlc](https://github.com/oaubert/python-vlc) | File header: LGPL-2.1-or-later; [full text](licenses/LGPL-2.1.txt). |
| Hack font | [Source Foundry](https://sourcefoundry.org/hack/), DejaVu contributors, Bitstream | MIT, public-domain DejaVu work and Bitstream Vera terms; [font license](VideoPlayer/src/resources/fonts/Hack/LICENSE.md). |
| Basic Icons | [Icongeek26](https://www.flaticon.com/authors/icongeek26) | Flaticon License, per upstream attribution. |
| Suru Icons | [Sam Hewitt](https://snwh.org/) | CC BY-SA 4.0, per upstream attribution. |
| Clean App Download Buttons | [Tony Thomas / MediaLoot](https://medialoot.com/item/clean-app-download-buttons/) | MediaLoot License, per upstream attribution. |
| Flag Icons | [Panayiotis Lipiridis](https://github.com/lipis/flag-icons) | MIT, per upstream attribution. |
| Translations | Contributors in the [upstream README](VideoPlayer/src/README.md#translations) | Original contributor list and translation sources retained. |

Artwork is retained from the stated upstream baseline. The program's GPL license does not replace font, icon or artwork terms. Retain the separate author credits and applicable asset notices.

## Dependencies

Installed runtimes and downloaded applications are excluded from Git. Versions are recorded in [requirements-lock.txt](VideoPlayer/requirements-lock.txt), [pyproject.toml](VideoPlayer/src/pyproject.toml) and `uv.lock`.

| Dependency | Credit / source | License information |
|---|---|---|
| Python | [Python Software Foundation](https://www.python.org/) | PSF License and bundled component notices. |
| PyQt5 | [Riverbank Computing](https://www.riverbankcomputing.com/software/pyqt) | This project uses the GPLv3 distribution, not a purchased commercial license. |
| Qt5 | [The Qt Project / The Qt Company and contributors](https://www.qt.io/licensing/) | LGPLv3/GPL alternatives and module-specific third-party terms; consult the selected distribution. |
| libVLC / VLC plugins | [VideoLAN and VLC contributors](https://www.videolan.org/) | libVLC: LGPL-2.1-or-later; plugin/dependency terms vary, including GPL components. Do not label the entire runtime as LGPL-only; see [VideoLAN legal information](https://www.videolan.org/legal.html). |
| pydantic | [Samuel Colvin and contributors](https://github.com/pydantic/pydantic) | MIT. |
| streamlink | [Christopher Rosell, Streamlink team and contributors](https://github.com/streamlink/streamlink) | BSD-2-Clause. |
| yt-dlp | [yt-dlp contributors](https://github.com/yt-dlp/yt-dlp) | Main project: Unlicense; dependencies retain their own terms. |

## Source publication and later binary releases

Keep these notices, original copyright statements, license texts and modification notices with source copies. Executable distribution requires complete corresponding source and build information by a method permitted by the applicable GPL/LGPL terms, including relevant non-system dependencies. An upstream homepage link alone does not substitute for the corresponding modified source.

The existing local ZIP is excluded from Git. Later binary releases require matching source, dependency notices/licenses and a check of the actual bundled libraries/plugins and artwork terms. This document records attribution and source scope; it does not certify that every local binary's redistribution requirements are complete.
