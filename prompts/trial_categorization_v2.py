"""
Improved Trial Categorization Prompts
- Clearer tier decision logic for edge cases
- Two-pass system: initial categorization + verification
"""

# Enhanced prompt with clearer tier logic
TRIAL_CATEGORIZATION_ENHANCED = """You are analyzing a clinical trial to determine if a patient can enroll.

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

STEP-BY-STEP ANALYSIS:

STEP 1: What MUTATION does the trial REQUIRE?
Read eligibility carefully:
- "G12D-only" = Explicitly requires KRAS G12D only
- "Multi-KRAS" = Accepts multiple KRAS variants (G12D, G12C, G12V, etc.)
- "No-mutation-required" = No mention of KRAS/RAS/BRAF requirement

STEP 2: What CANCER TYPES does the trial accept?
Check "Listed Conditions" above:
- "CRC-only" = Only colorectal/colon/rectal
- "GI-focused" = Only GI cancers (CRC + pancreas + gastric + bile duct)
- "Solid-tumors" = Broad solid tumors OR includes non-GI like NSCLC/lung/breast

STEP 3: Assign TIER using this DECISION TREE:

┌─ Is mutation required? ─────────────────────────────────────┐
│                                                              │
│ YES: G12D-only                    YES: Multi-KRAS           │ NO: No-mutation-required
│     │                                  │                     │
│     ├─ CRC-only → TIER 1               └─ Any cancer → TIER 2    └─ CRC accepted → TIER 3
│     ├─ GI-focused → TIER 1.5                                         (Always Tier 3!)
│     └─ Solid-tumors → TIER 2
│
└──────────────────────────────────────────────────────────────┘

CRITICAL RULES (CHECK THESE FIRST):
1. ✋ NO mutation requirement → ALWAYS Tier 3 (even if Solid-tumors!)
2. ✋ Multi-KRAS → ALWAYS Tier 2 (regardless of cancer scope)
3. ✋ Solid-tumors scope → ALWAYS Tier 2 (IF mutation is required)
4. ✋ Cannot enroll (BRAF/G12C/wild-type only) → ALWAYS Tier 4

TIER DEFINITIONS:
- Tier 1: G12D-only + CRC-only (RARE: trial only accepts CRC, nothing else)
- Tier 1.5: G12D-only + GI-focused (CRC + pancreas + gastric, NO lung/breast)
- Tier 2: Multi-KRAS + any cancer OR G12D + Solid-tumors
- Tier 3: CRC accepted + NO mutation requirement ← MOST COMMON!
- Tier 4: Patient cannot enroll (wrong mutation or not CRC)

COMMON MISTAKES TO AVOID:
❌ WRONG: "No mutation + Solid-tumors = Tier 2"
✅ RIGHT: "No mutation + ANY cancer = Tier 3"

❌ WRONG: "Solid-tumors always = Tier 2"
✅ RIGHT: "Solid-tumors = Tier 2 ONLY IF mutation required"

EXAMPLES:
1. Listed: ["Solid Tumor"], Mutation: G12D → Tier 2 (mutation required + solid tumors)
2. Listed: ["Solid Tumor"], Mutation: None → Tier 3 (NO mutation = always Tier 3)
3. Listed: ["CRC"], Mutation: None → Tier 3 (NO mutation = Tier 3)
4. Listed: ["CRC"], Mutation: G12D → Tier 1 (G12D + CRC-only)
5. Listed: ["CRC", "PDAC"], Mutation: G12D → Tier 1.5 (G12D + GI-focused)
6. Listed: ["CRC", "NSCLC"], Mutation: G12D → Tier 2 (includes lung = solid tumors)
7. Listed: ["CRC"], Mutation: Multi-KRAS → Tier 2 (Multi-KRAS = always Tier 2)

Respond with ONLY valid JSON:
{{
    "analysis": {{
        "is_crc_adenocarcinoma": true/false,
        "mutation_in_eligibility": "exact text or 'none'",
        "explicit_mutation_requirement": "G12D-only/Multi-KRAS/No-mutation-required/BRAF-required/RAS-wild-type"
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
        "notes": "any uncertainty"
    }}
}}
"""

# Verification prompt for edge cases
TIER_VERIFICATION_PROMPT = """You are verifying a clinical trial categorization.

ORIGINAL CATEGORIZATION:
NCT: {nct_id}
Tier: {tier}
Mutation: {mutation}
Cancer Scope: {cancer_scope}
Reason: {reason}

VERIFICATION CHECKLIST:
□ If mutation = "No-mutation-required" → tier MUST be 3 or 4 (never 2)
□ If mutation = "Multi-KRAS" → tier MUST be 2 (always)
□ If cancer_scope = "Solid-tumors" AND mutation required → tier should be 2
□ If cancer_scope = "Solid-tumors" AND NO mutation → tier should be 3

EDGE CASE DETECTION:
Is this categorization: "No-mutation-required + Solid-tumors = Tier 2"?
→ This is WRONG. Correct tier is 3.

Review the original categorization above. Is it correct?

Respond with JSON:
{{
    "is_correct": true/false,
    "corrected_tier": X (if incorrect),
    "corrected_reason": "explanation" (if incorrect),
    "verification_notes": "what you checked"
}}
"""


def get_enhanced_categorization_prompt(nct_id: str, title: str, official_title: str,
                                       conditions: list, interventions: list,
                                       brief_summary: str, eligibility_criteria: str) -> str:
    """Format the enhanced categorization prompt."""
    return TRIAL_CATEGORIZATION_ENHANCED.format(
        nct_id=nct_id,
        title=title,
        official_title=official_title,
        conditions=", ".join(conditions) if conditions else "Not specified",
        interventions=", ".join(interventions) if interventions else "Not specified",
        brief_summary=brief_summary[:1000] if brief_summary else "Not available",
        eligibility_criteria=eligibility_criteria[:3500] if eligibility_criteria else "Not available"
    )


def get_verification_prompt(nct_id: str, tier: str, mutation: str, 
                           cancer_scope: str, reason: str) -> str:
    """Format the verification prompt."""
    return TIER_VERIFICATION_PROMPT.format(
        nct_id=nct_id,
        tier=tier,
        mutation=mutation,
        cancer_scope=cancer_scope,
        reason=reason
    )

