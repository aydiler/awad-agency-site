"""Create a Call Asset and link it to Auto Insurance + Brand campaigns."""

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

client = GoogleAdsClient.load_from_storage("/home/ahmet/dev/web/awad-agency/google-ads.yaml")
customer_id = "1827370121"
ga = client.get_service("GoogleAdsService")
asset_service = client.get_service("AssetService")
campaign_asset_service = client.get_service("CampaignAssetService")

# Find campaigns
print("=== Finding campaigns ===", flush=True)
q = "SELECT campaign.id, campaign.name FROM campaign WHERE campaign.name IN ('Auto Insurance', 'Brand')"
campaigns = {}
for batch in ga.search_stream(customer_id=customer_id, query=q):
    for row in batch.results:
        campaigns[row.campaign.name] = f"customers/{customer_id}/campaigns/{row.campaign.id}"
        print(f"  '{row.campaign.name}' -> id={row.campaign.id}", flush=True)

# Check existing call assets
print("\n=== Existing call assets ===", flush=True)
q2 = """
    SELECT asset.id, asset.name, asset.call_asset.phone_number, asset.call_asset.country_code
    FROM asset
    WHERE asset.type = 'CALL'
"""
existing_phone = None
for batch in ga.search_stream(customer_id=customer_id, query=q2):
    for row in batch.results:
        a = row.asset
        print(f"  id={a.id}  '{a.name}'  phone='{a.call_asset.phone_number}'  country={a.call_asset.country_code}", flush=True)
        normalized = ''.join(c for c in a.call_asset.phone_number if c.isdigit())
        if normalized == "7343040466":
            existing_phone = f"customers/{customer_id}/assets/{a.id}"

# Create the Call asset if not exists
if existing_phone:
    asset_rn = existing_phone
    print(f"\n=== Reusing existing call asset: {asset_rn} ===", flush=True)
else:
    print("\n=== Creating Call asset ===", flush=True)
    op = client.get_type("AssetOperation")
    a = op.create
    a.name = "Awad Insurance - (734) 304-0466"
    a.call_asset.country_code = "US"
    a.call_asset.phone_number = "7343040466"
    a.call_asset.call_conversion_reporting_state = (
        client.enums.CallConversionReportingStateEnum.USE_ACCOUNT_LEVEL_CALL_CONVERSION_ACTION
    )
    # Ad schedule: Mon-Fri 9am-5pm + Sat 9am-1pm ET
    DOW = client.enums.DayOfWeekEnum
    MIN = client.enums.MinuteOfHourEnum
    for day in [DOW.MONDAY, DOW.TUESDAY, DOW.WEDNESDAY, DOW.THURSDAY, DOW.FRIDAY]:
        sched = a.call_asset.ad_schedule_targets.add()
        sched.day_of_week = day
        sched.start_hour = 9
        sched.end_hour = 17
        sched.start_minute = MIN.ZERO
        sched.end_minute = MIN.ZERO
    sat = a.call_asset.ad_schedule_targets.add()
    sat.day_of_week = DOW.SATURDAY
    sat.start_hour = 9
    sat.end_hour = 13
    sat.start_minute = MIN.ZERO
    sat.end_minute = MIN.ZERO

    try:
        resp = asset_service.mutate_assets(customer_id=customer_id, operations=[op])
        asset_rn = resp.results[0].resource_name
        print(f"  Created: {asset_rn}", flush=True)
    except GoogleAdsException as e:
        print(f"  Failed: {e}", flush=True)
        raise

# Link to each campaign
print("\n=== Linking call asset to campaigns ===", flush=True)
# First check existing links
q3 = f"""
    SELECT campaign_asset.campaign, campaign_asset.asset, campaign_asset.field_type
    FROM campaign_asset
    WHERE campaign_asset.asset = '{asset_rn}'
      AND campaign_asset.status != 'REMOVED'
"""
existing_links = set()
for batch in ga.search_stream(customer_id=customer_id, query=q3):
    for row in batch.results:
        existing_links.add(row.campaign_asset.campaign)
        print(f"  Already linked: {row.campaign_asset.campaign}", flush=True)

link_ops = []
for cname, crn in campaigns.items():
    if crn in existing_links:
        continue
    op = client.get_type("CampaignAssetOperation")
    ca = op.create
    ca.campaign = crn
    ca.asset = asset_rn
    ca.field_type = client.enums.AssetFieldTypeEnum.CALL
    link_ops.append((cname, op))

if link_ops:
    try:
        resp = campaign_asset_service.mutate_campaign_assets(
            customer_id=customer_id,
            operations=[op for _, op in link_ops],
        )
        for (cname, _), result in zip(link_ops, resp.results):
            print(f"  Linked to '{cname}': {result.resource_name}", flush=True)
    except GoogleAdsException as e:
        print(f"  Link failed: {e}", flush=True)
        raise
else:
    print("  No new links needed.", flush=True)

print("\n=== DONE ===", flush=True)
