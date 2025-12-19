#!/usr/bin/env python3
"""
GPT-powered institution name normalization.
Uses GPT to intelligently group similar institution names.
"""

import os
import sys
import json
import time
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

# Checkpoint files
CHECKPOINT_FILE = OUTPUT_DIR / "gpt_institution_checkpoint.json"


# =============================================================================
# PROMPTS
# =============================================================================

BATCH_NORMALIZATION_PROMPT = """You are an expert in healthcare institution naming conventions.

Given a list of clinical trial site institution names, group them into canonical institution names.

IMPORTANT RULES:
1. Same institution with slight name variations should be grouped (e.g., "Mayo Clinic Hospital" and "Mayo Clinic Cancer Center" → "Mayo Clinic")
2. Same institution in DIFFERENT CITIES should be grouped together (e.g., Mayo Clinic in Phoenix, Jacksonville, Rochester are all "Mayo Clinic")
3. DIFFERENT institutions with similar names should stay SEPARATE:
   - "Banner MD Anderson Cancer Center" (Gilbert, AZ) is DIFFERENT from "MD Anderson Cancer Center" (Houston, TX)
   - "Sibley Memorial Hospital" is DIFFERENT from "Memorial Sloan Kettering"
4. Research networks should be unified:
   - "START San Antonio", "START Midwest", "START Dublin" → "START"
   - "NEXT Oncology Dallas", "NEXT Virginia" → "NEXT Oncology"
5. Academic medical centers should be grouped with their cancer centers:
   - "Dana-Farber Cancer Institute", "Dana Farber/Harvard Cancer Center" → "Dana-Farber Cancer Institute"
6. Generic/placeholder names like "Research Site", "Local Institution", "Site 001" should keep their original names

INSTITUTION LIST (with locations for context):
{institution_list}

Respond with ONLY valid JSON in this format:
{{
    "groupings": [
        {{
            "canonical_name": "Dana-Farber Cancer Institute",
            "original_names": ["Dana Farber Cancer Institute", "Dana-Farber Cancer Institute (Boston)", "Dana Farber/Harvard Cancer Center"],
            "reasoning": "All are the same Boston cancer center"
        }},
        ...
    ]
}}

Only include institutions that need grouping. Institutions that are unique and don't match others can be omitted.
"""

SINGLE_INSTITUTION_PROMPT = """You are an expert in healthcare institution naming conventions.

Given this institution name and location, provide the best canonical name:

Institution: {institution}
City: {city}
State: {state}
Country: {country}

Consider:
1. Is this a well-known cancer center? Use its common name.
2. Is this part of a larger health system? Use the system name.
3. Is this a research network site? Use the network name.
4. Remove site numbers like "(Site 1007)" or location qualifiers like "(Boston)"
5. Standardize formatting (e.g., "MD Anderson" not "M.D. Anderson")

Respond with ONLY valid JSON:
{{
    "canonical_name": "The canonical institution name",
    "institution_type": "cancer_center/academic_medical_center/research_network/hospital/other",
    "parent_system": "Parent health system if applicable, else null",
    "reasoning": "Brief explanation"
}}
"""


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


