# Admin and recruiter separation

This change splits the app into two kinds of accounts that never overlap. Recruiters run the hiring
work. The admin looks after recruiter accounts and security, and cannot see any candidate data.
The screening pipeline, the scoring formula, Q&A over resumes and the recruiter screens are unchanged.

## Who can do what

| | Recruiter | Admin |
|---|---|---|
| Create, edit, delete own jobs | Yes | No |
| Upload resumes, screen, re-screen | Own jobs only | No |
| See candidates, scores, reports, notes, decisions | Own jobs only | No |
| Ask questions (RAG), compare, export CSV | Own jobs only | No |
| See recruiter name, email, sign-up date, status, last login | No | Yes |
| See each recruiter's job titles, job count and resume count | No | Yes |
| Approve, suspend, reactivate, delete recruiter accounts | No | Yes |
| See totals and the security / audit log | No | Yes |

The admin never sees job descriptions, resumes, candidate names or contact details, skills,
rankings, scores, notes, decisions, interview questions or per-candidate token usage. This is enforced
on the server: every recruiter endpoint requires a recruiter account (an admin gets HTTP 403), and
the admin endpoints build their answers from an explicit list of fields and from counts. They never
load candidate rows.

A recruiter can only reach their own data. Asking for another recruiter's job or candidate by
changing the ID in the URL gives the same 404 as an ID that does not exist, and the attempt is logged.

## Account states

| State | Meaning |
|---|---|
| Pending | Signed up, waiting for an admin. Cannot log in. |
| Active | Can log in and use the features of their role. |
| Suspended | Cannot log in. All sessions end immediately. Data is kept. Can be reactivated. |
| Deleted | Cannot log in, sessions end. Data is kept for the grace period, then purged (see below). Can be restored during the grace period. |

Sign-up on the website always creates a pending recruiter. It never makes an admin, not even for the
first account. Suspending and deleting need a reason (at least 5 characters) and an explicit
confirmation, and deleting also asks the admin to type the account's email.

The last active admin cannot be suspended, deleted or demoted, and an admin cannot do these things to
their own account.

## Making the first admin

Admins are created only on the server, with the setup script:

```
cd backend
venv\Scripts\activate
python scripts/create_admin.py
```

It asks for a name, email and password (typed twice, not shown). Use a different email from your
recruiter account: one person who needs both roles has two accounts. Until an admin exists the server
prints a reminder at start-up.

## Data retention and deletion

- **Suspended:** nothing is removed.
- **Deleted:** the account is disabled at once. Its jobs, resumes, results and uploaded files are kept
  for `DELETION_GRACE_DAYS` (default 30) so a mistake can be undone with Reactivate. After that they
  are permanently removed: jobs, candidates and the files on disk. The user row is kept but
  anonymised ("Deleted user 7", `deleted-7@invalid`, no password), so the audit log still points at a
  real ID. With `DELETION_GRACE_DAYS=0` this happens immediately.
- **Audit and security entries** are kept for `AUDIT_RETENTION_DAYS` (default 365), then removed.
- The purge runs when the server starts and whenever an admin opens the console.

## Audit log and security flags

Every admin action is recorded with the actor, the action, the target account, the time, the reason
and the outcome (success or denied). A refused action, such as trying to suspend the last admin, is
recorded as denied.

Security events recorded:

| Event | Flag raised when |
|---|---|
| Wrong password | 5 wrong passwords lock the email for 10 minutes and raise a flag |
| Login blocked (pending or suspended account) | Recorded, not flagged |
| Tried another recruiter's job or candidate | `FLAG_FOREIGN_ACCESS` tries in 10 minutes (default 5) |
| Duplicate uploads | `FLAG_DUPLICATES_PER_DAY` duplicates in 24 hours (default 10) |
| Many uploads | `FLAG_UPLOADS_PER_HOUR` resumes in an hour (default 100) |

Flags are for an admin to review and mark as reviewed. Nobody is blocked or labelled automatically.

The log stores IDs, counts and the reason the admin typed. It never stores resume text, file names,
candidate details or job descriptions. For a failed login on an email that has no account, only a
short one-way hash of the email is kept, so repeated attempts can be grouped without storing the
address. IP addresses are not recorded.

## Upgrading an existing installation

1. Stop the server and make a copy of `backend/data` (database and uploaded resumes) as a backup.
2. Replace the code and start the server as usual. The new columns and the `audit_events` table are
   added automatically. Your `.env` does not need changes; the new settings have defaults.
3. Accounts that were admins in the previous version and own jobs become recruiters and keep their
   jobs, because admins can no longer own jobs. This is written to the audit log.
4. Run `python scripts/create_admin.py` to create the admin, with a new email.
5. Log in as the admin and approve any pending recruiters. Jobs created before accounts existed (if
   any) go to the first recruiter who is approved.

There is no automatic downgrade. To go back, restore the backup from step 1.

## Settings (backend/.env)

