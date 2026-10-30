# ClickLab v3 — video bechna: title + thumbnail (CTR)

TrendRadar ne topic dhoondha, ChannelPulse ne bataya kaunsa format aapke channel par chalta hai — aur machine video bana deti hai. Insaan ke paas do cheezein bachti hain: **kaunsa topic** aur **video bechna**. Bechna = **title + thumbnail**. YouTube ka poora system isi par chalta hai: CTR (kitne logon ne click kiya). Ye tool usi kaam ke liye hai — andaze se nahi, numbers se.

Video ke andar ka kaam (script, voice, editing) ye tool **nahi** karta — wo video tool karta hai. Yahan sirf wo cheezein hain jo upload ke baad aapki hain: title, thumbnail, aur un par faisala.

## Tabs

| Tab | Kya karta hai |
|---|---|
| 📺 **Channel Analytics** *(nayi)* | Channel ka **naam, @handle, UC-… id, ya link** daalo → **50 channels tak** (YouTube ke apne Channel filter se: naam, @handle, subscriber, verified badge — sab YouTube ka diya hua, mera likha hua nahi). Phir channel kholo → **poora channel**: kul videos (gine gaye, 400 tak — uske aage `+`), **shorts aur longs ALAG-alag gine** (YouTube ke asli `/videos` aur `/shorts` tabs se), har video ki **asli listing** (tags, poori description, chapters, likes, category) + thumbnail ke naap, **upload ka routine** (hafta war kitni, kaunsa din, aakhri upload kitne din pehle, pichhle 30/90 din me kitni), **nayi vs purani videos ki raftaar**, **hit/flop ka nisbat** (apne hi median se), **niche** (YouTube ka apna category + uske category ke naam + keywords se), **kamai ka ANDAAZA range me** (aur apna Studio RPM daalne par wo aapka asli number ban jaata hai), aur **channel ke andar ka pattern** (Deep Analysis, p-values ke saath) — sab **YouTube Studio jaise Content table** me: har video, sort + filter + row kholkar detail (neeche "UI ka look" dekho) |
| 🕓 **Channel History** *(nayi)* | Channel ki **wohi readings jo is tool ne khud li thin** — waqt ke saath table aur chart. Koi YouTube ka past data nahi joda gaya (wo milta hi nahi, is liye banaya ja sakta tha — aur wo jhooth hota). Har scan par ek snapshot `thumb_output/hist/` me (hadd 60), aur **har snapshot ke saath ye record hai ke usne kaunse metrics us din dobara padhe** — jo metric us din nahi padha gaya, wo screen par **`—` aayega, 0 nahi**. Do snapshots ka **match hisaab sirf unhi videos par** jo dono me maujood thin; nayi aur hatai gayi videos alag gini jaati hain, aur jinki `vm` values same thin un par likha hai **"dobara nahi naapa gaya"**. **Do readings ka gap aadhe din se kam ho to per-day rate `—`** dikhega (itne chhote waqt ka daily rate shor hai, signal nahi). Ratio ke bars **log paimana** par, aur har bar ke tooltip me dono exact numbers |
| 🏆 **Channel Tulna** *(nayi)* | Aapki shart: *"ek channel mera, dusra competitor"* — ab **1 + jitne chahein** (checkbox se chuno; **order matter karta hai**, sabse pehle chuna hua "mera" hai). **24 maapon** par side-by-side table (subscriber, kul videos, shorts ka hissa %, median views, views/day, hit/flop rate, uploads/hafta, pichhle 30 din ki kamai, tags/description ki safai, chapters %, thumbnail ke naap…), har row par **jeetne wale ka nishan**, aur **kaun jeet raha hai** ka imandar jawab: har maap par **Mann-Whitney p-value + dono ka n** (chhota sample apne aap flag hota hai). Har column ka RPM-band **us channel ke apne niche** se banta hai. Wo table **teen hisson** me hai — **Maap / Kaun jeeta / Kamai** — wahi Studio style (neeche "UI ka look" dekho) |
| 🔎 **Competitors** | Topic daalo → **12 / 25 / 50** videos (default 50). "**search chaudo**" tick karo to tool YouTube ke apne auto-suggestions se 5 extra queries milata hai aur sabko merge karke duplicate hataata hai. "**asli tags + description bhi lao**" tick karo to har video ka **asli tags list, poori description, chapters, likes, channel subscribers** bhi aa jaate hain — **koi guess nahi**, jo YouTube par set hai wahi (naapa: 12 videos = 5.3 second 8 threads par, ~0.45s/video). Har thumbnail download karke **napta** jata hai: text, uska size, contrast, outline, chehre, rang, bheed, composition, title ki lambai/number/sawal, aur ye ki thumbnail title ko dohraata to nahi raha |
| 📄 **Har card par "iska poora analysis"** | Ab sirf thumbnail nahi — **us video ki poori listing**: **thumbnail score**, **title score**, **listing score** + checklist (title length, number, sawal, description ki lambai, tags ki ginti, chapters), **asli tags** (chip par click → Title Lab me daal do), **asli description** poori, chapters table, views/likes/comments/subs. Neeche **CTR/retention ka imandar block** (neeche dekho) aur apne Studio numbers import karne ka form |
| 📊 **Deep Analysis** | Har pattern ke har hisse ka **median views/day**, poore set ke muqable **lift**, aur ab **Mann-Whitney ka p-value** + **age/channel-matched lift (`m_lift`)** — yaani "zyada chala" ka dawa ab sirf number nahi, uski statistical sah-maani bhi. Listing ke pattern (tags, description, chapters, comments) bhi. **benchmark table (p10/p25/median/p75/p90) poora asli naapa hua**, koi ghandha hua number nahi |
| 🏆 **Jeete topics → ideas** | Aapki shart thi: *"us search par 50 videos hain — un me se best ko dekh kar un ke titles/tags/keywords se 10 suggestions do, aur un par thumbnails bhi banao."* Ye tab wahi karti hai. **Jeet** = views/day (umr se baantkar), aur jeeton me **ek channel se zyada se zyada 2** videos rakhi jaati hain — warna ek hi channel poori list le leta hai. Phir TF-IDF **sirf jeeton ke titles se** naye topics umerata hai, aur har candidate ka **support asli ginti** se naapta jata hai (jeeton ke kitne titles me ye phrase hai vs baaki ke kitne me) — jo phrase asli titles me nahi milta, wo idea banta hi nahi. Har idea ke saath: **titles** (har title ke neeche uska source video + uska asli views/day), **us channel ke ASLI tags**, **keywords** (jo inhi jeeton ke titles/tags me saath me aate hain), jeeton ke thumbnails par likha **asli OCR text**, aur **"is topic par thumbnail banao"** — us jeetne wale ki photo **reference** ban kar (strength ka slider aapka hai) AI tasveer banati hai, aur **wahi poora naap us par dobara chalta hai** (score, 320px par kitna text sach me padha gaya, asli cost). Har bani tasveer ke neeche **us idea ke apne jeeton ke median se tulna** aur **"dobara banao"** ka button. **Imandar caveat:** patterns aur tags ki table sirf *sah-observed* hai — **n = 46 par ye sirf ginti hai, saboot nahi**. Jo cheezein statistically significant nikli thin, sirf wahi Deep Analysis me **p-value aur n** ke saath dikhti hain |
| 📈 **Apna CTR + Calibration** | YouTube Studio ki CSV paste karo (dry-run pehle dikhata hai kya mela) → apni videos ke **asli CTR** par **Ridge + 5-fold** se score ke wazan fit hote hain. Cross-validated R² 0.05 se kam hua to fit **reject** — tool khud-dhoka nahi karta (neeche dekho) |
| 🖼 **Meri Thumbnail** | Apni file ka path / YouTube ka link / file chooser. OCR se text (ek baar poori size par, ek baar **320px par** — ye asli "browse par kaun padh sakta hai" ka test hai), chehre ke boxes, outline contrast, **4 asli YouTube sizes** (1280/320/210/168 px) preview, **aapki percentile us scan ke 50 videos me**, aur apne Studio ke asli CTR/retention daalne ka form |
| ⚡ **Behtar banao** | Har thumbnail card par. Tool **wohi photo rakhta hai**: purana text mitaata hai, title se 2–3 behtar shabd chunta hai (jo pehle se thumbnail par na likhe hon), unhe khaali jagah par outline ke saath bara likhta hai, rang/sharpen sudharta hai, subject bara karta hai → **photo jitne tareeka uthati hai utne versions (3–4)**, aur **har version ko dobara napkar score ka farq** dikhata hai. **Muft, ~4 second (naapa hua 4.3s), koi key nahi** |
| 🎨 **AI Thumbnail** | **Runware** se nayi tasveer. Idea likho, ya kisi competitor card par **"🎨 AI se banao"** dabao (uska title aa jaata hai), ya **"Is se inspire ho kar naya"** dabao — wo us video ka **title + asli tags + asli description + thumbnail ka OCR** jodkar idea banata hai aur uska thumbnail **reference** bana kar (strength 0.55) **inspire ho kar nayi** tasveer banata hai, copy nahi. Ek click me **4 alag art direction**, har ek wahi benchmark se napi jaati hai, **sabse upar wahi jo jeeti hai**. **Size aap chunte ho** (1024×576 / 1536×864 / **2048×1152**), **reference se kitna door jaana hai wo slider aapka hai**, aur har card par **4K ka button** (naapa: 3842×2180, $0.010 — ya **muft** Lanczos wala rasta). Har image ki **asli cost** Runware ke apne hisaab se dikhti hai, aur har card par **reference se asli naapa hua farak** |
| 🧠 **Thumbnail Generation** | Model ka faisala **kis naap par** hua (6 models ka asli test + asli price), size ka ladder aur uska daam, 4K ka asli rasta, kharcha kam karne ke tareeke, text ka rule, aur **reference (i2i) ka sach — naape hue numberon ke saath** |
| ✍️ **Title Lab** | Title ko YouTube ki tarah **truncate** karke dikhata hai — desktop browse (2 lines), mobile app (1 line), sidebar — kitne chars dikhenge, aur competitors ke asli titles isi size par. Neeche title ki jaanch |
| 🅰️ **A/B Variants** | Title+thumbnail ke jode save karo, CSV me nikaalo. Asli winner YouTube Studio ke "Test and compare" se hi pata chalta hai |
| 🔎 **Niche Finder** *(nayi)* | Topic likho (jaise "quiz", "minecraft parkour") → YouTube ke apne **Channel filter** se 6–50 channels dhoondh kar **har ek ki sirf asli gin**: channel ki **umar** (RSS ka joined-din), **latest 15 uploads ke views/tareekhen** (RSS), **kul uploads** (400 tak), **median views**, aur **reach = median ÷ subscribers** — rank isi se, "chhota magar chal raha hai" ka matlab size se zyada pahunch. **Do condition filters** (dropdown): *naya channel boom* = **6 mahine (180 din) se naya** + 100 se kam videos + subs ya median koi ek 1 lakh+; *chhota magar bara* = 4 saal+ purana + saal ke 12 se kam uploads + phir bhi 3 lakh+ subs ya 1 lakh+ median. **Strict match:** topic ka koi maayne wala lafz naam/handle/description ya titles me na mile to channel be-taaluq — bahar, aur ye gin bhi screen par. Sirf 10 hazar+ median wale list me aate hain; har dhoondh **Scan history** me mehfooz (kitne check kiye vs kitne qualify hue — dono gine) |
| 🏦 **Competitor bank** *(nayi)* | Kisi bhi scan ke video card ya uske poore analysis me **"Competitor banao"** → ek click me save (style box khali ho to classifier ka andaza, warna record bina style ke — bank me saaf likha aata hai "classifier pehchaan nahi paaya"). Bank view me har record us din ka snapshot hai, source label ke saath; **"jeeton se bank bharo"** us scan ki jeeti hui videos (2×+ views/day) style-suggestion ke saath bhar deta hai. `thumb_output\cmpbank.json` — aapka data, laptop copy par saath chalta hai |
| 🕘 **Scan history** *(nayi)* | Top bar ka button — **har scan ka mehfooz record** (topic, channel, Niche Finder dhoondh). Koi bhi record wapas usi ki table me khulta hai — numbers dobara naape nahi jaate; Niche records par **checked vs qualified** ki gin dikhti hai; delete bhi ho sakta hai. Niche dhoondh khatam hote hi row foran dikhti hai, page reload ki zaroorat nahi |

## Numbers ka matlab (jo tool check karta hai)

**In saari hadin ghandhi nahi, 102 asli thumbnails par naapi gayi hain.** Poora per-video naap `thresholds_measured.json` (is folder me, 102 rows) par hai — har threshold us distribution ka percentile hai (jaise `clutter_ok` = p90, `face_ok` ≈ p90, `h_ok` = p25, `cr_ok` = WCAG AA). Code me `TH` **ek jagah** hi asli value hai aur **UI wahi se padhta hai** (`/api/sys`) — page me koi doosra hand-picked number likha nahi, isliye docs aur UI kabhi alag nahi ho sakte.

