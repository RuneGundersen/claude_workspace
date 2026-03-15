"""
Visualization utilities for the snowdrift model.

Functions
---------
plot_drift_1d   : 1-D drift height profile with u* overlay
plot_drift_2d   : 2-D x–z cross-section: wind field + drift height
plot_drift_3d   : 3-D plan-view heatmap of drift(y, x)
plot_ensemble   : drift mean ± std band
animate_2d      : (optional) matplotlib FuncAnimation of 2-D run snapshots
"""
from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Rectangle
from config import DomainConfig, ObstructionConfig


# ---------------------------------------------------------------------------
# 1-D
# ---------------------------------------------------------------------------
def plot_drift_1d(dom: DomainConfig,
                  obs: ObstructionConfig,
                  drift: np.ndarray,
                  u_star: np.ndarray | None = None,
                  title: str = '1-D Snowdrift') -> plt.Figure:
    """Plot 1-D drift height and optional friction velocity profile."""
    x = dom.x
    fig, ax1 = plt.subplots(figsize=(9, 4))

    ax1.fill_between(x, drift, alpha=0.5, color='steelblue', label='Drift height')
    ax1.plot(x, drift, color='steelblue', lw=1.5)
    ax1.set_xlabel('x (m)')
    ax1.set_ylabel('Drift height (m)', color='steelblue')
    ax1.tick_params(axis='y', labelcolor='steelblue')

    # Fence indicator
    _add_fence_patch_1d(ax1, obs, height=drift.max() if drift.max() > 0 else obs.height)

    if u_star is not None:
        ax2 = ax1.twinx()
        ax2.plot(x, u_star, 'r--', lw=1, label='u* (m/s)')
        ax2.axhline(0.163, color='r', ls=':', lw=0.8, label='u*_t')
        ax2.set_ylabel('u* (m/s)', color='red')
        ax2.tick_params(axis='y', labelcolor='red')

    ax1.set_title(title)
    ax1.legend(loc='upper left')
    fig.tight_layout()
    return fig


def _add_fence_patch_1d(ax, obs, height):
    rect = Rectangle((obs.x_pos, 0), obs.thickness, height,
                      linewidth=1, edgecolor='k', facecolor='gray', alpha=0.4,
                      label='Fence')
    ax.add_patch(rect)


