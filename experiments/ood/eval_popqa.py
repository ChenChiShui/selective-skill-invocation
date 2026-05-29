#!/usr/bin/env python3
"""
PopQA OOD generalization evaluation (Appendix 4.4).

Tests whether Selective Skill Invocation generalizes to knowledge-intensive QA.
Key hypothesis: DPO model should call skill MORE on low-popularity entities
(where parametric memory is weak) and LESS on high-popularity (where model
already knows the answer).

Conditions:
  closedbook: question only, model uses parametric memory
  noskill:    question + Wikipedia passages directly in prompt (open-book upper bound)
  skill:      model can invoke Wikipedia lookup skill

Metrics: Exact Match (EM) by popularity tier
  - low  (s_pop < 500):   long-tail entities, skill most valuable
  - mid  (500-5000):      moderate popularity
  - high (s_pop > 5000):  well-known, model likely knows already

Usage:
  python experiments/eval_popqa.py \\
      --condition skill \\
      --model-path /path/to/model \\
      --popqa-file /path/to/popqa_test.tsv \\
      --index-file /path/to/title_index.json.gz \\
      --output-dir exp/popqa-eval
"""

import argparse
import gzip
import json
import os
import re
import string
from collections import Counter
from pathlib import Path


# ── Metrics ───────────────────────────────────────────────────────────────────

def normalize_answer(s):
    s = re.sub(r'\b(a|an|the)\b', ' ', s.lower())
    s = ''.join(c for c in s if c not in string.punctuation)
    return ' '.join(s.split())

def exact_match(pred, golds):
    pred_n = normalize_answer(pred)
    return any(pred_n == normalize_answer(g) for g in golds)

def token_f1(pred, gold):
    p_toks = normalize_answer(pred).split()
    g_toks = normalize_answer(gold).split()
    common = Counter(p_toks) & Counter(g_toks)
    n = sum(common.values())
    if n == 0:
        return 0.0
    return 2 * (n / len(p_toks)) * (n / len(g_toks)) / (n / len(p_toks) + n / len(g_toks))

def best_f1(pred, golds):
    return max(token_f1(pred, g) for g in golds)

def pop_tier(s_pop):
    if s_pop < 500:
        return "low"
    if s_pop < 5000:
        return "mid"
    return "high"


# ── Skill ─────────────────────────────────────────────────────────────────────

SKILL_NAMES = {"lookup_person_fact", "lookup_creative_work",
               "lookup_geography", "lookup_family_relation"}

SKILL_LISTING = """You have access to 4 Wikipedia knowledge retrieval skills.
Call a skill when you are NOT confident about the answer.
Do NOT call a skill for well-known facts (e.g. capital of France, who wrote Hamlet).

- `lookup_person_fact()`: occupation, birthplace, nationality, religion
  Use <tool_call>{"name": "lookup_person_fact"}</tool_call>

- `lookup_creative_work()`: who directed/wrote/produced a film or book
  Use <tool_call>{"name": "lookup_creative_work"}</tool_call>

- `lookup_geography()`: capital city of obscure countries
  Use <tool_call>{"name": "lookup_geography"}</tool_call>

- `lookup_family_relation()`: who is someone's parent/spouse/child
  Use <tool_call>{"name": "lookup_family_relation"}</tool_call>
"""

SKILL_RESULT_TEMPLATE = "[Skill: {skill_name}]\n\nRetrieved Wikipedia passages for \"{entity}\":\n\n{passages}\n\nUse the above evidence to answer the question."

def load_index(index_file):
    print(f"Loading index from {index_file}...")
    with gzip.open(index_file, 'rt') as f:
        idx = json.load(f)
    print(f"  {len(idx):,} titles loaded")
    return idx

