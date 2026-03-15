"""
D3Q19 Lattice Boltzmann solver for the 3-D snowdrift model.

Array layout:  f[Q, Nz, Ny, Nx]
  axis 0 — velocity direction (Q=19)
  axis 1 — vertical  (z, ground=0, top=Nz-1)
  axis 2 — spanwise  (y, south=0, north=Ny-1)
  axis 3 — streamwise (x, inlet=0, outlet=Nx-1)

BGK collision + Smagorinsky SGS.
Boundary conditions:
  inlet  (x=0)   : Zou-He velocity (streamwise profile, w=v=0)
  outlet (x=Nx-1): Neumann (zero-gradient)
  bottom (z=0)   : no-slip bounce-back
  top    (z=Nz-1): free-slip
  y-walls        : periodic (or no-slip if desired)
  solid nodes    : halfway bounce-back
"""
from __future__ import annotations
import numpy as np
from config import DomainConfig, PhysicsConfig, SimConfig


# ---------------------------------------------------------------------------
# D3Q19 lattice constants
# ---------------------------------------------------------------------------
Q19 = 19
# velocity vectors [q, (ex, ey, ez)]  — standard D3Q19 ordering
_E3 = np.array([
    [ 0,  0,  0],   # 0  rest
    [ 1,  0,  0],   # 1
    [-1,  0,  0],   # 2
    [ 0,  1,  0],   # 3
    [ 0, -1,  0],   # 4
    [ 0,  0,  1],   # 5
    [ 0,  0, -1],   # 6
    [ 1,  1,  0],   # 7
    [-1, -1,  0],   # 8
    [ 1, -1,  0],   # 9
    [-1,  1,  0],   # 10
    [ 1,  0,  1],   # 11
    [-1,  0, -1],   # 12
    [ 1,  0, -1],   # 13
    [-1,  0,  1],   # 14
    [ 0,  1,  1],   # 15
    [ 0, -1, -1],   # 16
    [ 0,  1, -1],   # 17
    [ 0, -1,  1],   # 18
], dtype=np.int64)

_W3 = np.array([
    1/3,
    1/18, 1/18, 1/18, 1/18, 1/18, 1/18,
    1/36, 1/36, 1/36, 1/36,
    1/36, 1/36, 1/36, 1/36,
    1/36, 1/36, 1/36, 1/36,
])

# Opposite direction index
_OPP3 = np.array([0, 2,1, 4,3, 6,5, 8,7, 10,9, 12,11, 14,13, 16,15, 18,17],
                 dtype=np.int64)

CS2 = 1.0 / 3.0
CS4 = 1.0 / 9.0


