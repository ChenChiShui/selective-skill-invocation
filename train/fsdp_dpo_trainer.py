# Copyright 2024 Bytedance Ltd. and/or its affiliates
#
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
FSDP DPO Trainer — adapted from fsdp_sft_trainer.py.

Key changes:
  1. Replace MultiTurnSFTDataset with DPODataset (chosen/rejected pairs)
  2. Replace _compute_loss_and_backward with DPO loss (sigmoid)
  3. Load frozen ref model in __init__ for reference log prob computation

Usage:
  torchrun --nproc_per_node=N -m verl.trainer.fsdp_dpo_trainer \
    model.partial_pretrain=<sft_checkpoint> \
    model.ref_path=<sft_checkpoint> \
    data.train_files=<dpo_pairs.parquet> \
    data.val_files=<dpo_pairs_val.parquet> \
    dpo.beta=0.1 \
    ...
"""

import os

os.environ["NCCL_DEBUG"] = "WARN"
os.environ["TOKENIZERS_PARALLELISM"] = "true"

import logging
import re
from contextlib import nullcontext

import hydra
import torch
import torch.distributed
import torch.nn.functional as F
from tensordict import TensorDict
from torch import nn, optim
from torch.distributed.device_mesh import DeviceMesh, init_device_mesh
from torch.distributed.fsdp import CPUOffload, MixedPrecision, ShardingStrategy
from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
from torch.utils.data import DataLoader, Dataset, DistributedSampler
from tqdm import tqdm
from transformers import AutoConfig, AutoModelForCausalLM, PreTrainedModel

import verl.utils.hdfs_io as hdfs_io
from verl.utils.dataset.dpo_dataset import DPODataset
from verl.utils.debug import log_gpu_memory_usage
from verl.utils.distributed import initialize_global_process_group
from verl.utils.fs import copy_to_local
from verl.utils.fsdp_utils import (
    CPUOffloadPolicy,
    MixedPrecisionPolicy,
    apply_fsdp2,
    fsdp2_load_full_state_dict,
    get_fsdp_wrap_policy,
    get_init_weight_context_manager,
    init_fn,
    fsdp2_clip_grad_norm_,
)
from verl.utils.torch_functional import get_cosine_schedule_with_warmup
from verl.utils.py_functional import convert_to_regular_types
from verl.utils.tracking import Tracking
from verl.utils.device import get_device_name, get_torch_device, is_cuda_available, is_npu_available
from verl.workers.sharding_manager.fsdp_ulysses import FSDPUlyssesShardingManager

logger = logging.getLogger(__file__)
logger.setLevel(os.getenv("VERL_DPO_LOGGING_LEVEL", "WARN"))


def extract_step(path):
    match = re.search(r"global_step_(\d+)", path)
    if match:
        return int(match.group(1))
    return None


def compute_sequence_log_probs(logits: torch.Tensor, input_ids: torch.Tensor, loss_mask: torch.Tensor) -> torch.Tensor:
    """
    Compute per-sequence average log probability (over assistant tokens only).

    Args:
        logits: (batch, seq_len, vocab_size)
        input_ids: (batch, seq_len)
        loss_mask: (batch, seq_len), 1 at assistant token positions

    Returns:
        log_probs: (batch,), per-sequence average log prob
    """
    # shift: logits[t] predicts token[t+1]
    # chunked computation to avoid OOM with large tensors (16384 × vocab_size ≈ 9GB)
    shift_labels = input_ids[:, 1:].contiguous()      # (batch, seq_len-1)
    shift_mask = loss_mask[:, 1:].contiguous().float() # (batch, seq_len-1)
    batch_size = logits.size(0)
    seq_len = logits.size(1) - 1  # shifted length
    vocab_size = logits.size(2)

    chunk_size = 1024  # ~0.6GB per chunk (1024 × 152064 × 4 bytes)
    masked_log_probs = torch.zeros(batch_size, device=logits.device, dtype=torch.float32)
    valid_tokens = torch.zeros(batch_size, device=logits.device, dtype=torch.float32)

    for start in range(0, seq_len, chunk_size):
        end = min(start + chunk_size, seq_len)
        # slice directly, avoid global contiguous call
        chunk_logits = logits[:, start:end, :].reshape(-1, vocab_size)
        chunk_labels = shift_labels[:, start:end].reshape(-1)
        chunk_mask = shift_mask[:, start:end]  # (batch, chunk)

        chunk_lp = -F.cross_entropy(chunk_logits, chunk_labels, reduction="none")
        chunk_lp = chunk_lp.view(batch_size, -1)  # (batch, chunk)

        masked_log_probs += (chunk_lp * chunk_mask).sum(dim=-1)
        valid_tokens += chunk_mask.sum(dim=-1)

        del chunk_logits, chunk_lp

    valid_tokens = valid_tokens.clamp(min=1e-8)
    return masked_log_probs / valid_tokens


class FSDPDPOTrainer:
    def __init__(
        self,
        config,
        device_mesh: DeviceMesh,
        ulysses_device_mesh: DeviceMesh,
        tokenizer,
        train_dataset: Dataset,
        val_dataset: Dataset,
    ):
        self.config = config
        self.device_mesh = device_mesh
        self.ulysses_device_mesh = ulysses_device_mesh
        self.sharding_manager = FSDPUlyssesShardingManager(self.ulysses_device_mesh)
        self.tokenizer = tokenizer

        # DPO hyperparameters (use OmegaConf.select for safe access in struct mode)
        from omegaconf import OmegaConf
        self.beta = float(OmegaConf.select(config, "dpo.beta", default=0.1))

        self._normalize_config_bsz()
        self.config.ulysses_sequence_parallel_size = getattr(self.config, "ulysses_sequence_parallel_size", 1)
        self.use_remove_padding = getattr(self.config, "use_remove_padding", False)

        if self.device_mesh.get_rank() == 0:
            print(f"[DPO] beta={self.beta}")
            print(f"[DPO] sequence parallel size: {self.config.ulysses_sequence_parallel_size}")

        self._build_dataloader(train_dataset, val_dataset)
        self._build_model_optimizer()

        if self.device_mesh.get_rank() == 0:
            print(self.config)
        self.device_name = get_device_name()

    def _normalize_config_bsz(self):
        dp_size = self.device_mesh.size(0) if not self.ulysses_device_mesh else self.ulysses_device_mesh.size(0)
        assert self.config.data.train_batch_size % dp_size == 0
        self.config.data.train_batch_size //= dp_size
        assert self.config.data.train_batch_size % self.config.data.micro_batch_size_per_gpu == 0

    def _build_dataloader(self, train_dataset, val_dataset):
        config = self.config
        self.train_dataset, self.val_dataset = train_dataset, val_dataset

        if self.config.ulysses_sequence_parallel_size > 1:
            rank = self.ulysses_device_mesh.get_local_rank("dp")
            world_size = self.ulysses_device_mesh.size(0)
        else:
            rank = self.device_mesh.get_rank()
            world_size = self.device_mesh.size()

        self.train_sampler = DistributedSampler(self.train_dataset, shuffle=True, num_replicas=world_size, rank=rank, drop_last=True)
        self.train_dataloader = DataLoader(
            dataset=self.train_dataset,
            batch_size=config.data.train_batch_size,
            sampler=self.train_sampler,
            num_workers=4,
            pin_memory=True,
            drop_last=True,
        )

        self.val_sampler = DistributedSampler(self.val_dataset, shuffle=False, num_replicas=world_size, rank=rank, drop_last=True)
        self.val_dataloader = DataLoader(
            dataset=self.val_dataset,
            batch_size=config.data.micro_batch_size_per_gpu,
            sampler=self.val_sampler,
            num_workers=4,
            pin_memory=True,
            drop_last=True,
        )

    def _build_model_optimizer(self):
        local_model_path = copy_to_local(src=self.config.model.partial_pretrain, verbose=True)

        log_gpu_memory_usage("Before model allocation", logger=logger)
        trust_remote_code = self.config.model.trust_remote_code
        config = AutoConfig.from_pretrained(local_model_path, trust_remote_code=trust_remote_code)
        self.model_config = config

        init_context = get_init_weight_context_manager(use_meta_tensor=not config.tie_word_embeddings, mesh=self.device_mesh)

        # ── Policy model (trainable) ──────────────────────────────────────────
        with init_context():
            self.model: PreTrainedModel = AutoModelForCausalLM.from_pretrained(
                local_model_path,
                config=config,
                torch_dtype=torch.bfloat16,
                attn_implementation="sdpa",
                trust_remote_code=trust_remote_code,
            )
            if self.config.model.enable_gradient_checkpointing:
                self.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})

        log_gpu_memory_usage("After policy model allocation", logger=logger)

        # ── Reference model (frozen) ──────────────────────────────────────────
        from omegaconf import OmegaConf
        ref_path = OmegaConf.select(self.config, "model.ref_path", default=local_model_path)
        local_ref_path = copy_to_local(src=ref_path, verbose=True)
        with init_context():
            self.ref_model: PreTrainedModel = AutoModelForCausalLM.from_pretrained(
                local_ref_path,
                config=AutoConfig.from_pretrained(local_ref_path, trust_remote_code=trust_remote_code),
                torch_dtype=torch.bfloat16,
                attn_implementation="sdpa",
                trust_remote_code=trust_remote_code,
            )
        # ref model fully frozen
        for p in self.ref_model.parameters():
            p.requires_grad_(False)

        log_gpu_memory_usage("After ref model allocation", logger=logger)

        # ── FSDP wrapping ────────────────────────────────────────────────────
        mixed_precision = MixedPrecision(param_dtype=torch.bfloat16, reduce_dtype=torch.float32, buffer_dtype=torch.float32)
        auto_wrap_policy = get_fsdp_wrap_policy(self.model, config=self.config.model.fsdp_config.wrap_policy, is_lora=False)

        cpu_offload = CPUOffload(offload_params=self.config.model.fsdp_config.offload_params) if self.config.model.fsdp_config.cpu_offload else None

        fsdp_strategy = self.config.model.strategy

        if fsdp_strategy == "fsdp":
            self.fsdp_model = FSDP(
                self.model,
                cpu_offload=cpu_offload,
                param_init_fn=init_fn,
                use_orig_params=False,
                auto_wrap_policy=auto_wrap_policy,
                device_id=get_torch_device().current_device(),
                sharding_strategy=ShardingStrategy.FULL_SHARD,
                mixed_precision=mixed_precision,
                sync_module_states=True,
                device_mesh=self.device_mesh,
                forward_prefetch=False,
            )
            self.fsdp_ref_model = FSDP(
                self.ref_model,
                cpu_offload=cpu_offload,
                param_init_fn=init_fn,
                use_orig_params=False,
                auto_wrap_policy=get_fsdp_wrap_policy(self.ref_model, config=self.config.model.fsdp_config.wrap_policy, is_lora=False),
                device_id=get_torch_device().current_device(),
                sharding_strategy=ShardingStrategy.FULL_SHARD,
                mixed_precision=mixed_precision,
                sync_module_states=True,
                device_mesh=self.device_mesh,
                forward_prefetch=False,
            )
        elif fsdp_strategy == "fsdp2":
            mp_policy = MixedPrecisionPolicy(param_dtype=torch.bfloat16, reduce_dtype=torch.float32, cast_forward_inputs=True)
            fsdp_kwargs = {"mesh": self.device_mesh, "mp_policy": mp_policy, "offload_policy": cpu_offload, "reshard_after_forward": True}

            full_state = self.model.state_dict()
            apply_fsdp2(self.model, fsdp_kwargs, self.config.model.fsdp_config)
            fsdp2_load_full_state_dict(self.model, full_state, self.device_mesh, cpu_offload)
            del full_state
            torch.cuda.empty_cache()
            self.fsdp_model = self.model

            ref_full_state = self.ref_model.state_dict()
            apply_fsdp2(self.ref_model, fsdp_kwargs, self.config.model.fsdp_config)
            fsdp2_load_full_state_dict(self.ref_model, ref_full_state, self.device_mesh, cpu_offload)
            del ref_full_state
            torch.cuda.empty_cache()
            self.fsdp_ref_model = self.ref_model
        else:
            raise NotImplementedError(f"not implement {fsdp_strategy}")

        log_gpu_memory_usage("After FSDP wrapping", logger=logger)

        self.optimizer = optim.AdamW(
            self.fsdp_model.parameters(),
            lr=self.config.optim.lr,
            betas=self.config.optim.betas,
            weight_decay=self.config.optim.weight_decay,
        )

        self.steps_per_epoch = len(self.train_dataloader)
        self.total_steps = self.steps_per_epoch * self.config.trainer.total_epochs
        if self.config.trainer.total_training_steps is not None:
            self.total_steps = self.config.trainer.total_training_steps

        num_warmup_steps = int(self.total_steps * self.config.optim.warmup_steps_ratio)
        self.lr_scheduler = get_cosine_schedule_with_warmup(
            optimizer=self.optimizer, num_warmup_steps=num_warmup_steps, num_training_steps=self.total_steps
        )

        if self.device_mesh.get_rank() == 0:
            print(f"[DPO] steps/epoch={self.steps_per_epoch}, total_steps={self.total_steps}")

    def _compute_dpo_loss(self, batch, do_backward=True):
        """
        Compute DPO loss (sigmoid).

        batch contains:
          chosen_input_ids, chosen_attention_mask, chosen_position_ids, chosen_loss_mask
          rejected_input_ids, rejected_attention_mask, rejected_position_ids, rejected_loss_mask
        """
        # concatenate chosen + rejected for a single forward pass
        input_ids = torch.cat([
            batch["chosen_input_ids"].to(self.device_name),
            batch["rejected_input_ids"].to(self.device_name),
        ], dim=0)
        attention_mask = torch.cat([
            batch["chosen_attention_mask"].to(self.device_name),
            batch["rejected_attention_mask"].to(self.device_name),
        ], dim=0)
        position_ids = torch.cat([
            batch["chosen_position_ids"].to(self.device_name),
            batch["rejected_position_ids"].to(self.device_name),
        ], dim=0)
        loss_mask = torch.cat([
            batch["chosen_loss_mask"].to(self.device_name),
            batch["rejected_loss_mask"].to(self.device_name),
        ], dim=0)

        with torch.autocast(device_type=self.device_name, dtype=torch.bfloat16):
            # Policy log probs
            self.fsdp_model.train()
            policy_logits = self.fsdp_model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                position_ids=position_ids,
                use_cache=False,
            ).logits
            policy_log_probs = compute_sequence_log_probs(policy_logits, input_ids, loss_mask)
            del policy_logits  # free immediately before ref model forward
            torch.cuda.empty_cache()

            # Reference log probs (frozen, no_grad)
            self.fsdp_ref_model.eval()
            with torch.no_grad():
                ref_logits = self.fsdp_ref_model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    position_ids=position_ids,
                    use_cache=False,
                ).logits
            ref_log_probs = compute_sequence_log_probs(ref_logits, input_ids, loss_mask)
            del ref_logits  # free immediately
            torch.cuda.empty_cache()

        bsz = input_ids.size(0) // 2
        chosen_policy_lp = policy_log_probs[:bsz]
        rejected_policy_lp = policy_log_probs[bsz:]
        chosen_ref_lp = ref_log_probs[:bsz]
        rejected_ref_lp = ref_log_probs[bsz:]

        # DPO loss
        logits_dpo = self.beta * (
            (chosen_policy_lp - chosen_ref_lp) - (rejected_policy_lp - rejected_ref_lp)
        )
        loss = -F.logsigmoid(logits_dpo).mean()

        # Additional metrics
        with torch.no_grad():
            chosen_rewards = self.beta * (chosen_policy_lp - chosen_ref_lp)
            rejected_rewards = self.beta * (rejected_policy_lp - rejected_ref_lp)
            reward_margin = (chosen_rewards - rejected_rewards).mean()
            accuracy = (chosen_rewards > rejected_rewards).float().mean()

        if do_backward:
            loss.backward()

        return loss, {
            "dpo/reward_margin": reward_margin.item(),
            "dpo/accuracy": accuracy.item(),
            "dpo/chosen_reward": chosen_rewards.mean().item(),
            "dpo/rejected_reward": rejected_rewards.mean().item(),
        }

    def _get_grad_norm(self):
        """Compute L2 norm of current parameter gradients (before clipping)."""
        total = 0.0
        for p in self.fsdp_model.parameters():
            if p.grad is not None:
                total += float(p.grad.detach().float().norm()) ** 2
        return float(total ** 0.5)

    def training_step(self, batch: TensorDict):
        self.optimizer.zero_grad()

        micro_batches = batch.split(self.config.data.micro_batch_size_per_gpu)
        n_micro_batches = len(micro_batches)
        step_loss = 0
        step_metrics = {}

        vanilla_margins, entropy_margins = [], []
        vanilla_accs, entropy_accs = [], []
        vanilla_grad_norms, entropy_grad_norms = [], []

        for idx, micro_batch in enumerate(micro_batches):
            loss, metrics = self._compute_dpo_loss(micro_batch, do_backward=False)
            (loss / n_micro_batches).backward()
            step_loss += loss.item()
            for k, v in metrics.items():
                step_metrics[k] = step_metrics.get(k, 0) + v / n_micro_batches

            # record gradient norm after backward
            grad_norm_cur = self._get_grad_norm()

            # group statistics by is_entropy flag
            if "is_entropy" in micro_batch.keys():
                is_ent = micro_batch["is_entropy"].bool().cpu().any().item()
                margin = metrics["dpo/reward_margin"]
                acc    = metrics["dpo/accuracy"]
                if is_ent:
                    entropy_margins.append(margin)
                    entropy_accs.append(acc)
                    entropy_grad_norms.append(grad_norm_cur)
                else:
                    vanilla_margins.append(margin)
                    vanilla_accs.append(acc)
                    vanilla_grad_norms.append(grad_norm_cur)

        if vanilla_margins:
            step_metrics["dpo/vanilla_reward_margin"] = sum(vanilla_margins) / len(vanilla_margins)
            step_metrics["dpo/vanilla_accuracy"]      = sum(vanilla_accs)    / len(vanilla_accs)
            step_metrics["dpo/vanilla_grad_norm"]     = sum(vanilla_grad_norms) / len(vanilla_grad_norms)
        if entropy_margins:
            step_metrics["dpo/entropy_reward_margin"] = sum(entropy_margins) / len(entropy_margins)
            step_metrics["dpo/entropy_accuracy"]      = sum(entropy_accs)    / len(entropy_accs)
            step_metrics["dpo/entropy_grad_norm"]     = sum(entropy_grad_norms) / len(entropy_grad_norms)

        if self.config.model.strategy == "fsdp":
            grad_norm = self.fsdp_model.clip_grad_norm_(max_norm=self.config.optim.clip_grad)
        elif self.config.model.strategy == "fsdp2":
            grad_norm = fsdp2_clip_grad_norm_(self.fsdp_model.parameters(), max_norm=self.config.optim.clip_grad)
        else:
            raise NotImplementedError

        if not torch.isfinite(grad_norm):
            print(f"WARN: grad_norm is not finite: {grad_norm}")
            self.optimizer.zero_grad()
        else:
            self.optimizer.step()

        self.lr_scheduler.step()
        lr = self.lr_scheduler.get_last_lr()[0]

        step_loss_tensor = torch.tensor(step_loss).to(self.device_name)
        if is_cuda_available:
            torch.distributed.all_reduce(step_loss_tensor, op=torch.distributed.ReduceOp.AVG)

        return {"train/loss": step_loss_tensor.item(), "train/lr(1e-3)": lr * 1e3, **step_metrics}

    def validation_step(self, batch: TensorDict):
        self.fsdp_model.eval()
        with torch.no_grad():
            loss, _ = self._compute_dpo_loss(batch, do_backward=False)
            if is_cuda_available:
                torch.distributed.all_reduce(loss, op=torch.distributed.ReduceOp.AVG)
        return loss

    def save_checkpoint(self, step):
        path = os.path.join(self.config.trainer.default_local_dir, f"global_step_{step}")
        fsdp_strategy = self.config.model.strategy

        if fsdp_strategy == "fsdp":
            from torch.distributed.fsdp import FullStateDictConfig, StateDictType
            cfg = FullStateDictConfig(offload_to_cpu=True, rank0_only=True)
            with FSDP.state_dict_type(self.fsdp_model, StateDictType.FULL_STATE_DICT, cfg):
                state_dict = self.fsdp_model.state_dict()
            if self.device_mesh.get_rank() == 0:
                os.makedirs(path, exist_ok=True)
                self.model.save_pretrained(path, state_dict=state_dict)
                self.tokenizer.save_pretrained(path)
        elif fsdp_strategy == "fsdp2":
            from torch.distributed.checkpoint.state_dict import StateDictOptions, get_model_state_dict
            options = StateDictOptions(full_state_dict=True, cpu_offload=True)
            state_dict = get_model_state_dict(self.fsdp_model, options=options)
            if self.device_mesh.get_rank() == 0:
                os.makedirs(path, exist_ok=True)
                self.model.save_pretrained(path, state_dict=state_dict)
                self.model_config.save_pretrained(path)
                self.tokenizer.save_pretrained(path)

        if self.device_mesh.get_rank() == 0 and self.config.trainer.default_hdfs_dir:
            hdfs_io.makedirs(self.config.trainer.default_hdfs_dir, exist_ok=True)
            hdfs_io.copy(src=path, dst=self.config.trainer.default_hdfs_dir, dirs_exist_ok=True)

        torch.distributed.barrier()

    def fit(self):
        rank = self.device_mesh.get_rank()
        if rank == 0:
            tracking = Tracking(
                project_name=self.config.trainer.project_name,
                experiment_name=self.config.trainer.experiment_name,
                default_backend=self.config.trainer.logger,
            )

        global_step = 0
        self.total_training_steps = self.total_steps
        print(f"[DPO] Total training steps: {self.total_training_steps}")

        for epoch in range(self.config.trainer.total_epochs):
            self.train_sampler.set_epoch(epoch=epoch)
            epoch_vanilla_margins, epoch_entropy_margins = [], []
            epoch_vanilla_accs, epoch_entropy_accs = [], []
            epoch_vanilla_grad_norms, epoch_entropy_grad_norms = [], []

            for data in tqdm(
                self.train_dataloader,
                total=self.steps_per_epoch,
                desc=f"Epoch {epoch + 1}/{self.config.trainer.total_epochs}",
                disable=rank != 0,
            ):
                global_step += 1
                data = TensorDict(data, batch_size=self.config.data.train_batch_size).to(self.device_name)
                metric = self.training_step(data)
                if rank == 0:
                    tracking.log(data=metric, step=global_step)
                # collect epoch-level grouped statistics
                if "dpo/vanilla_reward_margin" in metric:
                    epoch_vanilla_margins.append(metric["dpo/vanilla_reward_margin"])
                    epoch_vanilla_accs.append(metric["dpo/vanilla_accuracy"])
                if "dpo/entropy_reward_margin" in metric:
                    epoch_entropy_margins.append(metric["dpo/entropy_reward_margin"])
                    epoch_entropy_accs.append(metric["dpo/entropy_accuracy"])
                if "dpo/vanilla_grad_norm" in metric:
                    epoch_vanilla_grad_norms.append(metric["dpo/vanilla_grad_norm"])
                if "dpo/entropy_grad_norm" in metric:
                    epoch_entropy_grad_norms.append(metric["dpo/entropy_grad_norm"])

                if global_step >= self.total_training_steps:
                    val_losses = []
                    for val_data in self.val_dataloader:
                        val_data = TensorDict(val_data, batch_size=self.config.data.micro_batch_size_per_gpu).to(self.device_name)
                        val_losses.append(self.validation_step(val_data))
                    if rank == 0:
                        avg_val_loss = torch.mean(torch.stack(val_losses))
                        tracking.log(data={"val/loss": avg_val_loss.item()}, step=global_step)
                    torch.distributed.barrier()
                    self.save_checkpoint(step=global_step)
                    return

            val_losses = []
            for data in self.val_dataloader:
                data = TensorDict(data, batch_size=self.config.data.micro_batch_size_per_gpu).to(self.device_name)
                val_losses.append(self.validation_step(data))
            if rank == 0:
                tracking.log(data={"val/loss": torch.mean(torch.stack(val_losses)).item()}, step=global_step)
                # epoch-level gradient analysis summary
                epoch_grad_log = {}
                if epoch_vanilla_margins:
                    epoch_grad_log["epoch/vanilla_reward_margin"] = sum(epoch_vanilla_margins) / len(epoch_vanilla_margins)
                    epoch_grad_log["epoch/vanilla_accuracy"]      = sum(epoch_vanilla_accs)    / len(epoch_vanilla_accs)
                if epoch_entropy_margins:
                    epoch_grad_log["epoch/entropy_reward_margin"] = sum(epoch_entropy_margins) / len(epoch_entropy_margins)
                    epoch_grad_log["epoch/entropy_accuracy"]      = sum(epoch_entropy_accs)    / len(epoch_entropy_accs)
                if epoch_vanilla_grad_norms:
                    epoch_grad_log["epoch/vanilla_grad_norm"] = sum(epoch_vanilla_grad_norms) / len(epoch_vanilla_grad_norms)
                if epoch_entropy_grad_norms:
                    epoch_grad_log["epoch/entropy_grad_norm"] = sum(epoch_entropy_grad_norms) / len(epoch_entropy_grad_norms)
                if epoch_grad_log:
                    tracking.log(data=epoch_grad_log, step=global_step)
                    def _fmt(v):
                        try: return f"{float(v):.4f}"
                        except: return str(v)
                    print(f"[Epoch {epoch+1}] "
                          f"vanilla_margin={_fmt(epoch_grad_log.get('epoch/vanilla_reward_margin', 0))}  "
                          f"entropy_margin={_fmt(epoch_grad_log.get('epoch/entropy_reward_margin', 0))}  "
                          f"vanilla_grad={_fmt(epoch_grad_log.get('epoch/vanilla_grad_norm', 0))}  "
                          f"entropy_grad={_fmt(epoch_grad_log.get('epoch/entropy_grad_norm', 0))}  "
                          f"vanilla_acc={_fmt(epoch_grad_log.get('epoch/vanilla_accuracy', 0))}  "
                          f"entropy_acc={_fmt(epoch_grad_log.get('epoch/entropy_accuracy', 0))}")
            torch.distributed.barrier()
            self.save_checkpoint(step=global_step)


@hydra.main(config_path="config", config_name="dpo_trainer", version_base=None)
def main(config):
    device_name = get_device_name()
    local_rank, rank, world_size = initialize_global_process_group()

    device_mesh = init_device_mesh(device_type=device_name, mesh_shape=(world_size,), mesh_dim_names=("fsdp",))
    dp_size = world_size // getattr(config, "ulysses_sequence_parallel_size", 1)
    ulysses_device_mesh = init_device_mesh(
        device_type=device_name,
        mesh_shape=(dp_size, getattr(config, "ulysses_sequence_parallel_size", 1)),
        mesh_dim_names=("dp", "sp"),
    )

    from verl.utils import hf_tokenizer
    local_model_path = copy_to_local(src=config.model.partial_pretrain, verbose=True)
    tokenizer = hf_tokenizer(local_model_path, trust_remote_code=config.model.trust_remote_code)

    from omegaconf import OmegaConf
    truncation = OmegaConf.select(config, "data.truncation", default="right")
    branch_turn_n = OmegaConf.select(config, "data.branch_turn_n", default=3)
    dpo_dataset_config = {
        "max_length": config.data.max_length,
        "truncation": truncation,
        "branch_turn_n": branch_turn_n,
    }
    train_dataset = DPODataset(
        parquet_files=config.data.train_files,
        tokenizer=tokenizer,
        config=dpo_dataset_config,
    )
    val_dataset = DPODataset(
        parquet_files=config.data.val_files,
        tokenizer=tokenizer,
        config=dpo_dataset_config,
    )

    trainer = FSDPDPOTrainer(
        config=config,
        device_mesh=device_mesh,
        ulysses_device_mesh=ulysses_device_mesh,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
    )
    trainer.fit()


if __name__ == "__main__":
    main()
