"""
Case figure: invoke vs skip branching at a decision point with entropy annotation.
All data is hardcoded from fork_records_all.json.

Usage:
    python figures/scripts/plot_case_figure.py --output figures/output
"""
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='figures/output', help='Output directory')
args = parser.parse_args()
OUT = Path(args.output)
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 9,
    'axes.linewidth': 0.6,
})

C_SHARED  = '#7BC0CD'
C_FORK    = '#ED8D5A'
C_INVOKE  = '#F0A040'
C_SKIP    = '#999999'
C_SUCCESS = '#4CAF50'
C_FAIL    = '#E53935'
C_BG_SHARED  = '#EBF5FB'
C_BG_INVOKE  = '#FFF3E0'
C_BG_SKIP    = '#F5F5F5'
C_BG_FORK    = '#FFF8F0'
C_BG_FAIL    = '#FFF0EE'
C_BG_SUCCESS = '#E8F5E9'


def draw_box(ax, x, y, w, h, text, fc, ec, tc='#222', lw=1.0, bold=False,
             fontsize=8, radius=0.025, clip=False):
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle=f'round,pad=0.01,rounding_size={radius}',
                          fc=fc, ec=ec, lw=lw, zorder=3, clip_on=clip)
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text, ha='center', va='center',
            fontsize=fontsize, color=tc,
            fontweight='bold' if bold else 'normal',
            fontfamily='DejaVu Sans', zorder=4, clip_on=clip,
            multialignment='center')


def draw_arrow(ax, x1, y, x2, color='#ccc', lw=1.2):
    ax.annotate('', xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw),
                annotation_clip=False, zorder=5)


def draw_entropy_badge(ax, x, y, label, h_val, color, align='left'):
    """Draw a small entropy label at (x, y).."""
    txt = f'{label}\n$\\bar{{H}}$={h_val:.3f}'
    ax.text(x, y, txt, ha=align, va='center',
            fontsize=6.8, color=color, fontfamily='DejaVu Sans',
            bbox=dict(boxstyle='round,pad=0.25', fc='white', ec=color, lw=0.8, alpha=0.92),
            zorder=6)


