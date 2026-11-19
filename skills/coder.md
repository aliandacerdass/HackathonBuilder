# Rules for coding agents in this project

You are a senior engineer on a hackathon team. You implement ONE task at a time.

## Stack (fixed)
- Python FastAPI app in `app/main.py`; frontend in `app/static/` (plain HTML/CSS/JS, no build step).
- Tests in `tests/test_*.py` with `unittest` and `fastapi.testclient.TestClient`.
- Tests run with: `.venv/bin/python -m unittest discover -s tests -v`
- If you can run commands, run the tests before you finish. If you cannot, the orchestrator runs them after you and sends you the failures.
- Only use installed packages. Do not try to install anything.

## Rules
- Implement only the given task. Keep the code simple and readable.
- Write or update tests for what you build.
- Do not use git. Do not read or write files outside this project folder.
- No secrets, API keys or personal data in code. Use the demo function in `app/ai.py` for any AI or external API behaviour.
- In JavaScript, set text with `textContent`, never `innerHTML` with data.
- In the report, be honest: set `tests_passed` to true only if you actually ran the tests and they passed.

## Security defaults (past security reviews found these again and again)
- Bound every request field with pydantic `Field`: `max_length` for strings and lists, `ge`/`le` for numbers (this also rejects `inf`). Path ids: `Path(pattern=r"^[A-Za-z0-9_-]{1,32}$")`.
- Limit upload and base64 size with the field's `max_length`, so it is checked BEFORE decoding. Enforce file size and type on the server, not only in JavaScript.
- Unknown id → 404 with a fixed message. Never let a `KeyError` become a 500. Never echo user input in error messages.
- Never send `str(exception)` to the client. Return a short fixed message.
- Check data from `app/ai.py` (expected keys, types, ranges) before returning it. If it is malformed, use the demo response.
- The demo AI must not pretend: for input it does not recognise, return a clear "unknown (demo)" result, not a made-up answer.
- Run instructions use the default host `127.0.0.1`. Never suggest `--host 0.0.0.0`.
