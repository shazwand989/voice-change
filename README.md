# AI Transcriber

Django SaaS app — transcribes audio/video files and generates AI prompts using OpenAI.

---

## Quick Start

### 1. Configure `.env`

Edit `.env` in the project root:

```env
OPENAI_API_KEY=your-openai-api-key

TRIAL_MAX_FILE_SIZE_MB=15   # max file size for free trial (MB)

DB_ENGINE=mysql
DB_NAME=voice_change
DB_USER=root
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=3306
```

> After changing `.env`, **restart the server** for changes to take effect.

---

### 2. Activate virtual environment

```powershell
.\venv_django\Scripts\Activate.ps1
```

If blocked by execution policy, run this first:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

---

### 3. Apply migrations

```powershell
python manage.py migrate
```

---

### 4. Seed default packages

```powershell
python manage.py seed_packages
```

Creates: Starter (10), Professional (50), Business (200), Unlimited.
Safe to run multiple times — skips existing packages.

---

### 5. Create admin user

```powershell
python manage.py createsuperuser
```

Or use the existing account: **admin / admin123**

---

### 6. Start the server

```powershell
python manage.py runserver
```

Server runs at: **http://127.0.0.1:8000/**

---

## URLs

| URL | Description |
|-----|-------------|
| `/` | Landing page |
| `/app/trial/` | Free trial (no login required) |
| `/app/` | Main transcriber (login + approved) |
| `/accounts/login/` | Login |
| `/accounts/register/` | Register |
| `/accounts/dashboard/` | Customer dashboard |
| `/accounts/admin-dashboard/` | Admin dashboard |
| `/packages/` | Manage packages (admin) |
| `/admin/` | Django admin panel |

---

## User Roles & Flow

1. User registers → status: **pending**
2. Admin approves in dashboard → status: **approved**
3. Admin assigns a package to the user
4. User can now access `/app/` and transcribe files

For access requests: **WhatsApp 019-254 8927**

---

## Changing the Trial File Size Limit

Edit `.env`:

```env
TRIAL_MAX_FILE_SIZE_MB=15
```

Then restart the server.

---

## Full Restart (after any code or `.env` change)

```powershell
# Stop the running server (Ctrl+C), then:
.\venv_django\Scripts\Activate.ps1
python manage.py runserver
```