def execute_skill(skill_name, wiki_title, index):
    passages = index.get(wiki_title, [])
    if not passages:
        return f"[No Wikipedia passages found for '{wiki_title}']"
    text = "\n\n".join(f"[{i+1}] {p}" for i, p in enumerate(passages[:3]))
    return SKILL_RESULT_TEMPLATE.format(skill_name=skill_name, entity=wiki_title, passages=text)


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM = (
    "You are a knowledgeable assistant. Answer factual questions concisely. "
    "Answers are typically 1-3 words."
)

TOOL_CALL_RE = re.compile(r'<tool_call>\s*\{.*?"name"\s*:\s*"(\w+)".*?\}\s*</tool_call>', re.DOTALL)

def parse_skill_call(text):
    m = TOOL_CALL_RE.search(text)
    return m.group(1) if m else None

def extract_answer(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL)
    return text.strip().split('\n')[0].strip()

def build_closedbook_prompt(tok, question):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Question: {question}\nAnswer:"}]
    return tok.apply_chat_template(msgs, add_generation_prompt=True,
                                   tokenize=False, enable_thinking=False)

def build_noskill_prompt(tok, question, passages):
    passage_text = "\n\n".join(f"[{i+1}] {p}" for i, p in enumerate(passages[:3]))
    user_content = f"Wikipedia passages:\n{passage_text}\n\nQuestion: {question}\nAnswer:"
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content}]
    return tok.apply_chat_template(msgs, add_generation_prompt=True,
                                   tokenize=False, enable_thinking=False)

def build_skill_prompt(tok, question):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{SKILL_LISTING}\n\nQuestion: {question}\nAnswer:"}]
    return tok.apply_chat_template(msgs, add_generation_prompt=True,
                                   tokenize=False, enable_thinking=False)

def build_skill_with_result_prompt(tok, question, skill_name, skill_result):
    msgs = [
        {"role": "system",    "content": SYSTEM},
        {"role": "user",      "content": f"{SKILL_LISTING}\n\nQuestion: {question}"},
        {"role": "assistant", "content": f'<tool_call>{{"name": "{skill_name}"}}</tool_call>'},
        {"role": "tool",      "content": skill_result},
        {"role": "user",      "content": "Now answer the question (1-3 words):"},
    ]
    return tok.apply_chat_template(msgs, add_generation_prompt=True,
                                   tokenize=False, enable_thinking=False)


# ── Main eval ─────────────────────────────────────────────────────────────────

