# PixelClaw Progress Log

## Apr 16 2026

Bootstrapped the project from scratch.

**Environment & structure**
- Set up micromamba environment (`pixelclaw`) with Python 3.12, raylib, anthropic, and Pillow.
- Established two-package layout: `agentcore/` (reusable core, no app-specific imports) and `pixelclaw/` (image app built on top of it). Designed so `agentcore` can be extracted into its own repo later.

**agentcore — framework**
- `Document` / `Context` — abstract base classes for open documents and app state (documents list, history log, current task, Anthropic API chat history).
- `Tool` — abstract base for LLM-callable tools (name, JSON schema, execute).
- `Agent` — Anthropic conversation loop with tool dispatch and chat history management.
- `App` — Raylib window lifecycle (`on_start`, `update`, `draw`, `on_close`, `on_files_dropped` hooks; `_process_input` routes mouse, keyboard, scroll wheel, and file drops each frame).
- `Panel` — named rectangular UI region forming a hierarchy: background fill, recursive draw, mouse hit-testing and focus routing (focus follows click), keyboard routing down the focus chain, `handle_mouse_wheel` routed independently of mouse movement.
- `Font` — TrueType font wrapper with a per-physical-pixel cache for HiDPI-correct rendering; `measure()` and `draw()` in logical coordinates.
- `NinePatch` — 9-slice image loaded from PNG + JSON sidecar (border widths); wraps `DrawTextureNPatch`.
- `resources` — lazy singleton for the default font (DejaVuSans); auto-unloaded by `App`.
- `ChatPanel` — scrollable transcript of chat entries displayed as speech balloons (agent left, user right) with word-wrap, scissor clipping, and mouse-wheel scrolling.
- `InputField` — single-line text input with full editing: cursor, click-to-place, drag-to-select, shift+arrows, Alt/Ctrl word movement, Home/End/Up/Down, Backspace/Delete with OS auto-repeat, Ctrl+A/C/X/V clipboard, Enter to submit.

**pixelclaw — image app**
- `ImageDocument` — wraps a PIL `Image`; load/save.
- `ImageWorkspace` — extends `Context[ImageDocument]`; adds a selection rectangle.
- `LayoutManager` — hard-coded four-panel layout: Header (64 px tall), Dock (128 px wide), Main (fills remainder), Chat (20 % of width); recalculates on window resize.
- `DockPanel` — shows a thumbnail and filename for each open document; active document highlighted; click to activate.
- `MainPanel` — displays the active document scaled-to-fit with aspect ratio preserved; "drop an image" hint when empty.
- `textures` — PIL→Raylib texture conversion with separate thumbnail and display caches; `unload_all()` on close.
- `PixelClawApp` — wires everything together; handles file-drop (PNG/JPEG/etc.) by opening documents into the workspace and logging to context history.

**Assets**
- `agentcore/resources/DejaVuSans.ttf` — default UI font.
- `agentcore/resources/speechBalloonLeft.png` / `speechBalloonRight.png` + JSON sidecars — 9-slice speech balloon images for the chat panel.

---

## Apr 16 2026 (continued)

**LLM backend & agent loop**
- Switched from Anthropic SDK to **LiteLLM** for provider-agnostic function-calling; default model `gpt-5.4-nano` (key read from `api_key.secret`); `litellm.suppress_debug_info = True` silences startup noise.
- `Agent` rebuilt around OpenAI-style `chat/completions`: `_build_messages()` assembles `[system(instructions), system(context), *history]` fresh each call; `_trim_history()` drops oldest user-turn groups when history exceeds 40 messages; `_write_debug()` writes `debug_output/NNNN_request.json` + `NNNN_response.json` for inspection; debug folder is cleared on each launch.
- `Tool.to_api_dict()` now emits OpenAI function-calling schema (`{"type":"function","function":{...}}`).
- `Context.agent_reason` field — set by `Agent` to the model's text content before each tool dispatch, so tools can record the intent alongside the image version.
- `Context.render_context()` default implementation; overridden in `ImageWorkspace` to report image size, channel layout, dtype, version count, and selection rect.
- Agent messages and tool invocations printed to terminal as they arrive (`[agent] …` / `[tool] name(args)`).
- Background threading: `_handle_message` starts a daemon thread; `update()` drains `_reply_queue` on the main thread and invalidates textures there (all OpenGL calls on main thread only — documented as architectural rule in `CLAUDE.md`).
- `get_instructions_path()` hook on `App`; `PixelClawApp` points to `pixelclaw/agent_instructions.md`.

