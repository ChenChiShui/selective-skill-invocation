"""
Collect per-token gradient norms from DPO preference pairs.
Outputs .npy files used by plot_figure4_gradient_kde.py.

For each chosen sequence, hooks the embedding layer to capture token-level
gradient norms, aligns them relative to the skill-call token (branch_msg_idx),
and saves per-pair curves for vanilla and entropy-guided pairs separately.

Usage:
    python figures/scripts/collect_gradient_data.py \\
        --model   /path/to/dpo-checkpoint \\
        --data    data/dpo/mixed_pairs.parquet \\
        --output  figures/data/grad_norm_v2
"""

import argparse, json, re, sys
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM
from scipy.ndimage import gaussian_filter1d

parser = argparse.ArgumentParser()
parser.add_argument('--model',   required=True, help='DPO checkpoint path')
parser.add_argument('--data', required=True, help='Combined DPO pairs .parquet (contains both vanilla and entropy pairs, distinguished by source field)')
parser.add_argument('--output',  default='figures/data/grad_norm_v2',
                    help='Output prefix (saves _vanilla_only_curves.npy and _entropy_only_curves.npy)')
args = parser.parse_args()

CKPT     = args.model
REF_CKPT = CKPT
DATA     = args.data
OUT      = args.output
Path(OUT).mkdir(parents=True, exist_ok=True)

DEVICE     = 'cuda:0'
MAX_LEN    = 8192   #
CONTEXT_WINDOW = 512  # entropy
WINDOW     = 60   # skill call
SIGMA      = 3.0  # gaussian
MAX_PAIRS  = 40   #

print(f"Loading tokenizer & policy model from {CKPT}")
tok = AutoTokenizer.from_pretrained(CKPT, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    CKPT, torch_dtype=torch.bfloat16, device_map=DEVICE, trust_remote_code=True)
model.train()

print(f"Loading ref model from {REF_CKPT}")
ref_model = AutoModelForCausalLM.from_pretrained(
    REF_CKPT, torch_dtype=torch.bfloat16, device_map=DEVICE, trust_remote_code=True)
ref_model.eval()

# ──
df = pd.read_parquet(args.data)
print(f"Data: {len(df)} pairs")

def is_entropy(src):
    return src not in ('vanilla_easy', 'vanilla_hard') and 'vanilla' not in src

df['is_entropy'] = df['source'].apply(is_entropy)
vanilla_df = df[~df['is_entropy']].reset_index(drop=True)
entropy_df = df[ df['is_entropy']].reset_index(drop=True)
print(f"  vanilla: {len(vanilla_df)}  entropy: {len(entropy_df)}")

