"""Launch this source release with the existing environment and workspace."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.run_paper_release import workspace_path

if __name__=='__main__':
    from arcticdem_workbench.windows_runtime import prepare_runtime
    import json
    print('Startup:',json.dumps(prepare_runtime(),ensure_ascii=False),flush=True)
    from arcticdem_workbench.gui import launch
    workspace, reason=workspace_path(sys.argv[1] if len(sys.argv)>1 else None)
    print('Workspace:',workspace,'('+reason+')',flush=True)
    raise SystemExit(launch(workspace))
