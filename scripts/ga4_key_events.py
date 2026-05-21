"""Mark GA4 events as Key Events (conversion events) via Admin API."""

import yaml
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

with open("/home/ahmet/dev/web/awad-agency/google-ads.yaml") as f:
    cfg = yaml.safe_load(f)

creds = Credentials(
    token=None, refresh_token=cfg["refresh_token"],
    client_id=cfg["client_id"], client_secret=cfg["client_secret"],
    token_uri="https://oauth2.googleapis.com/token",
    scopes=["https://www.googleapis.com/auth/analytics.edit"],
)

admin = build("analyticsadmin", "v1beta", credentials=creds, cache_discovery=False)
property_name = "properties/526377656"

# Events to mark as Key Events (= conversions in GA4 v1beta API)
# These match the names our JS pushes via gtag('event', name, ...)
KEY_EVENTS = [
    {
        "eventName": "generate_lead",
        "countingMethod": "ONCE_PER_EVENT",
        "currencyCode": "USD",  # default conversion value currency
    },
    {
        "eventName": "phone_click",
        "countingMethod": "ONCE_PER_SESSION",
    },
    {
        "eventName": "form_step_3_complete",
        "countingMethod": "ONCE_PER_SESSION",
    },
]

# List existing first to avoid duplicates
print("=== Existing conversion events (= key events) ===", flush=True)
try:
    existing = admin.properties().conversionEvents().list(parent=property_name).execute()
    existing_names = {e["eventName"] for e in existing.get("conversionEvents", [])}
    for ev in existing.get("conversionEvents", []):
        print(f"  {ev['eventName']:<30}  counting={ev.get('countingMethod', 'UNSPECIFIED')}", flush=True)
    if not existing.get("conversionEvents"):
        print("  (none)", flush=True)
except HttpError as e:
    print(f"  Error listing: {e}", flush=True)
    existing_names = set()

print("\n=== Creating new key events ===", flush=True)
for spec in KEY_EVENTS:
    name = spec["eventName"]
    if name in existing_names:
        print(f"  ✓ {name} already exists, skipping", flush=True)
        continue
    try:
        body = {
            "eventName": name,
            "countingMethod": spec.get("countingMethod", "ONCE_PER_EVENT"),
        }
        result = admin.properties().conversionEvents().create(
            parent=property_name,
            body=body,
        ).execute()
        print(f"  ✓ Created '{name}' — {result['name']}", flush=True)
    except HttpError as e:
        print(f"  ✗ Failed for '{name}': {e}", flush=True)
