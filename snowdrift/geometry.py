"""
Build obstacle (solid-node) boolean masks for 1-D, 2-D and 3-D domains.

Convention
----------
Mask entry is True  → solid node (bounce-back / no-slip)
Mask entry is False → fluid node
"""
from __future__ import annotations
import numpy as np
from config import DomainConfig, ObstructionConfig


# ---------------------------------------------------------------------------
# 1-D mask  (Nx,)
# ---------------------------------------------------------------------------
def make_mask_1d(dom: DomainConfig, obs: ObstructionConfig) -> np.ndarray:
    """Return solid mask for the 1-D model.

    In 1-D we cannot represent a vertical fence directly.
    Instead we mark the streamwise cells occupied by the fence base.
    The effective blocking is encoded as a reduced velocity zone in model_1d.
    """
    mask = np.zeros(dom.Nx, dtype=bool)
    ix0  = int(round(obs.x_pos            / dom.dx))
    ix1  = int(round((obs.x_pos + obs.thickness) / dom.dx))
    mask[ix0:ix1] = True
    return mask


# ---------------------------------------------------------------------------
# 2-D mask  (Nz, Nx)  — x: streamwise, z: vertical
# ---------------------------------------------------------------------------
def make_mask_2d(dom: DomainConfig, obs: ObstructionConfig) -> np.ndarray:
    """Return solid mask for the 2-D (x–z) model.

    The fence is treated as a 2-D solid rectangle in the x–z plane.
    Angle θ reduces the effective height:  H_eff = H · |cos θ|.
    Porosity is handled separately in the LBM boundary step.
    """
    H_eff = obs.height * abs(np.cos(obs.angle_rad))
    Nz_f  = max(1, int(round(H_eff    / dom.dx)))
    ix0   = int(round(obs.x_pos            / dom.dx))
    ix1   = max(ix0 + 1, int(round((obs.x_pos + obs.thickness) / dom.dx)))
    ix0   = np.clip(ix0, 0, dom.Nx - 1)
    ix1   = np.clip(ix1, 1, dom.Nx)

    mask = np.zeros((dom.Nz, dom.Nx), dtype=bool)
    mask[:Nz_f, ix0:ix1] = True        # ground surface is z=0 (row index 0)
    return mask


# ---------------------------------------------------------------------------
# 3-D mask  (Nz, Ny, Nx)
# ---------------------------------------------------------------------------
def make_mask_3d(dom: DomainConfig, obs: ObstructionConfig) -> np.ndarray:
    """Return solid mask for the 3-D (x–y–z) model.

    The fence is a finite rectangular panel centred in y at the domain mid-plane.
    Its spanwise width W = obs.width  (0 → full channel width).
    Rotation angle θ is applied about the z-axis.

    For angle θ:
      Node (x,y) is inside the fence footprint if its position in the
      fence-local frame (obtained by rotating by −θ around the fence centre)
      satisfies  |x_local| ≤ thickness/2  and  |y_local| ≤ W/2.
    """
    W      = obs.width if obs.width > 0 else dom.Ly
    Nz_f   = max(1, int(round(obs.height / dom.dx)))
    theta  = obs.angle_rad

    # Fence centre in physical x
    x_fc   = obs.x_pos + obs.thickness / 2.0
    y_fc   = dom.Ly / 2.0
    half_t = obs.thickness / 2.0
    half_w = W / 2.0

    # Node coordinate arrays (physical)
    xc = (np.arange(dom.Nx) + 0.5) * dom.dx    # (Nx,)
    yc = (np.arange(dom.Ny) + 0.5) * dom.dx    # (Ny,)

    # Broadcast → 2-D plan-view arrays
    X, Y   = np.meshgrid(xc, yc, indexing='ij')   # (Nx, Ny)
    dX     = X - x_fc
    dY     = Y - y_fc

    # Rotate to fence-local frame
    Xl     =  dX * np.cos(theta) + dY * np.sin(theta)
    Yl     = -dX * np.sin(theta) + dY * np.cos(theta)

    # Fence footprint in plan (Nx, Ny)
    plan_mask = (np.abs(Xl) <= half_t) & (np.abs(Yl) <= half_w)

    # Broadcast to 3-D: solid for z-layers 0 … Nz_f−1
    mask = np.zeros((dom.Nz, dom.Ny, dom.Nx), dtype=bool)
    for kz in range(Nz_f):
        mask[kz, :, :] = plan_mask.T    # transpose: (Ny, Nx)

    return mask


# ---------------------------------------------------------------------------
# Ground mask helpers (always solid bottom row)
# ---------------------------------------------------------------------------
def add_ground(mask_2d: np.ndarray) -> np.ndarray:
    """Return copy of mask with bottom z-row forced solid (ground)."""
    m = mask_2d.copy()
    m[0, :] = True
    return m


def fence_stats(dom: DomainConfig, obs: ObstructionConfig) -> dict:
    """Return a dict of key fence geometry values for logging."""
    return dict(
        height   = obs.height,
        width    = obs.width if obs.width > 0 else dom.Ly,
        angle_deg= obs.angle,
        H_eff    = obs.effective_height,
        x_pos    = obs.x_pos,
        porosity = obs.porosity,
    )
