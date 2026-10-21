# SightLine (iOS)

## Requirements

- macOS with Xcode installed
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
```

Get both values from the Supabase dashboard → Project Settings → API.

> Write the URL as `https:/$()/…`. In `.xcconfig` files, `//` starts a comment, so a plain `https://…` gets cut off at `https:`.

### 3. Select your signing team

1. Open `SightLine.xcodeproj` in Xcode.
2. Select the **SightLine** project in the navigator → **SightLine** target → **Signing & Capabilities**.
3. Check **Automatically manage signing** and choose your **Team**.
4. If Xcode reports that the bundle identifier is unavailable, change **Bundle Identifier** to something unique (for example, `com.<yourname>.SightLine`).

Please don't commit the team or bundle ID change. It's specific to your Apple account.

### 4. Build to your phone

1. Plug in your iPhone, unlock it, and tap **Trust** when it asks about this computer.
2. Turn on Developer Mode: **Settings → Privacy & Security → Developer Mode**, then restart the phone.
3. In Xcode's toolbar, select your iPhone as the run destination.
4. Press **⌘R**.

On a free Apple account, the first launch will be blocked. Go to **Settings → General → VPN & Device Management**, tap your developer profile, and choose **Trust**. Apps signed with a free account expire after 7 days, so rebuild to reinstall.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Crash at launch reading `SUPABASE_URL` | `Secrets.xcconfig` is missing or empty | Repeat step 2 |
| Supabase URL is just `https:` | `//` treated as a comment | Use `https:/$()/` |
| "No signing certificate" / "Failed to register bundle identifier" | Wrong team, or bundle ID already taken | Repeat step 3 and change the bundle ID |
| Phone not listed as a destination | Not trusted, or Developer Mode is off | Repeat step 4.1–4.2 |