# ── tokenize ──
def tokenize_messages(messages_str, max_len=MAX_LEN, branch_msg_idx=None):
    msgs = json.loads(messages_str)
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False,
                                   enable_thinking=False)
    #
    enc = tok(text, return_tensors='pt')
    ids = enc['input_ids'][0]

    #
    if len(ids) > max_len and branch_msg_idx is not None:
        #
        prefix_msgs = msgs[:int(branch_msg_idx)]
        if prefix_msgs:
            prefix_text = tok.apply_chat_template(
                prefix_msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            prefix_ids = tok(prefix_text, return_tensors='pt')['input_ids'][0]
            branch_tok = min(len(prefix_ids), len(ids)-1)
        else:
            branch_tok = 0
        #
        start = max(0, branch_tok - CONTEXT_WINDOW)
        end   = min(len(ids), branch_tok + CONTEXT_WINDOW)
        ids = ids[start:end]

    #
    if len(ids) > max_len:
        ids = ids[-max_len:]
    return ids

def build_loss_mask(messages_str, input_ids):
    """Positions corresponding to assistant turns are set to 1."""
    msgs = json.loads(messages_str)
    mask = torch.zeros(len(input_ids), dtype=torch.float32)
    #
    for i, m in enumerate(msgs):
        if m['role'] != 'assistant': continue
        #
        prefix_msgs = msgs[:i+1]
        prefix_text = tok.apply_chat_template(
            prefix_msgs, tokenize=False, add_generation_prompt=False, enable_thinking=False)
        prefix_ids = tok(prefix_text, return_tensors='pt',
                         truncation=True, max_length=MAX_LEN)['input_ids'][0]
        end = len(prefix_ids)
        #
        prev_msgs = msgs[:i]
        if prev_msgs:
            prev_text = tok.apply_chat_template(
                prev_msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            prev_ids = tok(prev_text, return_tensors='pt',
                           truncation=True, max_length=MAX_LEN)['input_ids'][0]
            start = len(prev_ids)
        else:
            start = 0
        start = min(start, len(input_ids)-1)
        end   = min(end,   len(input_ids))
        if end > start:
            mask[start:end] = 1.0
    return mask

def find_branch_token_idx(messages_str, input_ids, branch_msg_idx):
    """Convert branch_msg_idx (message-level) to token-level position."""
    if branch_msg_idx is None or (isinstance(branch_msg_idx, float) and np.isnan(branch_msg_idx)):
        return None
    branch_msg_idx = int(branch_msg_idx)
    msgs = json.loads(messages_str)
    prefix_msgs = msgs[:branch_msg_idx]
    if not prefix_msgs:
        return 0
    prefix_text = tok.apply_chat_template(
        prefix_msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    prefix_ids = tok(prefix_text, return_tensors='pt',
                     truncation=True, max_length=MAX_LEN)['input_ids'][0]
    return min(len(prefix_ids), len(input_ids)-1)

# ──
def get_token_grad_norms(chosen_ids, chosen_mask, rejected_ids, rejected_mask):
    """
    Return per-token gradient norm for the chosen sequence (seq_len,).
    Uses input embedding gradient.
    """
    model.zero_grad()

    # embedding hook：
    grads = {}
    def fwd_hook(module, input, output):
        output.retain_grad()
        def grad_hook(g):
            grads['embed'] = g.detach().float()  # (2, seq_len, hidden)
        output.register_hook(grad_hook)

    h = model.model.embed_tokens.register_forward_hook(fwd_hook)

    chosen_ids   = chosen_ids.unsqueeze(0).to(DEVICE)    # (1, seq_len)
    rejected_ids = rejected_ids.unsqueeze(0).to(DEVICE)
    chosen_mask_t   = chosen_mask.unsqueeze(0).to(DEVICE)
    rejected_mask_t = rejected_mask.unsqueeze(0).to(DEVICE)

    # pad
    max_len = max(chosen_ids.size(1), rejected_ids.size(1))
    def pad(t, val=tok.pad_token_id or 0):
        if t.size(1) < max_len:
            t = F.pad(t, (0, max_len - t.size(1)), value=val)
        return t
    def pad_mask(m):
        if m.size(1) < max_len:
            m = F.pad(m, (0, max_len - m.size(1)), value=0.0)
        return m

    chosen_ids   = pad(chosen_ids)
    rejected_ids = pad(rejected_ids)
    chosen_mask_t   = pad_mask(chosen_mask_t)
    rejected_mask_t = pad_mask(rejected_mask_t)

    input_ids   = torch.cat([chosen_ids,   rejected_ids],   dim=0)  # (2, seq_len)
    attn_mask   = (input_ids != (tok.pad_token_id or 0)).long()
    loss_mask   = torch.cat([chosen_mask_t, rejected_mask_t], dim=0)

    def get_seq_lp(m, ids, mask):
        with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
            logits = m(input_ids=ids, attention_mask=(ids != (tok.pad_token_id or 0)).long(),
                       use_cache=False).logits
        shift_logits = logits[:, :-1, :].float()
        shift_labels = ids[:, 1:].contiguous()
        shift_mask   = mask[:, 1:].float()
        log_probs = -F.cross_entropy(
            shift_logits.reshape(-1, shift_logits.size(-1)),
            shift_labels.reshape(-1), reduction='none'
        ).reshape(ids.size(0), -1)
        return (log_probs * shift_mask).sum(-1) / (shift_mask.sum(-1) + 1e-8)

    # policy log probs（
    policy_lp = get_seq_lp(model, input_ids, loss_mask)
    # ref log probs（
    with torch.no_grad():
        ref_lp = get_seq_lp(ref_model, input_ids, loss_mask)

    chosen_policy_lp   = policy_lp[0:1]
    rejected_policy_lp = policy_lp[1:2]
    chosen_ref_lp      = ref_lp[0:1]
    rejected_ref_lp    = ref_lp[1:2]

    beta = 0.1
    logits_dpo = beta * (
        (chosen_policy_lp - chosen_ref_lp) - (rejected_policy_lp - rejected_ref_lp)
    )
    loss = -F.logsigmoid(logits_dpo).mean()
    loss.backward()

    h.remove()

    if 'embed' not in grads:
        return None

    # grads['embed']: (2, seq_len, hidden)
    #
    chosen_grad = grads['embed'][0]  # (seq_len, hidden)
    grad_norms = chosen_grad.norm(dim=-1).cpu().numpy()  # (seq_len,)
    return grad_norms

# ──
vanilla_curves = []  # list of (branch_tok, grad_norms)
entropy_curves = []

def process_group(sub_df, label, max_n, store):
    count = 0
    for _, row in sub_df.iterrows():
        if count >= max_n: break
        try:
            bmx = row.get('branch_msg_idx', None)
            chosen_ids  = tokenize_messages(row['chosen_messages'],  branch_msg_idx=bmx)
            rejected_ids= tokenize_messages(row['rejected_messages'], branch_msg_idx=bmx)
            chosen_mask = build_loss_mask(row['chosen_messages'], chosen_ids)
            rejected_mask = build_loss_mask(row['rejected_messages'], rejected_ids)

            branch_tok = find_branch_token_idx(
                row['chosen_messages'], chosen_ids,
                row.get('branch_msg_idx', None))

            grad_norms = get_token_grad_norms(
                chosen_ids, chosen_mask, rejected_ids, rejected_mask)
            if grad_norms is None: continue

            store.append((branch_tok, grad_norms))
            count += 1
            if count % 10 == 0:
                print(f"  [{label}] {count}/{max_n}")
        except Exception as e:
            print(f"  [{label}] skip: {e}")
            continue
    print(f"  [{label}] done: {count} pairs")

print("\nProcessing vanilla pairs...")
process_group(vanilla_df, 'vanilla', MAX_PAIRS, vanilla_curves)
print("\nProcessing entropy pairs...")
process_group(entropy_df, 'entropy', MAX_PAIRS, entropy_curves)

# ──
def align_and_average(curves, window=WINDOW):
    """
    Align each curve at branch_tok, take [-window, +window] range, then average.
    For vanilla pairs with branch_tok=None, use sequence midpoint.
    """
    aligned = []
    for branch_tok, grad_norms in curves:
        n = len(grad_norms)
        if branch_tok is None:
            branch_tok = n // 2
        branch_tok = min(branch_tok, n-1)
        left  = branch_tok
        right = n - branch_tok
        # pad
        pad_l = max(0, window - left)
        pad_r = max(0, window - right + 1)
        padded = np.pad(grad_norms, (pad_l, pad_r), mode='constant', constant_values=0)
        center = branch_tok + pad_l
        segment = padded[center-window: center+window+1]
        if len(segment) == 2*window+1:
            aligned.append(segment)
    if not aligned:
        return np.zeros(2*window+1), np.zeros(2*window+1)
    arr = np.stack(aligned)
    return arr.mean(axis=0), arr.std(axis=0)

x = np.arange(-WINDOW, WINDOW+1)

v_mean, v_std = align_and_average(vanilla_curves)
e_mean, e_std = align_and_average(entropy_curves)

# gaussian
v_smooth = gaussian_filter1d(v_mean, sigma=SIGMA)
e_smooth = gaussian_filter1d(e_mean, sigma=SIGMA)

#
v_smooth = v_smooth / (v_smooth.max() + 1e-8)
e_smooth = e_smooth / (e_smooth.max() + 1e-8)

# mixed = vanilla + entropy（
n_vanilla = len(vanilla_curves)
n_entropy = len(entropy_curves)
total = n_vanilla + n_entropy
m_smooth = (v_smooth * n_vanilla + e_smooth * n_entropy) / total
m_smooth = m_smooth / (m_smooth.max() + 1e-8)

#
np.save(f'{OUT}/vanilla_grad_aligned.npy', v_mean)
np.save(f'{OUT}/entropy_grad_aligned.npy', e_mean)
np.save(f'{OUT}/x_offsets.npy', x)
print(f"\nRaw data saved to {OUT}/")

# ──
fig, ax = plt.subplots(figsize=(8, 4))

ax.axvline(0, color='gray', linestyle='--', linewidth=1.0, alpha=0.6, label='Skill Call Position')
ax.axvspan(-3, 3, alpha=0.08, color='orange', label='branch_turn_n=3 mask region')

ax.plot(x, v_smooth, color='#999999', linewidth=2.0, linestyle='--',
        label=f'Vanilla Only (episode-level, n={n_vanilla})')
ax.plot(x, e_smooth, color='#FF7F0E', linewidth=2.0, linestyle='-',
        label=f'Entropy Only (step-level, n={n_entropy})')
ax.plot(x, m_smooth, color='#1F77B4', linewidth=2.5, linestyle='-',
        label=f'Mixed (vanilla+entropy)')

ax.set_xlabel('Token Offset from Skill Call', fontsize=12)
ax.set_ylabel('Normalized Gradient Magnitude', fontsize=12)
ax.set_title('Token-Level DPO Gradient Distribution: Vanilla vs Entropy vs Mixed\n'
             '(8B RL base model, round1_v3_clean 170 pairs, β=0.1)', fontsize=11)
ax.legend(fontsize=10)
ax.set_xlim(-WINDOW, WINDOW)
ax.set_ylim(0, 1.15)
ax.grid(True, alpha=0.3)

plt.tight_layout()
out_fig = f'{OUT}/token_grad_analysis.pdf'
plt.savefig(out_fig, dpi=150, bbox_inches='tight')
plt.savefig(out_fig.replace('.pdf', '.png'), dpi=150, bbox_inches='tight')
print(f"Figure saved: {out_fig}")

#
print(f"\n=== Data Summary ===")
print(f"vanilla: {n_vanilla} pairs, peak at offset={x[np.argmax(v_smooth)]}, peak_val={v_smooth.max():.4f}")
print(f"entropy: {n_entropy} pairs, peak at offset={x[np.argmax(e_smooth)]}, peak_val={e_smooth.max():.4f}")
print(f"vanilla grad center avg (±5): {v_mean[WINDOW-5:WINDOW+6].mean():.6f}")
print(f"entropy grad center avg (±5): {e_mean[WINDOW-5:WINDOW+6].mean():.6f}")
