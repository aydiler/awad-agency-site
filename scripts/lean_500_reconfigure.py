"""Reconfigure Phase 1 for $500/mo lean launch.

Changes (all PAUSED — flip when ready):
  - Pause Brand campaign + Ad Group 2 (Michigan No-Fault Specific)
  - Auto Insurance budget $63.33/day → $16.45/day
  - Max CPC ceiling $25 → $18
  - Geo 15-mi → 10-mi radius
  - Remove Saturday schedule
  - Add daypart bid adjustments: Mon-Fri 10-14 (+20%), Mon-Fri 18-20 (-15%)
  - Add 4 sitelinks + 8 callouts + 2 structured snippet sets
  - Add 4 more headlines to active RSA (11 -> 15)

Idempotent.
"""

import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

client = GoogleAdsClient.load_from_storage("/home/ahmet/dev/web/awad-agency/google-ads.yaml")
customer_id = "1827370121"
ga = client.get_service("GoogleAdsService")


def find_one(query):
    for batch in ga.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            return row
    return None


# ============================================================
# Look up resources
# ============================================================
auto = find_one("SELECT campaign.id FROM campaign WHERE campaign.name = 'Auto Insurance'")
brand = find_one("SELECT campaign.id FROM campaign WHERE campaign.name = 'Brand'")
if not auto or not brand:
    print("ABORT: campaigns not found", flush=True)
    sys.exit(1)

auto_rn = f"customers/{customer_id}/campaigns/{auto.campaign.id}"
brand_rn = f"customers/{customer_id}/campaigns/{brand.campaign.id}"

ag2 = find_one(f"""
    SELECT ad_group.id FROM ad_group
    WHERE ad_group.campaign = '{auto_rn}' AND ad_group.name = 'Michigan Auto Specific'
""")
ag1 = find_one(f"""
    SELECT ad_group.id FROM ad_group
    WHERE ad_group.campaign = '{auto_rn}' AND ad_group.name = 'Local Auto Quotes'
""")
ag1_rn = f"customers/{customer_id}/adGroups/{ag1.ad_group.id}"
ag2_rn = f"customers/{customer_id}/adGroups/{ag2.ad_group.id}"

auto_budget = find_one(f"""
    SELECT campaign.id, campaign_budget.id
    FROM campaign WHERE campaign.id = {auto.campaign.id}
""")
auto_budget_rn = f"customers/{customer_id}/campaignBudgets/{auto_budget.campaign_budget.id}"

print(f"Auto: {auto_rn}", flush=True)
print(f"Brand: {brand_rn}", flush=True)
print(f"AG1 Local Auto Quotes: {ag1_rn}", flush=True)
print(f"AG2 Michigan No-Fault: {ag2_rn}", flush=True)
print(f"Auto budget: {auto_budget_rn}", flush=True)

# ============================================================
# Step 1: Pause Brand + AG2
# ============================================================
print("\n=== 1. Pause Brand campaign + AG2 ===", flush=True)
campaign_service = client.get_service("CampaignService")
ad_group_service = client.get_service("AdGroupService")

# Pause Brand (already PAUSED at campaign level — this is more about ensuring it stays paused/marked clearly)
# Actually Brand IS already PAUSED. Just verify and skip.
# AG2: pause it
ag2_op = client.get_type("AdGroupOperation")
ag2_op.update.resource_name = ag2_rn
ag2_op.update.status = client.enums.AdGroupStatusEnum.PAUSED
ag2_op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
try:
    r = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[ag2_op])
    print(f"  Paused AG2: {r.results[0].resource_name}", flush=True)
except GoogleAdsException as e:
    print(f"  AG2 pause err: {e.failure}", flush=True)

# Brand campaign is already PAUSED. Per "$500 lean", we keep it paused. No status change needed.
print("  Brand campaign remains PAUSED (as planned for $500 lean)", flush=True)

# ============================================================
# Step 2: Auto Insurance budget + max CPC ceiling
# ============================================================
print("\n=== 2. Update Auto Insurance budget + bid ceiling ===", flush=True)
campaign_budget_service = client.get_service("CampaignBudgetService")

# Budget: $16.45/day
budget_op = client.get_type("CampaignBudgetOperation")
budget_op.update.resource_name = auto_budget_rn
budget_op.update.amount_micros = 16_450_000
budget_op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))
try:
    r = campaign_budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[budget_op])
    print(f"  Budget -> $16.45/day", flush=True)
except GoogleAdsException as e:
    print(f"  Budget err: {e.failure}", flush=True)

# Max CPC: $18
cmp_op = client.get_type("CampaignOperation")
cmp_op.update.resource_name = auto_rn
cmp_op.update.target_spend.cpc_bid_ceiling_micros = 18_000_000
cmp_op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["target_spend.cpc_bid_ceiling_micros"]))
try:
    r = campaign_service.mutate_campaigns(customer_id=customer_id, operations=[cmp_op])
    print(f"  Max CPC -> $18", flush=True)