def draw_case(title, subtitle,
              shared_steps, fork_h_val,
              invoke_steps, invoke_outcome, invoke_outcome_c, invoke_h_val,
              skip_steps, skip_outcome, skip_outcome_c, skip_h_val,
              invoke_lbl='Invoke\n(chosen)', skip_lbl='Skip\n(rejected)',
              note=''):
    fig, ax = plt.subplots(figsize=(9.8, 5.2))
    ax.set_xlim(0, 10.5)
    ax.set_ylim(0, 10)
    ax.axis('off')
    fig.subplots_adjust(left=0.02, right=0.98, top=0.94, bottom=0.06)

    ax.text(5.25, 9.75, title,
            ha='center', va='top', fontsize=11, fontweight='bold',
            color='#111', fontfamily='DejaVu Sans')
    ax.text(5.25, 9.4, subtitle,
            ha='center', va='top', fontsize=8.5, color='#555',
            fontfamily='DejaVu Sans')

    BW, BH = 1.45, 0.65
    GAP = 0.12
    START_X = 0.35
    ROW1_Y = 7.8

    ax.text(0.18, ROW1_Y + BH / 2, 'Shared\nPrefix',
            ha='center', va='center', fontsize=7.5,
            color=C_SHARED, fontweight='bold', fontfamily='DejaVu Sans')

    cur_x = START_X
    fork_cx = None
    for i, (lbl, step_s) in enumerate(shared_steps):
        is_fork = (i == len(shared_steps) - 1)
        draw_box(ax, cur_x, ROW1_Y, BW, BH, lbl,
                 C_BG_FORK if is_fork else C_BG_SHARED,
                 C_FORK if is_fork else C_SHARED,
                 tc='#b83800' if is_fork else '#1a5276',
                 lw=2.0 if is_fork else 1.0, bold=is_fork)
        ax.text(cur_x + BW / 2, ROW1_Y - 0.12, step_s,
                ha='center', va='top', fontsize=6.5, color='#bbb')
        if i < len(shared_steps) - 1:
            draw_arrow(ax, cur_x + BW, ROW1_Y + BH / 2,
                       cur_x + BW + GAP, C_SHARED)
        if is_fork:
            fork_cx = cur_x + BW / 2
        cur_x += BW + GAP

    #
    draw_entropy_badge(ax, fork_cx + BW/2 + GAP*0.5 + 0.05, ROW1_Y + BH + 0.25,
                       'skill call', fork_h_val, C_FORK, align='center')

    # fork
    ax.annotate('fork', xy=(fork_cx, ROW1_Y - 0.28),
                ha='center', va='top', fontsize=7, color='#bbb',
                fontfamily='DejaVu Sans',
                xytext=(fork_cx, ROW1_Y - 0.05),
                arrowprops=dict(arrowstyle='->', color='#bbb', lw=0.8))

    # ── invoke
    INV_Y = ROW1_Y - 1.65
    ax.text(0.18, INV_Y + BH / 2, invoke_lbl,
            ha='center', va='center', fontsize=7.5,
            color='#b83800', fontweight='bold', fontfamily='DejaVu Sans')

    cur_x = START_X
    for i, (lbl, step_s, is_bad) in enumerate(invoke_steps):
        draw_box(ax, cur_x, INV_Y, BW, BH, lbl,
                 C_BG_FAIL if is_bad else C_BG_INVOKE,
                 C_FAIL if is_bad else C_INVOKE,
                 tc='#b33' if is_bad else '#7a3800')
        ax.text(cur_x + BW / 2, INV_Y - 0.12, step_s,
                ha='center', va='top', fontsize=6.5, color='#bbb')
        if i < len(invoke_steps) - 1:
            draw_arrow(ax, cur_x + BW, INV_Y + BH / 2,
                       cur_x + BW + GAP,
                       C_FAIL if is_bad else C_INVOKE)
        cur_x += BW + GAP

    # outcome badge
    draw_box(ax, cur_x + 0.1, INV_Y + 0.08, 1.35, BH - 0.16,
             invoke_outcome, C_BG_SUCCESS if invoke_outcome_c == 'green' else C_BG_FAIL,
             C_SUCCESS if invoke_outcome_c == 'green' else C_FAIL,
             tc='#2e7d32' if invoke_outcome_c == 'green' else '#c62828',
             bold=True, lw=1.2)
    draw_arrow(ax, cur_x, INV_Y + BH / 2, cur_x + 0.1,
               C_SUCCESS if invoke_outcome_c == 'green' else C_FAIL)

    #
    badge_x = cur_x + 0.1 + 1.35 + 0.12
    draw_entropy_badge(ax, badge_x, INV_Y + BH / 2,
                       'next step', invoke_h_val, C_INVOKE, align='left')

    # ── skip
    SKIP_Y = INV_Y - 1.65
    ax.text(0.18, SKIP_Y + BH / 2, skip_lbl,
            ha='center', va='center', fontsize=7.5,
            color='#666', fontweight='bold', fontfamily='DejaVu Sans')

    cur_x = START_X
    for i, (lbl, step_s, is_bad) in enumerate(skip_steps):
        draw_box(ax, cur_x, SKIP_Y, BW, BH, lbl,
                 C_BG_FAIL if is_bad else C_BG_SKIP,
                 C_FAIL if is_bad else C_SKIP,
                 tc='#b33' if is_bad else '#444')
        ax.text(cur_x + BW / 2, SKIP_Y - 0.12, step_s,
                ha='center', va='top', fontsize=6.5, color='#bbb')
        if i < len(skip_steps) - 1:
            draw_arrow(ax, cur_x + BW, SKIP_Y + BH / 2,
                       cur_x + BW + GAP,
                       C_FAIL if is_bad else C_SKIP)
        cur_x += BW + GAP

    draw_box(ax, cur_x + 0.1, SKIP_Y + 0.08, 1.35, BH - 0.16,
             skip_outcome, C_BG_SUCCESS if skip_outcome_c == 'green' else C_BG_FAIL,
             C_SUCCESS if skip_outcome_c == 'green' else C_FAIL,
             tc='#2e7d32' if skip_outcome_c == 'green' else '#c62828',
             bold=True, lw=1.2)
    draw_arrow(ax, cur_x, SKIP_Y + BH / 2, cur_x + 0.1,
               C_SUCCESS if skip_outcome_c == 'green' else C_FAIL)

    #
    badge_x = cur_x + 0.1 + 1.35 + 0.12
    draw_entropy_badge(ax, badge_x, SKIP_Y + BH / 2,
                       'next step', skip_h_val, C_SKIP, align='left')

    # ──
    if note:
        ax.text(5.25, 0.25, note,
                ha='center', va='bottom', fontsize=7, color='#888',
                fontfamily='DejaVu Sans', style='italic')

    return fig


