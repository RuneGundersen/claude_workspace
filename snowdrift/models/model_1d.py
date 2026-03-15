"""
1-D snowdrift model orchestrator.

Uses the D1Q3 LBM solver (lbm1d.LBM1D) for depth-averaged streamwise wind,
and a simplified 1-D snow transport balance (no explicit particle tracking).

Snow mass balance (1-D, steady-state approximation):
  dq/dx = E(x) − D(x)
where q = snow flux (kg m⁻¹ s⁻¹), E = erosion, D = deposition.

Useful for quick parameter sweeps, threshold analysis, and validation.

Output
------
  drift[Nx] : snowdrift height profile (m)  after t_total seconds
  u[Nx]     : mean streamwise velocity (m/s)
  u_star[Nx]: friction velocity (m/s)
"""
from __future__ import annotations
import numpy as np
from config import SnowdriftConfig
from geometry import make_mask_1d
from core.lbm1d import LBM1D


class Model1D:
    """1-D snowdrift model.

    Parameters
    ----------
    cfg : SnowdriftConfig
    """

    def __init__(self, cfg: SnowdriftConfig):
        self.cfg = cfg
        dom, phys, sim, obs = cfg.domain, cfg.physics, cfg.sim, cfg.obstruction

        self.mask = make_mask_1d(dom, obs)
        self.lbm  = LBM1D(dom, phys, sim, obs)

        self.t        = 0.0
        self.t_spinup = sim.t_spinup
        self.t_total  = sim.t_total

        # Snow transport state
        self.q        = np.zeros(dom.Nx)   # snow flux (kg m⁻¹ s⁻¹)
        self.drift    = np.zeros(dom.Nx)   # drift height (m)
        self.snapshots: list[dict] = []

    # ------------------------------------------------------------------ run
    def spinup(self, verbose: bool = False):
        """Run LBM-only warm-up until t_spinup."""
        n_steps = int(self.t_spinup / self.lbm.dt)
        for _ in range(n_steps):
            self.lbm.step()
        if verbose:
            print(f"  Spin-up complete: {n_steps} LBM steps, t={self.t_spinup:.1f} s")

    def run(self, verbose: bool = True) -> dict:
        """Run the full simulation.

        Returns
        -------
        result dict with keys: drift, u, u_star, t_snapshots, drift_snapshots
        """
        self.spinup(verbose=verbose)

        dom   = self.cfg.domain
        phys  = self.cfg.physics
        sim   = self.cfg.sim
        dt_lbm = self.lbm.dt
        dt_snow = sim.dt_snow

        n_lbm  = int(self.t_total / dt_lbm)
        t_out  = sim.output_dt
        next_out = t_out

        # Per-LBM-step snow advancement
        snow_steps_per_lbm = max(1, int(dt_lbm / dt_snow))
        dt_s_actual        = dt_lbm / snow_steps_per_lbm

        if verbose:
            print(f"  Running {n_lbm} LBM steps  "
                  f"({snow_steps_per_lbm} snow sub-steps each)...")

        for step_i in range(n_lbm):
            self.lbm.step()
            self.t += dt_lbm

            # Update snow flux using LBM friction velocity
            u_star = self.lbm.friction_velocity()  # (Nx,)
            self._advance_snow(u_star, dt_s_actual * snow_steps_per_lbm)

            if self.t >= next_out:
                self.snapshots.append({
                    't':     self.t,
                    'drift': self.drift.copy(),
                    'u':     self.lbm.u.copy(),
                    'u_star': u_star.copy(),
                })
                next_out += t_out
                if verbose:
                    print(f"    t={self.t:.1f} s  "
                          f"max_drift={self.drift.max():.4f} m  "
                          f"max_u*={u_star.max():.3f} m/s")

        return {
            'drift':   self.drift,
            'u':       self.lbm.u,
            'u_star':  self.lbm.friction_velocity(),
            'snapshots': self.snapshots,
        }

    # ------------------------------------------------------- snow transport
    def _advance_snow(self, u_star: np.ndarray, dt: float):
        """Update 1-D snow flux and drift height.

        Simplified steady-state flux model:
          q_sat = alpha * max(0, u* - u*_t)^3   (Bagnold saltation flux)
          dq/dx = (q_sat − q) / l_r              (relaxation to saturation)
          ddrift/dt = deposition_rate
        """
        phys   = self.cfg.physics
        dom    = self.cfg.domain
        alpha_b = 1.5e-3    # Bagnold-like coefficient (kg m⁻¹ s⁻¹) / (m/s)^3
        l_r    = 0.5        # relaxation length (m)

        # Saturation flux
        excess   = np.maximum(u_star - phys.u_star_t, 0.0)
        q_sat    = alpha_b * excess**3

        # Flux relaxation (upwind Euler in x)
        dq_dx    = (q_sat - self.q) / l_r
        self.q  += dq_dx * dt

        # Where q decreases (deposition), add to drift
        dq       = dq_dx * dt
        deposit  = np.where(dq < 0, -dq, 0.0)   # kg m⁻² per step
        # Convert to height: assume snow density 300 kg/m³
        rho_dep  = 300.0
        self.drift += deposit / rho_dep

        # Clamp negative flux
        self.q = np.maximum(self.q, 0.0)
