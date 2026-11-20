import argparse, os, sys, time
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True)
a = ap.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
(out / 'present.txt').write_text('here\n')
p = Path('stray.txt')
p.write_text('stale\n')
old = time.time() - 3600
os.utime(p, (old, old))
sys.exit(0)
