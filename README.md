# LLM-Kinase-Affinity

This repository provides the **datasets, prompts, and code** used in our study of kinase–inhibitor binding affinity prediction with large language models (LLMs) and in-context learning (ICL).

The study evaluates text-based and multimodal ICL across multiple LLMs and compares web-interface and API-based inference settings.

## Repository Structure

```text
LLM-Kinase-Affinity/
├── data/
│   ├── text-ICL/          # Datasets for text-based ICL
│   └── bimodal-ICL/       # Datasets and 2D molecular structure images for multimodal ICL
│
├── prompt/                # Prompt templates used in the experiments
│
├── code/                  # Scripts for data processing, model inference, and evaluation
│
└── README.md
```

## Data

The datasets are derived from those used in **GPT4Kinase** and originally obtained from **BindingDB**. They contain kinase sequences, inhibitor SMILES, and experimental binding affinity ((K_d)) information.

The 'text-ICL' directory contains datasets used for text-based ICL experiments.

The 'bimodal-ICL' directory additionally contains standardized 2D molecular structure images associated with the training examples.

## Prompts

The `prompt` directory contains the prompt templates used for:

* web-interface text ICL;
* API-based text ICL;
* API-based multimodal ICL.

## Code
The 'code' directory contains scripts used for data processing, API-based model inference, multimodal input construction, and prediction evaluation.
The experiments include GPT, Qwen, and Gemini models under a unified evaluation workflow.

## Citation

If you use the datasets, prompts, or code from this repository, please cite the accompanying paper. Citation information will be updated upon publication.
