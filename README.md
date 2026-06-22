# Label Station

**Label Station** is a local web app for printing DYMO fixture labels directly from a grandMA3 patch.

It is designed for lighting programmers, gaffers, and technicians who want to print fixture labels without manually exporting a CSV, editing a spreadsheet, and importing into DYMO Connect.

The basic workflow is:

1. Run Label Station on your laptop.
2. Run the MA3 plugin from grandMA3.
3. Enter a fixture range, such as `201 t 208` or `1 thru`.
4. Label Station pulls fixture info from MA, fills your DYMO template, applies your link map, and prints the labels.

---

## Download

Download the latest Windows release here:

`https://github.com/YOUR_GITHUB_USERNAME/LabelStation/releases/latest`

Download:

`LabelStation_Windows_Portable.zip`

Unzip it, then run:

`Start_LabelStation_Real_Print.bat`

Then open:

`http://127.0.0.1:5000`

---

## Requirements

### Computer

* Windows 10 or Windows 11
* DYMO Connect installed
* A DYMO printer installed and working in DYMO Connect
* grandMA3 onPC or a grandMA3 console on the same network

### Printer

Label Station uses the DYMO Connect background web service. It does **not** print directly to a printer IP address.

The flow is:

`Label Station → DYMO Connect local service → installed DYMO printer`

Before using Label Station, confirm that you can print a normal test label from DYMO Connect.

---

## Quick Start

1. Install DYMO Connect.
2. Confirm your DYMO printer prints from DYMO Connect.
3. Download and unzip `LabelStation_Windows_Portable.zip`.
4. Run `Start_LabelStation_Real_Print.bat`.
5. Open `http://127.0.0.1:5000`.
6. Go to the **Template** page and upload your DYMO template.
7. Go to the **Link Map** page and set up your universe/link mappings.
8. In grandMA3, run the included Label Station plugin.
9. Enter the Label Station server IP and fixture range.
10. Review labels if needed, then print.

---

## Running Label Station

Inside the unzipped folder, run:

`Start_LabelStation_Real_Print.bat`

Leave that window open while using Label Station. Closing the window stops the app.

The app normally runs at:

`http://127.0.0.1:5000`

If using MA3 onPC on the same laptop, use:

`127.0.0.1:5000`

If using a real MA3 console, use the laptop’s network IP shown on the Label Station status page, for example:

`192.168.1.42:5000`

The server listens on all available IPv4 interfaces, including localhost, Wi-Fi, Ethernet, and USB Ethernet. If the console cannot reach the laptop, check Windows Firewall and make sure both devices are on the same network.

---

## Simulate Mode vs Real Print Mode

The normal release starts in real print mode.

Real print mode sends labels to the DYMO Connect service.

If you are testing without a printer, use the simulate mode script if included:

`Start_LabelStation_Simulate.bat`

In simulate mode, Label Station behaves normally but does not physically print.

---

# Template Setup

Label Station uses DYMO XML templates. These are normally `.dymo` files created in DYMO Connect.

## Template Page

Open:

`http://127.0.0.1:5000/templates`

From the Template page, you can:

* Upload a DYMO template
* Validate required placeholder fields
* Preview a sample label
* Download the active template
* Restore the default template

Uploaded templates are saved as the active template and persist after restart.

---

## Creating a Custom DYMO Template

In DYMO Connect, design your label however you want.

Wherever you want Label Station data to appear, type the matching placeholder token into a text object.

Required tokens:

| Token          | Meaning                                  |
| -------------- | ---------------------------------------- |
| `#fid`         | Fixture ID                               |
| `#u`           | DMX universe                             |
| `#add`         | DMX address, zero-padded to three digits |
| `#profile`     | Mode/profile line                        |
| `#description` | Mode description                         |
| `#fixturetype` | Fixture name/type                        |
| `#link`        | Link key / CRMX / hardline text          |

Example label text:

```text
#fid
Address: #u/#add
Profile: #profile
#description
Fixture: #fixturetype
LINK: #link
```

Save the file from DYMO Connect, then upload it on the Template page.

---

## Address Formatting

The `#add` field is always zero-padded to three digits.

Examples:

| MA Patch | Label Output |
| -------- | ------------ |
| `1.001`  | `1/001`      |
| `1.037`  | `1/037`      |
| `21.361` | `21/361`     |

---

## Custom Templates from Other Users

Other users can make their own DYMO templates as long as the template includes the same required tokens.

They can change:

