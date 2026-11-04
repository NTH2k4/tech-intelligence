# Tech Intelligence — Engineering Handoff

**Handoff snapshot:** 2026-11-04  
**Repository:** `NTH2k4/tech-intelligence` (reported remote; verify with `git remote -v`)  
**Local project path:** `~/projects/tech-intelligence`

## 1. Project objective

Build a daily technology and AI intelligence briefing in Vietnamese. The system collects trusted technology/AI sources, deduplicates and normalizes articles, scores relevance/impact/novelty/source authority with Gemini, stores state in Cloudflare D1 through a Worker API, composes a concise briefing, and delivers it to Telegram.

The current handoff covers the local, end-to-end implementation. Production scheduling and remote deployment are not yet complete.

## 2. Current architecture

- **Collector (`collector/`)**: OpenAI News RSS, Google DeepMind RSS, Hugging Face RSS, arXiv AI/ML/CL RSS, and Hacker News top stories.
- **Normalization**: HTML cleanup, canonical URL normalization, timestamp parsing, URL-hash article IDs, and deduplication.
- **Source-balanced pipeline (`scripts/run_pipeline.py`)**: selects across sources rather than taking only the globally newest N records; runs AI scoring; commits and verifies through State API.
- **Intelligence (`intelligence/`)**: batch scoring using Gemini. Existing scoring model in the successful run: `gemini-3.5-flash-lite`.
- **State API (`cloudflare/state-api/`)**: Cloudflare Worker backed by D1; protected internal endpoints for state, commit, and briefing lifecycle.
- **Briefing (`briefing/composer.py`)**: creates Vietnamese briefing and splits content into Telegram-safe chunks.
- **Telegram (`integrations/telegram_client.py`)**: sends messages to configured chat.
- **Daily briefing (`scripts/run_daily_briefing.py`)**: filters eligible articles, previews by default, and requires explicit `--send` for delivery. The manual interactive send path asks the operator to type `SEND` before claiming the date.

## 3. Verified results on 2026-11-04

### Collection

A 36-hour Collector run produced 29 unique articles across all 5 sources:

| Source | Articles |
|---|---:|
| OpenAI | 4 |
| Google DeepMind | 1 |
| Hugging Face | 4 |
| arXiv | 8 |
| Hacker News | 12 |
| **Total** | **29** |

No source was empty or failed in that run.

### Balanced selection and scoring

A dry-run selected 10 articles with the following source distribution:

- Hacker News: 3
- arXiv: 2
- Hugging Face: 2
- Google DeepMind: 1
- OpenAI: 2

Gemini scoring completed for all 10 articles in batches of 7 and 3. The run used `gemini-3.5-flash-lite` for scoring and ended with `success`.

### State API / D1 local commit

Successful pipeline run:

`run-20261104T091611-2be355836889`

- 10 articles committed to local D1.
- State API read-back verification passed for all 10.
- 10 newly scored evaluations verified.
- This was a **local Worker/D1** operation, not a remote D1 deployment.

### AI scoring result

For the 10 scored articles:

- `read`: 3
- `monitor`: 3
- `skip`: 4

The sample looked directionally sensible: OpenAI stories (2) and Google DeepMind (1) were `read`; two Hugging Face stories and one arXiv paper were `monitor`; three Hacker News stories and one arXiv paper were `skip`.

### Briefing preview and Telegram delivery

A Vietnamese briefing was generated from 6 eligible articles (3 `read` + 3 `monitor`) for `Asia/Ho_Chi_Minh` date `2026-11-04`.

The operator explicitly confirmed the interactive prompt by entering `SEND`. Telegram returned two successful message IDs: `6` and `7`. The user confirmed seeing the messages in Telegram.

State API / D1 local verification:

- Briefing ID: `ti_briefing_20261104_104535fcb71a`
- Date: `2026-11-04`
- Briefing status: `sent`
- Article count: `6`
- Telegram message IDs: `[6, 7]`
- `sent_at`: `2026-11-04T09:26:51Z`
- All 6 associated articles were changed to `delivered` with `delivered_at = 2026-11-04T09:26:51Z`.

The lifecycle test harness previously passed 7/7 local integration checks, covering seed, claim, duplicate-claim rejection (409), complete/delivered, and failure/not-delivered paths. No Telegram request was made by that test harness.

## 4. Environment and operating commands

Python environment:

```bash
cd ~/projects/tech-intelligence
source .venv/bin/activate
```

Run local State API Worker (Terminal 1):

```bash
cd ~/projects/tech-intelligence/cloudflare/state-api
npx wrangler dev --local
```

Run collection only (no Gemini and no D1 write):

```bash
cd ~/projects/tech-intelligence
source .venv/bin/activate
python -m collector.main --hours 36 --max-per-feed 8 --hn-limit 15 --output /tmp/tech-intelligence-collector-36h.json
```

Run pipeline without D1 writes:

