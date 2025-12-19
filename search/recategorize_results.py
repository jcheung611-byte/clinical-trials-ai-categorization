#!/usr/bin/env python3
"""
Recategorize search results with improved logic:
1. Distinguish between colorectal-primary trials vs basket trials
2. Filter out Tier 4 (non-colon/non-RAS) 

Tier 1: G12D + trial where colorectal is the PRIMARY cancer type
Tier 2: G12D alone OR G12D + basket trial (colorectal is one of many) OR RAS + colorectal
Tier 3: Colorectal but no RAS mutation
"""

import pandas as pd
import requests
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = SCRIPT_DIR / "output"
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


def fetch_trial_details_for_categorization(nct_id: str) -> Dict:
    """Fetch conditions and eligibility for categorization."""
    url = f"{BASE_URL}/{nct_id}"
    try:
        response = requests.get(url, params={"format": "json"}, timeout=30)
        response.raise_for_status()
        data = response.json()
        protocol = data.get("protocolSection", {})
        cond_mod = protocol.get("conditionsModule", {})
        id_mod = protocol.get("identificationModule", {})
        elig_mod = protocol.get("eligibilityModule", {})
        
        return {
            "conditions": cond_mod.get("conditions", []),
            "title": id_mod.get("briefTitle", ""),
            "eligibility": elig_mod.get("eligibilityCriteria", "")
        }
    except:
        return {"conditions": [], "title": "", "eligibility": ""}


def is_g12d_specific(title: str, eligibility: str) -> Tuple[bool, bool]:
    """
    Determine if trial is G12D-specific or multi-RAS.
    
    Returns:
        (has_g12d, is_g12d_specific)
        
    Logic:
    - G12D-specific: Only mentions G12D, not other specific mutations
    - Multi-RAS: Mentions G12D AND other mutations (G12C, G12V, pan-RAS, etc.)
    """
    combined = (title + " " + eligibility).upper()
    
    has_g12d = "G12D" in combined
    
    if not has_g12d:
        return False, False
    
    # Check for other specific mutations (NOT including G12D itself)
    other_mutations = [
        r"G12C", r"G12V", r"G12R", r"G12A", r"G12S",
        r"G13D", r"G13C",
        r"PAN.?RAS", r"RAS.?ON",  # Pan-RAS indicators
        r"MULTIPLE.*KRAS", r"ANY.*KRAS.*MUTATION",
    ]
    
    has_other = any(re.search(pattern, combined) for pattern in other_mutations)
    
    # If has other mutations mentioned, it's multi-RAS
    if has_other:
        return True, False
    
    # Otherwise it's G12D-specific
    return True, True


def is_colorectal_primary(conditions: List[str]) -> Tuple[bool, bool]:
    """
    Determine if colorectal is the primary condition.
    
    Returns:
        (is_colorectal_mentioned, is_colorectal_primary)
        
    Logic:
    - Primary: Only colorectal/colon/rectal/CRC conditions listed
    - Not primary (basket): Colorectal + other cancer types (lung, pancreatic, solid tumor, etc.)
    """
    if not conditions:
        return False, False
    
    conditions_upper = [c.upper() for c in conditions]
    conditions_text = " ".join(conditions_upper)
    
    # Check if colorectal mentioned at all
    colorectal_terms = ["COLORECTAL", "COLON", "RECTAL", "CRC", "MCRC"]
    has_colorectal = any(term in conditions_text for term in colorectal_terms)
    
    if not has_colorectal:
        return False, False
    
    # Check if it's a basket trial (has non-colorectal cancers too)
    other_cancer_terms = [
        "LUNG", "NSCLC", "PANCREA", "PDAC", "GASTRIC", "STOMACH",
        "SOLID TUMOR", "ADVANCED SOLID", "BILE DUCT", "CHOLANGIOCARCINOMA",
        "HEPATOCELLULAR", "LIVER", "OVARIAN", "BREAST", "MELANOMA",
        "PROSTATE", "BLADDER", "RENAL", "KIDNEY", "THYROID", "HEAD AND NECK",
        "ESOPHAGEAL", "GLIOMA", "BRAIN", "LEUKEMIA", "LYMPHOMA", "MYELOMA",
        "SARCOMA", "ENDOMETRIAL", "UTERINE", "CERVICAL"
    ]
    
    has_other_cancer = any(term in conditions_text for term in other_cancer_terms)
    
    # If only colorectal-related conditions → primary
    # If colorectal + other cancers → basket trial (not primary)
    is_primary = has_colorectal and not has_other_cancer
    
    return has_colorectal, is_primary


