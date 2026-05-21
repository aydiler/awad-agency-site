"""Build Phase 1 Search campaigns per GOOGLE-ADS-PLAN.md (revised May 2026).

Creates two campaigns in PAUSED status:
  - "Auto Insurance" — Search, $63.33/day, 2 ad groups (Local + MI No-Fault)
  - "Brand" — Search, $3.33/day, 1 ad group (Awad Insurance)

Configures: geo proximity 15-mi around Southgate office, mobile +20% bid,
ad schedule Mon-Fri 7am-8pm + Sat 9am-2pm ET, attaches the Master Negatives
shared list, Maximize Clicks with $25 max CPC cap.

Idempotent: aborts if "Auto Insurance" or "Brand" already exists.
"""

import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.api_core import protobuf_helpers

client = GoogleAdsClient.load_from_storage("/home/ahmet/dev/web/awad-agency/google-ads.yaml")
customer_id = "1827370121"
ga = client.get_service("GoogleAdsService")

# ---- Lookup helpers (script is idempotent — re-running picks up where last run left off) ----
print("=== Looking up existing state ===", flush=True)


def find_campaign(name):
    q = f"SELECT campaign.id FROM campaign WHERE campaign.name = '{name}' AND campaign.status != 'REMOVED'"
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for row in batch.results:
            return f"customers/{customer_id}/campaigns/{row.campaign.id}"
    return None


def find_ad_group(campaign_rn, name):
    q = f"SELECT ad_group.id FROM ad_group WHERE ad_group.campaign = '{campaign_rn}' AND ad_group.name = '{name}' AND ad_group.status != 'REMOVED'"
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for row in batch.results:
            return f"customers/{customer_id}/adGroups/{row.ad_group.id}"
    return None


def ad_group_has_ads(ad_group_rn):
    q = f"SELECT ad_group_ad.ad.id FROM ad_group_ad WHERE ad_group_ad.ad_group = '{ad_group_rn}' AND ad_group_ad.status != 'REMOVED'"
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for _ in batch.results:
            return True
    return False


def ad_group_keyword_count(ad_group_rn):
    q = f"SELECT ad_group_criterion.criterion_id FROM ad_group_criterion WHERE ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.ad_group = '{ad_group_rn}' AND ad_group_criterion.status != 'REMOVED'"
    cnt = 0
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for _ in batch.results:
            cnt += 1
    return cnt


def campaign_has_negative_set(campaign_rn, set_id):
    q = f"SELECT campaign_shared_set.shared_set FROM campaign_shared_set WHERE campaign_shared_set.campaign = '{campaign_rn}'"
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for row in batch.results:
            if str(set_id) in row.campaign_shared_set.shared_set:
                return True
    return False


def campaign_has_proximity(campaign_rn):
    q = f"SELECT campaign_criterion.criterion_id, campaign_criterion.type FROM campaign_criterion WHERE campaign_criterion.campaign = '{campaign_rn}' AND campaign_criterion.type = 'PROXIMITY'"
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for _ in batch.results:
            return True
    return False

# ---- Shared services ----
campaign_budget_service = client.get_service("CampaignBudgetService")
campaign_service = client.get_service("CampaignService")
ad_group_service = client.get_service("AdGroupService")
ad_group_ad_service = client.get_service("AdGroupAdService")
ad_group_criterion_service = client.get_service("AdGroupCriterionService")
campaign_criterion_service = client.get_service("CampaignCriterionService")
campaign_shared_set_service = client.get_service("CampaignSharedSetService")

# ============================================================
# STEP 1: BUDGETS (idempotent — reuses if name matches)
# ============================================================
print("=== Step 1: Create/reuse campaign budgets ===", flush=True)


