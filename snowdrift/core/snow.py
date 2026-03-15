"""
Lagrangian snow particle module — 2-D and 3-D.

Follows Nishimura & Hunt (2000) and Tanji et al. (2021) §2.3.
Equation of motion:
  du_p/dt = f_drag(u - u_p) - g ẑ
Drag uses the Schiller-Naumann correction to Stokes drag.
"""
from __future__ import annotations
import numpy as np
from config import DomainConfig, PhysicsConfig, SimConfig


class SnowParticles2D:
    """2-D Lagrangian snow particles.

    State arrays (length N_max, active[:] selects live particles):
      x, z  : position (m)
      vx, vz: velocity (m/s)
    """

    def __init__(self,
                 dom:  DomainConfig,
                 phys: PhysicsConfig,
                 sim:  SimConfig,
                 solid: np.ndarray,
                 rng:  np.random.Generator | None = None):
        self.dom   = dom
        self.phys  = phys
        self.sim   = sim
        self.solid = solid          # (Nz, Nx) bool

        self.rng   = rng or np.random.default_rng(sim.seed)
        N          = sim.n_particles

        self.x     = np.zeros(N)
        self.z     = np.zeros(N)
        self.vx    = np.zeros(N)
        self.vz    = np.zeros(N)
        self.active= np.zeros(N, dtype=bool)
        self._N    = N

        # Snowdrift accumulation: height of deposited snow at each x-cell (m)
        self.drift = np.zeros(dom.Nx)

        # Deposition count per x-cell (for statistics)
        self.dep_count = np.zeros(dom.Nx, dtype=np.int64)

    # ----------------------------------------------------------------- inject
    def inject(self, u_star: float):
        """Inject new particles at the inlet (x ≈ 0) if u* > u*_t.

        Injection follows the concentration profile n(z) of Eq.(24).
        """
        if u_star <= self.phys.u_star_t:
            return

        n_free = int(np.sum(~self.active))
        if n_free == 0:
            return

        # How many to inject this call (proportional to flux)
        n_inject = min(n_free, max(1, int(n_free * 0.1)))
        z_levels = self.dom.z
        n_z      = self.phys.snow_concentration(z_levels, u_star)  # g/m³
        # Probability weight per z-level
        prob     = n_z / (n_z.sum() + 1e-30)

        slots    = np.where(~self.active)[0][:n_inject]
        n_inject = len(slots)
        if n_inject == 0:
            return

        # Sample z from concentration profile
        iz_idx   = self.rng.choice(len(z_levels), size=n_inject, p=prob)
        z_inject = z_levels[iz_idx] + self.rng.uniform(-0.5, 0.5, n_inject) * self.dom.dx

        self.x[slots]  = self.dom.dx * 0.5 + self.rng.uniform(0, 0.5*self.dom.dx, n_inject)
        # Inject from first fluid cell (dom.z[1] = 1.5*dx) to avoid immediate deposition
        z_min = self.dom.z[1] if len(self.dom.z) > 1 else self.dom.dx * 1.5
        self.z[slots]  = np.clip(z_inject, z_min, self.dom.Lz - self.dom.dx)
        # Initial velocity ≈ local wind (approximate with log profile)
        self.vx[slots] = self.phys.log_profile(self.z[slots]) * (
            1.0 + self.rng.normal(0, 0.1, n_inject))
        # Initial vz: zero mean + turbulent fluctuation.
        # (particles enter from inlet in suspension; drag + gravity do the rest)
        self.vz[slots] = self.rng.normal(0, self.phys.w_fall, n_inject)
        self.active[slots] = True

    # ----------------------------------------------------------------- step
    def step(self,
             ux_field: np.ndarray,
             uz_field: np.ndarray,
             u_star:   float,
             dt:       float,
             interp_fn):
        """Advance all active particles by dt seconds.

        Parameters
        ----------
        ux_field, uz_field : (Nz, Nx) wind velocity arrays [m/s]
        u_star  : surface friction velocity [m/s]
        dt      : timestep [s]
        interp_fn : callable(x, z) → (ux, uz) — bilinear interpolation
        """
        # Always try to inject (even if no active particles yet)
        self.inject(u_star)

        if not np.any(self.active):
            return

        sel = self.active

        # --- Fluid velocity at particle positions (bilinear interp) ----
        u_f, w_f = interp_fn(self.x[sel], self.z[sel])

        # --- Schiller-Naumann drag ----
        dvx  = u_f - self.vx[sel]
        dvz  = w_f - self.vz[sel]
        V_R  = np.sqrt(dvx**2 + dvz**2) + 1e-12
        Re_p = V_R * self.phys.d_snow / self.phys.nu_air
        f_sn = 1.0 + 0.15 * Re_p**0.687          # Schiller-Naumann correction

        # Drag acceleration: a = f_SN / tau_p * (u_fluid - v_p)
        tau_p_inv = f_sn / self.phys.tau_p
        ax = tau_p_inv * dvx
        az = tau_p_inv * dvz - self.phys.g         # gravity

        # --- Euler integration ----
        self.vx[sel] += ax * dt
        self.vz[sel] += az * dt
        self.x[sel]  += self.vx[sel] * dt
        self.z[sel]  += self.vz[sel] * dt

        # --- Boundary checks ----
        self._check_boundaries(sel)

        # --- Inject new particles ----
        self.inject(u_star)

    def _check_boundaries(self, sel: np.ndarray):
        """Handle deposition, removal, and domain exits."""
        idx = np.where(sel)[0]

        # Outlet / top → remove
        out = (self.x[idx] >= self.dom.Lx) | (self.z[idx] >= self.dom.Lz)
        self.active[idx[out]] = False

        # Inlet wrap-around (particles going backward)
        back = self.x[idx] < 0
        self.active[idx[back]] = False

        # Ground / deposition (z ≤ drift height at that x)
        alive = ~out & ~back
        ia    = idx[alive]
        if ia.size == 0:
            return

        # Map to x-cell
        ix_p  = np.clip((self.x[ia] / self.dom.dx).astype(int), 0, self.dom.Nx-1)
        # Deposition threshold = top of ground cell (iz=0 spans 0..dx).
        # Using 0.5*dx would miss particles that the solid check (iz=0) removes first.
        z_gnd = self.drift[ix_p] + self.dom.dx

        # Deposit only when moving downward (vz < 0) and at/below surface
        deposited = (self.z[ia] <= z_gnd) & (self.vz[ia] < 0)
        for k, flag in zip(ia, deposited):
            if flag:
                ix_k = np.clip(int(self.x[k] / self.dom.dx), 0, self.dom.Nx - 1)
                # Accumulate drift height (volume of one particle / cell area)
                vol  = (np.pi/6.0) * self.phys.d_snow**3
                self.drift[ix_k] += vol / (self.dom.dx**2) * self.phys.alpha
                self.dep_count[ix_k] += 1
                self.active[k]  = False

        # Solid obstacle collision → remove
        iz_p = np.clip((self.z[ia] / self.dom.dx).astype(int), 0, self.dom.Nz-1)
        ix_p = np.clip((self.x[ia] / self.dom.dx).astype(int), 0, self.dom.Nx-1)
        in_solid = self.solid[iz_p, ix_p]
        self.active[ia[in_solid]] = False

    # ----------------------------------------------------------------- stats
    @property
    def n_active(self) -> int:
        return int(self.active.sum())

    def reset_drift(self):
        self.drift[:]     = 0.0
        self.dep_count[:] = 0
        self.active[:]    = False
