"""Atomic stage grids, configuration counts and honest CPU/GPU accounting."""
from contextlib import contextmanager
from datetime import datetime,timezone
import math,os
from pathlib import Path
from src import config
from src.delivery import atomic_json,read_json,canonical_sha
from src.bonus.protocol import ROOT


class BudgetLedger:
    def __init__(self,path=None,budget=None):
        self.path=Path(path or config.CACHE_DIR/'bonus_v2/budget-ledger.json')
        self.budget=budget or read_json(ROOT/'budgets.json')
        if sum(self.budget['max_configurations_by_stage'].values())!=self.budget['max_total_configurations']:
            raise ValueError('Stage and total budgets disagree')

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        lock=self.path.with_suffix('.lock')
        try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError: raise RuntimeError('Budget ledger is busy; stale locks require inspection') from None
        try:
            os.close(fd)
            if self.path.exists():
                state=read_json(self.path)
                if state['budget_sha256']!=canonical_sha(self.budget): raise ValueError('Budget changed after registration')
            else:
                state={'version':'bonus-budget-ledger-v1','budget_sha256':canonical_sha(self.budget),
                    'grids':{},'configurations':{},'jobs':{},'cpu_seconds':0.,'gpu_job_wall_seconds':0.,'over_budget':False}
            yield state
            atomic_json(self.path,state)
        finally: lock.unlink()

    def seal_grid(self,stage,configurations):
        if stage not in self.budget['max_configurations_by_stage'] or not configurations:
            raise ValueError('Unknown stage or empty grid')
        if len(configurations)>self.budget['max_configurations_by_stage'][stage]: raise ValueError('Grid exceeds stage budget')
        rows={str(c['id']):canonical_sha(c) for c in configurations}
        if len(rows)!=len(configurations): raise ValueError('Duplicate configuration IDs')
        with self.locked() as state:
            if stage in state['grids']:
                if state['grids'][stage]['configurations']!=rows: raise ValueError('Stage grid is already frozen')
            else:
                state['grids'][stage]={'configurations':rows,'sealed_utc':datetime.now(timezone.utc).isoformat()}
        return canonical_sha(rows)

    def register(self,stage,configuration):
        ident=str(configuration['id']); signature=canonical_sha(configuration)
        with self.locked() as state:
            self._check_cost(state,0.,0.)
            grid=state['grids'].get(stage)
            if grid is None or grid['configurations'].get(ident)!=signature:
                raise PermissionError('Configuration must match a previously sealed stage grid')
            key=stage+':'+ident
            if key in state['configurations']:
                if state['configurations'][key]!=signature: raise ValueError('Configuration identity changed')
            else:
                if len(state['configurations'])>=self.budget['max_total_configurations']: raise RuntimeError('Configuration budget exhausted')
                count=sum(k.startswith(stage+':') for k in state['configurations'])
                if count>=self.budget['max_configurations_by_stage'][stage]: raise RuntimeError('Stage configuration budget exhausted')
                state['configurations'][key]=signature
        return key

    def _check_cost(self,state,cpu,gpu):
        if state['over_budget'] or state['cpu_seconds']+cpu>self.budget['max_cpu_seconds'] or state['gpu_job_wall_seconds']+gpu>self.budget['max_gpu_job_wall_seconds']:
            raise RuntimeError('Compute budget exhausted; do not start another job')

    def can_start(self,estimated_cpu_seconds=0.,estimated_gpu_job_seconds=0.):
        values=[estimated_cpu_seconds,estimated_gpu_job_seconds]
        if any(not math.isfinite(v) or v<0 for v in values): raise ValueError('Invalid estimated cost')
        with self.locked() as state: self._check_cost(state,*values)

    def record_cost(self,job_id,*,cpu_seconds,gpu_job_wall_seconds=0.):
        cost={'cpu_seconds':cpu_seconds,'gpu_job_wall_seconds':gpu_job_wall_seconds}
        if any(not math.isfinite(v) or v<0 for v in cost.values()): raise ValueError('Invalid actual cost')
        exceeded=False
        with self.locked() as state:
            if job_id in state['jobs']:
                if state['jobs'][job_id]!=cost: raise ValueError('Cost already recorded with different values')
                return
            state['jobs'][job_id]=cost
            for key,value in cost.items(): state[key]+=value
            exceeded=state['cpu_seconds']>self.budget['max_cpu_seconds'] or state['gpu_job_wall_seconds']>self.budget['max_gpu_job_wall_seconds']
            state['over_budget']|=exceeded
        if exceeded: raise RuntimeError('Actual overrun recorded; all subsequent jobs are blocked')
