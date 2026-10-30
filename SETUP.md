# ClickLab — setup baat (ek hi file me sab)

ClickLab ek single-file tool hai: `clicklab.py`. Ye YouTube channels aur unki videos ka
asli data (yt-dlp se) aur thumbnails ke naap (pixels + OCR + face detect) khud naap kar
dikhata hai — title/thumbnail strategy, comparison, pattern, outlier radar, AI thumbnail
sab kuch. Har number ya to naapa hua hai ya "data nahi" likha aata hai; jitna bhi
adhoora hai, wahan saaf-saaf likha hota hai aur poora karne ka button milta hai.

## Kya-kya chahiye (requirements)

Zaroori (ye teen ke bina tool chalta hi nahi):

- Python 3.12 ya naya (tested 3.12/3.14 par). `setup.bat` na hone par khud winget se
  install kar deta hai.
- `pip install -r requirements.txt` me se: `pillow`, `numpy`, `yt-dlp` (yt-dlp ka
  command-line binary PATH par milna chahiye — pip wala package wahi karta hai).
- Internet: data YouTube se live aata hai (yt-dlp). Koi database/server install nahi
  karna — sab kuch ek folder ke andar plain files me save hota hai.

Optional magar strongly recommended (ye na ho to tool chalta hai, bas kuch naap
khali-dikhaye jaayenge, aur wo khali jagah par likha bhi aayega ke kyun khali hai):

- `opencv-python-headless` — chehre ka naap. Na hone par face wale numbers "data nahi".
- `rapidocr-onnxruntime` — thumbnail par likha text padhna (local OCR). Note (28 Oct):
  Gemini key lagi ho to text-padhai by default **Gemini ke vision model** se hoti hai —
  machine par kuch nahi chalta, aur ye local wale se behtar padhti hai; local engine
  fallback/bada-scan (speed-batta) ke liye kaam aata hai. RapidOCR na ho to system me
  Tesseract ho to wo use hota hai; Gemini key bhi na ho aur Tesseract bhi na ho to
  text-based naap khali rahenge. (Ye sab CPU par chalta hai — in kisi me GPU nahi
  chahiye.)
- `scikit-learn` — pattern se CTR ka andaza lagane wali calibration. Na hone par wo
  hisaab "abhi nahi" dikhega, baaki sab chalega.
- `pytrends` (`pip install pytrends`) — sirf "Bahar ki garmahat" wale card ka Google
  Trends hisala. Na hone par wo card saaf-saaf "install karo" bolta hai; baaki kuch
  prabhavit nahi hota. (Ye Google ka unofficial data deta hai — ye baat UI me likhi hai.)
- Tesseract OCR (sirf RapidOCR ke fallback ke liye) — `setup.bat` khud install kar
  deta hai; manual ke liye github.com/UB-Mannheim/tesseract.

"AI Thumbnail" tab ke liye Runware ki API key sabse sasti rasta hai (poora baaki tool
key ke bina bilkul chalta hai). Key dene ka koi bhi ek tareeqa:

1. Tool khol ke "AI Thumbnail" tab me key box me daal do (wo `runware_key.txt` me save
   ho jaati hai), ya
2. Environment variable `RUNWARE_API_KEY` set kar lo, ya
3. Is folder me `runware_key.txt` naam ki file bana ke usme sirf key likh do.

## Bahar ki APIs — kaunsi judi hai, kaunsi key maangti hai, aur sach kya hai

ClickLab ka core (naap, Deep Analysis, comparison) keyless hi poora chalta hai. Bahar
ki cheezein chaar hisson me hain:

