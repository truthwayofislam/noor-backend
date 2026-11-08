# Noor API

Standalone FastAPI service for Noor accounts, activity rewards, and
leaderboards. User and activity data is stored in Turso; deploy this repository
separately from the Flutter app.

## Local setup

Requires Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, and a long random `SECRET_KEY` in
`.env`. Get the Turso values from your Turso dashboard or CLI. Never commit
`.env` or share its secrets.

Run the API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`; OpenAPI docs are at
`http://localhost:8000/docs`. At startup, the backend creates or migrates its
`users` and `activities` tables.

## Deploy on a VPS with Docker

Install Docker Engine and Docker Compose on the server, then clone this repo.
Copy `.env.example` to `.env` beside the Dockerfile and set the variables
described above. Configure DNS and HTTPS with a reverse proxy (for example,
Caddy) and expose only HTTPS publicly.

```bash
cp .env.example .env
# Edit .env and set the production secrets before continuing.
docker compose up -d --build
docker compose logs -f api
```

`docker-compose.yml` runs the API on port 8000 and restarts it automatically.
Keep port 8000 behind the HTTPS reverse proxy; do not expose it directly to the
public internet. Container logs are rotated to limit disk use. Two GB RAM can
work for an early, low-traffic API, but two GB of server storage is tight for
the OS, Docker images, and logs; more disk is preferable. The database is
remote Turso, so the VPS does not need to hold the app's account database on
its local disk.

For uptime monitors, use `/healthz` or `/health`. Both accept `GET` and `HEAD`
and return HTTP 200 while the API is responding. These are liveness endpoints;
they do not independently verify Turso connectivity.

## Render deployment

`render.yaml` remains available for Render deployments. Configure the three
secrets (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, and `SECRET_KEY`) in the
service environment.

## Connect the Flutter app

The app's current backend URL is a compile-time default. Once the new server
has a public HTTPS URL, build the app with:

```bash
flutter build apk --release \
  --dart-define=API_BASE_URL=https://api.example.com
```

Use your real HTTPS API hostname instead of `api.example.com`. No backend
credentials belong in the Flutter app.

## Push as a separate GitHub repository

Create an empty GitHub repository, then from this directory run:

```bash
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git push -u origin main
```

Replace the URL with the repository you created. The `.env` file is ignored;
configure its secret values directly on the server instead.

## API

- `POST /auth/register` - create an account
- `POST /auth/login` - sign in
- `GET /users/me` - get the signed-in user's profile
- `PUT /users/me` - update the profile
- `POST /users/activity` - record activity and points
- `GET /users/rank` - get the user's leaderboard rank
- `GET /leaderboard/global` - global leaderboard
- `GET /leaderboard/country/{country}` - country leaderboard

Passwords are hashed before they are stored. Rewards are assigned by the
server, not by the points value sent by the app. Activity submissions are
idempotent and update the user's streak and profile.

## Tests

```bash
python -m unittest discover -s tests -v
```
