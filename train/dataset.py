# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Dataset for preference pair training (chosen/rejected).

parquet schema：
  chosen_messages:   JSON string, list of messages ([{"role":..., "content":...}, ...])
  rejected_messages: JSON string, list of messages

__getitem__ returns 8 tensors (4 each for chosen and rejected):
  chosen_input_ids, chosen_attention_mask, chosen_position_ids, chosen_loss_mask
  rejected_input_ids, rejected_attention_mask, rejected_position_ids, rejected_loss_mask

loss_mask is 1 only at assistant token positions, 0 elsewhere (user/tool/padding).
"""

import json
from typing import List, Union

import pandas as pd
import torch
from torch.utils.data import Dataset
from transformers import PreTrainedTokenizer

from verl.utils import hf_tokenizer
from verl.utils.fs import copy_local_path_from_hdfs


class DPODataset(Dataset):
    """
    Dataset for DPO training with chosen/rejected preference pairs.
    Reuses MultiTurnSFTDataset's tokenization and loss_mask logic.
    """

    def __init__(self, parquet_files: Union[str, List[str]], tokenizer, config=None):
        config = config or {}
        self.config = config
        self.truncation = config.get("truncation", "left")  # left truncation by default, preserves tail
        self.max_length = config.get("max_length", 2048)
        self.chosen_key = config.get("chosen_key", "chosen_messages")
        self.rejected_key = config.get("rejected_key", "rejected_messages")

        assert self.truncation in ["error", "left", "right"]

        if not isinstance(parquet_files, list):
            parquet_files = [parquet_files]
        self.parquet_files = parquet_files

        if isinstance(tokenizer, str):
            tokenizer = hf_tokenizer(tokenizer)
        self.tokenizer: PreTrainedTokenizer = tokenizer

        self._download()
        self._read_files_and_process()

    def _download(self):
        for i, parquet_file in enumerate(self.parquet_files):
            self.parquet_files[i] = copy_local_path_from_hdfs(parquet_file, verbose=True)

    def _read_files_and_process(self):
        dataframes = []
        for parquet_file in self.parquet_files:
            dataframes.append(pd.read_parquet(parquet_file))
        self.dataframe = pd.concat(dataframes, ignore_index=True)

        # Parse JSON string to messages list
        self.chosen_messages = [
            json.loads(s) for s in self.dataframe[self.chosen_key].tolist()
        ]
        self.rejected_messages = [
            json.loads(s) for s in self.dataframe[self.rejected_key].tolist()
        ]
        # Read precomputed branch_msg_idx (required for entropy data; None for vanilla data)
        if 'branch_msg_idx' in self.dataframe.columns:
            self.branch_msg_indices = self.dataframe['branch_msg_idx'].tolist()
        else:
            self.branch_msg_indices = [None] * len(self.chosen_messages)
        # rejected may have its own branch_msg_idx (when chosen/rejected prefixes differ in length)
        if 'rejected_branch_msg_idx' in self.dataframe.columns:
            self.rejected_branch_msg_indices = self.dataframe['rejected_branch_msg_idx'].tolist()
        else:
            self.rejected_branch_msg_indices = [None] * len(self.chosen_messages)
        # Read source field for gradient analysis (vanilla vs entropy grouping)
        if 'source' in self.dataframe.columns:
            self.sources = self.dataframe['source'].tolist()
        else:
            self.sources = ['unknown'] * len(self.chosen_messages)

    def __len__(self):
        return len(self.chosen_messages)

    def _tokenize_messages(self, messages: list, branch_msg_idx: int = 0,
                           branch_turn_only: bool = True,
                           branch_turn_n: int = 0) -> dict:
        """
        Tokenize a messages list and return input_ids/attention_mask/position_ids/loss_mask.

        Three masking strategies:
        - branch_turn_only=True: mask only the branch turn's assistant tokens (most precise, weakest gradient)
        - branch_turn_only=False, branch_turn_n=0: all assistant tokens after branch (broadest)
        - branch_turn_only=False, branch_turn_n=N (N>0): assistant tokens within first N user-turns after branch
          (N=3 balances signal/noise: covers decision + short-term consequences)
        """
        tokenizer = self.tokenizer

        full_tokens = tokenizer.apply_chat_template(
            messages, tokenize=True, return_tensors="pt", add_generation_prompt=False
        )
        input_ids = full_tokens[0]
        attention_mask = torch.ones_like(input_ids)
        loss_mask = torch.zeros_like(input_ids, dtype=torch.long)

        if branch_turn_only and branch_msg_idx > 0:
            # Train only on branch-turn assistant tokens
            # BFCL format: branch may have 2 consecutive user messages; skip extra user to find assistant
            branch_assistant_indices = []
            seen_first_assistant = False
            for i in range(branch_msg_idx, len(messages)):
                role = messages[i].get("role")
                if role == "assistant":
                    branch_assistant_indices.append(i)
                    seen_first_assistant = True
                elif role == "user" and i > branch_msg_idx and seen_first_assistant:
                    break
            target_indices = set(branch_assistant_indices)
        elif branch_turn_n > 0 and branch_msg_idx > 0:
            # Train on assistant tokens within first N user-turns after branch
            # BFCL format: each turn may start with 2 consecutive user messages
            # ("I have updated..." notification + actual user question)
            # branch_msg_idx points to 1st user (notification); 2nd user does not count as new turn
            # A new turn starts only after the first assistant message appears
            target_indices = set()
            turn_count = 0
            seen_first_assistant = False
            for i in range(branch_msg_idx, len(messages)):
                role = messages[i].get("role")
                if role == "user" and i > branch_msg_idx:
                    if seen_first_assistant:
                        turn_count += 1
                        if turn_count >= branch_turn_n:
                            break
                elif role == "assistant":
                    seen_first_assistant = True
                    target_indices.add(i)
        else:
            # All assistant tokens after branch
            target_indices = set(
                i for i, msg in enumerate(messages)
                if msg.get("role") == "assistant" and i >= branch_msg_idx
            )

        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
            if i not in target_indices:
                continue
            prefix_tokens = tokenizer.apply_chat_template(
                messages[: i + 1], tokenize=True, return_tensors="pt", add_generation_prompt=False
            )
            prev_tokens = (
                tokenizer.apply_chat_template(
                    messages[:i], tokenize=True, return_tensors="pt", add_generation_prompt=False
                )
                if i > 0
                else None
            )
            start_pos = prev_tokens[0].shape[0] if prev_tokens is not None else 0
            end_pos = prefix_tokens[0].shape[0]
            loss_mask[start_pos:end_pos] = 1

        # Handle sequence length
        seq_len = input_ids.shape[0]
        pad_id = self.tokenizer.pad_token_id if self.tokenizer.pad_token_id is not None else 0

        if seq_len < self.max_length:
            pad_len = self.max_length - seq_len
            input_ids = torch.cat([input_ids, torch.full((pad_len,), pad_id, dtype=input_ids.dtype)])
            attention_mask = torch.cat([attention_mask, torch.zeros(pad_len, dtype=attention_mask.dtype)])
            loss_mask = torch.cat([loss_mask, torch.zeros(pad_len, dtype=loss_mask.dtype)])
        elif seq_len > self.max_length:
            if self.truncation == "left":
                input_ids = input_ids[-self.max_length:]
                attention_mask = attention_mask[-self.max_length:]
                loss_mask = loss_mask[-self.max_length:]
            elif self.truncation == "right":
                input_ids = input_ids[: self.max_length]
                attention_mask = attention_mask[: self.max_length]
                loss_mask = loss_mask[: self.max_length]
            else:
                raise ValueError(f"{seq_len=} > {self.max_length=}, truncation='error'")

        position_ids = torch.arange(len(input_ids), dtype=torch.long) * attention_mask

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "position_ids": position_ids,
            "loss_mask": loss_mask,
        }

    @staticmethod
    def _trim_prefix(msgs: list, branch_msg_idx: int, context_turns: int = 1) -> list:
        """
        Shorten prefix: keep system + skill_reminder + N most recent turns before branch + content after branch.

        context_turns=3: keep 3 most recent turns before branch for context,
        while substantially reducing sequence length (removes earlier verbose turns).

        Do not strip <think> content: thinking tokens are part of model reasoning;
        removing them causes train/inference distribution mismatch.
        """
        result = []

        # 1. Keep system and skill_reminder messages
        for m in msgs:
            role = m.get('role', '')
            if role == 'system':
                result.append(m)
            elif role == 'user' and '<system-reminder>' in (m.get('content') or ''):
                result.append(m)
            else:
                break

        # 2. Find N most recent turns before branch (1 turn = 1 user message + subsequent assistant/tool)
        prefix_msgs = msgs[:branch_msg_idx]
        # Find user message positions (excluding skill_reminder)
        user_indices = [i for i, m in enumerate(prefix_msgs)
                        if m.get('role') == 'user'
                        and '<system-reminder>' not in (m.get('content') or '')]
        # Take the starting positions of the most recent context_turns user turns
        if len(user_indices) > context_turns:
            start_idx = user_indices[-context_turns]
        elif user_indices:
            start_idx = user_indices[0]
        else:
            start_idx = branch_msg_idx  # no user turn found; start from branch directly

        result.extend(prefix_msgs[start_idx:])

        # 3. Append from branch point onwards
        result.extend(msgs[branch_msg_idx:])
        return result

    def __getitem__(self, item):
        chosen_msgs = self.chosen_messages[item]
        rejected_msgs = self.rejected_messages[item]

        # Use precomputed branch_msg_idx when available
        stored_idx = self.branch_msg_indices[item]
        is_skill_fix = stored_idx is not None and not (isinstance(stored_idx, float) and stored_idx != stored_idx)

        if is_skill_fix:
            # entropy passK / skill_fix data: has explicit branch point
            # branch_turn_n from config (default 3): train on N turns of assistant tokens after branch
            # N=1: only branch turn (most precise, weakest gradient)
            # N=3: 3 turns after branch (balanced signal/noise, default)
            # N=0: all turns after branch (strongest gradient, most noise)
            chosen_branch_idx = int(stored_idx)
            # rejected may have its own branch_msg_idx
            rej_stored = self.rejected_branch_msg_indices[item]
            rej_is_valid = rej_stored is not None and not (isinstance(rej_stored, float) and rej_stored != rej_stored)
            rejected_branch_idx = int(rej_stored) if rej_is_valid else chosen_branch_idx
            branch_turn_only = False
            branch_turn_n = self.config.get("branch_turn_n", 3)
        else:
            # vanilla data: two distinct trajectories, train on full trajectory
            chosen_branch_idx = 0
            for i, (c, r) in enumerate(zip(chosen_msgs, rejected_msgs)):
                if c != r:
                    chosen_branch_idx = i
                    break
            rejected_branch_idx = chosen_branch_idx
            branch_turn_only = False
            branch_turn_n = 0

        chosen = self._tokenize_messages(chosen_msgs, branch_msg_idx=chosen_branch_idx,
                                         branch_turn_only=branch_turn_only,
                                         branch_turn_n=branch_turn_n)
        rejected = self._tokenize_messages(rejected_msgs, branch_msg_idx=rejected_branch_idx,
                                           branch_turn_only=branch_turn_only,
                                           branch_turn_n=branch_turn_n)

        src = self.sources[item]
        is_entropy = int(src not in ('vanilla_easy', 'vanilla_hard') and 'vanilla' not in src)

        return {
            "chosen_input_ids":       chosen["input_ids"],
            "chosen_attention_mask":  chosen["attention_mask"],
            "chosen_position_ids":    chosen["position_ids"],
            "chosen_loss_mask":       chosen["loss_mask"],
            "rejected_input_ids":     rejected["input_ids"],
            "rejected_attention_mask": rejected["attention_mask"],
            "rejected_position_ids":  rejected["position_ids"],
            "rejected_loss_mask":     rejected["loss_mask"],
            "is_entropy":             torch.tensor(is_entropy, dtype=torch.long),
        }
