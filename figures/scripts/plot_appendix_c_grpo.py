#!/usr/bin/env python3
"""
Appendix C: GRPO-noskill vs GRPO-bonus training curves.
All data is hardcoded from training logs.

Usage:
    python figures/scripts/plot_appendix_c_grpo.py --output figures/output/grpo_bonus_vs_noskill
"""
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='figures/output/grpo_bonus_vs_noskill')
args = parser.parse_args()
Path(args.output).parent.mkdir(parents=True, exist_ok=True)

def smooth(xs, ys, w=3):
    """Simple moving average, returns same-length arrays."""
    xs, ys = np.array(xs), np.array(ys)
    kernel = np.ones(w) / w
    ys_s = np.convolve(ys, kernel, mode='same')
    # fix edge effects: use smaller window at boundaries
    for i in range(w // 2):
        ys_s[i]  = ys[:i*2+1].mean()
        ys_s[-1-i] = ys[-i*2-1:].mean() if i > 0 else ys[-1]
    return xs, ys_s

# ──

# noskill train SR（per-step，
noskill_train_sr = {
    1:0.160, 2:0.203, 3:0.324, 4:0.281, 5:0.367, 6:0.277, 7:0.344, 8:0.344,
    9:0.398, 10:0.457, 11:0.340, 12:0.492, 13:0.375, 14:0.535, 15:0.512,
    16:0.418, 17:0.262, 18:0.555, 19:0.473, 20:0.625, 21:0.512, 22:0.418,
    23:0.504, 24:0.559, 25:0.551, 26:0.441, 27:0.562, 28:0.480, 29:0.688,
    30:0.590, 31:0.770, 32:0.602, 33:0.664, 34:0.516, 35:0.645, 36:0.801,
    37:0.785, 38:0.844, 39:0.789, 40:0.809, 41:0.891, 42:0.758, 43:0.629,
    44:0.738, 45:0.918, 46:0.852, 47:0.887, 48:0.844, 49:0.832, 50:0.785,
}

# skill+bonus (bonus=1.0) train SR
bonus_train_sr = {
    1:0.203, 2:0.215, 3:0.355, 4:0.281, 5:0.398, 6:0.184, 7:0.402, 8:0.527,
    9:0.523, 10:0.512, 11:0.531, 12:0.613, 13:0.535, 14:0.633, 15:0.648,
    16:0.637, 17:0.492, 18:0.688, 19:0.598, 20:0.750, 21:0.605, 22:0.707,
    23:0.625, 24:0.680, 25:0.723, 26:0.758, 27:0.703, 28:0.633,
    29:0.711, 30:0.695, 31:0.664, 32:0.680, 33:0.738, 34:0.684,
    35:0.750, 36:0.785, 37:0.512, 38:0.836, 39:0.566, 40:0.781,
    41:0.711, 42:0.750, 43:0.594, 44:0.738, 45:0.730, 46:0.836,
    47:0.699, 48:0.625, 49:0.852, 50:0.617,
}

bonus_train_tool = {
    1:14.6, 2:29.4, 3:6.4, 4:3.3, 5:3.1, 6:0.4, 7:8.1, 8:11.9, 9:6.8,
    10:6.8, 11:8.2, 12:8.7, 13:10.3, 14:8.5, 15:8.4, 16:7.5, 17:8.5,
    18:5.4, 19:6.1, 20:5.7, 21:5.5, 22:4.9, 23:3.6, 24:3.2, 25:2.7,
    26:1.9, 27:1.0, 28:2.0,
    29:3.7, 30:3.9, 31:3.8, 32:2.9, 33:2.1, 34:2.4,
    35:1.5, 36:1.8, 37:3.0, 38:1.3, 39:2.2,
    40:1.5,
}

# ──
c_bonus   = '#FF9800'   #
c_noskill = '#9E9E9E'   #
c_tool    = '#2196F3'   #

# ──
fig, ax = plt.subplots(1, 1, figsize=(6.75, 5))

xs_n  = sorted(noskill_train_sr); ys_n  = [noskill_train_sr[s] for s in xs_n]
xs_b  = sorted(bonus_train_sr);   ys_b  = [bonus_train_sr[s]   for s in xs_b]
xs_bt = sorted(bonus_train_tool); ys_bt = [bonus_train_tool[s] for s in xs_bt]

#
_, ys_n_s  = smooth(xs_n,  ys_n,  w=11)
_, ys_b_s  = smooth(xs_b,  ys_b,  w=11)

#
ax_r = ax.twinx()
ax_r.bar(xs_bt, ys_bt, color=c_tool, alpha=0.30, width=0.7, label='train skill/ep (+skill)', zorder=1)
ax_r.set_ylabel('Skill Calls / Episode', color=c_tool, fontsize=12)
ax_r.tick_params(axis='y', labelcolor=c_tool, labelsize=10)
#
ax_r.set_ylim(0, max(ys_bt) * 1.5)

#
ax.plot(xs_n, ys_n, 's', color=c_noskill, ms=3, alpha=0.2, zorder=3)
ax.plot(xs_n, ys_n_s, '--', color=c_noskill, lw=2.5, label='noskill train SR', zorder=4)
ax.plot(xs_b, ys_b, 'o', color=c_bonus, ms=3, alpha=0.2, zorder=3)
ax.plot(xs_b, ys_b_s, '-', color=c_bonus, lw=2.5, label='+skill train SR', zorder=4)

ax.set_xlabel('Training Step', fontsize=12)
ax.set_ylabel('Success Rate', fontsize=12)
ax.set_ylim(0, 1.05)
ax.set_xlim(0, 36)
ax.tick_params(labelsize=10)

ax.set_title('GRPO +skill (bonus=1.0) vs noskill: Train SR & Skill Calls', fontsize=12)

lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax_r.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc='upper left',
          framealpha=0.9, edgecolor='#cccccc')
ax.grid(alpha=0.15, linestyle='--', zorder=2)

plt.tight_layout()
out = args.output + '.png'
plt.savefig(out, dpi=150, bbox_inches='tight')
print(f"Saved to {out}")
