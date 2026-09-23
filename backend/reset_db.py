import sys
from app.db import SessionLocal, Base, engine
from app.ingestion.load_demo_case import load_demo_data

def run():
    try:
        Base.metadata.create_all(bind=engine)
        stats = load_demo_data()
        with open("reset_out.txt", "w") as f:
            f.write(f"Load OK, stats: {stats}")
    except Exception as e:
        with open("reset_out.txt", "w") as f:
            f.write(f"ERROR: {e}")

if __name__ == "__main__":
    run()
