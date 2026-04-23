import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"

sys.path.insert(0, str(SRC_DIR))

from clean_project.pipeline import run_pipeline
import clean_project.config.settings as config

print(SRC_DIR)
if __name__ == "__main__":
    run_pipeline()
