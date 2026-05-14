#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a style LoRA adapter on raw text continuations.")
    parser.add_argument("--model-name", required=True, help="Base Hugging Face causal LM model name or path.")
    parser.add_argument("--dataset-path", required=True, help="Path to JSONL with a `text` field per line.")
    parser.add_argument("--output-dir", required=True, help="Directory to save adapter artifacts.")
    parser.add_argument("--epochs", type=float, default=3.0, help="Number of training epochs.")
    parser.add_argument("--max-steps", type=int, default=-1, help="Maximum optimizer steps. Overrides epochs.")
    parser.add_argument("--learning-rate", type=float, default=5e-5, help="Optimizer learning rate.")
    parser.add_argument("--batch-size", type=int, default=4, help="Per-device training batch size.")
    parser.add_argument("--grad-accum", type=int, default=1, help="Gradient accumulation steps.")
    parser.add_argument("--max-length", type=int, default=256, help="Max tokenized sequence length.")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank.")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha.")
    parser.add_argument("--lora-dropout", type=float, default=0.05, help="LoRA dropout.")
    parser.add_argument("--save-steps", type=int, default=50, help="Checkpoint save interval.")
    return parser.parse_args()


def load_text_examples(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            text = (obj.get("text") or "").strip()
            if text:
                rows.append({"text": text})
    return rows


def main() -> int:
    args = parse_args()
    dataset_path = Path(args.dataset_path)
    if not dataset_path.exists():
        raise SystemExit(f"Dataset path does not exist: {dataset_path}")

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    except ImportError as exc:
        raise SystemExit(
            "Missing training dependencies. Install torch, transformers, datasets, accelerate, and peft first."
        ) from exc

    examples = load_text_examples(dataset_path)
    if not examples:
        raise SystemExit("Training dataset is empty.")

    dataset = Dataset.from_list(examples)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize(batch: dict) -> dict:
        tokenized = tokenizer(
            batch["text"],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",
        )
        labels = []
        for input_ids, attention_mask in zip(tokenized["input_ids"], tokenized["attention_mask"]):
            row_labels = [
                token_id if mask == 1 else -100 for token_id, mask in zip(input_ids, attention_mask)
            ]
            labels.append(row_labels)
        tokenized["labels"] = labels
        return tokenized

    tokenized_dataset = dataset.map(tokenize, batched=True, remove_columns=["text"])

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, lora_config)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_strategy="steps",
        save_steps=args.save_steps,
        report_to="none",
        fp16=torch.cuda.is_available(),
        do_train=True,
        dataloader_pin_memory=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
    )
    trainer.train()
    trainer.save_model()
    tokenizer.save_pretrained(output_dir)
    print(f"Saved LoRA adapter to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
