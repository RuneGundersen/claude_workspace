"""
D2Q9 Lattice Boltzmann solver for the 2-D snowdrift model.

Array layout:  f[Q, Nz, Nx]
  axis 0 — velocity direction (Q=9)
  axis 1 — vertical  (z, ground=0, top=Nz-1)
  axis 2 — streamwise (x, inlet=0, outlet=Nx-1)

BGK collision + Smagorinsky SGS (Hou et al. 1994 quadratic formula).
Boundary conditions:
  inlet  (x=0)    : Zou-He velocity
  outlet (x=Nx-1) : Neumann (zero-gradient)
  bottom (z=0)    : no-slip bounce-back (ground)
  top    (z=Nz-1) : free-slip
  solid nodes      : halfway bounce-back
"""
from __future__ import annotations
import numpy as np
from config import DomainConfig, PhysicsConfig, SimConfig


# ---------------------------------------------------------------------------
# D2Q9 lattice constants
# ---------------------------------------------------------------------------
Q  = 9
# velocity vectors  [q, (ex, ez)]   x=streamwise, z=vertical
E  = np.array([[0,0],[1,0],[0,1],[-1,0],[0,-1],[1,1],[-1,1],[-1,-1],[1,-1]], dtype=np.int64)
W  = np.array([4/9, 1/9,1/9,1/9,1/9, 1/36,1/36,1/36,1/36])
OPP= np.array([0,   3,  4,  1,  2,   7,   8,   5,   6  ], dtype=np.int64)  # opposite dirs
CS2 = 1.0 / 3.0    # c_s²
CS4 = 1.0 / 9.0    # c_s⁴


