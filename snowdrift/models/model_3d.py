"""
3-D snowdrift model orchestrator.

Couples:
  - D3Q19 LBM wind solver  (core/lbm3d.LBM3D)
  - Lagrangian 3-D snow particles  (core/snow3d.SnowParticles3D)
  - Optional synthetic inlet turbulence  (core/turbulence.SyntheticTurbulence)

Memory note: a 3-D run with dx=0.05 m on a 12×4×4 m domain needs
  f[19, 80, 80, 240] = ~3 GB (float64).  Use dx ≥ 0.1 m for development.
"""
from __future__ import annotations
import numpy as np
from config import SnowdriftConfig
from geometry import make_mask_3d
from core.lbm3d import LBM3D
from core.snow3d import SnowParticles3D
from core.turbulence import SyntheticTurbulence


class Model3D:
    """3-D snowdrift model.

    Parameters
    ----------
    cfg       : SnowdriftConfig
    use_turb  : add synthetic inlet turbulence
    ensemble  : number of ensemble members (0 → use cfg.sim.n_ensemble)
    """

    def __init__(self,
                 cfg:      SnowdriftConfig,
                 use_turb: bool = True,
                 ensemble: int  = 0):
        self.cfg = cfg
        dom, phys, sim, obs = cfg.domain, cfg.physics, cfg.sim, cfg.obstruction

        # Obstacle mask  (Nz, Ny, Nx)
        mask3d = make_mask_3d(dom, obs)
        # Ground layer (z=0) always solid
        mask3d[0, :, :] = True
        self.solid = mask3d

        # LBM solver
        self.lbm  = LBM3D(dom, phys, sim, self.solid)

        # Turbulence: 2-D z-profile fluctuation broadcast over y
        self.turb = SyntheticTurbulence(dom, phys, sim) if use_turb else None

        self.n_ensemble = ensemble if ensemble > 0 else sim.n_ensemble

    # ----------------------------------------------------------------- run
    def spinup(self, verbose: bool = False):
        n_steps = int(self.cfg.sim.t_spinup / self.lbm.dt)
        t = 0.0
        dom, phys = self.cfg.domain, self.cfg.physics
        for _ in range(n_steps):
            u_mean = phys.log_profile(dom.z)   # (Nz,)
            if self.turb:
                u_mean = u_mean + self.turb.fluctuation(t)
            # Broadcast over y:  (Nz, Ny)
            u_in = u_mean[:, np.newaxis] * np.ones((dom.Nz, dom.Ny))
            self.lbm.step(u_in)
            t += self.lbm.dt
        if verbose:
            print(f"  Spin-up: {n_steps} steps, t={self.cfg.sim.t_spinup:.1f} s")

    def run_single(self, seed_offset: int = 0, verbose: bool = False) -> np.ndarray:
        """Run one ensemble member.  Returns drift[Ny, Nx]."""
        cfg = self.cfg
        dom, phys, sim = cfg.domain, cfg.physics, cfg.sim
        dt_lbm  = self.lbm.dt
        dt_snow = sim.dt_snow

        rng  = np.random.default_rng(sim.seed + seed_offset)
        snow = SnowParticles3D(dom, phys, sim, self.solid, rng=rng)

        n_lbm        = int(sim.t_total / dt_lbm)
        snow_per_lbm = max(1, int(dt_lbm / dt_snow))
        dt_s = dt_lbm / snow_per_lbm
        t    = 0.0

        for step_i in range(n_lbm):
            u_mean = phys.log_profile(dom.z)
            if self.turb:
                u_mean = u_mean + self.turb.fluctuation(t)
            u_in = u_mean[:, np.newaxis] * np.ones((dom.Nz, dom.Ny))
            self.lbm.step(u_in)
            t += dt_lbm

            u_star = float(np.mean(self.lbm.friction_velocity()[:, 0]))

            for _ in range(snow_per_lbm):
                snow.step(u_star, dt_s, self.lbm.interpolate_velocity)

            if verbose and step_i % max(1, n_lbm // 10) == 0:
                print(f"    step {step_i}/{n_lbm}  t={t:.2f}s  "
                      f"active={snow.n_active}  "
                      f"max_drift={snow.drift.max():.4f} m")

        return snow.drift.copy()

    def run(self, verbose: bool = True) -> dict:
        """Run full ensemble.

        Returns
        -------
        dict with keys: drift_mean (Ny, Nx), drift_std, drift_all, u_star (Ny, Nx)
        """
        self.spinup(verbose=verbose)
        drifts = []
        for i in range(self.n_ensemble):
            if verbose:
                print(f"  Ensemble {i+1}/{self.n_ensemble}")
            d = self.run_single(seed_offset=i,
                                verbose=verbose and self.n_ensemble == 1)
            drifts.append(d)

        drifts = np.array(drifts)   # (n_ensemble, Ny, Nx)
        u_star = self.lbm.friction_velocity()

        result = {
            'drift_mean': drifts.mean(axis=0),
            'drift_std':  drifts.std(axis=0),
            'drift_all':  drifts,
            'u_star':     u_star,
        }
        if verbose:
            print(f"  Done. max mean drift = {result['drift_mean'].max():.4f} m")
        return result