* Label size
* Font
* Layout
* Text placement
* Static text
* Branding
* Backgrounds
* Borders

The app only needs the placeholder tokens to know where to insert data.

The website preview is an approximation. DYMO Connect performs the real final rendering when printing.

---

# Link Map

The Link Map tells Label Station what to put in the `#link` field based on the fixture’s DMX universe.

For example:

| Universe | Link Output       |
| -------- | ----------------- |
| 1        | `11111111A CRMX`  |
| 2        | `11111111B CRMX²` |
| 21       | `72872821 CRMX`   |
| 30       | `DMX Hardline`    |

The Link Map is saved and persists after restart.

---

## Link Map Page

Open:

`http://127.0.0.1:5000/setup`

The Link Map page lets you add, edit, bulk add, or reset universe mappings.

---

## Link Fields

Each Link Map row has these fields:

### Universe

The DMX universe number.

Example:

`21`

### Link Key

An 8-digit linking key.

Example:

`72872821`

The field is limited to 8 digits.

### Letter

An optional single letter that follows the linking key.

Example:

`A`

This creates:

`72872821A`

### Type

Choose one:

* `CRMX`
* `CRMX²`
* `DMX Hardline`
* `Other`

---

## Link Output Examples

### CRMX

Input:

```text
Key: 11111111
Letter: A
Type: CRMX
```

Output:

```text
11111111A CRMX
```

### CRMX²

Input:

```text
Key: 11111111
Letter: B
Type: CRMX²
```

Output:

```text
11111111B CRMX²
```

### DMX Hardline

Input:

```text
Type: DMX Hardline
```

Output:

```text
DMX Hardline
```

### Other

If Type is set to `Other`, the custom text replaces the entire link field.

Input:

```text
Type: Other
Other text: FOH Hardline
```

Output:

```text
FOH Hardline
```

The Link Key and Letter are ignored when using `Other`.

---

## Bulk Add Universes

The Bulk Add tool lets you quickly create multiple universe rows.

Example:

```text
Start Universe: 1
Number of Universes: 10
```

This creates rows for universes 1 through 10.

You can then fill out the link key, optional letter, and type for each row and save them all at once.

---

## Reset All Link Mappings

The Link Map page includes a **Reset all link mappings** button.

This clears all saved universe mappings and returns the map to 0 entries.

This does not delete:

* Uploaded templates
* Profile/mode overrides
* MA plugin settings

---

# Review Screen

When Label Station receives a print job, it checks whether all required data is ready.

If everything is known, it can print immediately.

If something needs attention, the app opens the Review screen.

The Review screen lets you:

* Edit Link values
* Edit Profile values
* Edit Description values
* Save universe Link mappings
* Save profile/mode overrides
* Preview labels
* Discard the batch
* Print the batch

---

## Link Sync Behavior

Link values are grouped by universe.

If you change the Link field for one fixture on Universe 21, all other fixtures on Universe 21 update instantly.

This is because Link is a universe-level value.

---

## Profile and Description Override Behavior

Profile and Description are grouped by matching fixture/profile data, not by universe.

This means if multiple fixtures share the same fixture type and mode data, editing one updates the matching fixtures.

Example:

| Fixture | Fixture Type | Profile  | Description        |
| ------- | ------------ | -------- | ------------------ |
| 201     | Titan Tube   | Mode 140 | D16 CCT GM C RGB S |
| 202     | Titan Tube   | Mode 140 | D16 CCT GM C RGB S |

If you override the Profile or Description on fixture 201, fixture 202 updates too.

But a different fixture type or mode does not change.

This is useful because MA fixture profiles are not always named cleanly.

---

## Live Preview

When you edit Link, Profile, or Description on the Review screen, the label preview updates.

The preview is approximate and may not perfectly match DYMO Connect’s final print rendering, especially for unusual fonts or layouts. The actual print is rendered by DYMO.

---

# MA3 Plugin

The MA3 plugin is included in the release folder:

`ma_plugins/LabelStation_PrintFromPatch_V4_8_ObjectList.lua`

This plugin sends patch data from MA to Label Station.

---

## Installing the MA3 Plugin

For now, the easiest method is to copy and paste the Lua code into a new MA3 plugin.

1. Open the Plugin Pool in MA3.
2. Create a new plugin.
3. Add a Lua component.
4. Paste the contents of `LabelStation_PrintFromPatch_V4_8_ObjectList.lua`.
5. Save the plugin.
6. Run it.

