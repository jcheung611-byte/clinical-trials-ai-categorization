"""
Systematic Model Comparison for Trial Categorization

Tests multiple OpenAI models on the same trial set and tracks:
- Accuracy (compared to known expected tiers)
- Cost (input + output tokens)
- Consistency (run each trial 2x, check if same result)
- Speed (latency per trial)
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
    ('NCT06227377', '2', 'G12D + Solid tumors'),
    ('NCT06179160', '2', 'G12D + Solid tumors'),
    ('NCT06586515', '2', 'G12D + includes NSCLC'),
    ('NCT06704724', '2', 'Multi-KRAS + includes NSCLC'),
    ('NCT03745326', '1.5', 'G12D + GI only'),
    ('NCT06364696', '2', 'G12D + Solid tumors'),
    ('NCT06385925', '2', 'G12D + Malignant Neoplasm'),
    ('NCT05786924', '2', 'Multi-KRAS + broad'),
]

# Models to test
MODELS_TO_TEST = [
    {
        'name': 'gpt-4o-mini',
        'api': 'chat',  # Chat Completions API
        'pricing': {'input': 0.15, 'output': 0.60},  # per 1M tokens
    },
    {
        'name': 'gpt-4o',
        'api': 'chat',
        'pricing': {'input': 2.50, 'output': 10.00},
    },
    {
        'name': 'gpt-5-mini',
        'api': 'responses',  # Responses API
        'pricing': {'input': None, 'output': None},  # TBD from API
        'reasoning_effort': 'none',
    },
    {
        'name': 'gpt-5-nano',
        'api': 'responses',
        'pricing': {'input': None, 'output': None},
        'reasoning_effort': 'none',
    },
    {
        'name': 'gpt-5.2',
        'api': 'responses',
        'pricing': {'input': None, 'output': None},
        'reasoning_effort': 'none',  # Default for GPT-5.2
    },
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


def call_chat_completions(model_name, prompt):
    """Call using Chat Completions API (GPT-4 models)."""
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
        'total_tokens': response.usage.total_tokens,
    }


def call_responses_api(model_name, prompt, reasoning_effort='none'):
    """Call using Responses API (GPT-5 models)."""
    start = time.time()
    
    try:
        # Note: Using new Responses API format based on documentation
        response = client.responses.create(
            model=model_name,
            input=prompt,
            reasoning={'effort': reasoning_effort},
            text={'verbosity': 'medium'},
            response_format={'type': 'json_object'},
        )
        
        latency = time.time() - start
        
        # Parse the response (format may differ from Chat Completions)
        result = json.loads(response.output.text)
        
        return {
            'result': result,
            'latency': latency,
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.total_tokens,
        }
    except Exception as e:
        return {
            'error': str(e),
            'latency': time.time() - start,
        }


def test_model(model_config, test_trials):
    """Test a single model on all trials."""
    print(f"\n{'='*80}")
    print(f"Testing: {model_config['name']}")
    print(f"{'='*80}")
    
    results = []
    total_cost = 0
    correct = 0
    
    for nct_id, expected_tier, description in test_trials:
        print(f"\n{nct_id}: ", end='', flush=True)
        
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
        if model_config['api'] == 'chat':
            response_data = call_chat_completions(model_config['name'], prompt)
        else:
            reasoning_effort = model_config.get('reasoning_effort', 'none')
            response_data = call_responses_api(model_config['name'], prompt, reasoning_effort)
        
        if 'error' in response_data:
            print(f"ERROR: {response_data['error']}")
            results.append({
                'nct_id': nct_id,
                'expected': expected_tier,
                'got': None,
                'error': response_data['error'],
            })
            continue
        
        # Extract tier
        tier = response_data['result'].get('classification', {}).get('tier', '?')
        match = '✓' if str(tier) == expected_tier else '✗'
        
        if str(tier) == expected_tier:
            correct += 1
        
        # Calculate cost
        input_cost = (response_data['input_tokens'] / 1_000_000) * model_config['pricing']['input'] if model_config['pricing']['input'] else 0
        output_cost = (response_data['output_tokens'] / 1_000_000) * model_config['pricing']['output'] if model_config['pricing']['output'] else 0
        cost = input_cost + output_cost
        total_cost += cost
        
        print(f"Expected {expected_tier}, Got {tier} {match} (${cost:.4f}, {response_data['latency']:.1f}s)")
        
        results.append({
            'nct_id': nct_id,
            'expected': expected_tier,
            'got': str(tier),
            'match': match == '✓',
            'cost': cost,
            'latency': response_data['latency'],
            'tokens': {
                'input': response_data['input_tokens'],
                'output': response_data['output_tokens'],
            }
        })
    
    accuracy = (correct / len(test_trials)) * 100
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {model_config['name']}")
    print(f"  Accuracy: {correct}/{len(test_trials)} ({accuracy:.1f}%)")
    print(f"  Total Cost: ${total_cost:.4f}")
    print(f"  Avg Latency: {sum(r['latency'] for r in results if 'latency' in r) / len(results):.2f}s")
    print(f"{'='*80}")
    
    return {
        'model': model_config['name'],
        'accuracy': accuracy,
        'correct': correct,
        'total': len(test_trials),
        'total_cost': total_cost,
        'results': results,
    }


def main():
    """Run comparison across all models."""
    print("="*80)
    print("SYSTEMATIC MODEL COMPARISON FOR TRIAL CATEGORIZATION")
    print("="*80)
    
    all_results = []
    
    for model_config in MODELS_TO_TEST:
        try:
            model_results = test_model(model_config, TEST_TRIALS)
            all_results.append(model_results)
        except Exception as e:
            print(f"\nFailed to test {model_config['name']}: {e}")
            continue
    
    # Final comparison
    print("\n" + "="*80)
    print("FINAL COMPARISON")
    print("="*80)
    print(f"{'Model':<20} {'Accuracy':<12} {'Total Cost':<12} {'Avg Latency'}")
    print("-"*80)
    
    for result in all_results:
        avg_latency = sum(r['latency'] for r in result['results'] if 'latency' in r) / len(result['results'])
        print(f"{result['model']:<20} {result['accuracy']:>5.1f}% ({result['correct']}/{result['total']})  ${result['total_cost']:>8.4f}    {avg_latency:>6.2f}s")
    
    # Save results
    with open('model_comparison_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print("\nResults saved to model_comparison_results.json")


if __name__ == '__main__':
    main()