| Check | Theek kya hai |
|---|---|
| **views/day (vpd)** | Tool ka ranking isi par hai, raw views par nahi. 3 saal purani video ke 3M views ≠ aaj ke 3M views. Views ÷ video ki umr = fair naap |
| **Text ka size @320px** | **18px+** browse par padha ja sakta hai; 10px se chhota mobile feed me gayab. Tool 320px par alag OCR karke dekhta hai ki sach me kitne shabd padhe ja rahe hain |
| **Text ka contrast (asli glyph vs uska background)** | **4.5:1 = WCAG AA pass** (`cr_ok`). Poore image ka contrast nahi, aur na box ke andar ka p5/p95 — ab **Otsu se nikaale gaye aksharon ke mask** ke pixels aur unke **theek peeche ke background** ka WCAG ratio naapa jaata hai (max 21:1). 102 thumbnails par: p10 = 2.2, median = 8.2, max = 20.75 — isliye 7:1 par score bhar jaata hai (`cr_full`). Purana tareeqa 5041:1 jaise number de raha tha, wo poora galat tha |
| **Outline (ring)** | Text ke girdh ki line aur uske theek bahar ke background ka ratio ≥ **3:1** (`ring_ok`, corpus p10 = 2.55) ho to text bache hue background par bhi tikta hai |
| **Shabdon ki ginti** | **1–4 ideal**, 5–8 zyada, 9+ mobile par nazar nahi aata |
| **Thumbnail title dohrata hai** | >25% shabd same = jagah barbaad |
| **Chehra** | Frame ka **8%+** chehra (`face_ok`) = acha; 1% se kam = koi faayda nahi. Ye had **102 thumbnails ke naap se hai** (max face area ka p50 = 2.3%, p90 = 9.1%). Detection **YuNet** (`cv2.FaceDetectorYN`, ONNX) se hoti hai — Haar se 102 par **68** chehre mile the, YuNet se **82**, aur 12-video wale purane scan me Haar **ek bhi chehra nahi** dhoond paaya tha |
| **Brightness / depth** | Brightness 0.10–0.60, tonal depth 0.45+ = image "pop" karti hai |
| **Bheed (edges)** | **8% se kam = saaf** (`clutter_ok`). Ye had bhi naapi gayi hai: 102 thumbnails par edge% ka p90 = 8 aur **poora max 12** — purani 22% wali had **kabhi bajti hi nahi thi**, yaani wo check theatre tha |
| **Blur** | Laplacian variance < 60 = thumbnail dhundhla hai (screenshot se aayi file ka sabse aam nuqsan). Ye naap size se azaad hai — 1280 par bhi, 2048 par bhi ek hi scale |
| **Composition (asli boxes se)** | Subject ka box **OCR ke text blocks + YuNet ke face boxes** se banta hai — koi edge-centroid andaaza nahi. Teen number: **dominance** (ek cheez kitni dominant hai; 0.32 se kam = bheed, 0.95+ = ek hi cheez), **subject ka size** (frame ka %; 7% se chhota = browse par dikhta hi nahi, corpus p25 = 7.2 p50 = 12.1 p90 = 30.0), aur **rule-of-thirds** (subject ka center kitna nearby third-line par hai; `thirds_ok` = 0.60, corpus p50 = 0.68). Jis thumbnail par na text ka box na chehra mila, wahan ye numbers **khali** rehte hain — 0 ghatana nahi |
| **Thumbnail ↔ topic/topic ka semantic match** | TF-IDF (sklearn) se: thumbnail par likha text aur topic/title ke shabd kitne milti hain. `t_topic` 0 = thumbnail ne topic ka ek bhi shabd nahi liya. 46-video ke asli scan me **median 0.0** nikla — yaani zyada tar thumbnails topic dohrate hi nahi (ye ek asli insight hai, kharabi nahi). Caveat: RapidOCR stylized text ko jodkar "BLACKHOLE" likh deta hai, tab "black hole" se match nahi hota |
| **Title** | 30–60 chars, shuru me number, competitor wale shabd **pehle 40 chars** ke andar |
| **Listing score** | 0–100: title ki jaanch + description ki lambai + tags ki ginti + chapters. Ye **asli** cheezon par hai jo us video par set hai — guess nahi |

Deep Analysis ka `lift` sabse zaroori hai, magar ab akela kaafi nahi — har bucket ke saath teen aur number aate hain:

- **`p`** — Mann-Whitney U (pure Python) se: us bucket ka views/day baaki sample se *talluq ke sath* alag hai ya nahi. **p ≥ 0.05 = "farq saboot nahi"**, chahe lift 5× hi kyun na dikhe. 46 videos ke asli scan me **sirf 2 buckets significant hue** (composition <0.55 ka nuqsan p=0.013, aur comments p=0.00 — jo palta hua kaaran hai, wajah nahi). Baaki sab "sig=False". Ye imandari hai, kamzori nahi.
- **`m_lift`** — matched control: us bucket ke videos ko **same umr aur same size ke channel** ke videos se tolā jaata hai, taaki "purani/chhoti channel wali video" ka asar lift me chhupa na ho.
- **`base_out`** — baseline me **wo hissa nahi jis ka wo feature naapa hi nahi gaya** (jaise bina text/thumbnail wale). Pehle baseline me gine bhi jaate the aur bache bhi — number neeche se upar dono tarah jhoota hota tha.
- **`min_n` = 5** — is se chhota bucket dikhta hi nahi (pehle "3 se kam" ka rule tha aur code us par bharosa nahi karta tha).

## Jeete topics → ideas — engine kya karta hai (`/api/ideas?id=<scan>&k=10`)

Ye aapki maangi hui cheez hai: *"50 videos me se best ko dekho, un ke titles/tags/keywords dekho, mujhe 10 suggestions + un par thumbnails do."* Ye wahi karta hai, aur har suggestion ye baat apne andar likhe hue deta hai ki wo kahan se aayi.

1. **Jeet ka faaisala views/day se** — raw views se nahi. `WIN_N = 12` jeete, `WIN_CAP = 2` (ek channel se zyada se zyada 2, warna ek channel poori list le leta hai). 46-video wale `black hole documentary` scan me: **12 jeete ka median 6.3K views/day vs 34 baaki ka 197/day** — ye ~32× ka farq hai, aur yehi is tab ki bunyad hai ki topic selection me asli signal hai.
2. **Topics TF-IDF se umer-te hain — sirf jeeton ke titles se.** Phir har candidate ka support **asli ginti** se naapa jata hai: "galaxy" 6/12 jeeton me vs 7/34 baaki me. Kuch candidates jeeton me akele hote hain ("big bang" 3 vs 0) — ye mazboot ishara hai, **par n = 3 hai**, isliye idea card ye khud likhta hai. Jo phrase asli titles me nahi milta, wo idea banta hi nahi — fantasy topics yahan nahi hain.
3. **Titles** jeeton ke hook patterns (colon, pipe, caps, number) se bante hain, aur **har title ke neeche uska source video + uska asli views/day** likha hota hai. Sach ye bhi hai ke hook jodne se kabhi-kabhi bekaar title banta hai ("Nasa | Black Holes Explained") — isliye source hamesha dikhta hai taaki aap khud theek kar lo. Ye tool ka sabse kamzor hissa hai aur chhupaya nahi gaya.
4. **Tags = us channel ke khud lagaye hue ASLI tags** (yt-dlp se), meri soch se nahi. **Keywords** wo shabd hain jo inhi jeeton ke titles+tags me **saath me** aate hain (co-occurrence), TF-IDF ki ranking se nahi.
5. **Thumbnail**: us idea ke sabse behtar jeetne wale thumbnail ko **reference** bana kar (i2i strength ka slider aapka hai, default 0.55) Z-Image Turbo se 8 tasveerein (~$0.0006/ea), aur phir **wahi poora naap un par dobara chalta hai** — score, 320px par sach me kitna text padha gaya, contrast, cost. "Acha lag raha hai" par faisala nahi hota. Har result ke neeche **us idea ke apne jeeton ke medians se tulna** (words, 320px text, score) aur **"dobara banao"** ka button hota hai.
6. **Had:** 46 videos ek topic ka slice hain, poora YouTube nahi. Ideas **is scan ke andar ke saboot** par khade hain — "ye topic guaranteed jeetega" is tool me koi nahi keh sakta, aur UI ye kehta bhi nahi.

## CTR aur retention — yahan imandari se kaam liya gaya hai

YouTube ka asli CTR/retention **sirf apni video ka** milta hai (YouTube Analytics owner-authorized hai; kisi aur channel ki video ka CTR public API me kahin nahi). Isliye:

