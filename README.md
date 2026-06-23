# Label Station

A local laptop web app for printing DYMO fixture labels from grandMA3 patch data.

## Current version

This full package includes the latest working pieces from the test session:

- MA3 ObjectList-based patch read plugin.
- Range shortcuts: `201`, `201 thru 203`, `201 t 203`, and open-ended `1 thru` / `1 t`.
- Website review refresh: if you resend from MA, the open review page switches to the latest batch.
- Discard/retry button on review page.
- Universe-based Link Map with bulk add, reset all, CRMX / CRMX² / DMX Hardline / Other.
- Link Map persists in `data/link_map.json`.
- Profile/description override system grouped by matching fixture/profile data, not by universe.
- Live preview updates when fields are edited.
- DYMO template manager with token validation and active-template upload.
- Simulate mode by default so the app can run without the printer.

## Install

Requires Python 3.10+.

```bat
pip install -r requirements.txt
```

## Run

```bat
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

Do **not** use `https://` with this development server.

## DYMO template

The app needs a DYMO template containing these tokens:

```text
#fid
#u
#add
#profile
#description
#fixturetype
#link
```

Go to the **Template** page in the web UI to upload your `.dymo` file. The active template is saved to:

```text
data/templates/active.dymo
```

If you want a default fallback template, place it next to `app.py` named:

```text
LabelTemplate_2026_Python.dymo
```

## Simulate vs real printing

By default, `dymo_print.py` runs in simulate mode. It fills/previews labels but does not send to a real printer.

For real printing on Windows:

```bat
set DYMO_SIMULATE=0
python app.py
```

DYMO Connect must be installed because this app sends labels through DYMO's local background web service.

## MA3 plugin

Use this plugin file:

```text
ma_plugins/LabelStation_PrintFromPatch_V4_8_ObjectList.lua
```

For same-laptop MA onPC testing:

```text
Fixture Range: 1 thru
Server IP:Port: 127.0.0.1:5000
```

For a real console talking to the laptop, use the laptop's network IP instead, for example:

```text
192.168.18.45:5000
```

## Ranges

Supported range input:

```text
201
201 thru 203
201 t 203
1 thru
1 t
201 + 205 + 207
201 t 203 + 300
```

## Data files

Generated data lives in `data/`:

```text
data/link_map.json
data/profile_overrides.json
data/templates/active.dymo
```

These are intentionally persistent. Delete them or use the reset buttons in the UI if you want to start fresh.
