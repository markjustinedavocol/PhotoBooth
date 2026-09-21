# Miles Apart: a photobooth for long-distance couples

Two partners in different places step into the same virtual booth. They see each other live, a shared countdown fires both cameras at the same moment, and the photos come back as one strip. The strip shows each partner's city and local time, like "Manila 9:14 PM ♥ Toronto 9:14 AM".

Built with Django, Django Channels (WebSockets), WebRTC and Pillow.

## Features

- **Accounts:** sign up, log in and reset a password. Profiles have a display name, avatar, city and timezone. The timezone is detected automatically at sign-up.
- **Pairing:** share an 8-character invite code or link. Each person can be in one active couple at a time.
- **Booth room:** live side-by-side video over WebRTC, with a mic toggle, presence and "ready" indicators. The server starts the synced 3-2-1 countdown and takes 4 shots.
- **Strips:** Pillow puts the photos together as a vertical strip or a 2×2 grid. There are 4 frame themes (Classic, Polaroid, Film, Pastel Hearts) and 4 filters (Natural, B&W, Sepia, Warm). Each filter is previewed live in CSS and applied again when the strip is rendered.
- **Private gallery:** favorite, download as PNG, delete, switch layouts, and flip a strip over to read its love note.
- **Extras:** "days together" and "days until we meet" counters, plus your partner's local time on the dashboard.
- **Privacy:** photos are never served from a public media URL. Every image goes through a view that checks the viewer belongs to that couple.

## Project layout

| App | What's in it |
| --- | --- |
| `accounts` | Profile, sign-up/login/reset, per-user timezone middleware, private avatars |
| `couples` | Couple model, invite and join flow, dashboard, anniversary and meetup dates |
| `booth` | BoothSession and Frame models, WebSocket consumer, frame uploads, strip renderer (`booth/strips.py`), `seed_demo` command |
| `gallery` | PhotoStrip model, gallery, detail/flip card, download, favorite, delete |

## Setup (Windows, PowerShell)

```powershell
cd "C:\Users\JOHN MICHAEL PARAGAS\OneDrive\Documents\Photobooth"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then set SECRET_KEY
python manage.py migrate
python manage.py seed_demo      # optional demo couple: alex / sam, password photobooth123
python manage.py createsuperuser  # optional, for /admin
python manage.py runserver
```

Open http://127.0.0.1:8000. Daphne is installed, so `runserver` serves both HTTP and WebSockets.

On macOS or Linux, run `source .venv/bin/activate` instead of `Activate.ps1`.

## Trying the booth on one computer

1. Run `python manage.py seed_demo`.
2. Log in as **alex** in a normal browser window.
3. Log in as **sam** in a private/incognito window, or in a second browser.
4. As alex, go to **Booth → Open the booth**. Sam's dashboard then shows "Alex is in the booth, join now".
5. Both tap **I'm ready**, then either one taps **Start the countdown**.

Both windows use the same webcam. Chrome and Edge usually allow that. Firefox may give the camera to only one window at a time.

## Trying it on two devices (the real long-distance test)

