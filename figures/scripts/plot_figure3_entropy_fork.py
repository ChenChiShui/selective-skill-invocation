"""
Figure 3: Entropy-fork analysis — token entropy on invoke vs skip paths (Section 4).

The invoke path (after skill injection) exhibits higher average token entropy
than the skip path, motivating entropy-guided branch-point selection.

Usage:
    python figures/scripts/plot_figure3_entropy_fork.py \\
        --data    figures/data/fork_records_all.json \\
        --output  figures/output/entropy_fork_base_left_v2
"""
import argparse
import json, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--data',   default='figures/data/fork_records_all.json')
parser.add_argument('--output', default='figures/output/entropy_fork_base_left_v2')
args = parser.parse_args()
DATA = args.data
Path(args.output).parent.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    'font.family': 'cmr10',
    'mathtext.fontset': 'cm',
    'axes.formatter.use_mathtext': True,
    'font.size': 15,
    'axes.linewidth': 0.8,
    'xtick.major.width': 0.8,
    'ytick.major.width': 0.8,
    'xtick.major.size': 3.5,
    'ytick.major.size': 3.5,
})

SKIP       = 1
N_PRE      = 25
N_POST_MIN = 10
N_POST     = 75
P_LO, P_HI = 10, 90

COLOR_A = '#9CA3AF'   # Pre (shared prefix) —
COLOR_B = '#ED8D5A'   # Invoke path —
COLOR_C = '#7BC0CD'   # Skip path —

records = json.load(open(DATA))
valid = [r for r in records
         if r.get('seq_a') and r.get('seq_b') and r.get('seq_c')
         and len(r['seq_a']) >= N_PRE + SKIP
         and len(r['seq_b']) >= N_POST_MIN and len(r['seq_c']) >= N_POST_MIN]

seq_a_pre = np.array([r['seq_a'][SKIP:SKIP + N_PRE] for r in valid])
b_seqs    = [r['seq_b'] for r in valid]
c_seqs    = [r['seq_c'] for r in valid]


def masked_mean_pct(seqs, n_post, p_lo=P_LO, p_hi=P_HI):
    means = np.full(n_post, np.nan)
    lo    = np.full(n_post, np.nan)
    hi    = np.full(n_post, np.nan)
    for i in range(n_post):
        vals = np.array([s[i] for s in seqs if len(s) > i])
        if len(vals) < 2:
            continue
        means[i] = vals.mean()
        lo[i]    = np.percentile(vals, p_lo)
        hi[i]    = np.percentile(vals, p_hi)
    return means, lo, hi


mean_b, lo_b, hi_b = masked_mean_pct(b_seqs, N_POST)
mean_c, lo_c, hi_c = masked_mean_pct(c_seqs, N_POST)

mean_pre = seq_a_pre.mean(axis=0)
lo_pre   = np.percentile(seq_a_pre, P_LO, axis=0)
hi_pre   = np.percentile(seq_a_pre, P_HI, axis=0)

x_pre  = np.arange(-N_PRE, 0)
x_post = np.arange(0, N_POST)

fig, ax = plt.subplots(figsize=(6.5, 4.2))
fig.subplots_adjust(left=0.13, right=0.97, bottom=0.14, top=0.97)

# Pre（
ax.fill_between(x_pre, lo_pre, hi_pre, alpha=0.15, color=COLOR_A, zorder=2)
ax.plot(x_pre, mean_pre, color=COLOR_A, lw=3.0, zorder=4,
        label='Shared prefix')

# Skip（
mask_c = ~np.isnan(mean_c)
if mask_c.any():
    ax.fill_between(x_post[mask_c], lo_c[mask_c], hi_c[mask_c],
                    alpha=0.15, color=COLOR_C, zorder=3)
    ax.plot(x_post[mask_c], mean_c[mask_c], color=COLOR_C, lw=3.0, zorder=4,
            label='Skip path (no skill injection)')

# Invoke（
mask_b = ~np.isnan(mean_b)
if mask_b.any():
    ax.fill_between(x_post[mask_b], lo_b[mask_b], hi_b[mask_b],
                    alpha=0.15, color=COLOR_B, zorder=3)
    ax.plot(x_post[mask_b], mean_b[mask_b], color=COLOR_B, lw=3.0, zorder=5,
            label='Invoke path (skill injected)')

ax.axvline(x=0, color='black', lw=1.5, ls='--', alpha=0.7, zorder=6)
ax.annotate('Skill call',
            xy=(0, 0.78), xycoords=('data', 'axes fraction'),
            xytext=(4, 0.78), textcoords=('data', 'axes fraction'),
            fontsize=15, fontweight='bold', color='#4B5563',
            ha='left', va='center',
            arrowprops=dict(arrowstyle='->', color='#4B5563', lw=0.9,
                            mutation_scale=10))

ax.set_xlabel('Token position relative to skill call', fontsize=16)
ax.set_ylabel('Token entropy', fontsize=16)
ax.legend(fontsize=12, loc='upper right', framealpha=0.9,
          edgecolor='#cccccc', handlelength=1.8, labelspacing=0.45)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.tick_params(axis='both', which='both', length=0, labelsize=14)
ax.grid(axis='y', alpha=0.15, ls='--', lw=0.6)
ax.set_xlim(x_pre[0] - 0.5, x_post[-1] + 0.5)
ax.set_ylim(bottom=0)

for ext in ['png', 'pdf']:
    out_path = f'{args.output}.{ext}'
    fig.savefig(out_path, dpi=200, bbox_inches='tight', facecolor='white')
    print(f'saved: {out_path}')

plt.close(fig)
