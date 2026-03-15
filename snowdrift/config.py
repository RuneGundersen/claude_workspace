"""
Snowdrift model configuration — domain, obstruction, physics, simulation.
All physical quantities in SI units (m, s, kg).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------
@dataclass
class DomainConfig:
    """Physical domain dimensions and grid resolution.

    Axes:
      x — streamwise  (wind direction, West → East)
      y — spanwise    (South → North, used in 3-D only)
      z — vertical    (height above ground)
    """
    Lx: float = 12.0    # streamwise length  (m)
    Ly: float =  4.0    # spanwise width     (m)  — 3-D only
    Lz: float =  4.0    # vertical height    (m)
    dx: float =  0.05   # isotropic grid spacing (m)

    # ---- derived ----
    @property
    def Nx(self) -> int: return int(round(self.Lx / self.dx))
    @property
    def Ny(self) -> int: return int(round(self.Ly / self.dx))
    @property
    def Nz(self) -> int: return int(round(self.Lz / self.dx))

    @property
    def x(self) -> np.ndarray:
        return (np.arange(self.Nx) + 0.5) * self.dx
    @property
    def z(self) -> np.ndarray:
        return (np.arange(self.Nz) + 0.5) * self.dx

    def __post_init__(self):
        assert self.dx > 0,    "dx must be positive"
        assert self.Nx >= 10,  f"Nx={self.Nx} too small — increase Lx or decrease dx"
        assert self.Nz >= 10,  f"Nz={self.Nz} too small — increase Lz or decrease dx"


# ---------------------------------------------------------------------------
# Obstruction (snow fence / hill / barrier)
# ---------------------------------------------------------------------------
@dataclass
class ObstructionConfig:
    """Parameters for the fence / obstruction.

    Geometry in the x–y plane (plan view):
      - x_pos  : position of windward face (m from inlet)
      - height : vertical extent H (m)
      - width  : spanwise extent W (m); 0 = full channel width (2-D case)
      - angle  : rotation about z-axis from y-axis (degrees)
                 0° → fence normal to wind
                 45° → fence at 45° to wind
      - thickness : streamwise depth of fence (m)
      - porosity  : 0 = solid, 1 = transparent (fraction of open area)
    """
    height:    float = 1.0    # H  (m)
    width:     float = 0.0    # W  (m);  0 → full channel width
    x_pos:     float = 4.0    # x  position of windward face (m)
    angle:     float = 0.0    # θ  (degrees)
    thickness: float = 0.1    # fence depth in x-direction (m)
    porosity:  float = 0.0    # 0 = solid, 1 = fully porous

    @property
    def angle_rad(self) -> float:
        return np.radians(self.angle)

    @property
    def effective_height(self) -> float:
        """Effective height normal to incoming flow (reduced by angle)."""
        return self.height * abs(np.cos(self.angle_rad))


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------
@dataclass
class PhysicsConfig:
    """Atmospheric boundary layer and snow-particle physics.

    Default values follow Tanji et al. (2021).
    """
    # Wind
    U_ref:      float = 6.0       # mean wind speed at z_ref (m s⁻¹)
    z_ref:      float = 0.10      # reference height for U_ref (m)
    z0:         float = 1.0e-4    # aerodynamic roughness length — flat snow (m)
    kappa:      float = 0.41      # von Kármán constant
    Cs:         float = 0.12      # Smagorinsky coefficient
    nu_air:     float = 1.5e-5    # kinematic viscosity of air (m² s⁻¹)
    rho_air:    float = 1.34      # air density (kg m⁻³)

    # Snow particles
    rho_snow:   float = 910.0     # snow-particle density (kg m⁻³)
    d_snow:     float = 100.0e-6  # particle diameter (m)
    g:          float = 9.8       # gravitational acceleration (m s⁻²)
    alpha:      float = 1500.0    # snow-flux acceleration factor (Tanji 2021)
    n_max:      float = 30.0      # max snow concentration (g m⁻³)

    # ---- derived ----
    @property
    def u_star(self) -> float:
        """Friction velocity from log-law: U = (u* / κ) ln(z / z0)."""
        return self.U_ref * self.kappa / np.log(max(self.z_ref, self.z0 * 1.01) / self.z0)

    @property
    def u_star_t(self) -> float:
        """Threshold friction velocity — Bagnold (1941) / Clifton et al. (2006).
        u*_t = 0.2 * sqrt((ρ_p − ρ_a)/ρ_a · g · d) ≈ 0.163 m s⁻¹"""
        return 0.2 * np.sqrt(
            (self.rho_snow - self.rho_air) / self.rho_air * self.g * self.d_snow
        )

    @property
    def w_fall(self) -> float:
        """Terminal settling velocity ≈ 0.30 m s⁻¹ (Tanji et al. 2021 §2.3)."""
        return 0.30

    @property
    def tau_p(self) -> float:
        """Stokes particle response time (s)."""
        return self.rho_snow * self.d_snow**2 / (18 * self.nu_air * self.rho_air)

    def log_profile(self, z: np.ndarray) -> np.ndarray:
        """Mean streamwise wind speed U(z) [m s⁻¹] from log law."""
        z_safe = np.maximum(z, self.z0 * 1.01)
        return (self.u_star / self.kappa) * np.log(z_safe / self.z0)

    def snow_concentration(self, z: np.ndarray, u_star_local: float) -> np.ndarray:
        """Snow concentration profile n(z) [g m⁻³] — Eq.(24) Tanji et al.

        n(z) = min(n_max, n_max · (z / 0.15)^( -0.30 / (κ · u*) ))
        """
        u_star_local = max(u_star_local, 1e-6)
        exponent = -0.30 / (self.kappa * u_star_local)
        z_safe   = np.maximum(z, 1e-4)
        n        = self.n_max * (z_safe / 0.15) ** exponent
        return np.minimum(n, self.n_max)

    def u_star_from_log(self, u_z: float, z: float) -> float:
        """Estimate friction velocity from velocity u_z measured at height z."""
        z_safe = max(z, self.z0 * 1.01)
        return self.kappa * u_z / np.log(z_safe / self.z0)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
@dataclass
class SimConfig:
    """Numerical integration and output settings."""
    t_total:        float = 30.0   # total simulation time after spin-up (s)
    t_spinup:       float = 5.0    # LBM-only warm-up time (s)
    dt_snow:        float = 0.001  # snow-module timestep (s)
    output_dt:      float = 1.0    # save snapshot every N seconds
    n_ensemble:     int   = 50     # ensemble members for probabilistic snowdrift
    n_particles:    int   = 2000   # max active snow particles per timestep
    seed:           int   = 42     # random seed for reproducibility
    Ma:             float = 0.10   # target Mach number (controls LBM dt)
    U_max_factor:   float = 1.5    # U_max = U_max_factor * U_ref for Ma calc
    tau_min:        float = 0.60   # minimum relaxation time (LES effective viscosity floor)
    # tau_min > 0.50 is required: air viscosity gives tau~0.5000 (unstable).
    # 0.60 gives stable flow with ≤1 transient overflow per 50k steps (no NaN).
    # 0.55 causes many NaN warnings; 0.51 is chaotically turbulent in 2D.

    def lbm_dt(self, dx: float, U_ref: float) -> float:
        """LBM timestep such that U_max corresponds to the target Mach number.
        Ma = U_lbm / c_s,  c_s = 1/sqrt(3)  ->  U_lbm = Ma/sqrt(3)
        dt_phys = dx * U_lbm / U_max_phys
        """
        U_max  = self.U_max_factor * U_ref
        U_lbm  = self.Ma / np.sqrt(3.0)
        return dx * U_lbm / U_max

    def lbm_tau(self, dx: float, dt: float, nu_air: float) -> float:
        """BGK relaxation time tau = 3*nu_lbm + 0.5.

        The molecular nu_lbm for air is negligibly small (tau ~ 0.5000),
        so the result is clamped to tau_min which provides the implicit LES
        subgrid viscosity floor.
        """
        nu_lbm = nu_air * dt / dx**2
        return max(3.0 * nu_lbm + 0.5, self.tau_min)

    def validate_lbm(self, dx: float, dt: float, nu_air: float):
        tau = self.lbm_tau(dx, dt, nu_air)
        if tau <= 0.5:
            raise ValueError(
                f"LBM unstable: tau={tau:.6f} <= 0.5. "
                "Decrease dt, increase dx, or increase Ma."
            )
        if tau > 2.0:
            print(f"Warning: tau={tau:.4f} > 2.0 — high viscosity, consider reducing dx or dt.")
        return tau


# ---------------------------------------------------------------------------
# Top-level bundle
# ---------------------------------------------------------------------------
@dataclass
class SnowdriftConfig:
    """Convenience wrapper grouping all sub-configs."""
    domain:      DomainConfig      = field(default_factory=DomainConfig)
    obstruction: ObstructionConfig = field(default_factory=ObstructionConfig)
    physics:     PhysicsConfig     = field(default_factory=PhysicsConfig)
    sim:         SimConfig         = field(default_factory=SimConfig)
    label:       str               = 'run'

    def summary(self) -> str:
        d, o, p, s = self.domain, self.obstruction, self.physics, self.sim
        dt   = s.lbm_dt(d.dx, p.U_ref)
        tau  = s.lbm_tau(d.dx, dt, p.nu_air)
        lines = [
            f"=== Snowdrift config: {self.label} ===",
            f"Domain     : {d.Lx}x{d.Lz} m,  dx={d.dx} m,  grid {d.Nx}x{d.Nz}",
            f"Fence      : H={o.height} m, W={o.width} m, angle={o.angle} deg, "
            f"x={o.x_pos} m, porosity={o.porosity}",
            f"Wind       : U_ref={p.U_ref} m/s, u*={p.u_star:.3f} m/s, "
            f"u*_t={p.u_star_t:.3f} m/s",
            f"LBM        : dt={dt:.2e} s, tau={tau:.4f}, Ma={s.Ma}",
            f"Simulation : t_total={s.t_total} s (+{s.t_spinup} s spinup), "
            f"ensemble={s.n_ensemble}",
        ]
        return "\n".join(lines)
