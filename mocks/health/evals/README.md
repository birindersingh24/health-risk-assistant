# evals/: do not ingest

These files hold the answers: the planted cases, the golden questions and the red-team prompts.

- Never chunk, embed or load them anywhere the assistant can read.
- Never use them for fine-tuning or as few-shot examples in a prompt.
- Only test code reads them.

If the assistant can see them, it copies answers instead of working them out, and every score becomes meaningless. See `../README.md` ("What goes where" and "Evals") for how to use them.
