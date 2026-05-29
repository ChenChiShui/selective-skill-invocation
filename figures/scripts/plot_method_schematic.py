"""
Method schematic: two-level gradient signal comparison (episode-level vs step-level).
All data is hardcoded.

Usage:
    python figures/scripts/plot_method_schematic.py --output figures/output
"""
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='figures/output', help='Output directory')
args = parser.parse_args()

plt.rcParams.update({
    'font.family': 'cmr10',
    'mathtext.fontset': 'cm',
    'axes.formatter.use_mathtext': True,
    'axes.linewidth': 0.8,
    'xtick.major.width': 0.8,
    'ytick.major.width': 0.8,
    'xtick.major.size': 3.5,
    'ytick.major.size': 3.5,
    'font.size': 11,
})

OUT = Path(args.output)
OUT.mkdir(parents=True, exist_ok=True)

# ──
C_ORANGE  = '#ED8D5A'   #
C_GRAY    = '#A8A29E'   #
C_ORANGE_LIGHT = '#F7D0B5'  #
C_GRAY_LIGHT   = '#E8E5E3'  #
C_TEXT    = '#333333'
C_LABEL   = '#555555'

# ──
fig = plt.figure(figsize=(13, 7.5))
gs = fig.add_gridspec(
    2, 2,
    height_ratios=[1.6, 1.0],
    width_ratios=[1.05, 0.95],
    hspace=0.6, wspace=0.38,
    left=0.06, right=0.97, top=0.97, bottom=0.08
)

ax_ep   = fig.add_subplot(gs[0, 0])
ax_st   = fig.add_subplot(gs[0, 1])
ax_bar  = fig.add_subplot(gs[1, 0])
ax_flow = fig.add_subplot(gs[1, 1])


# ──
def draw_traj_bar(ax, y, segments, bar_h=0.32, fontsize=8):
    for x0, x1, color, label, lc in segments:
        rect = FancyBboxPatch(
            (x0, y - bar_h / 2), x1 - x0, bar_h,
            boxstyle='round,pad=0.005',
            linewidth=0.5, edgecolor='#aaaaaa',
            facecolor=color, zorder=3
        )
        ax.add_patch(rect)
        if label:
            ax.text((x0 + x1) / 2, y, label,
                    ha='center', va='center',
                    fontsize=fontsize, color=lc, fontweight='bold', zorder=4)


def draw_gradient_bar(ax, y, segments, bar_h=0.14):
    for x0, x1, gval, color in segments:
        h = bar_h * max(gval, 0.05)
        rect = FancyBboxPatch(
            (x0, y - h / 2), x1 - x0, h,
            boxstyle='square,pad=0',
            linewidth=0, facecolor=color,
            alpha=max(gval, 0.12), zorder=3
        )
        ax.add_patch(rect)


# ════════════════════════════════════════════════════════════════
# Panel A：Episode-level DPO Pair
# ════════════════════════════════════════════════════════════════
ax_ep.set_xlim(0, 10)
ax_ep.set_ylim(-0.4, 5.2)
ax_ep.axis('off')
ax_ep.set_title('(a)  Episode-level DPO Pair',
                fontsize=12, fontweight='bold', color=C_GRAY, loc='left', pad=8)

# Chosen bar
segs_chosen = [
    (0.0, 2.0, C_GRAY_LIGHT, 'shared prefix', C_LABEL),
    (2.0, 4.5, C_ORANGE_LIGHT, 'action seq.', C_TEXT),
    (4.5, 7.0, C_ORANGE_LIGHT, '[+] skill call', C_TEXT),
    (7.0, 9.5, C_ORANGE_LIGHT, 'success >>', C_TEXT),
]
draw_traj_bar(ax_ep, 4.0, segs_chosen)
ax_ep.text(-0.05, 4.0, 'Chosen\n(success)', ha='right', va='center',
           fontsize=8.5, color=C_ORANGE, fontweight='bold')

# Rejected bar
segs_rejected = [
    (0.0, 2.0, C_GRAY_LIGHT, 'shared prefix', C_LABEL),
    (2.0, 5.5, C_GRAY_LIGHT, 'action seq.', C_TEXT),
    (5.5, 7.5, C_GRAY_LIGHT, '[x] no skill', C_LABEL),
    (7.5, 9.5, C_GRAY_LIGHT, 'fail >>', C_LABEL),
]
draw_traj_bar(ax_ep, 3.0, segs_rejected)
ax_ep.text(-0.05, 3.0, 'Rejected\n(failure)', ha='right', va='center',
           fontsize=8.5, color=C_GRAY, fontweight='bold')

