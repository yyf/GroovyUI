# Security

## Reporting a vulnerability

If you believe you found a security issue in GroovyUI (studio, API, executor, or install path), **do not** open a public GitHub issue with exploit details or paste secrets.

1. Contact the maintainer through a **private** channel you already use for this project (e.g. direct email listed on your GitHub profile or org site).
2. Include steps to reproduce, affected version, and impact.
3. Allow reasonable time to fix before public disclosure.

We will acknowledge receipt and work on a fix; credit can be discussed if you want it.

## Secrets and local data

- **HF tokens** and **Anthropic API keys** belong in environment variables (`HF_TOKEN`, `ANTHROPIC_API_KEY`) or local `.groovy/studio_settings.json` — never in git, issues, or PRs.
- The Studio API returns only `*_set` flags, not raw key values.
- **File GitHub request** flows (model, blueprint, node) use browser deep links with scrubbed public metadata only — no GitHub token in the app.

## Untrusted input

- GitHub issue bodies and attached JSON from users are **untrusted**. Maintainers must not run arbitrary install scripts or commands from issues without review.
- Workflow JSON from the network or LLM output should be treated as data, not instructions.

## Scope

This policy covers the open-source tree in this repository. Third-party model weights and Hugging Face hosts have their own terms and security models.
