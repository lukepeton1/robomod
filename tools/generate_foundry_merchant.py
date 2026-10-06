#!/usr/bin/env python3
"""Generate production Foundry merchant CDO policy from transfer_policy.json."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "Source/grafting/transfer_policy.json"
OUTPUT = ROOT / "Source/patches/foundry_merchant.json"

def main():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    rows = [
        item["row"]
        for item in policy["transferable"]
        if item["kind"] == "affix"
    ]
    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-merchant",
        "target": "Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix",
        "status": "production",
        "purpose": (
            "Seed the vanilla Perfumer/affix merchant with curated ordinary transferable "
            "affixes. Vanilla initialization still appends the game's enchanted rows, and "
            "the existing Power Cell/UI/server/multicast transaction remains untouched."
        ),
        "operations": [{
            "op": "set_name_array",
            "cdo": "Default__BP_Merchant_UpgradeAffix_C",
            "field": "AffixRows",
            "values": rows,
        }],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(rows)} ordinary affixes")

if __name__ == "__main__":
    main()