```bash
STATE_API_URL=http://127.0.0.1:8787 \
GEMINI_MODEL=gemini-3.6-flash \
GEMINI_SCORING_MODEL=gemini-3.5-flash-lite \
python -m scripts.run_pipeline --hours 36 --max-per-feed 8 --hn-limit 15 --limit 10 --dry-run
```

Run pipeline with local D1 commit (omit `--dry-run`):

```bash
STATE_API_URL=http://127.0.0.1:8787 \
GEMINI_MODEL=gemini-3.6-flash \
GEMINI_SCORING_MODEL=gemini-3.5-flash-lite \
python -m scripts.run_pipeline --hours 36 --max-per-feed 8 --hn-limit 15 --limit 10
```

Preview the daily briefing (no claim and no Telegram send):

```bash
STATE_API_URL=http://127.0.0.1:8787 \
GEMINI_MODEL=gemini-3.6-flash \
python -m scripts.run_daily_briefing --base-url http://127.0.0.1:8787
```

Manual Telegram send is an external side effect. Use `--send` only after reviewing the freshly generated content and explicitly confirming `SEND` at the interactive prompt.

## 5. Environment configuration notes

- `.env` contains sensitive values such as `GEMINI_API_KEY`, Telegram credentials, and State API configuration. Never commit it.
- `cloudflare/state-api/.dev.vars` contains the local Worker bearer token. Never commit it.
- `GEMINI_MODEL` is used by the briefing composer (`gemini-3.6-flash` was verified working).
- `GEMINI_SCORING_MODEL` is used by the Intelligence Scorer (`gemini-3.5-flash-lite` was verified working).
- A shell-exported variable takes precedence over `.env` when `load_dotenv(..., override=False)` is used. Check `echo "$GEMINI_MODEL"` if a different model is unexpectedly selected.
- When invoking `load_dotenv` from `python - <<'PY'` on Python 3.14, pass an explicit path, e.g. `load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)`. Implicit `find_dotenv()` raised an `AssertionError` in stdin execution in this environment.

## 6. Important known issues / follow-up work

1. **Generated URL fidelity:** The delivered Telegram message changed the VALET repository URL from the source-provided `github.com/respailab/VALET` to `github.org/respailab/VALET`. This is a concrete hallucinated URL defect. Add pre-send output validation that every URL in the generated briefing is grounded in the selected source data, or render source links deterministically outside the LLM-generated text. Do not trust generated URLs blindly.
2. **Unsupported claims / wording:** The briefing occasionally strengthened source claims (for example, asserting biomedical experimentation or drug-development outcomes not clearly established by the feed summary). Tighten prompt rules and/or validate claims against source excerpts.
3. **Vietnamese proofreading:** One preview contained concatenated/misspelled words (e.g. `mạch inPCB`, `thíchứng`). Consider a deterministic cleanup/quality check or a second editorial pass.
4. **Worker/D1 remote deployment:** Migration `0003_briefing_runs.sql` was applied locally. Remote migration was still pending; a remote D1 operation previously returned Cloudflare API HTTP 403 code `7403`. The precise cause was not resolved. Do not assume remote schema is current.
5. **Production scheduling:** Azure Container Apps Jobs / scheduled execution has not been deployed. Hermes Agent remains a future enhancement.
6. **Delivery recovery:** If Telegram partially sends and the subsequent State API completion fails, reconcile Telegram and D1 manually before retrying. Avoid blind retries that can duplicate messages.
7. **Content selection policy:** Keep the current quality-first thresholds unless evaluation evidence justifies a change. Do not lower the `read`/`monitor` threshold just to fill a briefing.

## 7. Repository hygiene and commit constraints

The user previously requested that a local modification to `.github/copilot-instructions.md` **must not be included in the commit**. Preserve that file's local modification and exclude it from staging unless the user explicitly changes this instruction.

Do not commit:

- `.env`, `.env.*`
- `cloudflare/state-api/.dev.vars*`
- `.venv/`
- `node_modules/`
- `.wrangler/`
- `*.bak`, `*.before-*`, temporary diagnostic JSON files
- local databases, API tokens, Telegram tokens, or Gemini API keys

Run `git status --short`, `git diff --check`, inspect the actual diff, verify `git remote -v` and current branch, then stage only reviewed project files. Do not use `git add .` or `git add -A` blindly.

The intended repository is `NTH2k4/tech-intelligence`, but verify the configured push URL locally before pushing.

## 8. Production readiness status

The current project has a demonstrated local end-to-end path through Telegram delivery. It is ready for another engineering agent to continue from a concrete implementation baseline, but it is **not yet production-deployed**.

Not completed:

- remote D1 migration and remote Worker validation
- production secrets setup
- scheduled daily execution
- alerting / run monitoring / delivery reconciliation automation
- final code review, secret scan, Git commit and push

The next agent should start by reviewing the current working tree and the generated URL integrity issue, then complete repository hygiene and production-readiness work without repeating the already-passed local collector/scoring/lifecycle checks.