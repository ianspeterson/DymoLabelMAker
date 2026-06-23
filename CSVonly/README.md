# BO Label Station

BO Label Station is a local Windows web app for printing DYMO fixture labels from a Blackout/CSV patch export.

This version does **not** require an MA plugin. The fixture selection syntax lives inside the website.

The basic workflow is:

1. Start BO Label Station.
2. Upload or re-upload a CSV patch.
3. Confirm/remap the CSV columns if needed.
4. Enter a fixture selection like `101`, `101 t 120`, or `1 thru`.
5. Review links/profile/description/ballast-label options if needed.
6. Print DYMO labels.

---

## For normal users

Download the latest release zip:

`BO_LabelStation_Windows_Portable.zip`

Unzip it and run:

`Start_BOLabelStation_Real_Print.bat`

Then open:

`http://127.0.0.1:5000`

Leave the black terminal window open while using the app. Closing it stops the app.

---

## Requirements

- Windows 10 or Windows 11
- DYMO Connect installed
- DYMO printer working from DYMO Connect first
- A CSV patch export from Blackout or another patch source

BO Label Station prints through the DYMO Connect local service. It does **not** print directly to a printer IP address.

The print path is:

`BO Label Station → DYMO Connect local service → installed DYMO printer`

Before troubleshooting BO Label Station, make sure DYMO Connect can print a normal label.

---

## Real print mode

The normal startup script runs in real print mode:

`Start_BOLabelStation_Real_Print.bat`

That script sets:

`DYMO_SIMULATE=0`

So labels are actually sent to DYMO Connect.

A simulate script may also be included for dry-run testing:

`Start_BOLabelStation_Simulate.bat`

Do not use the simulate script when you want physical labels.

---

## First-time setup

1. Install DYMO Connect.
2. Confirm the DYMO printer prints from DYMO Connect.
3. Download and unzip the release zip.
4. Run `Start_BOLabelStation_Real_Print.bat`.
5. Open `http://127.0.0.1:5000`.
6. Go to **Template** and upload your DYMO label template.
7. Go to **Patch CSV** and upload your current patch CSV.
8. Confirm the column mapping.
9. Go back to **Print Labels**.
10. Enter a fixture range and review/print.

---

# Patch CSV page

Open:

`http://127.0.0.1:5000/patch`

The Patch CSV page lets you upload a new CSV at any time. Re-uploading a CSV replaces the active patch.

The app reads columns by header name, not by column order. This means column order can change and extra columns can exist without breaking the app.

After upload, BO Label Station tries to auto-map useful columns. You can adjust the mapping manually.

## Required mapped fields

These are required:

| App Field | Meaning |
|---|---|
| `fid` | Fixture number / label headline |
| `address_label` | Preferred full address field, such as `1/001`, `21.361`, or `2 / 1-33` |
| `fixturetype` | Fixture type/name |

## Optional mapped fields

These are optional:

| App Field | Meaning |
|---|---|
| `universe` | Universe column, used if address is separate |
| `address` | Address column, used if address is separate |
| `profile` | Mode/profile field |
| `description` | Description/mode text field |
| `link` | Optional link text from CSV |

If the CSV has a Link column and the mapped value is filled in, the app uses that link value.

If there is no Link column, or the Link value is blank, the app falls back to the universe-based Link Map.

---

# Fixture selection syntax

The main page contains the fixture selection input.

Examples:

| Input | Meaning |
|---|---|
| `101` | Print fixture 101 |
| `101 thru 120` | Print fixtures 101 through 120 |
| `101 t 120` | Shorthand for 101 through 120 |
| `1 thru` | Print from fixture 1 onward |

Use a small range first to test your template and printer before printing the whole patch.

---

# DYMO template setup

Open:

`http://127.0.0.1:5000/templates`

Upload a DYMO `.dymo`, `.label`, or XML template containing these placeholder tokens:

| Token | Meaning |
|---|---|
| `#fid` | Fixture ID |
| `#u` | Universe |
| `#add` | Address, zero-padded to three digits |
| `#profile` | Profile/mode line |
| `#description` | Description line |
| `#fixturetype` | Fixture type/name |
| `#link` | Link key / CRMX / hardline text |