Future versions may include a proper MA3 plugin XML import.

---

## Using the MA3 Plugin

When you run the plugin, it asks for:

### Fixture Range

Examples:

```text
201
201 thru 208
201 t 208
1 thru
```

`201 t 208` is shorthand for `201 thru 208`.

`1 thru` means start at fixture 1 and include everything after that.

### Server IP:Port

If MA3 onPC is running on the same laptop as Label Station:

```text
127.0.0.1:5000
```

If using a real console, enter the laptop’s network IP shown on the Label Station status page:

```text
192.168.1.42:5000
```

The plugin remembers the last server IP you entered.

---

## What Data Comes From MA

The plugin pulls fixture data from the MA patch, including:

* Fixture ID
* Fixture type/name
* Patch address
* Mode/profile information when available

Label Station then formats the label fields.

If the MA mode/profile information is ugly or incorrect, fix it on the Review screen and save the override.

---

# Recommended Workflow

## First-Time Setup

1. Start Label Station.
2. Open `http://127.0.0.1:5000` Or any interface with port 5000
3. Upload your DYMO template on the Template page.
4. Build your Link Map.
5. Confirm your DYMO printer works in DYMO Connect.
6. Import or paste the MA3 plugin.
7. Test one fixture.
8. Test a small range.
9. Print your full patch.

---

## Daily Use

1. Start Label Station.
2. Leave the server window open.
3. Run the MA3 plugin.
4. Enter a fixture range.
5. Review if needed.
6. Print labels.

For a full patch print, use:

```text
1 thru
```

For a small range:

```text
201 t 208
```

For one fixture:

```text
201
```

---

# Troubleshooting

## The web page does not open

Make sure the Label Station server is running.

Open:

`http://127.0.0.1:5000`

Do not use:

`https://127.0.0.1:5000`

Label Station uses plain HTTP, not HTTPS.

If you accidentally use HTTPS, the terminal may show strange errors like:

`Bad HTTP/0.9 request type`

That means a browser tried to use HTTPS against the HTTP server.

---

## MA3 cannot reach the laptop

Check:

* Label Station is running.
* The laptop and console are on the same network.
* You are using the correct laptop IP.
* Windows Firewall is allowing inbound connections to Python/Label Station on port 5000.
* The server page shows the IP address you are trying to use.

For same-laptop MA3 onPC testing, use:

`127.0.0.1:5000`

For a real console, use the laptop’s Ethernet or Wi-Fi IP.

---

## The app says Simulate Mode

Simulate Mode means the app will not physically print.

Use the real print startup script:

`Start_LabelStation_Real_Print.bat`

---

## DYMO printer does not print

First confirm DYMO Connect can print a normal label.

Then check DYMO’s local service:

`https://127.0.0.1:41951/DYMO/DLS/Printing/StatusConnected`

You may need to accept the browser certificate warning.

You want the page to say:

`true`

Then check:

`https://127.0.0.1:41951/DYMO/DLS/Printing/GetPrinters`

Your DYMO printer should appear there.

---

## The template is missing

Go to the Template page and upload your `.dymo` file.

The active uploaded template is saved in:

`data/templates/active.dymo`

---

## A template uploads but fields are missing

Your DYMO template must contain all required tokens:

```text
#fid
#u
#add
#profile
#description
#fixturetype
#link
```

Open the template in DYMO Connect and add any missing tokens.

---

## The preview looks slightly wrong

The website preview is approximate.

The real print is rendered by DYMO Connect.

If the printed label looks correct, the preview issue is not critical.

---

## The review page shows an old batch

Use **Discard this batch**, then send the range again from MA.

Newer versions of Label Station should automatically replace old pending jobs when a new MA request is sent.

---

# Data Storage

Label Station stores user settings in the local `data/` folder.

This may include:

* Link Map
* Uploaded active template
* Profile/mode overrides
* Pending state

If you want to back up your setup, copy the `data/` folder.

If you want a clean reset, close Label Station and delete the `data/` folder.

---

# Release Notes

## v0.1.0

Initial public Windows portable release.

Features:

* DYMO label printing from grandMA3 patch data
* MA3 plugin communication over local HTTP
* Custom DYMO template upload
* Template token validation
* Universe-based Link Map
* Bulk universe add
* Link Map reset
* CRMX / CRMX² / DMX Hardline / Other link types
* Profile and description overrides
* Live review preview
* Single fixture, range, and full patch support
* Portable Windows app