def get_or_create_budget(name, daily_micros):
    q = f"SELECT campaign_budget.id, campaign_budget.name FROM campaign_budget WHERE campaign_budget.name = '{name}' AND campaign_budget.status != 'REMOVED'"
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for row in batch.results:
            rn = f"customers/{customer_id}/campaignBudgets/{row.campaign_budget.id}"
            print(f"  Reusing budget: {name} -> {rn}", flush=True)
            return rn
    op = client.get_type("CampaignBudgetOperation")
    b = op.create
    b.name = name
    b.amount_micros = daily_micros
    b.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False
    resp = campaign_budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[op])
    rn = resp.results[0].resource_name
    print(f"  Created budget: {name} = ${daily_micros / 1_000_000:.2f}/day  -> {rn}", flush=True)
    return rn


auto_budget_rn = get_or_create_budget("Auto Insurance — Phase 1", 63_330_000)
brand_budget_rn = get_or_create_budget("Brand — Phase 1", 3_330_000)

# ============================================================
# STEP 2: CAMPAIGNS (paused, idempotent)
# ============================================================
print("\n=== Step 2: Create/reuse campaigns (PAUSED) ===", flush=True)


def create_campaign(name, budget_rn):
    op = client.get_type("CampaignOperation")
    c = op.create
    c.name = name
    c.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    c.status = client.enums.CampaignStatusEnum.PAUSED
    c.campaign_budget = budget_rn
    c.bidding_strategy_type = client.enums.BiddingStrategyTypeEnum.TARGET_SPEND
    # Maximize Clicks (= TARGET_SPEND) with max CPC ceiling
    c.target_spend.cpc_bid_ceiling_micros = 25_000_000  # $25 max CPC
    # Networks: Search only — disable partners and display
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False
    c.network_settings.target_content_network = False
    c.network_settings.target_partner_search_network = False
    # (Ad rotation mode is deprecated at campaign level — Google manages it automatically)
    # Geo: presence only (not interest)
    c.geo_target_type_setting.positive_geo_target_type = (
        client.enums.PositiveGeoTargetTypeEnum.PRESENCE
    )
    c.geo_target_type_setting.negative_geo_target_type = (
        client.enums.NegativeGeoTargetTypeEnum.PRESENCE
    )
    # EU political advertising declaration (required, not applicable to insurance)
    c.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    resp = campaign_service.mutate_campaigns(customer_id=customer_id, operations=[op])
    rn = resp.results[0].resource_name
    print(f"  Created campaign: {name} -> {rn}", flush=True)
    return rn


auto_campaign_rn = find_campaign("Auto Insurance") or create_campaign("Auto Insurance", auto_budget_rn)
brand_campaign_rn = find_campaign("Brand") or create_campaign("Brand", brand_budget_rn)
if find_campaign("Auto Insurance"):
    print(f"  Reusing 'Auto Insurance' -> {auto_campaign_rn}", flush=True)
if find_campaign("Brand"):
    print(f"  Reusing 'Brand' -> {brand_campaign_rn}", flush=True)

# ============================================================
# STEP 3: CAMPAIGN CRITERIA — geo, language, device, schedule, negatives
# ============================================================
print("\n=== Step 3: Configure campaign criteria ===", flush=True)


def cc_proximity(campaign_rn, lat, lng, radius_mi):
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = campaign_rn
    c.proximity.geo_point.latitude_in_micro_degrees = int(lat * 1_000_000)
    c.proximity.geo_point.longitude_in_micro_degrees = int(lng * 1_000_000)
    c.proximity.radius = radius_mi
    c.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.MILES
    # Address (optional but recommended for display)
    c.proximity.address.street_address = "15201 Dix Toledo Road"
    c.proximity.address.city_name = "Southgate"
    c.proximity.address.province_name = "Michigan"
    c.proximity.address.postal_code = "48195"
    c.proximity.address.country_code = "US"
    return op


def cc_language(campaign_rn, language_id):
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = campaign_rn
    c.language.language_constant = f"languageConstants/{language_id}"
    return op


def cc_device(campaign_rn, device_enum, bid_modifier):
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = campaign_rn
    c.device.type_ = device_enum
    c.bid_modifier = bid_modifier
    return op


