"""
Figure 4: Gradient localization — step-level vs episode-level DPO (Section 6).

Usage:
    python figures/scripts/plot_figure4_gradient_kde.py \
        --vanilla figures/data/grad_norm_v2_vanilla_only_curves.npy \
        --entropy figures/data/grad_norm_v2_entropy_only_curves.npy \
        --output  figures/output/gradient_focus_analysis_v3
"""

import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--vanilla', default='figures/data/grad_norm_v2_vanilla_only_curves.npy')
parser.add_argument('--entropy', default='figures/data/grad_norm_v2_entropy_only_curves.npy')
parser.add_argument('--output',  default='figures/output/gradient_focus_analysis_v3')
args = parser.parse_args()
Path(args.output).parent.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    'font.family': 'cmr10',
    'mathtext.fontset': 'cm',
    'axes.formatter.use_mathtext': True,
    'font.size': 13,
    'axes.linewidth': 0.8,
    'xtick.major.width': 0.8,
    'ytick.major.width': 0.8,
    'xtick.major.size': 3.5,
    'ytick.major.size': 3.5,
})

C_E    = '#ED8D5A'
C_V    = '#A8A29E'
C_ZONE = '#ED8D5A'

x = np.arange(-60, 61)

vanilla = np.load(args.vanilla)
entropy = np.load(args.entropy)


def bg_norm(arr):
    bg = arr.mean(axis=1, keepdims=True)
    return arr / (bg + 1e-8)


peak_pos_v = x[bg_norm(vanilla).argmax(axis=1)]
peak_pos_e = x[bg_norm(entropy).argmax(axis=1)]

# ──
fig, ax = plt.subplots(figsize=(6.5, 4.2))
fig.subplots_adjust(left=0.13, right=0.97, bottom=0.14, top=0.97)

X_SHOW = (-40, 50)
xs_kde = np.linspace(X_SHOW[0], X_SHOW[1], 600)


def smooth_kde(pos_array, xs):
    from scipy.stats import gaussian_kde
    kde = gaussian_kde(pos_array, bw_method=0.35)
    return kde(xs)


kde_v = smooth_kde(peak_pos_v, xs_kde)
kde_e = smooth_kde(peak_pos_e, xs_kde)

#
ax.axvspan(-7, 6, alpha=0.08, color=C_ZONE, zorder=0)

#
ax.axvline(0, color=C_E, lw=1.5, ls='--', alpha=0.8, zorder=3)

# KDE
ax.fill_between(xs_kde, kde_v, alpha=0.12, color=C_V)
ax.fill_between(xs_kde, kde_e, alpha=0.18, color=C_E)

# KDE
ax.plot(xs_kde, kde_v, color=C_V, lw=2.5, ls='--',
        label='Episode-level (Vanilla)')
ax.plot(xs_kde, kde_e, color=C_E, lw=3.0,
        label='Turn-level (Entropy)')

ymax = max(kde_v.max(), kde_e.max())

# "Skill call"
ax.text(-0.5, ymax * 1.15, 'Skill call',
        ha='center', va='top', fontsize=14, fontweight='bold',
        color=C_E)

ax.set_xlim(X_SHOW)
ax.set_ylim(0, ymax * 1.28)
ax.set_xlabel('Token position relative to skill call', fontsize=16)
ax.set_ylabel('Density of gradient peak', fontsize=16)
ax.legend(fontsize=12, loc='upper right', framealpha=0.9,
          edgecolor='#cccccc', handlelength=1.8, labelspacing=0.45)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.tick_params(axis='both', which='both', length=0, labelsize=12)
ax.grid(axis='y', alpha=0.15, ls='--', lw=0.6)

# ──
for ext in ['png', 'pdf']:
    out_path = f'{args.output}.{ext}'
    fig.savefig(out_path, dpi=200, bbox_inches='tight', facecolor='white')
    print(f'saved: {out_path}')

plt.close(fig)