Browsers only allow camera access on `https://` or `localhost`. To reach your machine from a phone or another computer, use an HTTPS tunnel such as [ngrok](https://ngrok.com) or Cloudflare Tunnel:

```powershell
ngrok http 8000
```

Then add the tunnel host to `.env`:

```
ALLOWED_HOSTS=localhost,127.0.0.1,abc123.ngrok-free.app
CSRF_TRUSTED_ORIGINS=https://abc123.ngrok-free.app
```

The live video uses Google's public STUN servers. That covers most home networks. Some strict mobile or corporate networks need a TURN server, which you add to `RTC_CONFIG` in `static/js/booth.js`. Even when live video can't connect, the synced countdown and the strip still work, because they go through the Django server.

## Deploying to Render with Cloudinary

The repo is ready for Render. `render.yaml` sets up a web service and a PostgreSQL database, and `build.sh` installs dependencies, collects static files, migrates the database and creates the admin account. Photos are stored in Cloudinary.

### 1. Get your Cloudinary URL

Sign up at https://cloudinary.com (the free plan is enough). On the dashboard, open **API Keys** and copy the **API environment variable**. It looks like this:

```
CLOUDINARY_URL=cloudinary://123456789012345:AbCdEfGhIjKlMnOpQrStUvWxYz@your-cloud-name
```

You only need the part after `CLOUDINARY_URL=`.

Photos are uploaded as **authenticated** files in a `miles-apart/` folder, so they have no public link. Cloudinary's Media Library lists them under **Raw** files.

### 2. Push the code to GitHub

Commit and push as usual. `render.yaml` and `build.sh` need to be in the repo.

### 3. Create the Blueprint on Render

1. In the Render dashboard, go to **New → Blueprint** and connect your GitHub repo.
2. Render reads `render.yaml` and asks for these values:
   | Variable | What to enter |
   | --- | --- |
   | `CLOUDINARY_URL` | the `cloudinary://…` value from step 1 |
   | `DJANGO_SUPERUSER_USERNAME` | your admin username, e.g. `admin` |
   | `DJANGO_SUPERUSER_PASSWORD` | a strong password |
   | `DJANGO_SUPERUSER_EMAIL` | your email |
3. Click **Apply**. The first build takes a few minutes. Your site is then at `https://miles-apart.onrender.com`, or whatever name Render gives it.

You don't need to set `SECRET_KEY`, `DATABASE_URL` or `ALLOWED_HOSTS`. Render generates or fills them in.

### Optional settings

- **Real password-reset emails.** Add `EMAIL_URL`, e.g. `smtp+tls://you@gmail.com:APP-PASSWORD@smtp.gmail.com:587` with a Gmail app password. Without it, reset emails only appear in Render's logs.
- **Custom domain.** Add it in Render, then set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS=https://yourdomain.com`.

### Free-plan limits

- **The site sleeps after about 15 minutes of no visits.** The next visit takes 30–60 seconds to wake it up. Open the site a minute before a booth date.
- **Render's free PostgreSQL expires after 30 days.** Upgrade the database, or point `DATABASE_URL` at another Postgres host such as Neon or Supabase, before then. Photos stay safe in Cloudinary either way, but the accounts and strip records live in the database.
- **Everything runs as one process.** The booth's real-time messages use an in-memory channel layer, which is fine for a single instance. Before scaling to more instances, add a Render **Key Value** (Redis) instance and set `REDIS_URL` to its internal URL.

## Redis and production

In development the channel layer is in-memory, which only works with a single server process. For production:

1. Run Redis. On Windows use `docker run -p 6379:6379 redis:7` or [Memurai](https://www.memurai.com/).
2. Set `REDIS_URL=redis://localhost:6379/0`.
3. Set `DEBUG=False`, a real `SECRET_KEY`, `ALLOWED_HOSTS`, and optionally `DATABASE_URL` for PostgreSQL (`pip install "psycopg[binary]"`).
4. Run `python manage.py collectstatic`. Serve `staticfiles/` from your web server, and run the app with Daphne or Uvicorn:

   ```bash
   daphne -b 0.0.0.0 -p 8000 photobooth.asgi:application
   # or
   uvicorn photobooth.asgi:application --host 0.0.0.0 --port 8000
   ```

Do not serve `MEDIA_ROOT` publicly. The app serves strips and avatars itself, after checking permissions.

## Tests

```powershell
python manage.py test
```

The tests cover pairing rules, permission checks on every private view, upload validation, strip generation (every theme, filter and layout), concurrent-finish safety, gallery actions, and the WebSocket consumer: relaying messages, the synced start, and rejecting strangers.

## How the sync works

```
alex's browser ──ws──┐                    ┌──ws── sam's browser
                     │  BoothConsumer     │
   hello / ready ────┼──── relayed ───────┼───→
   WebRTC signal ────┼──── relayed ───────┼───→   (then video flows peer-to-peer)
   start ───────────→│ WAITING→CAPTURING  │
                     │ broadcast countdown├───→ both count 3-2-1 and snap together
   POST frames ─────→│ last frame in?     │←──── POST frames
                     │ render strip (PIL) │
                     │ broadcast strip_ready → both redirect to the strip
```

- Exactly one browser (the one with the lower user id) sends the WebRTC offer, so the two sides never offer at the same time.
- The start is claimed with an atomic `UPDATE … WHERE status='waiting'`. Double-clicks and simultaneous clicks start exactly one shoot. Strip rendering is claimed the same way.
- If a partner's photos never arrive, **Make the strip with what we have** builds the strip with placeholders.