# Gradient bar
grad_ep_segs = [
    (0.0, 2.0, 0.12, C_GRAY),
    (2.0, 9.5, 1.0,  C_ORANGE),
]
draw_gradient_bar(ax_ep, 2.2, grad_ep_segs)
ax_ep.text(-0.05, 2.2, r'$\nabla$ Loss', ha='right', va='center',
           fontsize=8, color=C_TEXT, style='italic')

ax_ep.annotate('', xy=(9.5, 1.85), xytext=(2.0, 1.85),
               arrowprops=dict(arrowstyle='<->', color=C_ORANGE, lw=1.5))
ax_ep.text(5.75, 1.62, 'gradient dispersed across entire trajectory',
           ha='center', fontsize=8, color=C_ORANGE, style='italic')

ax_ep.axvline(0.0, ymin=0.52, ymax=0.95, color=C_GRAY, lw=1.0, ls='--', alpha=0.6)
ax_ep.text(0.0, 4.65, 'branch\nstart', ha='center', va='bottom',
           fontsize=6.5, color=C_GRAY)

ax_ep.text(4.75, 0.55,
           'Loss mask: entire sequence after branch\n'
           r'$\rightarrow$ diffuse gradient signal',
           ha='center', va='center', fontsize=8.5,
           bbox=dict(boxstyle='round,pad=0.4', fc='#FFF5EE', ec=C_GRAY, lw=1.0, alpha=0.95),
           color=C_GRAY, fontweight='bold')

ax_ep.set_ylim(-0.3, 5.1)


# ════════════════════════════════════════════════════════════════
# Panel B：Step-level DPO Pair
# ════════════════════════════════════════════════════════════════
ax_st.set_xlim(0, 10)
ax_st.set_ylim(-0.4, 5.2)
ax_st.axis('off')
ax_st.set_title('(b)  Step-level DPO Pair  (entropy-guided)',
                fontsize=12, fontweight='bold', color=C_ORANGE, loc='left', pad=8)

segs_chosen_st = [
    (0.0, 3.5, C_GRAY_LIGHT, 'masked prefix  (shared)', C_LABEL),
    (3.5, 5.5, C_ORANGE_LIGHT, 'Skill call', C_TEXT),
    (5.5, 7.5, C_ORANGE_LIGHT, 'skill result', C_TEXT),
    (7.5, 9.5, C_ORANGE_LIGHT, 'success >>', C_TEXT),
]
draw_traj_bar(ax_st, 4.0, segs_chosen_st)
ax_st.text(-0.05, 4.0, 'Chosen\n(invoke\n+ success)', ha='right', va='center',
           fontsize=7.5, color=C_ORANGE, fontweight='bold')

segs_rejected_st = [
    (0.0, 3.5, C_GRAY_LIGHT, 'masked prefix  (shared)', C_LABEL),
    (3.5, 5.5, C_GRAY_LIGHT, 'No skill', C_LABEL),
    (5.5, 7.5, C_GRAY_LIGHT, 'manual action', C_LABEL),
    (7.5, 9.5, C_GRAY_LIGHT, 'fail >>', C_LABEL),
]
draw_traj_bar(ax_st, 3.0, segs_rejected_st)
ax_st.text(-0.05, 3.0, 'Rejected\n(skip\n+ failure)', ha='right', va='center',
           fontsize=7.5, color=C_GRAY, fontweight='bold')

grad_st_segs = [
    (0.0, 3.5, 0.0,  C_GRAY),
    (3.5, 9.5, 1.0,  C_ORANGE),
]
draw_gradient_bar(ax_st, 2.2, grad_st_segs)
ax_st.text(-0.05, 2.2, r'$\nabla$ Loss', ha='right', va='center',
           fontsize=8, color=C_TEXT, style='italic')

ax_st.annotate('', xy=(3.5, 1.85), xytext=(0.0, 1.85),
               arrowprops=dict(arrowstyle='<->', color=C_GRAY, lw=1.5))
ax_st.text(1.75, 1.62, 'zero gradient\n(masked)',
           ha='center', fontsize=7.5, color=C_GRAY, style='italic')

ax_st.annotate('', xy=(9.5, 1.85), xytext=(3.5, 1.85),
               arrowprops=dict(arrowstyle='<->', color=C_ORANGE, lw=1.8))
ax_st.text(6.5, 1.62, 'gradient focused on\ndecision point',
           ha='center', fontsize=7.5, color=C_ORANGE, style='italic', fontweight='bold')

# skill call
ax_st.axvline(3.5, ymin=0.36, ymax=0.95, color=C_ORANGE, lw=1.8, ls='--', alpha=0.85)
ax_st.text(3.5, 4.68, 'Skill call\n(entropy peak)',
           ha='center', va='bottom', fontsize=7, color=C_ORANGE, fontweight='bold')

