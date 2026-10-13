"""Windows-friendly validation entry point; reuses the active environment."""
from pathlib import Path
import argparse
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from arcticdem_workbench.validation_suite import run_benchmark,new_output
from arcticdem_workbench.diagnostics import bundle

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',default=str(ROOT/'work'))
    parser.add_argument('--profile',choices=('quick','extended'),default='quick')
    args=parser.parse_args();output=new_output(args.workspace)
    code=0
    try:
        result=run_benchmark(output,args.profile)
        print('REPORT:',result['html'])
        if result['summary']['unexpected_checks']:code=2
    except Exception:
        traceback.print_exc();code=1
    if output.is_dir():
        try:
            print('UPLOAD ZIP:',bundle(output))
        except Exception:
            traceback.print_exc();code=1
    return code

if __name__=='__main__':raise SystemExit(main())
