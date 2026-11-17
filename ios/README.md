# SightLine (iOS)

## Backend Link
 - https://sightline-eyw3.onrender.com

## Requirements

- macOS with Xcode 26 or newer (Xcode doesn't run on Windows)
- An Apple ID signed in to Xcode (Xcode → Settings → Accounts). A free account works.
- An iPhone and a USB cable

## Running the app

### 1. Clone

```bash
git clone <REPO_URL>
cd <REPO_NAME>/ios
```

### 2. Create your secrets file

`Secrets.xcconfig` is gitignored, so a fresh clone does not have it. Copy the template and fill it in:

```bash
cp SightLine/App/Secrets.example.xcconfig SightLine/App/Secrets.xcconfig
```

Then open `SightLine/App/Secrets.xcconfig` and set:

```
SUPABASE_URL = https:/$()/YOUR-PROJECT.supabase.co
SUPABASE_ANON_KEY = YOUR-ANON-KEY

API_BASE_URL = https:/$()/sightline-eyw3.onrender.com

TEST_USER_EMAIL = test-user@example.com
TEST_USER_PASSWORD = test-user-password
```

- `SUPABASE_URL` and `SUPABASE_ANON_KEY` come from the Supabase dashboard → Project Settings → API. Use the anon/publishable key, never the secret one.
- `API_BASE_URL` is the backend the app uploads to: the deployed one above, or your own computer while testing locally (see [Testing the upload](#testing-the-upload-debug-builds)).
- `TEST_USER_*` is a user from Supabase → Authentication → Users. Only the debug upload button uses it, to get a login token until the real login screens land. Ask on Slack for the shared test user's details, and don't paste them anywhere public, including AI chats.

The project reads this file through `SightLine/App/Config.xcconfig`. If a value is missing, the app still builds and shows "`<KEY>` isn't set" when it needs that value.

> Write the URL as `https:/$()/…`. In `.xcconfig` files, `//` starts a comment, so a plain `https://…` gets cut off at `https:`.

### 3. Select your signing team

1. Open `SightLine.xcodeproj` in Xcode.
2. Select the **SightLine** project in the navigator → **SightLine** target → **Signing & Capabilities**.
3. Check **Automatically manage signing** and choose your **Team**.
4. If Xcode reports that the bundle identifier is unavailable, change **Bundle Identifier** to something unique (for example, `com.<yourname>.SightLine`).

Please don't commit the team or bundle ID change. It's specific to your Apple account.

Using the Meta glasses also needs the Meta AI app and Developer Mode. See [GLASSES.md](GLASSES.md).

### 4. Build to your phone

1. Plug in your iPhone, unlock it, and tap **Trust** when it asks about this computer.
2. Turn on Developer Mode: **Settings → Privacy & Security → Developer Mode**, then restart the phone.
3. In Xcode's toolbar, select your iPhone as the run destination.
4. Press **⌘R**.

On a free Apple account, the first launch will be blocked. Go to **Settings → General → VPN & Device Management**, tap your developer profile, and choose **Trust**. Apps signed with a free account expire after 7 days, so rebuild to reinstall.

## Testing the upload (debug builds)

Debug builds show an **Upload test clip** button at the top of the home screen. It sends `SightLine/Resources/test-clip.mp4` to `POST /chunks/upload`. Saved glasses videos get an **Upload to backend** button on their detail screen. Each button shows **Uploaded** with the new chunk's ID, or the error.

Code: `Networking/APIClient.swift` (base URL and error handling), `Services/UploadService.swift` (the multipart request), and `Networking/DevAuth.swift` (debug sign-in for the test user).

A successful upload puts the file in the Supabase Storage `footage` bucket under `<user id>/<date>/` and adds a row to the `chunks` table. The row's `status` is `split` once the backend has cut the video into 5-second windows.

### Try the same request with curl first

If curl works and the app doesn't, the problem is in the Swift code, not the backend. On Windows PowerShell, type `curl.exe` instead of `curl`, put each command on one line, and leave out the trailing `\`.

```sh
# 1. Sign in as the test user and copy "access_token" from the response
curl -X POST "https://YOUR-PROJECT.supabase.co/auth/v1/token?grant_type=password" \
  -H "apikey: YOUR-ANON-KEY" -H "Content-Type: application/json" \
  -d '{"email": "test-user@example.com", "password": "test-user-password"}'

# 2. Upload the test clip with that token
curl -X POST "https://sightline-eyw3.onrender.com/chunks/upload" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -F "file=@SightLine/Resources/test-clip.mp4;type=video/mp4" \
  -F "date=2026-11-17"
```

Expect HTTP 201 and a JSON `chunk` with an `id`. The deployed backend sleeps when idle, so the first request can take up to a minute.

### Using a backend running on your computer

Use this when the deployed backend is down or you're testing backend changes.

1. Start the backend with Docker ([backend/README.md](../backend/README.md)). Before you do, edit `docker-compose.yml` on your machine only: change `"127.0.0.1:8000:8000"` to `"8000:8000"` so your phone can reach it. Don't commit that change.
2. Find the computer's Wi-Fi IP address. On a Mac, run `ipconfig getifaddr en0`. On Windows, run `ipconfig` and use the Wi-Fi adapter's IPv4 address. Connect the phone to the same Wi-Fi network.
3. In `Secrets.xcconfig`, set `API_BASE_URL = http:/$()/192.168.x.x:8000`, then rebuild.
4. When iOS asks to find devices on your local network, tap **Allow**. On Windows, also allow Docker through the firewall on private networks.

Plain `http://` to local IP addresses works because `SightLine-Info.plist` sets `NSAllowsLocalNetworking`, an App Transport Security exception meant for local testing only. The deployed backend uses `https`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "`API_BASE_URL` isn't set" (or another key) | `Secrets.xcconfig` is missing or the value is empty | Repeat step 2, then rebuild |
| Values in `Secrets.xcconfig` are ignored | The target isn't based on `Config.xcconfig` | Project → Info → Configurations → set the **SightLine** target to **Config** for Debug and Release |
| "Server returned 401" | Token missing or expired | Check `TEST_USER_*` and sign in with curl to confirm the account works |
| "Test user sign-in failed" | Wrong test user email/password or anon key | Fix the values in `Secrets.xcconfig` |
| "Could not connect to the server" (local backend) | Phone can't reach your computer | Same Wi-Fi network, Docker port changed to `8000:8000`, Local Network allowed, firewall open |
| "The request timed out" (deployed backend) | The server was waking up | Tap again |
| Supabase URL is just `https:` | `//` treated as a comment | Use `https:/$()/` |
| "No signing certificate" / "Failed to register bundle identifier" | Wrong team, or bundle ID already taken | Repeat step 3 and change the bundle ID |
| Phone not listed as a destination | Not trusted, or Developer Mode is off | Repeat step 4.1–4.2 |
