# LLM Kinase-Inhibitor Affinity

This repository provides the **datasets, prompts, and code** used in our study of kinase–inhibitor binding affinity prediction with large language models (LLMs) and in-context learning (ICL).

The study evaluates text-based and multimodal ICL across multiple LLMs and compares web-interface and API-based inference settings.

## Repository Structure

```text
LLM Kinase-Inhibitor Affinity/
├── data/
│   ├── text-ICL/          # Datasets for text-based(Web txt&API text) ICL
│   └── bimodal-ICL/       # Datasets and 2D molecular structure images for multimodal ICL
│
├── prompt/                # Prompts used for experiments and the construction of the dual-modal dataset
│
├── code/                  # Scripts for data processing, and model inference.
│
└── README.md
```

## Data

The datasets are derived from those used in **GPT4Kinase** and originally obtained from **BindingDB**. They contain kinase sequences, inhibitor SMILES, and experimental binding affinity ((Kd)) information.

The "text-ICL" directory contains datasets used for text-based ICL experiments.

The "bimodal-ICL" incorporates the bimodal dataset we constructed. Specifically, it was generated using GPT-5.5 based on a prompting approach and contains standardized 2D structural images of ternary molecules.

## Prompts

The "prompt" directory contains the prompt templates used for:

* web-interface text ICL;
* API-based text ICL;
* API-based multimodal ICL.

## Code
The "code" directory contains scripts used for data processing, API-based model inference,and multimodal input construction.
The experiments include GPT, Qwen, and Gemini models under a unified evaluation workflow.

## Citation

If you use the datasets, prompts, or code from this repository, please cite the accompanying paper. Citation information will be updated upon publication.
