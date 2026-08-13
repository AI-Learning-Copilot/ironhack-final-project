# Nemotron Experiment

## Objective

The `experiment/nemotron` branch explores using NVIDIA Nemotron as an alternative LLM for the Ironhack AI Course Copilot.

The experiment was kept isolated from `main` so that the GPT-4o-mini implementation remains the production baseline.

## Model

The experiment uses:

`nvidia/nemotron-3-nano-30b-a3b`

The model is accessed through NVIDIA's OpenAI-compatible API endpoint.

The implementation uses:

- `LLM_PROVIDER=nvidia`
- `NVIDIA_API_KEY`
- NVIDIA API endpoint
- `enable_thinking=False`
- `max_tokens=4096`

The existing GPT-4o-mini model remains the default configuration in `src/schemas.py`.

## Experiment Changes

The Nemotron branch introduced a configurable LLM factory in `src/agent.py`, allowing the Copilot to switch between the default OpenAI model and the NVIDIA Nemotron model.

The branch also includes improvements to the agent prompt, including stricter tool usage, language handling, and explicit use of the term "context" when explaining RAG.

Quiz generation was also improved so that common course abbreviations such as PCA, CLIP, RAG, and NLP are expanded during quiz-specific retrieval.

## Branch Status

The Nemotron implementation is maintained on:

`experiment/nemotron`

It has not been merged into `main`.

The main branch continues to use GPT-4o-mini.

## Evaluation

The Nemotron experiment was evaluated separately from the GPT-4o-mini baseline.

The observed evaluation results should be recorded separately from the GPT-4o-mini results. Because the two experiments were not conducted under identical conditions, the results should not be presented as a controlled head-to-head accuracy comparison.

## Conclusion

The experiment demonstrates that the Copilot can be configured to use Nemotron while preserving the same overall agentic RAG architecture.

The experiment remains isolated on its own branch while GPT-4o-mini remains the implementation on `main`.