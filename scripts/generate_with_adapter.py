#!/usr/bin/env python3
from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate text with a base model plus a trained LoRA adapter.")
    parser.add_argument("--model-name", required=True, help="Base Hugging Face causal LM model name or path.")
    parser.add_argument("--adapter-path", required=True, help="Path to the saved LoRA adapter.")
    parser.add_argument("--prompt", required=True, help="Prompt to generate from.")
    parser.add_argument("--max-new-tokens", type=int, default=250, help="Maximum new tokens to generate.")
    parser.add_argument("--temperature", type=float, default=0.8, help="Sampling temperature.")
    parser.add_argument("--top-p", type=float, default=0.95, help="Top-p sampling cutoff.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise SystemExit(
            "Missing inference dependencies. Install torch, transformers, accelerate, and peft first."
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    model = PeftModel.from_pretrained(base_model, args.adapter_path)
    model.eval()

    encoded = tokenizer(args.prompt, return_tensors="pt")
    if torch.cuda.is_available():
        encoded = {key: value.cuda() for key, value in encoded.items()}
        model = model.cuda()

    output = model.generate(
        **encoded,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )
    text = tokenizer.decode(output[0], skip_special_tokens=True)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