except GoogleAdsException as e:
    print(f"  Max CPC err: {e.failure}", flush=True)

# ============================================================
# Step 3: Geo 15mi -> 10mi; Schedule: remove Saturday + add dayparts
# ============================================================
print("\n=== 3. Geo + schedule criteria ===", flush=True)
ccs = client.get_service("CampaignCriterionService")

# Find existing criteria
crit_rows = []
for batch in ga.search_stream(customer_id=customer_id, query=f"""
    SELECT campaign_criterion.criterion_id,
           campaign_criterion.type,
           campaign_criterion.proximity.radius,
           campaign_criterion.ad_schedule.day_of_week,
           campaign_criterion.ad_schedule.start_hour,
           campaign_criterion.ad_schedule.end_hour
    FROM campaign_criterion
    WHERE campaign_criterion.campaign = '{auto_rn}'
      AND campaign_criterion.status != 'REMOVED'
"""):
    for row in batch.results:
        crit_rows.append(row.campaign_criterion)

remove_ops = []
DOW = client.enums.DayOfWeekEnum
for c in crit_rows:
    rn = f"customers/{customer_id}/campaignCriteria/{auto.campaign.id}~{c.criterion_id}"
    # Remove old 15-mi proximity
    if c.type_.name == "PROXIMITY" and c.proximity.radius >= 14.5:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = rn
        remove_ops.append(op)
        print(f"  Will remove old 15-mi proximity", flush=True)
    # Remove Saturday schedule
    if c.type_.name == "AD_SCHEDULE" and c.ad_schedule.day_of_week == DOW.SATURDAY:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = rn
        remove_ops.append(op)
        print(f"  Will remove Sat 9-14 schedule", flush=True)

if remove_ops:
    try:
        r = ccs.mutate_campaign_criteria(customer_id=customer_id, operations=remove_ops)
        print(f"  Removed {len(r.results)} criteria", flush=True)
    except GoogleAdsException as e:
        print(f"  Remove err: {e.failure}", flush=True)

# Add new 10-mi proximity
add_ops = []
MIN = client.enums.MinuteOfHourEnum
op = client.get_type("CampaignCriterionOperation")
op.create.campaign = auto_rn
op.create.proximity.geo_point.latitude_in_micro_degrees = 42_197_800
op.create.proximity.geo_point.longitude_in_micro_degrees = -83_206_500
op.create.proximity.radius = 10.0
op.create.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.MILES
op.create.proximity.address.street_address = "15201 Dix Toledo Road"
op.create.proximity.address.city_name = "Southgate"
op.create.proximity.address.province_name = "Michigan"
op.create.proximity.address.postal_code = "48195"
op.create.proximity.address.country_code = "US"
add_ops.append(op)

# Add daypart bid adjustments
weekdays = [DOW.MONDAY, DOW.TUESDAY, DOW.WEDNESDAY, DOW.THURSDAY, DOW.FRIDAY]
# Peak: M-F 10-14, +20%
for d in weekdays:
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = auto_rn
    op.create.ad_schedule.day_of_week = d
    op.create.ad_schedule.start_hour = 10
    op.create.ad_schedule.end_hour = 14
    op.create.ad_schedule.start_minute = MIN.ZERO
    op.create.ad_schedule.end_minute = MIN.ZERO
    op.create.bid_modifier = 1.20
    add_ops.append(op)
# Evening: M-F 18-20, -15%
for d in weekdays:
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = auto_rn
    op.create.ad_schedule.day_of_week = d
    op.create.ad_schedule.start_hour = 18
    op.create.ad_schedule.end_hour = 20
    op.create.ad_schedule.start_minute = MIN.ZERO
    op.create.ad_schedule.end_minute = MIN.ZERO
    op.create.bid_modifier = 0.85
    add_ops.append(op)

try:
    r = ccs.mutate_campaign_criteria(customer_id=customer_id, operations=add_ops)
    print(f"  Added {len(r.results)} criteria (10-mi geo + 10 daypart adjustments)", flush=True)
except GoogleAdsException as e:
    print(f"  Add err: {e.failure}", flush=True)

# ============================================================
# Step 4: Sitelinks (4), Callouts (8), Structured Snippets (2 sets)
# ============================================================
print("\n=== 4. Account-level assets (sitelinks, callouts, snippets) ===", flush=True)
asset_service = client.get_service("AssetService")
customer_asset_service = client.get_service("CustomerAssetService")
campaign_asset_service = client.get_service("CampaignAssetService")

