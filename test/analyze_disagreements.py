"""
Deep dive into the 7 disagreements between Agentic 5-mini and GPT-5.2.
Goal: Understand WHY they disagree and if there's a prompt/pipeline issue.
"""

import sys
sys.path.insert(0, '..')

import pandas as pd
import requests
import json
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv('../.env')
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

from prompts.trial_categorization import get_trial_categorization_prompt
from prompts.trial_categorization_v2 import get_enhanced_categorization_prompt


def fetch_trial_data(nct_id):
    """Fetch trial data from API."""
    url = f'https://clinicaltrials.gov/api/v2/studies/{nct_id}'
    data = requests.get(url, params={'format': 'json'}, timeout=30).json()
    protocol = data.get('protocolSection', {})
    
    return {
        'title': protocol.get('identificationModule', {}).get('briefTitle', ''),
        'official_title': protocol.get('identificationModule', {}).get('officialTitle', ''),
        'conditions': protocol.get('conditionsModule', {}).get('conditions', []),
        'interventions': [i.get('name', '') for i in protocol.get('armsInterventionsModule', {}).get('interventions', [])],
        'brief_summary': protocol.get('descriptionModule', {}).get('briefSummary', ''),
        'eligibility': protocol.get('eligibilityModule', {}).get('eligibilityCriteria', ''),
    }


def test_with_prompt(nct_id, trial_data, prompt_getter, model='gpt-5-mini'):
    """Test categorization with a specific prompt."""
    prompt = prompt_getter(
        nct_id,
        trial_data['title'],
        trial_data['official_title'],
        trial_data['conditions'],
        trial_data['interventions'],
        trial_data['brief_summary'],
        trial_data['eligibility']
    )
    
    json_prompt = prompt + "\n\nRespond with ONLY valid JSON."
    
    response = client.responses.create(
        model=model,
        input=json_prompt,
    )
    
    # Extract text
    text = None
    for item in response.output:
        if hasattr(item, 'type') and item.type == 'message':
            if hasattr(item, 'content') and len(item.content) > 0:
                text = item.content[0].text
                break
    
    if not text:
        raise ValueError("Could not extract response")
    
    result = json.loads(text)
    return result


def main():
    """Analyze the disagreements in detail."""
    print("="*80)
    print("DEEP DIVE: DISAGREEMENTS BETWEEN AGENTIC 5-MINI AND GPT-5.2")
    print("="*80)
    
    # Load disagreements
    df = pd.read_csv('agentic_vs_52_comparison_fixed.csv')
    disagreements = df[~df['match']]
    
    print(f"\nAnalyzing {len(disagreements)} disagreements\n")
    
    # Test each disagreement with both prompts
    results = []
    
    for idx, row in disagreements.iterrows():
        nct_id = row['nct_id']
        
        print(f"\n{'='*80}")
        print(f"TRIAL: {nct_id}")
        print(f"{'='*80}")
        print(f"GPT-5.2 (ground truth): Tier {row['gpt_5_2_tier']} | {row['mutation_5_2']} + {row['cancer_scope_5_2']}")
        print(f"Agentic result:         Tier {row['agentic_tier']} | {row['mutation_agentic']} + {row['cancer_scope_agentic']}")
        
        # Fetch trial data
        trial_data = fetch_trial_data(nct_id)
        
        print(f"\nTrial Info:")
        print(f"  Conditions: {trial_data['conditions']}")
        print(f"  Eligibility (first 300 chars): {trial_data['eligibility'][:300]}...")
        
        # Test with both prompts using 5-mini
        print(f"\n--- Testing with 5-mini ---")
        
        try:
            # Test 1: Original prompt (used by GPT-5.2)
            print(f"\n1. Using ORIGINAL prompt (same as GPT-5.2):")
            result_original = test_with_prompt(nct_id, trial_data, get_trial_categorization_prompt, 'gpt-5-mini')
            tier_original = result_original['classification']['tier']
            mutation_original = result_original['analysis'].get('explicit_mutation_requirement', '')
            cancer_original = result_original['classification'].get('cancer_scope', '')
            print(f"   Result: Tier {tier_original} | {mutation_original} + {cancer_original}")
            
            # Test 2: Enhanced prompt (used by Agentic)
            print(f"\n2. Using ENHANCED prompt (agentic v2):")
            result_enhanced = test_with_prompt(nct_id, trial_data, get_enhanced_categorization_prompt, 'gpt-5-mini')
            tier_enhanced = result_enhanced['classification']['tier']
            mutation_enhanced = result_enhanced['analysis'].get('explicit_mutation_requirement', '')
            cancer_enhanced = result_enhanced['classification'].get('cancer_scope', '')
            print(f"   Result: Tier {tier_enhanced} | {mutation_enhanced} + {cancer_enhanced}")
            
            # Compare
            print(f"\n--- Analysis ---")
            if tier_original == tier_enhanced:
                print(f"✓ Both prompts agree: Tier {tier_original}")
            else:
                print(f"✗ Prompts disagree! Original={tier_original}, Enhanced={tier_enhanced}")
            
            if tier_original == row['gpt_5_2_tier']:
                print(f"✓ Original prompt matches GPT-5.2 (prompt is NOT the issue)")
            else:
                print(f"✗ Original prompt differs from GPT-5.2 (MODEL difference, not prompt)")
            
            results.append({
                'nct_id': nct_id,
                'gpt_5_2_tier': row['gpt_5_2_tier'],
                'agentic_tier': row['agentic_tier'],
                'mini_original_prompt': tier_original,
                'mini_enhanced_prompt': tier_enhanced,
                'prompt_matters': tier_original != tier_enhanced,
                'model_matters': tier_original != row['gpt_5_2_tier'],
            })
            
        except Exception as e:
            print(f"ERROR: {str(e)}")
            continue
    
    # Summary
    results_df = pd.DataFrame(results)
    results_df.to_csv('disagreement_analysis.csv', index=False)
    
    print(f"\n\n{'='*80}")
    print("SUMMARY")
    print("="*80)
    
    print(f"\nTotal disagreements analyzed: {len(results_df)}")
    
    prompt_matters = results_df['prompt_matters'].sum()
    model_matters = results_df['model_matters'].sum()
    
    print(f"\nPrompt differences (original vs enhanced): {prompt_matters}/{len(results_df)}")
    print(f"Model differences (5-mini vs 5.2 on same prompt): {model_matters}/{len(results_df)}")
    
    if prompt_matters > 0:
        print(f"\n⚠️  PROMPT IS A FACTOR in {prompt_matters} cases")
        print("   → The enhanced prompt (agentic) is producing different results")
    
    if model_matters > 0:
        print(f"\n⚠️  MODEL IS A FACTOR in {model_matters} cases")
        print("   → GPT-5-mini and GPT-5.2 disagree even with the same prompt")
    
    print(f"\n✓ Results saved to: disagreement_analysis.csv")
    print("="*80)


if __name__ == '__main__':
    main()

