"""Reproduce the frozen MYA submission with the supplied tactical tracking."""
import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    os.environ[key]='1'
from src.delivery import main
if __name__=='__main__':
    raise SystemExit(main())