def cc_schedule(campaign_rn, day, start_h, end_h):
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = campaign_rn
    c.ad_schedule.day_of_week = day
    c.ad_schedule.start_hour = start_h
    c.ad_schedule.end_hour = end_h
    c.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
    c.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
    return op


# Apply to both campaigns
LAT, LNG = 42.1978, -83.2065
DOW = client.enums.DayOfWeekEnum
DEV = client.enums.DeviceEnum
weekday_schedule = [DOW.MONDAY, DOW.TUESDAY, DOW.WEDNESDAY, DOW.THURSDAY, DOW.FRIDAY]

criteria_ops = []
for campaign_rn in (auto_campaign_rn, brand_campaign_rn):
    if campaign_has_proximity(campaign_rn):
        print(f"  Skipping criteria for {campaign_rn} — already configured", flush=True)
        continue
    # Geo: 15-mi radius around office
    criteria_ops.append(cc_proximity(campaign_rn, LAT, LNG, 15.0))
    # Language: English (id 1000)
    criteria_ops.append(cc_language(campaign_rn, 1000))
    # Device bid modifiers — mobile +20%, tablet -10%
    criteria_ops.append(cc_device(campaign_rn, DEV.MOBILE, 1.20))
    criteria_ops.append(cc_device(campaign_rn, DEV.TABLET, 0.90))
    # Ad schedule: Mon-Fri 7-20, Sat 9-14 (ET assumed)
    for day in weekday_schedule:
        criteria_ops.append(cc_schedule(campaign_rn, day, 7, 20))
    criteria_ops.append(cc_schedule(campaign_rn, DOW.SATURDAY, 9, 14))

if criteria_ops:
    cc_resp = campaign_criterion_service.mutate_campaign_criteria(
        customer_id=customer_id, operations=criteria_ops
    )
    print(f"  Applied {len(cc_resp.results)} campaign criteria (geo, language, device, schedule)", flush=True)
else:
    print(f"  Criteria already in place on both campaigns", flush=True)

# ============================================================
# STEP 4: Attach negative keyword shared set
# ============================================================
print("\n=== Step 4: Attach negative keyword shared list ===", flush=True)
SHARED_SET_ID = "12008848774"  # "Awad Insurance - Master Negatives" (122 keywords)
shared_set_rn = f"customers/{customer_id}/sharedSets/{SHARED_SET_ID}"

attach_ops = []
for campaign_rn in (auto_campaign_rn, brand_campaign_rn):
    if campaign_has_negative_set(campaign_rn, SHARED_SET_ID):
        print(f"  Already attached to {campaign_rn}", flush=True)
        continue
    op = client.get_type("CampaignSharedSetOperation")
    css = op.create
    css.campaign = campaign_rn
    css.shared_set = shared_set_rn
    attach_ops.append(op)

if attach_ops:
    cs_resp = campaign_shared_set_service.mutate_campaign_shared_sets(
        customer_id=customer_id, operations=attach_ops
    )
    print(f"  Attached shared negative list to {len(cs_resp.results)} campaigns", flush=True)

# ============================================================
# STEP 5: AD GROUPS
# ============================================================
print("\n=== Step 5: Create ad groups ===", flush=True)


def create_ad_group(campaign_rn, name, default_cpc_micros=15_000_000):
    op = client.get_type("AdGroupOperation")
    ag = op.create
    ag.name = name
    ag.campaign = campaign_rn
    ag.status = client.enums.AdGroupStatusEnum.ENABLED
    ag.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    ag.cpc_bid_micros = default_cpc_micros
    resp = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[op])
    rn = resp.results[0].resource_name
    print(f"  Created ad group: {name} -> {rn}", flush=True)
    return rn


ag_local_rn = find_ad_group(auto_campaign_rn, "Local Auto Quotes") or create_ad_group(auto_campaign_rn, "Local Auto Quotes", 18_000_000)
ag_mi_rn = find_ad_group(auto_campaign_rn, "Michigan Auto Specific") or create_ad_group(auto_campaign_rn, "Michigan Auto Specific", 15_000_000)
ag_brand_rn = find_ad_group(brand_campaign_rn, "Awad Insurance") or create_ad_group(brand_campaign_rn, "Awad Insurance", 5_000_000)

