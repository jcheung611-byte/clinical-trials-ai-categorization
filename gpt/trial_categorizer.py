#!/usr/bin/env python3
"""
GPT-powered clinical trial categorization.
Uses GPT-4o-mini for accurate mutation and cancer type classification.
"""

import os
import sys
import json
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
from dotenv import load_dotenv

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# Load environment variables from .env file
load_dotenv()

SCRIPT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = SCRIPT_DIR / "output"
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# Checkpoint files
CHECKPOINT_FILE = OUTPUT_DIR / "gpt_categorization_checkpoint.json"
PARTIAL_OUTPUT = OUTPUT_DIR / "gpt_categorization_partial.csv"


# =============================================================================
# PROMPTS
# =============================================================================

CATEGORIZATION_PROMPT = """You are analyzing a clinical trial for a patient with:
- KRAS G12D mutation
- Colorectal adenocarcinoma (colon/rectal cancer)

TRIAL DATA:
-----------
NCT ID: {nct_id}
Title: {title}
Official Title: {official_title}
Listed Conditions: {conditions}
Interventions: {interventions}

Brief Summary:
{brief_summary}

ELIGIBILITY CRITERIA (READ CAREFULLY):
{eligibility_criteria}
-----------

STEP 1 - Does this trial treat COLORECTAL ADENOCARCINOMA?
- Crohn's disease, colitis, polyps, neuroendocrine tumors, sarcoma = NOT colorectal adenocarcinoma
- Must be colorectal CANCER (carcinoma/adenocarcinoma)

STEP 2 - MUTATION REQUIREMENT (BE STRICT):
Search eligibility text for EXPLICIT mutation requirements.
- "G12D-only" = eligibility EXPLICITLY requires "G12D" or "KRAS G12D" and ONLY G12D
- "Multi-KRAS" = accepts G12D among other KRAS mutations (G12C, G12V, G12R, etc.)
- "RAS-wild-type" = requires NO RAS mutation (patient cannot enroll)
- "No-mutation-required" = no explicit mutation requirement in eligibility

CRITICAL: Most CRC trials have NO mutation requirement. Be strict - only "G12D-only" if explicitly required.

STEP 3 - CANCER SCOPE:
- "CRC-only" = only colorectal/colon/rectal adenocarcinoma
- "GI-focused" = only GI cancers (CRC + pancreas + gastric)
- "Solid-tumors" = broad cancers OR includes lung/breast/ovarian

STEP 4 - PRIORITY TIER:
- Tier 1: EXPLICIT G12D-only requirement + CRC-only (rare)
- Tier 1.5: EXPLICIT G12D-only + GI-focused
- Tier 2: Multi-KRAS (accepts G12D) OR G12D + solid tumors
- Tier 3: CRC accepted + NO mutation requirement (common)
- Tier 4: NOT colorectal adenocarcinoma OR requires wild-type/G12C-only

Respond with ONLY valid JSON:
{{
    "mutation": {{
        "trial_accepts_g12d": true/false,
        "has_mutation_requirement": true/false,
        "mutation_requirement": "G12D-only/Multi-KRAS/Any-RAS/No-mutation-required/RAS-wild-type",
        "accepted_mutations": ["list"],
        "mutation_notes": "brief"
    }},
    "cancer": {{
        "trial_accepts_crc": true/false,
        "cancer_scope": "CRC-only/GI-focused/Solid-tumors/Other-specific",
        "includes_non_gi": true/false,
        "accepted_cancers": ["list"],
        "cancer_notes": "brief"
    }},
    "trial_info": {{
        "phase": "Phase X",
        "line_of_therapy": "1L/2L/3L+/any/not specified",
        "drug_name": "drug name",
        "drug_mechanism": "brief"
    }},
    "priority": {{
        "tier": 1/1.5/2/3/4,
        "tier_label": "description",
        "reasoning": "explain tier"
    }}
}}
"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_phase(phases: List[str]) -> str:
    """Format phase list from API to readable string."""
    if not phases:
        return "Not Applicable"
    
    # Convert ["PHASE1", "PHASE2"] -> "Phase 1/2"
    phase_nums = []
    for p in phases:
        p_upper = p.upper()
        if "PHASE1" in p_upper or "PHASE 1" in p_upper:
            phase_nums.append("1")
        elif "PHASE2" in p_upper or "PHASE 2" in p_upper:
            phase_nums.append("2")
        elif "PHASE3" in p_upper or "PHASE 3" in p_upper:
            phase_nums.append("3")
        elif "PHASE4" in p_upper or "PHASE 4" in p_upper:
            phase_nums.append("4")
        elif "EARLY" in p_upper:
            phase_nums.append("Early Phase 1")
        elif "NA" in p_upper or "NOT_APPLICABLE" in p_upper:
            return "Not Applicable"
    
    if not phase_nums:
        return "Not Applicable"
    
    # Remove duplicates and sort
    phase_nums = sorted(set(phase_nums), key=lambda x: x if x.isdigit() else "0")
    
    if len(phase_nums) == 1:
        if phase_nums[0].isdigit():
            return f"Phase {phase_nums[0]}"
        return phase_nums[0]
    else:
        return f"Phase {'/'.join(phase_nums)}"


# =============================================================================
# API FUNCTIONS
# =============================================================================

def get_openai_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set.\n"
            "Set it with: export OPENAI_API_KEY='your-key-here'"
        )
    return OpenAI(api_key=api_key)


def fetch_trial_details(nct_id: str, max_retries: int = 3) -> Optional[Dict]:
    """Fetch full trial data from ClinicalTrials.gov API."""
    url = f"{BASE_URL}/{nct_id}"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params={"format": "json"}, timeout=30)
            response.raise_for_status()
            data = response.json()
            protocol = data.get("protocolSection", {})
            
            id_mod = protocol.get("identificationModule", {})
            desc_mod = protocol.get("descriptionModule", {})
            cond_mod = protocol.get("conditionsModule", {})
            elig_mod = protocol.get("eligibilityModule", {})
            arms_mod = protocol.get("armsInterventionsModule", {})
            design_mod = protocol.get("designModule", {})
            
            interventions = arms_mod.get("interventions", [])
            phases = design_mod.get("phases", [])
            
            return {
                "nct_id": id_mod.get("nctId", ""),
                "title": id_mod.get("briefTitle", ""),
                "official_title": id_mod.get("officialTitle", ""),
                "brief_summary": desc_mod.get("briefSummary", ""),
                "conditions": cond_mod.get("conditions", []),
                "eligibility_criteria": elig_mod.get("eligibilityCriteria", ""),
                "interventions": [i.get("name", "") for i in interventions],
                "phases": phases,  # e.g., ["PHASE1", "PHASE2"]
            }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
            continue
    
    return None


def categorize_with_gpt(
    client: OpenAI,
    trial_data: Dict,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Optional[Dict]:
    """Use GPT to categorize a clinical trial."""
    
    prompt = CATEGORIZATION_PROMPT.format(
        nct_id=trial_data["nct_id"],
        title=trial_data["title"],
        official_title=trial_data.get("official_title", "")[:500],
        conditions=", ".join(trial_data["conditions"]),
        interventions=", ".join(trial_data["interventions"]),
        brief_summary=trial_data.get("brief_summary", "")[:1500],
        eligibility_criteria=trial_data.get("eligibility_criteria", "")[:3000],
    )
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert clinical trial analyst. Always respond with valid JSON only, no markdown."
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1000,
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                return {"error": str(e)}
    
    return None


# =============================================================================
# CHECKPOINT MANAGEMENT
# =============================================================================

def load_checkpoint() -> Tuple[set, List[Dict]]:
    """Load checkpoint if exists."""
    processed_ncts = set()
    results = []
    
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            data = json.load(f)
            processed_ncts = set(data.get("processed_ncts", []))
    
    if PARTIAL_OUTPUT.exists():
        df = pd.read_csv(PARTIAL_OUTPUT)
        results = df.to_dict('records')
    
    return processed_ncts, results


def save_checkpoint(processed_ncts: set, results: List[Dict]):
    """Save checkpoint."""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({"processed_ncts": list(processed_ncts)}, f)
    
    if results:
        df = pd.DataFrame(results)
        df.to_csv(PARTIAL_OUTPUT, index=False)


# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_trials(
    input_file: Path,
    output_file: Path,
    nct_column: str = "NCT Code",
    model: str = "gpt-4o-mini",
    limit: Optional[int] = None,
    resume: bool = True
):
    """Process trials from input file and add GPT categorization."""
    
    print("=" * 70)
    print("  GPT-POWERED TRIAL CATEGORIZATION")
    print(f"  Model: {model}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Load input data
    print(f"\n  Loading input from: {input_file}")
    df = pd.read_csv(input_file)
    print(f"  Total rows: {len(df)}")
    
    # Get unique NCT codes
    nct_codes = df[nct_column].unique()
    print(f"  Unique trials: {len(nct_codes)}")
    
    if limit:
        nct_codes = nct_codes[:limit]
        print(f"  Limited to: {limit} trials")
    
    # Load checkpoint
    processed_ncts, results = (set(), []) if not resume else load_checkpoint()
    if processed_ncts:
        print(f"  Resuming from checkpoint: {len(processed_ncts)} already processed")
    
    # Filter to unprocessed
    to_process = [nct for nct in nct_codes if nct not in processed_ncts]
    print(f"  To process: {len(to_process)}")
    
    # Initialize OpenAI client
    print("\n  Initializing OpenAI client...")
    client = get_openai_client()
    print("  ✓ Client ready")
    
    # Process trials
    print("\n  Processing trials...")
    errors = []
    
    for i, nct_id in enumerate(to_process, 1):
        if i % 10 == 0 or i == 1:
            print(f"    [{i}/{len(to_process)}] {nct_id}")
        
        # Fetch trial details
        trial_data = fetch_trial_details(nct_id)
        if not trial_data:
            errors.append(nct_id)
            continue
        
        # Categorize with GPT
        gpt_result = categorize_with_gpt(client, trial_data, model)
        
        if gpt_result and "error" not in gpt_result:
            # Format phase from API (e.g., ["PHASE1", "PHASE2"] -> "Phase 1/2")
            api_phases = trial_data.get("phases", [])
            phase_str = format_phase(api_phases)
            
            result = {
                # Core identifiers
                "NCT Code": nct_id,
                "Trial Name": trial_data["title"],
                "Phase": phase_str,
                # Priority
                "Priority Tier": gpt_result.get("priority", {}).get("tier", 4),
                "Priority Label": gpt_result.get("priority", {}).get("tier_label", ""),
                # Mutation
                "Accepts G12D": gpt_result.get("mutation", {}).get("trial_accepts_g12d", False),
                "Has Mutation Req": gpt_result.get("mutation", {}).get("has_mutation_requirement", False),
                "Mutation Type": gpt_result.get("mutation", {}).get("mutation_requirement", ""),
                # Cancer
                "Accepts CRC": gpt_result.get("cancer", {}).get("trial_accepts_crc", False),
                "Cancer Scope": gpt_result.get("cancer", {}).get("cancer_scope", ""),
                "Includes Non-GI": gpt_result.get("cancer", {}).get("includes_non_gi", False),
                # Details
                "Accepted Mutations": ", ".join(gpt_result.get("mutation", {}).get("accepted_mutations", [])),
                "Accepted Cancers": ", ".join(gpt_result.get("cancer", {}).get("accepted_cancers", [])),
                "Line of Therapy": gpt_result.get("trial_info", {}).get("line_of_therapy", ""),
                "Drug Name": gpt_result.get("trial_info", {}).get("drug_name", ""),
                "Drug Mechanism": gpt_result.get("trial_info", {}).get("drug_mechanism", ""),
                "Priority Reasoning": gpt_result.get("priority", {}).get("reasoning", ""),
                "Mutation Notes": gpt_result.get("mutation", {}).get("mutation_notes", ""),
                "Cancer Notes": gpt_result.get("cancer", {}).get("cancer_notes", ""),
            }
            results.append(result)
        else:
            errors.append(nct_id)
        
        processed_ncts.add(nct_id)
        
        # Checkpoint every 50 trials
        if i % 50 == 0:
            save_checkpoint(processed_ncts, results)
            print(f"    ✓ Checkpoint saved ({len(results)} results)")
        
        # Rate limiting
        time.sleep(0.2)
    
    # Final save
    print("\n  Saving final results...")
    df_results = pd.DataFrame(results)
    df_results.to_csv(output_file, index=False)
    
    # Summary
    print("\n" + "=" * 70)
    print("  COMPLETE!")
    print("=" * 70)
    print(f"\n  Trials processed: {len(results)}")
    print(f"  Errors: {len(errors)}")
    
    if len(results) > 0:
        print(f"\n  By Priority Tier:")
        for tier in sorted(df_results["Priority Tier"].unique()):
            count = len(df_results[df_results["Priority Tier"] == tier])
            print(f"    Tier {tier}: {count} trials")
        
        print(f"\n  Mutation Analysis:")
        print(f"    Accepts G12D: {df_results['Accepts G12D'].sum()}")
        if 'Mutation Type' in df_results.columns:
            for mt in df_results['Mutation Type'].value_counts().head(5).items():
                print(f"    {mt[0]}: {mt[1]}")
        
        print(f"\n  Cancer Scope:")
        print(f"    Accepts CRC: {df_results['Accepts CRC'].sum()}")
        if 'Cancer Scope' in df_results.columns:
            for cs in df_results['Cancer Scope'].value_counts().head(5).items():
                print(f"    {cs[0]}: {cs[1]}")
    
    print(f"\n  Saved to: {output_file}")
    
    if errors:
        print(f"\n  Errors (first 10):")
        for e in errors[:10]:
            print(f"    {e}")
    
    return df_results


if __name__ == "__main__":
    # Default: process net new trials
    input_file = OUTPUT_DIR / "net_new_trials_1216_center_level.csv"
    output_file = OUTPUT_DIR / "net_new_trials_gpt_categorized.csv"
    
    # Run with limit for testing
    process_trials(
        input_file=input_file,
        output_file=output_file,
        limit=None,  # Set to small number for testing
        model="gpt-4o-mini"
    )

