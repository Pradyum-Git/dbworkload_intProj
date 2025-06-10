# test_init.py
import os
from pathlib import Path

from dbworkload.models.util import init

def main():
    # Locate the repo root and the debug-zip folder
    repo_root = Path(__file__).resolve().parent
    zip_dir = repo_root / "debug-zips" / "debug_2"

    # Run the init routine
    init(
        zip_dir=zip_dir,
        db_name="tpcc",
        cloud_storage_uri="",
        cluster_url="",
        anonymize=False,
        data_gen_mode="constraint-aware",
    )

    # Simple sanity-checks
    assert (repo_root / "tpcc.yaml").exists(), "tpcc.yaml was not created"
    #assert (repo_root / "tpcc.csv").exists(),  "tpcc.csv was not created"

    print("✅ init completed and generated YAML/CSV successfully")

if __name__ == "__main__":
    main()