# ============================================================
# STEP 6: KEYWORDS
# ============================================================
print("\n=== Step 6: Add keywords ===", flush=True)

KEYWORDS = {
    ag_local_rn: [  # Ad Group 1: Local Auto Quotes
        ("auto insurance quote southgate", "EXACT"),
        ("car insurance quote southgate MI", "EXACT"),
        ("auto insurance southgate michigan", "EXACT"),
        ("car insurance southgate", "EXACT"),
        ("auto insurance quotes near me", "PHRASE"),
        ("car insurance quote downriver", "PHRASE"),
        ("auto insurance quote downriver MI", "PHRASE"),
        ("auto insurance agent near me", "PHRASE"),
        ("car insurance agent near me", "PHRASE"),
        ("auto insurance agency downriver", "PHRASE"),
    ],
    ag_mi_rn: [  # Ad Group 2: Michigan Auto Specific
        ("michigan no-fault insurance agent", "EXACT"),
        ("no-fault auto insurance southgate", "EXACT"),
        ("michigan no-fault insurance quotes", "PHRASE"),
        ("michigan PIP coverage options", "PHRASE"),
        ("SR-22 insurance downriver", "PHRASE"),
        ("SR-22 insurance southgate MI", "PHRASE"),
        ("teen driver insurance southgate", "PHRASE"),
        ("cheap car insurance downriver MI", "PHRASE"),
        ("michigan auto insurance rates", "PHRASE"),
        ("no-fault insurance agent near me", "PHRASE"),
    ],
    ag_brand_rn: [  # Brand campaign
        ("awad insurance", "EXACT"),
        ("awad agency", "EXACT"),
        ("awad insurance southgate", "EXACT"),
        ("awad insurance agency", "EXACT"),
        ("awad agency insurance", "PHRASE"),
        ("awad insurance michigan", "PHRASE"),
    ],
}

kw_ops = []
match_enum = client.enums.KeywordMatchTypeEnum
match_map = {"EXACT": match_enum.EXACT, "PHRASE": match_enum.PHRASE, "BROAD": match_enum.BROAD}

for ad_group_rn, kws in KEYWORDS.items():
    existing_kw_count = ad_group_keyword_count(ad_group_rn)
    if existing_kw_count >= len(kws):
        print(f"  Skipping {ad_group_rn} — already has {existing_kw_count} keywords", flush=True)
        continue
    for text, match_type in kws:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = ad_group_rn
        c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        c.keyword.text = text
        c.keyword.match_type = match_map[match_type]
        kw_ops.append(op)

if kw_ops:
    kw_resp = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=kw_ops
    )
    print(f"  Added {len(kw_resp.results)} keywords", flush=True)
else:
    print(f"  Keywords already in place on all ad groups", flush=True)

# ============================================================
# STEP 7: RSAs (Responsive Search Ads)
# ============================================================
print("\n=== Step 7: Create RSAs ===", flush=True)

