import os
import sys
from pathlib import Path

# Ensure the app module can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.config import settings

def main():
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print("fastembed not installed. Install with: pip install fastembed")
        sys.exit(1)
        
    model_name = "BAAI/bge-small-en-v1.5"
    cache_dir = str(settings.data_dir / "models")
    print(f"Downloading model {model_name} to {cache_dir}...")
    # Instantiating the TextEmbedding model will automatically download and cache it
    TextEmbedding(model_name, cache_dir=cache_dir)
    print("Download complete.")

if __name__ == "__main__":
    main()