**Image representation & version history**
- `ImageDocument` stores images as numpy `uint8` RGBA arrays (`(H, W, 4)`).
- Version history: `_versions: list[tuple[np.ndarray, str]]` — each entry is `(array, reason)`; initial load gets reason `"loaded from file"`.
- `push(array, reason)` appends and returns the new version index.
- `revert_to(index)` discards later versions.
- `version_history()` returns `[(index, reason), …]`.
- Fixed `load()` to use `np.array()` (copy) instead of `np.asarray()` (view into PIL buffer) to avoid GC-related data corruption.

**LLM-callable tools**
- `apply` — execute arbitrary Python/numpy code against the active image **in place**; supports single expressions and multi-line code blocks (assigns to `result`); `np`, `ndi` (scipy.ndimage), and `skimage` available. Instructions note this modifies the active document — use `multi_apply` to produce a new document.
- `inspect` — report per-channel min/max/mean, transparency breakdown, content bounding box, and an 8×8 hex alpha map for spatial orientation; optional sub-region.
- `crop` — crop to rectangle; reports resulting version index.
- `pad` — add border; performs **alpha bleed** (fills transparent border pixels with nearest edge pixel's RGB) so edge effects like glow work correctly. Root-caused via diagnostic instrumentation: tool-padded images had `[0,0,0,0]` in transparent zone vs. GraphicConverter's `[112,112,112,0]`, causing invisible glow.
- `scale` — resize with nearest/bilinear/lanczos resampling; derives missing dimension from aspect ratio.
- `version_history` — list all versions with index and reason.
- `revert` — revert to a given version index, discarding later ones.
- `set_active` — change the active document by name.
- `close_documents` — close named documents; accepts `["all except active"]` as a shorthand.
- `new_from_region` — create a new document from a region of the active image without modifying the original; omit region args to duplicate.
- `multi_apply` — apply Python/numpy code reading from multiple named documents; write result to a named or new document. Accepts `"active"` as a special document name in both `images` and `result_name` to avoid needing to track the active document's filename across multi-step turns.

**Display fixes**
- `textures.py`: display textures use `TEXTURE_FILTER_POINT` (sharp pixels); thumbnails use `TEXTURE_FILTER_BILINEAR`.
- `font.py`: extended character set (curly quotes, em-dash, en-dash, ellipsis, etc.) loaded via `codepoints_arr`; fixed `global` declaration so module-level variables are updated correctly on first use.

**Agent instructions** (`pixelclaw/agent_instructions.md`)
- Documents all tools with examples including flip/rotate, glow (multi-line), grayscale, and alpha-composite patterns.
- Protocol rules: never announce an action without calling the tool; single-step tasks call the tool immediately with no preamble; `apply` is in-place, `multi_apply` creates/updates a named document.

---

## Apr 17 2026

**New image tools**
- `generate_image` — creates a new document via OpenAI `gpt-image-1`; posts "Generating image: …" progress message to chat before the API call.
- `edit_image` — edits the active document via `gpt-image-1`; uses the selection rect as a mask if present; posts progress message; `_nearest_size()` picks the closest supported size.
- `remove_background` — removes image background using `rembg` neural network (default model `isnet-general-use`; 6 models listed for LLM selection); posts "Removing background…" or "Downloading model…" depending on cache state.
- `new_image` — creates a blank canvas filled with a solid RGBA color (default transparent); instant, no API call. Agent instructions explicitly tell the LLM to prefer this over `generate_image` for solid fills.
- `rotate` — rotates the active image by a given number of degrees (CCW positive) around a configurable pivot (default: image center); canvas expands automatically so no content is lost by finding the rotated bounding box of the active (non-transparent) content and growing the canvas to contain it; reports original and new size.
- `soft_threshold` — cleans up grayscale masks by snapping interior pixels to 0/255 while preserving anti-aliased edges. Works by: thresholding to binary, flood-filling enclosed holes (with edge-pad trick so shapes touching the border are handled), computing per-pixel distance from the binary edge, then blending — original value within `min_dist` px of the edge, snapped value beyond `min_dist` px, interpolated in between. Parameters: `channel` (luminance/alpha/red/green/blue), `threshold` (128), `min_dist` (2), `max_dist` (7).
- `inspect` — extended to include an 8×8 color map (average RGB per cell as hex) alongside the existing alpha map, so the LLM can identify spatial color and transparency issues.
- `pad` — default fill color now samples all four corners and uses the most common (if any two agree) or the average; prevents black-bar artifacts when padding images with a uniform background.

**OpenAI integration**
- `api_key.secret` is the OpenAI key used via LiteLLM (not an Anthropic key). `openai_key.secret` may also be present; if so it takes priority; otherwise `api_key.secret` is used for both the agent and image tools.
- `ml_deps.py` — `ensure_packages()` installs optional ML dependencies at startup (before `InitWindow`); `rembg[cpu]` installed via pip, `numba` (required by pymatting → rembg) installed via micromamba to get pre-built binaries.

**Vision support**
- Agent injects a 128×128 base64 PNG thumbnail of the active document into the last user message as a `detail:low` image URL, enabling vision-capable models to see what they're working on.
- `Agent._use_vision` flag; `_call_llm()` auto-detects vision-related API errors, disables vision, and retries transparently.
- `Context.message_queue` (thread-safe `queue.Queue`) + `post_message()` — tools post progress strings from background threads; `PixelClawApp.update()` drains the queue into the chat panel each frame.
- Post-operation verification rule added to agent instructions: after any visual operation, call `inspect` before reporting success.

**UI — checkerboard background**
- `MainPanel` loads `pixelclaw/resources/backgroundPattern.png` as a tiled texture behind the active image so transparency is visually apparent. Uses `TEXTURE_WRAP_REPEAT` + `DrawTexturePro` with an oversized source rect (no `DrawTextureTiled` in this Raylib version).

**File save (Cmd+S / Ctrl+S)**
- `file_dialogs.py` — `save_image()` shows a native save dialog: `NSSavePanel` via PyObjC on macOS, tkinter fallback on other platforms. PyObjC kept strictly inside `file_dialogs.py`.
- Layout-aware key detection: `_find_key_for_char('s')` scans key codes 32–350 using `glfwGetKeyName(key, 0)` (layout-aware) to find the code that produces `'s'` in the current OS keyboard layout. Runs once in `on_start()` after `InitWindow`. Correctly handles Dvorak, Colemak, etc.
- JPEG save composites on a white RGB background before saving (no alpha channel in JPEG).

---

## Apr 18 2026

**`pixelate` tool** (`pixelclaw/tools/pixelate.py`)
- Wraps the pyxelate library (installed from GitHub; uses Bayesian Gaussian Mixture + sobel-weighted downsampling).
- Accepts `factor` **or** `target_width`/`target_height` (or both, validated for consistency). When a target size is given the image is pre-scaled (Lanczos) to the nearest exact multiple of the factor before pixelation, so the output matches the requested size precisely.
- `svd` defaults to `false` (faster; empirically looks better).
- Posts a progress message (with expected output size and palette count) before the slow BGM step.
- Includes a `__main__` test block: prompts for input path and parameters, writes `<stem>_pixelated.png`.
- Agent instructions updated: `pixelate` entry now includes `target_width`/`target_height` params and an explicit rule to never follow a `pixelate` call with a `scale` call.

**`undo` tool** (`pixelclaw/tools/undo.py`)
- No-argument shortcut for "revert to previous version". Returns the version label and current image dimensions.
- `revert` tool also updated to report image dimensions after reverting, so the agent is grounded before proceeding with further operations.
- Agent instructions updated: explicit rule that when asked to undo-then-redo, `undo` must be called first and its returned state verified before any subsequent tool call.

**Main panel UI tweak** (`pixelclaw/mainpanel.py`)
- 16 px top and bottom margin added; image scales to fit the margined area.
- Current image dimensions (e.g. `512×512`) drawn right-aligned in the top margin in small translucent gray text.

**`separate_layers` tool** (`pixelclaw/tools/separate_layers.py`)
- Splits a cartoon/line-art image into `_ink` (black outlines, varying alpha), `_color` (flat fill colors), `_bg` (background, fully opaque), and `_palette` (swatch strip) documents.
- **Palette discovery**: uses pyxelate's BGM (not K-means) on a near-black-purified copy of the image. Pixels with `max(R,G,B) < 64` are snapped to true black before fitting, preventing AI-image speckle in dark areas from registering as spurious fill colors.
- **Background detection**: samples border pixels, quantizes to 8-step bins, and votes for the most common color — handles any background color, not just white.
- **Unmixing**: extended palette is `[black, bg_color, ...fill_colors]`. For each pixel the two nearest palette entries are found (Euclidean RGB) and the linear mix solved. Cases: ink/fill, fill/bg, ink/bg, solid fill, solid ink, solid bg — each assigns correctly to the three output layers.
- Background layer is fully opaque (solid detected bg color, no alpha cutout).
- Includes a `__main__` test block.

**InputField improvements**
- `Alt+Backspace` — delete word to the left of cursor.
- `Alt+Delete` — delete word to the right of cursor.
- **Focus bug fix** — `Panel.is_focused` previously only checked one level up the parent chain; a click on the main panel would update `root._focused_child` but leave `ChatPanel._focused_child` still pointing at `InputField`, causing the cursor to appear focused while keyboard events were dead-ended elsewhere. Fixed by walking the full ancestor chain to verify every level agrees.

**`posterize` tool** (`pixelclaw/tools/posterize.py`)
- Reduces an image to a small flat-color palette to eliminate speckle/texture common in AI-generated images, without changing image size.
- Pipeline: Gaussian blur of configurable `blend_radius` → BGM palette discovery (via sklearn `BayesianGaussianMixture`) on blurred pixels → nearest-palette remap of original pixels → optional despeckle pass.
- **Palette discovery**: subsamples to 50k pixels for speed; active components filtered by weight threshold; pure black `(0,0,0)` and white `(255,255,255)` always guaranteed in palette (replacing near-black/near-white entries within L2 distance 60, or appending if none are close).
- **Despeckle** (`despeckle=True` by default): after palette remap, finds every pixel whose label differs from all 8 neighbors and replaces it with the modal neighbor label. Vectorized via `np.roll` + per-label vote counts.
- Includes a `__main__` test block (prompts for input, palette, blend_radius, despeckle; writes `<stem>_posterized.png`).
- Registered in `__init__.py`, imported and instantiated in `main.py`, documented in `agent_instructions.md`.

**`inspect` tool update**
- Now reports unique color count (RGB, ignoring alpha) for the inspected region.

**Tab-to-focus shortcut**
- Pressing Tab anywhere in the window routes keyboard focus to the chat input field (`root.set_focus(chat)` + `chat.set_focus(chat._input)`). Both links in the focus chain must be set — only setting the bottom link was the original bug.

**Thinking indicator**
- `ChatPanel` gains `thinking: bool` + `_thinking_start: float` attributes. When `thinking` is True and ≥5 seconds have elapsed, three pulsing dots are drawn below the last speech balloon (inside the scroll scissor region); content height is expanded to include them, and the panel auto-scrolls to show them on their first visible frame.
- `PixelClawApp._handle_message()` sets `thinking = True`; `update()` clears it when the reply arrives.

**Agent instruction fixes**
- `edit_image` description now explicitly calls out removing specific objects as a use case.
- `remove_background` description clarified: removes the *background* (making it transparent), not objects within the scene — cross-references `edit_image` for object removal.

**CLAUDE.md additions**
- `debug_output/` directory documented as the primary debugging tool (numbered request/response JSON pairs, cleared on each launch).
- "How to add a new tool" checklist added with all four required steps (create file, register in `__init__.py`, import + instantiate in `main.py`, document in `agent_instructions.md`), with a note that missing step 4 is the most common mistake.

**Pixel info display in MainPanel**
- When the mouse hovers over the image, the bottom gutter shows `(x, y)  #RRGGBBAA` — pixel coordinates and HTML color with alpha.
- Each hex pair is drawn in its own color: RR in red, GG in green, BB in blue, AA in gray.

**Click-to-insert pixel info into chat input**
- Left-clicking on the image inserts pixel data into the chat `InputField` at the cursor position, using three smart heuristics based on the two words immediately preceding the cursor:
  - "color" or "colour" present → insert just the HTML color string.
  - "pos", "position", or "here" present → insert just `(X:n, Y:n)`.
  - Neither → insert `(X:n, Y:n, #RRGGBBAA)` (full info).
- After insertion, focus is restored to the input field.
- Guard: clicks that activate the window (i.e. the window was not focused the previous frame) are ignored, so switching to the app never accidentally inserts data. Implemented by snapshotting `IsWindowFocused()` at the start of `_process_input` and updating it at the end.

**InputField polish when window is inactive**
- Blinking cursor is hidden when `IsWindowFocused()` is false.
- Any active text selection is drawn as an outline rect (not filled) while the window is inactive, matching standard platform conventions.

**Inline markdown rendering** (`agentcore/mdrender.py`)
- New module: `Style` (frozen dataclass with `bold`, `italic`, `code` flags), `Run` (text + style), `parse()` (regex-based inline-markdown parser), `wrap_runs()` (word-wrap respecting style boundaries and explicit newlines), `draw_runs()` (draw a single pre-wrapped line of styled runs).
- Supported spans: `**bold**`, `*italic*`, `***bold-italic***`, `` `code` ``, and underscore variants.
- Code spans rendered in amber; bold uses DejaVuSans-Bold; italic uses DejaVuSans-Oblique; bold-italic uses DejaVuSans-BoldOblique.
- `agentcore/resources.py` extended with `bold_font()`, `italic_font()`, `bold_italic_font()` singletons and `style_font_map()` (lazy dict mapping `Style→Font`); all fonts unloaded by `unload_all()`.
- `ChatPanel` updated to use `parse` + `wrap_runs` + `draw_runs` in place of the old plain-string `_wrap_text`. Both `_entry_height` and the draw loop are updated.
- Added `DejaVuSans-Bold.ttf` to `agentcore/resources/`.

**Word-wrap measurement bug fix**
- `wrap_runs` previously accumulated line width by summing individually-measured words and spaces. Raylib's `MeasureTextEx` adds inter-glyph `spacing` (1.0 px) between every character in a concatenated string, so the drawn width of a merged run was always wider than the sum of its parts — causing bold text to overflow balloon boundaries.
- Fixed by replacing the accumulator with `_measure_line()`, which calls `_merge_line()` on the candidate token list and measures each resulting run as a whole string — exactly mirroring what `draw_runs` will paint.

**`inspect` tool — smart background detection**
- When the image has no transparent pixels, `inspect` now checks whether ≥3/4 corners share the same RGB color.
- If so, reports `Background: #RRGGBB (N/4 corners match)` and computes a tight `Content bbox` based on non-background pixels rather than alpha.
- If not, reports "no background detected" and `Content bbox: full image`.
- Transparent images still use the existing alpha-based path (reports `Background: transparent`).

**`query` tool** (`pixelclaw/tools/query.py`)
- Runs arbitrary Python/numpy code on the active image and returns a string, dict, number, or list — not an ndarray.
- Both `img` (float32) and `image` (uint8) are available; `np`, `ndi`, `skimage` in scope.
- Fills the gap where `apply` can't return computed data (bbox coordinates, statistics, etc.) to the agent. Includes a worked example in the schema description showing how to compute a non-white bounding box.

**`trim` tool** (`pixelclaw/tools/trim.py`)
- Crops the active image to the tight bounding box of non-background pixels.
- Background auto-detected from corners (≥3/4 must agree) or specified as `'#RRGGBB'`, `'#RRGGBBAA'`, or `'transparent'`.
- Optional `tolerance` (per-channel max delta, default 0) for near-background pixels.
- Reports pixels removed from each edge and the detected/used background color.

**`rotate` tool — 90° special case**
- Angles within 0.01° of a 90° multiple (90, 180, 270, and their negatives) now use PIL's lossless `transpose()` rather than the padded-canvas rotation path.
- A 1024×683 image rotated 90° or -90° now produces exactly 683×1024 with no padding.

## Apr 18 2026 (continued — toolbar, file ops, LLM tools)

**`ToolbarButton` class** (`agentcore/toolbarbutton.py`)
- New `Panel` subclass that draws a single button from a texture atlas (96×96 cells) with a bold text label below the icon.
- Four visual states: normal, hover, pressed, disabled — each with a distinct tint.
- `alt_label` attribute: if set and `alt_held` is True, the label swaps to the alternate text (e.g. "Save" → "Save As") without changing behavior.
- `alt_held` is set externally each frame by the parent panel (not queried inside `draw()`) to keep `agentcore` platform-agnostic.
- `on_click` callback fired on mouse-release only if the press originated inside the button.

**`HeaderPanel`** (`pixelclaw/headerpanel.py`)
- Replaces the plain `Panel` used for the header.
- Three `ToolbarButton` children: Open (col 0), Save (col 1, alt_label "Save As"), Close (col 2).
- `setup(workspace, on_open, on_save, on_close_doc)` called after layout; loads a toolbar icon atlas and the app icon texture, both with bilinear filtering.
- `draw()` updates `disabled` state for Save/Close (require an active document) and pushes the current Option-key state to `_btn_save.alt_held`.
- Title "PixelClaw" drawn in bold font; `pixelclaw_icon.png` drawn at 48 px (half of its 96 px source) immediately left of the title, vertically centered.
- `unload()` frees both textures.

**macOS Option/Alt key detection** (`pixelclaw/headerpanel.py`)
- `rl.IsKeyDown(KEY_LEFT_ALT)` is unreliable on macOS because GLFW intercepts the Option key for dead-key composition before reporting it.
- Added module-level `_alt_is_held()` that queries `NSEvent.modifierFlags() & NSAlternateKeyMask` via PyObjC on macOS; falls back to `rl.IsKeyDown` on other platforms.
- This same function is imported into `main.py` for the Save keyboard shortcut path.

**Native file dialogs** (`pixelclaw/file_dialogs.py`)
- `open_images()`: macOS uses `NSOpenPanel` (multi-select, filtered to image types); other platforms use tkinter's `askopenfilenames`.
- `save_image(default_name)`: macOS uses `NSSavePanel`; fallback uses tkinter's `asksaveasfilename`.
- `_refocus_app()`: calls `NSApp.activateIgnoringOtherApps_(True)` unconditionally after every `runModal()` call (both OK and Cancel) so the Raylib window regains keyboard focus after the dialog closes.

**`Document.file_path`** (`agentcore/document.py`, `pixelclaw/document.py`)
- Added `file_path: Path | None = None` to `Document.__init__` — distinct from `path` (which tools use as a display name).
- `ImageDocument.load()` and `save()` now set `self.file_path = path`.
- This separation matters because tools like `generate_image` set `doc.path = Path("generated.png")` without any real on-disk file.

**Smart Save behavior** (`pixelclaw/main.py`)
- If `doc.file_path` is set and Option is not held: save directly to the existing path (no dialog).
- If `doc.file_path` is not set, or Option is held: open the Save dialog (defaulting to current filename).
- Before overwriting, the original is moved to `<stem>.bak<ext>` — but only if that .bak file does not already exist.
- Saving as JPEG: image is alpha-composited onto a white background before encoding.
- After a successful save: `doc.path`, `doc.file_path`, and `doc.dirty` are updated.

**Keyboard shortcuts** (`pixelclaw/main.py`)
- Cmd/Ctrl+O: Open file dialog.
- Cmd/Ctrl+S: Save (same smart-save logic as the button).
- Cmd/Ctrl+W: Close active document.
- All three use `_find_key_for_char()` (layout-aware via `glfwGetKeyName`) so they work correctly on Dvorak, Colemak, etc.
- `_mod()` is re-evaluated fresh before each shortcut check (not cached) to avoid stale modifier state after a blocking native dialog returns.

**`save_document` tool** (`pixelclaw/tools/save_document.py`)
- LLM-callable tool: saves a document (active or named) to its current path or a specified path.
- Path resolution: absolute paths used as-is; bare filenames placed in `doc.file_path.parent`; no extension defaults to `.png`.
- Same .bak backup and JPEG white-composite logic as the UI Save action.
- Never shows a dialog.

**`rename_document` tool** (`pixelclaw/tools/rename_document.py`)
- LLM-callable tool: renames a document's display name and, if it has an on-disk file, renames the file too.
- If `new_name` has no extension, the current extension is preserved.
- Updates both `doc.path` and `doc.file_path`.

**`close_documents` tool update**
- Added `"active"` as a special value alongside `"all except active"`, so the LLM can close the current document with a single short invocation.

---

## Apr 19 2026

**Speech-to-text (STT)** (`agentcore/stt.py`)
- New module using `faster-whisper` (`base.en` model, ~145 MB, downloaded on first use) and `sounddevice` for microphone capture.
- `preload()` warms up the Whisper model in a background thread at app launch.
- `start_recording()` begins buffering mic audio on a daemon thread via `sounddevice.InputStream` (16 kHz, mono, float32, 50 ms chunks).
- Two commit modes chosen at key-release time:
  - `commit_immediate()` — push-to-talk: stop capture now and transcribe everything buffered.
  - `commit_vad()` — tap mode: keep capturing; stop automatically after 1 s of post-speech silence (energy-based VAD, RMS threshold 0.02); after 5 s with no speech detected, cancel and print a diagnostic message.
- `cancel()` aborts any active session without transcribing.
- `state()` returns `"idle"` / `"recording"` / `"transcribing"` for UI polling.
- Recordings below the minimum energy floor are not sent to Whisper (avoids hallucinated output on silence).
- Includes a `__main__` test block (VAD mode, 15 s timeout).

**STT integration in ChatPanel** (`agentcore/chatpanel.py`)
- Mic button drawn to the right of the input field: 28 px wide, shifted 2 px above the input baseline, icon (12×24, half-scale from `MicIcon.png`) tinted gray/pulsing-red/amber for idle/recording/transcribing states. "F5" label drawn in small gray text below the icon.
- Clicking the mic button starts recording + VAD mode (click again to cancel).
- `on_mic_press()` / `on_mic_release()` called by `PixelClawApp._process_input` for the F5 key; distinguishes brief press (< 300 ms → VAD mode) from long press (≥ 300 ms → push-to-talk mode), matching the Apple-menu press convention.
- Transcription results are delivered to the main thread via a `queue.SimpleQueue` drained at the start of each `draw()` call; inserted at the cursor via `InputField.insert_text()`.
- Starting any recording immediately calls `speech.stop()` to cut off any active TTS playback.

**TTS stop** (`agentcore/speech.py`)
- New `stop()` function: sets a `threading.Event` that the `_play_raylib` playback loop checks between each 10 ms sleep; calls `StopSound` and exits immediately when set.
- `_play_raylib` clears the event at the start of each new utterance so normal playback is unaffected.

**F5 key binding** (`pixelclaw/main.py`)
- F5 chosen for STT trigger (F2 was intercepted by the user's keyboard remapping utility).
- `IsKeyPressed(KEY_F5)` → `on_mic_press()`; `IsKeyReleased(KEY_F5)` → `on_mic_release()` polled each frame in `_process_input`, before panel key routing.
- `preload_stt()` called in `on_start()` alongside `preload_speech()`.

**macOS dual-OpenMP crash fix**
- `faster-whisper` (CTranslate2) links `libiomp5`; `numpy`/`scipy` link `libomp`. Both being loaded in the same process caused a SIGSEGV in OpenMP thread-barrier initialization.
- Fix: `os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")` set before all other imports; `WhisperModel` created with `cpu_threads=1, num_workers=1` to prevent CTranslate2 from creating a thread pool, eliminating the conflict entirely.

**InputField: Cmd+A/C/X/V** (`agentcore/inputfield.py`)
- Added `_super()` helper (`KEY_LEFT_SUPER` / `KEY_RIGHT_SUPER`).
- All four clipboard shortcuts (A, C, X, V) now accept either Ctrl or Cmd as the modifier; the existing Ctrl-only guard widened to `(ctrl or _super()) and not _alt()`.

**README — Installation section**
- New "Installation" section with a 3-step clone/create/run code block and a macOS-only platform note.
- Runtime Downloads table updated to include the Whisper `base.en` model (~145 MB).

**New dependencies** (`environment.yml`)
- `faster-whisper` (pip) — Whisper inference via CTranslate2.
- `sounddevice` (pip) — cross-platform microphone capture via PortAudio.

---

## Apr 21 2026

**Compact transcript logger** (`agentcore/log.py`)
- New module that writes a Markdown log file for each session to `logs/YYYY-MM-DD_HH-MM-SS.md`.
- Four functions: `userMsg(text)`, `agentMsg(text)`, `toolUse(name, args, result)`, `error(text)`.
- File created lazily on first write; `logs/` directory created automatically.
- Hooked into `Agent.chat()`: `userMsg` on input, `agentMsg` on any assistant text content, `toolUse` after each tool call, `error` on tool exceptions.

**Adjustable display background** (`pixelclaw/workspace.py`, `pixelclaw/mainpanel.py`, `pixelclaw/tools/set_bg_color.py`)
- `ImageWorkspace` gains a `display_bg: str` field (default `"checkerboard"`).
- `MainPanel.draw()` branches on `display_bg`: checkerboard pattern as before, or a solid `DrawRectangle` fill using PIL's `ImageColor.getrgb()` to parse any HTML color string.
- New `set_background` LLM tool accepts `"checkerboard"` or any HTML color (e.g. `"red"`, `"#FF0000"`, `"rgb(0,128,255)"`); validates via PIL before accepting.
- `render_context()` reports the current display background so the agent is aware of it.
- Agent instructions updated: `set_background` is explicitly marked as a **view-only** setting (does not modify pixels); a rule distinguishes display background from image background (`apply`/`pad`/`edit_image` for the latter).

**`defringe` tool** (`pixelclaw/tools/defringe.py`)
- Removes background-color contamination from semi-transparent edge pixels left by `remove_background`.
- Algorithm: `distance_transform_edt` finds each fringe pixel's nearest fully-opaque neighbor; copies that neighbor's RGB while leaving alpha intact; a `radius` parameter limits the fix to true edge pixels.
- Parameters: `threshold` (alpha value defining "opaque", default 230) and `radius` (max distance in px, default 3.0).
- Agent instructions updated to recommend `defringe` proactively after `remove_background` when halos are visible.

**Agent instruction improvements**
- New rule: when asked to "try again" or "try it again" (with different settings), always call `undo` first before retrying — never stack operations.

**Configurable LLM model**
- `/model` slash command: handled in `_handle_message` before the agent thread. `/model` alone reports the current model; `/model <name>` validates the new model by making a 1-token test completion (background thread, shows thinking indicator), confirms on success, or reverts with an error on failure.
- Model name expansion: `_expand_model()` prepends provider prefixes automatically — `opus`/`sonnet`/`haiku` → `anthropic/claude-`, `claude-` → `anthropic/`, `gemini-` → `gemini/`.
- Initial model configurable via `pixelclaw.cfg` (INI-format, powered by `configargparse`) or `--model` CLI flag; CLI overrides config file overrides `DEFAULT_MODEL`. `pixelclaw.cfg` created with a curated comment block listing common model strings for OpenAI, Anthropic, Google, and Groq.
- `configargparse` added to `environment.yml`.

**InputField: key auto-repeat fix** (`agentcore/app.py`, `agentcore/inputfield.py`)
- `GetKeyPressed()` is a one-shot event queue and never repeats; the existing `IsKeyPressedRepeat` calls inside `on_key_press` were dead code.
- Fix: `App._process_input` now polls `IsKeyPressedRepeat` each frame for a `_REPEAT_KEYS` set (Backspace, Delete, Left, Right, Up, Down, Home, End) and dispatches them through the panel tree. `GetKeyPressed()` handles the initial press for all keys; `IsKeyPressedRepeat` handles OS repeat events only — the two are disjoint.
- Dead `IsKeyPressedRepeat` calls removed from `InputField.on_key_press`.

**InputField: cursor blink reset on movement** (`agentcore/inputfield.py`)
- Cursor now becomes immediately visible whenever it moves, and only starts blinking after being idle for `_BLINK_RATE` seconds.
- Implemented via `_blink_reset_time` (set in `_clamp_scroll()`, `on_mouse_press()`, and `on_mouse_move()`); draw uses `idle = GetTime() - _blink_reset_time` instead of raw `GetTime()`.