RSAS = {
    ag_local_rn: {
        "final_url": "https://www.awadinsurance.com/auto-insurance-quote",
        "path1": "Auto-Insurance",
        "path2": "Quote",
        "headlines": [
            "Free Auto Insurance Quote",
            "Southgate Auto Insurance",
            "Save on Car Insurance Today",
            "Compare Auto Rates & Save",
            "Trusted Local Insurance",
            "Get a Quote in 2 Minutes",
            "Bundle Home & Auto - Save",
            "5-Star Rated Local Agent",
            "Downriver Auto Insurance",
            "Licensed Michigan Agent",
"Your Local Insurance Agent",
        ],
        "descriptions": [  # all <=90 chars
            "Free auto insurance quote from Awad Agency in Southgate. Independent local agent.",
            "Compare Michigan auto insurance rates from multiple carriers. Licensed local agent.",
            "Save on car insurance with Awad Agency. Bundle auto & home for extra savings.",
            "SR-22, teen drivers, multi-car discounts. Awad Agency covers it all. Free quotes.",
        ],
    },
    ag_mi_rn: {
        "final_url": "https://www.awadinsurance.com/auto-insurance-quote",
        "path1": "Auto-Insurance",
        "path2": "MI",
        "headlines": [
            "Michigan No-Fault Experts",
            "No-Fault Insurance Quote",
            "Southgate Auto Insurance",
            "SR-22 Insurance Available",
            "Trusted Local MI Agent",
            "Understand Your PIP Options",
            "Free Auto Insurance Quote",
            "Licensed MI No-Fault Agent",
            "Save on Michigan Auto Rates",
            "Teen Driver Coverage Here",
"Get a Quote in 2 Minutes",
        ],
        "descriptions": [  # all <=90 chars
            "Michigan no-fault auto experts. Free quote from Awad Agency in Southgate, MI.",
            "Navigate Michigan no-fault with a licensed local agent. Compare PIP options.",
            "SR-22, teen drivers, high-risk coverage. Awad Agency in Southgate handles it all.",
            "Independent local agent in Downriver MI. Multiple carriers, no-fault expertise.",
        ],
    },
    ag_brand_rn: {
        "final_url": "https://www.awadinsurance.com/",
        "path1": "Awad-Agency",
        "path2": "",
        "headlines": [
            "Awad Insurance Agency",
            "Your Local Insurance Agent",
            "Awad Agency Southgate MI",
            "Call Awad Insurance Today",
            "Free Insurance Quotes",
            "5-Star Rated Local Agency",
            "Licensed Michigan Agent",
            "Bundle & Save With Awad",
            "Serving Downriver MI",
"Auto Home Life Business",
            "Awad Agency - Free Quote",
        ],
        "descriptions": [  # all <=90 chars
            "Awad Insurance Agency: independent local agent in Southgate, MI. Free quote.",
            "Auto, home, life & commercial insurance. Licensed local agent in Downriver MI.",
            "5-star rated Southgate agency. Free quotes, multiple carriers, same-day coverage.",
            "Trusted local insurance agent in Southgate. Bundle home & auto to save.",
        ],
    },
}

rsa_ops = []
for ad_group_rn, rsa in RSAS.items():
    if ad_group_has_ads(ad_group_rn):
        print(f"  Skipping {ad_group_rn} — already has an ad", flush=True)
        continue
    op = client.get_type("AdGroupAdOperation")
    ad = op.create
    ad.ad_group = ad_group_rn
    ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

    ad.ad.final_urls.append(rsa["final_url"])
    if rsa["path1"]:
        ad.ad.responsive_search_ad.path1 = rsa["path1"]
    if rsa["path2"]:
        ad.ad.responsive_search_ad.path2 = rsa["path2"]

    for h in rsa["headlines"]:
        asset = client.get_type("AdTextAsset")
        asset.text = h
        ad.ad.responsive_search_ad.headlines.append(asset)
    for d in rsa["descriptions"]:
        asset = client.get_type("AdTextAsset")
        asset.text = d
        ad.ad.responsive_search_ad.descriptions.append(asset)

    rsa_ops.append(op)

if rsa_ops:
    try:
        rsa_resp = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=rsa_ops
        )
        print(f"  Created {len(rsa_resp.results)} RSAs", flush=True)
    except GoogleAdsException as e:
        print(f"  RSA creation failed: {e}", flush=True)
        raise
else:
    print(f"  All ad groups already have ads", flush=True)

# ============================================================
# DONE
# ============================================================
print("\n=== DONE ===", flush=True)
print(f"  Auto Insurance campaign: {auto_campaign_rn}", flush=True)
print(f"  Brand campaign:          {brand_campaign_rn}", flush=True)
print("\nBoth campaigns are in PAUSED status. Review in Google Ads UI, then enable.", flush=True)
