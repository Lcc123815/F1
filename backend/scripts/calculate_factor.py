import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.factor_service import run_pe_factor_pipeline

if __name__ == "__main__":
    run_pe_factor_pipeline()