# skill call
ax_st.axvspan(3.5, 5.5, alpha=0.07, color=C_ORANGE, zorder=0)

ax_st.text(4.75, 0.55,
           'Loss mask: only 3 turns after skill call\n'
           r'$\rightarrow$ precise gradient on skill decision',
           ha='center', va='center', fontsize=8.5,
           bbox=dict(boxstyle='round,pad=0.4', fc='#FFF5EE', ec=C_ORANGE, lw=1.0, alpha=0.95),
           color=C_ORANGE, fontweight='bold')

ax_st.set_ylim(-0.3, 5.1)


# ════════════════════════════════════════════════════════════════
# Panel C：
# ════════════════════════════════════════════════════════════════
regions = ['Context\n(<-7)', 'Skill call\n[-7, 6)', r'Post-skill$({\geq}6)$']
vanilla_pct = [51, 11, 38]
entropy_pct = [32, 43, 25]

x_pos = np.arange(len(regions))
width = 0.32

bars_v = ax_bar.bar(x_pos - width/2, vanilla_pct, width,
                    label='Episode-level',
                    color=C_GRAY, alpha=0.85, edgecolor='white', linewidth=0.5)
bars_e = ax_bar.bar(x_pos + width/2, entropy_pct, width,
                    label='Step-level (Ours)',
                    color=C_ORANGE, alpha=0.85, edgecolor='white', linewidth=0.5)

for bar in bars_v:
    ax_bar.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                f'{bar.get_height():.0f}%',
                ha='center', va='bottom', fontsize=8, color=C_GRAY)
for bar in bars_e:
    ax_bar.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                f'{bar.get_height():.0f}%',
                ha='center', va='bottom', fontsize=8, color=C_ORANGE)

ax_bar.axvspan(0.5, 1.5, alpha=0.07, color=C_ORANGE, zorder=0)
ax_bar.text(1.0, 46, r'3.9$\times$ more' + '\nthan Episode-level!',
            ha='center', fontsize=8, color=C_ORANGE, fontweight='bold', va='bottom',
            bbox=dict(boxstyle='round,pad=0.3', fc='#FFF5EE', ec=C_ORANGE, lw=0.8, alpha=0.9))

ax_bar.set_xticks(x_pos)
ax_bar.set_xticklabels(regions, fontsize=9.5)
ax_bar.set_ylabel('% of samples with gradient\npeak in this region', fontsize=10)
ax_bar.set_title('(c)  Where Does the Gradient Peak Land?',
                 fontsize=12, fontweight='bold', color=C_TEXT, pad=6)
ax_bar.set_ylim(0, 58)
ax_bar.legend(fontsize=9, loc='upper right', framealpha=0.9,
              edgecolor='#cccccc', handlelength=1.4, labelspacing=0.35)
ax_bar.spines['top'].set_visible(False)
ax_bar.spines['right'].set_visible(False)
ax_bar.grid(axis='y', alpha=0.15, ls='--', lw=0.6)
ax_bar.tick_params(axis='x', length=0, labelsize=9.5)
ax_bar.tick_params(axis='y', labelsize=9)


# ════════════════════════════════════════════════════════════════
# Panel D：Two-level signal
# ════════════════════════════════════════════════════════════════
ax_flow.axis('off')
ax_flow.set_xlim(0, 10)
ax_flow.set_ylim(0, 10)
ax_flow.set_title('(d)  Two-level Signal: Complementary Roles',
                  fontsize=12, fontweight='bold', color=C_TEXT, pad=6)

# Episode-level box（
ep_box = FancyBboxPatch((0.3, 5.8), 4.2, 4.0,
                        boxstyle='round,pad=0.18',
                        linewidth=1.5, edgecolor=C_GRAY,
                        facecolor='#F3F2F1', zorder=2)
ax_flow.add_patch(ep_box)
ax_flow.text(2.4, 9.6, 'Episode-level Pair',
             ha='center', va='top', fontsize=9, fontweight='bold', color=C_GRAY)
ax_flow.text(2.4, 9.1, 'success traj. vs. failure traj.',
             ha='center', va='top', fontsize=7.5, color='#666666', style='italic')
ax_flow.plot([0.55, 4.25], [8.7, 8.7], color=C_GRAY, lw=0.6, alpha=0.4)
ax_flow.text(0.65, 8.5, '[+]', ha='left', va='top', fontsize=8.5, color='#2E7D32')
ax_flow.text(1.15, 8.5, 'Global behavior preference',
             ha='left', va='top', fontsize=7.5, color=C_TEXT)