| Setting | Default | Meaning |
|---|---|---|
| `REQUIRE_APPROVAL` | `true` | New recruiters wait for an admin |
| `ALLOW_REGISTRATION` | `true` | `false` turns off sign-up on the website |
| `DEMO_LOGIN` | `true` | One-click demo recruiter. Turn off if the app is put online |
| `DELETION_GRACE_DAYS` | `30` | Days before a deleted recruiter's data is purged |
| `AUDIT_RETENTION_DAYS` | `365` | Days audit entries are kept |
| `FLAG_UPLOADS_PER_HOUR` | `100` | Upload burst flag |
| `FLAG_DUPLICATES_PER_DAY` | `10` | Duplicate upload flag |
| `FLAG_FOREIGN_ACCESS` | `5` | Tries at other recruiters' data in 10 minutes |

## Changed files

Backend:
- `app/models.py`: account state columns on `users`, new `AuditEvent` table
- `app/database.py`: adds new columns to old databases, converts old admins that own jobs
- `app/config.py`, `.env.example`: new settings
- `app/auth.py`: `recruiter_user` and `admin_user` permissions, inactive accounts lose their sessions
- `app/services/accounts.py` (new): approve, suspend, reactivate, delete, demote, purge, audit records
- `app/routers/auth.py`: sign-up creates pending recruiters, login checks the account state, events
- `app/routers/admin.py` (new): admin console API with allowlisted fields
- `app/routers/users.py`: removed (replaced by the admin API)
- `app/routers/common.py`: strict ownership checks, logs attempts on other recruiters' data
- `app/routers/jobs.py`, `candidates.py`, `system.py`: recruiter-only, upload events and flags
- `app/schemas.py`: admin response models, action body
- `app/main.py`: admin router, purge and admin reminder at start-up
- `scripts/create_admin.py` (new): the only way to make an admin

Frontend:
- `src/pages/AdminConsole.jsx` (new), `src/components/ActionDialog.jsx` (new)
- `src/pages/AuthPage.jsx`: sign-up shows "waiting for approval", no first-admin flow
- `src/App.jsx`: admins only get the console, recruiters only get the recruiter screens
- `src/pages/Team.jsx`: removed
- `src/pages/Jobs.jsx`, `src/api.js`, `src/styles.css`

Tests:
- `tests/test_admin.py` (new): the 10 acceptance criteria plus flag review
- `tests/test_auth.py`: rewritten for pending sign-ups and the lock flag
- `tests/conftest.py`: helpers that make an admin with the setup function and approve recruiters

## Acceptance criteria and tests

| # | Criterion | Test |
|---|---|---|
| 1 | Admin cannot reach candidate detail, resume download, ranking or results | `test_1_admin_cannot_read_candidates_resumes_rankings_or_results` |
| 2 | Admin cannot create, change or delete jobs | `test_2_admin_cannot_create_change_or_delete_jobs` |
| 3 | Admin sees allowlisted metadata and counts only | `test_3_admin_sees_allowlisted_metadata_and_counts_only` |
| 4 | Recruiters cannot reach each other's data | `test_4_recruiters_cannot_reach_each_others_data` |
| 5 | Pending and suspended recruiters are blocked | `test_5_pending_and_suspended_recruiters_are_blocked` |
| 6 | Suspension ends existing sessions | `test_6_suspension_revokes_existing_sessions` |
| 7 | Only admins manage accounts | `test_7_only_admins_manage_accounts_and_serious_actions_need_reason_and_confirm` |
| 8 | Last active admin is protected | `test_8_last_active_admin_cannot_be_removed_or_demoted` |
| 9 | Deletion follows the retention policy | `test_9_deletion_follows_the_retention_policy`, `test_9b_zero_grace_purges_at_once` |
| 10 | Audit log without resume contents | `test_10_audit_log_records_actions_without_resume_contents` |

The full suite is 43 tests and runs with `python -m pytest -q` from `backend`.

## Security assumptions

- The app runs on a machine you control. Anyone with direct access to the server's files or database
  can read everything, including resumes; the separation is enforced by the application, not by
  encryption at rest.
- Passwords are hashed with PBKDF2-SHA256 (240,000 rounds, random salt). Session tokens are random,
  sent in an `httpOnly`, `SameSite=Lax` cookie, and only their SHA-256 hash is stored.
- The cookie is not marked `Secure` because the app runs on plain `http://localhost`. Behind HTTPS it
  should be.

## Remaining limitations

- The wrong-password lock is kept in memory, so it resets when the server restarts and is not shared
  between several server processes.
- There is no password reset or email verification. An admin can suspend or delete an account but
  cannot reset its password.
- There is no CSRF token; protection relies on `SameSite=Lax` cookies and JSON request bodies. A public
  deployment should add one, plus HTTPS.
- The purge runs at start-up and when the console opens, not on a timer.
- Job titles are visible to the admin, as the change request allows. A recruiter who puts private
  details in a job title would expose them.
- The audit log is a normal table, so someone with direct database access could change it.
- The demo recruiter skips approval by design. Set `DEMO_LOGIN=false` outside a demo.
