"""
Figure: Token-Level KL Divergence aligned to skill-call token (Section 3.5 / gradient analysis).

Compares three training strategies (episode-level, turn-level, mixed) by showing
KL(pi_train || pi_ref) per token, aligned to the skill-call token position (x=0).

Usage:
    python figures/scripts/plot_kl_divergence.py \\
        --vanilla figures/data/kl_rollout_vanilla_only_curves.npy \\
        --entropy figures/data/kl_rollout_entropy_only_curves.npy \\
        --mixed   figures/data/kl_rollout_mixed_curves.npy \\
        --output  figures/output/kl_divergence
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter1d
from pathlib import Path

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'axes.linewidth': 0.8,
})

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--vanilla', default='figures/data/kl_rollout_vanilla_only_curves.npy')
parser.add_argument('--entropy', default='figures/data/kl_rollout_entropy_only_curves.npy')
parser.add_argument('--mixed',   default='figures/data/kl_rollout_mixed_curves.npy')
parser.add_argument('--output',  default='figures/output/kl_divergence')
args = parser.parse_args()
Path(args.output).parent.mkdir(parents=True, exist_ok=True)

WINDOW = 60
SIGMA  = 3.0
x_raw  = np.arange(-WINDOW, WINDOW + 1)

labels  = ['vanilla_only', 'entropy_only', 'mixed']
#
C_DARK  = '#999999'
C_MIX   = '#E65100'   #
colors  = [C_DARK, C_DARK, C_MIX]
lws     = [1.5, 1.5, 2.5]
alphas  = [0.6,  0.6,  1.0]
ls_list = ['--', '-',  '-']
sr_vals = [75.0, 70.3, 82.8]
legend_labels = [
    f'Episode-level only  (SR={sr_vals[0]}%)',
    f'Turn-level only     (SR={sr_vals[1]}%)',
    f'Mixed               (SR={sr_vals[2]}%)',
]

kl_data = {}
for label in labels:
    arr = np.load(getattr(args, label.replace('_only', '')))
    kl_data[label] = arr

peak_offsets = [x_raw[gaussian_filter1d(kl_data[l].mean(axis=0), SIGMA).argmax()] for l in labels]
SHIFT = -int(np.median(peak_offsets))
x = x_raw + SHIFT

smoothed   = {l: gaussian_filter1d(kl_data[l].mean(axis=0), SIGMA) for l in labels}
smooth_std = {l: gaussian_filter1d(kl_data[l].std(axis=0),  SIGMA) for l in labels}

# ═══════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7.3, 5.0))
fig.subplots_adjust(left=0.09, right=0.93, top=0.88, bottom=0.14)

X_LEFT, X_RIGHT = -15, 35

# ──
C_BLUEGRAY = '#5B7FA6'   #
C_ORANGE   = '#E06000'
C_GREEN    = '#2E7D32'
C_GRAY     = '#888888'

ax.axvspan(X_LEFT, -7,      alpha=0.05, color=C_GRAY,     zorder=0)
ax.axvspan(-7,     -4,      alpha=0.10, color=C_BLUEGRAY, zorder=0)
ax.axvspan(-4,     +6,      alpha=0.09, color=C_ORANGE,   zorder=0)
ax.axvspan(+6,     +12,     alpha=0.10, color=C_BLUEGRAY, zorder=0)
ax.axvspan(+12,    X_RIGHT, alpha=0.06, color=C_GREEN,    zorder=0)

#
ax.axvline(-7,  color=C_BLUEGRAY, lw=0.8, ls=':', alpha=0.55, zorder=5)
ax.axvline(-4,  color=C_ORANGE,   lw=0.8, ls=':', alpha=0.55, zorder=5)
ax.axvline( 0,  color='#444444',  lw=1.4, ls='--',alpha=0.75, zorder=5)
ax.axvline(+6,  color=C_BLUEGRAY, lw=0.8, ls=':', alpha=0.55, zorder=5)
ax.axvline(+12, color=C_GREEN,    lw=0.8, ls=':', alpha=0.55, zorder=5)

y_max = max(smoothed[l].max() for l in labels) * 1.22

# ──
for label, color, ls, lw, alpha, legend_label in zip(
        labels, colors, ls_list, lws, alphas, legend_labels):
    m  = smoothed[label]
    s  = smooth_std[label]
    zorder = 5 if label == 'mixed' else 3
    ax.plot(x, m, color=color, ls=ls, lw=lw, label=legend_label,
            alpha=alpha, zorder=zorder)
    ax.fill_between(x, m - s*0.25, m + s*0.25,
                    color=color,
                    alpha=0.12 if label == 'mixed' else 0.07,
                    zorder=zorder - 1)

# ──
#
ann_kw = dict(fontsize=7.5, ha='center', va='center',
              arrowprops=dict(arrowstyle='->', lw=1.0,
                              connectionstyle='arc3,rad=0.15'))
bbox_blue = dict(boxstyle='round,pad=0.22', fc='white',
                 ec=C_BLUEGRAY, alpha=0.92, lw=0.8)
bbox_grn  = dict(boxstyle='round,pad=0.22', fc='white',
                 ec=C_GREEN,    alpha=0.92, lw=0.8)

# ①
ax.annotate('① turn header\n<|im_start|>assistant',
    xy=(-6, smoothed['vanilla_only'][WINDOW - 6]),
    xytext=(-17, y_max * 0.72),
    color=C_BLUEGRAY,
    arrowprops=dict(arrowstyle='->', color=C_BLUEGRAY, lw=1.0,
                    connectionstyle='arc3,rad=0.2'),
    bbox=bbox_blue, fontsize=7.5, ha='center', va='center', zorder=8)

# ②
ax.annotate('② </tool_call> boundary\nchosen vs. rejected diverge',
    xy=(+7, smoothed['vanilla_only'][WINDOW + 7]),
    xytext=(+27, y_max * 0.60),
    color=C_BLUEGRAY,
    arrowprops=dict(arrowstyle='->', color=C_BLUEGRAY, lw=1.0,
                    connectionstyle='arc3,rad=-0.2'),
    bbox=bbox_blue, fontsize=7.5, ha='center', va='center', zorder=8)

# ③
ax.annotate('③ <tool_response>\nskill result vs. action list',
    xy=(+15, smoothed['vanilla_only'][WINDOW + 15]),
    xytext=(+28, y_max * 0.30),
    color=C_GREEN,
    arrowprops=dict(arrowstyle='->', color=C_GREEN, lw=1.0,
                    connectionstyle='arc3,rad=-0.15'),
    bbox=bbox_grn, fontsize=7.5, ha='center', va='center', zorder=8)

# ──
ax.set_xlabel('Token Offset  (0 = branch_tok, skill-call start)', fontsize=10)
ax.set_ylabel('KL Divergence  KL(π_train ∥ π_ref)', fontsize=10)
ax.set_title(
    'Token-Level KL Divergence Aligned to Skill-Call Token\n'
    'Mixed (blue) benefits from both episode-level and turn-level signals',
    fontsize=10, fontweight='bold')

#
ax.legend(fontsize=8.5, loc='upper left', framealpha=0.88,
          edgecolor='#cccccc', handlelength=1.8, labelspacing=0.45)
ax.set_xlim(X_LEFT, X_RIGHT + 2)
ax.set_ylim(-0.15, y_max)
ax.grid(True, alpha=0.12, linestyle='--', lw=0.6)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

for ext in ['png', 'pdf']:
    out_path = f'{args.output}.{ext}'
    fig.savefig(out_path, dpi=180, bbox_inches='tight', facecolor='white')
    print(f'saved: {out_path}')

plt.close(fig)
