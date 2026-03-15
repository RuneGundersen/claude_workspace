"""
2-D snowdrift model orchestrator.

Couples:
  - D2Q9 LBM wind solver  (core/lbm2d.LBM2D)
  - Lagrangian snow particles  (core/snow.SnowParticles2D)
  - Optional synthetic inlet turbulence  (core/turbulence.SyntheticTurbulence)

Ensemble averaging (n_ensemble runs) gives probabilistic drift statistics.

Output
------
  drift_mean[Nx] : mean snowdrift height (m)
  drift_std[Nx]  : std-dev across ensemble (m)
  u_star[Nx]     : mean friction velocity (m/s)
"""
from __future__ import annotations
import numpy as np
from config import SnowdriftConfig
from geometry import make_mask_2d, add_ground
from core.lbm2d import LBM2D
from core.snow  import SnowParticles2D
from core.turbulence import SyntheticTurbulence


class Model2D:
    """2-D snowdrift model.

    Parameters
    ----------
    cfg       : SnowdriftConfig
    use_turb  : add synthetic inlet turbulence  (default True)
    ensemble  : number of ensemble members  (overrides cfg.sim.n_ensemble if > 0)
    """

    def __init__(self,
                 cfg:      SnowdriftConfig,
                 use_turb: bool = True,
                 ensemble: int  = 0):
        self.cfg      = cfg
        dom, phys, sim, obs = cfg.domain, cfg.physics, cfg.sim, cfg.obstruction

        # Obstacle mask (with ground)
        mask2d   = make_mask_2d(dom, obs)
        self.solid = add_ground(mask2d)

        # LBM solver
        self.lbm  = LBM2D(dom, phys, sim, self.solid)

        # Turbulence generator
        self.turb = SyntheticTurbulence(dom, phys, sim) if use_turb else None

        self.n_ensemble = ensemble if ensemble > 0 else sim.n_ensemble
        self.snapshots: list[dict] = []

    # ------------------------------------------------------------------- run
    def spinup(self, verbose: bool = False):
        """LBM-only warm-up (no particles)."""
        n_steps = int(self.cfg.sim.t_spinup / self.lbm.dt)
        t = 0.0
        for _ in range(n_steps):
            u_in = (self.turb.inlet_velocity(t) if self.turb
                    else self.cfg.physics.log_profile(self.cfg.domain.z))
            self.lbm.step(u_in)
            t += self.lbm.dt
        if verbose:
            print(f"  Spin-up: {n_steps} steps, t={self.cfg.sim.t_spinup:.1f} s")

    def run_single(self, seed_offset: int = 0, verbose: bool = False) -> np.ndarray:
        """Run one ensemble member.  Returns drift[Nx]."""
        cfg  = self.cfg
        dom, phys, sim = cfg.domain, cfg.physics, cfg.sim
        dt_lbm  = self.lbm.dt
        dt_snow = sim.dt_snow

        rng = np.random.default_rng(sim.seed + seed_offset)
        snow = SnowParticles2D(dom, phys, sim, self.solid, rng=rng)

        n_lbm = int(sim.t_total / dt_lbm)
        snow_per_lbm = max(1, int(dt_lbm / dt_snow))
        dt_s = dt_lbm / snow_per_lbm
        t = 0.0
        t_after_spinup = 0.0

        for step_i in range(n_lbm):
            u_in = (self.turb.inlet_velocity(t) if self.turb
                    else phys.log_profile(dom.z))
            self.lbm.step(u_in)
            t += dt_lbm
            t_after_spinup += dt_lbm

            # Use inlet u* (ix=0) where Zou-He guarantees the log profile
            u_star = float(self.lbm.friction_velocity()[0])

            # Snow sub-steps
            for _ in range(snow_per_lbm):
                snow.step(self.lbm.ux, self.lbm.uz, u_star, dt_s,
                          self.lbm.interpolate_velocity)

            if verbose and step_i % max(1, n_lbm // 10) == 0:
                print(f"    step {step_i}/{n_lbm}  "
                      f"t={t_after_spinup:.2f}s  "
                      f"active={snow.n_active}  "
                      f"max_drift={snow.drift.max():.4f} m")

        return snow.drift.copy()

    def run(self, verbose: bool = True) -> dict:
        """Run full ensemble.

        Returns
        -------
        dict with keys: drift_mean, drift_std, drift_all, u_star, snapshots
        """
        self.spinup(verbose=verbose)

        drifts = []
        for i in range(self.n_ensemble):
            if verbose:
                print(f"  Ensemble {i+1}/{self.n_ensemble}")
            d = self.run_single(seed_offset=i, verbose=verbose and self.n_ensemble == 1)
            drifts.append(d)

        drifts = np.array(drifts)   # (n_ensemble, Nx)
        u_star = self.lbm.friction_velocity()

        result = {
            'drift_mean': drifts.mean(axis=0),
            'drift_std':  drifts.std(axis=0),
            'drift_all':  drifts,
            'u_star':     u_star,
            'snapshots':  self.snapshots,
        }
        if verbose:
            print(f"  Done. max mean drift = {result['drift_mean'].max():.4f} m")
        return result