- **Jo asli hai wahi asli dikhta hai**: views, likes, comments, subscribers, tags, description, chapters — sab yt-dlp se, `thumb_output\metac\` me cache.
- **Jo public nahi wo "index" ke naam par dikhta hai**, saaf label ke saath: **CTR index** = thumbnail score 50% + listing score 25% + likes/views percentile 25%; **retention index** = chapters + duration + engagement se, 5–95 ke beech. Dono ka kaam **tulna** hai, "YouTube ka CTR" ka dikhawa nahi.
- **Apna asli number aap khud daal sakte ho**: detail card aur 🖼 Meri Thumbnail me form hai → `thumb_output\own.json` me save hota hai, aur uske baad us video par **asli CTR/retention** dikhta hai. Ye sirf aapke channel ke videos ke liye kaam karta hai (jo aapke Studio me hain).

### Apna Studio CSV import + score ke wazon ki calibration (nayi cheez)

Ab ek-ek karke type karne ki zaroorat nahi: **📈 Apna CTR + Calibration** tab me YouTube Studio ki CSV paste karo (Analytics → Content → Videos → Export CSV). Importer 8 columns ko pehchan leta hai (title/id, publication date, views, impressions, CTR, average view duration, average % viewed) aur **dry-run** pehle dikhata hai kaunsa column mila aur kaunsi row kis video se melli — save tabhi hota hai jab aap "import" dabate ho. Melaam **video id** se pehle, na milne par title se.

Us ke baad **"wazan fit karo"** dabao: tool apni hi har video ka thumbnail **dubara naapta hai** (woi engine jo har scan me chalta hai — koi alag rasta nahi), aur **Ridge regression + 5-fold cross-validation** se 13 features ke wazan aapke asli CTR par fit karta hai → `thumb_output\calibration.json`. Score ab usi par chalega, aur har card par likha hoga ke wazan **calibrated** hain ya **heuristic**.

Do imandar baatein, khaas taur par:

1. **In-sample R² par bharosa nahi.** Fit tabhi chalta hai jab **cross-validated R² ≥ 0.05** ho. Naape hue 16 (jaan-boojhkar banaye gaye) CTR rows par in-sample R² **0.55** tha magar cv-R² **−0.63** — yaani wo model yaad kar raha tha, seekh nahi raha. Tool ne file reject kar di aur heuristic wazan hi chalate rahe. Ye gate isliye code me hai (`CAL_MIN_CV`), mere faisale par nahi.
2. **Kam se kam 8 video (`CAL_MIN_N`)**, magar 30 se kam par ye sirf ishara hai. Jo feature ka coefficient **minus** me nikle, uska matlab hai mere channel par wo cheez CTR ke **ulti** chalti hai — tool use 0 kar deta hai par asli signed coefficient dikhta rehta hai, chhupata nahi.

**Aaj tak ka sach:** calibration ka poora rasta test kiya gaya (16 rows import → features → fit → reject) magar **asli weights abhi tak nahi bane**, kyunke asli CTR ka data aapke paas hi hai. UI me jo bhi "heuristic" likha dikhe, uska matlab wazan engineering ke andaze hain — chhupaya nahi jaata.

## AI thumbnail — Runware (model naap kar chuna gaya, andaze se nahi)

Aapki shart thi: **model acha aur sasta, text bhi handle kare, minimum kharcha.** Isliye Runware ke 6 models 24 Oct ko **asli test** kiye — ek hi prompt, cost `includeCost:true` se (Runware ka apna hisaab), aur "text sahi likha ya nahi" **ClickLab ki apni naapi** se (OCR + 320px par padhna + score):

| model | ek image | asli test me kya hua |
|---|---|---|
| **`runware:z-image@turbo`** ← default | **$0.0006** (4-task batch me ek task $0.0012 gaya) | 1.3–2 second, OCR ne "GRAVITY" sahi padha, 320px par text nazar aaya, **score 98**. Sabse sasta, sabse tez, text bhi saaf |
| `bfl:flux@3-image-klein` | $0.0025 | asli photo jaisa look, par text bigaad diya ("GRAVI"). 4× mehnga |
| `prunaai:1@1` | $0.0044 | text sahi, score 94 — par 7× mehnga |
| `prunaai:p-image@ideogram` | $0.0113 | 9 second aur text ka kachra — score 32. Reject |
| `google:nano-banana@2-lite` | $0.0336 | 16:9 size hi support nahi karta (fixed list hai). Reject |
| `bytedance:seedream@5.0-pro` | $0.048 | is kaam ke liye zaroorat se zyada mehnga |

### Size ka ladder (teeno daam 24 Oct ko asli naape gaye)

| size | ek image (range) | kab |
|---|---|---|
| 1024×576 | **$0.0006–0.0012** | try karne ke liye — 4 soch ~$0.0024–0.0048 |
| 1536×864 | $0.0013–0.0025 | beech ka rasta |
| **2048×1152** | $0.0032 | **zyada kaam ke liye kaafi** — in models ki apni hadd 2048 px hai |
| **4K (upscale)** | **$0.010** | alag kaam: `prunaai:p-image@upscale`, 8 MP target → **naapa hua 3842×2180, 13 second** |

> Range isliye kyunki ek hi model + ek hi size ka bill din bhar alag-alag aata hai — 24 Oct ko 1024×576 do batches me **$0.0006** aur **$0.0012** dono bill hua, aur 1536×864 teen tasks $0.0013 par ek task $0.0025 par. Tool wohi dikhata hai jo Runware ne bill kiya, isliye har result par apni **asli** cost likhi hoti hai.

Tool ab tasveer **sikodta nahi** — jis size par banayi, usi par save karta hai. Analysis har size par sasta hi hai (naapa: 0.14s at 1280, 0.18s at 1536, 0.29s at 2048 — tool internally 120px/400px par napta hai). Yaad rakhne ki baat: **YouTube browse/player apni taraf se 1280×720 tak hi rakhta hai**, isliye 4K ka fayda zoom/print tak mehdood hai — aur 4K generation se nahi, upscale se aata hai. Har card par do buttons hain: **$0.010 wala asli upscale** aur **muft wala** (Pillow Lanczos + sharpen — paisa zero, par nayi detail paida nahi hoti, sirf tasveer badi hoti hai).

### Reference (i2i) ka sach — pehle jo likha tha wo ghalat tha, ab naapa hua hai

24 Oct ko ek hi prompt, ek hi model, sirf reference ka tareeka badal kar test kiya. "Farak" usi 0–100 scale par jo har AI card par dikhta hai:

| tareeka | reference se farak |
|---|---|
| koi reference nahi | **13** |
| `imageUrls` bheja | **16** ← yaani **ye param is model par koi asar nahi karta** |
| `seedImage` + strength 0.30 | **1** (reference ka remix) |
| **`seedImage` + strength 0.55** | **3** ← default, "inspired, naya" |
| `seedImage` + strength 0.85 | **9** (rang-roop barkaraar, scene naya) |

Teeno calls ka daam same tha: **$0.0006** — reference muft hai, farak sirf strength ka. Iska matlab v2 ka "reference" **theatre tha**: `imageUrls` us model par ignore ho jata tha. Ab **`seedImage` + `strength`** bheja jaata hai (`strength` akela bhejne par Runware `invalidDependency` deta hai), aur AI tab me uska **slider** hai. Default 0.55 par reference ka sirf rang-roop mehsoos hota hai — scene, layout aur chehre naye bante hain, isliye **copyright ka khatra kam** rehta hai. Phir bhi **har card par apna asli naapa hua farak** dikhta hai taaki aap khud faisala karo: **≤2 = remix (khatra sabse zyada) · ≤8 = inspired · ≤15 = kaafi naya · usse zyada = bilkul naya**.

### Text ka rule (sabse zaroori faisala)

Is rule ki shuruat is soch se thi ke diffusion models text bigaad dete hain. **24 Oct ko maine apni banayi hui images khud dekhi — wo soch is model par sach nahi nikli:** `z-image` ne "MYSTERY OF BLACK HOLES" teeno baar poori sahi spelling me likha tha. Meri purani report ("7–13 jagah bekaar ke letters") OCR ki ginti thi, jo usi **sahi** text ko gin rahi thi. Balki nuksan mera scrub kar raha tha — pakka text dhundhla kar "BLA CK HOLES" ban gaya, aur wo bacha hua text baad me naye shabdon se takraya.

Aur model perfect bhi nahi hai: 24 Oct ki files me ek par "MYSTERY" → **"KLYSTERY"** nikla, ek par "THEY LAUGHED" → **"THEY LAUGEDED"**, aur us ghalat spelling wale card ko purana score **98** de gaya tha. Local OCR se ye faaisla pakka nahi hota (wo "BLACK" ko "BLA"+"CK" tod deta hai), isliye tool is par bharosa nahi karta — **shabd Pillow se lagen to spelling 100% pakki hai**, yahi default isliye hai.

**Ab kuch bhi chup-chaap nahi bigada jaata.** Raw me text mila to **dono** cards bante hain: **"AI ka text (as-is)"** — jaisa tha waisa, na scrub na overlay, aur card par likha hota hai ke OCR ne kya padha, kitna confidence mila aur aapke kitne shabd mile (ye sab sirf ishara hai, pakka nahi — OCR "BLACK" ko "BLA" + "CK" tod deta hai, isliye poora sahi text bhi 3 me se 1 hi match karta hai) — aur **"scene + text (Pillow)"** — muft scrub karke aapke apne shabd. Kaun jeeta, ye benchmark aur aapki aankh faaisla karti hai, mera andaaza nahi.

**Scrub kaise hota hai (24 Oct ko ~15 renders apni aankh se dekh kar chuna gaya):** pehle OCR ke word-boxes **lines me jod diye** jaate hain — alag-alag shabdon par kaam karne se "E A" jaise tukde bach jaate the. Phir har line ke andar `cv2.medianBlur` se **local background** nikalta hai, usse jo alag hai (yani akshar) uska mask banta hai, chhote dhabe aur poori line ko dhakne wale dhabe gira diye jaate hain, aur mask chehron ke boxes se kaat diya jaata hai. Phir `cv2.inpaint` (TELEA) **sirf un aksharon** ki jagah bhar deta hai. Natija: flat/bare background par text poori tarah gaya (BBC wala black-hole thumbnail saaf, sher ka aasmaan saaf — sirf pehle se kaali subtitle-lines par halki chhein). Do purane tareeqe isliye haare: plain fill (2×2 resize / median / gaussian) se **rectangle ke dhabbe** bache, aur poore box par inpaint se halki **streaks** — dono maine dekhe. cv2 na ho to purana median-11 wala fallback chalta hai.

**Scrub ki had (24 Oct, naap kar):** text agar kisi **cheez ke upar** baitha hai (chalta hua portal, haath) to inpaint us jagah ki detail wapas nahi bana sakta — wahan ka hissa dhundhla ho jaata hai. "kitna bigda" ka muft number bhi try kiya (text-band ke andar kitne pixels badle) magar wo farak nahi kar paa raha: **saaf** scrub 12% aur 32% badlaav me tha, aur **bigda** scrub 31% me — number bilkul same range. Isliye koi number ghadta nahi hoon: **dono cards apne asli score ke saath** aate hain (portal wale case me as-is **93** aur scrubbed **40** aaya — tool ne khud pakad liya) aur jo jeeta wo aap chunte ho.

**Chehre ka rule:** text line agar kisi **chehre ke box par chadh rahi** hai to scrub **hoti hi nahi** — scrub chehra dhundhla kar deta hai (busy composite me face smear hua, ye bhi dekha gaya). Aise case me card saaf likhta hai ke text chheda hi nahi gaya aur kyun, aur **"bina text" ka card banaya hi nahi jaata** — wo as-is card ki nakal hoti, yaani dohra jhoot.

**Spelling ka shak (muft check — score ise chhuta nahi):** `_spell_check` aapke maange hue shabdon ko OCR ke tokens se `difflib` se taalta hai aur har shabd ko `ok` / `close` / `miss` deta hai. Sirf **close** par card par **laal "spelling shak" chip** aur ek line aati hai — kyunke iska matlab hai "koi mukammal token qareeb hai magar barabar nahi". Chaar asli files par 24 Oct ko test kiya: "MYSTERY" → **KLYSTERY** pakda gaya ✓, "THEY LAUGHED" → **LAUGEDED** pakda gaya ✓, aur poori sahi spelling ("IT IS HERE") par koi awaaz nahi uthi. Ek **jhootha alarm bhi pakda gaya:** "BLACK" ka OCR "LACK" de gaya tha (B chhoot gaya) — pehle wo bhi flag ho raha tha, ab shabd ka **prefix/suffix tukda** flag nahi hota, warna har bar shak ki awaaz uthegi. `miss` par koi token nahi dikhaya jaata (0.72 se kam ka muqabla shor hai, saboot nahi). **Score is check se nahi badalta** — score sirf bara aur padhne layak text jaanta hai; spelling ka aakhri faaisla aapki aankh karti hai, isliye ye sirf card par ishara hai.

Phir bhi default **scene AI se, shabd Pillow se** hai — kyunki Pillow wala rasta size, outline aur "320px par padha jaayega" ki guarantee deta hai, jo AI ka text nahi deta. Wohi text engine jo ⚡ use karta hai — khaali jagah dhoondta hai, outline lagata hai, aur 320px par padha jaane wala size chunta hai. Natije me spelling 100% sahi aur contrast pakka. "text bhi AI se" ka checkbox majood hai, par benchmark khud bata deta hai ke wo behtar tha ya nahi.

Prompt me detail daali jaati hai (art direction, subject, composition, lighting, rang, depth, "no text" rule) aur wohi 4 directions ek saath bheji jaati hain — taaki 4 alag soch aayein, ek hi soch ke 4 duplicate nahi. Prompt ki lambai 1400 chars par cap hai; model ne inkaar kiya to tool khud chhota karke dobara try karta hai.

**Bina-text par imandaari:** jis variant me shabd jaan-boojh kar nahi daale jaate, wahan text ke saare number zero rehte hain aur bache hue nishanon ki ginti alag dikhti hai — warna scene ki quality ke saath OCR ka shor milakar score jhoota upar chala jaata hai (ek baar to yahi wajah bani ki "bina text" sabse upar aa gaya). "bina text" tabhi banta hai jab raw me text tha hi nahi, ya text scrub karke hataya gaya ho — aur scrub wale case me uska **as-is** card saath me hi aata hai, taaki aap khud compare karo.

**Key kahan rehti hai:** `runware_key.txt` (tool ke folder me) ya env `RUNWARE_API_KEY`. UI me 🎨 tab se bhi daal/saaf ki ja sakti hai. **Key ke bina bhi tool poora chalta hai** — ⚡ ko kisi key ki zaroorat nahi, sirf *nayi* tasveer aur 4K upscale ke liye key chahiye.

**Local SD ka rasta band nahi hua:** aapke paas **RTX 5070 Ti (16 GB) + 64 GB RAM** hai, ComfyUI (`127.0.0.1:8188`) ya `models\` folder ka `.gguf` tool pehchan leta hai (🧠 tab me status dikhta hai). Par filhaal wohi rasta mehnga padta hai: apni bijli, apna waqt, 6–7 GB model — jabki yahan ek image $0.0006 me 2 second me aa jaati hai. Local SD tab jodega jab offline kaam karna ho ya ek hi scene ke sau variations chahiye hon.

## Channel Analytics + Channel Tulna — kya asli hai, kya nahi

Aapki request: *"channel ka name likhu ya link do ya channel id do to channel aye… 50 channels aye… channel kholne per complete analytics mile… har video kay analytics… tags views keywords description thumbnail… monetized hai ya nhi aur expected kitne kmata hoga kitne shorts hain kitne longs hain per video kay ki kmai… expected niche aur video kay hisab se rpm cpm… comptitor wala option: 1 channel mera aur dosra competitor, dono ka comparison… maximum channels add ka option."*

Ye wahi hai. Neeche **har dawa ke saath uska source** hai, kyunke is feature me sabse bada khatra yahi hai ke "analytics" ka shabd sun kar adhoora data poora na samajh liya jaye.

### Kaise kaam karta hai (ek line me)
1. **Naam/handle/id/link** → `ch_search` YouTube ke **Channel filter** (`sp=EgIQAg%3D%3D`) se 50 channels deta hai (naam, @handle, subscriber, verified — sab public fields).
2. `ch_resolve`: `UC…` id ho to seedha, `@handle` ho to uska exact mel, URL ho to wahi; **sirf naam** ho to tabhi apne aap channel khulta hai jab mel **ek-dana** ho (donon taraf token overlap ≥ 0.6 **aur** doosre se saaf behtar). Warna **candidate list** dikhti hai — "naam se pakka mel nahi hua, khud chun kar channel kholo". (Ye isliye zaroori hua: `tech` likhne par tool ne apne aap "Tech Burner" khol diya tha — ghalat channel.)
3. Channel khulte hi uske **asli `/videos` aur `/shorts` tabs** walk hote hain → **ginti** (kitni videos, kitni shorts) aur upload dates.
4. Phir **wahi purana naap** jo topic scan par chalta hai (download + OCR + OpenCV + listing jaanch) — **jitni aap chunte ho (25/50/100) utni sabse nayi videos par**. Naya code likha hi nahi gaya, isi liye numbers har jagah ek jaise hain.
5. Scan file `kind: "channel"` ke saath save hoti hai → wo **Competitors**, **Deep Analysis**, **Jeete topics → ideas**, **Channel Tulna** sab me usi tarah use hoti hai jaise koi topic scan.

### Jo GINTI se milta hai (asli, dobara check ho sakta hai)
- **Kul videos / kul shorts** — YouTube ke apni listing se, **400 tak** (`CH_WALK`). 400 par pahunchte hi har jagah **`400+`** likha jaata hai, "400" nahi — kyunke uske aage hum gin nahi paate.
- **Har video ke views, likes, comments, duration, upload date, category, tags, description, chapters, channel ke subscribers** — `yt-dlp -J` ke public fields, `metac/` me cache.
- **Upload ka routine**: har hafte kitni, pichhle 30/90 din me kitni, aakhri upload kitne din pehle, **kaunsa din** sabse zyada chalta hai (sirf tab jab us din ka n ≥ 4 ho — warna ye table dikhti hi nahi).
- **Nayi vs purani videos ki raftaar** (views/day, umr se normalise) — sirf tab jab **20+ longs** upload-date ke saath mili ho. Na mil line par **"nahin gin sakta"** likha aata hai, khaali nahi.
- **Hit/flop ka nisbat**: apne hi channel ke median se (2×+ = hit, 30%- = flop) — comparison kisi aur se nahi, usi channel ke andar se.
- **Channel ke andar ka pattern** (Deep Analysis): har bucket ka median views/day, lift, **Mann-Whitney p-value**, aur channel-matched lift.

### Ye paanch cheezein YouTube public data me HAI HI NAHI — isliye banawat karke nahi dikhayin jaatin
1. **Channel ka joined date** 2. **Channel ka kul views** (sirf gin-i-gayi videos ka jama mil sakta hai) 3. **Monetized hai ya nahi** 4. **RPM/CPM** 5. **Watch time**. Inki jagah jo sach me hai wo dikhta hai: subscriber **1000+** ki shart, watch-hours ki **oopar ki had** (`watch_hours_upper` — ye *se zyada nahi* ho sakti, isliye iska matlab ye nahi ke channel ko itne hours mile), aur kamai **range** me.
6. Isi tarah: **traffic source, audience ka mulk, revenue** bhi public nahi — ye kahin nahi dikhaye jaate.

### Kamai ka number kaise banta hai (aur kaise aapka asli ho jaata hai)
- Shuru me: us channel ke **niche ke RPM band** se (longs aur shorts ke alag band; band ka source har table ke neeche likha hota hai — jaise *"longs: keywords (86 hits) se niche: education/exam"*). Isliye ye **ANDAAZA** hai, isme "expected" ka matlab sirf "is band me itna hota hai" hai.
- **Aap apna YouTube Studio ka RPM daal do** (channel dashboard ke kamai card me do) → poora estimate **aapke number** se dobara gin liya jaata hai aur source likha jaata hai *"aapka apna Studio RPM (…)"*. Tab ye estimate nahi, aapka hisaab hai.
- **Range ki ahmiyat naapa hua example (24 Oct, Dhruv Rathee ka channel):** default education band me **30 din ka andaza $892,493** tha; RPM **0.34–0.46** (India, low-CPM) dene par wahi number **$68,424** ho gaya — **13 guna farq sirf RPM ke andaze se**. Isliye ek number nahi, range dikhti hai.

### Shorts vs longs — aur "poora channel analyze ho gaya" ka jhooth
- Shorts aur longs **YouTube ke alag tabs** se gine jaate hain; kisi channel ka `/shorts` tab na ho to **"0 shorts"** likha jaata hai, galti se nahi.
- **`agg` aur `deep` (pattern analysis) sirf LONGS par chalte hain** — kyunki Shorts ka distribution (views, duration, CTR) bilkul alag hota hai, unhe milakar chalane se "winning pattern" asal me Shorts ka hota. UI me ye har jagah likha hota hai.
- **Analysis sirf sabse nayi N videos par hoti hai**; baaki sirf **gini** jaati hain. Har channel dashboard par ye line saaf likhi hoti hai (scan ke andar `cov` field me bhi): *"channel me se X videos analyze hui (listing me se sabse nayi), baaki sirf gini gayi hain"*. Isliye "channel ka median" ka matlab **"analyze ki gayi videos ka median"** hai, poore channel ka nahi.

### Tulna (comparison) ka imandar hissa
- **24 maap**, har row par **jeetne wala** (trophy) — aur jo maap bade hain un par sirf *number* nahi, **dono ka n** bhi saath dikhta hai.
- **"Kaun jeet raha hai" ka faisala** sirf median ke farq se nahi: **Mann-Whitney U test** ka p-value + dono sample ka n. Chhota sample (n < 8) apne aap "kam bharose" flag hota hai.
- **Aaj ka asli example (Dhruv Rathee vs Tech Burner):** views/day ka farq **11.64×**, **p = 0.0002**, n = 15 vs 10 — yaani distribution ka farq ittefaq nahi lagta. Isi table me **subscriber** bhi 2.66× zyada hai, magar *hit rate* Tech Burner ka behtar hai (40% vs 26.7%) — ye bhi chhupaaya nahi jaata.
- **Order matter karta hai**: sabse pehle chuna hua channel "mera" hai, saari p-lines usi ke against.

### Kharcha (naapa hua)
- **50 channels ki search ~3.5 second**, channel ki **listing walk** (100 entries) ~3 second — 400 tak chand hi second.
- **Asli kharcha utni videos ka hai jitni aap "analyze" ke liye chunte ho**: topic scan ke barabar hi (**50 videos = naapa hua 42 second**; dusri baar cache ki wajah se seconds).
- Channel ki listing/search cache **24 ghante** (`chc/`) rehti hai; scan file 6 ghante.

### API (curl se bhi check ho sakta hai)
```
GET  /api/chsearch?q=<naam>&n=50      → 50 channels (name/handle/subs/verified/url)
GET  /api/chscan?q=<naam|@handle|UC…|url>&n=50
       → {job,id} (scan shuru) | {need:true,cands:[…]} (naam se mel pakka nahi) | {err:"…"}
