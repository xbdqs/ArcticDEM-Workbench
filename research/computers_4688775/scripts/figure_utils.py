"""Local, working-directory-independent figure helpers."""
from pathlib import Path
import shutil, subprocess, sys, hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'regenerated/figures'
OUT.mkdir(exist_ok=True,parents=True)
def run_source(script,*args):
    subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],cwd=ROOT,check=True)
def rename_generated(stem,number,source_folder=None):
    src=source_folder or OUT
    for ext in ('png','pdf','svg'):
        p=src/f'{stem}.{ext}'
        if p.is_file():shutil.copyfile(p,OUT/f'Figure_{number:02d}.{ext}')
def copy_gui(number):
    original=ROOT/f'inputs/gui_original/Figure_{number:02d}_original_author_screen.png'
    target=OUT/f'Figure_{number:02d}.png';shutil.copyfile(original,target)
    assert hashlib.sha256(original.read_bytes()).digest()==hashlib.sha256(target.read_bytes()).digest()
    print(f'Figure {number}: existing author-captured Qt screenshot copied byte-identically (not numerically redrawn)')
