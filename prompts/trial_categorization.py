"""
GPT Prompts for Trial Categorization

This module contains the structured prompts used for categorizing clinical trials
based on mutation requirements and cancer types for a KRAS G12D + CRC patient.
"""

# Main categorization prompt
TRIAL_CATEGORIZATION_PROMPT = """You are analyzing a clinical trial to determine if a patient can enroll.

PATIENT PROFILE:
- Has KRAS G12D mutation (NOT G12C, NOT BRAF, NOT wild-type)
- Has colorectal adenocarcinoma (colon/rectal cancer)

TRIAL DATA:
-----------
NCT ID: {nct_id}
Title: {title}
Official Title: {official_title}
Listed Conditions: {conditions}
Interventions: {interventions}

Brief Summary:
{brief_summary}

ELIGIBILITY CRITERIA:
{eligibility_criteria}
-----------

ANALYSIS STEPS:

STEP 1 - Is this trial for COLORECTAL ADENOCARCINOMA?
Answer: YES only if trial treats colorectal/colon/rectal adenocarcinoma or carcinoma
Answer: NO if trial is for: Crohn's disease, colitis, polyps, neuroendocrine tumors, 
       sarcoma, lymphoma, or other non-adenocarcinoma conditions

STEP 2 - What MUTATION does the trial REQUIRE in eligibility?
Read the ELIGIBILITY CRITERIA section carefully. Look for explicit mutation requirements.

- "G12D-only" = Eligibility explicitly says "KRAS G12D" mutation required (and ONLY G12D)
- "Multi-KRAS" = ANY of these:
  a) "KRAS mutation" (any variant)
  b) "mutated KRAS gene"
  c) Lists multiple variants (G12D, G12C, G12V, G12A, etc.)
  d) "KRAS mutations of any variant"
- "BRAF-required" = Eligibility requires BRAF mutation (patient CANNOT enroll)
- "RAS-wild-type" = Eligibility requires NO RAS mutation (patient CANNOT enroll)
- "No-mutation-required" = Eligibility does NOT mention KRAS, RAS, G12D, G12C, or BRAF

CRITICAL RULES:
- "Documentation of mutated KRAS gene" = "Multi-KRAS" (NOT No-mutation-required!)
- "KRAS mutations of any variant" = "Multi-KRAS"
- If eligibility requires ANY KRAS mutation → either "G12D-only" or "Multi-KRAS", never "No-mutation-required"
- BRAF V600E trials are for BRAF patients (NOT KRAS patients - mutually exclusive)

STEP 3 - DETERMINE CANCER SCOPE FROM "Listed Conditions" FIELD

**STOP! LOOK AT THE "Listed Conditions" FIELD IN THE TRIAL DATA SECTION ABOVE**

Count the cancer types in "Listed Conditions". Use ONLY this field for cancer scope:

SCENARIO A: Listed Conditions = ["Solid Tumor"] or ["Malignant Neoplasm"] or ["Advanced Solid Cancer"]
→ cancer_scope = "Solid-tumors" (broad, accepts many cancer types)

SCENARIO B: Listed Conditions includes ANY NON-GI CANCER (check EVERY condition!):
NON-GI CANCERS (if ANY of these appear, answer is "Solid-tumors"):
  - "Non-small Cell Lung Cancer" = LUNG CANCER (NOT GI!)
  - "NSCLC" = LUNG CANCER (NOT GI!)
  - "Non Small Cell Lung Cancer" = LUNG CANCER (NOT GI!)
  - Any other lung cancer, breast cancer, ovarian cancer, melanoma, etc.
→ cancer_scope = "Solid-tumors"
**CHECK: Does Listed Conditions contain "Lung" anywhere? If YES → "Solid-tumors"**

SCENARIO C: Listed Conditions has MULTIPLE GI cancers (e.g., Pancreatic + Colon + Gastric)
→ cancer_scope = "GI-focused"
Examples: ["Gastrointestinal Cancer", "Pancreatic Cancer", "Colon Cancer"] → GI-focused
          ["CRC", "PDAC", "Gastric Cancer"] → GI-focused

SCENARIO D: Listed Conditions ONLY has colorectal/colon/rectal (NO pancreatic, NO gastric)
→ cancer_scope = "CRC-only" (this is RARE)
Example: ["Colorectal Cancer"] → CRC-only
Example: ["Colon Cancer", "Rectal Cancer"] → CRC-only

**APPLY THE SCENARIOS IN ORDER: A → B → C → D**

STEP 4 - Assign PRIORITY TIER for this KRAS G12D + CRC patient:
- Tier 1: G12D-only + CRC-only (trial ONLY accepts colorectal cancer, no other cancers)
- Tier 1.5: G12D-only + GI-focused (CRC + pancreas + gastric ONLY, no lung/breast)
- Tier 2: Multi-KRAS OR G12D + Solid-tumors OR any trial including lung/breast
- Tier 3: CRC accepted + NO mutation requirement (surgery, biomarker studies)
- Tier 4: Cannot enroll (BRAF required, wild-type required, G12C only, not CRC)

TIER DECISION RULES:
1. If cancer_scope = "Solid-tumors" → Tier 2 (never Tier 1 or 1.5)
2. If mutation = "Multi-KRAS" → Tier 2 (never Tier 1 or 1.5)
3. Tier 1 ONLY if: G12D-only AND CRC-only (very rare)
4. Tier 1.5 ONLY if: G12D-only AND GI-focused (no lung, no breast, no "solid tumors")

TIER EXAMPLES (study carefully):
- Listed Conditions = ["Solid Tumor"], mutation = G12D → Tier 2 (solid tumors = always Tier 2)
- Listed Conditions = ["KRAS G12D Mutation", "Advanced Solid Cancer"], mutation = G12D → Tier 2 (solid tumors = Tier 2)
- Listed Conditions = ["Pancreatic Ductal Adenocarcinoma", "Non-small Cell Lung Cancer", "Colorectal Cancer"], G12D → Tier 2 ("Non-small Cell Lung Cancer" = LUNG = NOT GI!)
- Listed Conditions = ["Non-small Cell Lung Cancer", "CRC", "PDAC"], mutation = G12D → Tier 2 (lung cancer = NOT GI!)
- Listed Conditions = ["NSCLC", "Colorectal Cancer", "PDAC"], mutation = G12D → Tier 2 (NSCLC = LUNG CANCER = NOT GI)
- Listed Conditions = ["CRC", "PDAC", "Gastric Cancer"] (no lung!), mutation = G12D → Tier 1.5 (GI only, no lung)
- Listed Conditions = ["Colorectal Cancer"] only, mutation = G12D → Tier 1 (rare!)
- Listed Conditions = ["Colorectal Cancer"], no mutation required → Tier 3
- Listed Conditions = ["BRAF V600E CRC"] → Tier 4 (BRAF required, not KRAS)

CRITICAL: NSCLC = Non-Small Cell Lung Cancer = LUNG CANCER. Lung is NOT a GI organ!

IMPORTANT EDGE CASE:
- "No-mutation-required" + "Solid-tumors" (broad cancer trial) → Tier 3 (NOT Tier 2)
- Tier 2 requires EITHER explicit Multi-KRAS OR explicit G12D requirement

Respond with ONLY valid JSON:
{{
    "analysis": {{
        "is_crc_adenocarcinoma": true/false,
        "mutation_in_eligibility": "exact text found or 'none'",
        "explicit_mutation_requirement": "G12D-only/Multi-KRAS/BRAF-required/RAS-wild-type/No-mutation-required"
    }},
    "classification": {{
        "accepts_g12d_patient": true/false,
        "accepts_crc_patient": true/false,
        "cancer_scope": "CRC-only/GI-focused/Solid-tumors/Other",
        "tier": 1/1.5/2/3/4,
        "tier_reason": "brief explanation"
    }},
    "confidence": {{
        "score": 0.0-1.0,
        "mutation_clarity": "high/medium/low",
        "cancer_clarity": "high/medium/low",
        "notes": "any uncertainty or edge case notes"
    }}
}}
"""