GET  /api/progress?id=<jid>           → wahi progress jo topic scan ka hai; done par scan ban jaata hai
GET  /api/chcmp?id=<id1>,<id2>,<id3>  → 24 maap + winners + Mann-Whitney p/n + har column ka RPM source
POST /api/rpm {cid, long, short, note}→ apna Studio RPM save karke us scan ki saari kamai dobara ginta hai
```

## Niche Finder — chhote magar chalte hue channels ki dhoondh (poori gin, koi andaza nahi)

Aapki request thi: *"wo channels jo abhi chhote hain magar chal rahe hain — naye niches dhoondh kar do."* Tab wahi karta hai, aur poora kaam **naape hue numberon** par hai, model ke andaze par nahi:

1. Topic se **channel candidates** — YouTube ka apna Channel filter (`n` 6 se 50, default 18).
2. Har candidate ka **asli data**: channel ki **umar** (YouTube RSS ka joined-din), **latest 15 uploads ke views aur tareekhen** (RSS), **kul uploads** (400 tak gine), **median views**, **subscribers**. Jo YouTube ke apne feed me likha hai, wahi dikhta hai.
3. **Rank = reach = median views ÷ subscribers.** Isliye chhote channels bhi list me aa sakte hain jin ki pahunch badi hai — yehi "chhota magar chal raha hai" ka matlab hai.
4. **Do condition filters** (dropdown, default "Sab") — har flag ki shart screen par usi waqt likhi hoti hai:
   - **Naya channel boom:** channel **6 mahine (180 din) se naya**, kul uploads 100 se kam, aur subscribers ya median views **koi ek 1 lakh+**. (Pehle "naya" ki had 18 mahine thi — user ki definition ke mutabiq 6 mahine kar di gayi.)
   - **Chhota magar bara:** channel 4 saal+ purana, saal ke **12 se kam** uploads, phir bhi **3 lakh+ subscribers ya 1 lakh+ median views** — ruk kar bhi bara ho gaya channel.
5. **List me aane se pehle ke gates:** median views 10,000 se kam → bahar; 3 se kam uploads → bahar; **strict match** — topic ka koi bhi maayne wala lafz (3+ characters) channel ke naam/handle/description ya latest titles me na mile → **be-taaluq, bahar**, aur "Strict match: X channel bahar rakhe gaye" ki gin screen par; low-RPM zubaan ka andaza (naam/description ki script se) → alag flag, default filter me bahar.
6. **Har dhoondh Scan history me mehfooz hoti hai** — topic, `n`, rows aur meta: **kitne candidates check kiye vs kitne qualify hue** (donon gine, kabhi jhooth nahi). Jawab 24 ghante cache hai; uske baad dobara naapa jaata hai.

**Jo ye NAHI karti:** subscriber growth-rate, views ka trend, ya "ye niche aage chalega" ka waada — ye cheezein YouTube public data me hoti hi nahi, isliye yahan koi banawati score nahi banta. Flag sirf upar di gayi sharton par lagta hai, aur har flag apni shart khud likhta hai.

```
GET  /api/radar?q=<topic>&n=6..50   → {job,id} (naap shuru) | {rows,meta,cached:true} (24-ghante cache se)
GET  /api/progress?id=<jid>         → job ki progress; done par rows + scan ka id
GET  /api/niche?id=<scanid>         → mehfooz Niche Finder record (Scan history se wapas kholne ke liye)
```

## Competitor bank — apni chuni hui videos ka record

Kisi bhi scan ke video card ya uske **poore analysis** me **"Competitor banao"** → style/niche/note ke saath save. Sidebar ka **Competitor bank** view har record ko us din ka snapshot dikhata hai (numbers "save ke waqt ke" likhe hain), channel ki creation date aur aakhri upload ke saath; "poora analysis" seedha us scan ka wo video khol deta hai. **"Jeeton se bank bharo"** us topic scan ki jeeti hui videos (2×+ median views/day) classifier ke style-suggestion ke saath bhar deta hai.

**Imandari ka rule:** aapka chuna style/niche aapki raaye hai, numbers us scan ki asli readings — dono ka source record par likha. Style ka box khali chhod sakte ho: classifier ka andaza bhar jata hai, aur wo bhi na mile to record **bina style ke save hota hai** aur bank me saaf likha aata hai "classifier pehchaan nahi paaya — zoom me khud chun lein". (Pehle aisi video save hi nahi hoti thi — doosre laptop par "click kiya magar kuch nahi gaya" ki wajah yehi nikli.)

```
GET  /api/cmpb                                  → poori bank
POST /api/cmpbsave {vid,style,niche,note,…}     → save (style khali bhi chalega)
POST /api/cmpbdel {vid}                         → hatana
POST /api/cmpbseed?id=<scan>                    → jeeti videos se bharo
```
File `thumb_output\cmpbank.json` (hadd 500) — aapka data hai, repo ya share zip me nahi jata.

## Scan history — har dhoondh ka mehfooz record (audit trail)

Top bar ka 🕘 button. **Har scan** — topic scan, channel scan, aur Niche Finder dhoondh — `thumb_output\scans\` me ek immutable JSON record ban jata hai. History view unhi records se banti hai: kind ke hisaab se filter (Topic / Channel / Niche), kisi bhi record ka **wahi table dobara khul jata hai** jo us din bana tha (numbers wahi ke, dobara naape nahi jaate), Niche records par **checked vs qualified** ki gin, aur delete ka option. Niche dhoondh khatam hote hi uski history row **foran** dikhti hai — page reload ki zaroorat nahi. Server restart ke baad bhi purani dhoondh wapas milti hain, kyunke record disk par hai.

## Requirements

- **Python 3.10+** aur **Pillow + numpy**. Ek baar: **`setup.bat` double-click** — Python, Pillow, yt-dlp aur Tesseract install ho jayenge.
- **OpenCV (`pip install opencv-python-headless`)** — chehre aur composition isi se. Version **4.5.4+** chahiye kyunke `cv2.FaceDetectorYN` (YuNet) usi me hai. Model file `models\face_detection_yunet_2023mar.onnx` (232 KB) folder ke saath hai; na mili to tool Haar par gir jaata hai aur **har result par likhta hai ke kaunsa engine chala** (Haar 102 thumbnails par 68 chehre dhoond paaya tha, YuNet 82; 12-video ke scan me Haar ne **ek bhi** nahi dhoondha).
- **`pip install rapidocr-onnxruntime`** — OCR. Ye PP-OCRv4 hai aur Tesseract se kaafi behtar: "How to study GRAMMAR" Tesseract ne `['RA','ry']` padha, RapidOCR ne poora. Na ho to Tesseract par gir jaata hai, aur har scan/card par likha hota hai kaunsa chala.
- **`pip install scikit-learn`** — TF-IDF semantic match aur CTR par weight calibration. Na hone par wo do number khali rahenge; baaki poora tool chalega.
- `yt-dlp` na bhi ho to tool pehli baar khud download kar ke `bin\yt-dlp.exe` me rakh leta hai.
- **Scan/analysis ke liye koi API key nahi** — sab kuch public: yt-dlp search + i.ytimg.com thumbnails + RapidOCR/Tesseract + Pillow + OpenCV. Kuch bhi upload nahi hota, sab aapke PC par. **Sirf 🎨 AI thumbnail aur 4K upscale ke liye Runware key chahiye** (optional, aur usme bhi har image ki asli cost UI me dikhti hai).
- **Jo cheez jaan-boojhkar nahi lagayi gayi: saliency.** Score me "subject kahan hai" ka saliency signal dalne ki koshish ki gayi — spectral-residual saliency faces ka **7/38** aur Itti-Koch-Neumann **3/36** asli subjects ko pakad paaye (SR ka entropy 102 images par 0.975–0.999, yaani wo har jagah barabar "khaas" hai). Ye kaam nahi kar raha, isliye **saliency score aur verdicts se hata diya gaya hai**; wo sirf diagnostic (`an.sal`) dikhta hai aur us par `sal_validated: false` ka label hai.

## Chalane ka tareeqa

1. **`ClickLab.bat` double-click karo** → browser me `http://127.0.0.1:8028` khul jayega.
2. **🔎 Competitors** me topic daalo, **50** chuno, "search chaudo" + "asli tags + description" tick karo. Pehli baar **~1 minute** (50 videos ka naapa hua waqt: 42 second — download + OCR, 8 threads); tags/description ka extra ~0.45s/video. **Dusri baar seconds** — sab cache ho jata hai.
3. **📊 Deep Analysis** kholo → kaunsa pattern copy karna hai aur kaunse numbers beat karne hain (benchmark table). Tags/description/chapters ke buckets bhi yahi hain.
4. **🏆 Jeete topics → ideas** kholo → **10 suggestions**: topic, uske titles, us channel ke **asli tags**, keywords, aur har idea par **"is topic par thumbnail banao"**. Har suggestion ke andar likha hota hai wo kis jeetne wale video se aaya aur uska views/day kitna hai. Bani tasveer pasand na aaye to **"dobara banao"**.
5. Kisi bhi competitor card par **"iska poora analysis"** → uski **asli listing** (tags, description, chapters, listing score, title score). Kisi chip par click → Title Lab me wo tag daal do.
6. **🖼 Meri Thumbnail** me apni thumbnail daalo → percentile usi scan ke videos me. Apna Studio ka asli CTR/retention daalo to wahi asli nazar aayega.
7. Pasand na aaye to **⚡ Behtar banao** (muft, wohi photo) ya **"Is se inspire ho kar naya"** → 🎨 (nayi tasveer, $0.0006–0.0012/image at 1024). Dono ke natije wahi benchmark napte hain — jo jeete uska "iska poora analysis" se dobara check karo, phir 4K button.
8. **✍️ Title Lab** me title likho → "Preview banao" → **🅰️ A/B me save karo**.
9. Upload ke baad 24–48 ghante me dekho kaunsa click kha raha hai — phir **Studio ki CSV nikal kar 📈 tab me paste karo** (ek baar me poora channel), aur **"wazan fit karo"** dabao. Uske baad tool ka har score aapke asli CTR par bana hoga, mere andaze par nahi. Kam se kam 8 video chahiye, 30+ par ye sach me kaam ki cheez hai.

## Topbar: poora scan CSV/JSON me, aur asli Back

