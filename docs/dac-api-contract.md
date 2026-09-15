# DAC push-mode API contract

The contract between `ctn-dropd` (Rust) and `dynamic-audio-creative` (Flask,
this repo). The Rust client at `crates/daemon/src/dac.rs` is written against
exactly this — if the Python diverges, the daemon breaks silently at
deserialisation, so treat this file as the source of truth for both sides.

Base: `{DAC_BASE_URL}/api/v1`. Auth: `X-API-Key: <key>` on every endpoint
except the presigned PUT, where the signed URL *is* the authorisation.

## Endpoints

### `GET /me`
Validates the key and names its owner. Called on every key entry, so it must be
cheap.
```json
{ "advertiser_id": 12, "advertiser_name": "Acme Motors" }
```

### `GET /campaigns`
The advertiser's **push** campaigns. **This is the endpoint that makes the
whole product work** — Frequency has no campaign listing, DAC's database does.

Only campaigns whose type is `push` are ever returned. DAC's other campaigns
generate their own creative from a feed, and a pushed file would be overwritten
by the next scheduled run, so they are invisible to the daemon — as is any
campaign that is not active.
```json
[{ "id": 41, "name": "Spring Sale", "advertiser_name": "Acme Motors",
   "delivery_enabled": true, "deliverable": true }]
```
`deliverable` is `false` when the campaign is missing `frequency_app_id`, or its
advertiser is missing `frequency_client` / `frequency_token`. The desktop picker
greys these out, so a folder is never assigned to a target that cannot receive.

### `POST /campaigns/{id}/uploads`
Request somewhere to put the bytes.
```json
{ "filename": "spot.wav", "content_hash": "<blake3 hex>",
  "size": 4194304, "content_type": "audio/wav" }
```
Answers one of:
```json
{ "upload_url": "https://…presigned…", "upload_key": "pushed/41/<hash>.wav" }
{ "duplicate_run_id": 903 }
```
`duplicate_run_id` when `(campaign_id, content_hash)` already has a delivered
run. The daemon skips the upload entirely.

`404` if the campaign is not visible to this key — a campaign belonging to
another advertiser, one that is inactive, and one that is not a push campaign
are all the same `404`. Every `/campaigns/{id}/…` endpoint scopes the same way,
so a campaign switched away from push type reads to the daemon as simply gone.

**The presigned PUT must be signed for the same `content_type` the daemon
sends**, or S3 rejects the signature. The daemon sends what it declared here.

### `PUT {upload_url}`
Raw bytes, straight to object storage. DAC never sees them. The daemon allows
30 minutes for this call and nothing else.

### `POST /campaigns/{id}/push`
Register the uploaded object.
```json
{ "upload_key": "pushed/41/<hash>.wav", "content_hash": "<blake3 hex>",
  "filename": "spot.wav" }
```
→ `{ "run_id": 904 }`

`422` means the file itself is wrong — duration mismatch against the ad unit,
unsupported format. The daemon treats 422 as **permanent** and dead-letters
immediately rather than retrying. Put a human-readable reason in the body; it is
shown verbatim next to the file in the UI.

### `GET /runs/{run_id}`
```json
{ "run_id": 904, "status": "complete", "delivery_error": null }
```
`delivery_error` is the verdict of the *latest* delivery attempt, and is always
`null` while the run is still going. A re-pushed file that previously failed
keeps that failure in DAC's own history, but reports no error while it retries.
`status` is `AdRun.status` unchanged. The daemon only distinguishes `complete`,
`failed`, and "still going".

### `GET /campaigns/{id}/runs`
Delivery history, newest first. Backs the revert timeline.
```json
[{ "run_id": 904, "filename": "spot.wav", "delivered_at": "2026-09-08T12:00:00Z",
   "status": "complete", "is_active": true, "error": null }]
```

### `POST /campaigns/{id}/revert`
`{ "run_id": 871 }` → `{ "run_id": 905 }`. Re-delivers a previous run's audio.
No upload: DAC still holds the file.

### `POST /campaigns/{id}/pause`
`{ "paused": true }` → `{}`.

## Conventions

* **Hash**: blake3, lowercase hex, of the whole file. DAC only compares it for
  equality, never recomputes it.
* **Retry semantics**: the daemon retries `5xx` and `429`. It does not retry any
  other `4xx`. Choose status codes accordingly — a `400` for something transient
  will strand the file.
* **Idempotency**: `(campaign_id, content_hash)` is unique. A repeated `push`
  with the same pair must return the existing `run_id`, not create a second run.
  The daemon retries freely on the assumption that this holds.

## Implementation notes (DAC side)

* Revert re-delivers the **same** `AdRun` via `redeliver()` and returns its own
  `run_id`, not a new one. The daemon should poll whatever id comes back.
* Pause is soft: it flips `campaign.delivery_enabled`. Pushes to a paused
  campaign are accepted and stay `pending` until unpaused.
* Delivery is tick-driven (`POST /scheduler/tick`, Render cron), so a pushed run
  is `pending` for up to one cron interval before `delivering`.
* The 422 body is `text/plain`. All other errors are JSON `{"error": "..."}`.
* Campaign type is set in the DAC admin. An advertiser's key grants read access
  to their push campaigns and nothing else; switching a campaign to push clears
  its feed, schedule and script settings, and no AI pipeline runs for it again.
