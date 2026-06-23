"""Local test sender for Label Station. Run while app.py is running."""
import json
import urllib.request

payload = {
    "fixtures": [
        {
            "fid": "703",
            "universe": 1,
            "address": 463,
            "profile": "37 ch",
            "description": "Limited CCT & RGB + Control - 16 Bit",
            "fixturetype": "Proteus Maximus",
        },
        {
            "fid": "704",
            "universe": 5,
            "address": 1,
            "profile": "37 ch",
            "description": "Limited CCT & RGB + Control - 16 Bit",
            "fixturetype": "Proteus Maximus",
        },
    ]
}

body = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:5000/print",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=5) as r:
    print(r.status, r.read().decode("utf-8"))