1. **Bina key, bina install — hamesha chalne wale:**
   - **SponsorBlock** (sponsor.ajay.app) — video ke sponsor/self-promo segments. Ye
     **logon ke lagaye marks** hain (community data), YouTube ya is tool ka naap nahi.
     Jis video par marks nahi, wahan "—" dikhega aur "ads nahi the" ka dawa kabhi
     nahi kiya jaata. (Is network par live test kiya gaya — kaam kar raha hai.)
   - **Reddit ka public feed** — "Bahar ki garmahat" card me topic ke sawal. Pehle
     JSON try hota hai; network JSON ko block kare to **RSS** chalta hai. Sach: RSS me
     vote/jawab ki ginti nahi hoti — isliye wo dikhate hi nahi. Reddit kabhi- kabhi
     IP block karta hai; tab saaf error dikhega, jhooth nahi. (Live test: RSS se
     kaam kiya, JSON is network par 403.)
   - **Pollinations** (muft AI image) — AI Thumbnail ka keyless rasta. Koi key nahi,
     koi hisaab nahi. (Live test: 1024×576 image aayi.)
   - **TikTok/Instagram thumbnail** ("Meri Thumbnail" me link paste karo) — wahi yt-dlp
     istaal hota hai, nayi API nahi. TikTok ke views YouTube ke views jaise nahi gine
     jaate — isliye platform ka data sirf dikhta hai, tulna thumbnail ke NAAP se hota
     hai. Sach: is network par TikTok ne IP block kiya aur Instagram login maanga —
     code-path error-sahit live check kiya; asli thumbnail is network par abhi
     test nahi hua. Instagram ke liye tool ke folder me `cookies.txt` daalne se
     (browser extension "Get cookies.txt LOCALLY") login khul jaata hai.

2. **Free magar apni API key chahiye (bina key ke feature apni maujoodgi saaf-kahte
   hain, koi nakli kaam nahi):**
   - **YouTube Data API v3** — "Trending" scan (YouTube ka APNA official chart, ek
     scan = 1 unit, free quota 10,000 units/day) aur usme videos ke **official topic
     tags**. Trending me **category filter bhi API ka apna parameter hai**
     (`chart=mostPopular` + `videoCategoryId`) — "is mulk me is category ka chart"
     ka sawal seedha YouTube se hota hai. **Niche ka lafz** us chart ke *andar*
     local filter hai (0 units, strict word-match, ginti screen par:
     `chart_se_aaye` vs `niche_match`; 0 match = honest natija, error message).
     API: `/api/trend?region=&n=&cat=&kw=`. Key: `YT_API_KEY` env, `youtube_key.txt`, ya Trending card ka box.
     **Live verified (key ke saath):** Pakistan ka official chart (GTA VI, Sidhu
     Moose Wala, Marvel), API ke views/lambai, aur har video ke official topic tags
     — sab aaye; poora naap engine unhi par chala.)
     **Ek se zyada keys (pool):** `youtube_key.txt` me ek line per key, ya Trending
     card ke box me saari keys paste karke "pool me add karo". Tool round-robin
     chalta hai — jis key ka quota khatam (403/429) usko chhod kar agli key apne
     aap lag jaati hai. Har key ka apna 10,000 units/day hota hai, so ek se zyada
     accounts = ek se zyada quota. "pool hatao" poora pool mita deta hai.
   - **Gemini** (googleapis.com generativelanguage) — teen kaam: **OCR** (poore tool ki
     text-padhai — 28 Oct se default; AI page ke Gemini card ka toggle, band karne par
     local RapidOCR/Tesseract), "Gemini se dekhwa lo" (aapke thumbnail par vision model
     ki paanch-point raye — ye **model ka andaza hai, naap nahi**, UI me yahi likha
     hai), aur AI Thumbnail ka "Gemini" engine. Key: `GEMINI_API_KEY` env,
     `gemini_key.txt`, ya AI Thumbnail ka box.
     **OCR live verified (28 Oct):** asli thumbnail par lafz + boxes sahi aaye, 3–20
     second per tasveer, free tier par. Machine par kuch nahi chalta — jis computer
     par GPU/bilkul taqat na ho us par bhi OCR aaram karti hai. Speed-batta built-in:
     10 minute me 60 se zyada Gemini-OCR calls (bada channel-scan) ho jayein to baaki
     padhai apne aap local engine par chali jaati hai — free tier aadhe scan me khatam
     nahi hoti.
     **Vision (dekhwa) live verified:** asli thumbnail par paanch-point raye aayi.
     Model naam pathar par nahi likhe — tool ke paas chain hai (3.5 → 3.8 → 2.5):
     ek model vyast (503) ya naye keys par band (404) ho to agla try hota hai, aur
     jo model asli mein jawab de wahi UI me dikhta hai. **Image engine par free quota
     paththar ka nahi** — 24 Oct ke test me image models 429 "quota khatam" de rahe
     the (OCR rasta 28 Oct ko free tier par chal raha hai — dono ki alag quota hai).
     Muft tasveer chahiye to Pollinations rasta hai; paisa kharch karna ho to Runware;
     aur agar aapke paas **Google AI Pro/Ultra subscription** hai to neeche wala
     Antigravity rasta bina API key ke chalta hai.)
     **Ek se zyada keys (pool):** `gemini_key.txt` me ek line per key, ya AI
     Thumbnail ke Gemini box me saari keys paste karke "pool me add karo". Free tier
     ki daily limit ek key ki hoti hai — pool me kai keys hain to ek thakne par tool
     agli key apne aap lagaata hai; saari thak jayein to saaf error dikhega, nakli
     koshish nahi. "pool hatao" poora pool mita deta hai.