Example label text:

```text
#fid
Address: #u/#add
#profile
#description
#fixturetype
#link
```

Address output is normalized to three digits:

| Input | Output |
|---|---|
| `1/1` | `1/001` |
| `1/37` | `1/037` |
| `21.361` | `21/361` |

---

# Link Map

Open:

`http://127.0.0.1:5000/setup`

The Link Map tells BO Label Station what to print in the `#link` field based on universe.

Use it when the CSV does not have a Link column, or when the Link field is blank.

Each Link Map row can contain:

- Universe
- 8-digit Link Key
- Optional letter
- Type: `CRMX`, `CRMX²`, `DMX Hardline`, or `Other`
- Other/custom text

Examples:

| Mapping | Output |
|---|---|
| Key `11111111`, Letter `A`, Type `CRMX` | `11111111A CRMX` |
| Key `11111111`, Letter `B`, Type `CRMX²` | `11111111B CRMX²` |
| Type `DMX Hardline` | `DMX Hardline` |
| Type `Other`, Other text `FOH Hardline` | `FOH Hardline` |

The Bulk Add tool creates multiple universe rows quickly.

The Reset button clears all saved universe mappings. It does not delete templates, CSVs, or profile overrides.

---

# Review screen

The Review screen opens when the app needs confirmation or when you choose to review before printing.

You can edit:

- Link values
- Profile values
- Description values
- Add ballast label options

## Link behavior

Links are synced by universe.

If you change the Link value for one fixture on Universe 21, the other fixtures on Universe 21 update too.

## Profile/description behavior

Profile and description overrides are synced by matching fixture/profile groups, not by universe.

This lets you clean up ugly mode names once and apply the cleanup to matching fixtures.

## Add ballast label

The **Add ballast label** checkbox prints a second copy of matching fixture labels.

The ballast-label choice is grouped by fixture type only, regardless of profile/mode.

Example:

- Fixture type: `Astera Titan Tube`
- Some are Mode 140
- Some are Mode 138

Checking **Add ballast label** for that fixture type applies to all `Astera Titan Tube` rows in the current batch, even if the profiles are different.

The second copy is just another copy of the same filled label.

---

# Data storage

BO Label Station stores user data in the local `data/` folder next to the EXE.

This includes:

- Active CSV
- Column map
- Active uploaded template
- Link Map
- Profile/description overrides

To back up your setup, copy the `data/` folder.

To reset everything, close the app and delete the `data/` folder.

---

# Troubleshooting

## The app opens then closes

Run `Start_BOLabelStation_Real_Print.bat` instead of double-clicking the EXE directly. The terminal will show the error.

Common causes:

- Port 5000 is already in use by another copy of Label Station
- DYMO Connect is not installed/running
- Windows blocked the app with firewall/security settings

## The page does not load

Use:

`http://127.0.0.1:5000`

Do not use HTTPS.

## The printer does not print

Confirm DYMO Connect can print a test label first.

Then check the DYMO service:

`https://127.0.0.1:41951/DYMO/DLS/Printing/StatusConnected`

You may need to accept the browser certificate warning.

The page should say:

`true`

Then check:

`https://127.0.0.1:41951/DYMO/DLS/Printing/GetPrinters`

Your DYMO printer should appear.

## CSV columns are wrong

Go to the Patch CSV page and adjust the column mapping. The app uses the mapping by header name, not column order.

## Link field is blank

Either map a CSV Link column or add a universe mapping on the Link Map page.

## Template fields are missing

Your DYMO template must include:

```text
#fid
#u
#add
#profile
#description
#fixturetype
#link
```

---

# Building the EXE from source

This release kit is meant to be built on Windows.

Double-click:

`BUILD_EXE_FIRST.bat`

After the build finishes, test:

`dist\BOLabelStation\Start_BOLabelStation_Real_Print.bat`

Give users this file:

`dist\BO_LabelStation_Windows_Portable.zip`

Do not give users only the `.exe`. Give them the whole portable zip.