# ---------------------------------------------------------------------------
# 2-D cross-section
# ---------------------------------------------------------------------------
def plot_drift_2d(dom: DomainConfig,
                  obs: ObstructionConfig,
                  solid: np.ndarray,
                  drift: np.ndarray,
                  ux: np.ndarray | None = None,
                  uz: np.ndarray | None = None,
                  u_star: np.ndarray | None = None,
                  title: str = '2-D Snowdrift') -> plt.Figure:
    """2-D cross-section plot: wind speed contours + drift profile."""
    x = dom.x
    z = dom.z

    fig, axes = plt.subplots(2, 1, figsize=(11, 7),
                              gridspec_kw={'height_ratios': [3, 1]})
    ax_flow, ax_drift = axes

    # --- Flow field ---
    if ux is not None:
        speed = np.sqrt(ux**2 + (uz if uz is not None else np.zeros_like(ux))**2)
        X, Z = np.meshgrid(x, z)
        cf = ax_flow.contourf(X, Z, speed, levels=20, cmap='Blues')
        plt.colorbar(cf, ax=ax_flow, label='|u| (m/s)')

        # Streamlines (quiver, subsampled)
        step = max(1, dom.Nz // 15)
        stepx = max(1, dom.Nx // 30)
        if uz is not None:
            ax_flow.quiver(X[::step, ::stepx], Z[::step, ::stepx],
                           ux[::step, ::stepx], uz[::step, ::stepx],
                           scale=80, width=0.002, alpha=0.6, color='white')

    # Solid mask
    solid_plot = np.ma.masked_where(~solid, solid.astype(float))
    ax_flow.contourf(*np.meshgrid(x, z), solid_plot, levels=[0.5, 1.5],
                     colors=['dimgray'], alpha=0.8)

    # Drift height line
    ax_flow.plot(x, drift, 'c-', lw=2, label='Drift surface')
    ax_flow.fill_between(x, drift, alpha=0.35, color='cyan')

    ax_flow.set_xlim(0, dom.Lx)
    ax_flow.set_ylim(0, dom.Lz)
    ax_flow.set_ylabel('z (m)')
    ax_flow.set_title(title)
    ax_flow.legend(loc='upper right', fontsize=8)

    # --- Drift profile ---
    ax_drift.fill_between(x, drift, alpha=0.6, color='steelblue')
    ax_drift.plot(x, drift, 'steelblue', lw=1.5)
    if u_star is not None:
        ax2 = ax_drift.twinx()
        ax2.plot(x, u_star, 'r--', lw=1, label='u*')
        ax2.axhline(0.163, color='r', ls=':', lw=0.8)
        ax2.set_ylabel('u* (m/s)', color='r', fontsize=8)
        ax2.tick_params(axis='y', labelcolor='r', labelsize=7)
    ax_drift.set_xlabel('x (m)')
    ax_drift.set_ylabel('Drift (m)')
    ax_drift.set_xlim(0, dom.Lx)

    # Fence marker
    ax_flow.axvline(obs.x_pos, color='k', ls='--', lw=0.8, alpha=0.5)
    ax_drift.axvline(obs.x_pos, color='k', ls='--', lw=0.8, alpha=0.5)

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------
def plot_ensemble(dom: DomainConfig,
                  obs: ObstructionConfig,
                  drift_mean: np.ndarray,
                  drift_std: np.ndarray,
                  title: str = 'Ensemble drift') -> plt.Figure:
    """Plot ensemble mean ± 1σ band."""
    x = dom.x
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.fill_between(x, drift_mean - drift_std, drift_mean + drift_std,
                    alpha=0.3, color='steelblue', label='±1σ')
    ax.plot(x, drift_mean, 'steelblue', lw=2, label='Mean drift')
    ax.axvline(obs.x_pos, color='k', ls='--', lw=0.8, label='Fence')
    ax.axvline(obs.x_pos + obs.thickness, color='k', ls='--', lw=0.8)
    ax.set_xlabel('x (m)')
    ax.set_ylabel('Drift height (m)')
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 3-D plan view
# ---------------------------------------------------------------------------
def plot_drift_3d(dom: DomainConfig,
                  obs: ObstructionConfig,
                  drift: np.ndarray,
                  title: str = '3-D Snowdrift — plan view') -> plt.Figure:
    """Plan-view (x–y) heatmap of drift height (Ny, Nx)."""
    x = dom.x
    # y array
    y = (np.arange(dom.Ny) + 0.5) * dom.dx

    fig, ax = plt.subplots(figsize=(10, 4))
    X, Y = np.meshgrid(x, y)
    cf = ax.contourf(X, Y, drift, levels=30, cmap='Blues')
    plt.colorbar(cf, ax=ax, label='Drift height (m)')

    # Fence footprint
    fence_y0 = (dom.Ly - obs.width) / 2.0 if obs.width > 0 else 0.0
    fence_y1 = dom.Ly - fence_y0 if obs.width > 0 else dom.Ly
    rect = Rectangle((obs.x_pos, fence_y0), obs.thickness, fence_y1 - fence_y0,
                      linewidth=1.5, edgecolor='red', facecolor='none',
                      label='Fence')
    ax.add_patch(rect)

    ax.set_xlabel('x (m)')
    ax.set_ylabel('y (m)')
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Animation (optional)
# ---------------------------------------------------------------------------
def animate_2d(dom: DomainConfig,
               obs: ObstructionConfig,
               solid: np.ndarray,
               snapshots: list[dict],
               interval: int = 200) -> 'matplotlib.animation.FuncAnimation':
    """Create a FuncAnimation over time snapshots from a 2-D run.

    Each snapshot dict needs keys: 't', 'drift', and optionally 'u'.
    """
    from matplotlib.animation import FuncAnimation

    x = dom.x
    fig, ax = plt.subplots(figsize=(10, 3))
    line, = ax.plot([], [], 'steelblue', lw=2)
    fill  = ax.fill_between(x, np.zeros_like(x), alpha=0.4, color='steelblue')
    ax.set_xlim(0, dom.Lx)
    max_drift = max(s['drift'].max() for s in snapshots) * 1.2 or 0.1
    ax.set_ylim(0, max_drift)
    ax.set_xlabel('x (m)')
    ax.set_ylabel('Drift (m)')
    ax.axvline(obs.x_pos, color='k', ls='--', lw=0.8)
    title_txt = ax.set_title('')

    def _update(frame):
        nonlocal fill
        snap = snapshots[frame]
        d = snap['drift']
        line.set_data(x, d)
        fill.remove()
        fill = ax.fill_between(x, d, alpha=0.4, color='steelblue')
        title_txt.set_text(f't = {snap["t"]:.1f} s')
        return line, fill, title_txt

    anim = FuncAnimation(fig, _update, frames=len(snapshots),
                         interval=interval, blit=False)
    return anim