3. **Optional library, unofficial data:** Google Trends (pytrends) — upar bataya gaya.
   UI me 0–100 ka nisbat aur "barh raha/gir raha" direction dikhta hai, "exact search
   ginti" ka dawa nahi. (Live test: 53 hafte ka data aaya.)

4. **Jaan-boojh ke NAHI jodi:** Social Blade (API paid), ChannelCrawler (free API ab
   nahi hai — paid SaaS), vidIQ/Creative Fabric (paid + key). Subscriber history ka
   kaam tool khud apne channel-scan snapshots se poora karta hai — jitni baar aapne
   channel scan kiya, utne asli points milte hain, kisi teesre party ke andaaze ke
   bina.

5. **Subscription rasta (API key nahi chahiye) — Antigravity CLI (Nano Banana 2):**
   28 Oct ko tool me "Antigravity — Nano Banana 2 (aapki subscription)" engine juda.
   Ye Google ki **AI Pro/Ultra subscription** par chalta hai — API key aur uski quota
   ka sawal hi nahi. Shart: us machine par Antigravity CLI (`agy`) install aur ek baar
   sign-in ho (Antigravity CLI ka download page; tool apne aap
   `%LOCALAPPDATA%\agy\bin\agy.exe` dhoondh leta hai). AI page par engine menu me
   "Antigravity" nazar aata hai. Sach: tasveer 60–175 second leti hai (CLI ka apna
   kaam hai) aur quota token-based hai (5-ghante aur hafte ki resets) — is liye tool
   isme seedha 4-shot batch bhi chalata hai aur cost ki jagah "subscription quota"
   likhta hai. Live verified (28 Oct): 4-shot batch ke 8 cards, Nano Banana 2,
   1376×768, koi paisa nahi.

**Accounts ka poora hisaab (kya kahan maangta hai):**

| Platform | Account/key chahiye? | Is se kya chalta hai | Bina iske |
|---|---|---|---|
| Google/Gemini (aistudio.google.com — free API key; AI Pro subscription alag) | haan (key) | OCR (default, behtareen padhai, machine par zero bojh), "Gemini se dekhwa lo", Gemini image engine | local RapidOCR/Tesseract OCR chalti hai (CPU, GPU ki zaroorat nahi — bas slow) |
| Antigravity CLI (Google AI Pro/Ultra subscription) | subscription + CLI sign-in, API key nahi | AI Thumbnail ka Nano Banana 2 engine (bina paisa) | engine menu me wo option "install/sign-in" kakeh ke chhup jaata hai |
| Runware (runware.ai — paid, $0.0006/image se shuru) | haan (key) | AI Thumbnail ke behtareen models (Z-Image Turbo, FLUX.3 Klein, P-Image), inspired-vs-copy ka naap | Pollinations muft rasta + Gemini/Antigravity engines |
| YouTube Data API v3 (aistudio/cloud console — free quota) | haan (key) | Trending scan (official chart), official topic tags | yt-dlp wale scans (channel/topic) phir bhi poore chalte hain |
| Kuch nahi | — | poora naap engine, Deep Analysis, pattern, comparison, benchmarks, Behtar banao | — |

