"""
Systematic Model Comparison - GPT-4o vs GPT-5 models
"""

import os
import json
import time
import requests
from dotenv import load_dotenv
from openai import OpenAI
import sys
sys.path.insert(0, '..')

from prompts.trial_categorization import get_trial_categorization_prompt

load_dotenv('../.env')
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# Test set with known expected tiers
TEST_TRIALS = [
    ('NCT06445062', '1.5', 'G12D + GI (CRC, PDAC)'),
    ('NCT06589440', '3', 'No mutation + CRC only'),
    ('NCT06586515', '2', 'G12D + includes NSCLC'),
    ('NCT03745326', '1.5', 'G12D + GI only (no lung)'),
    ('NCT06364696', '2', 'G12D + Solid tumors'),
    ('NCT06385925', '2', 'G12D + Malignant Neoplasm'),
    ('NCT06227377', '2', 'G12D + Solid tumors'),
    ('NCT06179160', '2', 'G12D + Solid tumors'),
    ('NCT06704724', '2', 'Multi-KRAS + includes NSCLC'),
    ('NCT05786924', '2', 'Multi-KRAS + broad'),
]


def fetch_trial_data(nct_id):
    """Fetch trial data from ClinicalTrials.gov API."""
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


def call_gpt4_model(model_name, prompt):
    """Call GPT-4 models via Chat Completions API."""
    start = time.time()
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {'role': 'system', 'content': 'Expert clinical trial analyst. JSON only.'},
            {'role': 'user', 'content': prompt}
        ],
        response_format={'type': 'json_object'},
        temperature=0.1,
        max_tokens=700,
    )
    
    latency = time.time() - start
    result = json.loads(response.choices[0].message.content)
    
    return {
        'result': result,
        'latency': latency,
        'input_tokens': response.usage.prompt_tokens,
        'output_tokens': response.usage.completion_tokens,
        'reasoning_tokens': 0,
    }


def call_gpt5_model(model_name, prompt):
    """Call GPT-5 models via Responses API."""
    start = time.time()
    
    # Add JSON instruction to prompt
    json_prompt = prompt + "\n\nRespond with ONLY valid JSON in the exact format specified above."
    
    response = client.responses.create(
        model=model_name,
        input=json_prompt,
    )
    
    latency = time.time() - start
    
    # Extract text from response
    text = None
    for item in response.output:
        if hasattr(item, 'type') and item.type == 'message':
            if hasattr(item, 'content') and len(item.content) > 0:
                text = item.content[0].text
                break
    
    if not text:
        raise ValueError(f"Could not extract text from response: {response.output}")
    
    # Parse JSON
    result = json.loads(text)
    
    return {
        'result': result,
        'latency': latency,
        'input_tokens': response.usage.input_tokens,
        'output_tokens': response.usage.output_tokens,
        'reasoning_tokens': response.usage.output_tokens_details.reasoning_tokens,
    }


def test_model(model_name, test_trials, is_gpt5=False):
    """Test a single model on all trials."""
    print(f"\n{'='*80}")
    print(f"Testing: {model_name}")
    print(f"{'='*80}")
    
    results = []
    correct = 0
    
    for nct_id, expected_tier, description in test_trials:
        print(f"{nct_id}: ", end='', flush=True)
        
        # Fetch trial data
        trial_data = fetch_trial_data(nct_id)
        
        # Generate prompt
        prompt = get_trial_categorization_prompt(
            nct_id,
            trial_data['title'],
            trial_data['official_title'],
            trial_data['conditions'],
            trial_data['interventions'],
            trial_data['brief_summary'],
            trial_data['eligibility']
        )
        
        # Call appropriate API
        try:
            if is_gpt5:
                response_data = call_gpt5_model(model_name, prompt)
            else:
                response_data = call_gpt4_model(model_name, prompt)
        except Exception as e:
            print(f"ERROR: {str(e)[:100]}")
            results.append({
                'nct_id': nct_id,
                'expected': expected_tier,
                'error': str(e),
            })
            continue
        
        # Extract tier
        tier = response_data['result'].get('classification', {}).get('tier', '?')
        match = '✓' if str(tier) == expected_tier else '✗'
        
        if str(tier) == expected_tier:
            correct += 1
        
        print(f"Exp {expected_tier}, Got {tier} {match} ({response_data['latency']:.1f}s, {response_data['reasoning_tokens']} reasoning tokens)")
        
        results.append({
            'nct_id': nct_id,
            'expected': expected_tier,
            'got': str(tier),
            'match': match == '✓',
            'latency': response_data['latency'],
            'tokens': {
                'input': response_data['input_tokens'],
                'output': response_data['output_tokens'],
                'reasoning': response_data['reasoning_tokens'],
            }
        })
    
    accuracy = (correct / len(test_trials)) * 100
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {model_name}")
    print(f"  Accuracy: {correct}/{len(test_trials)} ({accuracy:.1f}%)")
    avg_latency = sum(r['latency'] for r in results if 'latency' in r) / len([r for r in results if 'latency' in r])
    print(f"  Avg Latency: {avg_latency:.2f}s")
    total_reasoning = sum(r['tokens']['reasoning'] for r in results if 'tokens' in r)
    print(f"  Total Reasoning Tokens: {total_reasoning}")
    print(f"{'='*80}")
    
    return {
        'model': model_name,
        'accuracy': accuracy,
        'correct': correct,
        'total': len(test_trials),
        'results': results,
    }


def main():
    """Run comparison across all models."""
    print("="*80)
    print("SYSTEMATIC MODEL COMPARISON: GPT-4 vs GPT-5")
    print("="*80)
    
    models = [
        ('gpt-4o-mini', False),
        ('gpt-4o', False),
        ('gpt-5-nano', True),
        ('gpt-5-mini', True),
        ('gpt-5.2', True),
    ]
    
    all_results = []
    
    for model_name, is_gpt5 in models:
        try:
            model_results = test_model(model_name, TEST_TRIALS, is_gpt5)
            all_results.append(model_results)
        except Exception as e:
            print(f"\nFailed to test {model_name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Final comparison
    print("\n" + "="*80)
    print("FINAL COMPARISON")
    print("="*80)
    print(f"{'Model':<20} {'Accuracy':<15} {'Avg Latency'}")
    print("-"*80)
    
    for result in all_results:
        avg_latency = sum(r['latency'] for r in result['results'] if 'latency' in r) / len([r for r in result['results'] if 'latency' in r])
        print(f"{result['model']:<20} {result['accuracy']:>5.1f}% ({result['correct']}/{result['total']:>2})     {avg_latency:>6.2f}s")
    
    # Save results
    output_file = 'model_comparison_results.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nResults saved to {output_file}")
    print("\n" + "="*80)
    print("KEY FINDING: Which model should we use?")
    print("="*80)
    
    # Find best model
    best_accuracy = max(r['accuracy'] for r in all_results)
    best_models = [r for r in all_results if r['accuracy'] == best_accuracy]
    
    print(f"Best accuracy: {best_accuracy:.1f}%")
    print(f"Models with best accuracy: {', '.join(r['model'] for r in best_models)}")


if __name__ == '__main__':
    main()

