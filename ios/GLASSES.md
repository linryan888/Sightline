# Meta glasses: live preview, photos and recording

Brandon built this on the `glasses-integration` branch. It connects SightLine to
Ray-Ban Meta glasses through Meta's Wearables Device Access Toolkit (DAT). It
shows the glasses camera live in the app, takes photos, and records video. Every
photo and video is saved inside the app and listed on the home screen.

Start with the general setup in [README.md](README.md): clone the repo, create
`Secrets.xcconfig`, choose a signing team, build to your phone. This page covers
only the glasses-specific steps.

## What you need

- A Mac with **Xcode 26** or newer. The project uses Swift settings that older
  Xcode versions don't have.
- A real **iPhone**. The Simulator can't talk to the glasses.
- **Ray-Ban Meta glasses**, paired with the **Meta AI** app on that iPhone, with
  their software up to date. To check the glasses' version: Meta AI → Devices
  tab → your glasses → gear icon.
- **Developer Mode turned on in the Meta AI app.** Without it, approval fails
  with an "Internal error" in Meta AI.
  1. In Meta AI, open **Settings → App Info**.
  2. Tap the **App version** number five times. A Developer Mode toggle appears.
  3. Turn it on and tap **Enable**.

  Meta has moved this setting between app versions. If you can't find it there,
  check Meta's [setup guide](https://wearables.developer.meta.com/docs/develop/dat/getting-started-toolkit/).

You don't need a Meta developer account or app ID while testing.
`SightLine-Info.plist` leaves `MetaAppID` and `ClientToken` empty on purpose,
which tells the SDK to run in Developer Mode.

## Run it

1. Open `ios/SightLine.xcodeproj`. Xcode downloads the
   [`meta-wearables-dat-ios`](https://github.com/facebook/meta-wearables-dat-ios)
   Swift package (pinned to 1.0.1) the first time. If the build complains about
   a missing `MWDATCore` or `MWDATCamera`, use **File → Packages → Reset Package
   Caches**.
2. Choose your signing team and build to your iPhone (README steps 3–4).
3. Put the glasses on, or open the case, so they're awake and connected to
   Meta AI.
4. In SightLine, tap **+**. The Glasses screen opens.
5. Tap **Connect**. Meta AI opens and asks you to approve SightLine. Approve it,
   and Meta AI sends you back to SightLine. You only do this once per install.
6. Tap **Start**. The first time, Meta AI opens again to ask for camera
   permission. Once you're back, the live preview appears.
7. Tap **Record** and then **End** to record a clip. Tap **Photo** to take a
   photo. Each capture is shown in a sheet, saved in the app, and added to the
   home screen list.
8. Tap an item in the list to view it. **Share or Save** exports it to Photos or
   Files. In debug builds, video items also have an **Upload to backend** button
   (see "Testing the upload" in [README.md](README.md)).

The status dot under the preview turns green when the glasses are connected.

## How the code is organized

Everything is in `ios/SightLine/`.

| File | What it does |
|---|---|
| `SightLineApp.swift` | Calls `Wearables.configure()` at launch, creates one shared `GlassesManager`, and passes `sightline://` callback URLs from Meta AI to it. |
| `App/GlassesManager.swift` | All of the glasses logic: registration (Connect/Disconnect), the device session, camera permission, the live stream, photos and recording. Views read its state (`currentFrame`, `isStreaming`, `isRecording`, `errorMessage`, and so on). |
| `App/GlassesRecorder.swift` | Writes live frames to an H.264 `.mov` in the temp folder. Video only, no audio. Thread-safe, because frames arrive on the SDK's thread. |
| `App/GlassesView.swift` | The Glasses screen: connect prompt, preview, Start/Record/Photo buttons, error alert. It saves each new photo or video through `CaptureStorage`. |
| `App/CaptureStorage.swift` | Copies captures into `Documents/Captures/` and inserts an `Item` for each one. |
| `App/CaptureViews.swift` | The list row (thumbnail, type, time) and the detail screen (viewer, share, debug upload). |
| `Item.swift` | SwiftData model. Brandon added `mediaKind` (`"photo"` or `"video"`) and `mediaFileName`. |
| `../SightLine-Info.plist` | Meta SDK settings (`MWDAT`), the `sightline` URL scheme, Bluetooth and background modes, and permission prompts. Xcode merges it into the generated Info.plist. |

To use the glasses from another view:

```swift
@Environment(GlassesManager.self) private var glasses

glasses.connect()                  // one-time pairing via Meta AI
await glasses.startStreaming()     // live frames -> glasses.currentFrame
glasses.capturePhoto()             // -> glasses.lastPhoto
glasses.toggleRecording()          // -> glasses.lastVideoURL (temp .mov)
glasses.stopStreaming()
```

Saved recordings are at `item.mediaURL`
(`Documents/Captures/video_<uuid>.mov`). That's the file the upload service
sends to the backend.

## Good to know

- **Streaming stops when the app goes to the background.** iOS pauses the raw
  stream, so `GlassesManager` ends the session cleanly, and any recording in
  progress is saved. The Meta AI round trips for Connect and camera permission
  are the exception: they don't stop the session.
- **Video quality:** the stream runs at the SDK's `.medium` resolution and
  24 fps, and recordings match it. Change `StreamConfiguration` in
  `GlassesManager.beginStream` to adjust.
- **Logs:** filter the Xcode console by `Glasses` to see session and stream
  state changes and errors.
- **Before release:** set the real `MetaAppID` and `ClientToken` from the
  Wearables Developer Center in `SightLine-Info.plist`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Meta AI shows "Internal error" after you tap Allow | Developer Mode is off in Meta AI (see above). |
| Connect opens Meta AI but you never come back to SightLine | The `sightline` URL scheme isn't registered. Make sure the target still uses `SightLine-Info.plist` (Build Settings → Info.plist File). |
| "No glasses detected" | Wake the glasses, check that they show as connected in Meta AI, and check that Bluetooth is on. |
| "Camera permission denied" | Tap Start again and allow it in Meta AI, or allow it in Meta AI → your glasses → app permissions. |
| Preview stays black or keeps loading | Stop, then Start again. If it still fails, Disconnect, Connect, and check the `Glasses` logs. |
| "No video was recorded" | The recording was too short to get a frame. Record for at least a second. |
