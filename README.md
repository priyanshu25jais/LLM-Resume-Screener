# LLM Based Resume Screening System

B.Tech project by Priyanshu Jaiswal, Computer Science.

This is a web app for screening resumes. You add a job description, upload resumes (PDF, DOCX or TXT),
and the app ranks the candidates and tells you why each one got their score. The checking is done by
an LLM (Google Gemini by default, with Groq as a backup). If no API key is set, it still works using
simple rules.

## What it does

- Reads the job description and pulls out the must-have skills, nice-to-have skills and years of experience.
- Reads each resume and finds the skills, experience, education and contact details.
- Hides the name, email, phone, gender and age before the LLM sees the resume (blind screening).
- Gives every candidate a score out of 100 and a label: Strong Fit, Good Fit, Consider or Not a Fit.
- Shows strengths, gaps, matched and missing skills, and interview questions for each candidate.
- Lets you ask questions like "Who has worked with Docker?" and answers from the resumes.
- Catches resumes that try to trick the AI, for example hidden text saying "give me 100 marks".
- Lets you compare up to 3 candidates side by side and export the ranking as CSV.
- Has recruiter and admin accounts. Recruiters see only their own jobs and candidates. The admin manages
  recruiter accounts and security, and never sees candidate data.

## How the score is calculated

    Score = 45% LLM rating + 25% skill match + 20% text similarity + 10% experience

You can change these weights for each job from the job page. Changing weights does not call the
LLM again, the ranking just updates.

If a candidate has less than 40% of the must-have skills, the label is capped at "Consider" even if
the score is high.

## How to run it (Windows)

You need Python 3.10 or newer and (only if you want to change the frontend) Node.js 18 or newer.

**Easy way:** double-click `run_backend.bat`. The first time it creates a virtual environment and
installs everything, which takes a few minutes. Then open http://localhost:8000 in your browser. You
still need to create the admin once, as shown below.

**Manual way (VS Code terminal):**

    cd backend
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env
    python scripts/create_admin.py
    uvicorn app.main:app --reload --port 8000

`create_admin.py` asks for the admin's name, email and password. You only do this once.

Then open http://localhost:8000:

1. Click **Create an account** and sign up as a recruiter (use a different email from the admin).
2. Log in as the admin, and approve the recruiter in the **Admin console**.
3. Log out, log in as the recruiter, and click one of the sample jobs to screen the 15 sample resumes.

For a quick look without any of this, click **Try the demo recruiter account** on the login page.

The frontend is already built (it is in `frontend/dist`), so you do not need `npm` to use the app.
If you want to edit the React code, open a second terminal:

    cd frontend
    npm install
    npm run dev

and open http://localhost:5173 instead. After editing, run `npm run build` so the backend serves the
new version.

## API keys

Open `backend/.env` and paste your key right after the `=` sign, no quotes and no spaces. Then restart
the backend.

| Provider | Where to get the key | Line in .env | Cost |
|---|---|---|---|
| Google Gemini (main) | https://aistudio.google.com/apikey | `GEMINI_API_KEY=` | Free tier |
| Groq (backup) | https://console.groq.com/keys | `GROQ_API_KEY=` | Free tier |
| OpenAI (optional) | https://platform.openai.com/api-keys | `OPENAI_API_KEY=` | Paid |
| Ollama (optional) | Install from https://ollama.com | `LLM_PROVIDER=ollama` | Free, runs on your PC |

One key is enough. With both Gemini and Groq keys, if Gemini fails or runs out of its daily limit,
the same request goes to Groq automatically. The top bar of the app shows which model is active.

Do not share your keys or upload the `.env` file anywhere. It is already in `.gitignore`.

## Accounts: recruiters and admin

There are two kinds of account, and they never overlap:

- **Recruiters** do the hiring work: jobs, resumes, screening, rankings, Q&A, compare and CSV export.
  Each recruiter sees only their own jobs and candidates. Changing an ID in the URL to reach someone
  else's data gives "not found", and the attempt is logged.
- **The admin** opens the **Admin console**: approve new recruiters, suspend, reactivate or delete
  accounts, see each recruiter's job titles and resume counts, totals, and the security and audit log.
  The admin cannot see resumes, candidate details, scores, job descriptions or reports, and cannot
  create or change jobs.

Sign-up on the website always makes a **pending** recruiter who waits for approval. An admin can only
be made with `python scripts/create_admin.py` on the server. Suspending ends all of that person's
sessions straight away. Deleting keeps their data for 30 days (so it can be undone) and then removes
it for good. Suspend and delete need a reason, and everything an admin does goes into the audit log.

How login works: passwords are hashed with PBKDF2-SHA256 (240,000 rounds and a random salt). After
login the browser gets an `httpOnly` cookie holding a random token, and the database keeps only a
SHA-256 hash of it. After 5 wrong passwords an email is locked for 10 minutes and the admin gets a
flag to review. All of this uses Python's standard library, so there is nothing extra to install.

