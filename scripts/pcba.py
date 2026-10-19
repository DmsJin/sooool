"""CPU-friendly PCBA MuJoCo environment entrypoint; no model calls by default."""
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE','1')
os.environ.setdefault('LP_NUM_THREADS','2')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environments/pcba'))
if len(sys.argv)>1 and sys.argv[1]=='clock-preflight':
    from pcba_gym.process_clock import main
elif len(sys.argv)>1 and sys.argv[1]=='export':
    from pcba_gym.replay_export import main
elif len(sys.argv)>1 and sys.argv[1]=='showcase':
    from pcba_gym.showcase import main
    sys.argv.pop(1)
elif len(sys.argv)>1 and sys.argv[1]=='loop-demo':
    from pcba_gym.loop_demo import main
elif len(sys.argv)>1 and sys.argv[1]=='latency':
    from pcba_gym.latency import main
elif len(sys.argv)>1 and sys.argv[1]=='simulate':
    from pcba_gym.simulate import main
elif len(sys.argv)>1 and sys.argv[1]=='pipeline':
    from pcba_gym.pipeline import main
elif len(sys.argv)>1 and sys.argv[1] in ('eval','report'):
    from pcba_gym.runner import main
else:
    from pcba_gym.demo import main

if __name__=='__main__':main()