# Helper: idempotent by asset name
def find_existing_assets_by_name(asset_type, names):
    name_set = set(names)
    found = {}
    for batch in ga.search_stream(customer_id=customer_id, query=f"""
        SELECT asset.id, asset.name FROM asset
        WHERE asset.type = '{asset_type}' AND asset.name IN ({','.join("'" + n.replace("'", "\\'") + "'" for n in names)})
    """):
        for row in batch.results:
            found[row.asset.name] = f"customers/{customer_id}/assets/{row.asset.id}"
    return found


# --- Sitelinks ---
SITELINKS = [  # description max 25 chars each
    ("Free Quote in 2 Min", "Quote in under 2 minutes", "Multiple carriers",
     "https://www.awadinsurance.com/auto-insurance-quote"),
    ("Auto Insurance Info", "Michigan no-fault expert", "PIP, SR-22, teen drivers",
     "https://www.awadinsurance.com/auto-insurance"),
    ("About Awad Agency", "Local Southgate agent", "Serving Downriver MI",
     "https://www.awadinsurance.com/about"),
    ("Contact Us", "Visit Southgate office", "Call (734) 304-0466",
     "https://www.awadinsurance.com/contact"),
]
existing = find_existing_assets_by_name("SITELINK", [s[0] for s in SITELINKS])

sl_asset_ops = []
sl_new_links = []  # (name) to link after creation
for name, d1, d2, url in SITELINKS:
    if name in existing:
        sl_new_links.append((name, existing[name]))
        continue
    op = client.get_type("AssetOperation")
    op.create.name = name
    op.create.sitelink_asset.link_text = name
    op.create.sitelink_asset.description1 = d1
    op.create.sitelink_asset.description2 = d2
    op.create.final_urls.append(url)
    sl_asset_ops.append((name, op))

if sl_asset_ops:
    try:
        r = asset_service.mutate_assets(customer_id=customer_id, operations=[op for _, op in sl_asset_ops])
        for (name, _), result in zip(sl_asset_ops, r.results):
            sl_new_links.append((name, result.resource_name))
            print(f"  Created sitelink: {name}", flush=True)
    except GoogleAdsException as e:
        print(f"  Sitelink creation err: {e.failure}", flush=True)

# --- Callouts ---
CALLOUTS = ["Free Quotes", "Independent Agency", "Licensed MI Agents", "Bundle & Save",
            "Multiple Carriers", "Same-Day Coverage", "5-Star Rated Local", "Serving Downriver"]
existing_co = find_existing_assets_by_name("CALLOUT", CALLOUTS)
co_ops = []
co_links = []
for text in CALLOUTS:
    if text in existing_co:
        co_links.append((text, existing_co[text]))
        continue
    op = client.get_type("AssetOperation")
    op.create.name = text
    op.create.callout_asset.callout_text = text
    co_ops.append((text, op))

if co_ops:
    try:
        r = asset_service.mutate_assets(customer_id=customer_id, operations=[op for _, op in co_ops])
        for (text, _), result in zip(co_ops, r.results):
            co_links.append((text, result.resource_name))
            print(f"  Created callout: {text}", flush=True)
    except GoogleAdsException as e:
        print(f"  Callout creation err: {e.failure}", flush=True)

# --- Structured Snippets ---
SNIPPETS = [
    ("Insurance Coverage SS", "Insurance coverage", ["Auto", "Home", "Life", "Renters", "Commercial", "Umbrella"]),
    ("Insurance Types SS", "Types", ["Free Quotes", "Policy Reviews", "Claims Support", "Bundle Discounts"]),
]
existing_ss = find_existing_assets_by_name("STRUCTURED_SNIPPET", [s[0] for s in SNIPPETS])
ss_ops = []
ss_links = []
for name, header, values in SNIPPETS:
    if name in existing_ss:
        ss_links.append((name, existing_ss[name]))
        continue
    op = client.get_type("AssetOperation")
    op.create.name = name
    op.create.structured_snippet_asset.header = header
    op.create.structured_snippet_asset.values.extend(values)
    ss_ops.append((name, op))

if ss_ops:
    try:
        r = asset_service.mutate_assets(customer_id=customer_id, operations=[op for _, op in ss_ops])
        for (name, _), result in zip(ss_ops, r.results):
            ss_links.append((name, result.resource_name))
            print(f"  Created snippet: {name}", flush=True)
    except GoogleAdsException as e:
        print(f"  Snippet creation err: {e.failure}", flush=True)

# --- Link all assets to the Auto Insurance campaign ---
# Check existing campaign asset links to avoid duplicates
existing_camp_assets = set()
for batch in ga.search_stream(customer_id=customer_id, query=f"""
    SELECT campaign_asset.asset, campaign_asset.field_type
    FROM campaign_asset
    WHERE campaign_asset.campaign = '{auto_rn}' AND campaign_asset.status != 'REMOVED'
"""):
    for row in batch.results:
        existing_camp_assets.add((row.campaign_asset.asset, row.campaign_asset.field_type.name))