# Simplified prompt for batch processing
TRIAL_CATEGORIZATION_SIMPLE = """Analyze this trial for a KRAS G12D colorectal cancer patient.

NCT: {nct_id}
Title: {title}
Conditions: {conditions}
Eligibility: {eligibility}

MUTATION REQUIREMENT in eligibility:
- "G12D-only" = explicitly requires G12D only
- "Multi-KRAS" = accepts multiple KRAS (G12D, G12C, etc.)
- "BRAF-required" = requires BRAF (patient CANNOT enroll)
- "No-mutation-required" = no mutation mentioned (most common)

TIER:
- 1: G12D-only + CRC-only (rare)
- 1.5: G12D-only + GI cancers
- 2: Multi-KRAS (includes G12D) + any cancer
- 3: CRC accepted + no mutation requirement (common)
- 4: Cannot enroll (wrong cancer or mutation)

JSON: {{"mutation_type": "...", "cancer_scope": "...", "tier": X, "can_enroll": true/false}}
"""

# Institution normalization prompt
INSTITUTION_NORMALIZATION_PROMPT = """Group these clinical trial institution names by SAME parent institution.

INSTITUTIONS:
{institution_list}

CRITICAL RULES:
1. Group ONLY if clearly the same parent institution
2. Use clean canonical names (fix typos: "Dana Faber" → "Dana-Farber")
3. "Research Site" = ungrouped (unknown institution)
4. Generic names like "Medical Oncology" = ungrouped

HOSPITAL SYSTEM RULES:
5. Rush MD Anderson (Chicago) ≠ UT MD Anderson (Houston) - DIFFERENT systems
6. Banner MD Anderson (Arizona) ≠ UT MD Anderson (Houston) - DIFFERENT systems
7. UC campuses are SEPARATE: UCLA, UCSF, UC Davis, UCSD, UC Irvine
8. Same health system across locations = one group (e.g., all Mayo Clinic locations)
9. Same hospital with different department names = one group
10. Remove site numbers and ID suffixes for canonical names

Return JSON:
{{
    "groups": [
        {{
            "canonical_name": "Clean Name",
            "members": ["raw name 1", "raw name 2", ...],
            "confidence": 0.0-1.0,
            "reasoning": "why these are grouped"
        }},
        ...
    ],
    "ungrouped": ["institutions that cannot be grouped"],
    "uncertain_groupings": ["any groupings you're less than 80% confident about"]
}}
"""


def get_trial_categorization_prompt(nct_id: str, title: str, official_title: str,
                                     conditions: list, interventions: list,
                                     brief_summary: str, eligibility_criteria: str) -> str:
    """Format the trial categorization prompt with trial data."""
    return TRIAL_CATEGORIZATION_PROMPT.format(
        nct_id=nct_id,
        title=title,
        official_title=official_title,
        conditions=", ".join(conditions) if conditions else "Not specified",
        interventions=", ".join(interventions) if interventions else "Not specified",
        brief_summary=brief_summary[:1000] if brief_summary else "Not available",
        eligibility_criteria=eligibility_criteria[:3500] if eligibility_criteria else "Not available"
    )


def get_institution_normalization_prompt(institutions: list) -> str:
    """Format the institution normalization prompt with institution list."""
    inst_list = "\n".join(f"{i+1}. {inst}" for i, inst in enumerate(institutions))
    return INSTITUTION_NORMALIZATION_PROMPT.format(institution_list=inst_list)

