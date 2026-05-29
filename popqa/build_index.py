#!/usr/bin/env python3
"""
Build title→passages index from Tevatron Wikipedia NQ corpus.
Required for PopQA Wikipedia lookup skills.

Download corpus: https://huggingface.co/datasets/Tevatron/wikipedia-nq-corpus

Usage:
    python popqa/build_index.py \
        --corpus /path/to/corpus.jsonl.gz \
        --output popqa/title_index.json.gz
"""
import argparse, gzip, json, sys
from collections import defaultdict
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--corpus', required=True, help='Path to corpus.jsonl.gz')
parser.add_argument('--output', default='popqa/title_index.json.gz')
parser.add_argument('--popqa-tsv', default=None,
                    help='Optional: PopQA test.tsv to filter index to only needed titles. '
                         'Download from https://huggingface.co/datasets/akariasai/PopQA')
args = parser.parse_args()

CORPUS  = Path(args.corpus)
OUT     = Path(args.output)
MAX_PER_TITLE = 5  # max passages per title (~500 words each)

print("Building title index...")
index = defaultdict(list)
n = 0
with gzip.open(CORPUS, 'rt') as f:
    for line in f:
        d = json.loads(line)
        title = d['title']
        if len(index[title]) < MAX_PER_TITLE:
            index[title].append(d['text'])
        n += 1
        if n % 2000000 == 0:
            print(f"  {n//1000000}M passages processed, {len(index):,} titles")

print(f"Done. {len(index):,} unique titles")

# Optionally filter to only titles needed by PopQA (greatly reduces file size)
if args.popqa_tsv:
    import pandas as pd
    popqa = pd.read_csv(args.popqa_tsv, sep='\t')
    needed_titles = set(popqa['s_wiki_title'].dropna())
    filtered = {t: v for t, v in index.items() if t in needed_titles}
    print(f"Filtered to PopQA titles: {len(filtered):,} / {len(needed_titles):,}")
else:
    filtered = index
    print(f"No filtering applied, keeping all {len(filtered):,} titles")

print(f"Saving to {OUT}...")
with gzip.open(OUT, 'wt') as f:
    json.dump(filtered, f)
print("Done.")