**Sirf Gemini key wale ke liye quickstart (jaise GPU-raakha dost):** zip kholo →
`setup.bat` → `python clicklab.py` → AI page par Gemini key daalo → bas. Poora
measurement engine, channel/topic scans, OCR (Gemini se), "Gemini se dekhwa lo" aur
Gemini/Antigravity image rasta chal jaate hain; Runware/YouTube keys ki zaroorat
nahi. OCR ka local fallback bhi apne aap ready rehta hai.

Is zip ke andar koi key nahi hai — jo bhi use kare, apni key khud lagaye.

## Install kaise karein

Windows par: folder kholo, `setup.bat` double-click. Wo Python check/install karta hai,
`requirements.txt` ki packages lagata hai, aur Tesseract (fallback OCR) install karta
hai. Kuch optional package fail ho to bhi tool chalta hai — setup khud batata hai ke
kis ka asar kya hoga.

Manual tareeqa: `python -m pip install -r requirements.txt`.

## Chalana kaise

`ClickLab.bat` double-click — browser apne aap `http://127.0.0.1:8028` khol leta hai.
Ya terminal me `python clicklab.py`. Agar 8028 kisi aur cheez ne bhara hua ho to tool
agla khali port le leta hai aur terminal me poora address chhap deta hai — usi ko
browser me kholo.

## Pehli baar chalane par

Ye zip bilkul saaf hai: isme pichle user ki koi history, koi scan, koi thumbnail cache
nahi hai. Pehli chalaane par `thumb_output/`, `reports/`, `models/` folders apne aap
ban jaate hain. `models/` me face-detection ka model pehli face-naap par ek baar
download hota hai (uske baad offline chalta hai); download fail ho to Haar fallback
chalta hai aur UI me saaf likha aata hai kaunsa engine chal raha hai.

`thresholds_measured.json` history nahi hai — wo tool ki apni naapi hui paimaana-failein
hain (102 videos par measure ki gayi), isi liye ye zip ke saath di ja rahi hai taake
naye user ko bhi wahi asli thresholds milein.

## Naap ka rule (jo har jagah same hai)

Channel kholte hi tool uski **saari gini gayi listing** naapta hai — long videos aur
shorts dono, har type ki 400 tak (us se zyada ho to "+" ke saath ginati dikhti hai).
Koi sampling nahi, koi chhupa hua "sirf 50" nahi. Poora channel naapne me waqt lagta
hai, isliye progress bar live chalta hai aur har naapi hui video turant table me
dikhti hai. Comparison, channel analytics, pattern — sab jagah sirf wahi videos ka
hisaab hai jo waqai naapi gayi hain, aur naapi-banai-gini ka farq har jagah likha
hoti hai. Purane adhoore scans par "naap adhoora" chip aur "poora channel naap lo" ka
button milta hai. Topic scan me aapne jitni videos maangi ("50 tak" jaisa number),
tool utni puri karne ke liye khamoshi se extra search rounds chalata hai — ek search
se kam aayi to chhup kar "36 hi aayi" nahi kehta; asli stock khatam ho tabhi kam
dikhai degi, aur tab bhi ginti saaf likhi aati hai.

## Topic Funnel aur nayi guided cheezein (credit bachane ka rule)

"Topic funnel" view (sidebar me) guided flow hai: **niche → us-niche ki styles → keywords →
scan**. Tool apne aap ek bhi search nahi karta — har step par aapka button; jab tak "aage
barho" na dabaayein, koi kharcha nahi hota. Keywords step YouTube ke apne suggest box aur
us search ke natijon ke titles ki ginti se bante hain — koi extra API key ya model nahi.

