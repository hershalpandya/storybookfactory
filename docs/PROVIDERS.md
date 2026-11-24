# Choosing and setting up the image provider

The toolkit draws pictures through one image provider per project, chosen by the owner. It never switches provider on its own.

Start with:

```sh
storybook provider status PROJECT
```

It says which provider the project uses, whether a Gemini API key can be found, and what to do next.

## Option 1: Google Gemini API (pay per image)

1. Open Google AI Studio (aistudio.google.com), sign in, choose **Get API key** and create a key in a project with billing enabled. Each image costs a few cents (about USD 0.03-0.05 per output image, plus input and thinking tokens); the journal records an upper-bound estimate for every call, and Google AI Studio billing is authoritative.
2. Store the key on a Mac with `storybook provider set-key` and paste it into the system prompt. It goes into the login Keychain, never into the project or your shell history. On Linux or Windows, set `GEMINI_API_KEY` in your shell profile instead. The Keychain item is named `Storybook Toolkit Gemini API`; set `STORYBOOK_KEYCHAIN_SERVICE` to use a key stored under another name.
3. Record the choice: `storybook provider choose PROJECT gemini-api --owner "Your name"`.
4. Check without spending: `storybook edition gemini-probe PROJECT SLOT`, then dry-run any call with `storybook edition gemini PROJECT SLOT --dry-run`.

## Option 2: a subscription tool you already pay for (Codex, ChatGPT)

Some subscriptions include image generation in the tool itself (for example Codex or ChatGPT). There is no API key: your agent operates the tool in its own interface and saves each image.

1. Record the choice: `storybook provider choose PROJECT subscription --tool codex --owner "Your name"` (or `--tool chatgpt`, `--tool other`).
2. Every image still goes through the journal: `storybook edition art-round` freezes a small round, `art-start` records the exact prompt and inputs before each request, `art-capture` saves the returned file, and `art-review` records the frozen checks. Assign a passing image with an `assign` revision that names the round and attempt.
3. The subscription covers the cost, so the journal counts calls and retries but no dollars.

## Switching

To switch provider, the owner runs `provider choose` again. A failed or paused provider call never falls back to another provider automatically.
