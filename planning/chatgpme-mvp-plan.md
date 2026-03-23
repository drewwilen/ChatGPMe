# ChatGPMe: 2-3 Week Implementation Plan for a Backend-First MVP

## Summary
Build a backend-first MVP that proves the core project claim: given a user corpus, ChatGPMe can ingest writing samples, retrieve style-relevant context, generate text in that style, and evaluate whether it outperforms a generic baseline. Defer Chrome extension work until the backend pipeline and evaluation loop are working.

Current repo state appears to be effectively greenfield, so the immediate goal is to stand up a minimal but end-to-end system with four pieces: corpus ingestion, style-conditioned generation, automated evaluation, and a thin demo interface.

## Key Changes
### System shape
- Create a Python backend with a single pipeline: `ingest -> preprocess -> style store -> generate -> evaluate`.
- Start with local file ingestion first, structured so Google Drive/Gmail connectors can be added behind the same interface after the MVP works.
- Use one open-source base model and one adaptation method for v1. Default: retrieval-augmented style prompting first, with LoRA left as the next experiment once the evaluation harness exists.
- Store per-user corpora, cleaned chunks, metadata, embeddings, and evaluation outputs in a simple local layout. Default: filesystem artifacts plus a lightweight metadata store such as SQLite or JSON if that is faster to ship.

### Public interfaces / types
- Define one ingestion interface: `load_user_corpus(user_id, source_config) -> list[Document]`
- Define one preprocessing output type: `Document { id, source, text, created_at?, doc_type, chunk_ids }`
- Define one generation interface: `generate_in_user_style(user_id, prompt, mode) -> GeneratedDraft`
- Define one evaluation interface: `run_style_eval(target_author, prompts, candidate_outputs, baseline_outputs) -> EvalReport`
- Keep source connectors pluggable so `local_files`, `google_drive`, and `gmail` all map into the same `Document` structure.

### Implementation work by subsystem
- Ingestion and preprocessing: support local text/doc inputs first, normalize text, strip boilerplate where possible, chunk long documents, and tag metadata needed for retrieval and later analysis.
- Style retrieval: embed chunks, retrieve top-k style examples for a prompt, and assemble a controlled generation prompt using only retrieved examples plus explicit style instructions.
- Generation: implement one baseline path and one personalized path. Baseline: generic model with "write in X style" instruction. Personalized: same model plus retrieved exemplars from the user corpus.
- Evaluation: build a prompt set, generate paired outputs, and score them with an LLM judge on style similarity, tone, vocabulary, and authenticity; aggregate scores per author and per prompt type.
- Demo surface: ship a minimal CLI or simple web form where a teammate can pick a corpus, enter a prompt, and compare baseline vs personalized outputs side by side.

## 3-Person Task Split
### Drew Wilenzick
- Own the application skeleton and end-to-end integration.
- Set up repo structure, environment, config, and shared interfaces for ingestion, generation, and evaluation.
- Build the thin demo surface for running prompts and viewing outputs.
- Integrate the other two workstreams into one runnable MVP.
- Deliverable by end of period: one command or page that runs the full flow on a sample corpus.

### David Goldfarb
- Own data ingestion, preprocessing, and connector preparation.
- Implement local corpus ingestion first and define the canonical `Document` format.
- Add cleaning, chunking, metadata tagging, and storage of processed corpora.
- Stub or partially implement Google Drive/Gmail auth and fetch logic only if local ingestion is already stable.
- Deliverable by end of period: at least one reproducible corpus pipeline that turns raw writing samples into retrieval-ready chunks.

### Noam Canter
- Own personalization logic and evaluation.
- Implement embeddings, retrieval, and personalized prompt assembly.
- Build the baseline vs personalized generation comparison flow.
- Create the automated evaluation harness with fixed prompts and score aggregation.
- Deliverable by end of period: an evaluation report showing whether personalization beats the baseline on at least one author corpus.

## Test Plan
- Ingestion test: local sample corpus is loaded, cleaned, chunked, and stored without manual intervention.
- Retrieval test: a prompt about a known topic returns relevant style exemplars from the correct corpus.
- Generation test: baseline and personalized outputs are both produced for the same prompt with identical model settings except conditioning.
- Evaluation test: the judge pipeline runs across multiple prompts and outputs aggregate metrics without crashing.
- End-to-end demo test: a teammate can select a corpus, enter a prompt, and inspect baseline vs personalized outputs in one session.
- Regression check: run the system on at least two distinct author corpora to ensure the pipeline is not overfit to one dataset.

## Assumptions And Defaults
- Planning horizon is the next 2-3 weeks, not the full semester.
- The team should optimize for backend MVP progress first.
- Chrome extension work is out of scope for this phase except for keeping interfaces compatible with later integration.
- Google Drive/Gmail live connectors are secondary to proving the core AI pipeline; use local corpora first to de-risk the project.
- v1 personalization method is RAG-style exemplar retrieval, not LoRA fine-tuning.
- v1 evaluation uses publicly available author-style corpora plus LLM-as-judge scoring; human user testing comes later after the MVP is stable.