- **CSV / JSON** button har scan ka poora data nikaal deta hai (`/api/export?id=<scan>&fmt=csv|json`) — views/day, listing score, tags ki ginti, aur thumbnail ke **saare** naap ek row me. Excel/Sheets me khol kar khud chalane ke liye; file ka naam `clicklab_<scan>.csv`.
- **← (Peeche)** button aur browser ka Back **dono** chalte hain. Har tab ka apna address hai: `#/ideas/<scan>`, `#/deep/<scan>`, `#/mine/<scan>`, `#/cmp/<scan>`. Matlab kisi bhi view ka **seedha link** copy karke bheja ja sakta hai, aur refresh par wahi view khulta hai.
- Topbar ka chip ab **napay hue** videos dikhata hai (jaise **46**), maangi hui 50 nahi. Chip par mouse le jao to poora hisaab likha hota hai: *50 maange the; filter karke 46 bache (shorts hataaye, ek channel se zayada nahi, duplicate hataaye)*. Jo number UI me dikhta hai wahi engine me chalta hai — dono alag nahi ho sakte.
- Har response par `Cache-Control: no-store` bheja jata hai. Ye tool restart hota rehta hai aur poori app ek hi page me hai — bina iske browser purana page pakad kar baithta tha aur naya code dikhta hi nahi.

## UI ka look — YouTube Studio jaisa Content table

Aapki shart thi: *"analysis ka look YouTube Studio jaisa dikhna chahiye, saari videos ki; comparison me bhi wahi style; aur har button par click ka ehsaas — tool jaisa."* Jo bana:

**Content table — har channel ki saari videos.** Channel Analytics kholo to ab wahi Studio ka layout hai:

- **Pehla column:** thumbnail (140px) + us par **duration ka badge**, shorts par **SHORT** ka chip; neeche title (2 lines) aur uske neeche `channel · category`.
- **Baaki columns right-aligned tabular numbers** (Studio jaise): Views ke neeche **views/day**, Likes/Comments ka **%**, Date ke neeche **kitne din purani**, Lambai, aur Listing + Thumbnail **chhoti bar ke saath**.
- **Har column header par click = sort** (chhota caret direction batata hai). **Filter row:** `Sab / Longs / Shorts` ka segmented control, **date window** (7 / 30 / 90 / 365 din), aur **title + tags ki search**. Upar ginti likhi hoti hai: `11 / 40 dikh rahi hain`.
- **Row par click → detail usi jagah khulti hai** (nayi tab nahi): thumbnail par OCR aur chehre ke boxes **asli coordinates** se, 11 KPI, saare tags, description ka tukra, YouTube ka link, aur "poora analysis" ka button.
- **Neeche wo line jo sach bolti hai:** naap sirf **latest N** videos par hua hai (channel me 400+ videos ho sakti hain) — table ye chhupata nahi, ye likhta hai.

**Channel Tulna bhi usi table me**, ab teen hisson me:

| Tab | Kya dikhta hai |
|---|---|
| **Maap (24 rows)** | Dono channels side-by-side, har row par jeetne wala cell halka blue + trophy, bar normalized (jeeta neela, haara grey) |
| **Kaun jeeta** | views/day ke medians, dono ka **n**, farq ka bar aur **Mann-Whitney p-value** — hara = p<0.05, peela = kamzor saboot |
| **Kamai** | RPM range + 30-din ka **andaza**, aur ye line saath me: YouTube kisi aur channel ka RPM/watch-time public nahi karta |

**Design system.** Range **ek hi `:root` token block** me hai (Studio ka palette: `--bg #0f0f0f`, `--panel #212121`, `--acc #3ea6ff`, `--ok/--warn/--bad`) — page me koi ad-hoc colour nahi likha. UI me **koi emoji nahi**: saare icons ek chhote SVG path map se aate hain (`ico(name,size)`), headings sentence-case, scrollbars bhi theme ke. **Har clickable cheez** par (buttons, sort headers, rows, channel pills, tabs) hover + `:active{transform:scale(.97)}` + keyboard ke liye `:focus-visible` outline hai — "tool jaisa" ehsaas isi se aata hai.

**Naapa hua, maana hua nahi:** 1333px par bhi `scrollWidth == clientWidth` (table container se bahar nahi chhapta), aur **405px par bhi wahi** — wahan table apne andar horizontally scroll hota hai, page nahi. Console me **0 errors / 0 warnings**. Table ka header **sticky** hai (`top:57px`, topbar ke theek neeche) — 40 rows scroll karo to columns yaad rehti hain; 900px se neeche sticky jaan boojh kar band kar diya jata hai, chhoti screen par wo nuqsaan hota hai.


## Badlav ka record (changelog)

Har round ka record yahin likha jaye, naya upar. Har entry me teen cheezein lazmi: kya badla, kyun (wo cheez pehle kya galat kar rahi thi), aur browser me kya naapa gaya. Jo number yahan likhe hain wo usi waqt ke hain — screen par jo dikhega wo aapke apne data se banega.

### Trending — ab category aur niche ke saath: "is mulk me, is niche me kya trending hai"

**1. Kya naya hai:** Trending card me do naye control: **category ka select** (YouTube ki apni 23 category list — `videoCategoryId` parameter, seedha API ko jaata hai) aur **niche ka lafz** (optional). Category filter **official hai** — "America me Music ka chart" API ka apna sawal hai, hamari filtering nahi. Niche ka lafz **chart ke andar** lagta hai: title / YouTube ke official topic tag / channel ke naam me lafz mile (strict, koi fuzzy milan nahi) tabhi video rehti hai. Gin screen par: `chart_se_aaye` vs `niche_match`. Scan ka topic label ab poora sach likhta hai: `TRENDING Pakistan · Sports · niche: cricket — YouTube ka apna chart`. Niche/category browser me yaad rehte hain. API: `/api/trend?region=&n=&cat=&kw=`; scan file me `trend:{cat,catname,kw,chart_n,match_n}`.
**2. Kyun zaroori tha:** pehle Trending sirf **poore mulk ka overall** chart tha — user ki maang thi "is country me is niche me kya trending hai". Overall chart har cheez ka mixture hota hai; niche ka sawal usme se dab jaata tha.
**3. Browser/API me naapa (sab asli calls):** `cat=17` (Sports, PK) → **10/10** videos sports chart se, `trend.cat=17 catname=Sports` file me likha. `kw=cricket` poore PK chart par → **0/25 match** — tool ne jhoot nahi bola, saaf error di: *"is chart me 25 videos thin — kisi me cricket ke lafz nahi mile… aapka niche abhi is mulk ke official chart me nahi hai"* — ye **natija** hai, khami nahi. `US · Music · kw=song` → **25/25** match (music chart me song hi hain — ginti sahi kaam kar rahi hai, dono taraf se). UI se live chala: "Sports · niche: cricket" PK → chart me se **1** video mili aur result usi label ke saath khula. Quota: category filter ke bawajood ek trend scan = **1 unit** (keyword filter local hai, 0 units).

### Channel History — 24 ghante / hafta / mahine ke window deltas (real-time subscribers aur watch time ka jugaad, poora asli)

**1. Kya naya hai:** Channel History view me naya section: **"Last 24 hours · 7 days · 30 days — the channel against itself"**. Har column ka **baseline** (window ke start se pehle ki aakhri apni reading) aur uska **asli span** header me likha hai. Rows: **subscribers Δ** (latest reading minus baseline), **uploads Δ**, **views gained** (sirf dono readings me matched videos — wahi `_pair` rule), aur **watch time**. API me naya: `/api/hist` response me `windows[]` (`base`, `gap`, `d_subs`, `d_up`, `d_views`, `wt_min`…).
**2. Kyun zaroori tha:** user ne "real-time subscribers aur watch time (24h/week/month)" maanga. YouTube public API subscribers ka **past nahi** deta — to asli jugaad yahi hai: **apni snapshots ka farak** (jo tool khud mehta hai). Watch time to YouTube **sirf channel ke malik ko** (Studio) deta hai — kisi bhi doosre channel ka public watch time **hoti hi nahi**, isliye wo sirf **apne** channel ke liye aur sirf **asli hisson se** gin'ta hai: `views gained × Studio retention (own.json) × naapi hui duration`. Inputs sab asli; product isliye **"estimate from real inputs"** label ke saath dikhta hai, exact Studio report ka dawa nahi.
**3. Imaandari ke niyam (screen par likhe hain):** baseline na mile to cell **khaali (—)**, **0 nahi** — do readings ke bina farak hota hi nahi. Views jinke `vm` same thin ya `meas` me nahi → **"not re-measured"** (0 jhoot). Subscriber Δ YouTube ki **rounded** public ginti se hai (e.g. "1.23M") — chhota asli farak dikhega hi nahi, ye YouTube ki hadd hai, chupi nahi. Watch time jinka Studio retention import nahi → **"— no Studio data"**, koi guess nahi.
**4. Naapa gaya (Think School, 10 snapshots):** aaj nayi snapshot li → 24-ghante wale column me **baseline 2026-10-28** aur **actual span 2.73 din** header me sahi chapa; **subscribers Δ +10,000** (do asli readings ka farak), **uploads Δ 0**, views **"not re-measured"** (kyunki un views ko dobara padha hi nahi gaya), watch time **"— no Studio data"**. 7-din/mahine ke columns **"no reading that far back"** — kyunke usse purani koi apni reading hai hi nahi. Table poora honest; koi number banawat ka nahi.

### Niche Finder — poori dhoondh, phir strict, aur "naya channel" ki umar 6 mahine

**1. Kya naya hai:** Niche Finder tab: topic se 6–50 channels ki dhoondh, har channel ki **asli gin** (RSS se umar + latest 15 uploads ke views, listing se kul uploads aur median views), **rank = reach** (median ÷ subs), do condition filters (*naya channel boom*, *chhota magar bara*), aur har dhoondh ka record Scan history me. Uske baad ki maang par do sakhtiyan: **(a)** "naya channel" ki umar 18 mahine se ghata kar **6 mahine (180 din)** kar di — user ki definition yahi thi ("5–6 mahine hue hue"); **(b)** **strict match** — topic ka koi bhi maayne wala lafz naam/handle/description ya titles me na mile to channel dhoondh se bahar, aur "Strict match: X channel bahar rakhe gaye" ki gin UI me. Pehle ke cached jawab (strict lagne se pehle naape gaye) kabhi serve na hon, isliye cache key `rad_` se `rad2_` kar di — matlab kisi topic ki pehli dhoondh 2–3 minute phir lagegi.

**2. Kyun zaroori tha (pehle kya galat tha):** "minecraft parkour" jaisi dhoondh me bhi be-taaluq channels aa rahe the (sirf subscribers bade the), aur 18-mahine-purane channels "naya" keh kar list me aa rahe the jabke user ne 5–6 mahine ke naye channels maange the.

**3. Browser me naapa:** "quantum beekeeping" n=6 → 6 check, **1 strict-bahar, 1 qualify** — gin screen par sahi; "retro synthwave radio" → Japanese channel zubaan-filter se bahar, aur record **foran** Scan history me (bina reload). Zero console errors.

### Competitor bank — ek click me save ("style chuno" ki rukawat hatayi)

**1. Kya:** "Competitor banao" ab hamesha save karta hai — style ka box classifier ka andaza bhar leta hai, aur wo bhi na mile to record bina style ke save hota hai; bank view me honest note: "classifier pehchaan nahi paaya — zoom me khud chun lein". **2. Kyun:** doosre laptop par user ne click kiya magar kuch save nahi hua — classifier us video ka style na pehchaan paaya tha aur form "style chuno" par sakht block kar raha tha, jo user ki nazar mein "kuch nahi hua" lagta tha. **3. Naapa:** khaali-style record save hua → bank me honest note ke saath dikha → delete bhi theek; bank count 4→5→4.

### Niche dhoondh ka result foran screen par (polling ab network-glitch bardaasht)

**1. Kya:** dhoondh khatam hote hi table aur Scan history row foran. **2. Kyun:** progress-poll ka loop **ek** network glitch par mar jata tha, jabke server scan pura karke history me likh chuka hota tha — isliye result sirf history me milta, screen par nahi ("search khtm hotay hi result udhr nhi dikhta"). Ab loop 10 lagataar glitches bardaasht karta hai, aur job kho jane par bhi (server restart) `/api/radar` dobara maar kar mehfooz (cache) jawab khud khol leta hai. **3. Naapa:** live search → table + history row foran; zero console errors.

### Channel History — waqt ke saath sirf apni hi readings

**1. Kya naya hai:** **Channel History** tab. Channel ki wo saari readings jo **is tool ne khud li thin**, waqt ke saath — snapshot ki list, unke beech ka farq, aur uska chart. Source sirf app ka apna store hai: `thumb_output/hist/<channel id>.json` (channel id se banti file, kyunke same channel do topic/channel scans me aa sakta hai), hadd **60 snapshots**. Scan chalte hi ek snapshot banta hai (`manual`), aur jo channels is feature se pehle khule the unke liye pehli baar kholne par ek **back-fill** snapshot (`backfill`) — wo bhi tab tak dohrata nahi jab tak file me pehle se maujood ho. API bhi curl se check ho sakti hai: `/api/hist?id=…`, `&take=1` (ek snapshot lelo), `&refresh=K` (**K videos ke views sach me dobara padho**).

**2. Kyun zaroori tha (pehle kya galat tha):** pehle har channel ki **ek hi scan file** hoti thi aur dobara scan karne par purane numbers **overwrite** ho jaate the. Matlab "badlav" ka koi record hi nahi tha — screen par jo bhi growth dikhti, wo ek hi pal ke number se nahi nikaal sakti thi. Aur sabse khatarnak galati wo hoti jab "views nahi badhe" ka matlab ye nikaalta ke **views dobara padhe hi nahi gaye the**: number ka `0` aur "naapa hi nahi gaya" ek jaise dikh rahe the.

