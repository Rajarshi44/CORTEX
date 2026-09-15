from typing import Dict, Type
from .base import Detector

REGISTRY: Dict[str, Detector] = {}

def register(cls: Type[Detector]) -> Type[Detector]:
    """Decorator to register a detector plugin."""
    instance = cls()
    REGISTRY[instance.name] = instance
    return cls