class LBM2D:
    """D2Q9 BGK solver with Smagorinsky SGS.

    Parameters
    ----------
    dom     : DomainConfig
    phys    : PhysicsConfig
    sim     : SimConfig
    solid   : bool array (Nz, Nx), True = solid node
    """

    def __init__(self,
                 dom:   DomainConfig,
                 phys:  PhysicsConfig,
                 sim:   SimConfig,
                 solid: np.ndarray):
        self.dom   = dom
        self.phys  = phys
        self.sim   = sim
        self.solid = solid.astype(bool)

        Nx, Nz  = dom.Nx, dom.Nz
        self.Nx = Nx
        self.Nz = Nz

        # Unit conversion: physical ↔ lattice
        self.dt   = sim.lbm_dt(dom.dx, phys.U_ref)
        self.tau0 = sim.lbm_tau(dom.dx, self.dt, phys.nu_air)
        sim.validate_lbm(dom.dx, self.dt, phys.nu_air)

        # Velocity scale:  u_lbm = u_phys * dt / dx
        self._scale = self.dt / dom.dx

        # Distribution function  f[Q, Nz, Nx], initialised to rest equilibrium
        self.f = np.zeros((Q, Nz, Nx))
        self._init_f()

        # Macroscopic fields (physical units)
        self.ux   = np.zeros((Nz, Nx))   # streamwise velocity  (m/s)
        self.uz   = np.zeros((Nz, Nx))   # vertical velocity    (m/s)
        self.rho  = np.ones( (Nz, Nx))   # density (lattice, ≈ 1)

        self._compute_macro()

    # ------------------------------------------------------------------ init
    def _init_f(self):
        """Initialise f to equilibrium at rest with uniform density=1."""
        rho = np.ones((self.Nz, self.Nx))
        ux  = np.zeros((self.Nz, self.Nx))
        uz  = np.zeros((self.Nz, self.Nx))
        # Set inlet column to log profile
        z   = self.dom.z
        u_in= self.phys.log_profile(z) * self._scale        # lattice units
        for kz in range(self.Nz):
            ux[kz, 0] = u_in[kz]
        self.f[:] = self._equilibrium(rho, ux * self._scale, uz * self._scale)
        # Init with log profile for fluid nodes, rest equilibrium for solid nodes
        for ix in range(self.Nx):
            for kz in range(self.Nz):
                if self.solid[kz, ix]:
                    self.f[:, kz, ix] = W.copy()   # rest equilibrium (ux=0)
                else:
                    ux_l = self.phys.log_profile(self.dom.z[kz]) * self._scale
                    self.f[:, kz, ix] = self._equilibrium_scalar(1.0, ux_l, 0.0)

    def _equilibrium_scalar(self, rho: float, ux: float, uz: float) -> np.ndarray:
        """Equilibrium for a single node — returns shape (Q,)."""
        ue  = E[:, 0] * ux + E[:, 1] * uz
        usq = ux*ux + uz*uz
        return W * rho * (1.0 + ue/CS2 + ue**2/(2*CS4) - usq/(2*CS2))

    def _equilibrium(self, rho: np.ndarray, ux: np.ndarray, uz: np.ndarray) -> np.ndarray:
        """Vectorised equilibrium — returns shape (Q, Nz, Nx)."""
        feq = np.empty((Q, self.Nz, self.Nx))
        for q in range(Q):
            ue   = E[q,0]*ux + E[q,1]*uz
            usq  = ux**2 + uz**2
            feq[q] = W[q] * rho * (1.0 + ue/CS2 + ue**2/(2*CS4) - usq/(2*CS2))
        return feq

    # -------------------------------------------------------------- main step
    def step(self, u_inlet: np.ndarray | None = None):
        """Advance one LBM timestep.

        Parameters
        ----------
        u_inlet : (Nz,) array of physical inlet velocity [m/s], or None.
                  If None the log profile is used.
        """
        Nz, Nx  = self.Nz, self.Nx
        fluid   = ~self.solid

        # --- 1. Macroscopic quantities (physical units) ----
        self._compute_macro()

        # --- 2. Collision with Smagorinsky SGS ----
        ux_l = self.ux * self._scale    # lattice units
        uz_l = self.uz * self._scale
        feq  = self._equilibrium(self.rho, ux_l, uz_l)
        fneq = self.f - feq

        # Local effective relaxation time (Smagorinsky quadratic — Hou 1994)
        omega_eff = self._smagorinsky_omega(self.rho, fneq, fluid)

        # BGK collision
        f_post = self.f - omega_eff * fneq

        # --- 3. Streaming with link bounce-back ----
        # Pull scheme: f_new[q][iz, ix] = f_post[q][iz-ez, ix-ex]
        # If the source node (iz-ez, ix-ex) is solid, reflect using OPP direction
        # from the destination — this is "link" (halfway) bounce-back.
        iz_all = np.arange(Nz)
        ix_all = np.arange(Nx)
        f_new = np.empty_like(self.f)
        for q in range(Q):
            ex, ez = int(E[q, 0]), int(E[q, 1])
            f_new[q] = np.roll(np.roll(f_post[q], ex, axis=1), ez, axis=0)
            # Fluid nodes whose source was a solid node
            iz_src = (iz_all - ez) % Nz          # (Nz,)
            ix_src = (ix_all - ex) % Nx          # (Nx,)
            from_solid = self.solid[iz_src[:, None], ix_src[None, :]] & fluid
            if np.any(from_solid):
                f_new[q][from_solid] = f_post[OPP[q]][from_solid]
        # Keep solid node values well-defined (optional, avoids NaN drift)
        for q in range(Q):
            f_new[q][self.solid] = f_post[OPP[q]][self.solid]

        # --- 4. Boundary conditions ----
        # 4a. No-slip bottom (z=0): upward-going distributions at ground are unknown
        for q in range(Q):
            if E[q, 1] > 0:   # directions pointing upward (q=2,5,6)
                f_new[q][0, :] = f_post[OPP[q]][0, :]

        # 4b. Free-slip top (z=Nz-1): mirror downward-going distributions
        f_new[4][Nz-1, :] = f_new[2][Nz-1, :]   # −z  ← +z
        f_new[7][Nz-1, :] = f_new[5][Nz-1, :]   # d=7 ← d=5
        f_new[8][Nz-1, :] = f_new[6][Nz-1, :]   # d=8 ← d=6

        # 4c. Zou-He velocity inlet (x=0)
        if u_inlet is None:
            u_inlet = self.phys.log_profile(self.dom.z)
        self._bc_inlet_zou_he(f_new, u_inlet)

        # 4d. Zou-He pressure outlet (x=Nx-1): rho=1, ux extrapolated
        self._bc_outlet_zou_he(f_new)

        self.f[:] = f_new
        self._compute_macro()

    # ------------------------------------------------------------- macroscopic
    def _compute_macro(self):
        """Compute density and velocity from distribution functions."""
        # Replace any NaN/Inf in f with rest equilibrium before computing macro
        if not np.all(np.isfinite(self.f)):
            np.nan_to_num(self.f, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
            # Restore unit density at affected nodes
            bad = ~np.isfinite(self.f.sum(axis=0))
            for q in range(Q):
                self.f[q][bad] = W[q]
        self.rho  = self.f.sum(axis=0)
        rho_safe  = np.maximum(self.rho, 1e-12)
        # Lattice velocity
        ux_l = sum(E[q, 0] * self.f[q] for q in range(Q)) / rho_safe
        uz_l = sum(E[q, 1] * self.f[q] for q in range(Q)) / rho_safe
        # Convert to physical units
        self.ux = ux_l / self._scale
        self.uz = uz_l / self._scale
        # Zero out solid nodes
        self.ux[self.solid] = 0.0
        self.uz[self.solid] = 0.0

    # --------------------------------------------------------------- SGS
    def _smagorinsky_omega(self,
                            rho:   np.ndarray,
                            fneq:  np.ndarray,
                            fluid: np.ndarray) -> np.ndarray:
        """Return effective relaxation frequency ω_eff(x,z) — Hou et al. 1994."""
        tau0 = self.tau0
        Cs   = self.phys.Cs
        dx   = self.dom.dx

        # ||Π^neq|| = sqrt(2 * Σ_ij Π_ij² )
        # Π_ij^neq = Σ_q e_qi e_qj fneq_q
        Pxx  = sum(E[q,0]*E[q,0] * fneq[q] for q in range(Q))
        Pzz  = sum(E[q,1]*E[q,1] * fneq[q] for q in range(Q))
        Pxz  = sum(E[q,0]*E[q,1] * fneq[q] for q in range(Q))
        # ||Π|| in lattice units; clamp components before squaring to prevent overflow
        Pxx  = np.clip(Pxx, -1e9, 1e9)
        Pzz  = np.clip(Pzz, -1e9, 1e9)
        Pxz  = np.clip(Pxz, -1e9, 1e9)
        Pi_sq = np.minimum(Pxx**2 + Pzz**2 + 2*Pxz**2, 1e20)
        Pi    = np.sqrt(np.maximum(2.0 * Pi_sq, 0.0))

        # Quadratic formula for tau_eff (all quantities in lattice units)
        # tau_eff = 0.5*(tau0 + sqrt(tau0^2 + 18*Cs^2*Pi/rho))
        rho_safe = np.maximum(rho, 1e-12)
        B        = 18.0 * Cs**2 * Pi / rho_safe
        disc     = np.maximum(tau0**2 + B, 0.0)
        tau_eff  = 0.5 * (tau0 + np.sqrt(disc + 1e-30))
        # Safety: tau >= 0.5001
        tau_eff  = np.maximum(tau_eff, 0.5001)
        omega    = 1.0 / tau_eff
        # Solid nodes get neutral omega
        omega[~fluid] = 1.0
        return omega[np.newaxis, :, :]   # broadcast over Q

    # ---------------------------------------------------------- inlet BC
    def _bc_inlet_zou_he(self, f: np.ndarray, u_inlet: np.ndarray):
        """Zou-He velocity boundary at x=0.

        u_inlet : (Nz,) array of physical velocities [m/s].
        w=0 assumed (no vertical inflow).
        """
        ux = u_inlet * self._scale     # lattice units
        uz = np.zeros(self.Nz)
        ix = 0

        ux = np.clip(ux, -0.49, 0.49)   # ensure denominator (1-ux) >= 0.51
        rho_in = (f[0, :, ix] + f[2, :, ix] + f[4, :, ix] +
                  2.0*(f[3, :, ix] + f[6, :, ix] + f[7, :, ix])) / (1.0 - ux)
        rho_in = np.clip(rho_in, 0.9, 1.2)

        f[1, :, ix] = f[3, :, ix] + (2.0/3.0)*rho_in*ux
        f[5, :, ix] = f[7, :, ix] - 0.5*(f[2,:,ix]-f[4,:,ix]) + (1.0/6.0)*rho_in*ux
        f[8, :, ix] = f[6, :, ix] + 0.5*(f[2,:,ix]-f[4,:,ix]) + (1.0/6.0)*rho_in*ux

    def _bc_outlet_zou_he(self, f: np.ndarray):
        """Zou-He pressure outlet at x=Nx-1: rho=1, ux from interior, uz=0.

        Unknown distributions at the outlet are those with ex < 0 (q=3,6,7).
        """
        ix   = self.Nx - 1
        rho_out = 1.0

        # Extrapolate ux from the interior (zero-gradient)
        ux = (-1.0 + (f[0, :, ix] + f[2, :, ix] + f[4, :, ix] +
                      2.0*(f[1, :, ix] + f[5, :, ix] + f[8, :, ix])) / rho_out)
        ux = np.clip(ux, -0.3, 0.3)   # keep lattice Ma < 0.52

        f[3, :, ix] = f[1, :, ix] - (2.0/3.0)*rho_out*ux
        f[7, :, ix] = f[5, :, ix] + 0.5*(f[2,:,ix]-f[4,:,ix]) - (1.0/6.0)*rho_out*ux
        f[6, :, ix] = f[8, :, ix] - 0.5*(f[2,:,ix]-f[4,:,ix]) - (1.0/6.0)*rho_out*ux

    # ---------------------------------------------------------- utility
    def friction_velocity(self) -> np.ndarray:
        """Estimate surface friction velocity u*(x) from wall-adjacent layer."""
        z1  = self.dom.z[1]          # height of second row (above ground)
        u1  = np.abs(self.ux[1, :])  # speed at z1
        return self.phys.u_star_from_log(u1, z1)

    def interpolate_velocity(self, xp: np.ndarray, zp: np.ndarray):
        """Bilinear interpolation of (ux, uz) at particle positions.

        Parameters
        ----------
        xp, zp : (N,) arrays of physical coordinates

        Returns
        -------
        u_x, u_z : (N,) arrays of velocity components [m/s]
        """
        dx   = self.dom.dx
        # Convert to fractional index.
        # Clamp z to start at 0.5 so particles near the ground always sample
        # from the first fluid row (iz=0 is solid → ux=0, which would stall particles).
        xi   = np.clip(xp / dx - 0.5, 0, self.Nx - 2)
        zi   = np.clip(zp / dx - 0.5, 0.5, self.Nz - 2)
        ix   = xi.astype(int)
        iz   = zi.astype(int)
        fx   = xi - ix
        fz   = zi - iz

        def _interp(field):
            return (  (1-fx)*(1-fz)*field[iz,   ix  ]
                    + (  fx)*(1-fz)*field[iz,   ix+1]
                    + (1-fx)*(  fz)*field[iz+1, ix  ]
                    + (  fx)*(  fz)*field[iz+1, ix+1] )

        return _interp(self.ux), _interp(self.uz)