**3. Imaandari ke jo niyam screen par likhe hain (ye is feature ki hadd hain, aur iski taqat bhi):**
- **Har snapshot ke saath `meas` likha jaata hai** — usne kaunse per-video metrics us din dobara padhe. Jis metric ko us din nahi padha gaya, uska diff **gana hi nahi jaata**: UI me **`—`** aata hai, **0 nahi**. Isi liye refresh waale snapshot me **likes/comments ke columns `—` hain** — unhe dobara padha hi nahi gaya tha, sirf views padhe gaye.
- **Match hisaab sirf unhi videos par** jo dono readings me maujood thin (is test me **211 videos matched**), plus "nayi"/"hatai gayi" ki alag ginti. Jinki `vm` (thumbnail ke naap) same thin, un par saaf likha hai **"not re-measured"**.
- **Do readings ka gap aadha din se kam ho to per-day rate `—`** dikhta hai, tooltip me wajah: itne chhote waqt ka daily rate shor hai, signal nahi.
- Ratio ke bars **log paimana** par (1.00x beech me), aur har bar/cell ke tooltip me **dono exact numbers**.
- Purani history files (jin me `meas` nahi tha) load par migrate ho jaati hain — unka sirf wahi hisaab hota hai jo unme sach me record hai.

**4. Browser me naapa gaya (CarryMinati ka channel, 211 videos):** teen snapshots — `backfill`, `manual`, `refresh` — jinka gap **14 minute** tha. **211 videos dono readings me matched**, aur match set ka views total **31,780,858 → 31,835,034 = 1.0020×** (dono number tooltip me; caption me yehi likha hai ke "views ke alawa kuch dobara nahi padha gaya"). **Likes ka column `—`**, **per-day cell `—` + tooltip**, flat charts par **"nothing changed between these snapshots — the numbers were not fetched again"**. Channel ki kul views ka axis **4.47B** tak print karta hai. Poore app ke **13 routes** render hue, **page ka kinara 1338 = window ki chourai** (koi table overflow nahi), aur **0 console errors**.

**5. Hadd (chhupi nahi hui):** YouTube ke paas history ka data nahi hota — **jitni readings aap khud loge, utni hi series banegi**. Pehli baar kholne par sirf ek back-fill snapshot milega; us din graph ka koi past nahi hoga, aur screen par wahi likha hoga. Refresh ka kharcha isliye alag se dikhaaya jaata hai (approx **1 second per video**, naapa hua) kyunke views ka purana meta-cache stale hota hai — is liye refresh `enrich` ke asli raste se jaata hai, cache se nahi.



### premium visual pass: ek hi token source, aur ratio ka sahi chart

**1. Andha polish nahi — pehle naap liya.** Ek script ne gin kar bataya ke system kahan toot raha hai. **Pehle:** 27 tokens, 289 `var()` istemaal, magar `:root` ke **bahar 21 hex rang aur 19 kachche rgb**; **22 alag font sizes** (12.2 / 12.5 / 12.6 / 12.8 / 13.2 / 13.5 / 11.5 …); **20 alag kaakr** (2/3/4/5/6/8/9/10/12/99/999px); 5 alag saaye; palette me ek bhi nahi tha magar `::selection` ka teal, `.yt` ka neela surface `#0f1420`, aur paanch man-girri grey (`#4a4a4a`, `#5c5c5c`, `#5a5a5a`, `#3f3f3f`) idhar udhar likhi thin. Yehi wo nishaniyan hain jin se UI "banta hua" nahi "jama kiya hua" lagta.

**2. Ab:** **54 tokens** (semantic naam: `--fs-label`, `--fs-dense`, `--edge2`, `--scrim-chip`, `--sh2u`, `--rp`…), **459 `var()` istemaal, 0 undefined, 0 bekaar (unused) token, `:root` ke bahar 0 hex aur 0 kachcha rgb** (jo alpha tints hain wo `rgba(var(--okrgb),.3)` jaise token se bante hain), aur **0 font-size scale ke bahar**. Range ka scale: `--r0 4 · --r1 6 · --r2 10 · --r3 15 · --rp 999`. Unchai ka scale: `--sh1 --sh2 --sh2u --sh3`. **Rang badle nahi** (YouTube Studio ka hi palette hai — wahi maang thi), badla sirf itna hai ke ab wo **ek jagah se** aate hain.

**3. Naya gate: `_tok.py` ab har round chalta hai.** Ye chaaron cheezein pakarta hai: paribhasha ke bina `var()`, **circular token definition**, bekaar token, aur hard-coded rang / font-size. Is gate ne **apne hi patch ka banaya hua bug pakda**: mere replacement ne token ki apni paribhasha bhi badal di thi — `--scrim-chip:var(--scrim-chip)` — jisse thumbnails par date/duration ke chips khali (transparent) ho gaye the. Browser me `getComputedStyle` ne "missing token" dikhaya, audit ne wajah bata di. Ab aisi galti chup nahi sakti.

**4. Ratio ke liye sahi chart (aur ek jhooth jo pakda gaya).** Outliers aur Engagement ke "median se / apni size ke ghere se" columns ab **diverging bar** dikhate hain: **beech ki rekha = 1.00x** (apne ghere ke barabar), dayen = zyada, bayen = kam. Pehla version **linear** tha aur jhooth bol raha tha: **4.96x aur 25.86x ki bar bilkul ek jaisi bhar gayi** (sab 3x par saturate). Ab **tauzani (log) paimana** hai, hadd 30x — kyunke ratio ki duniya me 2x aur 0.5x barabar hain, aur 4x aur 25x alag hone chahiye. Naap (browser me, har bar ka fill): **25.86x → 47.8%**, **8.03x → 30.6%**, **6.41x → 27.3%**, **4.96x → 23.5%**, **0.51x → 9.9% bayen taraf**. Har bar par **tooltip asli number** deta hai, aur screen par likha hai ke beech ki rekha kya hai aur lambai log paimana par hai.

**5. Browser me jaanch (do views):** Deep Analysis aur Channel Analytics dono par — **0 console errors**, **0 unresolved `var()`**, page ka kinara **1327 < 1338** (koi table overflow nahi), Channel Analytics ke **274 heatmap cells, 5 tables, 4 KPIs, 0 baghair `scope` ke header** sab salamat. Screenshot se dekh kar confirm kiya ke cards, chips aur table theek dikh rahe hain.


### Engagement: har 1000 views par kitne likes

**1. Kya naya hai:** Deep Analysis me **Engagement** ka section. Ye YouTube ki **asli liked-count** se banta hai (jo har video ki metadata ke saath already aa chuki thi — koi naya network kharcha nahi). Batata hai ke jis ne video dekhi, us ne kitni talqeen zahir ki: **median likes per 1000 views**, aur **p25–p75 ka band** (taaki ek number ke peeche na bhag jaao).

**2. Is channel par kya nikla (CarryMinati, 203 videos):** median **66.0 likes / 1000 views**, aur **aadhi videos 56.5 – 76.6 ke band** me — yaani channel ka "talqeen ka level" kaafi ek jaisa hai. Sabse oopar: **EK AURAT 141.1** (apni size ke ghere ke **2.38×**), **THE ART OF BAD WORDS 125.8** (49.7M views par 6.3M likes). Sabse neeche: **HOT BIKINI SEX 28.2 (0.42×)**, **India's Adult Film of the Year! 30.3**. **202 videos par comments bhi naap paye** — wo bhi saath dikhta hai.

**3. Sabse ahem sabaq — apna hi pehla version dhoka de raha tha.** Pehle version me **paanchon** traits "positive" nikli thin (roshni +4.4, bheed +7.9, title ke shabd +6.8, description ki lambai +8.8, tags +3.1 — sab ek hi taraf). Ye shak ki baat thi, is liye size ka asar nikaala: ab **har video ka engagement usi size ki videos ke median se** napa jata hai (listing ke views par char barabar hisse — wahi tareeqa jo Outliers me kaam kar chuka hai). Natija: **roshni +3%, bheed +2%, title ke shabd +4%, description ki lambai +6%, tags ka to sign hi palat kar −1%**. Yaani "ujla thumbnail / lamba description = zyada likes" ka jo ehsaas tha, wo **zyada tar video ke size ka asar tha**, thumbnail ki khaas baat nahi. Yehi wo jagah hai jahan "deep" analysis asli kaam aati hai: pehla hisaab seedha aur fast tha, magar galat direction ki salah de raha tha.

**4. Imaandari ki haddin (screen par likhi hui):** ye **CTR nahi hai** — CTR sirf aapke apne Studio me hota hai (wo "Apna CTR" form se aata hai). Ye naap uske *baad* ka hai. **5,000 se kam views wali videos upar ki do list me nahi** hotin (300 views par 15 likes = 50/1000, jo shor hai signal nahi) — is channel par aisi **koi video nikli hi nahi**, aur screen par wahi likha hai bajaye iske ke chup kara diya jaye. **Dislikes aur share** YouTube API se nahi aate, is liye shamil nahi. Aur batwar wali table **ham-raftari hai, wajah nahi**.

**5. Apni hi screen ki pakdi gayi nakaarein (do):** (i) ek line khud-apni contradict kar rahi thi — *"5K se kam views wali videos shamil nahi: 0"*. Ab wo soorat-alag likhti hai: koi video bahar hui hi nahi to ye saaf kaha jata hai. (ii) Table ka column heading "apne median se" tha jabke hisaab ab size ke ghere ka lag raha tha — heading ab **"apni size ke ghere se"** kehti hai, wahi jo code karta hai.

**6. Raftaar aur chourai ka nap (browser me):** is section ne pehle version me **page ko 1443px tak phaila diya** (window 1338px) kyunke char-column wali do tables adhi-chourai me rakhi thin. Poore-chourai wale pattern (jo Outliers me pehle se hai) par laane ke baad: **tables 1032px, page ka kinara 1327 < 1338, koi element overflow nahi, 0 console errors**. Section khulne par koi extra network call nahi — sab data already cached scan me hai.


### outliers (apni umr ke median se) aur poore channel ke keywords

Aapki shart thi: *"ye vidiq aur youtube studio ka mixture tool hai, har wo feature dalo jo in dono me hota — deep, very very deep"* aur *"us video par click karne se keywords nahi dikhte, wo bhi dikhne chahiye — real, no guess"*. Dono **Deep Analysis** ke andar aa gaye hain, aur koi naya data source nahi joda gaya — jo cheez pehle se aapki videos ki metadata me mojood hai, bas wahi gina jata hai.

**1. Outliers — har video apni hi umr ke ghere se nap-ti hai.** Pehla version poore channel ke median se napa karta tha; browser me napa to natija galat nikla — **203 me se 191 videos "2 saal se zyada" wale ek hi ghere me** aa rahi thin, matlab muqabla phir bhi wahi ek median se ho raha tha. Ab ghere **channel ki apni listing ke char barabar hisse** (umr ke hisaab se) bante hain. Isi channel par nap kar dekha: `0–2389 din — 51 videos · 2390–3532 din — 51 · 3533–3769 din — 51 · 3770+ din — 50`. Har ghere ka apna median alag hai (teen nap kar dekhe: **26.5K / 7.1K / 1.1K views/day**) aur **har row ke saamne likha hai ke kaunsa median lagaya gaya** — koi calculation chhupi nahi hui.

Ye badlav sirf behtar wording nahi tha, **natija badal gaya** — aur yehi maqsad tha: "3× se upar" dikhai dene wali videos **54 se ghat kar 15** reh gayin, aur beech ki patti (0.8–1.25×) **25 se 57** ho gayi. Yaani zyadatar videos apne hi ghere ke aas-paas hain (jo sach hai), aur sirf **39** videos 2× se upar hain — pehle **74** dikhati thin, wo umr ka dhoka tha.

**2. Keywords aur tags — jo channel ne khud lagaya, aur jo us ne title me likha.** Har video ke **asli tags** (YouTube ki apni metadata, jo Table mode me har row ke liye padhi jati hai) ko **asli titles** se mila kar: channel ke sabse common tags (is scan me **1,045 alag tags**, median **11 tags per video**), har tag **kitni videos me** hai aur **kitni bar title me bhi likha hai**, description ke shuru ke 260 akhar se **hashtags**, titles ke sabse common shabd (common/be-matlab shabd hata kar), aur sabse kaam ki line — **jin tags ko 3 ya zyada videos ne lagaya magar wo title me kahin nahi likha**: wo chhuta hua keyword hai jo thumbnail par bhi dikhna chahiye. Isi scan par nap: **203 videos me tags mile, 16 par ek bhi tag nahi, aur 100 videos me ek bhi tag title me nahi likha.** Yahan **koi generate kiya hua keyword nahi** — jo dikhta hai wo ya to channel ka apna tag hai ya uske title ka shabd.

**3. Imandari ki had (screen par likhi hui, meri zubaani nahi).** "2× upar" ka matlab ye nahi ke algorithm ne video ko push kiya — topic, trending ya playlist ka asar ho sakta hai; matlab sirf itna hai ke **apne hi ghere me ye video normal se kitna hat kar hai**. 30 din se nayi videos alag flag hoti hain (un ka views/day abhi poora nahi betha). Jis channel ke paas 5 se kam naapi gayi videos hain wo is hisse se **bahar** rehta hai, aur kitne bahar rahe ye bhi screen par nikalta hai. Aur ghere khud-b-khud bante hain — is liye koi "2 saal" jaisi man-mani had code me nahi rakhi gayi.

**4. Kaise bana (technical):** sab **client-side** hai, `d.items` par — jo asli tags/description already har row ke liye la chuka hai, is liye **server me naya endpoint nahi aur na koi extra yt-dlp call**; feature kholne par koi network kharcha nahi hota. Code `dxOut()` (outliers) aur `dxKeys()` (keywords) Deep Analysis ke andar do naye sections ke roop me judte hain; outlier row par click us video ka poora record kholta hai. Browser me verify kiya: **0 console errors**, page ka kinara nahi phaila (1327 < 1338), aur numbers upar wale hi screen par nazar aaye.