class LBM3D:
    """D3Q19 BGK solver with Smagorinsky SGS for 3-D snowdrift.

    Parameters
    ----------
    dom   : DomainConfig
    phys  : PhysicsConfig
    sim   : SimConfig
    solid : bool array (Nz, Ny, Nx), True = solid node
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

        Nx, Ny, Nz = dom.Nx, dom.Ny, dom.Nz
        self.Nx, self.Ny, self.Nz = Nx, Ny, Nz

        # Unit conversion
        self.dt     = sim.lbm_dt(dom.dx, phys.U_ref)
        self.tau0   = sim.lbm_tau(dom.dx, self.dt, phys.nu_air)
        sim.validate_lbm(dom.dx, self.dt, phys.nu_air)
        self._scale = self.dt / dom.dx

        # f[Q19, Nz, Ny, Nx]
        self.f = np.zeros((Q19, Nz, Ny, Nx))
        self._init_f()

        # Macroscopic fields (physical units)
        self.ux  = np.zeros((Nz, Ny, Nx))
        self.uy  = np.zeros((Nz, Ny, Nx))
        self.uz  = np.zeros((Nz, Ny, Nx))
        self.rho = np.ones( (Nz, Ny, Nx))
        self._compute_macro()

    # ------------------------------------------------------------------ init
    def _init_f(self):
        """Initialise to log-profile equilibrium."""
        z = self.dom.z   # (Nz,)
        for kz in range(self.Nz):
            ux_l = self.phys.log_profile(np.array([z[kz]]))[0] * self._scale
            feq  = self._feq_scalar(1.0, ux_l, 0.0, 0.0)
            self.f[:, kz, :, :] = feq[:, np.newaxis, np.newaxis]

    def _feq_scalar(self, rho: float, ux: float, uy: float, uz: float) -> np.ndarray:
        """Equilibrium for a single node, returns (Q19,)."""
        feq = np.empty(Q19)
        usq = ux*ux + uy*uy + uz*uz
        for q in range(Q19):
            ue = _E3[q,0]*ux + _E3[q,1]*uy + _E3[q,2]*uz
            feq[q] = _W3[q] * rho * (1.0 + ue/CS2 + ue**2/(2*CS4) - usq/(2*CS2))
        return feq

    def _equilibrium(self,
                     rho: np.ndarray,
                     ux:  np.ndarray,
                     uy:  np.ndarray,
                     uz:  np.ndarray) -> np.ndarray:
        """Vectorised equilibrium — returns (Q19, Nz, Ny, Nx)."""
        feq = np.empty((Q19, self.Nz, self.Ny, self.Nx))
        usq = ux**2 + uy**2 + uz**2
        for q in range(Q19):
            ue = _E3[q,0]*ux + _E3[q,1]*uy + _E3[q,2]*uz
            feq[q] = _W3[q] * rho * (1.0 + ue/CS2 + ue**2/(2*CS4) - usq/(2*CS2))
        return feq

    # -------------------------------------------------------------- main step
    def step(self, u_inlet: np.ndarray | None = None):
        """Advance one LBM timestep.

        Parameters
        ----------
        u_inlet : (Nz, Ny) array of physical inlet velocities [m/s], or None.
        """
        Nz, Ny, Nx = self.Nz, self.Ny, self.Nx
        fluid = ~self.solid

        # 1. Macroscopic
        self._compute_macro()

        # 2. Collision (BGK + Smagorinsky)
        ux_l = self.ux * self._scale
        uy_l = self.uy * self._scale
        uz_l = self.uz * self._scale
        feq  = self._equilibrium(self.rho, ux_l, uy_l, uz_l)
        fneq = self.f - feq

        omega_eff = self._smagorinsky_omega(self.rho, fneq, fluid)
        f_post = self.f - omega_eff * fneq

        # 3. Streaming (pull, periodic wrapping — BCs will overwrite)
        f_new = np.empty_like(self.f)
        for q in range(Q19):
            ex, ey, ez = int(_E3[q,0]), int(_E3[q,1]), int(_E3[q,2])
            tmp = np.roll(f_post[q], ex, axis=2)   # x
            tmp = np.roll(tmp,       ey, axis=1)   # y
            tmp = np.roll(tmp,       ez, axis=0)   # z
            f_new[q] = tmp

        # 4. BCs
        # 4a. Bounce-back solid nodes
        for q in range(Q19):
            f_new[q][self.solid] = f_post[_OPP3[q]][self.solid]

        # 4b. No-slip bottom (z=0)
        for q in range(Q19):
            if _E3[q, 2] < 0:
                f_new[q][0, :, :] = f_post[_OPP3[q]][0, :, :]

        # 4c. Free-slip top (z=Nz-1): mirror z-component
        for q in range(Q19):
            if _E3[q, 2] < 0:
                # Find the +z partner
                opp = _OPP3[q]
                f_new[q][Nz-1, :, :] = f_new[opp][Nz-1, :, :]

        # 4d. Periodic y-boundaries (already handled by np.roll above)

        # 4e. Zou-He velocity inlet (x=0)
        if u_inlet is None:
            u_inlet = self.phys.log_profile(self.dom.z)[:, np.newaxis] * np.ones((Nz, Ny))
        self._bc_inlet_zou_he(f_new, u_inlet)

        # 4f. Neumann outlet (x=Nx-1)
        f_new[:, :, :, Nx-1] = f_new[:, :, :, Nx-2]

        self.f[:] = f_new
        self._compute_macro()

    # ----------------------------------------------------------------- macro
    def _compute_macro(self):
        if not np.all(np.isfinite(self.f)):
            np.nan_to_num(self.f, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
            bad = ~np.isfinite(self.f.sum(axis=0))
            for q in range(Q19):
                self.f[q][bad] = _W3[q]
        self.rho = self.f.sum(axis=0)
        rho_safe = np.maximum(self.rho, 1e-12)
        ux_l = sum(_E3[q,0] * self.f[q] for q in range(Q19)) / rho_safe
        uy_l = sum(_E3[q,1] * self.f[q] for q in range(Q19)) / rho_safe
        uz_l = sum(_E3[q,2] * self.f[q] for q in range(Q19)) / rho_safe
        self.ux = ux_l / self._scale
        self.uy = uy_l / self._scale
        self.uz = uz_l / self._scale
        self.ux[self.solid] = 0.0
        self.uy[self.solid] = 0.0
        self.uz[self.solid] = 0.0

    # ------------------------------------------------------------------- SGS
    def _smagorinsky_omega(self,
                            rho:   np.ndarray,
                            fneq:  np.ndarray,
                            fluid: np.ndarray) -> np.ndarray:
        tau0 = self.tau0
        Cs   = self.phys.Cs
        dx   = self.dom.dx

        # Stress tensor components (3-D: xx, yy, zz, xy, xz, yz)
        Pxx = np.clip(sum(_E3[q,0]*_E3[q,0] * fneq[q] for q in range(Q19)), -1e9, 1e9)
        Pyy = np.clip(sum(_E3[q,1]*_E3[q,1] * fneq[q] for q in range(Q19)), -1e9, 1e9)
        Pzz = np.clip(sum(_E3[q,2]*_E3[q,2] * fneq[q] for q in range(Q19)), -1e9, 1e9)
        Pxy = np.clip(sum(_E3[q,0]*_E3[q,1] * fneq[q] for q in range(Q19)), -1e9, 1e9)
        Pxz = np.clip(sum(_E3[q,0]*_E3[q,2] * fneq[q] for q in range(Q19)), -1e9, 1e9)
        Pyz = np.clip(sum(_E3[q,1]*_E3[q,2] * fneq[q] for q in range(Q19)), -1e9, 1e9)
        Pi_sq = np.minimum(Pxx**2 + Pyy**2 + Pzz**2 + 2*Pxy**2 + 2*Pxz**2 + 2*Pyz**2, 1e20)
        Pi    = np.sqrt(np.maximum(2.0 * Pi_sq, 0.0))

        rho_safe = np.maximum(rho, 1e-12)
        B       = 18.0 * Cs**2 * Pi / rho_safe
        disc    = np.maximum(tau0**2 + B, 0.0)
        tau_eff = 0.5 * (tau0 + np.sqrt(disc + 1e-30))
        tau_eff = np.maximum(tau_eff, 0.5001)
        omega   = 1.0 / tau_eff
        omega[~fluid] = 1.0
        return omega[np.newaxis, :, :, :]

    # ----------------------------------------------------------- inlet BC
    def _bc_inlet_zou_he(self, f: np.ndarray, u_inlet: np.ndarray):
        """Zou-He velocity BC at x=0 (2-D inlet slice in Nz×Ny).

        u_inlet : (Nz, Ny) physical velocities [m/s], uy=uz=0 assumed.
        """
        ux = u_inlet * self._scale   # (Nz, Ny) lattice units
        ix = 0

        # Density from known distributions (q pointing away from wall + rest)
        # For D3Q19 at x=0 inlet face, incoming directions are q in {1,7,9,11,13}
        # (those with ex=+1).  Known are rest(0) + ex<0 + ey,ez-only.
        # Simplified: use rho = (known_sum) / (1 - ux)
        known = (f[0,:,:,ix]
                 + f[3,:,:,ix] + f[4,:,:,ix]
                 + f[5,:,:,ix] + f[6,:,:,ix]
                 + f[15,:,:,ix] + f[16,:,:,ix]
                 + f[17,:,:,ix] + f[18,:,:,ix]
                 + 2.0*(f[2,:,:,ix] + f[8,:,:,ix] + f[10,:,:,ix]
                        + f[12,:,:,ix] + f[14,:,:,ix]))
        rho_in = np.maximum(known / np.maximum(1.0 - ux, 1e-6), 0.9)

        # Set incoming distributions (ex=+1)
        f[1, :, :, ix]  = f[2, :, :, ix]  + (2.0/3.0)*rho_in*ux
        f[7, :, :, ix]  = f[8, :, :, ix]  - 0.5*(f[3,:,:,ix]-f[4,:,:,ix]) + (1.0/6.0)*rho_in*ux
        f[9, :, :, ix]  = f[10,:, :, ix]  + 0.5*(f[3,:,:,ix]-f[4,:,:,ix]) + (1.0/6.0)*rho_in*ux
        f[11,:, :, ix]  = f[12,:, :, ix]  - 0.5*(f[5,:,:,ix]-f[6,:,:,ix]) + (1.0/6.0)*rho_in*ux
        f[13,:, :, ix]  = f[14,:, :, ix]  + 0.5*(f[5,:,:,ix]-f[6,:,:,ix]) + (1.0/6.0)*rho_in*ux

    # --------------------------------------------------------------- utility
    def friction_velocity(self) -> np.ndarray:
        """Estimate u*(x, y) from wall-adjacent layer — returns (Ny, Nx)."""
        z1 = self.dom.z[1]
        u1 = np.abs(self.ux[1, :, :])   # (Ny, Nx)
        return self.phys.u_star_from_log(u1, z1)

    def interpolate_velocity(self, xp: np.ndarray, yp: np.ndarray, zp: np.ndarray):
        """Trilinear interpolation of (ux, uy, uz) at particle positions.

        Parameters
        ----------
        xp, yp, zp : (N,) arrays of physical coordinates

        Returns
        -------
        u_x, u_y, u_z : (N,) arrays [m/s]
        """
        dx = self.dom.dx
        xi = np.clip(xp / dx - 0.5, 0, self.Nx - 2)
        yi = np.clip(yp / dx - 0.5, 0, self.Ny - 2)
        zi = np.clip(zp / dx - 0.5, 0, self.Nz - 2)
        ix = xi.astype(int); iy = yi.astype(int); iz = zi.astype(int)
        fx = xi - ix;       fy = yi - iy;       fz = zi - iz

        def _interp(field):
            return (  (1-fx)*(1-fy)*(1-fz)*field[iz,   iy,   ix  ]
                    + (  fx)*(1-fy)*(1-fz)*field[iz,   iy,   ix+1]
                    + (1-fx)*(  fy)*(1-fz)*field[iz,   iy+1, ix  ]
                    + (  fx)*(  fy)*(1-fz)*field[iz,   iy+1, ix+1]
                    + (1-fx)*(1-fy)*(  fz)*field[iz+1, iy,   ix  ]
                    + (  fx)*(1-fy)*(  fz)*field[iz+1, iy,   ix+1]
                    + (1-fx)*(  fy)*(  fz)*field[iz+1, iy+1, ix  ]
                    + (  fx)*(  fy)*(  fz)*field[iz+1, iy+1, ix+1])

        return _interp(self.ux), _interp(self.uy), _interp(self.uz)
