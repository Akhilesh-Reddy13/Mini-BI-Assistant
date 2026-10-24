# Intent interpretation

The Groq adapter in `backend/app/interpreter.py` maps each question to one of five application intents: `total_revenue`, `top_product`, `monthly_trend`, `top_region`, or `compare_months`. It also allows `unsupported`. It does not produce SQL or answer with business numbers. The analytics service remains the only source of figures.

## Groq request

When `GROQ_API_KEY` is present, the backend sends a Chat Completions request to `https://api.groq.com/openai/v1/chat/completions`. The default model is `llama-3.3-70b-versatile`; it can be changed with `GROQ_MODEL`. The request uses temperature zero, a short output limit, a timeout, and JSON mode. The prompt asks only for a supported intent and parameters. Month comparison parameters must be explicit, distinct `YYYY-MM` values.

The response is treated as untrusted data. The backend parses JSON and requires exactly `intent` and `parameters`; intent must be whitelisted; month values are validated as real calendar months; all unexpected parameters are rejected. A failure, malformed JSON, or invalid classification never reaches analytics as a model-produced answer.

## Local fallback

When no key is configured or a Groq request/response fails validation, a conservative local pattern parser recognizes common phrasings for the supported intents. It handles explicit month names/years and `YYYY-MM` for comparisons. If it cannot identify the intent confidently, or the month/year is ambiguous, it returns `unsupported` and an explanation. This keeps local demos and tests working without network access or credentials.

Set these environment variables in the backend process:

```text
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TIMEOUT_SECONDS=8
```

The key must remain on the backend and must not be committed or sent to the browser. The fallback does not have general language understanding; its supported wording is intentionally limited and can be expanded with tests.

## Official API references consulted

- [Groq Chat Completions API reference](https://console.groq.com/docs/api-reference)
- [Groq Structured Outputs and JSON mode](https://console.groq.com/docs/structured-outputs)
- [Groq supported models](https://console.groq.com/docs/models)
