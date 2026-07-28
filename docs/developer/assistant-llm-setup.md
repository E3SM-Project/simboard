# Assistant LLM Setup

Configure `.envs/local/backend.env` to enable LLM-backed summaries on the execution details page. If LLM support is disabled or misconfigured, the backend falls back to the deterministic metadata summary.

## Required Settings

```env
ASSISTANT_LLM_ENABLED=true
ASSISTANT_LLM_PROVIDER=ollama  # ollama or livai
```

Use exactly one provider and configure only that provider's environment variables.

## Local Ollama Setup

Recommended local default:

```env
ASSISTANT_LLM_ENABLED=true
ASSISTANT_LLM_PROVIDER=ollama
ASSISTANT_OLLAMA_BASE_URL=http://localhost:11434
ASSISTANT_OLLAMA_MODEL=llama3.1:8b
ASSISTANT_OLLAMA_API_KEY=
ASSISTANT_LLM_TEMPERATURE=0.2
ASSISTANT_LLM_MAX_TOKENS=256
```

`ASSISTANT_LLM_MAX_TOKENS=256` keeps local summaries concise on developer hardware. If unset, the backend runtime default is `2048`.

Install and run Ollama:

1. On macOS, install Ollama natively: https://docs.ollama.com/quickstart
2. Pull a model:

   ```bash
   make ollama-pull-fast     # llama3.1:8b, faster local default
   make ollama-pull-dev      # gemma4:e4b, prompt-contract iteration
   make ollama-pull-quality  # gemma4:26b, quality checks
   ```

3. Start Ollama in a separate terminal:

   ```bash
   make ollama-serve
   ```

   This runs `ollama serve` with `OLLAMA_KEEP_ALIVE=-1`, so models stay loaded while the server is running.

4. Restart the backend:

   ```bash
   make backend-run
   ```

Supported local model choices:

| Model         | Use case                                              |
| ------------- | ----------------------------------------------------- |
| `llama3.1:8b` | Faster local summaries on typical developer hardware. |
| `gemma4:e4b`  | Fast prompt-contract iteration.                       |
| `gemma4:26b`  | Preferred quality checks.                             |
| `gemma4:31b`  | Only for hardware that can support it.                |

`ASSISTANT_OLLAMA_BASE_URL=http://localhost:11434` is accepted and normalized internally to Ollama's OpenAI-compatible `/v1` endpoint. Values that already include `/v1` also work.

On macOS, native Ollama is recommended. Docker Desktop on macOS does not support Ollama GPU acceleration, so Docker-based Ollama is useful only for CPU-only portability testing.

## LivAI Setup

```env
ASSISTANT_LLM_ENABLED=true
ASSISTANT_LLM_PROVIDER=livai
ASSISTANT_LIVAI_API_KEY=
ASSISTANT_LIVAI_MODEL=gpt-5.4
ASSISTANT_LIVAI_BASE_URL=https://livai-api.llnl.gov/
ASSISTANT_LLM_TEMPERATURE=0.2
ASSISTANT_LLM_MAX_TOKENS=8192
ASSISTANT_SNAPSHOT_MAX_CHARS=12000
```

For LivAI, `ASSISTANT_LIVAI_API_KEY`, `ASSISTANT_LIVAI_MODEL`, and `ASSISTANT_LIVAI_BASE_URL` are required.

### Model Selection

| Model          | Guidance                                                                                                                                                           |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `gpt-5.4`      | Recommended full model. Reliable structured output completion and handles 8K+ token responses.                                                                     |
| `gpt-5.4-mini` | Avoid for this workflow. It may truncate structured responses before completing all required fields such as `limitations`, `citations`, and `suggested_followups`. |

### Token Budget Guidance

| Setting                        | Guidance                                                                                                |
| ------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `ASSISTANT_LLM_MAX_TOKENS`     | Use `4096` to `8192` for `gpt-5.4`; use `2048` for mini models if used despite limitations.             |
| `ASSISTANT_SNAPSHOT_MAX_CHARS` | Use `12000` to `16000` to balance detail and token budget; reduce to `8000` to `10000` for mini models. |

For current LivAI OpenAI-compatible chat endpoints, SimBoard omits `ASSISTANT_LLM_TEMPERATURE` for `gpt-5*` models because the endpoint rejects that parameter. `ASSISTANT_LLM_MAX_TOKENS` still applies.

## Fallback Troubleshooting

After changing `.envs/local/backend.env`, restart the backend before testing again:

```bash
make backend-run
```

Common fallback reasons:

| Fallback reason                        | Meaning                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------ |
| `fallback_reason=ollama_misconfigured` | Missing `ASSISTANT_OLLAMA_MODEL` or `ASSISTANT_OLLAMA_BASE_URL`.                           |
| `fallback_reason=livai_misconfigured`  | Missing `ASSISTANT_LIVAI_API_KEY`, `ASSISTANT_LIVAI_MODEL`, or `ASSISTANT_LIVAI_BASE_URL`. |

For Ollama, `ASSISTANT_OLLAMA_API_KEY` is optional for local runs and can stay blank unless an auth proxy requires it.
