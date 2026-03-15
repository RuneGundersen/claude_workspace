"""
Lagrangian snow particle module — 3-D.

Mirrors SnowParticles2D from snow.py but tracks x, y, z positions and
uses trilinear interpolation via the LBM3D solver.
"""
from __future__ import annotations
import numpy as np
from config import DomainConfig, PhysicsConfig, SimConfig


class SnowParticles3D:
    """3-D Lagrangian snow particles.

    State arrays (length N_max):
      x, y, z   : position (m)
      vx, vy, vz: velocity (m/s)
    """

    def __init__(self,
                 dom:   DomainConfig,
                 phys:  PhysicsConfig,
                 sim:   SimConfig,
                 solid: np.ndarray,
                 rng:   np.random.Generator | None = None):
        self.dom   = dom
        self.phys  = phys
        self.sim   = sim
        self.solid = solid   # (Nz, Ny, Nx) bool

        self.rng   = rng or np.random.default_rng(sim.seed)
        N = sim.n_particles

        self.x  = np.zeros(N); self.y  = np.zeros(N); self.z  = np.zeros(N)
        self.vx = np.zeros(N); self.vy = np.zeros(N); self.vz = np.zeros(N)
        self.active = np.zeros(N, dtype=bool)
        self._N = N

        # 2-D drift map (Ny, Nx) — height of deposited snow (m)
        self.drift     = np.zeros((dom.Ny, dom.Nx))
        self.dep_count = np.zeros((dom.Ny, dom.Nx), dtype=np.int64)

    # ----------------------------------------------------------------- inject
    def inject(self, u_star: float):
        if u_star <= self.phys.u_star_t:
            return
        n_free = int(np.sum(~self.active))
        if n_free == 0:
            return
        n_inject = min(n_free, max(1, int(n_free * 0.1)))
        z_levels = self.dom.z
        n_z      = self.phys.snow_concentration(z_levels, u_star)
        prob     = n_z / (n_z.sum() + 1e-30)
        slots    = np.where(~self.active)[0][:n_inject]
        n_inject = len(slots)
        if n_inject == 0:
            return

        iz_idx   = self.rng.choice(len(z_levels), size=n_inject, p=prob)
        z_inject = z_levels[iz_idx] + self.rng.uniform(-0.5, 0.5, n_inject) * self.dom.dx

        self.x[slots]  = self.dom.dx * 0.5 + self.rng.uniform(0, 0.5*self.dom.dx, n_inject)
        self.y[slots]  = self.rng.uniform(0, self.dom.Ly, n_inject)
        self.z[slots]  = np.clip(z_inject, self.dom.dx*0.5, self.dom.Lz - self.dom.dx)
        self.vx[slots] = self.phys.log_profile(self.z[slots]) * (1.0 + self.rng.normal(0, 0.1, n_inject))
        self.vy[slots] = self.rng.normal(0, 0.05, n_inject)
        self.vz[slots] = self.rng.normal(0, self.phys.w_fall, n_inject)
        self.active[slots] = True

    # ------------------------------------------------------------------ step
    def step(self, u_star: float, dt: float, interp_fn):
        """Advance all active particles by dt seconds.

        interp_fn : callable(x, y, z) → (ux, uy, uz)
        """
        self.inject(u_star)

        if not np.any(self.active):
            return
        sel = self.active

        u_f, v_f, w_f = interp_fn(self.x[sel], self.y[sel], self.z[sel])

        dvx = u_f - self.vx[sel]
        dvy = v_f - self.vy[sel]
        dvz = w_f - self.vz[sel]
        V_R = np.sqrt(dvx**2 + dvy**2 + dvz**2) + 1e-12
        Re_p = V_R * self.phys.d_snow / self.phys.nu_air
        f_sn = 1.0 + 0.15 * Re_p**0.687

        tau_p_inv = f_sn / self.phys.tau_p
        ax = tau_p_inv * dvx
        ay = tau_p_inv * dvy
        az = tau_p_inv * dvz - self.phys.g

        self.vx[sel] += ax * dt
        self.vy[sel] += ay * dt
        self.vz[sel] += az * dt
        self.x[sel]  += self.vx[sel] * dt
        self.y[sel]  += self.vy[sel] * dt
        self.z[sel]  += self.vz[sel] * dt

        # Periodic y
        self.y[sel] = self.y[sel] % self.dom.Ly

        self._check_boundaries(sel)
        self.inject(u_star)

    def _check_boundaries(self, sel: np.ndarray):
        idx = np.where(sel)[0]
        out = (self.x[idx] >= self.dom.Lx) | (self.z[idx] >= self.dom.Lz)
        self.active[idx[out]] = False
        back = self.x[idx] < 0
        self.active[idx[back]] = False

        alive = ~out & ~back
        ia = idx[alive]
        if ia.size == 0:
            return

        ix_p = np.clip((self.x[ia] / self.dom.dx).astype(int), 0, self.dom.Nx-1)
        iy_p = np.clip((self.y[ia] / self.dom.dx).astype(int), 0, self.dom.Ny-1)
        z_gnd = self.drift[iy_p, ix_p] + self.dom.dx

        deposited = (self.z[ia] <= z_gnd) & (self.vz[ia] < 0)
        for k, flag in zip(ia, deposited):
            if flag:
                ixk = np.clip(int(self.x[k] / self.dom.dx), 0, self.dom.Nx-1)
                iyk = np.clip(int(self.y[k] / self.dom.dx), 0, self.dom.Ny-1)
                vol = (np.pi/6.0) * self.phys.d_snow**3
                self.drift[iyk, ixk] += vol / (self.dom.dx**2) * self.phys.alpha
                self.dep_count[iyk, ixk] += 1
                self.active[k] = False

        iz_p = np.clip((self.z[ia] / self.dom.dx).astype(int), 0, self.dom.Nz-1)
        in_solid = self.solid[iz_p, iy_p, ix_p]
        self.active[ia[in_solid]] = False

    @property
    def n_active(self) -> int:
        return int(self.active.sum())

    def reset_drift(self):
        self.drift[:]     = 0.0
        self.dep_count[:] = 0
        self.active[:]    = False