**5. Cards mode ab page by page chalta hai (Table mode jaisa hi).** Pehle saare cards ek saath bante the. Nap kar dekha: **211 cards ek saath = 821 KB ka DOM aur 28 ms**; ab ek page par **24 cards = 98 KB aur 9 ms**, aur 211 ki jagah 24 hi images lazy load hoti hain. Index **absolute** rakhe jaate hain — page 2 ka pehla card `zoom(24)` se khulta hai (browser me verify: `zoom(24)…zoom(47)`, aakhri page par `zoom(192)…zoom(210)` = 19 cards) — is liye "poora analysis" hamesha sahi video kholta hai. Page badalne par nazar apne aap section ke upar chali jaati hai, aur aakhri page par "Agla" button disabled hota hai. Chaahne par **"saare cards ek saath"** bhi hai — aur us soorat me screen par saaf likha jata hai ke ye aap ne chuna hai aur page bhaari ho sakta hai (jhooth nahi likha jata ke "scan chhota hai").

**6. Screen reader ke liye har column ka naam.** **129 `<th>`** par `scope="col"` jod diya gaya (jin ke pahle se tha unhe chheda hi nahi). Ab screen reader cell par pohanch kar batata hai ke ye number kis column ka hai. Verify: Deep Analysis ke **117** aur Channel Analytics ke **26** header — sab par scope, **zero bache**.

**7. Apni hi screen ki nakaar — do baar.** (i) Outliers ke do KPI hamesha **zero** dikha rahe the ("channel ke median se nape = 0", "5 se kam videos wale channels = 0") — beshumar cheez dikhane se behtar hai kuch na dikhana. Unki jagah wahi haddin hain jo neeche ke batwar me nazar aati hain, taaki KPI aur table ek dusre se mel khayen: **2× se upar = 39, 1.25× se upar = 73, apne ghere ke barabar (0.8–1.25×) = 57, aadhe se bhi kam = 36, ghere = 4** (table ke columns se inka jod milta hai: 15+24+34 = 73). (ii) Heading me likha tha *"USI channel ke median se"* jabke hisaab ab usi umr ke ghere ka lag raha tha — heading ab wahi likhti hai jo code karta hai: *"usi channel ki **usi umr ki** videos ke median views/day se"*. Isi tarah "us umr (umr 0–2389 din)" lafz dohra raha tha; ab row par likha hai **"us ghere ka median (0–2389 din)"**.


### raftaar, poori channel ki listing, aur chhapne ka waqt

Aapki baat thi: *"pora tool ko smooth banao, shuru se dair sekhulta hai"*, *"sari videos ka data Studio jesa dikhao ya page by page"*, *"poori description aur keywords bhi, real no guess"*, *"kis time video upload karta hai aur weekly kitni"*. Neeche jo likha hai wo **napa hua** hai, socha hua nahi.

**1. Shuruat ki der khatam — 3.64 second se 0.55 second.** Pehle server chalu hote hi OpenCV, Paddle aur baaki bhaari engines load hote the, jabki aadhe tabs par unki zaroorat hi nahi hoti. Ab wo sab lazy hain: `load_sk()`, `load_ocr()`, `warm_all()` tab tak nahi chalte jab tak koi kaam unhe na mange, aur `start_warm()` unhe background me garam karta hai jab tak aap scan khol rahe hote ho. Nap ka natija (isi machine par): thandi shuruat **3.64s → 1.56s → 0.55s**, pehla API jawab **0.02s**, aur warm halat me `/` **0.001s**, `/api/chwalk` **0.031s**, `/api/data` **0.031s** (211 videos ka 1.3 MB JSON). Tab reload par page khulne me ab der nahi hoti.

**2. "Sari videos" ka masla hal — ya to ek button, ya page by page.** Pehle Channel Analytics me 400 tak gini hui videos dikhti thin lekin data sirf 6 ka, aur har row par `nap chao` likha tha jo wahi chand videos wapas khol deta tha. Ab do raaste hain: **`aur 100 videos laao`** ka ek bulk button (`/api/chmore` → `extend_chan`) jo poore channel ki listing koETA ke saath barhata jata hai, aur **Table (Studio)** mode jisme poori listing **25-25 pages** me khulti hai (`Pichhi / Agli`, `25 har page` badla ja sakta hai). Har bar ye line chhap ti hai ke kitni videos gini gayi aur kitna hissa naapa gaya — chupi hui ginti nahi.

**3. Poori description aur asli keywords.** Row kholne par ab `/api/meta` se us video ki **apni** metadata aati hai: description bina kaate, poore tags/keywords ki list, category, `subtitles N bhashayein`, aur upload ki tareekh ka chip. Ye sab **asli metadata** hai — koi andaza nahi. Jo cheez andaze par hai (wazan, score) wo alag se `heuristic` likha jata hai.

**4. Upload timing — din aur ghari ka naqsha (168 cell).** Table mode ke upar `Kab upload karta hai` ka panel hai: har din × har ghari ka cell, jitni zyada uploads utni gehrai, cell par **click = us din/ghari ki videos** (dobara click = filter khatam), aur upar chhe KPI: sabse zyada jis din, sabse common ghari, har hafte aurat, aakhri upload, sabse lamba gap, lagatar hafte. Neeche **`Hafte me kitni upload`** ke bars pichhle 26 hafte ke. Is channel par napa hua sach: **Shukr (32)** sabse zyada, **17:00-18:00** sabse common ghari, **0.37 uploads/hafte**, aakhri upload **41 din pehle**, sabse lamba gap **287 din**.

**5. Ghari ka data andaze se nahi — asli `timestamp` se.** YouTube ki listing (`/videos`, `UU`) me `timestamp` kabhi nahi aata (25 Oct ko test kiya); wo sirf har video ki apni metadata me hota hai. Is liye `meta_of` ab `ts` store karta hai aur har item par `pubts` (ghari tak ka poora waqt) jata hai. Purane scans ke liye **`baqi N videos ka waqt laao`** ka button hai (`/api/tback`) jo sirf metadata dobara padhta hai — thumbnail, OCR aur naap dobara nahi chalte. **Napa hua kharch: 211 videos ka back-fill 161 second** (3 workers). Natija: **203/211 videos ka asli chhapne ka waqt mila** (194 long me se 186); **8** aisi videos hain jin ki metadata me hi timestamp nahi — panel ye ginti khud chhap ta hai, chhupata nahi. Shorts naqsha se bahar rakhe hain kyunke un ki ghari ka matlab alag hota hai; hafte aur gap ki ginti un par bhi hoti hai.

**6. Table aur filter ab ek saath chalte hain.** Din/ghari ka filter lagane par rows, ginti (`6 / 211 dikh rahi hain`), pagination aur `khaali ho to sabab` sab usi filter ke hisaab se update hote hain. Jo rows abhi naapi nahi gin un par time filter lagta hi nahi, aur ye baat likhi jati hai.

**7. Keyboard aur screen reader.** Naqsha ke cell asli `<button>` hain: `Tab` se ghoomte hain, `Enter` se filter lagta hai (aaj test karke dekha), har cell par `aria-label="Itvaar 19:00 — 6 videos"` aur `aria-pressed`. Hafte ke bars par `role="img"` ka nichod hai. Poore page par **console 0 errors**, aur 1338px par bhi page chaora nahi hota (`scrollWidth 1327`).

**Data model ka record:** `meta/*.json` ka version **v:3** (purane cache par `ts` nahi tha, is liye version badhana para — pehla back-fill is liye har video ki metadata dobara padhta hai), item par naya field **`pubts`**, aur `/api/export` JSON me bhi `pubts`. `ts` field pehle se thumbnail ke text-stats ke liye istemaal hota tha — ghari ke liye alag naam rakha gaya warna dono aapas me takra jate (ye ghalti browser me pakri, test me nahi).

Aapki baat thi: *"asani ke liye aur easy-to-use ke liye gehrai se samjho, har feature studio ki tarah ho."* Pehle poore tool ko khol kar padha — aur ye chhe cheezein saaf dikhiin. Ye wo kaam hai jo is daur me hua:

**1. Card ka order palta gaya — pehle masla, phir naap.** Pehle card par 17 chips ek line me chhapte the (views/day, text ka area, contrast, chehra, blur, thirds…) aur action ke button sab se neeche dab kar reh jate the. Ab card ka bahav ye hai: thumbnail → **score ka badge (click = poora hisaab)** → title → channel/views → **us thumbnail ke masle, unka ilaaj ke saath** → sirf **3 button** (`Behtar banao`, `AI se banao`, `poora analysis`) + YouTube ka icon-link. Pehle 4 button the, ab 3 + ek icon — kam clicks, kam choices.

**2. `Masle dikhao | Poore naap` ka toggle.** Wahi 23 cards, do nazar. Default par sirf masle dikhte hain (zyadatar log sirf ye dekhna chahte hain); `Poore naap` par poore 17 chips wapas. Number chhupaye nahi gae — bas raaste se hataye gae.

**3. "In thumbnails me sabse zyada kya kharab hai" — ab pehli baar set ke level par.** Pehle `verdicts()` (jo har naap ke saath ilaaj likhta hai) sirf "Meri Thumbnail" tab tak mehdood tha. Ab wo har card par, `poora analysis` me, table ki row detail me, aur ek **aggregate card** me hai jo ginti deta hai: `Brightness — 17/23 videos me (74%) bahut dark — YouTube ke dark theme me dub jayega`. Neeche ye line bhi sach likhi jati hai: `23 naapi gayi videos me se 1 par tool ko koi masla nahi mila`. Ye is tool ka sabse qeemati hissa tha jo screen par nahi aa raha tha.

**4. Table ki har row par triage.** Thumbnail column me ab `4 masle` ka chhota chip hai (laal = badi kharabi, peela = dhyan do, hara = saaf), aur us par mouse le jao to poora list `title` me aa jata hai. Row kholo to **`Kya kharab hai — aur uska ilaaj`** aur uske neeche **`score ka poora hisaab`** ka drawer. Table ab sirf numbers nahi batati — batati hai kaunsi video pehle theek karni hai.

**5. Score ab black box nahi.** Server par `score_detail()` hai jo har feature ka `naam · kitna achha · wazan · mile hue number` deta hai, aur `base + jama − katauti = antim` tak ka hisaab. Purane scans (jo is field se pehle banaye gae) par bhi wo chalta hai — `_backfill_views()` unhe load par dobara naape bina derive kar leta hai. Wazan ab bhi **heuristic (andaze)** likhe jate hain jab tak aap apna Studio CSV import karke calibrate na karein — ye imandari hai, kami nahi.

**6. KPI strip ka tarteeb badla.** Ahem saat number sabse upar (naapi gayi, inme masla hai, badi kharabi, median views/day, median score, bada text @320, median contrast), aur baaki ath `▸ baaki naap (8) — poora hisaab kholo` ke andar. Pehle 15 number barabar oonchai par the, isliye koi number nazar nahi aata tha.

**Keyboard aur boraai ka hal.** `Ctrl K` = ek box se har jagah (scan, topic, channel — AND-match), `?` = shortcuts ka overlay, table me `j`/`k` se row, `Enter` se kholo, `Esc` se band. Loading ab **skeleton** me dikhti hai (`skelKpi/skelGrid/skelTable/skelLines`) — pehle `<div class="spin">Loading…</div>` tha jo atakne jaisa lagta tha. Toast ab **stack** me hote hain (`#tst`, type ka rang token se, click par band) — pehle ek hi toast hota tha aur doosra aane par pehla gayab. Jin jagahon par kaam fail hota hai wahan ab `failToast(e, "…")` chalta hai, yaani laal toast with "Kaam nahi hua" — pehle wahan bhi neela "info" toast tha.

**Khaali halat ab raasta dikhati hain.** Table me filter se ek bhi row na bache to ab likha aata hai kaunsa filter kitni rows kha gaya (`"zzzqqq" par koi title ya tag nahi mila · sirf shorts dikh rahe`) aur ek `Saare filter hatao` ka button jo waqai reset kar deta hai. A/B tab khaali ho to `esCard` batata hai kaise bharein + `Title Lab kholo` ka button. Ye `esCard` pattern ab har khaali jagah ke liye tayar hai.

**A11y jo is daur theek hui.** Table ke **saare 9 `<th>` par `scope="col"`**, aur jis column par sort hai us par **`aria-sort="ascending|descending"`** (screen reader ko batata hai ke sort kis disha me hai — caret sirf aankh ke liye hota hai). `+N aur masle` pehle `<span onclick>` tha (keyboard se pahuncha hi nahi ja sakta tha) — ab `<button>` hai, ab page par **17 `button.iss-more` aur 0 `span.iss-more`**. A/B table me `<thead>` + `scope` aur delete ka asli button (pehle `<span class="tag">✕</span>` tha). Topbar ka doosra lafz ab page ki heading se milta hai — channel scan par `Channel ke thumbnails`, topic scan par `Competitors` (pehle channel scan par bhi `Competitors` likha aata tha). Client ki copy se **baaqi emoji bhi hata diye** (`⚡ 🎨 🧠 ⚠`) — buttons pehle se icon+naam se pehchane jate hain, isliye copy me bhi wahi naam kaafi hai; warning chips ab `ico("alert")` se banti hain.

**Naapa hua (is browser session me, 1338px par):** console **0 errors**; table ke 9/9 headers par `scope="col"`, active column par `aria-sort=descending`; 23 rows + 23 triage chips; `scrollWidth 1327 < innerWidth 1338` (table ab bhi page chaudha nahi karti); row detail me `Kya kharab hai` + `score ka poora hisaab` + 4 issue rows; A/B khaali state apne 2 buttons ke saath; `?` overlay aur `Ctrl K` palette chalte hain.

