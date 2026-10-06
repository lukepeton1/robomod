#!/usr/bin/env python3
"""Generate the native perfumer graft-transaction probe from transfer_policy.json."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "Source/grafting/transfer_policy.json"
OUTPUT = ROOT / "Source/probes/graft_merchant_probe.json"

def main():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    values = [
        row["row"]
        for row in policy["transferable"]
        if row["kind"] == "affix"
    ]
    payload = {
        "schema_version": 1,
        "name": "graft-merchant-native-transaction-probe",
        "target": "Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix",
        "status": "diagnostic_probe",
        "purpose": (
            "Seed the perfumer AffixRows CDO with ordinary transferable affixes while "
            "leaving native price, UI, AddEnchantedAffix, server and multicast paths untouched."
        ),
        "operations": [{
            "op": "set_name_array",
            "cdo": "Default__BP_Merchant_UpgradeAffix_C",
            "field": "AffixRows",
            "values": values,
        }],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(values)} ordinary affix rows")

if __name__ == "__main__":
    main()
