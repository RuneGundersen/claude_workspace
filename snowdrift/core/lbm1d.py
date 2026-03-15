"""
D1Q3 Lattice Boltzmann solver for the 1-D snowdrift model.

The 1-D model treats only the streamwise direction.  The vertical dimension
is collapsed into a depth-averaged or column-integrated description.

D1Q3 velocity set:
  q=0 : rest       (e=0,  w=2/3)
  q=1 : right      (e=+1, w=1/6)
  q=2 : left       (e=−1, w=1/6)

BGK collision with constant τ.
Boundary conditions:
  inlet  (x=0)   : prescribed velocity (equilibrium injection)
  outlet (x=Nx-1): Neumann (copy from neighbour)
  fence region   : reduced momentum (porosity / blockage factor)
"""
from __future__ import annotations
import numpy as np
from config import DomainConfig, PhysicsConfig, SimConfig, ObstructionConfig


# ---------------------------------------------------------------------------
# D1Q3 constants
# ---------------------------------------------------------------------------
Q   = 3
E1D = np.array([0, 1, -1], dtype=np.int64)   # velocity directions
W1D = np.array([2/3, 1/6, 1/6])
OPP1D = np.array([0, 2, 1], dtype=np.int64)  # opposite indices
CS2 = 1.0 / 3.0


class LBM1D:
    """D1Q3 BGK solver for 1-D snowdrift.

    The "velocity" here is depth-averaged (or surface-layer) mean wind speed
    in the streamwise direction.

    Parameters
    ----------
    dom  : DomainConfig
    phys : PhysicsConfig
    sim  : SimConfig
    obs  : ObstructionConfig  (used for blockage / porosity)
    """

    def __init__(self,
                 dom:  DomainConfig,
                 phys: PhysicsConfig,
                 sim:  SimConfig,
                 obs:  ObstructionConfig):
        self.dom  = dom
        self.phys = phys
        self.sim  = sim
        self.obs  = obs

        Nx = dom.Nx
        self.Nx = Nx

        # Unit conversion
        self.dt     = sim.lbm_dt(dom.dx, phys.U_ref)
        self.tau    = sim.lbm_tau(dom.dx, self.dt, phys.nu_air)
        sim.validate_lbm(dom.dx, self.dt, phys.nu_air)
        self._scale = self.dt / dom.dx

        # Reference inlet speed (depth-averaged log profile approximation)
        z_avg        = 0.5 * dom.Lz
        self.u_ref   = phys.log_profile(np.array([z_avg]))[0]

        # Distribution functions f[Q, Nx]
        self.f  = np.zeros((Q, Nx))
        self._init_f()

        # Macroscopic
        self.u   = np.zeros(Nx)   # physical velocity (m/s)
        self.rho = np.ones(Nx)    # lattice density
        self._compute_macro()

        # Fence blockage mask (0 = free, 1 = full blockage)
        self._blockage = self._build_blockage()

        # 1-D drift accumulation (height in m at each x-cell)
        self.drift = np.zeros(Nx)

    # ------------------------------------------------------------------ init
    def _init_f(self):
        u_l = self.u_ref * self._scale
        for ix in range(self.Nx):
            self.f[:, ix] = self._feq_scalar(1.0, u_l)

    def _feq_scalar(self, rho: float, u: float) -> np.ndarray:
        """Equilibrium distribution for a single node."""
        return W1D * rho * (1.0 + E1D * u / CS2
                            + (E1D * u)**2 / (2 * CS2**2)
                            - u**2 / (2 * CS2))

    def _feq(self, rho: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Vectorised equilibrium (Q, Nx)."""
        feq = np.empty((Q, self.Nx))
        for q in range(Q):
            feq[q] = W1D[q] * rho * (1.0 + E1D[q]*u/CS2
                                      + (E1D[q]*u)**2/(2*CS2**2)
                                      - u**2/(2*CS2))
        return feq

    # --------------------------------------------------------------- blockage
    def _build_blockage(self) -> np.ndarray:
        """Return per-cell blockage factor in [0,1]."""
        b   = np.zeros(self.Nx)
        obs = self.obs
        ix0 = int(round(obs.x_pos / self.dom.dx))
        ix1 = max(ix0 + 1, int(round((obs.x_pos + obs.thickness) / self.dom.dx)))
        ix0 = np.clip(ix0, 0, self.Nx - 1)
        ix1 = np.clip(ix1, 1, self.Nx)
        # Effective blockage: (1 − porosity) · H_eff / Lz
        block_factor = (1.0 - obs.porosity) * obs.effective_height / self.dom.Lz
        b[ix0:ix1] = np.clip(block_factor, 0.0, 1.0)
        return b

    # ------------------------------------------------------------------ step
    def step(self, u_inlet: float | None = None):
        """Advance one LBM timestep.

        Parameters
        ----------
        u_inlet : inlet physical velocity (m/s).  If None, uses reference profile.
        """
        if u_inlet is None:
            u_inlet = self.u_ref

        Nx  = self.Nx
        tau = self.tau

        # 1. Compute macroscopic
        self._compute_macro()

        # 2. Collision (BGK)
        u_l  = self.u  * self._scale
        feq  = self._feq(self.rho, u_l)
        f_post = self.f - (1.0 / tau) * (self.f - feq)

        # 2b. Fence blockage — damp momentum in obstacle cells
        if np.any(self._blockage > 0):
            # Reduce distribution toward rest equilibrium proportional to blockage
            feq_rest = self._feq(self.rho, np.zeros(Nx))
            f_post += self._blockage[np.newaxis, :] * (feq_rest - f_post)

        # 3. Streaming (pull scheme)
        f_new = np.empty_like(self.f)
        for q in range(Q):
            f_new[q] = np.roll(f_post[q], E1D[q])

        # 4. BCs
        # Inlet (x=0): equilibrium injection at u_inlet
        u_in_l  = u_inlet * self._scale
        f_new[:, 0] = self._feq_scalar(1.0, u_in_l)

        # Outlet (x=Nx-1): Neumann copy
        f_new[:, Nx-1] = f_new[:, Nx-2]

        self.f[:] = f_new
        self._compute_macro()

    # ----------------------------------------------------------------- macro
    def _compute_macro(self):
        self.rho = self.f.sum(axis=0)
        rho_safe = np.maximum(self.rho, 1e-12)
        u_l = sum(E1D[q] * self.f[q] for q in range(Q)) / rho_safe
        self.u = u_l / self._scale

    # --------------------------------------------------------------- utility
    def friction_velocity(self) -> np.ndarray:
        """Estimate u*(x) from depth-averaged velocity via log law."""
        z_avg = 0.5 * self.dom.Lz
        return self.phys.u_star_from_log(np.abs(self.u), z_avg)

    @property
    def n_active_lbm(self) -> int:
        return self.Nx