def assign_priority_v2(mutation_type: str, cancer_type: str, 
                       is_crc_primary: bool, is_mutation_specific: bool) -> Tuple[int, str]:
    """
    Assign priority tier with improved logic.
    
    Tier 1: G12D-SPECIFIC + colorectal PRIMARY (not basket, not multi-RAS)
    Tier 2: G12D + basket trial OR G12D multi-RAS OR G12D alone OR other RAS + colorectal
    Tier 3: Colorectal but no RAS
    Tier 4: Non-colon/non-RAS (will be filtered out)
    """
    is_g12d = mutation_type == "G12D"
    is_ras = mutation_type in ["G12D", "G12C", "G12V", "G12R", "G12", "G13D", "G13", 
                               "KRAS", "NRAS", "HRAS", "RAS", "Pan-RAS", "RAS(ON)"]
    is_colorectal = cancer_type in ["mCRC", "Colorectal", "Colon", "Rectal", "CRC"]
    
    # Tier 1: G12D-SPECIFIC + colorectal PRIMARY
    if is_g12d and is_colorectal and is_crc_primary and is_mutation_specific:
        return (1, "1. G12D-specific + Colon-primary")
    
    # Tier 2: Various G12D/RAS combinations
    if is_g12d:
        if is_colorectal:
            if not is_mutation_specific:
                return (2, "2. Multi-RAS + Colon")
            elif not is_crc_primary:
                return (2, "2. G12D + Basket trial")
        return (2, "2. G12D general")
    
    if is_ras and is_colorectal:
        return (2, "2. RAS + Colon")
    
    # Tier 3: Colorectal but no RAS
    if is_colorectal and not is_ras:
        return (3, "3. Colon, no RAS")
    
    # Tier 4: Everything else
    return (4, "4. Non-colon/non-RAS")


def recategorize():
    """Recategorize existing results with new logic."""
    print("=" * 70)
    print("  RECATEGORIZING SEARCH RESULTS")
    print("  - Distinguishing colorectal-primary vs basket trials")
    print("  - Distinguishing G12D-specific vs multi-RAS trials")
    print("=" * 70)
    
    # Load existing results
    input_file = OUTPUT_DIR / "exhaustive_search_results.csv"
    df = pd.read_csv(input_file)
    print(f"\n  Loaded {len(df)} trials from {input_file.name}")
    
    # Get unique NCT codes that need re-evaluation
    # Focus on trials that might be Tier 1 or 2 (have G12D or colorectal)
    needs_check = df[
        (df['Mutation Type'] == 'G12D') | 
        (df['Cancer Type'].isin(['mCRC', 'Colorectal', 'Colon', 'Rectal', 'CRC']))
    ]['NCT Code'].unique()
    
    print(f"  Need to check {len(needs_check)} trials")
    
    # Fetch details and determine categorization
    nct_to_crc_primary = {}
    nct_to_g12d_specific = {}
    
    print("\n  Fetching trial details...")
    for i, nct_id in enumerate(needs_check, 1):
        if i % 50 == 0:
            print(f"    [{i}/{len(needs_check)}]")
        
        details = fetch_trial_details_for_categorization(nct_id)
        
        # Check colorectal
        has_crc, crc_primary = is_colorectal_primary(details["conditions"])
        nct_to_crc_primary[nct_id] = crc_primary
        
        # Check G12D specificity
        has_g12d, g12d_specific = is_g12d_specific(details["title"], details["eligibility"])
        nct_to_g12d_specific[nct_id] = g12d_specific
        
        time.sleep(0.1)
    
    # Stats
    crc_primary_count = sum(nct_to_crc_primary.values())
    g12d_specific_count = sum(nct_to_g12d_specific.values())
    
    print(f"\n  Cancer type analysis:")
    print(f"    Colorectal-primary: {crc_primary_count}")
    print(f"    Basket trials: {len(nct_to_crc_primary) - crc_primary_count}")
    
    print(f"\n  Mutation analysis:")
    print(f"    G12D-specific: {g12d_specific_count}")
    print(f"    Multi-RAS (includes G12D): {len([v for v in nct_to_g12d_specific.values() if v == False])}")
    
    # Recategorize
    print("\n  Recategorizing...")
    new_priorities = []
    new_priority_nums = []
    
    for _, row in df.iterrows():
        nct_id = row['NCT Code']
        mutation = row['Mutation Type']
        cancer = row['Cancer Type']
        
        crc_primary = nct_to_crc_primary.get(nct_id, False)
        g12d_specific = nct_to_g12d_specific.get(nct_id, True)  # Default to specific if not checked
        
        priority_num, priority_desc = assign_priority_v2(mutation, cancer, crc_primary, g12d_specific)
        
        new_priorities.append(priority_desc)
        new_priority_nums.append(priority_num)
    
    df['Priority'] = new_priorities
    df['Priority Num'] = new_priority_nums
    
    # Filter out Tier 4
    df_filtered = df[df['Priority Num'] < 4].copy()
    df_filtered = df_filtered.drop(columns=['Priority Num'])
    df_filtered = df_filtered.sort_values(['Priority', 'Already In List', 'NCT Code'])
    
    # Save filtered results
    output_file = OUTPUT_DIR / "exhaustive_search_filtered.csv"
    df_filtered.to_csv(output_file, index=False)
    
    # Also save full results with new categorization
    df_full = df.drop(columns=['Priority Num'])
    df_full.to_csv(OUTPUT_DIR / "exhaustive_search_results_v2.csv", index=False)
    
    # Summary
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    
    print(f"\n  Total trials (all tiers): {len(df)}")
    print(f"  Filtered (Tiers 1-3 only): {len(df_filtered)}")
    print(f"  Removed (Tier 4): {len(df) - len(df_filtered)}")
    
    print("\n  By Priority (filtered):")
    for p in sorted(df_filtered['Priority'].unique()):
        count = len(df_filtered[df_filtered['Priority'] == p])
        new_count = len(df_filtered[(df_filtered['Priority'] == p) & (~df_filtered['Already In List'])])
        print(f"    {p}: {count} total ({new_count} new)")
    
    print(f"\n  Saved to: {output_file}")
    print(f"  Full results (all tiers): exhaustive_search_results_v2.csv")
    
    return df_filtered


if __name__ == "__main__":
    df = recategorize()