Zoom view (kisi bhi video par click) me "Transcription laao" button hai: wo us video ke
**YouTube ke apne subtitles** (manual ya auto-generated) laata hai — ek baar, phir folder ke
`thumb_output/tr/` me cache ho jaata hai (dobara click par network nahi). Subtitles na hon to
saaf likha aata hai; jhoot kabhi nahi. Aisi videos (silent animation, quiz-type jisme sirf
screen par text hai) ke liye zoom me "Screen text (OCR)" button hai — video ke frames se
screen ka text nikalta hai, aur ye saaf label ke saath ke "ye screen par dikha hua text hai,
boli ki hua kuch nahi".

Selection (Studio table ki checkboxes) ke saath **bulk buttons** bhi hain: "Subtitles laao
(bulk, 15 tak)" aur "Screen text OCR (bulk, 4 tak)" — ek-ek karke, neeche chhota queue panel
dikhata hai kaun cache se aaya (0 kharcha) aur kahan galti aayi. Jo model calls hoti hain
(verdict, keywords) wo pehle aapki Gemini key se karti hain; Gemini limit/timeout/dead-model
ho jaaye to apne aap doosra Gemini model, phir muft Pollinations rasta — aur har jawab ke
saath likha hota hai ke jawab asal me kisne diya.

Tulna (cmp) page par "sirf jeetne wali" filter hai (jeet ka rule: us scan ke views/day median
ka 2×+ — ye hamara rule hai, YouTube ka nahi), usi filter par do extra cheezein:
"Jeetne walon ka model-verdict" (model se patterns + per-video hypothesis, ek baar, cache ke
saath, hamesha "ye model ki raay hai, sahy-sambandh hai wajah sabit nahi" label ke saath) aur
"Jeet ka formula?" card (bina model ke, sirf apne naape ka winners-vs-baaki tulna — title,
tags, thumbnail text, chehra %; group 5 se chhota ho to card dikhta hi nahi).

Channel/topic scan me "Style jeet" section thumbnails ka style-andaza pixels se lagata hai
(line art / dark / asli footage / flat) aur jeet ka naap views/day se karta hai — style ka
andaza galat ho to aap theek kar sakte hain, aapki fix hamesha pehle lagti hai. "Meri
Thumbnail" par apni thumbnail ka style-andaza us scan ki chalne wali styles se tulda jaata
hai — ye andaza hai, guarantee nahi, aur tool kabhi "badlo" nahi kehta. Topic scan ke neeche
"Best competitors" usi scan ki videos ke views/day se rank karta hai (poore channel data se
nahi) — kam video wali row par "kam bharosa" label ke saath.

## Is pass ki nayi cheezein (short)

- **Ab bilkul poori screen par:** koi width cap nahi — content sidebar ke baad jo
  jagah hai wahi bhar-ta hai (2730px ki desktop par bhi dayein taraf khaali patti
  nahi). Sirf lambi notes/paragraph ki line-lambai padhne-layak limit par rehti
  hai; tables, charts aur panels poori width par hote hain. Mobile par waise hi
  sab single-column.
- **Month by month — channel ka apne aap se tulna:** Channel history me naya
  section. Do alag series, dono ka sach alag likha hai:
  1. *Readings table* — asli mahine-baar gain/drop (subscribers, views, uploads),
     lekin sirf un mahinon me jab aap ne waqai snapshot liya tha. Mahina bina
     reading ka table me nahi aata — uska badlav zero nahi, unknown hai.
  2. *Upload-month cohorts* — har upload mahine ki videos ke AAJ tak ke views,
     share, cumulative aur chart. Ye "us mahine kitne views mile" nahi hai (ek
     scan se ye pata hi nahi chal sakta) — ye "us mahine chhapi videos aaj kitna
     kama rahi hain" hai, isliye label yei kehta hai.
     Series khud barhti hai: jitni zyada scans/snapshots, utni zyada mahine.