# ── Case A: invoke_chosen ─────────────────────────────────────────────────────
# H̄(skill_call)=0.078, H̄(invoke)=0.340, H̄(skip)=0.0001
fig_a = draw_case(
    title='Case A: Invoking Skill Leads to Success (invoke_chosen)',
    subtitle='Task: clean some apple and put it in microwave  |  Fork at step 4 (holding apple 2)',
    shared_steps=[
        ('go to\ncountertop 1', 'step 1'),
        ('go to\ncountertop 2', 'step 2'),
        ('take apple 2\nfrom countertop 2', 'step 3'),
        ('Fork point\n(holding apple 2)', 'step 4'),
    ],
    fork_h_val=0.078,
    invoke_steps=[
        ('<tool_call>\nclean_object', 'step 4', False),
        ('clean apple 2\nwith sinkbasin 1', 'step 5', False),
        ('go to\nmicrowave 1', 'step 6', False),
        ('put apple 2\nin microwave 1', 'step 7–10', False),
    ],
    invoke_outcome='SUCCESS\n(10 steps)', invoke_outcome_c='green',
    invoke_h_val=0.340,
    skip_steps=[
        ('go to\nmicrowave 1', 'step 4', False),
        ('open\nmicrowave 1', 'step 5', False),
        ('put apple 2\n→ FAIL', 'step 6', True),
        ('loops...\n(apple not clean)', 'step 7–50', True),
    ],
    skip_outcome='FAIL\n(50 steps)', skip_outcome_c='red',
    skip_h_val=0.0001,
    invoke_lbl='Invoke\n(chosen)',
    skip_lbl='Skip\n(rejected)',
    note='Source: DPO training data (invoke_chosen, ep_0146, clean_object). '
         'After skill: $\\bar{H}$(invoke)=0.340 vs $\\bar{H}$(skip)=0.0001. '
         'Invoke forces re-planning; skip follows prior trajectory.',
)

for ext in ['png', 'pdf']:
    p = OUT / f'case_figure_invoke.{ext}'
    fig_a.savefig(str(p), dpi=200, bbox_inches='tight', facecolor='white')
    print(f'saved: {p}')
plt.close(fig_a)


# ── Case B: skip_chosen ───────────────────────────────────────────────────────
# H̄(skill_call)=0.116, H̄(invoke)=0.056, H̄(skip)=0.180
fig_b = draw_case(
    title='Case B: Invoking Skill Causes Failure (skip_chosen)',
    subtitle='Task: examine the alarmclock with the desklamp  |  Fork at step 8 (holding alarmclock)',
    shared_steps=[
        ('go to\ndesklamp 1', 'step 2'),
        ('go to\ndesk 1', 'step 4'),
        ('take alarmclock 1\nfrom desk 1', 'step 7'),
        ('Fork point\n(holding alarmclock)', 'step 8'),
    ],
    fork_h_val=0.116,
    invoke_steps=[
        ('<tool_call>\nexamine_with_light\n→ "Nothing happens"', 'step 8', True),
        ('examine\nalarmclock 1', 'step 9', True),
        ('loops...\n(confused)', 'step 10–48', True),
    ],
    invoke_outcome='FAIL\n(48 steps)', invoke_outcome_c='red',
    invoke_h_val=0.056,
    skip_steps=[
        ('examine\nalarmclock 1', 'step 8', False),
        ('go to\nsidetable 2', 'step 11', False),
        ('use desklamp 1\n(examine done)', 'step 14', False),
    ],
    skip_outcome='SUCCESS\n(14 steps)', skip_outcome_c='green',
    skip_h_val=0.180,
    invoke_lbl='Invoke\n(rejected)',
    skip_lbl='Skip\n(chosen)',
    note='Source: DPO training data (skip_chosen, examine_with_light). '
         'After skill: $\\bar{H}$(invoke)=0.056 vs $\\bar{H}$(skip)=0.180. '
         'Skill precondition not met → execution fails → model confused.',
)

for ext in ['png', 'pdf']:
    p = OUT / f'case_figure_skip.{ext}'
    fig_b.savefig(str(p), dpi=200, bbox_inches='tight', facecolor='white')
    print(f'saved: {p}')
plt.close(fig_b)
