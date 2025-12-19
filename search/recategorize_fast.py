#!/usr/bin/env python3
"""
Fast recategorization using existing data + targeted API calls.
Adds checkpointing to prevent lost progress.

Tier Structure:
- Tier 1: G12D, CRC-specific
- Tier 2a: G12D, includes CRC
- Tier 2b: Multi-RAS, CRC-specific  
- Tier 2c: Multi-RAS, includes CRC
- Tier 3: CRC, no RAS
- Tier 4: Not eligible
"""

import pandas as pd
import requests
import re
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

SCRIPT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = SCRIPT_DIR / "output"
CHECKPOINT_FILE = OUTPUT_DIR / "recategorize_checkpoint.json"
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


def load_checkpoint() -> Dict:
    """Load checkpoint if exists."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {"analyzed": {}, "last_index": 0}


def save_checkpoint(data: Dict):
    """Save checkpoint."""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f)


def fetch_trial_details(nct_id: str, max_retries: int = 3) -> Optional[Dict]:
    """Fetch trial details with retry logic."""
    for attempt in range(max_retries):
        try:
            url = f"{BASE_URL}/{nct_id}"
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
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
            continue
    return None


def quick_cancer_check(title: str) -> Tuple[bool, bool, str]:
    """
    Quick cancer type check from title only.
    Returns: (has_crc, is_crc_specific, cancer_type)
    """
    title_upper = title.upper()
    
    # CRC indicators
    crc_terms = ["COLORECTAL", "COLON CANCER", "RECTAL CANCER", " CRC", "MCRC"]
    has_crc = any(term in title_upper for term in crc_terms)
    
    # Non-CRC indicators (definitive)
    non_crc_exclusive = [
        "NSCLC", "NON-SMALL CELL LUNG", "LUNG CANCER", "LUNG ADENOCARCINOMA",
        "PANCREATIC CANCER", "PANCREATIC DUCTAL", " PDAC",
        "HEPATOCELLULAR", "LIVER CANCER",
        "BREAST CANCER", "OVARIAN CANCER", "PROSTATE CANCER",
        "MELANOMA", "GLIOBLASTOMA", "LEUKEMIA", "LYMPHOMA",
        "BLADDER CANCER", "RENAL CELL", "KIDNEY CANCER"
    ]
    
    is_non_crc_only = any(term in title_upper for term in non_crc_exclusive) and not has_crc
    
    # Basket trial indicators
    basket_terms = ["SOLID TUMOR", "ADVANCED SOLID", "MULTIPLE TUMOR", "VARIOUS CANCER"]
    is_basket = any(term in title_upper for term in basket_terms)
    
    if is_non_crc_only:
        # Determine specific non-CRC type
        if "LUNG" in title_upper or "NSCLC" in title_upper:
            return False, False, "Lung"
        elif "PANCREA" in title_upper or "PDAC" in title_upper:
            return False, False, "Pancreatic"
        else:
            return False, False, "Other"
    
    if has_crc:
        is_specific = not is_basket
        return True, is_specific, "Colorectal"
    
    # Need API check
    return None, None, None


def quick_mutation_check(title: str) -> Tuple[bool, bool, bool, str]:
    """
    Quick mutation check from title only.
    Returns: (accepts_g12d, is_g12d_specific, is_other_only, mutation_type)
    """
    title_upper = title.upper()
    
    has_g12d = "G12D" in title_upper
    has_g12c = "G12C" in title_upper
    has_g12v = "G12V" in title_upper
    has_pan_ras = "PAN-RAS" in title_upper or "PAN RAS" in title_upper or "RAS(ON)" in title_upper
    has_kras = "KRAS" in title_upper
    
    if has_g12d:
        is_specific = not (has_g12c or has_g12v or has_pan_ras)
        return True, is_specific, False, "G12D"
    
    if has_g12c and not has_g12d:
        return False, False, True, "G12C"
    
    if has_g12v and not has_g12d:
        return False, False, True, "G12V"
    
    if has_pan_ras:
        return True, False, False, "Pan-RAS"
    
    if has_kras:
        # Might accept G12D, need to check eligibility
        return None, None, None, "KRAS"
    
    return False, False, False, "None"


def full_mutation_check(title: str, eligibility: str) -> Tuple[bool, bool, bool, str]:
    """Full mutation check using title + eligibility."""
    combined = (title + " " + eligibility).upper()
    
    has_g12d = "G12D" in combined
    has_g12c = "G12C" in combined
    has_g12v = "G12V" in combined
    has_g12r = "G12R" in combined
    has_pan_ras = any(p in combined for p in ["PAN-RAS", "PAN RAS", "RAS(ON)", "PANRAS"])
    
    # Check for multi-RAS patterns
    multi_ras_patterns = [
        r"G12[ACERV]",  # Other G12 mutations
        r"G13[CD]",     # G13 mutations
        r"MULTIPLE.*KRAS", r"ANY.*KRAS.*MUTATION",
    ]
    has_multi_ras = any(re.search(p, combined) for p in multi_ras_patterns) or has_pan_ras
    
    if has_g12d:
        is_specific = not (has_g12c or has_g12v or has_g12r or has_multi_ras)
        return True, is_specific, False, "G12D"
    
    if has_g12c and not has_g12d:
        return False, False, True, "G12C"
    
    if has_g12v and not has_g12d:
        return False, False, True, "G12V"
    
    if has_pan_ras or has_multi_ras:
        return True, False, False, "Pan-RAS"
    
    if "KRAS" in combined:
        return True, False, False, "KRAS"
    
    return False, False, False, "None"


def full_cancer_check(conditions: List[str]) -> Tuple[bool, bool, str]:
    """Full cancer check using conditions list."""
    if not conditions:
        return False, False, "Other"
    
    conditions_text = " ".join(conditions).upper()
    
    crc_terms = ["COLORECTAL", "COLON", "RECTAL", " CRC", "MCRC"]
    has_crc = any(term in conditions_text for term in crc_terms)
    
    other_cancer_terms = [
        "LUNG", "NSCLC", "PANCREA", "PDAC", "GASTRIC", "STOMACH",
        "SOLID TUMOR", "ADVANCED SOLID", "BILE DUCT", "CHOLANGIOCARCINOMA",
        "HEPATOCELLULAR", "LIVER", "OVARIAN", "BREAST", "MELANOMA",
        "PROSTATE", "BLADDER", "RENAL", "KIDNEY", "THYROID", "HEAD AND NECK",
        "ESOPHAGEAL", "GLIOMA", "BRAIN", "LEUKEMIA", "LYMPHOMA", "MYELOMA"
    ]
    has_other = any(term in conditions_text for term in other_cancer_terms)
    
    if has_crc:
        is_specific = not has_other
        return True, is_specific, "Colorectal"
    
    # Determine non-CRC type
    if "PANCREA" in conditions_text or "PDAC" in conditions_text:
        return False, False, "Pancreatic"
    elif "LUNG" in conditions_text or "NSCLC" in conditions_text:
        return False, False, "Lung"
    elif "SOLID TUMOR" in conditions_text:
        return False, False, "Solid Tumor"
    else:
        return False, False, "Other"


def assign_priority(accepts_g12d: bool, is_g12d_specific: bool, is_other_only: bool,
                   has_crc: bool, is_crc_specific: bool) -> Tuple[str, int]:
    """Assign priority tier."""
    
    # Tier 4: Not eligible
    if is_other_only:
        return ("4. Not eligible (wrong mutation)", 4)
    
    if not has_crc:
        return ("4. Not eligible (non-CRC)", 4)
    
    # Now: has_crc is True
    
    # Tier 1: G12D-specific + CRC-specific
    if is_g12d_specific and is_crc_specific:
        return ("1. G12D, CRC-specific", 1)
    
    # Tier 2a: G12D-specific + includes CRC (basket)
    if is_g12d_specific and not is_crc_specific:
        return ("2a. G12D, includes CRC", 2)
    
    # Tier 2b: Multi-RAS + CRC-specific
    if accepts_g12d and not is_g12d_specific and is_crc_specific:
        return ("2b. Multi-RAS, CRC-specific", 2)
    
    # Tier 2c: Multi-RAS + includes CRC (basket)
    if accepts_g12d and not is_g12d_specific and not is_crc_specific:
        return ("2c. Multi-RAS, includes CRC", 2)
    
    # Tier 3: CRC, no RAS
    if has_crc and not accepts_g12d:
        return ("3. CRC, no RAS", 3)
    
    return ("4. Not eligible", 4)


def recategorize():
    """Main recategorization with checkpointing."""
    print("=" * 70)
    print("  FAST RECATEGORIZATION WITH CHECKPOINTING")
    print("=" * 70)
    
    # Load existing results
    input_file = OUTPUT_DIR / "exhaustive_search_results.csv"
    df = pd.read_csv(input_file)
    print(f"\n  Loaded {len(df)} trials")
    
    # Load checkpoint
    checkpoint = load_checkpoint()
    analyzed = checkpoint.get("analyzed", {})
    start_idx = checkpoint.get("last_index", 0)
    
    print(f"  Checkpoint: {len(analyzed)} already analyzed, starting from index {start_idx}")
    
    # Get unique trials
    all_nct_ids = df['NCT Code'].unique().tolist()
    
    # Analyze each trial
    needs_api = []
    
    print("\n  Phase 1: Quick analysis using titles...")
    for i, nct_id in enumerate(all_nct_ids):
        if nct_id in analyzed:
            continue
            
        row = df[df['NCT Code'] == nct_id].iloc[0]
        title = row['Trial Name']
        
        # Quick mutation check
        accepts_g12d, is_g12d_specific, is_other_only, mutation_type = quick_mutation_check(title)
        
        # Quick cancer check
        has_crc, is_crc_specific, cancer_type = quick_cancer_check(title)
        
        # If quick checks are definitive, use them
        if is_other_only:  # G12C/G12V only - definitely Tier 4
            priority_label, priority_num = assign_priority(False, False, True, False, False)
            analyzed[nct_id] = {
                "accepts_g12d": False,
                "is_g12d_specific": False,
                "is_other_only": True,
                "has_crc": False,
                "is_crc_specific": False,
                "mutation_type": mutation_type,
                "cancer_type": cancer_type or "Other",
                "priority_label": priority_label,
                "priority_num": priority_num
            }
        elif has_crc is False and cancer_type is not None:  # Definitely non-CRC
            priority_label, priority_num = assign_priority(accepts_g12d or False, is_g12d_specific or False, False, False, False)
            analyzed[nct_id] = {
                "accepts_g12d": accepts_g12d or False,
                "is_g12d_specific": is_g12d_specific or False,
                "is_other_only": False,
                "has_crc": False,
                "is_crc_specific": False,
                "mutation_type": mutation_type,
                "cancer_type": cancer_type,
                "priority_label": priority_label,
                "priority_num": priority_num
            }
        elif accepts_g12d is not None and has_crc is not None:
            # Both checks gave results
            priority_label, priority_num = assign_priority(
                accepts_g12d, is_g12d_specific or False, False,
                has_crc, is_crc_specific or False
            )
            analyzed[nct_id] = {
                "accepts_g12d": accepts_g12d,
                "is_g12d_specific": is_g12d_specific or False,
                "is_other_only": False,
                "has_crc": has_crc,
                "is_crc_specific": is_crc_specific or False,
                "mutation_type": mutation_type,
                "cancer_type": cancer_type or "Other",
                "priority_label": priority_label,
                "priority_num": priority_num
            }
        else:
            # Need API check
            needs_api.append(nct_id)
    
    print(f"    Quick analysis complete: {len(analyzed)} definitive, {len(needs_api)} need API")
    
    # Save checkpoint after quick analysis
    save_checkpoint({"analyzed": analyzed, "last_index": 0})
    
    # Phase 2: API calls for ambiguous trials
    if needs_api:
        print(f"\n  Phase 2: Fetching API data for {len(needs_api)} trials...")
        
        for i, nct_id in enumerate(needs_api):
            if i % 50 == 0:
                print(f"    [{i}/{len(needs_api)}] - {nct_id}")
                save_checkpoint({"analyzed": analyzed, "last_index": i})
            
            details = fetch_trial_details(nct_id)
            if details is None:
                # Default to title-only analysis
                row = df[df['NCT Code'] == nct_id].iloc[0]
                title = row['Trial Name']
                details = {"title": title, "eligibility": "", "conditions": []}
            
            # Full mutation check
            accepts_g12d, is_g12d_specific, is_other_only, mutation_type = full_mutation_check(
                details["title"], details["eligibility"]
            )
            
            # Full cancer check
            has_crc, is_crc_specific, cancer_type = full_cancer_check(details["conditions"])
            
            # If conditions empty, fall back to title check
            if not details["conditions"]:
                _, _, cancer_type_title = quick_cancer_check(details["title"])
                if cancer_type_title:
                    cancer_type = cancer_type_title
            
            priority_label, priority_num = assign_priority(
                accepts_g12d, is_g12d_specific, is_other_only,
                has_crc, is_crc_specific
            )
            
            analyzed[nct_id] = {
                "accepts_g12d": accepts_g12d,
                "is_g12d_specific": is_g12d_specific,
                "is_other_only": is_other_only,
                "has_crc": has_crc,
                "is_crc_specific": is_crc_specific,
                "mutation_type": mutation_type,
                "cancer_type": cancer_type,
                "priority_label": priority_label,
                "priority_num": priority_num
            }
            
            time.sleep(0.1)
        
        save_checkpoint({"analyzed": analyzed, "last_index": len(needs_api)})
    
    # Apply to dataframe
    print("\n  Phase 3: Applying categorization...")
    
    new_priorities = []
    new_priority_nums = []
    new_mutation_types = []
    new_cancer_types = []
    
    for _, row in df.iterrows():
        nct_id = row['NCT Code']
        analysis = analyzed.get(nct_id, {})
        
        if analysis:
            new_priorities.append(analysis["priority_label"])
            new_priority_nums.append(analysis["priority_num"])
            new_mutation_types.append(analysis["mutation_type"])
            new_cancer_types.append(analysis["cancer_type"])
        else:
            new_priorities.append("4. Not eligible")
            new_priority_nums.append(4)
            new_mutation_types.append(row.get('Mutation Type', 'None'))
            new_cancer_types.append(row.get('Cancer Type', 'Other'))
    
    df['Priority'] = new_priorities
    df['Priority Num'] = new_priority_nums
    df['Mutation Type'] = new_mutation_types
    df['Cancer Type'] = new_cancer_types
    
    # Filter and save
    df_filtered = df[df['Priority Num'] < 4].copy()
    df_filtered = df_filtered.drop(columns=['Priority Num'])
    df_filtered = df_filtered.sort_values(['Priority', 'Already In List', 'NCT Code'])
    
    output_file = OUTPUT_DIR / "exhaustive_search_filtered.csv"
    df_filtered.to_csv(output_file, index=False)
    
    df_full = df.drop(columns=['Priority Num'])
    df_full.to_csv(OUTPUT_DIR / "exhaustive_search_results_v2.csv", index=False)
    
    # Summary
    print("\n" + "=" * 70)
    print("  FINAL RESULTS")
    print("=" * 70)
    
    print(f"\n  Total trials: {len(df)}")
    print(f"  Eligible (Tiers 1-3): {len(df_filtered)}")
    print(f"  Not eligible (Tier 4): {len(df) - len(df_filtered)}")
    
    print("\n  By Priority Tier:")
    for p in sorted(df_filtered['Priority'].unique()):
        count = len(df_filtered[df_filtered['Priority'] == p])
        new_count = len(df_filtered[(df_filtered['Priority'] == p) & (~df_filtered['Already In List'])])
        print(f"    {p}: {count} total ({new_count} new)")
    
    print(f"\n  Saved:")
    print(f"    - {output_file.name} (Tiers 1-3)")
    print(f"    - exhaustive_search_results_v2.csv (all)")
    
    # Clean up checkpoint
    CHECKPOINT_FILE.unlink(missing_ok=True)
    
    return df_filtered


if __name__ == "__main__":
    df = recategorize()

