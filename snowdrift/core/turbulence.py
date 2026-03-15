"""
Synthetic inflow turbulence for the snowdrift LBM solver.

Generates spatially correlated, time-varying perturbations that are
added to the mean log-law inlet profile.

Method: superposition of random Fourier modes with von Kármán spectrum
  E(k) ∝ k^4 / (k^2 + k_e^2)^(17/6)
where k_e = c_e / L_t  (c_e = 1.453, L_t = integral length scale).

Reference: Smirnov et al. (2001), J. Fluids Eng. 123, 359-371.
           Mann (1998) spectral tensor (simplified isotropic variant).
"""
from __future__ import annotations
import numpy as np
from config import DomainConfig, PhysicsConfig, SimConfig


class SyntheticTurbulence:
    """Synthetic inflow turbulence generator (von Kármán spectrum).

    Parameters
    ----------
    dom   : DomainConfig
    phys  : PhysicsConfig
    sim   : SimConfig
    n_modes : number of Fourier modes to superpose (default 100)
    tke_frac : turbulence intensity — σ = tke_frac * U_ref

    Usage
    -----
    turb = SyntheticTurbulence(dom, phys, sim)
    for each LBM step at physical time t:
        u_inlet = phys.log_profile(dom.z) + turb.fluctuation(t)
    """

    def __init__(self,
                 dom:     DomainConfig,
                 phys:    PhysicsConfig,
                 sim:     SimConfig,
                 n_modes: int   = 100,
                 tke_frac: float = 0.10):
        self.dom      = dom
        self.phys     = phys
        self.sim      = sim
        self.n_modes  = n_modes
        self.sigma    = tke_frac * phys.U_ref   # turbulent velocity scale (m/s)

        # Integral length scale ≈ 0.15 * Lz (boundary-layer estimate)
        self.L_t = 0.15 * dom.Lz

        rng = np.random.default_rng(sim.seed + 999)
        self._build_modes(rng)

    # ----------------------------------------------------------------- build
    def _von_karman_E(self, k: np.ndarray) -> np.ndarray:
        """1-D von Kármán energy spectrum E(k)."""
        c_e = 1.453
        k_e = c_e / self.L_t
        return (k**4) / (k**2 + k_e**2) ** (17.0 / 6.0)

    def _build_modes(self, rng: np.random.Generator):
        """Pre-compute random Fourier modes."""
        N = self.n_modes

        # Sample wavenumbers log-uniformly between k_min and k_max
        k_min = 2.0 * np.pi / self.dom.Lz   # largest eddy
        k_max = 2.0 * np.pi / (2.0 * self.dom.dx)  # Nyquist

        k = np.exp(rng.uniform(np.log(k_min), np.log(k_max), N))

        # Amplitude weighted by von Kármán spectrum (normalised)
        E = self._von_karman_E(k)
        E_norm = E / (E.sum() + 1e-30)
        A = self.sigma * np.sqrt(2.0 * E_norm)  # (N,)

        # Random phase, direction, and wave vector angle in (x,z)
        phi   = rng.uniform(0, 2.0 * np.pi, N)   # temporal phase
        psi_k = rng.uniform(0, 2.0 * np.pi, N)   # wave vector direction

        # Wave vector components
        kx = k * np.cos(psi_k)  # (N,)
        kz = k * np.sin(psi_k)  # (N,)

        # Frequency ω = k * U_conv  (Taylor's frozen turbulence)
        U_conv = self.phys.U_ref
        omega  = k * U_conv      # (N,)

        # Random polarisation angle (direction of velocity fluctuation ⊥ k)
        alpha  = rng.uniform(0, 2.0 * np.pi, N)

        # Unit vectors perpendicular to k in 2-D: (-sin ψ, cos ψ)
        # velocity perturbation direction
        ex_perp = -np.sin(psi_k)   # (N,)
        ez_perp =  np.cos(psi_k)   # (N,)

        self._A     = A
        self._kx    = kx
        self._kz    = kz
        self._omega = omega
        self._phi   = phi
        self._ex    = ex_perp
        self._ez    = ez_perp

    # ----------------------------------------------------------------- query
    def fluctuation(self, t: float) -> np.ndarray:
        """Return streamwise velocity fluctuation u'(z, t) at the inlet.

        Parameters
        ----------
        t : physical time (s)

        Returns
        -------
        u_prime : (Nz,) array of velocity perturbations [m/s]
        """
        z = self.dom.z   # (Nz,)

        # Sum over modes:  u'(z,t) = Σ_n A_n * ex_n * cos(kz_n*z - ω_n*t + φ_n)
        # shape: (Nz, N_modes)
        phase = (self._kz[np.newaxis, :] * z[:, np.newaxis]
                 - self._omega[np.newaxis, :] * t
                 + self._phi[np.newaxis, :])
        u_prime = np.sum(self._A[np.newaxis, :] * self._ex[np.newaxis, :] * np.cos(phase),
                         axis=1)
        return u_prime   # (Nz,)

    def inlet_velocity(self, t: float) -> np.ndarray:
        """Mean log profile + synthetic turbulent fluctuation.

        Returns
        -------
        u_inlet : (Nz,) array [m/s]
        """
        return self.phys.log_profile(self.dom.z) + self.fluctuation(t)