- **Channel creation date:** Channel analytics ke header me "channel created" chip
  aur uske neeche poora source likha hota hai — ya to YouTube ke About page se
  pakki date, ya (wo na mile to) listing ki sabse purani upload, jo sirf itna
  kehti hai ke channel "kam az kam itna purana hai". Purane scans par ek
  **fetch joined date** ka button hai — ek baar network se le kar scan file me
  likh deta hai, dobara kharcha nahi. Ye date Channel history, channel tulna
  (cmpc) ke cards aur table headers, video ke poore analysis, aur Competitor
  bank — har jagah source label ke saath dikhti hai.
- **Upload ka waqt:** naye channel scans (YouTube key set ho) har video ka asli
  publishedAt time rakhte hain — table me date ke neeche time + "asli waqt, API
  se" label, aur Content table me 7×24 ghari ka naqsha usi se banta hai.
  Purane scans par waqt ka naqsha **time backfill** button se bhar jata hai
  (1 API unit, ek hi baar per channel). CSV me `published_time` column (UTC).
- **Competitor bank:** kisi bhi video card ya uske poore analysis me **Competitor
  banao** — ek click me save. Style ka box classifier ka andaza prefill
  karta hai (aapka chuna final hota hai); box khali bhi chhoda ja sakta
  hai — record phir bhi save hota hai aur bank me honest note dikhta hai
  ("classifier pehchaan nahi paaya — zoom me khud chun lein"). Niche likh kar save. Sidebar me naya **Competitor bank** view:
  har record us din ke scan ka snapshot hai (numbers "save ke waqt ke" likhe
  hain), channel ki creation date aur aakhri upload ke saath; "poora analysis"
  seedha us scan ka wo video khol deta hai. Bank file `thumb_output/cmpbank.json`
  hai — aapka data hai, share zip me nahi jata.
- **Niche Finder:** sidebar ka **Niche Finder** tab — topic se channels ki
  dhoondh, har channel ki **asli gin** (RSS se channel ki umar aur latest
  uploads ke views, listing se kul uploads aur median views) aur do
  condition filters (*naya channel* = 6 mahine se naya; *chhota magar
  bara*). Iske liye **koi extra API key lazmi nahi** — wahi raaste hain
  jo Channel analytics use karta hai (YouTube key ho to candidates aur
  behtar). Shartein aur gin screen par likhi hoti hain: kitne candidates
  **check** kiye vs kitne **qualify** hue, aur kitne be-taaluq channels
  strict filter ne bahar rakha. Har dhoondh `thumb_output/scans/` me
  mehfooz record ban jaati hai jo top bar ke **Scan history** button se
  dobara khulta hai — numbers dobara naape nahi jaate, wahi purane
  number rekonstruekte hain.
