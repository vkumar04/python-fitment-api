#!/usr/bin/env python
"""Script to load fitment data into ChromaDB."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.rag_service import RAGService


def main():
    csv_path = Path(__file__).parent.parent / "datafiles" / "Fitment-data-master.csv"

    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)

    print(f"Loading data from {csv_path}...")
    service = RAGService()
    count = service.load_csv_data(str(csv_path))
    print(f"Successfully loaded {count} fitment records into ChromaDB")


if __name__ == "__main__":
    main()
