from pathlib import Path
import sys,runpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from arcticdem_workbench.windows_runtime import prepare_runtime
prepare_runtime()
script=ROOT/'research/rs_reproduction/reproduce_rs.py'
sys.path.insert(0,str(script.parent))
runpy.run_path(str(script),run_name='__main__')