- **Scan history:** top bar ka 🕘 button — har topic/channel/Niche scan ka
  immutable record apne machine par. Doosre laptop par data le jaana ho to
  `thumb_output\` copy karo; `git pull` is folder ko chhuta hi nahi.

## API keys ka pool (bulk) aur side menu ka hide — latest pass

- **Keys bulk me:** YouTube aur Gemini dono ke liye ab **pool** hai — `youtube_key.txt`
  / `gemini_key.txt` me ek line per key, ya app ke key box me saari keys paste karke
  "pool me add karo". Jab kisi ek key ka quota khatam hota hai (403/429) to tool
  chup-chaap agli key lagaata hai; saari keys khatam hon to saaf error. Ye sirf
  free-quata wale providers (YouTube Data API, Gemini) ke liye hai — Runware paid
  hai, usme ek hi account ki key rehti hai. Pool ki ginti UI me sach dikhti hai
  ("pool me N keys") — dikhawa nahi.
- **Side menu chhupana:** sidebar ke upar collapse button (ya `Ctrl/⌘ + B`) dabao —
  side ki pills chhup jaati hain aur content poori screen phail jaata hai; topbar me
  menu button wapas khol deta hai. Ye setting yaad rehti hai (reload ke baad bhi).
  Pills dikhti hon to content utna hi kam jitni sidebar, chhupi ho to poori width —
  dono screens poori verified hain (koi cheez screen se bahar nahi khisakti).
- **YouTube key card ab har jagah milega:** pehle wo sirf Competitors page par dikhta
  tha (jab tak koi scan khula na ho). Ab **AI thumbnail page par Gemini key card ke
  bilkul neeche** "YouTube Data API key" card hai — wahan bhi saari keys paste karke
  "pool me add karo" dabao, chip par ginti sach dikhegi.
- **Screen ka auto-adjust (global):** ek bug dikha tha — badi screen par aakhri card
  ka border katta hua (kuch browsers grid items ko kheench lete hain). Ab har grid par
  guard laga hai: cards screen se bahar kabhi nahi khisakte. Outlier radar ke cards
  430px se bade nahi hote aur poori width par barabar bikharte hain — na kata hua, na
  dhundhla. 1366×768 (laptop) se 2730 tak, side menu khuli ya band — sab par verified.
- **Bahut badi screen par content column center:** 2100px se chaudi screen par content
  apni jagah ruk kar screen ke beech center ho jata hai — dono taraf barabar kinara,
  dayein taraf ka border hamesha nazar aata hai. 2100px se kam jagah par pehle jaisa
  hi poori width use hoti hai — koi chhota-pan nahi. Ye isliye zaroori tha: kuch
  Windows/DPI settings mein browser window screen se thodi zyada chaudi ho jati hai
  (maximize bug), aur tab dayein taraf ka hissa screen ke bahar chala jata hai.

## Ghanti-war auto reading aur candlestick graph — latest pass

- **Tool ab khud ghanti-war naapta hai:** server chalu rehne par ek daemon chalta hai —
  pehla round ~1 minute baad, phir **har ghante** — jo bhi channel Channel History me
  tracked hai uski ek halki ASLI reading: subscribers About page se dubara (`bust=True`),
  videos ki current views listing pages se (listing me views khud hote hain — dobara
  padhna asli dobara-naap hai). Har reading `thumb_output\hist\<cid>.json` me save
  hoti rehti hai. **Server band = readings band** — jitni der tool chala utni hi series
  bhari milegi; kuch bhi peeche se bhara nahi jaata.
- **Candlestick (Channel History me naya card):** metric (subscribers/views/uploads) aur
  window chuno — 24 ghante = har ghante ki candle, hafta = har 6 ghante, mahina/sab =
  har roz ki candle. Chart par hover/har candle par us bucket ki asli readings ka
  open/high/low/close aur kitni readings se bani — sab likha hota hai.
- **Imandari ke rules (graph ke liye bhi wahi):** bucket khaali ho to **koi candle
  nahi, sirf gap ka nishan** — reading hi nahi li gayi to candle banana banawat hoti.
  Ek hi reading → flat doji (ek asli number). Views-candle me sirf wohi readings jo
  **usi waqt** naapi gayi thin (per-video numbers us snapshot ke waqt measure hue);
  subscribers YouTube ki taraf se rounded hain — chhote window me flat candles
  aana **normal aur sach** hai, chhupaaya nahi jaata.
- **Quota/prabhav:** sampler yt-dlp/urllib use karta hai — **YouTube Data API unit
  kharab nahi hota**; prati channel ghanti-war ~2 page-reads, beech me 2 second
  farq. History files slim snapshots se bharti hain (~20-25KB prati reading) aur
  1200 readings tak mehfooz rehti hai (≈ 50 hafte).
- **Agar candles khaali dikhein:** note khud samjhata hai — sampler ka pehla round
  server ke ~1 minute baad hai; "Take a snapshot now" se usi waqt ki asli reading
  mil jaati hai, aur "Everything" window purani asli readings dikhata hai.

### Candle chart fix — numbers axis par, hover poori column par, "is ghante kitne aaye" — latest pass

- **Chart ab chart jaisa dikhta hai:** flat readings wali line chhat se chipki hui
  nahi **beech baithti**, aur axis par **5 gridlines + asli numbers** hote hain.
  Flat series par upar chhota note khud likha aata hai ke YouTube ke public counts
  rounded hain — us rounding se chhota asli farq dikhna mumkin hi nahi. Ye banawat
  nahi: data wahi ka wahi hai, peshkani theek ki gayi hai.
- **Hover = poori column:** candle ke 2px ki tangein nishana karne ki zaroorat
  nahi — bucket ki kisi bhi jagah cursor le jao, uska box aa jata hai.
- **Box ki pehli line wo number hai jo chahiye:** **"gained since previous real
  reading: +X"** — pichhi asli reading se is reading tak kitne aaye. Window ke
  kinare par ye hisaab backend khud bhejta hai. Pehli (ya koi comparable reading
  na ho) to seedha likha aata hai *"— no comparable earlier reading on record"*.
- **Do qisam ki readings ka farq nahi ginna:** listing-sampler (~150 videos) aur
  poori-channel-scan (saare videos) ke totals alag cheezein napte hain. Tool
  cross-qisam ka "gain" khud reject karta hai aur window me dono qisam mix milne
  par chart ke neeche **heads-up note** chhapta hai — taake 20 lakh se 2 hazar
  dikhta "chanter" jhoot na lage (wo scope ka farq hai, girawata nahi).
- **Draw candles** dabate hi "Drawing candles from the real readings on record…"
  dikhta hai — button bekaar nahi lagta.

### Channel History ki list, re-scan aur chart pichay le jaana — previous pass

- **Channel History = pehle LIST:** `#/hist` kholte hi un saare channels ki table
  dikhti hai jo kabhi scan/measure hue (naam, readings ki gin, aakhri reading ka
  waqt, subs) — upar naam ka filter bhi. Jo channel sirf measure hua hai (uski scan
  file delete bhi ho gayi ho) wo bhi list me aata hai; uska record khul sakta hai,
  sirf "Scan JSON" ka link nahi milta.