**Ye daur do bug pakde, jo pehle ka checker nahi pakad pata tha.** `python -m py_compile` sirf Python check karta hai — `PAGE` ke andar ka JavaScript nahi. Ab ek chhota gate hai: inline `<script>` nikaal kar `node --check`. Usne do asli toot-ein pakdin (ek string ka `'<div id="iout">'` hissa khaali bach gaya tha, ek jagah `esCard(` se pehle ajnabi `'` reh gaya tha) — dono browser ko "Invalid regular expression" de rahe the aur app bilkul boot nahi ho rahi thi. **Rule: `clicklab.py` badalne ke baad `python _jscheck.py; node --check _js0.js` — yehi asli gate hai, brace counter nahi.** Aur ek aur baat: browser me test karte waqt same URL + same hash dobara `goto` karne se document reload **nahi** hota — purana JS chalta rehta hai. Isliye `?r=1` jaisa cache-buster lagao, warna aap apna fix test hi nahi kar rahe.


Aapki baat thi: *"topic scan ki search alag jagah, channel search alag jagah; videos/channels ki total sirf 40 nahi dikhein; tulna display me fit ho; 1 channel ke muqable 10 channels; niche saare tabs ek hi Studio style me."* Jo bana:

**1. Do alag chunav (sidebar).** `CHANNEL CHUNO` alag group hai (apna channel banane ke liye `naya channel`, hataane ke liye `hatao`) aur `TOPIC SCAN CHUNO` alag (naya topic scan). Pehle ek hi dropdown se dono mixed ho rahe the — ab har group ka apna select aur apne buttons hain, aur channel option ka label `naam · 400+ videos` hai (poora detail `title` me).

**2. Channel ki asli ginti, 40 nahi.** Pehle table me sirf "latest 40" dikhte the. Ab har channel scan par ek **walk** chalti hai: `tab()` se poore channel ki listing (longs + shorts, `CH_WALK = 400` tak) nikal kar `thumb_output/chc/` me cache hoti hai, aur `/api/chwalk` se wahi cached list UI ko milti hai. Upar KPI me **`400+` videos** dikhti hai (cap ki wajah se `+` lagaya jata hai — ye 400 se zayada ka sach hai, exact nahi), aur table ke neeche **`X / Y dikh rahi hain`** + `naap barhao` ka button: `extend_chan(id, n)` jo chune hue videos par poora naap (metadata + OCR + thumbnail score) chalata hai aur `agg/deep/cov/cst` dobara gin leta hai. **Naapi gayi** aur **gini gayi** do alag cheezein hain — UI dono alag dikhata hai, kyunki analysis sirf naapi gayi videos par hota hai.

**3. Tulna 10 channels tak, screen ke andar.** Pehle 2 channels the; ab **1 apna + 9 competitor** (picker live gin-ta hai: `— 10 chune / 10 tak`). Table ka style palta gaya: **channels rows me, maap columns me** — channel ka naam **left par chipka (sticky)** rehta hai, aur baaki columns **table ke andar hi** horizontally sarakte hain (`.stscr` + `width:max-content`), page kabhi bahar nahi jata. Do segments: `Ahem maap (7)` / `Saare maap (25)` — 25 columns screen par fit nahi aa sakte isliye core default hai. `mera` badge pehle channel par, har column ka jeetne wala cell neela + trophy, har cell ke neeche us column ke sabse bade number ke muqable bar. `Kaun jeeta` aur `Kamai` ke pehle column bhi chipke hue hain.

**4. Sab tabs ek hi Studio family me.** Deep Analysis ke pattern/benchmark tables, Jeete topics ki winners list, title patterns, ASLI tags, candidate phrases aur AI ke model tables — sab **`.st` shell + `table.stt`** me aa gaye (bar header = title + sample count, right-aligned tabular numbers, row hover). Bare `<table>` jo page par tair rahe the, wo khatam ho gaye; jo tables card ke andar hain unhe wahi hover milta hai. Naapa hua natija: Ideas aur Deep Analysis par **`bare tables: 0`**, 1333px aur 405px dono par `scrollWidth == clientWidth`, **console 0 errors**.

**5. Sacchi misaal (jo abhi disk par hai).** 10 channels ka Tulna: Dhruv Rathee (33.2M subs, 438 videos gini, 51 naapi), Tech Burner, Easy Tech Info, Tech Info, StudyIQ IAS English, Your Level Up Guru, Think School, Khan GS Research Centre, Sandeep Maheshwari, CarryMinati — **kul 211 videos naapi gayi**. Dhruv Rathee ka median views/day 13,116,288 (vpd 651,411) vs Tech Burner 12.5M (vpd 55,963) — farq **11.64×**, Mann-Whitney **p = 0.0002** (n=15 vs 10). Chhote sample wali lines par tool khud warning chhap ta hai.

## Data ki sudhaar — title field (record, taaki purane numbers par bharosa na ho)



`search_ids` title ko channel aur duration ke saath jod kar save kar raha tha, aur code ne wo join dobara tod diya. Natija teen khamiyan thin:

- har stored title ~15 chars lamba ho gaya tha, isliye **title ki lambai ke buckets ghalat** the;
- **"title me number: 100% vs 100%"** dikha — ye poora artifact tha (durations me digits hote hain), koi pattern nahi;
- TF-IDF ideas me **channel ke naam ghus gaye** — "Dhruv Rathee" ek "topic" ban kar aa gaya.

Ye galti **source par** theek ki gayi (title alag, channel alag, duration alag), aur **2 maujooda scans (46 + 46 = 92 rows)** ka stored data bhi theek kiya gaya — `metac/` ke asli metadata se mila kar — phir un scans ka `agg` aur `deep` **dubara naapa gaya**. Ab ke asli numbers: `black hole documentary` scan me title lambai ka median **72 chars** (11–100), "title me number" **12 vs 34** (lift 0.77, p = 0.43 — yaani *koi saboot nahi*), "title me sawal" p = 0.90. **Is tab tak ke purane screenshots me jo title-length/number ke number hain wo galat the.** Aapke scans dobara scan karne ki zaroorat nahi — sirf title field theek hua hai, naap dobara chal chuke hain.

## Data kahan hai

```
thumb_output\scans\<id>.json     — har scan ka permanent record: topic scan (items + aggregate + deep), channel scan, aur Niche Finder dhoondh — "Scan history" isi folder se banti hai; topic ka result 6 ghante tak dobara naapa nahi jaata
thumb_output\metac\<id>.json     — har video ka ASLI metadata (tags, description, chapters, likes, subs)
thumb_output\own.json            — aapke Studio se daale hue asli CTR/retention (CSV import se bhar jaata hai)
thumb_output\calibration.json    — aapke asli CTR par fit hue score ke wazan (cv-R² gate pass hua to hi banta hai)
thumb_output\thumbs\<id>.jpg     — download hue competitor thumbnails (+ .kind = maxres/hq)
thumb_output\chc\*.json          — channel search/listing ka cache (24 ghante); Niche Finder ka jawab isi me `rad2_<key>.json` ke naam se 24 ghante mehfooz rehta hai (strict filter lagne se pehle ke purane jawab serve na hon, isliye key jaan boojh kar badli gayi — pehli dhoondh dobara naapi jaati hai)
thumb_output\cmpbank.json        — Competitor bank (aapki chuni hui videos, hadd 500) — aapka data, share zip me nahi jata
thumb_output\ocrc\*.json         — OCR ka cache (file + size ka key) — dobara scan = seconds
thumb_output\regen\*.png         — ⚡ se bane behtar versions
thumb_output\ai\*.jpg            — 🎨 se bani tasveerein (native size par; _raw = AI ka original)
thumb_output\ai.json             — 🎨 ki history (model, size, strength, direction, asli cost, score, reference se farak)
thumb_output\checks\             — aapki upload ki hui thumbnails
thumb_output\variants.json       — A/B saved jode
runware_key.txt                  — 🎨 ki key (optional). Folder copy karne par key saath chalti hai
models\                          — (optional local SD ke liye) .gguf / .safetensors yahan
```

## Doosre laptop par le jaana

**GitHub se (behtar tareeqa):**
1. Ek baar: `git clone https://github.com/mossoo4568/clicklab.git`, phir us folder me **`setup.bat`** ek baar, phir **`ClickLab.bat`**.
2. Update ke liye folder me **`git pull`** — magar **uske baad server band karke dobara chalao**. Chalta hua Python purana code memory me pakde rehta hai; pull ke baad restart na kiya to screen par purani hi baat chalegi (yehi wo jaal tha jisme "naya code liya magar result waisa hi" lagta hai). `git log --oneline -1` se confirm kar lo ke naya commit aa gaya.
3. `thumb_output\` repo me nahi hai — isliye `git pull` aapki history/scans/bank ko **haath nahi lagata**. Apna data laptop-to-laptop le jaana ho to `thumb_output\` folder copy kar do.

**Zip se (koi git nahi chahiye):**
1. `ClickLab` folder copy karo (ya `ClickLab-share.zip` — usme code, docs aur `SHURU_KARNE_SE_PEHLE.txt` hai; keys aur history jaan boojh kar bahar hain).
2. Naye laptop par pehle **`setup.bat`** ek baar, phir **`ClickLab.bat`**.
3. Runware/Gemini/YouTube keys folder ke saath chali jaati hain; naye machine par badalni ho to AI thumbnail view se nayi daal do.

## Notes / limits

- **Ye observation hai, experiment nahi.** Deep Analysis batata hai ki *inhi videos me* kaunsa tareeka zyada chala — CTR ka pakka jawab sirf aapke apne A/B se milta hai. Isliye tool har chhota sample flag karta hai.
- **CTR/retention kisi aur channel ka public nahi hai.** Isliye wo "index" ke naam par, saaf label ke saath dikhta hai; asli number sirf apni video ka (`own.json` form se). Index ka kaam **tulna** hai, dikhawa nahi.
- **Tags/description/chapters asli hain** (yt-dlp), par YouTube khud kabhi-khali tags chhupa deta hai — jitne mile utne hi dikhate hain, poore 500 chars ka tags field public nahi hota.
- **Chapters ka waqt bhi asli hai** (v3 me theek hua): pehle `start` field padh rahe the jo yt-dlp deta hi nahi, isliye har chapter 0:00 par aa raha tha. Ab `start_time` (seconds) se aata hai — 1:51, 6:35 waghera jaise usne likhe hain. Purana metadata cache apne aap dobara le liya jaata hai (cache ka version badha diya gaya hai), aapko kuch nahi karna.
- **OCR abhi bhi galat padh sakta hai**, bas pehle se kam. RapidOCR (PP-OCRv4) Tesseract se behtar hai magar do asli nuqsanat hain jo **naape** hain: (1) wo stylized text ke shabd **bina space ke jod** deta hai — "BBC FOUR" → `BBCFOUR`, "5 EASY STEPS" → `5EASYSTEPS`, isliye **shabdon ki ginti phool sakti hai**; (2) decorative/3D text par wo kabhi-kabhi **CJK characters** de deta hai. Tool OCR ke boxes image par overlay karke dikhata hai: khud dekh lo kya padha gaya. Contrast aur text-size ke number in galtiyo se kam prabhavit hote hain kyunke wo **box ke pixels** par nape jaate hain, shabdon ki spelling par nahi.
- **Har scan ye record karta hai ke kaunsa engine chala** (YuNet/Haar, RapidOCR/Tesseract, TF-IDF haan/naa), **sample kaise chuna** (kitne alag channels, kitne shorts hataye, kitne dohrav), aur **us waqt kaunse wazan chal rahe the** (heuristic ya calibrated, kitne videos par). Purane scan me ye record nahi to UI saaf likhta hai "purana scan" — un numbers par bharosa mat karo.
- **Sample ki had:** ek topic par ek channel ke 3 se zyada videos nahi rakhe jaate (`ch_cap`), aur 60 second se chhote Shorts hataye jaate hain — warna "winning pattern" asal me ek hi channel ki nqli hota. Sample chhota pada to tool cap dheelha karta hai aur **khud warning likhta hai**.
- **⚡ Tier A hai** — nayi tasveer nahi banata, aapki photo sudharta hai. Isi liye result control me rehta hai. Nayi tasveer 🎨 banata hai.
- **🎨 ka kharcha asli hai.** Har image aur poore batch ki cost Runware ke apne jawab se dikhti hai. Runware kabhi-kabhi ek task ka double charge karta hai (ek hi model ke liye $0.0006 aur $0.0012 dono dekhe) — isliye UI price *range* dikhata hai, aur har result par asli cost likhi hoti hai.
- **4K ka matlab "nayi detail" nahi** — muft wala rasta sirf upsample karta hai. Asli upscale ($0.010) hi detail banata hai.
- **Title Lab ka font approximate hai** (Roboto/Arial) — asli YouTube thoda alag ho sakta hai, par "kitna katega" ka idea sahi milta hai.
- Thumbnail `maxresdefault` milti hai to wahi asli 16:9; na mile to `hqdefault` (4:3 crop) — card par `maxres`/`hq` likha hota hai.
- **Channel ke number adhoore ho sakte hain, aur ye likha hota hai:** videos ki ginti **400 tak** hai (uske aage `+`), analysis sirf **sabse nayi N videos** par hoti hai (baaki sirf gini jaati hain), pattern analysis **sirf longs** par chalta hai, aur **monetization/RPM/CPM/watch time/joined date** public hi nahi — kamai ka har number **ek RPM band par based hai**, jab tak aap apna Studio RPM na daal do. Channel dashboard par ye sab card ke neeche likha hota hai.
- Scan ka data **6 ghante** cache rehta hai; naya data chahiye to topic dobara daal do (cache ki wajah se tez lagega).
- Purane (v1/v2 ke) scans me tags/description nahi honge — wahi topic dobara scan kar lo, seconds lagenge.
- Port 8028 busy ho to tool apne aap agli free port le leta hai — kaala window batata hai kaunsa URL khula.