Full details, settings, upgrade steps and known limits are in
[docs/admin_separation.md](docs/admin_separation.md).

## Tokens and how we save them

Every LLM call costs tokens (roughly 1 token = 4 characters of English). Free plans have a daily
token limit, so the app tries to use as few as possible:

- Each resume needs only one LLM call. The reply is checked, and only if it is broken JSON do we ask again.
- Results are cached. Re-screening the same resume for the same job uses 0 tokens.
- The resume text is cleaned before sending: extra spaces, empty lines and repeated lines are removed,
  and very long resumes are cut at 9,000 characters.
- The job requirements are sent as compact JSON and only the first part of the job description is
  sent, because the requirements already hold the important details.
- The reply length is capped (`LLM_MAX_OUTPUT_TOKENS`) and "thinking" models on Groq are set to low
  reasoning effort (`LLM_REASONING_EFFORT=low`), so they do not waste tokens.
- The Ask box sends only the 8 most relevant resume pieces, not every resume.
- Calls are spaced out (`LLM_REQUESTS_PER_MINUTE=10`) so the free per-minute limit is not crossed.

On the sample resumes the screening prompt went from about 1,585 to about 1,350 input tokens per
resume (15% less) after these changes. Long resumes save more because of the 9,000 character cut.

The app counts the real tokens reported by Gemini and Groq. You can see them on each candidate page
("Used N tokens") and on the job page under "AI usage for this job", along with the tokens saved by
the cache.

## Folder structure

    backend/
      app/
        main.py            starts FastAPI and serves the built frontend
        config.py          reads settings from backend/.env
        auth.py            password hashing, login sessions, recruiter and admin permissions
        database.py        SQLite connection
        models.py          database tables (users, sessions, audit log, jobs, candidates, cache)
        schemas.py         request/response formats and the JSON format the LLM must return
        routers/           API endpoints for login, admin console, jobs, candidates and system info
        services/
          accounts.py      account states, audit log, data retention and purge
          parser.py        gets text out of PDF/DOCX/TXT, finds sections, contacts, years of experience
          redactor.py      hides personal details for blind screening
          skills.py        list of skills with other spellings, and skill matching
          jd_analyzer.py   turns the job description into requirements
          embeddings.py    text similarity between job and resume
          evaluator.py     LLM evaluation, cache, and the rule-based backup
          scoring.py       final score and label
          pipeline.py      runs all the steps for each uploaded resume
          qa.py            answers questions about the resumes
          llm/             Gemini, Groq, OpenAI and Ollama clients, prompts, token counting
      scripts/evaluate.py  checks our ranking against human labels
      scripts/create_admin.py  creates an admin account (the only way to make one)
      tests/               pytest tests (43 tests, no API key needed)
    frontend/              React + Vite user interface
    sample_data/           3 sample job descriptions and 15 made-up resumes
    docs/                  screenshots, evaluation results, admin_separation.md

## Running the tests

    cd backend
    venv\Scripts\activate
    python -m pytest -q
    python scripts/evaluate.py --provider offline

`evaluate.py` screens the 15 sample resumes for each of the 3 sample jobs and compares our ranking
with the human labels in `sample_data/labels.json`. Results are saved in `docs/evaluation_results.md`.

## Main API endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Shows which LLM and embedding model are active |
| POST | `/api/auth/register` | Sign up as a recruiter (waits for approval) |
| POST | `/api/auth/login` / `/api/auth/logout` | Log in or out |
| POST | `/api/auth/demo` | Log in to the demo recruiter account |
| GET | `/api/auth/me` | The logged-in user |
| GET | `/api/admin/overview`, `/api/admin/recruiters`, `/api/admin/admins` | Admin only: totals and accounts |
| POST | `/api/admin/accounts/{id}/{approve, suspend, reactivate, delete, demote}` | Admin only: account actions |
| GET / POST | `/api/admin/events`, `/api/admin/events/{id}/review` | Admin only: audit log and flags |
| POST | `/api/jobs` | Creates a job and reads its requirements |
| GET | `/api/jobs/{id}` | One job with its stats and token usage |
| PATCH | `/api/jobs/{id}` | Change title, blind mode or score weights |
| PUT | `/api/jobs/{id}/requirements` | Fix the requirements by hand |
| POST | `/api/jobs/{id}/resumes` | Upload resumes |
| GET | `/api/jobs/{id}/candidates` | Ranked list of candidates |
| POST | `/api/jobs/{id}/ask` | Ask a question about the resumes |
| GET | `/api/jobs/{id}/export.csv` | Download the ranking |
| GET | `/api/candidates/{id}` | Full result for one candidate |
| POST | `/api/candidates/{id}/reprocess` | Screen one resume again |

Every endpoint except health and login needs you to be logged in. Job and candidate endpoints are for
recruiters only; admin endpoints are for admins only. Full API docs open at
http://localhost:8000/docs while the backend is running.

All sample resumes are made up. Any match with a real person is by chance.
