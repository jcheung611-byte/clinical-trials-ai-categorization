"""
Full Parallel Categorization - 20 Workers
Process remaining 2,734 trials from checkpoint
Expected time: ~4-5 minutes
"""

import os
import sys
import json
import time
import pandas as pd
import subprocess

sys.path.insert(0, '..')

def main():
    print("="*80)
    print("FULL PARALLEL CATEGORIZATION: 20 Workers")
    print("="*80)
    
    # Load dataset
    trials_df = pd.read_csv('../output/exhaustive_search_results_v2.csv')
    trials_df.rename(columns={'NCT Code': 'nct_id'}, inplace=True)
    
    # Load existing
    existing_330 = pd.read_csv('../output/priority_trials_categorized.csv')
    existing_ncts = set(existing_330['nct_id'].values)
    
    # Load checkpoint
    checkpoint_file = '../output/agentic_checkpoint.csv'
    if os.path.exists(checkpoint_file):
        checkpoint_df = pd.read_csv(checkpoint_file)
        existing_ncts.update(checkpoint_df['nct_id'].values)
        print(f"\n✓ Found checkpoint: {len(checkpoint_df)} trials already processed")
    
    # Get unprocessed trials
    remaining_df = trials_df[~trials_df['nct_id'].isin(existing_ncts)]
    remaining_trials = remaining_df['nct_id'].tolist()
    
    print(f"\nDataset Summary:")
    print(f"  Total trials: {len(trials_df)}")
    print(f"  Already processed: {len(existing_ncts)}")
    print(f"  Remaining: {len(remaining_trials)}")
    
    print(f"\nParallel Configuration:")
    print(f"  Workers: 20")
    print(f"  Trials per worker: ~{len(remaining_trials) // 20}")
    print(f"  Expected time: ~{len(remaining_trials) * 1.8 / 60 / 20:.1f} minutes")
    print(f"  Expected cost: ~${len(remaining_trials) * 0.003:.2f}")
    
    # Split into 20 batches
    batch_size = len(remaining_trials) // 20
    batches = []
    for i in range(20):
        start_idx = i * batch_size
        if i == 19:  # Last batch gets remainder
            batch = remaining_trials[start_idx:]
        else:
            batch = remaining_trials[start_idx:start_idx + batch_size]
        batches.append(batch)
    
    # Create output directory
    output_dir = '../output/parallel_full_20workers'
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("LAUNCHING 20 WORKERS...")
    print("="*80)
    
    # Launch workers
    processes = []
    for worker_id, batch in enumerate(batches):
        batch_file = f'{output_dir}/batch_{worker_id}.json'
        with open(batch_file, 'w') as f:
            json.dump(batch, f)
        
        cmd = [
            'python3', '-c',
            f"""
import sys
sys.path.insert(0, '..')
import json
from test_parallel_categorization import process_batch

with open('{batch_file}') as f:
    batch = json.load(f)
    
process_batch(batch, {worker_id}, '{output_dir}')
"""
        ]
        
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(__file__),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        processes.append((proc, worker_id, len(batch)))
        
        if (worker_id + 1) % 5 == 0:
            print(f"✓ Workers 0-{worker_id} started ({sum(len(b) for b in batches[:worker_id+1])} trials assigned)")
    
    print(f"\n{'='*80}")
    print(f"All 20 workers launched!")
    print(f"{'='*80}")
    print(f"\nMonitor progress:")
    print(f"  tail -f {output_dir}/worker_*_log.txt")
    print(f"\nWaiting for completion...")
    print("="*80 + "\n")
    
    start_time = time.time()
    completed = 0
    completed_trials = 0
    
    for proc, worker_id, batch_size in processes:
        proc.wait()
        completed += 1
        completed_trials += batch_size
        elapsed = time.time() - start_time
        
        if completed % 5 == 0 or completed == 20:
            pct = (completed / 20) * 100
            print(f"✓ {completed}/20 workers completed ({pct:.0f}%) | "
                  f"{completed_trials} trials | "
                  f"{elapsed/60:.1f} min elapsed | "
                  f"ETA: {(elapsed / completed * 20 - elapsed)/60:.1f} min")
    
    total_time = time.time() - start_time
    
    # Merge results
    print(f"\n{'='*80}")
    print("MERGING RESULTS...")
    print("="*80)
    
    all_results = []
    total_cost = 0
    rate_limit_errors = 0
    
    for worker_id in range(20):
        result_file = f'{output_dir}/worker_{worker_id}_results.csv'
        log_file = f'{output_dir}/worker_{worker_id}_log.txt'
        
        # Check for rate limit errors
        if os.path.exists(log_file):
            with open(log_file) as f:
                log_content = f.read()
                if '429' in log_content or 'rate limit' in log_content.lower():
                    rate_limit_errors += 1
        
        if os.path.exists(result_file):
            df = pd.read_csv(result_file)
            all_results.append(df)
    
    if all_results:
        merged_df = pd.concat(all_results, ignore_index=True)
        
        # Merge with checkpoint if exists
        if os.path.exists(checkpoint_file):
            checkpoint_df = pd.read_csv(checkpoint_file)
            # Remove overlapping columns except nct_id and trial_name
            cols_to_keep = ['nct_id', 'trial_name', 'agentic_tier', 'agentic_mutation', 
                           'agentic_cancer_scope', 'agentic_tier_reason']
            checkpoint_df = checkpoint_df[[c for c in cols_to_keep if c in checkpoint_df.columns]]
            merged_df = pd.concat([checkpoint_df, merged_df], ignore_index=True)
        
        # Save final results
        merged_df.to_csv('../output/agentic_all_trials_complete.csv', index=False)
        
        print(f"\n{'='*80}")
        print("PARALLEL CATEGORIZATION COMPLETE!")
        print("="*80)
        
        print(f"\nResults:")
        print(f"  Total trials processed: {len(merged_df)}")
        print(f"  New trials this run: {len(all_results[0]) if all_results else 0}")
        print(f"  Total time: {total_time/60:.1f} minutes")
        print(f"  Avg time/trial: {total_time/sum(len(b) for b in batches):.1f} seconds")
        print(f"  Workers with rate limit errors: {rate_limit_errors}/20")
        
        print(f"\nTier distribution (all trials):")
        print(merged_df['agentic_tier'].value_counts().sort_index())
        
        print(f"\nFiles saved:")
        print(f"  ✓ Complete results: ../output/agentic_all_trials_complete.csv")
        print(f"  ✓ Worker logs: {output_dir}/worker_*_log.txt")
        print(f"  ✓ Worker results: {output_dir}/worker_*_results.csv")
        
        print(f"\n{'='*80}")
        print("NEXT STEP: Filter Tier 1/1.5/2 and verify with GPT-5.2")
        print("="*80)
        
        # Show Tier 1/1.5/2 count
        high_priority = merged_df[merged_df['agentic_tier'].isin([1, 1.5, 2])]
        print(f"\nHigh-priority trials to verify: {len(high_priority)}")
        print(high_priority['agentic_tier'].value_counts().sort_index())
        
    else:
        print(f"\n❌ No results found - check logs for errors")


if __name__ == '__main__':
    main()

