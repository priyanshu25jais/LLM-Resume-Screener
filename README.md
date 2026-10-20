# LLM Based Resume Screening System

B.Tech project by Priyanshu Jaiswal, Computer Science.

A web app that screens resumes against a job description. It scores each candidate out of 100 with
an LLM (Gemini, with Groq as backup), shows why they got that score, and ranks them.

## Features

- Reads the job description and pulls out must-have skills, nice-to-have skills and experience.
- Reads PDF, DOCX and TXT resumes and hides personal details before the LLM sees them.
- Score = 45% LLM rating + 25% skill match + 20% text similarity + 10% experience.
- Strengths, gaps, interview questions, candidate comparison, CSV export and questions over resumes.
- Recruiter accounts (own jobs only) and an admin console for approving and managing recruiters.
- Works without an API key in offline mode using rules.

**Tech:** FastAPI, SQLite, React (Vite), Gemini / Groq API.

## Setup (Windows)

Needs Python 3.10 or newer.

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `backend\.env` and paste your Gemini key (and Groq key as backup). Then create the admin account
once, and start the server:

```
python scripts/create_admin.py
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000. The frontend is already built in `frontend/dist`, so `npm` is not needed.
To edit the React code: `cd frontend`, `npm install`, `npm run dev`, then `npm run build` when done.

## Using it

1. Sign up as a recruiter on the website. The admin approves the account in the Admin console.
2. Log in as the recruiter, create a job or load a sample job, and upload resumes.
3. Open a candidate to see the score breakdown, strengths, gaps and interview questions.

For a quick look, click **Try the demo recruiter account** on the login page.

## Folder structure

```
backend/
  app/
    main.py        FastAPI app, also serves the built frontend
    auth.py        passwords, sessions, recruiter/admin permissions
    routers/       API endpoints (auth, admin, jobs, candidates, system)
    services/      parser, redactor, skills, embeddings, evaluator, scoring, pipeline, qa, accounts
    services/llm/  Gemini, Groq, OpenAI and Ollama clients, prompts, token counting
  scripts/         create_admin.py, evaluate.py (ranking accuracy on the sample data)
frontend/          React app (src) and the built version (dist)
sample_data/       3 sample job descriptions and 15 made-up resumes
```

API docs: http://localhost:8000/docs while the server is running.