- **"Open record"** par us channel ka poora record: candlestick card, har subscriber
  reading, saare snapshots — aur wahin **"Re-scan channel — fetch new videos"**: ye
  us channel ki poori nayi scan chalata hai (naye videos + fresh subscribers), aur
  poori hote hi history me nayi reading pka jaati hai — candles me dikhne lagti hai.
  Chhote channel par ~1 minute, bade par kuch minute (job progress bar ke saath).
- **Candle par cursor = forr numbers:** har candle/dashed-gap par mouse le jaao to
  chhota box time, readings ki gin aur open/high/low/close dikhta hai; gap par
  likha aata hai ke us bucket me koi reading li hi nahi gayi.
- **Chart ko pichay le jaana (crypto chart jaisa):** "‹ earlier" ek window peeche,
  "‹‹ ×7" saat windows ek saath; bar me window ki **asli tareekh** likhi hoti hai.
  Button apne aap band ho jaate hain jab peechay koi asli reading possible nahi
  (yaani pehli reading se aage) — andhere me andhi chapaq nahi.
- **Note:** readings wahi tak hain jab tak **tool chalta raha** (server band =
  sampler band). "Everything" window me pan ki koi zaroorat nahi — wo shuru se
  poori series bana deta hai.

## Troubleshooting

- `yt-dlp not found` — matlab `pip install yt-dlp` skip hua. Wo lagao, phir tool restart.
- Chehre/text wale numbers khali — upar wale optional packages me se wo wala lagao;
  tool khud jagah-jagah likh deta hai ke kaunsi cheez ke bina kaunsa naap chhoota.
- AI Thumbnail bina key ke bhi chalta hai — engine "Pollinations (muft)" select karo.
  Runware/Gemini engine key maangte hain — key upar batae tareeqon se daal do.
- Trending card "key set nahi" kehta hai — YouTube Data API key chahiye (free quota
  hai), phir wo apne aap chal padega.
- Doosra instance pehle se chalu ho to doosra band karo ya tool agle port par chala
  jaayega (terminal me address dekho).
