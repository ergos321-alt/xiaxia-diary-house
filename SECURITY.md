# Security

- Never commit `.env`, database URLs, bearer tokens, or credentials. Load secrets from server-side environment variables or secure runtime configuration.
- The diary database contains private user content. Keep it private and never publish database files, exports, or real diary examples.
- Require the configured web authentication and API bearer authentication for their respective interfaces. Use unique, high-entropy credentials and keep them server-side.
- Do not include diary content or credentials in public issues. Use GitHub private vulnerability reporting when enabled, or contact the maintainer privately through GitHub.
