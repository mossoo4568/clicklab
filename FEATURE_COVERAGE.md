# TubeMind feature coverage audit

Inspected all 66 public tool pages with REA on 10 November 2026. This is not a declaration of full subfeature parity. Each row describes the actual implemented scope and remaining differences. Public catalog evidence: `reports/tubemind-66-rea-audit.json`.

| Tool | Implemented scope and remaining differences |
|---|---|
| [YouTube Keyword Research](https://tubemind.io/tools/youtube-keyword-research) | Live sample phrase evidence, filters and CSV. Private index and demand/difficulty formulas are not replicated. |
| [YouTube Tag Extractor](https://tubemind.io/tools/youtube-tag-extractor) | Public video tags, correct API-style character count, copy and TXT export. |
| [Video Rank Checker](https://tubemind.io/tools/youtube-rank-checker) | Automatic title/tag keywords or manual five-keyword ranking. Up to 50 API results; signed-in top-200/channel-handle mode not implemented. |
| [Video SEO Checker](https://tubemind.io/tools/youtube-video-seo-checker) | Metadata heuristics, target-keyword and chapter checks. Scoring weights are ClickLab-specific. |
| [Hashtag Generator](https://tubemind.io/tools/youtube-hashtag-generator) | AI brief, requested count and local hashtag check. AI formatting/relevance still needs review. |
| [Trending Keywords](https://tubemind.io/tools/youtube-trending-keywords) | Two live search samples of up to 50 each, not global historical index trends. |
| [Niche Finder](https://tubemind.io/tools/youtube-niche-explorer) | Live sample and phrase evidence. Historical growth, index-wide opportunity and faceless classifications unavailable. |
| [Title Generator](https://tubemind.io/tools/youtube-title-generator) | AI drafts and 12 local formula directions; public video evidence can be attached. Dedicated 3-title shortlist workflow not implemented. |
| [Title Analyzer](https://tubemind.io/tools/title-analyzer) | Three-title checks, target phrase, imported title and approximate truncation. Proprietary winning-pattern analysis not replicated. |
| [Tags Generator](https://tubemind.io/tools/youtube-tags-generator) | AI tag list with official-style character count. Intent groups and interactive tag editor not implemented. |
| [Description & Metadata Generator](https://tubemind.io/tools/youtube-description-generator) | AI brief, source-description import and local template. Structured five-title packaging dashboard not replicated. |
| [Channel Description Generator](https://tubemind.io/tools/youtube-channel-description-generator) | AI About drafts and existing-description import. Separate scored About audit and link-title editor not implemented. |
| [Thumbnail & Title Tester](https://tubemind.io/tools/thumbnail-tester) | Three local variants, optional real competitor sample and grayscale. No CTR forecast; dedicated device-layout switch not implemented. |
| [Thumbnail Size Checker](https://tubemind.io/tools/thumbnail-size-checker) | Batch dimensions, format, shape and file-size checks. Duration-badge overlay and small-feed previews not implemented. |
| [Thumbnail Downloader](https://tubemind.io/tools/thumbnail-downloader) | Available video thumbnail sizes and original links. Channel thumbnail gallery/direct file download not implemented. |
| [Image Resizer (thumbnail, banner, PFP)](https://tubemind.io/tools/youtube-image-resizer) | Eight size presets, crop anchors, contain, JPEG/PNG/WebP, measured output-size constraint. Blurred background not implemented. |
| [Banner Template & Checker](https://tubemind.io/tools/channel-banner-template) | Safe-area overlay and dark/transparent standalone SVG templates. All device preview modes not replicated. |
| [Profile Picture & Banner Downloader](https://tubemind.io/tools/youtube-profile-picture-downloader) | API artwork URLs. Original-size reconstruction and direct file downloads not implemented. |
| [Channel Audit](https://tubemind.io/tools/youtube-channel-audit) | Five explicit checks, priority fixes, recent cadence, views and engagement. No universal growth score or verified monetization. |
| [Engagement Rate Calculator](https://tubemind.io/tools/youtube-engagement-rate-calculator) | Manual or real video/channel counts; weighted engagement with missing-count coverage. Matched-category benchmark not implemented. |
| [Channel Comparison](https://tubemind.io/tools/youtube-channel-comparison) | Two to four live channel profiles with sample views, cadence and engagement. Confirmed Shorts share unavailable. |
| [Channel Valuation](https://tubemind.io/tools/youtube-channel-valuation) | User profit and editable low/high multiples. Automatic broker-factor adjustments and acquisition memo not implemented. |
| [Subscriber Count Checker](https://tubemind.io/tools/youtube-subscriber-count) | Rounded public count/range and optional 2-minute refresh; persistent history available in Real Time. Pre-tracking history unavailable. |
| [Monetization Requirements Checker](https://tubemind.io/tools/youtube-monetization-checker) | Import public subscribers; current/future ad-entry and expanded-program numeric checks. Owner watch hours, policy/country eligibility and actual monetization cannot be verified. |
| [Channel Age Finder](https://tubemind.io/tools/youtube-channel-age-finder) | Bulk creation timestamp lookup, up to 10 channels. Calendar-age breakdown and per-year averages not yet shown in bulk mode. |
| [Channel ID Finder](https://tubemind.io/tools/channel-id-finder) | Bulk IDs, handles, dates and uploads-playlist IDs, up to 10. Copy/export is generic JSON, not dedicated CSV. |
| [Channel Name Generator](https://tubemind.io/tools/youtube-channel-name-generator) | AI names with brief and manual batch live-handle checking. No guaranteed claimability or persistent repeat-name exclusion. |
| [Subscribe Link Generator](https://tubemind.io/tools/subscribe-link-generator) | Permanent-ID subscribe URL and official website button markup. |
| [Name Checker](https://tubemind.io/tools/youtube-name-checker) | Seven candidate public-handle lookups. No API match does not prove registration availability; no proprietary brand score. |
| [Similar Channel Finder](https://tubemind.io/tools/youtube-similar-channels) | Live search candidates with size filters. Private similarity index and faceless/format filters unavailable. |
| [Shorts Outlier Finder](https://tubemind.io/tools/youtube-shorts-outlier-finder) | Confirmed Shorts listings, own-channel baselines, returned-result filters. At most 10 channels/search and 30 Shorts/channel; private index unavailable. |
| [YouTube Outlier Finder](https://tubemind.io/tools/youtube-outlier-finder) | Own-channel sampled baselines, date/duration/sort/sample filters. Duration groups are not confirmed Shorts; no global index. |
| [YouTube Outlier Calculator](https://tubemind.io/tools/youtube-outlier-calculator) | Manual baseline or fetched recent-upload comparison excluding target. Duration grouping and unequal ages limit comparison. |
| [YouTube Transcript & Subtitles](https://tubemind.io/tools/youtube-transcript) | Available subtitles; search/TXT and SRT from preserved fetched cues or pasted SRT/VTT. Old plain-text cache lacks timing; no extension-based translation. |
| [Video Stats](https://tubemind.io/tools/youtube-video-stats) | Public counts, tags, duration, category, language and lifetime velocity. Paid-promotion/made-for-kids flags and video historical index not implemented. |
| [Comment Picker](https://tubemind.io/tools/youtube-comment-picker) | Paged comments, filters, unique known authors, owner exclusion, dates, likes, winners/backups and draw record. Tagged-friend rule not implemented; only loaded eligible pool. |
| [Comment Reply Writer](https://tubemind.io/tools/youtube-comment-reply-writer) | Paste comments or load confirmed-unanswered comments, then generate drafts. Partial reply sets remain unknown; never posts replies. |
| [Video ID Extractor](https://tubemind.io/tools/video-id-extractor) | Bulk standard YouTube links/IDs and CSV. Attribution links, classification and availability-check workflow not implemented. |
| [Embed Code Generator](https://tubemind.io/tools/youtube-embed-code-generator) | Video/playlist, responsive/fixed/vertical, start/end, autoplay-muted, loop, captions and privacy host. Remaining player switches not implemented. |
| [Playlist Length Calculator](https://tubemind.io/tools/youtube-playlist-length-calculator) | Up to 500 entries, speed totals, available-entry subset and running totals. Private/deleted positions shift; complete arbitrary-size playlists not supported. |
| [Timestamp Link Generator](https://tubemind.io/tools/youtube-timestamp-link) | Flexible time input, multiple moments, short/watch links and Markdown data. Playlist preservation/embed moment variants not implemented. |
| [Chapters Generator](https://tubemind.io/tools/youtube-chapters-generator) | AI draft or local validation of provided timing. Last chapter needs duration. Automatic timing corrections are deliberately not invented. |
| [Title and Description Translator](https://tubemind.io/tools/youtube-localize-pack) | AI translation from supplied material and target languages. Dedicated six-language structured output controls not implemented. |
| [Trending Videos](https://tubemind.io/tools/youtube-trending-videos) | Country code/category chart and sample date/duration/sort filters. Lifetime views/hour is not measured hourly velocity. |
| [Comment Finder](https://tubemind.io/tools/youtube-comment-finder) | Server searchTerms, paging, local question/timestamp/reply filters, sorts and CSV. Returned replies may be incomplete; whole-video completeness not claimed. |
| [Video Summarizer](https://tubemind.io/tools/youtube-video-summarizer) | Available transcript or pasted text to AI overview. Factual review required; extension-specific language workflow unavailable. |
| [Frame by Frame Player](https://tubemind.io/tools/youtube-frame-by-frame) | YouTube native pause/comma/period frame stepping. No custom frame-accurate control/timecode export. |
| [YouTube API Quota Calculator](https://tubemind.io/tools/youtube-api-quota-calculator) | Itemized endpoint costs, separate search/upload buckets, tracking estimate and remaining quota. Actual project limits must be checked in Cloud Console. |
| [YouTube Pay Per View](https://tubemind.io/tools/youtube-pay-per-view) | User RPM or attributed published niche/country presets. Scenario estimates, not actual earnings. |
| [YouTube Money Calculator](https://tubemind.io/tools/youtube-money-calculator) | Separate long-form/Shorts assumptions, goal math and saved scenarios; optional attributed RPM presets. No earnings measurement. |
| [Sponsorship Rate Calculator](https://tubemind.io/tools/youtube-sponsorship-calculator) | Public-view import, user CPM range, rights/exclusivity/production add-ons. Lifetime sample is not verified first-30-day performance; format rate-card/memo not implemented. |
| [Best Time to Post](https://tubemind.io/tools/best-time-to-post-youtube) | Channel-sample weekday/hour evidence in chosen timezone. Private niche-wide breakout heatmap unavailable; not viewer-online data. |
| [RPM by Niche & Country](https://tubemind.io/tools/youtube-cpm-rpm-by-country) | User scenarios plus 127 published niche entries, 27 country factors and strict 100% blended audience. Third-party estimates, not YouTube official rates. |
| [Niche Score Checker](https://tubemind.io/tools/niche-checker) | Evidence-only live sample. Proprietary opportunity score, historical concentration/growth and verified faceless data unavailable. |
| [Watch Time Calculator](https://tubemind.io/tools/youtube-watch-time-calculator) | User-input pace, target and assumed monthly expiry. Rolling-cohort exact expiry and automated threshold-deadline planner not implemented. |
| [RPM & CPM Calculator](https://tubemind.io/tools/youtube-rpm-cpm-calculator) | Measured-input RPM/CPM, optional monetized-playback rate and goal math. Does not infer advertiser CPM from a guessed revenue share. |
| [RPM by Niche Comparison](https://tubemind.io/tools/youtube-rpm-by-niche) | User multi-niche rows and published preset insertion. No proprietary ranking; comparison is scenario arithmetic. |
| [YouTube Take-Home Calculator](https://tubemind.io/tools/youtube-take-home-calculator) | User gross/expenses/reserve rate. Multi-deduction source/date ledger and low/high month scenarios not implemented. |
| [AdSense Payout Checklist](https://tubemind.io/tools/adsense-payout-checklist) | Local self-reported setup checklist. Does not access AdSense or verify payout/account status. |
| [Income Mix Calculator](https://tubemind.io/tools/youtube-income-mix-calculator) | Seven sources, proportions, concentration and largest-source-halving stress test. |
| [Video Ideas Generator](https://tubemind.io/tools/youtube-video-ideas-generator) | AI briefs with optional attached live video evidence. Attached videos are not automatically certified breakouts. |
| [Hook Generator](https://tubemind.io/tools/hook-generator) | AI briefing plus ten local templates and word/runtime estimate. Dedicated hook quality/visual-cue dashboard not implemented. |
| [Script Review](https://tubemind.io/tools/youtube-script-review) | AI review with title/audience/context and speaking-rate assumptions. AI judgments are not verified retention forecasts. |
| [Script Generator](https://tubemind.io/tools/script-outline) | AI script or local timed outline, format/audience/voice brief and word/runtime estimates. Timings remain assumptions. |
| [Faceless Niche Finder](https://tubemind.io/tools/faceless-niche-finder) | Candidate topic research. No private faceless classifier/index; video format requires manual verification. |
| [Topic Research](https://tubemind.io/tools/youtube-topic-research) | Live topic/phrase/source evidence and attach-to-brief workflow. Outside-YouTube web research and unified AI report not implemented. |
