import math
from itertools import combinations
from typing import List, Dict, Set

class GhostNodePredictor:
    """
    Infers unobserved intermediaries based on structural holes in the network.
    """
    
    def __init__(self, graph):
        self.graph = graph

    def predict_ghost_nodes(self, communities: Dict[str, List[str]], threshold: float = 0.6) -> List[Dict]:
        ghosts = []
        
        for comm_id, members in communities.items():
            # Look for pairs with NO direct edge but high indirect similarity
            for a, b in combinations(members, 2):
                if self.graph.has_edge(a, b):
                    continue
                
                shared_neighbors = list(set(self.graph.neighbors(a)) & set(self.graph.neighbors(b)))
                num_shared = len(shared_neighbors)
                
                # Jaccard similarity as a proxy for structural equivalence
                degree_a = self.graph.degree(a)
                degree_b = self.graph.degree(b)
                
                if degree_a + degree_b - num_shared == 0:
                    continue
                    
                similarity = num_shared / (degree_a + degree_b - num_shared)
                
                if similarity > threshold and num_shared >= 2:
                    ghosts.append({
                        "connects": (a, b),
                        "confidence_score": round(similarity, 3),
                        "shared_neighbors_count": num_shared,
                        "shared_neighbors": shared_neighbors,
                        "interpretation": f"High structural similarity ({similarity:.2f}) but zero direct communication suggests a deliberately unobserved intermediary."
                    })
                    
        return sorted(ghosts, key=lambda x: x['confidence_score'], reverse=True)

# Mock graph for testing
if __name__ == "__main__":
    import networkx as nx
    G = nx.Graph()
    # A and B are not directly connected, but share 3 neighbors
    G.add_edges_from([('A', 'N1'), ('A', 'N2'), ('A', 'N3'), ('B', 'N1'), ('B', 'N2'), ('B', 'N3')])
    predictor = GhostNodePredictor(G)
    ghosts = predictor.predict_ghost_nodes({'comm_1': ['A', 'B', 'N1', 'N2', 'N3']}, threshold=0.5)
    print("Predicted Ghost Nodes:", ghosts)
