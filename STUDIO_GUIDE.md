# ClickLab creator workspace

Updated 10 November 2026. Start with `ClickLab.bat`, then open
`http://127.0.0.1:8028/#/home` (the launcher reports another port if required).

The original analytics, thumbnail measurement, generation, topic funnel, comparison,
calibration, scan history and competitor bank are still available. The new workspace
adds a searchable 66-tool catalog and a persistent public-statistics tracker.

## What Real Time means

This is **observation of public YouTube counters**, not access to another creator's
YouTube Studio real-time traffic. A fresh request returns the latest values YouTube
publishes. YouTube can delay or revise those counters. Public subscribers are rounded.

- Paste a channel ID, handle, channel URL or video URL. The first successful read
  adds the channel to the watchlist, using an hourly schedule by default.
- Choose 1 minute, 5 minutes, 15 minutes, 1 hour or 24 hours. Collection runs on the
  Python server even when the browser tab is closed. It stops when the server/PC stops.
- Current totals, fetch timestamps, recent uploads, 1h/24h/7d/30d counter differences,
  24 rolling hourly windows, a history chart and an interval ledger are available.
- The first read cannot provide an earlier day's history. Missing baselines are null,
  displayed as a dash, never zero. Zero means two actual readings have identical values.
- Hourly boundaries need observations within six minutes. Larger intervals use a
  tolerance of 10% capped at an hour. Actual elapsed time is shown. Differences include
  counter corrections and must not be labelled as exact traffic during that period.
- Negative differences are preserved. The chart does not bridge collection gaps.
  Exact observation timestamps are included in CSV export.
- Per-video daily changes require the same video in a reading near 24 hours ago.
  A newly discovered video has no invented baseline.
- Refreshes within 45 seconds reuse a successful saved observation. Scheduled errors
  preserve the previous result and show their error message.
- Each poll normally uses three read requests: channel, uploads playlist, video stats.
  At one-minute intervals that is approximately 4,320 read units/day/channel. Configure
  intervals to fit the API project's quota; additional requests and retries cost more.

Data lives in `thumb_output/realtime.sqlite3` (SQLite WAL). Charts use the last 32 days,
with at most 600 plotted points; CSV contains all retained observations. Paused channels
remain visible even if their most recent observation is older. Back up the output folder
with the server stopped, or use SQLite's online backup mechanism.

## Tool library and sources

The 66 catalog entries are original ClickLab implementations informed by the public
[TubeMind catalog](https://tubemind.io/tools), inspected with REA DOM/accessibility
capture. Catalog evidence is in `reports/tubemind-inspection.json`. Selected subscriber,
ranking and outlier flows were also inspected. This is **not an exact implementation
of every TubeMind subfeature** and does not include its private index or proprietary scores.

| Family | Available behavior |
|---|---|
| Channel | Live counts, age, ID resolution, subscription URLs, artwork, public-handle lookup, five-check audit, comparison, similar-channel candidates |
| Research | Current keyword/video samples, two-window title-word trends, top-50 API ranking for five phrases, niche/topic research, official country trending chart, own-channel outlier ratios |
| Shorts | Membership comes from the channel's actual `/shorts` listing; fresh counts come from the Data API; no duration-only guess is used for Shorts membership |
| Video | Stats, actual tags and thumbnails, listing checks, available subtitles, playlist duration up to 500 entries, paginated top-level comments, random draw with author deduplication, IDs, embeds, timestamp links, native YouTube frame stepping |
| Writing | AI titles, tags, descriptions, hashtags, names, About text, hooks, scripts, script review, chapter drafts, translations, summaries, idea drafts and reply drafts |
| Images | Local file measurement, resize/crop/contain, banner safe-area template, three-image title/thumbnail preview |
| Calculators | User-input earnings, per-view revenue, sponsorship, valuation, watch-time projections, RPM/CPM, niche/country scenario comparisons, income mix, expense/tax reserve, quota planning, numerical monetization thresholds and AdSense checklist |

### Differences and limits that remain explicit in the UI

- Search samples are not search-volume figures or a complete historical niche index.
  Niche Score currently shows evidence rather than TubeMind's proprietary opportunity score.
- Faceless Niche Finder provides candidate research; it does not certify that a channel
  is faceless. Verify the actual videos. Similarity is search-derived, not ground truth.
- Outliers compare recent samples and can be confounded by age. The general outlier
  tool groups durations; only the Shorts-specific tool verifies Shorts-list membership.
- Comments are top-level public comments, up to 100 per page with Load next 100.
  Replies are not downloaded. Draws cover only the loaded, filtered population.
- Public-handle resolution can establish that a channel exists; failure to resolve does
  not guarantee registration availability. Generated names are drafts, not checked claims.
- RPM/CPM, valuation, sponsorship and revenue scenarios use supplied inputs. There are no
  fabricated per-country benchmarks or claims about another channel's actual earnings.
- AI outputs use the existing configured text provider, can fail, and require review.
  Chapter timing must come from input. Transcript availability depends on YouTube.
- Best Time to Post summarizes sampled upload weekdays, not private audience-online data.
- Creator tools have local draft saving and JSON export; IDs and tracking also offer CSV.

## Implementation

- `clicklab.py`: existing server and analysis engine; mounts extension endpoints/assets.
- `studio_backend.py`: channel/video/research services and durable tracker.
- `studio.js`: workspace navigation, catalog, tools, results and tracker UI.
- `studio.css`: shared design tokens and responsive workspace styling.
- `test_studio.py`: deterministic tests for time boundaries, missing/zero data, corrections,
  gaps, persistence, CSV, stale channels, URL parsing, duplicate playlist occurrences,
  refresh deduplication and error redaction.

Copy all five runtime source files when distributing this version. Never distribute
API key files or private output data unintentionally. The old share ZIP is not rebuilt.

## Validation performed

- Python compilation, assembled JavaScript syntax and whitespace checks.
- All 66 tool forms render; all twelve numeric calculator workflows exercised.
- Live channel, video, audit, keyword, trend, rank, comments, similar-channel, trending,
  outlier, confirmed-Shorts and 500-entry playlist requests returned actual provider data.
- A title draft was generated by the configured Gemini provider.
- Image size inspection, thumbnail resize, banner resize and preview ran with a local fixture.
- Original channel, thumbnail, testing, scan history and comparison views smoke-tested.
- Desktop and 390px mobile layouts checked for horizontal page overflow.

Primary data references:
[Channel resource](https://developers.google.com/youtube/data/reference/rest/v3/channels),
[API quotas](https://developers.google.com/youtube/data/determine_quota_cost),
[YPP criteria](https://support.google.com/youtube/answer/72851).

## Professional interface update

Include `studio_pro.js` alongside `clicklab.py`, `studio.js`, `studio.css` and
`studio_backend.py` (five runtime source files). It adds focused analytics and
competitor pages, dedicated Settings, tool-state restoration and shared legacy-page
polish. Settings reports configured status, not provider verification. Saved keys
are not returned by its status endpoint. Twelve backend tests now pass, including
credential non-disclosure. See DESIGN_EXECUTION_PLAN.md for the scoped UI audit.