def normalize_batch_with_gpt(
    client: OpenAI,
    institutions: List[Dict],
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Optional[Dict]:
    """Use GPT to normalize a batch of institution names."""
    
    # Format institution list
    institution_list = "\n".join([
        f"- {inst['institution']} | {inst.get('city', '')} | {inst.get('state', '')} | {inst.get('country', '')}"
        for inst in institutions
    ])
    
    prompt = BATCH_NORMALIZATION_PROMPT.format(institution_list=institution_list)
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert healthcare institution analyst. Always respond with valid JSON only."
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=4000,
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                return {"error": str(e)}
    
    return None


def normalize_single_with_gpt(
    client: OpenAI,
    institution: str,
    city: str,
    state: str,
    country: str,
    model: str = "gpt-4o-mini"
) -> Optional[Dict]:
    """Use GPT to normalize a single institution name."""
    
    prompt = SINGLE_INSTITUTION_PROMPT.format(
        institution=institution,
        city=city,
        state=state,
        country=country
    )
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert healthcare institution analyst. Always respond with valid JSON only."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500,
        )
        
        return json.loads(response.choices[0].message.content)
        
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def load_checkpoint() -> Dict:
    """Load checkpoint if exists."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {"processed_batches": 0, "name_mappings": {}}


def save_checkpoint(data: Dict):
    """Save checkpoint."""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def normalize_institutions(
    input_file: Path,
    output_file: Path,
    institution_column: str = "Institution",
    batch_size: int = 50,
    model: str = "gpt-4o-mini",
    resume: bool = True
) -> pd.DataFrame:
    """Process institutions from input file and add GPT normalization."""
    
    print("=" * 70)
    print("  GPT-POWERED INSTITUTION NORMALIZATION")
    print(f"  Model: {model}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Load input data
    print(f"\n  Loading input from: {input_file}")
    df = pd.read_csv(input_file)
    print(f"  Total rows: {len(df)}")
    
    # Get unique institutions with their locations
    unique_institutions = df.groupby([institution_column]).agg({
        'City': 'first',
        'State': 'first',
        'Country': 'first'
    }).reset_index()
    
    print(f"  Unique institutions: {len(unique_institutions)}")
    
    # Load checkpoint
    checkpoint = load_checkpoint() if resume else {"processed_batches": 0, "name_mappings": {}}
    name_mappings = checkpoint.get("name_mappings", {})
    start_batch = checkpoint.get("processed_batches", 0)
    
    if name_mappings:
        print(f"  Resuming from checkpoint: {len(name_mappings)} institutions already mapped")
    
    # Initialize OpenAI client
    print("\n  Initializing OpenAI client...")
    client = get_openai_client()
    print("  ✓ Client ready")
    
    # Process in batches
    print("\n  Processing institutions in batches...")
    
    # Filter to unprocessed institutions
    unprocessed = unique_institutions[
        ~unique_institutions[institution_column].isin(name_mappings.keys())
    ]
    
    total_batches = (len(unprocessed) + batch_size - 1) // batch_size
    print(f"  Batches to process: {total_batches}")
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(unprocessed))
        batch = unprocessed.iloc[start_idx:end_idx]
        
        print(f"\n    Batch {batch_idx + 1}/{total_batches} ({len(batch)} institutions)")
        
        # Prepare batch data
        batch_data = [
            {
                "institution": row[institution_column],
                "city": row.get("City", ""),
                "state": row.get("State", ""),
                "country": row.get("Country", "")
            }
            for _, row in batch.iterrows()
        ]
        
        # Get GPT normalization
        result = normalize_batch_with_gpt(client, batch_data, model)
        
        if result and "groupings" in result:
            # Apply groupings
            for group in result["groupings"]:
                canonical = group.get("canonical_name", "")
                originals = group.get("original_names", [])
                
                for orig in originals:
                    if orig and canonical:
                        name_mappings[orig] = canonical
            
            # For institutions not in any group, use their original name
            for item in batch_data:
                inst = item["institution"]
                if inst not in name_mappings:
                    name_mappings[inst] = inst
        else:
            # Fallback: use original names
            for item in batch_data:
                inst = item["institution"]
                if inst not in name_mappings:
                    name_mappings[inst] = inst
        
        # Save checkpoint
        checkpoint = {
            "processed_batches": batch_idx + 1,
            "name_mappings": name_mappings
        }
        save_checkpoint(checkpoint)
        print(f"    ✓ Checkpoint saved ({len(name_mappings)} total mappings)")
        
        # Rate limiting
        time.sleep(0.5)
    
    # Apply mappings to full dataframe
    print("\n  Applying mappings to full dataset...")
    df["Institution_clean_gpt"] = df[institution_column].map(
        lambda x: name_mappings.get(x, x)
    )
    
    # Save output
    df.to_csv(output_file, index=False)
    
    # Summary
    print("\n" + "=" * 70)
    print("  COMPLETE!")
    print("=" * 70)
    
    raw_count = df[institution_column].nunique()
    clean_count = df["Institution_clean_gpt"].nunique()
    
    print(f"\n  Original unique institutions: {raw_count}")
    print(f"  Normalized unique institutions: {clean_count}")
    print(f"  Merged: {raw_count - clean_count} duplicates ({100*(raw_count-clean_count)/raw_count:.1f}%)")
    
    # Show top consolidated
    print(f"\n  Top 15 Institution_clean_gpt:")
    for inst, count in df["Institution_clean_gpt"].value_counts().head(15).items():
        print(f"    {inst}: {count}")
    
    print(f"\n  Saved to: {output_file}")
    
    return df


def compare_normalization_methods(input_file: Path) -> pd.DataFrame:
    """Compare existing normalization with GPT normalization."""
    
    print("=" * 70)
    print("  COMPARING NORMALIZATION METHODS")
    print("=" * 70)
    
    df = pd.read_csv(input_file)
    
    if "Institution_clean" not in df.columns or "Institution_clean_gpt" not in df.columns:
        print("  Error: Need both Institution_clean and Institution_clean_gpt columns")
        return None
    
    # Find differences
    differences = df[df["Institution_clean"] != df["Institution_clean_gpt"]]
    
    print(f"\n  Total rows: {len(df)}")
    print(f"  Rows with different normalization: {len(differences)}")
    
    # Show samples
    if len(differences) > 0:
        print(f"\n  Sample differences (first 20):")
        sample = differences[["Institution", "Institution_clean", "Institution_clean_gpt"]].drop_duplicates().head(20)
        for _, row in sample.iterrows():
            print(f"\n    Original: {row['Institution']}")
            print(f"    Keyword:  {row['Institution_clean']}")
            print(f"    GPT:      {row['Institution_clean_gpt']}")
    
    # Stats
    keyword_unique = df["Institution_clean"].nunique()
    gpt_unique = df["Institution_clean_gpt"].nunique()
    
    print(f"\n  Unique counts:")
    print(f"    Keyword-based: {keyword_unique}")
    print(f"    GPT-based: {gpt_unique}")
    print(f"    Difference: {keyword_unique - gpt_unique}")
    
    return differences


if __name__ == "__main__":
    # Default: normalize net new trials
    input_file = OUTPUT_DIR / "net_new_trials_1216_center_level.csv"
    output_file = OUTPUT_DIR / "net_new_trials_gpt_normalized.csv"
    
    normalize_institutions(
        input_file=input_file,
        output_file=output_file,
        batch_size=50,
        model="gpt-4o-mini"
    )