def run_eval(condition, rows, index, tok, llm, output_dir):
    from vllm import SamplingParams
    sp = SamplingParams(temperature=0.0, max_tokens=32)

    results = []
    stats = {t: {"em": 0, "f1": 0, "n": 0, "skill": 0} for t in ["low", "mid", "high"]}

    for i, row in enumerate(rows):
        q      = row["question"]
        golds  = json.loads(row["possible_answers"])
        title  = row["s_wiki_title"]
        tier   = pop_tier(row["s_pop"])
        passages = index.get(title, [])
        skill_called = None

        if condition == "closedbook":
            prompt = build_closedbook_prompt(tok, q)
            out = llm.generate([prompt], sp)[0].outputs[0].text
            pred = extract_answer(out)

        elif condition == "noskill":
            prompt = build_noskill_prompt(tok, q, passages)
            out = llm.generate([prompt], sp)[0].outputs[0].text
            pred = extract_answer(out)

        else:  # skill
            prompt = build_skill_prompt(tok, q)
            out1 = llm.generate([prompt], sp)[0].outputs[0].text
            skill_called = parse_skill_call(out1)
            if skill_called:
                effective = skill_called if skill_called in SKILL_NAMES else "lookup_person_fact"
                evidence = execute_skill(effective, title, index)
                prompt2 = build_skill_with_result_prompt(tok, q, effective, evidence)
                out2 = llm.generate([prompt2], sp)[0].outputs[0].text
                pred = extract_answer(out2)
            else:
                pred = extract_answer(out1)

        em = int(exact_match(pred, golds))
        f1 = best_f1(pred, golds)
        stats[tier]["em"] += em
        stats[tier]["f1"] += f1
        stats[tier]["n"]  += 1
        if skill_called:
            stats[tier]["skill"] += 1

        results.append({
            "id": row["id"], "question": q, "gold": golds[0], "pred": pred,
            "em": em, "f1": f1, "tier": tier, "s_pop": row["s_pop"],
            "skill_called": skill_called,
        })

        if (i + 1) % 200 == 0:
            total_em = sum(s["em"] for s in stats.values())
            total_n  = sum(s["n"]  for s in stats.values())
            print(f"  [{i+1}/{len(rows)}] EM={total_em/total_n*100:.1f}%")

    print(f"\n=== {condition} ===")
    total_em = total_f1 = total_n = total_skill = 0
    for tier in ["low", "mid", "high"]:
        s = stats[tier]
        if s["n"] == 0:
            continue
        print(f"  {tier:4s} (n={s['n']:4d}): EM={s['em']/s['n']*100:.1f}%  F1={s['f1']/s['n']*100:.1f}%  skill={s['skill']/s['n']*100:.1f}%")
        total_em += s["em"]; total_f1 += s["f1"]
        total_n  += s["n"]; total_skill += s["skill"]
    print(f"  {'all':4s} (n={total_n:4d}): EM={total_em/total_n*100:.1f}%  F1={total_f1/total_n*100:.1f}%  skill={total_skill/total_n*100:.1f}%")

    summary = {
        "condition": condition, "n": total_n,
        "overall_em": total_em / total_n, "overall_f1": total_f1 / total_n,
        "overall_skill_rate": total_skill / total_n,
        "by_tier": {
            t: {
                "em": stats[t]["em"] / stats[t]["n"] if stats[t]["n"] else 0,
                "f1": stats[t]["f1"] / stats[t]["n"] if stats[t]["n"] else 0,
                "skill_rate": stats[t]["skill"] / stats[t]["n"] if stats[t]["n"] else 0,
                "n": stats[t]["n"],
            } for t in ["low", "mid", "high"]
        },
    }

    os.makedirs(output_dir, exist_ok=True)
    with open(f"{output_dir}/summary_{condition}.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(f"{output_dir}/results_{condition}.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, choices=["noskill", "skill", "closedbook"])
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--tokenizer-path", default=None)
    parser.add_argument("--popqa-file", required=True,
                        help="PopQA test TSV file (e.g. popqa_test.tsv)")
    parser.add_argument("--index-file", required=True,
                        help="Wikipedia title index JSON.gz file")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--n-per-tier", type=int, default=0,
                        help="Questions per tier for quick eval (0 = full)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import pandas as pd
    from vllm import LLM
    from transformers import AutoTokenizer

    index = load_index(args.index_file)

    df = pd.read_csv(args.popqa_file, sep='\t')
    df['tier'] = df['s_pop'].apply(pop_tier)
    df = df[df['s_wiki_title'].isin(index)].reset_index(drop=True)

    if args.n_per_tier > 0:
        df = pd.concat([
            grp.sample(min(len(grp), args.n_per_tier), random_state=args.seed)
            for _, grp in df.groupby('tier', observed=True)
        ]).reset_index(drop=True)

    rows = df.to_dict('records')
    print(f"Eval: {len(rows)} questions  low={sum(1 for r in rows if r['tier']=='low')}  "
          f"mid={sum(1 for r in rows if r['tier']=='mid')}  high={sum(1 for r in rows if r['tier']=='high')}")

    tok = AutoTokenizer.from_pretrained(args.tokenizer_path or args.model_path, trust_remote_code=True)
    llm = LLM(args.model_path, dtype="bfloat16", gpu_memory_utilization=0.85,
               trust_remote_code=True, max_model_len=4096)

    run_eval(args.condition, rows, index, tok, llm, args.output_dir)


if __name__ == "__main__":
    main()