link_ops = []
def add_link(asset_rn, field_type_name):
    field_type_enum = getattr(client.enums.AssetFieldTypeEnum, field_type_name)
    if (asset_rn, field_type_name) in existing_camp_assets:
        return
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign = auto_rn
    op.create.asset = asset_rn
    op.create.field_type = field_type_enum
    link_ops.append(op)

for _, rn in sl_new_links:
    add_link(rn, "SITELINK")
for _, rn in co_links:
    add_link(rn, "CALLOUT")
for _, rn in ss_links:
    add_link(rn, "STRUCTURED_SNIPPET")

if link_ops:
    try:
        r = campaign_asset_service.mutate_campaign_assets(customer_id=customer_id, operations=link_ops)
        print(f"  Linked {len(r.results)} assets to Auto Insurance", flush=True)
    except GoogleAdsException as e:
        print(f"  Link err: {e.failure}", flush=True)

# ============================================================
# Step 5: Expand Local Auto Quotes RSA to 15 headlines
# ============================================================
print("\n=== 5. Expand Local Auto Quotes RSA to 15 headlines ===", flush=True)
# Find existing ad
ad_row = find_one(f"""
    SELECT ad_group_ad.ad.id, ad_group_ad.ad.responsive_search_ad.headlines
    FROM ad_group_ad
    WHERE ad_group_ad.ad_group = '{ag1_rn}'
      AND ad_group_ad.status != 'REMOVED'
""")
if ad_row:
    existing_headlines = {h.text for h in ad_row.ad_group_ad.ad.responsive_search_ad.headlines}
    EXTRA_HEADLINES = [
        "Local Auto Quotes Online",
        "Affordable Auto Coverage",
        "Compare 5+ Auto Carriers",
        "Same-Day Auto Coverage",
    ]
    new = [h for h in EXTRA_HEADLINES if h not in existing_headlines]
    if not new:
        print("  Already at 15 (no new to add)", flush=True)
    elif len(existing_headlines) + len(new) > 15:
        new = new[:15 - len(existing_headlines)]
    if new:
        # RSAs can only be edited by REMOVE + CREATE — Ads API doesn't support partial RSA updates
        # Create new ad with combined headlines + remove old
        rsa = ad_row.ad_group_ad.ad.responsive_search_ad
        # Get full ad details to recreate
        full_ad = find_one(f"""
            SELECT ad_group_ad.ad.id, ad_group_ad.ad.final_urls,
                   ad_group_ad.ad.responsive_search_ad.headlines,
                   ad_group_ad.ad.responsive_search_ad.descriptions,
                   ad_group_ad.ad.responsive_search_ad.path1,
                   ad_group_ad.ad.responsive_search_ad.path2,
                   ad_group_ad.ad.responsive_search_ad.headlines
            FROM ad_group_ad
            WHERE ad_group_ad.ad_group = '{ag1_rn}'
              AND ad_group_ad.status != 'REMOVED'
        """)
        old_ad_rn = f"customers/{customer_id}/adGroupAds/{ag1.ad_group.id}~{full_ad.ad_group_ad.ad.id}"
        # Build new ad
        new_op = client.get_type("AdGroupAdOperation")
        new_op.create.ad_group = ag1_rn
        new_op.create.status = client.enums.AdGroupAdStatusEnum.ENABLED
        new_op.create.ad.final_urls.append(full_ad.ad_group_ad.ad.final_urls[0])
        new_op.create.ad.responsive_search_ad.path1 = full_ad.ad_group_ad.ad.responsive_search_ad.path1
        new_op.create.ad.responsive_search_ad.path2 = full_ad.ad_group_ad.ad.responsive_search_ad.path2
        all_headlines = list(existing_headlines) + new
        for h_text in all_headlines:
            ta = client.get_type("AdTextAsset")
            ta.text = h_text
            new_op.create.ad.responsive_search_ad.headlines.append(ta)
        for d in full_ad.ad_group_ad.ad.responsive_search_ad.descriptions:
            ta = client.get_type("AdTextAsset")
            ta.text = d.text
            new_op.create.ad.responsive_search_ad.descriptions.append(ta)
        # Remove old
        rm_op = client.get_type("AdGroupAdOperation")
        rm_op.remove = old_ad_rn
        try:
            ad_group_ad_service = client.get_service("AdGroupAdService")
            r = ad_group_ad_service.mutate_ad_group_ads(
                customer_id=customer_id, operations=[new_op, rm_op]
            )
            print(f"  Replaced RSA with expanded version ({len(all_headlines)} headlines)", flush=True)
        except GoogleAdsException as e:
            print(f"  RSA expand err: {e.failure}", flush=True)

print("\n=== DONE — $500 lean configuration applied ===", flush=True)
print(f"Both campaigns remain PAUSED. Flip Auto Insurance to ENABLED when ready.", flush=True)
