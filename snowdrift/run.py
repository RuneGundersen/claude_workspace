"""
Snowdrift simulation — command-line entry point.

Usage examples
--------------
# Quick 1-D run with default settings:
  python run.py --model 1d

# 2-D run, fence at x=3 m, height=1.5 m, 5 ensemble members:
  python run.py --model 2d --x_pos 3.0 --height 1.5 --ensemble 5

# 2-D run with fence angle 30°, porosity 0.3:
  python run.py --model 2d --angle 30 --porosity 0.3

# 3-D run, coarser grid for speed:
  python run.py --model 3d --dx 0.10 --ensemble 3

# Save output to specific directory:
  python run.py --model 2d --outdir results/run01

# Disable synthetic turbulence:
  python run.py --model 2d --no_turb
"""
from __future__ import annotations
import argparse
import os
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')     # headless by default; change to 'TkAgg' for interactive
import matplotlib.pyplot as plt

from config import (DomainConfig, ObstructionConfig, PhysicsConfig,
                    SimConfig, SnowdriftConfig)
from models.model_1d import Model1D
from models.model_2d import Model2D
from models.model_3d import Model3D
from viz.plot import (plot_drift_1d, plot_drift_2d, plot_drift_3d,
                      plot_ensemble)


# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description='Snowdrift LBM simulation')

    # Model selection
    p.add_argument('--model',    default='2d',  choices=['1d', '2d', '3d'],
                   help='Dimensionality of model (default: 2d)')

    # Domain
    p.add_argument('--Lx',  type=float, default=12.0, help='Streamwise length (m)')
    p.add_argument('--Ly',  type=float, default=4.0,  help='Spanwise width (m) [3-D only]')
    p.add_argument('--Lz',  type=float, default=4.0,  help='Vertical height (m)')
    p.add_argument('--dx',  type=float, default=0.05, help='Grid spacing (m)')

    # Obstruction
    p.add_argument('--height',    type=float, default=1.0,  help='Fence height H (m)')
    p.add_argument('--width',     type=float, default=0.0,  help='Fence width W (m); 0=full')
    p.add_argument('--x_pos',     type=float, default=4.0,  help='Fence x-position (m)')
    p.add_argument('--angle',     type=float, default=0.0,  help='Fence angle to wind (deg)')
    p.add_argument('--thickness', type=float, default=0.1,  help='Fence thickness (m)')
    p.add_argument('--porosity',  type=float, default=0.0,  help='Fence porosity (0–1)')

    # Physics
    p.add_argument('--U_ref', type=float, default=6.0,  help='Mean wind speed at z_ref (m/s)')
    p.add_argument('--z0',    type=float, default=1e-4, help='Roughness length (m)')
    p.add_argument('--z_ref', type=float, default=0.10, help='Reference height for U_ref (m)')

    # Simulation
    p.add_argument('--t_total',   type=float, default=30.0,  help='Simulation time (s)')
    p.add_argument('--t_spinup',  type=float, default=5.0,   help='LBM spin-up time (s)')
    p.add_argument('--ensemble',  type=int,   default=10,    help='Ensemble members')
    p.add_argument('--n_particles', type=int, default=2000,  help='Max snow particles')
    p.add_argument('--seed',      type=int,   default=42,    help='Random seed')
    p.add_argument('--Ma',        type=float, default=0.10,  help='Target Mach number')

    # Options
    p.add_argument('--no_turb',  action='store_true', help='Disable synthetic turbulence')
    p.add_argument('--outdir',   default='output',    help='Output directory for figures/data')
    p.add_argument('--no_plots', action='store_true', help='Skip figure generation')
    p.add_argument('--save_npz', action='store_true', help='Save result arrays as .npz')

    return p.parse_args()


# ---------------------------------------------------------------------------
def build_config(args) -> SnowdriftConfig:
    dom  = DomainConfig(Lx=args.Lx, Ly=args.Ly, Lz=args.Lz, dx=args.dx)
    obs  = ObstructionConfig(height=args.height, width=args.width,
                              x_pos=args.x_pos, angle=args.angle,
                              thickness=args.thickness, porosity=args.porosity)
    phys = PhysicsConfig(U_ref=args.U_ref, z0=args.z0, z_ref=args.z_ref)
    sim  = SimConfig(t_total=args.t_total, t_spinup=args.t_spinup,
                     n_ensemble=args.ensemble, n_particles=args.n_particles,
                     seed=args.seed, Ma=args.Ma)
    label = f"{args.model}_H{args.height}_x{args.x_pos}_a{int(args.angle)}"
    return SnowdriftConfig(domain=dom, obstruction=obs, physics=phys,
                           sim=sim, label=label)


# ---------------------------------------------------------------------------
def run_1d(cfg: SnowdriftConfig, args) -> dict:
    print(cfg.summary())
    model  = Model1D(cfg)
    result = model.run(verbose=True)
    return result


def run_2d(cfg: SnowdriftConfig, args) -> dict:
    print(cfg.summary())
    model  = Model2D(cfg, use_turb=not args.no_turb, ensemble=args.ensemble)
    result = model.run(verbose=True)
    return result


def run_3d(cfg: SnowdriftConfig, args) -> dict:
    print(cfg.summary())
    model  = Model3D(cfg, use_turb=not args.no_turb, ensemble=args.ensemble)
    result = model.run(verbose=True)
    return result


# ---------------------------------------------------------------------------
def save_results(args, cfg: SnowdriftConfig, result: dict):
    os.makedirs(args.outdir, exist_ok=True)
    stem = os.path.join(args.outdir, cfg.label)
    dom, obs = cfg.domain, cfg.obstruction

    # Figures
    if not args.no_plots:
        if args.model == '1d':
            fig = plot_drift_1d(dom, obs,
                                result['drift'],
                                result.get('u_star'),
                                title=f'1-D Drift — {cfg.label}')
            fig.savefig(f'{stem}_drift.png', dpi=150)
            plt.close(fig)

        elif args.model == '2d':
            from geometry import make_mask_2d, add_ground
            solid = add_ground(make_mask_2d(dom, obs))
            fig = plot_drift_2d(dom, obs, solid,
                                result['drift_mean'],
                                u_star=result.get('u_star'),
                                title=f'2-D Drift — {cfg.label}')
            fig.savefig(f'{stem}_flow.png', dpi=150)
            plt.close(fig)

            fig2 = plot_ensemble(dom, obs,
                                 result['drift_mean'],
                                 result['drift_std'],
                                 title=f'Ensemble Drift — {cfg.label}')
            fig2.savefig(f'{stem}_ensemble.png', dpi=150)
            plt.close(fig2)

        elif args.model == '3d':
            fig = plot_drift_3d(dom, obs,
                                result['drift_mean'],
                                title=f'3-D Drift — {cfg.label}')
            fig.savefig(f'{stem}_plan.png', dpi=150)
            plt.close(fig)

        print(f"  Figures saved to {args.outdir}/")

    # Arrays
    if args.save_npz:
        np.savez_compressed(f'{stem}_data.npz', **{
            k: v for k, v in result.items()
            if isinstance(v, np.ndarray)
        })
        print(f"  Data saved to {stem}_data.npz")


# ---------------------------------------------------------------------------
def main():
    args   = parse_args()
    cfg    = build_config(args)

    dispatch = {'1d': run_1d, '2d': run_2d, '3d': run_3d}
    result = dispatch[args.model](cfg, args)

    save_results(args, cfg, result)
    print("Done.")


if __name__ == '__main__':
    main()
