from abc import ABC, abstractmethod
from typing import Any, Dict, List
import networkx as nx

class Detector(ABC):
    name: str = "base"
    severity_weight: float = 0.5
    
    @abstractmethod
    def run(self, graph: nx.Graph, directed_graph: nx.DiGraph, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute detection logic.
        Returns a list of dicts that conform to the Alert schema:
        {
            "type": self.name,
            "title": str,
            "description": str,
            "score": float,
            "entity_ids": List[str],
            "evidence": Dict[str, Any],
            "severity": "critical"|"high"|"medium"|"low",
            "reasons": List[str]
        }
        """
        pass
