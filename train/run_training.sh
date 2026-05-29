#!/bin/bash
# Training using verl fsdp_dpo_trainer (modified for SelSkill)
#
# Requires:
#   - verl installed from source: https://github.com/volcengine/verl
#     git clone https://github.com/volcengine/verl && pip install -e verl/
#   - Copy train/fsdp_dpo_trainer.py into verl:
#     cp train/fsdp_dpo_trainer.py /path/to/verl/verl/trainer/fsdp_dpo_trainer.py
#   - Copy train/dataset.py into verl:
#     cp train/dataset.py /path/to/verl/verl/utils/dataset/dpo_dataset.py
#   - 8× A100 80GB GPUs (or adjust NPROC)
#   - ~4h wall time per round on 8× A100

set -e

PROJECT_ROOT=${PROJECT_ROOT:-$(dirname $(dirname $(realpath $0)))}
PYTHON=${PYTHON:-python3}

# If verl is not pip-installed, add the verl source root to PYTHONPATH:
# export VERL_PATH=/path/to/verl
# export PYTHONPATH=$VERL_PATH:$PYTHONPATH

MODEL=${1:-""}
TRAIN_DATA=${2:-""}
OUTPUT_DIR=${3:-"$PROJECT_ROOT/checkpoints/run_$(date +%Y%m%d_%H%M%S)"}

if [ -z "$MODEL" ] || [ -z "$TRAIN_DATA" ]; then
    echo "Usage: bash run_training.sh <model_path> <train_data.parquet> [output_dir]"
    exit 1
fi

NPROC=${NPROC:-8}
mkdir -p "$OUTPUT_DIR"
LOG="$OUTPUT_DIR/train.log"
exec > >(tee -a "$LOG") 2>&1

echo "============================================"
echo "Training"
echo "Model:      $MODEL"
echo "Data:       $TRAIN_DATA"
echo "Output:     $OUTPUT_DIR"
echo "============================================"

torchrun --standalone --nnodes=1 --nproc_per_node=$NPROC \
    -m verl.trainer.fsdp_dpo_trainer \
    model.partial_pretrain=$MODEL \
    model.ref_path=$MODEL \
    model.trust_remote_code=True \
    model.enable_gradient_checkpointing=True \
    model.fsdp_config.param_offload=False \
    model.fsdp_config.optimizer_offload=False \
    model.strategy=fsdp2 \
    data.train_files=$TRAIN_DATA \
    data.val_files=$TRAIN_DATA \
    data.train_batch_size=8 \
    data.micro_batch_size_per_gpu=1 \
    data.max_length=16384 \
    data.truncation=left \
    +data.branch_turn_n=3 \
    dpo.beta=0.1 \
    optim.lr=5e-6 \
    optim.betas=[0.9,0.95] \
    optim.weight_decay=0.01 \
    optim.warmup_steps_ratio=0.1 \
    optim.clip_grad=1.0 \
    optim.lr_scheduler=cosine \
    trainer.total_epochs=3 \
    trainer.default_local_dir=$OUTPUT_DIR \
    trainer.project_name=selective_skill_dpo \
    trainer.experiment_name=$(basename $OUTPUT_DIR) \
    trainer.logger=[console] \
    trainer.seed=42
