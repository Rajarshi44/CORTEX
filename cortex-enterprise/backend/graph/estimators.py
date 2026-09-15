import numpy as np
import math
from itertools import combinations
from typing import List, Dict, Set

class IcebergEstimator:
    """
    Estimates the true, unobserved size of a criminal network using 
    capture-recapture statistics (Lincoln-Petersen / Chapman estimator)
    based on entity overlap across different intelligence sources.
    """
    
    def estimate_network_size(self, source_sets: Dict[str, Set[str]]) -> Dict:
        """
        source_sets: dict mapping source name to a set of entity IDs.
        e.g. {'FIR': {'e1', 'e2'}, 'CDR': {'e2', 'e3'}}
        """
        sources = list(source_sets.keys())
        estimates = []
        
        for s1, s2 in combinations(sources, 2):
            set1 = source_sets[s1]
            set2 = source_sets[s2]
            
            n1 = len(set1)
            n2 = len(set2)
            m = len(set1 & set2)  # overlap
            
            if m > 0:
                # Chapman's bias-corrected estimator
                N_hat = ((n1 + 1) * (n2 + 1) / (m + 1)) - 1
                
                # 95% Confidence Interval
                variance = ((n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m)) / (((m + 1) ** 2) * (m + 2))
                ci = 1.96 * math.sqrt(variance)
                
                estimates.append({
                    "sources": (s1, s2),
                    "estimate": N_hat,
                    "overlap": m,
                    "ci_low": max(0, N_hat - ci),
                    "ci_high": N_hat + ci
                })
                
        if not estimates:
            return {"error": "Insufficient overlap to compute estimate."}
            
        # Aggregate using median
        median_est = np.median([e["estimate"] for e in estimates])
        observed = len(set().union(*source_sets.values()))
        
        # We can't have a true size smaller than the observed size
        final_estimate = max(observed, median_est)
        
        return {
            "observed": observed,
            "estimated_total": round(final_estimate),
            "dark_number": round(final_estimate - observed),
            "visibility_pct": round(100 * observed / final_estimate, 1) if final_estimate > 0 else 100,
            "pairwise_estimates": estimates
        }

# Mock testing
if __name__ == "__main__":
    # Simulate: FIR found 40 people, CDR found 50, but only 10 appear in both.
    source_sets = {
        'FIR': set(f"P{i}" for i in range(1, 41)),
        'CDR': set(f"P{i}" for i in range(31, 81)) # 10 overlap (31-40)
    }
    estimator = IcebergEstimator()
    result = estimator.estimate_network_size(source_sets)
    print("Iceberg Estimation:", result)