ax_flow.text(0.65, 7.9, '[+]', ha='left', va='top', fontsize=8.5, color='#2E7D32')
ax_flow.text(1.15, 7.9, 'Stable training signal',
             ha='left', va='top', fontsize=7.5, color=C_TEXT)
ax_flow.text(0.65, 7.3, '[-]', ha='left', va='top', fontsize=8.5, color=C_GRAY)
ax_flow.text(1.15, 7.3, 'Diffuse gradient (whole traj.)',
             ha='left', va='top', fontsize=7.5, color='#666666')

# Step-level box（
st_box = FancyBboxPatch((5.5, 5.8), 4.2, 4.0,
                        boxstyle='round,pad=0.18',
                        linewidth=1.5, edgecolor=C_ORANGE,
                        facecolor='#FFF5EE', zorder=2)
ax_flow.add_patch(st_box)
ax_flow.text(7.6, 9.6, 'Step-level Pair',
             ha='center', va='top', fontsize=9, fontweight='bold', color=C_ORANGE)
ax_flow.text(7.6, 9.1, 'invoke vs. skip at Skill call',
             ha='center', va='top', fontsize=7.5, color='#666666', style='italic')
ax_flow.plot([5.75, 9.45], [8.7, 8.7], color=C_ORANGE, lw=0.6, alpha=0.4)
ax_flow.text(5.85, 8.5, '[+]', ha='left', va='top', fontsize=8.5, color='#2E7D32')
ax_flow.text(6.35, 8.5, 'Precise gradient at Skill call',
             ha='left', va='top', fontsize=7.5, color=C_TEXT)
ax_flow.text(5.85, 7.9, '[+]', ha='left', va='top', fontsize=8.5, color='#2E7D32')
ax_flow.text(6.35, 7.9, 'Counterfactual signal',
             ha='left', va='top', fontsize=7.5, color=C_TEXT)
ax_flow.text(5.85, 7.3, '[-]', ha='left', va='top', fontsize=8.5, color=C_GRAY)
ax_flow.text(6.35, 7.3, 'Alone: degrades overall SR',
             ha='left', va='top', fontsize=7.5, color='#666666')

#
ax_flow.annotate('', xy=(4.55, 4.15), xytext=(2.4, 5.8),
                 arrowprops=dict(arrowstyle='->', color=C_GRAY, lw=1.8,
                                 connectionstyle='arc3,rad=0.2'))
ax_flow.annotate('', xy=(5.45, 4.15), xytext=(7.6, 5.8),
                 arrowprops=dict(arrowstyle='->', color=C_ORANGE, lw=1.8,
                                 connectionstyle='arc3,rad=-0.2'))
ax_flow.text(5.0, 4.7, '+', ha='center', va='center', fontsize=20,
             color=C_TEXT, fontweight='bold')

#
mix_box = FancyBboxPatch((1.5, 1.2), 7.0, 2.8,
                         boxstyle='round,pad=0.22',
                         linewidth=2.0, edgecolor=C_ORANGE,
                         facecolor='#FFF5EE', zorder=2)
ax_flow.add_patch(mix_box)
ax_flow.text(5.0, 3.85, 'Mixed DPO  (Skill-Aware DPO)',
             ha='center', va='top', fontsize=9.5, fontweight='bold', color=C_ORANGE)
ax_flow.plot([1.75, 8.25], [3.35, 3.35], color=C_ORANGE, lw=0.7, alpha=0.4)
ax_flow.text(3.0, 3.15, 'SR:', ha='right', va='top', fontsize=8.5, color='#555555')
ax_flow.text(3.1, 3.15, r'75.8\%  $\to$  86.7\%  (+10.9pp)',
             ha='left', va='top', fontsize=8.5, color=C_ORANGE, fontweight='bold')
ax_flow.text(3.0, 2.55, 'Prec:', ha='right', va='top', fontsize=8.5, color='#555555')
ax_flow.text(3.1, 2.55, r'70.9\%  $\to$  100.0\%  (+29.1pp)',
             ha='left', va='top', fontsize=8.5, color=C_ORANGE, fontweight='bold')
ax_flow.text(5.0, 1.75, 'Behavior alignment  +  Necessity alignment',
             ha='center', va='top', fontsize=8, color='#666666', style='italic')


# ──
for ext in ['png', 'pdf']:
    out_path = OUT / f'schematic_two_level_gradient_v2.{ext}'
    fig.savefig(str(out_path), dpi=200, bbox_inches='tight', facecolor='white')
    print(f'saved: {out_path}')

plt.close(fig)
