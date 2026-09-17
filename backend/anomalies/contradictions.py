import re
from typing import List, Dict, Any

class ContradictionEngine:
    """
    Cross-references claims in text against physical evidence (CDR, financials, graph edges).
    """
    
    def __init__(self, graph, db_session):
        self.graph = graph
        self.db = db_session
        
    def check_statement(self, statement_text: str, person_id: str) -> List[Dict[str, Any]]:
        contradictions = []
        
        # 1. Location Claims vs CDR
        location_claims = self._extract_location_claims(statement_text)
        for claim in location_claims:
            cdr_locations = self._get_cdr_locations(person_id, claim['date'])
            if cdr_locations and not self._is_near(claim['place'], cdr_locations):
                contradictions.append({
                    "type": "LOCATION_MISMATCH",
                    "severity": "high",
                    "claim": f"Claims to be in {claim['place']} on {claim['date']}",
                    "evidence": f"CDR places phone near tower(s): {', '.join(cdr_locations)}",
                    "source_span": claim['span']
                })
                
        # 2. Relationship Denials vs Graph Edges
        denial_claims = self._extract_relationship_denials(statement_text)
        for denial in denial_claims:
            edges = self._get_graph_edges(person_id, denial['target_person'])
            if edges:
                contradictions.append({
                    "type": "RELATIONSHIP_DENIAL",
                    "severity": "critical",
                    "claim": f"Denies knowing or associating with {denial['target_name']}",
                    "evidence": f"Graph shows {len(edges)} direct connections (e.g. {edges[0]['type']})",
                    "source_span": denial['span']
                })
                
        return contradictions

    # --- Dummy extraction methods for the prototype ---
    
    def _extract_location_claims(self, text: str) -> List[Dict]:
        """In a real system, this uses NER (like GLiNER) to parse dates and locations."""
        claims = []
        # Simple regex for prototype
        if "was in Pune" in text:
            claims.append({"place": "Pune", "date": "2026-03-05", "span": "was in Pune on March 5th"})
        return claims
        
    def _extract_relationship_denials(self, text: str) -> List[Dict]:
        claims = []
        if "never met Salim" in text:
            claims.append({"target_name": "Salim", "target_person": "P_SALIM_01", "span": "I have never met Salim"})
        return claims

    def _get_cdr_locations(self, person_id: str, date: str) -> List[str]:
        """Mock CDR lookup."""
        # For the demo, we return a contradictory location
        return ["Mumbai (Andheri East)"]
        
    def _is_near(self, claimed_place: str, actual_places: List[str]) -> bool:
        return False
        
    def _get_graph_edges(self, p1: str, p2: str) -> List[Dict]:
        """Mock graph lookup."""
        return [{"type": "CALL", "count": 14, "last_date": "2026-03-04"}]
