# -*- coding: utf-8 -*-
"""
clicklab.py v1 — video bechna: title + thumbnail (CTR). Machine video bana rahi hai;
ye do cheezein insaan ki hain: title likhna aur thumbnail. Ye tool un dono ko numbers
se sudhaarata hai.

Do kaam:
  1. Competitor scan — topic daalo, uske top videos ke thumbnails kholo aur batao ki
     wo log thumbnail KAISE banate hain (text kitna, kitne shabd, kaunse rang, kitna
     contrast, title ki lambai). Aapka thumbnail unke pattern se match karna chahiye.
  2. Meri Thumbnail — apna thumbnail (file path / YouTube link / paste) daalo; tool use
     YouTube ke ASLI sizes par dikhaata hai (browse, mobile, sidebar) aur check karta hai:
     text padha ja sakta hai ya nahi, contrast WCAG pass hai ya nahi, bahut dark/bheed
     to nahi hai.
  3. Title Lab — title ko YouTube ki tarah truncate karke dikhata hai (desktop / mobile /
     sidebar), plus competitors ki title length ka benchmark.
  4. A/B — do variants save karo, baad me decide/export.

Start:  python clicklab.py   or double-click  "ClickLab.bat"
Open:   http://127.0.0.1:8028

Backend (sab free, koi API key nahi):
  yt-dlp  -> topic ke top video ids + views/dates (flat search + per-video batch)
  i.ytimg.com -> thumbnails (maxresdefault, na ho to hqdefault)
  Tesseract -> thumbnail par likha text (na mile to rang/bright analysis phir bhi chalta hai)
  Pillow -> dominant colours, brightness, contrast, clutter
Note: Tesseract na bhi ho to tool chalta hai — sirf OCR wale columns khali rahenge.
"""
import concurrent.futures as cf
import base64
import colorsys
import datetime as dt
import difflib
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
except Exception:                                     # bina Pillow ke bhi tool khulta hai
    Image = ImageDraw = ImageEnhance = ImageFilter = ImageFont = ImageOps = None

try:                                                  # optional: chehra pakadne ke liye
    import cv2
    import numpy as np
except Exception:
    cv2 = np = None

# ---- bhaari engines: ye import me ~1.5 second lete hain (sklearn apne peeche
# scipy/pandas le aata hai). Inhe tool ke pehle harf ke raaste se isliye hataya
# gaya hai ke page aur /api foran jawab dein — aur ye background me tayyar hote
# hain. Chhupaya kuch nahi jaata: /api/sys sach batata hai kaun tayyar hai,
# kaun abhi load ho raha hai, aur kaun is machine par hai hi nahi.
_TFIDF = _RIDGE = _KFOLD = None
_RAPID_CLS = None
_SK_DONE = _OCR_DONE = False
_ENG_LOCK = threading.Lock()


def load_sk():
    """sklearn ka TF-IDF + Ridge + KFold — sirf tab jab semantic tulna ya calibration
    sach me chahiye. Ek hi baar try hota hai; na milne par wahi purana fallback chalta hai."""
    global _TFIDF, _RIDGE, _KFOLD, _SK_DONE
    if _SK_DONE:
        return
    with _ENG_LOCK:
        if _SK_DONE:
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import Ridge
            from sklearn.model_selection import KFold
            _TFIDF, _RIDGE, _KFOLD = TfidfVectorizer, Ridge, KFold
        except Exception:
            pass
        _SK_DONE = True


def load_ocr():
    """RapidOCR (PP-OCRv4, onnxruntime) — sirf tab jab OCR chalana ho."""
    global _RAPID_CLS, _OCR_DONE
    if _OCR_DONE:
        return
    with _ENG_LOCK:
        if _OCR_DONE:
            return
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_CLS = RapidOCR
        except Exception:
            pass
        _OCR_DONE = True


def warm_all():
    """Sab bhaari cheezein ek saath — background thread se is liye ke tool kholte hi
    port jawab de chuka ho. Jo cheez machine par nahi hai wo chup-chaap nahi hoti,
    us ka status eng_state() me dikhta hai."""
    load_ocr()
    load_sk()
    get_yunet()
    find_ytdlp()
    find_tesseract()


def eng_state():
    """Teen halat alag hain — ye imandari ka hissa hai: tayyar, abhi load ho raha
    hai, aur is machine par hai hi nahi."""
    fe = face_engine()
    return {"ocr": bool(_RAPID_CLS), "ocr_loading": (not _RAPID_CLS) and not _OCR_DONE,
            "sk": bool(_TFIDF and _RIDGE), "sk_loading": (not _TFIDF) and not _SK_DONE,
            "face": fe, "face_ready": bool(_YUNET), "cv2": bool(cv2), "np": bool(np),
            "pillow": bool(Image), "tesseract": bool(find_tesseract())}


_WARM_DONE = [False]
_WARM_LK = threading.Lock()


def warm_bg():
    """Bhaari engines aur tools ki khoj tab hoti hai jab page jawab de chuka ho.
    Tool kholte hi screen aati hai; engines us waqt chupke tayyar hote hain, aur
    jo machine par hai hi nahi us ka sach /api/sys me likha rehta hai."""
    with _WARM_LK:
        if _WARM_DONE[0]:
            return
        _WARM_DONE[0] = True
    print("ytdlp:", find_ytdlp(), "| tesseract:", find_tesseract(), "| pillow:", bool(Image),
          "| cv2:", bool(cv2))
    tb = time.perf_counter()
    warm_all()
    print("engines tayyar:", eng_state(), "(", round(time.perf_counter() - tb, 1), "second )")
    g = geninfo()
    rw = g.get("runware") or {}
    print("gpu:", g.get("gpu") or "?", "| comfyui:", bool(g.get("comfy")),
          "| models folder:", len(g.get("models") or []))
    print("runware:", ("key set (" + rw.get("hint", "") + ") - " + str(rw.get("shots")) +
                       " soch ka kul $" + str(rw.get("batch")) + "-" + str(rw.get("batch_hi")) +
                       " per click" if rw.get("key") else
                       "key nahi - AI band hai; Behtar banao (wahi photo sudharna) muft chalta rahega. Key UI me daal sakte hain."))


def start_warm(delay=0.25):
    """Pehle jawab ke baad ek hi baar chalu. Pehla request page ka hota hai, is liye
    browser ko mil gaya tabhi bhaari kaam shuru hota hai."""
    if _WARM_DONE[0]:
        return
    t = threading.Timer(delay, warm_bg)
    t.daemon = True
    t.start()

PORT = 8028
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
HERE = Path(__file__).resolve().parent
OUT = HERE / "thumb_output"
THUMB_DIR = OUT / "thumbs"
CHK_DIR = OUT / "checks"
TMP_DIR = OUT / "tmp"
SCN_DIR = OUT / "scans"
REG_DIR = OUT / "regen"
HIST_DIR = OUT / "hist"
OCR_DIR = OUT / "ocrc"
META_DIR = OUT / "metac"
OWN_F = OUT / "own.json"
VAR_F = OUT / "variants.json"
MODEL_DIR = HERE / "models"
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
CAL_F = OUT / "calibration.json"

# Threshold SIRF yahan. Pehle code me 3 jagah alag-alag number likhe the (verdicts me
# "theek >=14px", score me "poora wazan >=18px", README me "18px+"; sample ka flag UI me
# n<4, buckets me n<2, pattern me n>=3) — ek hi cheez ke 3 farq number jhoot hain.
#
# Ye numbers ab ANDAAZE nahi: tool ne apne hi 102 asli competitor thumbnails par har
# metric ki distribution naapi hai, aur threshold us distribution par set kiye. Saamne jo
# percentile likha hai wo usi corpus ka asli naapa hua hissa hai (n=101-102). Misaal:
# "clutter_ok" pehle 22 tha jabke poore corpus ka maximum 12 nikla — yaani wo threshold
# kabhi kuch flag hi nahi karta tha (moot kachra). Ab wo 8 (=p90) par hai.
#
# Distribution (n=102, apne 12 topics ke maxres thumbnails par probe se naapi gayi):
#   h320   p5=10.5 p10=11.5 p25=18.5 p50=27.0 p75=35.8 p90=48.5
#   cr     p5=1.81 p10=2.23 p25=4.06 p50=8.20 p75=13.2 p90=19.7 (max 20.75; WCAG hadd 21)
#   ring   p10=2.55 p25=4.22 p50=9.45 p75=14.6
#   words  p50=4 p75=7 p90=11 | blocks p50=3 p75=5 | text area p50=12.8 p75=25.2
#   face%% p50=2.3 p75=6.9 p90=9.1 (max 17.4) | bright p10=.074 p50=.198 p90=.515
#   dyn    p10=.379 p25=.603 p50=.731 | clutter p50=4 p90=8 p95=10 (poora max 12)
#   sharp  p10=679 p50=1453 p90=2714 | dom p25=.32 p50=.49 p90=1.0
#   subj%% p25=7.2 p50=12.1 p90=30.0 | thirds p25=.585 p50=.68 p90=.825
TH = {"h_ok": 18.0, "h_mid": 12.0, "h_warn": 9.0,  # 320px par text (px) = p25 / p10 / ~p5
      "cr_ok": 4.5, "cr_warn": 3.0,         # asli glyph-vs-background WCAG = ~p25 / ~p15
      "ring_ok": 3.0,                       # outline/shadow ka asar = ~p13
      "words_ok": 4, "words_warn": 8,       # shabd = p50 / ~p80 (RapidOCR kuch shabd bina
                                            # space jod deta hai, ginati thodi phuli hoti hai)
      "blocks_ok": 2, "area_ok": 22,        # blocks = ~p25 / text area = ~p70
      "bright": (0.10, 0.60), "dyn_ok": 0.45,
      "clutter_ok": 8,                      # = p90 (pehle 22 = kabhi flag nahi karta tha)
      "face_ok": 8.0, "face_min": 1.0,      # chehra frame ka kitna % = ~p88 / ~p30
      "thirds_ok": 0.60, "dom_warn": 0.32,  # composition = ~p25 / dominance ka ~p25
      "ch_cap": 3, "short_s": 60,           # sample ki safai: ek channel se max, Shorts nahi
      # score ke features 0..1 par is range me normalize hote hain; range distribution ke
      # ~p10/p25 se ~p90 tak li gayi hai taaki poora corpus 0 ya 1 par na chipak jaaye
      "dom_lo": 0.32, "dom_hi": 0.95,       # frame me ek subject dominant hai ya bheed
      "subj_lo": 7.0, "subj_hi": 30.0,      # subject ka box frame ka kitna % hai
      "thirds_lo": 0.55, "thirds_hi": 0.85,
      "sharp_lo": 700.0, "sharp_hi": 2500.0,
      "face_lo": 1.0, "face_hi": 9.0, "cr_full": 7.0,
      "min_n": 5}                           # isse kam sample par koi lift dikhao hi mat
CAL_MIN_N = 8                               # itni asli CTR rows par hi weights fit karo
# Fit ka 5-fold cross-validation R² is se kam ho to wazan ISTEMAL NAHI karte:
# 0 ka matlab "mean se behtar kuch nahi sika", minus ka matlab mean se bhi bura.
# Naapa hua 16 nakli CTR rows par: R²(in-sample)=0.55 tha magar cv_r2=-0.63 —
# sirf in-sample dekh kar wazan badalna hi khud-dhoka hota.
CAL_MIN_CV = 0.05

TTL = 6 * 3600            # itne ghante purana scan chalega
WORKERS = 3               # parallel yt-dlp
WORKERS2 = 8              # parallel thumbnail/OCR (har thread alag tesseract; 8 core par aaram)
# Naap ke kharche ka andaza UI ko dikhane ke liye. Ye do number hawa se nahi aaye:
# 25 Oct ko is machine par alag naape gaye (yt-dlp se metadata ~3s/video, aur
# thumbnail+OCR+chehra ~0.5-1s/video). Inhi se meas_eta banata hai.
ENRICH_SEC = 3.0
MEASURE_SEC = 1.0
CHUNK = 10                # ek yt-dlp call me kitni videos
DEF_N = 50                # topic ke kitne videos
MAXN = 60                 # isse zyada nahi (warna pehli scan bahut lambi)
MAX_OCR_SIDE = 2400       # OCR se pehle itna upscale
FONTS = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeui.ttf",
         r"C:\Windows\Fonts\tahomabd.ttf", r"C:\Windows\Fonts\impact.ttf",
         r"C:\Windows\Fonts\arial.ttf"]

_lock = threading.Lock()
JOBS = {}

# ---------------- tools / helpers ----------------

_YDL_LOCK = threading.Lock()
_YDL = None


def find_ytdlp():
    """yt-dlp ki jagah ek baar dhoondh kar rakh lein — background warm-up aur pehla
    scan dono ek saath daud sakte hain, is liye lock. Download kabhi adhoora na rahe."""
    global _YDL
    if _YDL:
        return _YDL
    with _YDL_LOCK:
        return _find_ytdlp()


def _find_ytdlp():
    p = shutil.which("yt-dlp")
    if p:
        _YDL = p
        return p
    b = HERE / "bin" / "yt-dlp.exe"
    if b.exists():
        _YDL = str(b)
        return _YDL
    b.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", timeout=180) as r, \
            open(b, "wb") as f:
        f.write(r.read())
    _YDL = str(b)
    return _YDL


def find_tesseract():
    for c in (shutil.which("tesseract"),
              r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              str(HERE / "bin" / "tesseract" / "tesseract.exe")):
        if c and Path(c).exists():
            return c
    return None


def find_yunet():
    """YuNet (cv2.FaceDetectorYN) ka ONNX model — ek baar download, phir hamesha offline.
    Haar se farq: ye aadha-chehra / ghuma hua (yaw-roll-pitch) / chhota chehra bhi pakadta
    hai aur box tight deta hai. Model na mile to purana Haar fallback chalta hai."""
    p = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
    if p.exists() and p.stat().st_size > 10000:
        return str(p)
    try:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = str(p) + ".part"
        with urllib.request.urlopen(YUNET_URL, timeout=180) as r, open(tmp, "wb") as f:
            f.write(r.read())
        os.replace(tmp, str(p))
        return str(p)
    except Exception:
        return None


_YUNET = None          # None = try, False = tried and failed, else detector
_YUNET_LK = threading.Lock()   # sirf detector banane ka lock — import lock se alag
_RLOC = threading.local()      # RapidOCR engine per thread (nahi to onnx session share hoti hai)
# cv2.FaceDetectorYN ka ek session ek hi waqt par ek thread use kar sakta hai:
# scan ke threads ye share karte hain to process chup-chaap crash ho jata hai
# (koi Python traceback nahi, bas exit 1 — naapa hua: 50-video scan beech me mara).
# isliye detect() ko lock ke andar rakha hai; naapa hua 0.10s/img, serial bhi chalega.
_FACE_LK = threading.Lock()


def face_engine():
    """Bina model load kiye batata hai ke chehra kaun pakdega: yunet, haar ya kuch nahi.
    Page kholte hi ~0.2s ka ONNX session banana zaroori nahi — wo asli kaam tab hoga
    jab pehli naap chalegi. Is se pehla /api/sys halka rehta hai."""
    if cv2 is None:
        return "none"
    return "yunet" if (find_yunet() or _YUNET) else "haar"


def get_yunet():
    global _YUNET
    if cv2 is None:
        return None
    with _YUNET_LK:
        if _YUNET is None:
            m = find_yunet()
            try:
                _YUNET = cv2.FaceDetectorYN.create(m, "", (0, 0), 0.5) if m else False
            except Exception:
                _YUNET = False
    return _YUNET or None


def get_rapid():
    """RapidOCR (PP-OCRv4 onnx) — thread-local, kyun ki engine thread-safe nahi hai aur
    8 threads par scan chalta hai. ~1s models ek baar, phir ~0.2s/image."""
    eng = getattr(_RLOC, "eng", None)
    if eng is False:
        return None
    if eng is not None:
        return eng
    if _RAPID_CLS is None:
        load_ocr()
    if _RAPID_CLS is None:
        _RLOC.eng = False
        return None
    try:
        eng = _RAPID_CLS()
        _RLOC.eng = eng
    except Exception:
        _RLOC.eng = False
        return None
    return eng


def _rapid_resize(eng, side, kind):
    """PP-OCR ka apna resize: default 'min 736' (1280px thumbnail ko 1300px par le jaata
    hai — theek hai). 320px wale asli browse test ke liye resize bilkul band karna zaroori
    hai, warna chhota text bara karke padh liya jaayega aur test jhoota ho jaayega."""
    try:
        op = eng.text_detector.preprocess_op[0]
        op.limit_type = kind
        op.limit_side_len = int(side)
    except Exception:
        pass


def _rapid_words(img_arr, scale_to=None):
    """RapidOCR se line-level boxes + text. Word boxes line ke andar character-chourai se
    baante jaate hain (line ka box asli hai; word ka anumaanit — isliye `wid` flag)."""
    eng = get_rapid()
    if eng is None:
        return None
    if scale_to:
        w = int(scale_to)
        h = max(8, int(scale_to * img_arr.shape[0] / img_arr.shape[1]))
        arr = cv2.resize(img_arr, (w, h), interpolation=cv2.INTER_AREA if w < img_arr.shape[1] else cv2.INTER_CUBIC)
        _rapid_resize(eng, 100000, "max")        # jaisa hai waisa padho — 320px ka asli test
    else:
        arr = img_arr
        _rapid_resize(eng, 736, "min")
    try:
        res, _ = eng(arr)
    except Exception:
        return None
    out = []
    for item in (res or []):
        try:
            box, txt, conf = item[0], str(item[1]), float(item[2])
        except Exception:
            continue
        txt = txt.strip()
        if not txt or conf < 0.5 or not re.search(r"[0-9A-Za-z\u0600-\u06ff]", txt):
            continue
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        x0, y0 = max(0, min(xs)), max(0, min(ys))
        x1, y1 = min(arr.shape[1], max(xs)), min(arr.shape[0], max(ys))
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        sc = 1.0 / (float(scale_to) / arr.shape[1]) if scale_to else 1.0
        parts = [p for p in re.split(r"\s+", txt) if p]
        if not parts:
            continue
        total = sum(len(p) for p in parts) or 1
        cx = x0
        for p in parts:
            pw = max(2, int(round((x1 - x0) * (len(p) / float(total)))))
            out.append({"t": p, "x": int(cx / sc), "y": int(y0 / sc),
                        "w": int(pw / sc), "h": int((y1 - y0) / sc), "conf": int(round(conf * 100)),
                        "wid": 1, "line": "%d_%d_%d" % (int(x0 / sc), int(y0 / sc), int((y1 - y0) / sc))})
            cx += pw
    return out




def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def run(cmd, timeout=600):
    # YouTube ka bot-check ("Sign in to confirm you're not a bot") is machine ke IP par
    # nirbhar karta hai — kabhi-kabhi beech ke scans par aa jaata hai. Agar user ne tool
    # ke folder me cookies.txt rakha hai (browser extension "Get cookies.txt LOCALLY" se
    # export hoti hai) to wo har yt-dlp call me apne aap lag jaata hai. Jo call pehle se
    # --cookies de rahi hai usme dobara nahi jodte.
    try:
        if _YDL and cmd and str(cmd[0]) == _YDL:
            if "--cookies" not in cmd:
                ck = HERE / "cookies.txt"
                if ck.exists():
                    cmd = [cmd[0], "--cookies", str(ck)] + list(cmd[1:])
            # Windows par yt-dlp console codepage (cp1252) me likh sakta hai — phir
            # ' jaise characters U+FFFD ban jaate hain. Output hamesha UTF-8 maango.
            if "--encoding" not in cmd:
                cmd = [cmd[0], "--encoding", "utf-8"] + list(cmd[1:])
    except Exception:
        pass
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return (124, "", "timeout after %ss" % timeout)
    return (r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"))


def pnum(s):
    try:
        return int(float(s))
    except Exception:
        return None


def med(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return 0
    n = len(xs) // 2
    return xs[n] if len(xs) % 2 else round((xs[n - 1] + xs[n]) / 2, 4)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def pctl(xs, q):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return 0.0
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def srgb(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rng(x, lo, hi):
    """Seedhi line: `lo` par 0, `hi` par 1, beech me proportion. Thresholds TH me isliye
    hain taaki ek jagah se badlein aur code me kahin bhi number double na ho."""
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (float(x) - float(lo)) / float(hi - float(lo))))


def rlum(rgb):
    r, g, b = rgb
    return 0.2126 * srgb(r / 255.0) + 0.7152 * srgb(g / 255.0) + 0.0722 * srgb(b / 255.0)


def cratio(a, b):
    hi, lo = max(a, b), min(a, b)
    return round((hi + 0.05) / (lo + 0.05), 2)


def fam_of(hexc):
    try:
        r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    except Exception:
        return "?"
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    if v < 0.16:
        return "kaala"
    if s < 0.14:
        return "safed" if v > 0.80 else "grey"
    if v < 0.30:
        return "dark"
    d = h * 360
    if d < 15 or d >= 345:
        return "laal"
    if d < 42:
        return "narangi"
    if d < 70:
        return "peela"
    if d < 100:
        return "hara-peela"
    if d < 170:
        return "hara"
    if d < 200:
        return "cyan"
    if d < 255:
        return "neela"
    if d < 290:
        return "jamuni"
    return "gulaabi"


# ---------------- 1. topic -> videos ----------------

def search_ids(topic, n):
    y = find_ytdlp()
    # channel + duration bhi flat-playlist se mil jaate hain (baad me enrich me dobara
    # lena bekaar tha) — inhi se sample saaf kiya jaata hai, neeche search_wide me.
    cmd = [y, "--flat-playlist", "--no-warnings", "--print",
           "%(id)s\t%(title)s\t%(channel)s\t%(duration)s",
           "ytsearch" + str(n) + ":" + topic]
    rc, out, err = run(cmd, timeout=180)
    items = []
    for ln in out.splitlines():
        p = ln.split("\t")
        if len(p) >= 2 and p[0]:
            # " ".join(p[1:]) purana tareeqa tha — us se title ke aage channel ka naam aur
            # duration ka number chipak jaata tha ("... Explained | Dhruv Rathee 1303").
            # Us se title-lambai ki naap galat hoti thi, "title me number hai" har video par
            # sach ho jaata tha, aur ideas me channel ka naam baar-baar aata tha. Ab sirf
            # title; channel aur duration alag fields me hain.
            it = {"id": p[0], "title": (p[1] or "").strip()}
            if len(p) >= 3:
                it["chan"] = p[2]
            if len(p) >= 4:
                it["fdur"] = pnum(p[3])
            items.append(it)
    return items


# ---------------- style catalog (user ne khud di hai) ----------------
# Ye catalog sirf ye batata hai ke kaunsi production-style kis niche me chalti hai —
# koi ye dawa nahi ke style behtar hai. Style ka sach "Style jeet" view me nikalta
# hai: scan me jo videos actually jeet rahi hain (views/day), unki style ka share.
# any=True ka matlab style har niche me chal sakti hai (user ki list ke "Any niche").
STYLES = {
    "stickman":    {"n": "Any Stickman Animation",        "nic": ["Explainers", "History", "Stories", "Money & business"], "t": ["stickman animation", "stickman explainer video"]},
    "whiteboard":  {"n": "Whiteboard Animation",          "nic": ["Explainers", "Education", "Money & business"], "t": ["whiteboard animation", "whiteboard explainer"]},
    "blackboard":  {"n": "Blackboard Animation",          "nic": ["Explainers", "Education", "Science"], "t": ["blackboard animation lesson"]},
    "doodle":      {"n": "Cartoon Doodle",                "nic": ["Explainers", "Money & business", "Self-help"], "t": ["doodle animation explainer"]},
    "illustrated": {"n": "Illustrated Story",             "nic": ["Stories", "History", "Kids"], "t": ["illustrated animated story"]},
    "chalkboard":  {"n": "Chalkboard Lesson",             "nic": ["Education", "Maths", "Exams"], "t": ["chalkboard math explanation"]},
    "documentary": {"n": "Documentary",                   "nic": ["History", "True stories", "News & events", "Money & business"], "t": ["documentary"]},
    "stockfoot":   {"n": "Stock Footage Documentary",     "nic": ["Explainers", "Facts & lists", "History"], "any": True, "t": ["stock footage documentary", "facts list documentary"]},
    "mannequin":   {"n": "3D Mannequin Documentary",      "nic": ["History", "Documentary", "Stories"], "any": True, "t": ["3d mannequin documentary"]},
    "avatar":      {"n": "AI Avatar",                     "nic": ["Explainers", "Health", "Money", "Tips & habits"], "any": True, "t": ["ai avatar explainer"]},
    "compil":      {"n": "Compilation",                   "nic": ["Top 10s", "Best moments"], "any": True, "t": ["top 10 compilation"]},
    "sleep":       {"n": "Sleep Story",                   "nic": ["Sleep stories", "Calm history", "Audiobooks"], "t": ["sleep story", "bedtime story calm"]},
    "movieexp":    {"n": "Movie Explainer",               "nic": ["Movie recaps", "Series explained"], "any": True, "t": ["movie explained", "movie recap"]},
    "minstick":    {"n": "Minimal Stickman",              "nic": ["Explainers", "Ideas"], "t": ["minimal stickman animation"]},
    "beanie":      {"n": "Beanie Stickman",               "nic": ["How-to", "Tech", "Stories"], "t": ["stickman how to animation"]},
    "caveman":     {"n": "Caveman Comedy",                "nic": ["Comedy", "Satire", "Analogies"], "t": ["caveman comedy animation"]},
    "mgexp":       {"n": "Motion Graphics Explainer",     "nic": ["Explainers", "Numbers", "Business", "Tech"], "t": ["motion graphics explainer"]},
    "mgdoc":       {"n": "Motion Graphics Documentary",   "nic": ["Documentary", "True crime", "History", "Biography"], "t": ["motion graphics documentary"]},
    "memeexp":     {"n": "Meme Explainer",                "nic": ["Explainers", "Memes", "Education", "Science"], "t": ["meme explainer"]},
}


def styles_get():
    nics = []
    for s in STYLES.values():
        for x in s["nic"]:
            if x not in nics:
                nics.append(x)
    return {"ok": True, "styles": STYLES, "niches": nics}


KW_STOP = set("""the a an and or of to in for on with about how why what who when which is are was were be been do does did
this that these those it its as at by from if then than so too very more most other some such into over under your my our
their his her they we you i me he she us him them ka ki ke ko ka ne main me par pe se tak hain hai tha tha tha kar karti
karta liye bana bane ek bhi ya aur kya kis why's vs top best up down new 2024 2025 2026 video videos full hd 4k""".split())


def kw_find(niche, style):
    """Sirf us niche+style ke keywords — YouTube ka apna suggest box + us search ke
    natijon ke titles ki ginti. Koi naya naap nahi, koi model nahi: jo log sach me
    type kar rahe hain aur jo jeetne wale titles me baar baar likha hai, wahi.
    Asli tags to har video ke scan par hi milte hain — ye unka pehla andaaza hai."""
    st = STYLES.get(style) or {}
    nl = (niche or "").lower()
    seeds = []
    for t in st.get("t", [])[:3]:
        seeds.append(t)
        if nl:
            seeds.append(t + " " + nl)
    if not seeds:
        seeds = [nl or "youtube"]
    qs, seen = [], set()
    for s in seeds[:4]:
        if s not in seen:
            seen.add(s)
            qs.append(s)
        for g in suggest(s, 4):
            gl = g.lower()
            if gl not in seen and (not nl or any(w in gl for w in nl.split())):
                seen.add(gl)
                qs.append(g)
        if len(qs) >= 10:
            break
    cnt, src, vids = {}, {}, 0
    for qq in qs[:8]:
        try:
            got = list(search_ids(qq, 6))[:6]
        except Exception:
            got = []
        vids += len(got)
        for it in got:
            ttl = (it.get("title") or "").lower()
            ws = [w for w in re.findall(r"[a-z][a-z'-]{2,}", ttl) if w not in KW_STOP]
            for w in ws:
                cnt[w] = cnt.get(w, 0) + 1
                src.setdefault(w, qq)
            for i in range(len(ws) - 1):
                bg = ws[i] + " " + ws[i + 1]
                cnt[bg] = cnt.get(bg, 0) + 2   # do shabd ek saath = mazboot signal
                src.setdefault(bg, qq)
    for g in qs[1:]:
        gl = g.lower()
        cnt[gl] = max(cnt.get(gl, 0), 3)       # suggest box me tha = log type kar rahe hain
        src.setdefault(gl, "suggest box")
    top = sorted(cnt.items(), key=lambda kv: -kv[1])[:40]
    return {"ok": True, "kws": [{"w": w, "n": n, "src": src.get(w, "")} for w, n in top if n >= 2],
            "queries": qs, "vids": vids,
            "note": "ye shabd suggest box + " + str(vids) + " results ke titles se gin kar ikatthe hue hain — "
                    "asli tags har video ke scan par milte hain"}


# ---------------- transcription (sirf tab jab user maange) ----------------
# Video ke apne subtitles — YouTube ka diya hua data (manual ya auto-generated).
# Sach: auto subtitles me galtiyan hoti hain, aur har video par subtitles hote hi
# nahi — isliye ye kaam kabhi apne aap nahi hota, sirf button par, aur ek baar
# disk par cache ho jata hai (funnel ke "manual hi chale" rule ke saath).
TR_DIR = OUT / "tr"

# Screen-OCR ka shor rokne ke liye: ek video par ek hi OCR job chale (dusra caller
# chupchap pehle wale ke khatam hone ka intezaar kare, phir cache se le). Sath me
# live progress — UI "frame 34/60" dikha sakta hai, andhere me ghanta nahi ginta.
_TR_LOCKS = {}
_TRP = {}
_TR_M = threading.Lock()


def _tr_lock(vid):
    with _TR_M:
        return _TR_LOCKS.setdefault(vid, threading.Lock())


_LOG_M = threading.Lock()


def _log(msg):
    """cmd/console par ek line — threads se bhi aati hai to koi adhoori line nahi."""
    with _LOG_M:
        try:
            print(msg, flush=True)
        except Exception:
            pass


def _tr_vtt(vtt):
    """WebVTT ko plain text banana hai: timestamps aur tags hatado, aur auto-subtitles
    ki rolling duplication (ek hi line baar baar) hatao — wo formatting hai, content
    nahi."""
    out, prev = [], None
    for ln in vtt.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in ln:
            continue
        ln = re.sub(r"<[^>]+>", "", ln).lstrip(">").strip()
        if not ln or ln == prev:
            continue
        prev = ln
        out.append(ln)
    return " ".join(out)


def tr_get(vid):
    vid = re.sub(r"[^A-Za-z0-9_-]", "", vid or "")[:12]
    if not vid:
        return {"error": "video id saaf nahi"}
    TR_DIR.mkdir(exist_ok=True)
    fp = TR_DIR / (vid + ".txt")
    if fp.exists():
        return {"ok": True, "vid": vid,
                "text": fp.read_text(encoding="utf-8", errors="replace"), "cached": True}
    cmd = [find_ytdlp(), "--skip-download", "--no-warnings", "--write-auto-subs",
           "--write-subs", "--sub-langs", "en.*,ur.*,hi.*", "--convert-subs", "vtt",
           "-o", str(TR_DIR / (vid + ".%(ext)s")), "https://www.youtube.com/watch?v=" + vid]
    _log("tr %s: YouTube se subtitles fetch ho rahe hain..." % vid)
    r = run(cmd, timeout=120)
    # 429 (Too Many Requests) YouTube ka temporary rate-limit hai, tool ki kharabi
    # nahi — ek baar 4 second ruk kar dobara maango, tabhi haar maano.
    if r[0] != 0 and "429" in (r[2] or r[1] or ""):
        time.sleep(4)
        r = run(cmd, timeout=120)
    txt, lang = None, ""
    for f in sorted(TR_DIR.glob(vid + ".*.vtt")):
        try:
            parts = f.name.split(".")
            lg = parts[-2] if len(parts) >= 3 else ""
            t = _tr_vtt(f.read_text(encoding="utf-8", errors="replace"))
            if len(t) > 40 and (txt is None or lang.startswith("en") or not lang):
                txt, lang = t, lg
        except Exception:
            pass
    for f in TR_DIR.glob(vid + ".*"):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass
    if not txt:
        if r[0] == 0:
            _log("tr %s: is video par subtitles maujood hi nahi" % vid)
            return {"error": "is video ke subtitles YouTube par nahi hain (na manual, na auto) — "
                             "yahan transcription nahi, analysis hi sahi"}
        e = ((r[2] or r[1] or "").splitlines() or ["?"])[-1][:200]
        hint = ""
        if "429" in e or "not a bot" in e.lower() or "sign in to confirm" in e.lower():
            hint = (" — YouTube ne is IP ko thodi der ke liye roka hai (rate-limit) — ye tool "
                    "ki kharabi nahi; ek baar dobara koshish ho chuki. 1–2 minute baad button "
                    "phir dabayein, ya browser extension \"Get cookies.txt LOCALLY\" se cookies "
                    "export kar ke ClickLab folder me cookies.txt rakh dein — aksar ye wahi "
                    "raasta hai.")
        return {"error": "yt-dlp subtitles nahi la saka: " + e + hint}
    _log("tr %s: subtitles aa gaye (lang=%s, %d akshar) — cache me save" % (vid, lang or "?", len(txt)))
    cut = len(txt) > 60000
    txt = txt[:60000]
    fp.write_text(txt, encoding="utf-8")
    return {"ok": True, "vid": vid, "text": txt, "lang": lang, "cut": cut,
            "note": "ye YouTube ke apne subtitles hain (manual ya auto-generated) — auto me "
                    "galtiyan ho sakti hain; tool ne sirf timestamps hatakar joda hai, shabd badle nahi"}


def tr_ocr(vid):
    """Jin videos par subtitles hi nahi (khamosh video, quiz, text-only slides — jaise
    whiteboard/stickman explainers aksar hote hain), wahan SCREEN par likha text frames
    se padha jaata hai: video ka sabse chhota format download → har ~step second ka
    frame (max 60) → wahi OCR engine jo thumbnails ke liye chalta hai → lines, time
    ke saath. Ye awaz ka transcript NAHI hai — screen ka text hai; note me yehi likha
    jaata hai. Result <id>.ocr.txt me cache — ek hi video par ek baar kharcha."""
    vid = re.sub(r"[^A-Za-z0-9_-]", "", vid or "")[:12]
    if not vid:
        return {"error": "video id saaf nahi"}
    TR_DIR.mkdir(exist_ok=True)
    fp = TR_DIR / (vid + ".ocr.txt")
    if fp.exists():
        return {"ok": True, "vid": vid, "kind": "ocr", "cached": True,
                "text": fp.read_text(encoding="utf-8", errors="replace")}
    ff = shutil.which("ffmpeg")
    if not ff:
        return {"error": "ffmpeg nahi mila — screen-text OCR ke liye ffmpeg chahiye (install karke dobara try karein)"}
    if Image is None:
        return {"error": "Pillow/OCR engine is process me chala hi nahi — screen text OCR mumkin nahi"}
    wd = TR_DIR / (vid + ".frames")
    try:
        _TRP[vid] = {"stage": "download", "done": 0, "total": 0}
        _log("tr-ocr %s: video ka sabse chhota format download + frames nikalna shuru..." % vid)
        shutil.rmtree(wd, ignore_errors=True)
        wd.mkdir(parents=True)
        ytdlp = find_ytdlp()
        # YouTube media download kabhi 403/bot-block kar deta hai — player client
        # badal kar dobara azmate hain (tv/mweb clients ko aksel allow mil jaata hai).
        last_err = ""
        for cargs in (None, "youtube:player_client=android", "youtube:player_client=ios",
                      "youtube:player_client=tv"):
            cmd = [ytdlp, "-f", "worst[ext=mp4][height<=480]/worst[height<=480]/worst[ext=mp4]/worst",
                   "--no-warnings", "--no-playlist"]
            if cargs:
                cmd += ["--extractor-args", cargs]
            cmd += ["-o", str(wd / "v.%(ext)s"), "https://www.youtube.com/watch?v=" + vid]
            r = run(cmd, timeout=300)
            vids = sorted(wd.glob("v.*"))
            if vids:
                break
            last_err = (((r[2] or r[1] or "").splitlines() or ["?"])[-1])[:200]
            for junk in wd.glob("v.*"):
                try:
                    junk.unlink()
                except Exception:
                    pass
        if not vids:
            _log("tr-ocr %s: NA-KAM — video download nahi ho saka: %s" % (vid, last_err))
            return {"error": "video download nahi ho saka: " + last_err}
        vf = vids[0]
        dur = 0.0
        fpb = shutil.which("ffprobe")
        if fpb:
            rr = run([fpb, "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=noprint_wrappers=1:nokey=1", str(vf)], timeout=60)
            try:
                dur = float((rr[1] or "").strip())
            except Exception:
                dur = 0.0
        step = max(6.0, min(20.0, (dur / 60.0 if dur > 0 else 12.0)))
        fpsv = ("%.5f" % (1.0 / step))
        r2 = run([ff, "-hide_banner", "-loglevel", "error", "-i", str(vf),
                  "-vf", "fps=" + fpsv + ",scale=900:-2", "-q:v", "3",
                  "-frames:v", "60", str(wd / "f%04d.jpg")], timeout=240)
        frames = sorted(wd.glob("f*.jpg"))[:60]
        if not frames:
            return {"error": "frames nahi ban sake (ffmpeg): " +
                             (((r2[2] or r2[1] or "").splitlines() or ["?"])[-1])[:200]}
        _TRP[vid] = {"stage": "ocr", "done": 0, "total": len(frames)}
        _log("tr-ocr %s: %d frames bane — ab har frame ka alag OCR/API call (ye slow hissa hai)" % (vid, len(frames)))

        def frame_lines(p):
            ws = ocr_words(str(p)) or []
            ws = [w for w in ws if (w.get("t") or "").strip()]
            if not ws:
                return []
            ws.sort(key=lambda w: (w.get("y", 0), w.get("x", 0)))
            lines, cur, cy = [], [], None
            for w in ws:
                if cy is None or abs(w.get("y", 0) - cy) <= max(14, (w.get("h") or 12)):
                    cur.append(w)
                    cy = w.get("y", 0) if cy is None else cy
                else:
                    lines.append(cur)
                    cur, cy = [w], w.get("y", 0)
            if cur:
                lines.append(cur)
            out = []
            for ln in lines:
                ln.sort(key=lambda w: w.get("x", 0))
                s = " ".join(str(w["t"]).strip() for w in ln)
                s = re.sub(r"\s+", " ", s).strip()
                if len(s) >= 2 and not re.fullmatch(r"[-–—.|·•_—\s]+", s):
                    out.append(s)
            return out

        got, prev = [], None
        for i, p in enumerate(frames):
            _TRP[vid]["done"] = i + 1
            _log("tr-ocr %s: frame %d/%d ka OCR shuru" % (vid, i + 1, len(frames)))
            tsec = int(i * step + step / 2)
            stamp = "%02d:%02d" % (tsec // 60, tsec % 60)
            for s in frame_lines(p):
                if s == prev:
                    continue
                if got and s in got[-1][1]:  # rolling same slide ka dohra text
                    continue
                prev = s
                got.append((stamp, s))
        _log("tr-ocr %s: saare %d frames ka OCR khatam — ab lines jod kar cache likh raha hoon" % (vid, len(frames)))
        if not got:
            _log("tr-ocr %s: NA-KAM — frames me koi saaf text nahi padha gaya" % vid)
            return {"error": "frames me koi saaf text nahi padha gaya — ho sakta hai is video "
                             "me screen par likha ho hi na (ya text itna chhota/bahut tez badla "
                             "ho ke OCR na pakad saka)"}
        text = "\n".join(st + "  " + s for st, s in got)
        cut = len(text) > 60000
        text = text[:60000]
        fp.write_text(text, encoding="utf-8")
        _log("tr-ocr %s: MUKAMMAL — %d screen-text lines, cache me save (ab kabhi dobara API kharcha nahi)" % (vid, len(got)))
        return {"ok": True, "vid": vid, "kind": "ocr", "text": text, "cut": cut,
                "frames": len(frames), "step": int(step),
                "note": "ye SCREEN par dikha hua text hai — har ~%d second ke frame ka OCR, "
                        "time ke saath. Ye video ki AWAZ nahi hai (subtitles is par the hi "
                        "nahi), aur beech ke chhote/tez badle hue text chhoot sakte hain." % int(step)}
    finally:
        shutil.rmtree(wd, ignore_errors=True)
        _TRP.pop(vid, None)


# ---------------- jeet ka model-verdict (Gemini → Pollinations → saaf inkaar) ----------------
# Sirf un scans par jo "jeetne wali" (median se 2×+) chhaan chuke hain. Model ki raay
# sahy-sambandh batla sakti hai, wajah sabit nahi karti — ye label har jawab ke saath
# juda hai. Provider chain: pehle Gemini (apni key), wahan limit/na-hone par
# Pollinations ka keyless text endpoint, phir bhi na chale to dono ki asli galti
# dikhti hai — koi chhupana nahi. Jawab disk par cache (scan + jeetne walon ki list
# ka hash), taake dobara koi kharcha na ho.
VD_DIR = OUT / "verdict"


def _vd_med(a):
    """client ke medv se bilkul same: sorted list ka floor(len/2) wala element."""
    s = sorted(a)
    return s[len(s) // 2] if s else 0


def llm_txt(prompt, maxtok=1400):
    """Text LLM chain: Gemini models → Pollinations (keyless, muft) → saaf error.
    'via' field me likha aata hai ke jawab kis ne diya — UI khud dikhata hai."""
    r = gem_try([GEM_MODEL] + GEM_MODEL_ALT, [{"text": prompt}], maxtok=maxtok, temperature=0.3)
    if not r.get("error"):
        r["via"] = "Gemini (" + str(r.get("model") or "?") + ") — aapki apni key"
        return r
    ge = str(r.get("error"))[:150]
    if "timed out" in ge:
        # timeout 404/503 nahi hai is liye gem_try chain nahi chalata; yahan ek
        # doosri koshish alt models se — bhaari prompt ke liye 3.8 slow ho sakta hai.
        r2 = gem_try(GEM_MODEL_ALT, [{"text": prompt}], maxtok=maxtok, temperature=0.3)
        if not r2.get("error"):
            r2["via"] = "Gemini (" + str(r2.get("model") or "?") + ") — aapki apni key (doosri koshish)"
            r2["gem_err"] = ge
            return r2
        ge += " | doosri koshish: " + str(r2.get("error"))[:120]
    u = "https://text.pollinations.ai/" + urllib.parse.quote(prompt[:3500]) + "?model=openai"
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=90) as h:
            t = h.read().decode("utf-8", "replace").strip()
        if len(t) > 30:
            return {"text": t, "via": "Pollinations text endpoint (keyless, muft — model ka naam guaranteed nahi)",
                    "gem_err": ge}
        pe = "Pollinations ka jawab khaali/bahut chhota tha"
    except Exception as e:
        pe = "Pollinations se baat nahi hui: " + str(e)[:140]
    return {"error": ge + " | " + pe}


def vd_get(sid, force=False):
    sid = re.sub(r"[^a-z0-9]", "", (sid or "").lower())[:16]
    if not sid:
        return {"error": "scan id saaf nahi"}
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"error": "scan file nahi mila"}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": "scan file padhi nahi ja saki: " + str(e)[:100]}
    meas = []
    for it in d.get("items") or []:
        v = it.get("views") or 0
        # client ke vpd()/winOf() se ek hi formula, poore exact: days na ho to 1,
        # aur jo round karke 0 ho jaaye (views bahut chhote / umr bahut zyada) wo
        # median pool me nahi gine — client bhi wahi karta hai. Dono taraf "jeetne
        # wali" ka matlab same rahe, warna filter aur verdict alag list dikhaate.
        if v > 0:
            m = int(round(v / max(1, int(it.get("days") or 1))))
            if m > 0:
                meas.append((it, m))
    if len(meas) < 6:
        return {"error": "verdict ke liye kam se kam 6 naapi gayi videos chahiye — abhi %d hain. "
                         "Scan adhoori naapi hai to pehle scan dobara chala kar naap poori karein." % len(meas)}
    med = _vd_med([m for _, m in meas])
    win = [(it, m) for it, m in meas if med > 0 and m >= 2 * med]
    if len(win) < 2:
        return {"error": "is scan me jeetne wali (median se 2×+) 2 se kam nikli (%d) — itni thod par "
                         "model ki raay banana jhooth hoga." % len(win)}
    lose = [(it, m) for it, m in meas if m < med][:6]
    key = hashlib.md5(("|".join(sorted(str(it.get("id") or "") for it, _ in win)) + "|" + str(med)).
                      encode()).hexdigest()[:12]
    VD_DIR.mkdir(exist_ok=True)
    vf = VD_DIR / (sid + "-" + key + ".json")
    if vf.exists() and not force:
        try:
            out = json.loads(vf.read_text(encoding="utf-8"))
            out["cached"] = True
            return out
        except Exception:
            pass

    def row(it, m):
        return {"id": it.get("id"), "title": (it.get("title") or "")[:80],
                "views_per_day": m, "channel": (it.get("channel") or "")[:30],
                "tags": ", ".join((it.get("tags") or [])[:5]),
                "thumbnail_text": ((it.get("ts") or {}).get("text") or "")[:70]}

    W = [row(it, m) for it, m in win[:10]]
    L = [row(it, m) for it, m in lose]
    prompt = ("A YouTube topic scan was measured honestly (views/day = views divided by age in days; "
              "thumbnail_text is OCR of the real thumbnail; tags are the creator's own). "
              "Topic: " + str(d.get("topic") or "")[:120] + ". "
              "WINNING videos here (views/day at least 2x this scan's median " + str(med) + "): "
              + json.dumps(W, ensure_ascii=False) + ". "
              "LOW videos here (views/day below that median): " + json.dumps(L, ensure_ascii=False) + ". "
              "Using ONLY this data, write in Hinglish (roman Urdu/Hindi), analyst tone, no flattery: "
              "1) patterns: 3-5 short observations on what winners share that the low ones lack "
              "(title style, tags, thumbnail text); "
              "2) per_video: for each winner id one short line — a hypothesis of why it wins (not proof); "
              "3) missing: 2-4 concrete tests the low videos could try. "
              'Never invent facts that are not in this data; if data is thin, say so in the line. '
              'Your ENTIRE reply must be one JSON object: its first character must be { and its last '
              'must be } — no headings, no tables, no markdown, no sentence before or after it. '
              'Shape: {"patterns":["..."],'
              '"per_video":{"<video id>":"..."},"missing":["..."]}')
    r = llm_txt(prompt, maxtok=4000)
    if r.get("error"):
        return {"error": "model verdict nahi de saka — " + r["error"]}
    txt = r["text"]
    parsed = None
    mch = re.search(r"\{.*\}", txt, re.S)
    if mch:
        try:
            parsed = json.loads(mch.group(0))
        except Exception:
            parsed = None
    out = {"ok": True, "sid": sid, "med": med, "n_win": len(win), "n_lose": len(meas) - len(win),
           "via": r.get("via") or "", "gem_err": r.get("gem_err") or "",
           "winners": [str(it.get("id")) for it, _ in win],
           "verdict": parsed, "raw": "" if parsed else txt,
           "note": "ye model ki raay hai — sirf is scan ke naape gaye numbers par based. "
                   "Sah-sambandh (pattern) dikha sakta hai, wajah sabit nahi karta. Jo line "
                   "numbers se confirm nahi wo andaza hai — waise hi label kiya gaya hai."}
    try:
        vf.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return out


# ---------------- style jeet (andaza classifier + asli jeet ka naap) ----------------
# Do alag cheezein, aur screen par dono alag likhi jaati hain:
#   1) style ka ANDAZA — pixel patterns se (safed zameen + kaali lines = line art,
#      teeikh flat rang = cartoon/motion graphics, asli footage = photo). Ye
#      classifier hai, guarantee nahi — isliye "theek karo" ka rasta hai.
#   2) JEET ka naap — views/day, jo har video ka asli gina hua data hai.
# Bucket naam ASCII rakhe hain (client labels khud dikhata hai) taake fix karna aasan rahe.
STY_BUCKETS = ("lineart", "dark", "photo", "flat", "unknown")


def _sty_pix(p):
    try:
        im = Image.open(p).convert("HSV").resize((64, 36))
    except Exception:
        return None
    px = list(im.getdata())
    n = len(px)
    v = [x[2] / 255.0 for x in px]
    s = [x[1] / 255.0 for x in px]
    bright = sum(v) / n
    sat = sum(s) / n
    white = sum(1 for a, b in zip(v, s) if a > 0.88 and b < 0.18) / n
    dark = sum(1 for a in v if a < 0.25) / n
    vivid = sum(1 for a, b in zip(v, s) if b > 0.45 and a > 0.35) / n
    hue = [0] * 12
    for h, b, a in px:
        if b / 255.0 > 0.35 and a / 255.0 > 0.35:
            hue[int(h / 256.0 * 12) % 12] += 1
    hues = sum(1 for x in hue if x > n * 0.02)
    if white >= 0.40 and sat < 0.22:
        return "lineart"          # whiteboard / stickman / doodle-on-white
    if dark >= 0.5 and sat < 0.3:
        return "dark"            # blackboard / night / cinematic dark
    if vivid >= 0.3 and hues <= 3:
        return "flat"            # flat cartoon / motion graphics / meme
    if vivid >= 0.3 or hues >= 5:
        return "photo"           # footage jaisa, rang-biranga
    return "unknown"


def sty_measure(sid):
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    d = json.loads(f.read_text(encoding="utf-8"))
    fix = d.get("stfix") or {}
    sty = d.get("sty") or {}
    for it in d.get("items") or []:
        vid = it.get("id")
        if not vid:
            continue
        if vid in fix:
            sty[vid] = fix[vid]
            continue
        p = it.get("thumb")
        b = _sty_pix(p) if p else None
        if b:
            sty[vid] = b
    d["sty"] = sty
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "sty": sty}


def sty_fix(sid, vid, fix):
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    if fix not in STY_BUCKETS:
        return {"err": "ya style bucket nahi"}
    d = json.loads(f.read_text(encoding="utf-8"))
    d.setdefault("stfix", {})[vid] = fix
    d.setdefault("sty", {})[vid] = fix
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


def suggest(topic, k=4):
    """YouTube ka apna suggest box (koi API key nahi) — wide search ke liye related topic."""
    try:
        u = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q="
             + urllib.parse.quote(topic))
        d = json.loads(http_get(u, timeout=12).decode("utf-8", "replace"))
        out = []
        for s in (d[1] if isinstance(d, list) and len(d) > 1 else []):
            s = (s or "").strip()
            if s and s.lower() != topic.lower() and len(s) > 3:
                out.append(s)
        return out[:k]
    except Exception:
        return []


def _merge_search(res, cap_ch, min_dur):
    """Round-robin merge + sample ki safai: ek hi channel ke 12 video poore sample ko
    ek hi channel ki aadat par le jaate the (ab ek channel se zyada se zyada cap_ch),
    aur Shorts ke thumbnails normal videos jaise count hi nahi hote (alag feed, alag
    CTR) — wo alag hain. Jo gira hai wo chhupa nahi, gin kar dikhaya jaata hai."""
    merged, seen, per, drop = [], set(), {}, {"short": 0, "same_channel": 0, "dupe": 0}
    chs = set()
    for i in range(max(len(r) for r in res)):
        for r in res:
            if i >= len(r):
                continue
            it = r[i]
            if it["id"] in seen:
                drop["dupe"] += 1
                continue
            d = it.get("fdur")
            if min_dur and d and d < min_dur:
                drop["short"] += 1
                continue
            ch = (it.get("chan") or "").strip().lower()
            if ch:
                chs.add(ch)
                if cap_ch:
                    if per.get(ch, 0) >= cap_ch:
                        drop["same_channel"] += 1
                        continue
                    per[ch] = per.get(ch, 0) + 1
            seen.add(it["id"])
            merged.append(it)
    # channel_ginti hamesha asli alag-channels ki rahe — cap dheela karne par bhi
    return merged, drop, len(chs)


def search_wide(topic, n, wide, job=None):
    """Ek search = sirf top results (ak baar me 20 tak). Wide mode me topic ke related
    suggestions se alag-alag videos laakar merge karta hoon, isliye 50 videos tak
    asli range milti hai — sirf ek hi channel ke 12 video nahi.
    User ka rule: jitni videos ka kaha, utni milni chahiye. Kam padne par chup-chaap
    top-up rounds chalte hain — (1) baaki suggestions se aur queries, (2) channel-cap
    dheela, (3) aakhir me shorts bhi. Ye sab yt-dlp search hai — koi API key/credit
    nahi lagta, is liye be-fikr barh sakte hain. Phir bhi kam mile to scan me saaf
    likha hota hai ke search ne itne hi alag diye."""
    qs = [topic]
    if wide:
        qs += suggest(topic)
    qs = qs[:6]
    per = max(6, int(math.ceil(n * (1.35 if len(qs) > 1 else 1.0) / len(qs))))
    per = min(per, 25)

    def grab(qs_, per_):
        out = []
        with cf.ThreadPoolExecutor(max_workers=min(3, len(qs_))) as ex:
            futs = [ex.submit(search_ids, q, per_) for q in qs_]
            for fu in cf.as_completed(futs):
                try:
                    out.append(list(fu.result()))
                except Exception:
                    pass
        return out

    res = grab(qs, per)
    if not res:
        raise RuntimeError("kuch nahi mila (search)")
    merged, drop, nch = _merge_search(res, TH["ch_cap"], TH["short_s"])
    if len(merged) < n:                    # round 1: baaki suggestions se aur queries
        tried = set(qs)
        more = [q for q in suggest(topic) if q not in tried][:8]
        if not more:
            # suggestions khatam — modifier variants se doosre natije. Ye bhi sirf
            # yt-dlp search hai, koi API kharcha nahi.
            more = [q for q in (topic + " full", topic + " explained", topic + " lecture",
                                topic + " urdu", topic + " 2025", topic + " tutorial") if q not in tried][:6]
        if more:
            per2 = min(25, max(per, int(math.ceil((n - len(merged)) * 1.8 / len(more)))))
            res += grab(more, per2)
            m2, d2, c2 = _merge_search(res, TH["ch_cap"], TH["short_s"])
            if len(m2) > len(merged):
                merged, drop, nch = m2, d2, c2
            drop["topup_queries"] = len(more)
    if len(merged) < n:                    # round 2: channel-cap dheela (shorts filter barkarar)
        m2, d2, c2 = _merge_search(res, 0, TH["short_s"])
        if len(m2) > len(merged):
            merged, drop, nch = m2, d2, c2
            drop["cap_relaxed"] = 1
    if len(merged) < n:                    # round 3: shorts bhi — aakhri rasta
        m2, d2, c2 = _merge_search(res, 0, 0)
        if len(m2) > len(merged):
            merged, drop, nch = m2, d2, c2
            drop["cap_relaxed"] = 1
            drop["shorts_relaxed"] = 1
            drop["relaxed"] = 1            # purana flag — UI chip isi se chalta hai
    if job:
        job["current"] = "%d videos chun liye (%d search, %d channel)" % (min(len(merged), n), len(res), nch)
        job["filt"] = {"shorts_hataaye": drop["short"], "ek_channel_zayada": drop["same_channel"],
                       "duplicate": drop["dupe"], "channel_alag": nch, "relaxed": drop.get("relaxed", 0),
                       "cap_relaxed": drop.get("cap_relaxed", 0), "shorts_relaxed": drop.get("shorts_relaxed", 0),
                       "topup_queries": drop.get("topup_queries", 0), "manga": n, "mila": len(merged)}
    return merged[:n]


def _grab(chunk):
    y = find_ytdlp()
    urls = ["https://www.youtube.com/watch?v=" + i for i in chunk]
    cmd = [y, "--no-update", "--no-warnings", "--ignore-errors", "--skip-download",
           "--print", "%(id)s\t%(view_count)s\t%(upload_date)s\t%(duration)s\t%(channel)s"] + urls
    rc, out, err = run(cmd, timeout=300)
    got = {}
    for ln in out.splitlines():
        p = ln.split("\t")
        if len(p) < 5 or not p[0]:
            continue
        up = re.sub(r"\D", "", p[2])[:8]
        d = None
        if len(up) == 8:
            try:
                d = dt.date(int(up[:4]), int(up[4:6]), int(up[6:]))
            except Exception:
                d = None
        got[p[0]] = {"views": pnum(p[1]) or 0,
                     "upload": (up[:4] + "-" + up[4:6] + "-" + up[6:]) if len(up) == 8 else "",
                     "dur": pnum(p[3]) or 0,
                     "channel": p[4],
                     "days": max(1, (dt.date.today() - d).days) if d else None}
    return got


def enrich(ids, job):
    out = {}
    chunks = [ids[i:i + CHUNK] for i in range(0, len(ids), CHUNK)]
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, got in enumerate(ex.map(_grab, chunks)):
            out.update(got)
            job["done"] = min(job["total"], job["done"] + len(chunks[i]))
            job["current"] = "views/date: " + str(job["done"]) + "/" + str(job["total"])
    # yt-dlp kabhi-kabri bot-block kar deta hai ( searches ke baad "Sign in to confirm
    # you're not a bot"). Doosra rasta: YouTube Data API — 50 id ka ek call = 1 unit,
    # free quota 10,000/day ke saamne kuch nahi. Numbers phir bhi YouTube ke hi hain.
    miss = [i for i in ids if i not in out or not out[i].get("views")]
    if len(miss) >= 5:
        job["current"] = "views: YouTube API ka doosra rasta azma raha hoon…"
        g = yt_views(miss)
        if g:
            for k, v in g.items():
                if not out.get(k) or not out[k].get("views"):
                    out[k] = v
            job["api_fill"] = len(g)
    return out


# ---------------- 1b. us video ka ASLI metadata (tags, description, chapters) ----------------
# yt-dlp -J se, ek-ek video par. Naapa gaya (24 Oct): ek video ~2.2s serial, 8 threads me
# 12 videos 5.3s = ~0.45s/video wall, yaani 50 videos ke liye ~25s — aur har video ek baar
# disk par cache (thumb_output/metac/<id>.json), dobara scan me 1 second bhi nahi lagta.
# Jo yahan dikhega wo us video par ASHI laga hua hai: koi andaaza nahi, koi generate nahi.

STOP = set("""the a an and or of to in for on with your my this that it is are was we you how
why what who when where which kya ka ki ko se me me hai ha kar ne par tak bhi hi tu tune main
tum your video videos short shorts official full hd 4k live new 2024 2025 2026""".split())


def toks(s):
    """Title/tags/description ke shabd (roman+urdu), stopwords chhod kar."""
    return [w for w in re.findall(r"[a-z0-9\u0600-\u06ff\u0900-\u097f]{3,}", (s or "").lower())
            if w not in STOP]


def meta_of(vid):
    """Ek video ka ASLI metadata + disk cache. v2: chapters ka waqt yt-dlp ke `start_time`
    (seconds) se padha jaata hai — `start` naam ka koi field hota hi nahi, isliye har chapter
    0:00 par aa raha tha. v3: `ts` — video ke chhapne ka poora waqt (epoch seconds,
    `timestamp` field se). Ye channel ki flat listing me KABHI nahi aata (na /videos tab
    me, na uploads playlist me — 25 Oct ko test kar ke dekha), sirf us video ki apni
    metadata me hota hai. Is liye ghari ka pattern sirf naapi gayi videos par banta hai.
    Purana cache (bina v2/v3 ke) khud discard ho kar dobara aata hai."""
    if not re.fullmatch(r"[0-9A-Za-z_-]{11}", vid or ""):
        return {"err": "video id theek nahi"}
    f = META_DIR / (vid + ".json")
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("v") == 3:
                return d
        except Exception:
            pass
    y = find_ytdlp()
    # Bot-check hamesha ek hi client par padta hai — tv/android/ios clients ko aksel
    # allow mil jaata hai. Download wale raste par ye chain pehle se thi (isliye OCR
    # chalta raha); ab metadata par bhi wahi chain — default fail ho to client badal
    # kar dobara. cookies.txt rakha ho to run() usay apne aap laga deta hai.
    rc = out = err = None
    for cargs in (None, "youtube:player_client=tv", "youtube:player_client=android",
                  "youtube:player_client=ios"):
        cmd = [y, "-J", "--no-download", "--no-warnings"]
        if cargs:
            cmd += ["--extractor-args", cargs]
        rc, out, err = run(cmd + ["https://www.youtube.com/watch?v=" + vid], timeout=120)
        if rc == 0 and (out or "").strip():
            break
    if rc != 0 or not (out or "").strip():
        e = re.sub(r"\s+", " ", (err or ""))[:140]
        hint = ""
        if "not a bot" in e.lower() or "sign in to confirm" in e.lower():
            hint = (" — YouTube ne is IP ko bot shak kar rok diya (ye aap ke tool ki kharabi nahi, "
                    "YouTube ka challenge hai). Thori der baad dobara try karein; ya browser "
                    "extension \"Get cookies.txt LOCALLY\" se cookies export kar ke ClickLab "
                    "folder me cookies.txt file rakh dein — tool apne aap wo cookies use karega.")
        return {"err": "metadata nahi mila: " + e + hint}
    try:
        j = json.loads(out)
    except Exception:
        return {"err": "metadata parse nahi hua"}
    caps = len(j.get("automatic_captions") or {}) + len(j.get("subtitles") or {})
    m = {"v": 3, "id": vid, "title": j.get("title") or "", "ch": j.get("channel") or "",
         "tags": [str(t).strip() for t in (j.get("tags") or []) if str(t).strip()][:40],
         "desc": (j.get("description") or "")[:4000], "likes": j.get("like_count"),
         "cmts": j.get("comment_count"), "subs": j.get("channel_follower_count"),
         "views": j.get("view_count"), "up": j.get("upload_date") or "",
         "ts": j.get("timestamp"),
         "dur": j.get("duration") or 0, "cat": (j.get("categories") or [None])[0],
         "chaps": [{"t": int(round(float(c.get("start_time", c.get("start", 0)) or 0))), "s": str(c.get("title") or "")[:70]}
                   for c in (j.get("chapters") or [])][:24],
         "cc": caps, "rate": j.get("average_rating"), "age": j.get("age_restriction") or "",
         "got": dt.datetime.now().isoformat(timespec="seconds")}
    try:
        META_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return m


def seo_check(title, m):
    """Listing (title+tags+description) ki jaanch — sirf ASLI data se, jo us video par laga hai.
    Score 0-100 = kitni jaancheen poori hui. Ye CTR ka naap nahi, metadata ki safai ka naap hai."""
    m = m or {}
    t = (title or m.get("title") or "").strip()
    tg = m.get("tags") or []
    de = m.get("desc") or ""
    tw = set(toks(t))
    tgw = set()
    for x in tg:
        tgw |= set(toks(x))
    dew = set(toks(de))
    hit = sorted(w for w in tw if w in tgw or w in dew)
    miss = sorted(w for w in tw if w not in tgw and w not in dew)
    hh = len(re.findall(r"(?:^|\s)#\w{3,}", de))
    lk = len(re.findall(r"https?://", de))
    ck = []

    def add(state, t_, n_):
        ck.append({"s": state, "t": t_, "n": n_})

    n = len(tg)
    if n == 0:
        add("bad", "Tags: is video par koi tag nahi laga",
            "YouTube kehta hai tags ka asar ab bahut kam hai — par jo channel khud nahi lagata, "
            "wo apni listing ki baaki cheezon par bhi dhyan nahi deta.")
    else:
        add("ok", "Tags: " + str(n) + " ASLI tags lage hue hain",
            "ye poore ke poore wahi hain jo us channel ne lagaye the — koi generate nahi kiye.")
    if tw:
        r = round(len(hit) * 100 / len(tw))
        add("ok" if r >= 50 else "warn", "Title ke " + str(len(tw)) + " shabdon me se " + str(len(hit)) +
            " (" + str(r) + "%) tags/description me maujood",
            "jo shabd title me hain aur kahin aur nahi, wo YouTube ko topic samajhne me sabse tez hote hain." +
            (" Adhore: " + ", ".join(miss[:10]) if miss else ""))
    else:
        add("warn", "Title se koi shabd nikaala hi nahi ja saka", "title sirf numbers/short words ka hai.")
    dl = len(de)
    if dl < 40:
        add("bad", "Description sirf " + str(dl) + " characters ki hai",
            "description ke 2-3 line search aur suggested dono me kaam aate hain.")
    elif dl < 200:
        add("warn", "Description " + str(dl) + " characters — chhoti hai", "pehle 150 characters sabse zaroori hain.")
    else:
        add("ok", "Description " + str(dl) + " characters ki hai", "poori description neeche di gayi hai — wahi asli hai.")
    if tw and dew:
        o = sorted(w for w in tw if w in dew)
        add("ok" if len(o) >= 2 else "warn", "Description me title ke " + str(len(o)) + " shabd dobara hain",
            "pehle 200 characters me topic dohrana ranking me madad karta hai.")
    if hh > 5:
        add("warn", "Description me " + str(hh) + " hashtags", "3 se zyada hashtags spam maane jaate hain.")
    else:
        add("ok", "Hashtags: " + str(hh), "0-3 theek; ye description ke neeche clickable hote hain.")
    if (m.get("chaps") or []):
        add("ok", "Chapters: " + str(len(m["chaps"])) + " bane hue hain",
            "chapters = video ki structure, aur description me timestamps ka istemaal.")
    elif (m.get("dur") or 0) > 300:
        add("warn", "Chapters nahi bane (video " + str(int(m["dur"]) // 60) + " minute ki hai)",
            "lambi video me chapters viewer ko roke rakhte hain — retention ka sabse sasta tareeka.")
    if lk:
        add("ok", "Description me " + str(lk) + " link (affiliate/related)", "links description me kaam karte hain.")
    tl = len(t)
    add("ok" if tl <= 70 else "warn", "Title ki lambai " + str(tl) + " characters",
        "70 ke baad YouTube title kaat deta hai (Title Lab me asli cutting dikhti hai).")
    tot = len(ck)
    sc = int(round(100 * sum(1.0 if c["s"] == "ok" else 0.4 if c["s"] == "warn" else 0.0 for c in ck) / tot))
    return {"ls": sc, "chk": ck, "hit": hit[:14], "miss": miss[:14], "nt": len(tg), "dl": len(de),
            "hh": hh, "lk": lk}


def eng_of(m):
    """Asli ginti se engagement. Yeh koi andaaza nahi: likes aur comments YouTube par
    public counts hain, bas views se taqseem kiye gaye hain."""
    v = m.get("views") or 0
    lk = m.get("likes")
    cm = m.get("cmts") or 0
    if not v:
        return None
    e = {"views": v, "likes": lk, "cmts": cm}
    e["lr"] = round(lk * 100.0 / v, 3) if lk else None
    e["cr"] = round(cm * 100.0 / v, 3) if cm else None
    if lk:
        e["er"] = round((lk + cm * 4) * 100.0 / v, 3)   # comments ko 4x wazan (convention)
    return e


def own_load():
    try:
        return json.loads(OWN_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def own_set(vid, ctr, ret, extra=""):
    """Apni video ka ASLI CTR/retention (YouTube Studio se) yahan save hota hai — YouTube wo
    data sirf channel ke malik ko deta hai, isliye bahar se laane ka koi rasta nahi."""
    if not re.fullmatch(r"[0-9A-Za-z_-]{11}", vid or ""):
        return {"error": "video id theek nahi"}
    d = own_load()
    e = d.get(vid) or {}
    if ctr not in (None, ""):
        try:
            e["ctr"] = float(ctr)
        except Exception:
            return {"error": "CTR number me daalo (jaise 4.7)"}
    if ret not in (None, ""):
        try:
            e["ret"] = float(ret)
        except Exception:
            return {"error": "retention number me daalo (jaise 42)"}
    if extra:
        e["note"] = str(extra)[:200]
    e["at"] = dt.datetime.now().isoformat(timespec="seconds")
    d[vid] = e
    try:
        OWN_F.parent.mkdir(parents=True, exist_ok=True)
        OWN_F.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e2:
        return {"error": "save nahi hua: " + str(e2)[:120]}
    return {"ok": True, "vid": vid, "own": e}


# ---------------- 2. thumbnails ----------------

def get_thumb(vid):
    """maxres (asli 16:9) milte hi wahi; warna hq. Returns (path, kind)."""
    p = THUMB_DIR / (vid + ".jpg")
    meta = THUMB_DIR / (vid + ".kind")
    if p.exists() and meta.exists():
        return (p, meta.read_text(encoding="utf-8"))
    for kind in ("maxresdefault", "hqdefault"):
        try:
            b = http_get("https://i.ytimg.com/vi/" + vid + "/" + kind + ".jpg", timeout=25)
        except Exception:
            continue
        if len(b) < 1500:
            continue
        p.write_bytes(b)
        meta.write_text(kind, encoding="utf-8")
        return (p, kind)
    return (None, None)


# ---------------- 3. image analysis ----------------

def analyse(path):
    if Image is None:
        return {"err": "Pillow nahi hai — pip install pillow"}
    im = Image.open(path)
    im.load()
    W, H = im.size
    im = im.convert("RGB")
    sm = im.resize((120, max(1, int(120 * H / W))))
    SW, SH = sm.size
    px = sm.load()
    L, sat, hue = [], [], []
    for y in range(SH):
        for x in range(SW):
            c = px[x, y]
            L.append(rlum(c))
            hh, ss, vv = colorsys.rgb_to_hsv(*[v / 255.0 for v in c])
            sat.append(ss)
            hue.append(hh)
    cols = []
    try:
        q = im.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette() or []
        cnt = Counter(list(q.getdata())).most_common(6)
        tot = sum(n for _, n in cnt) or 1
        for i, n in cnt:
            hx = "#%02x%02x%02x" % (pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2])
            cols.append({"hex": hx, "pct": round(n * 100 / tot), "fam": fam_of(hx)})
    except Exception:
        cols = []
    # ---- edges: bheed, composition, focus, sharpness ----
    try:
        eg = im.convert("L").filter(ImageFilter.FIND_EDGES).resize((SW, SH))
        E = eg.load()
        em = [[E[x, y] for x in range(SW)] for y in range(SH)]
        clutter = round(mean([v for r in em for v in r]) / 255.0 * 100)
    except Exception:
        em, clutter = None, None
    comp = {}
    if em:
        tot = sum(sum(r) for r in em) or 1
        sx = sum(x * sum(em[y][x] for y in range(SH)) for x in range(SW)) / tot / SW
        sy = sum(y * sum(em[y][x] for x in range(SW)) for y in range(SH)) / tot / SH
        dmin = min(math.hypot(sx - tx, sy - ty) for tx in (1 / 3.0, 2 / 3.0) for ty in (1 / 3.0, 2 / 3.0))
        left = sum(sum(r[:SW // 2]) for r in em)
        core = sum(sum(em[y][SW // 4:SW - SW // 4]) for y in range(SH // 4, SH - SH // 4))
        bot = sum(sum(r) for r in em[int(SH * 0.82):])
        badge = sum(sum(r[int(SW * 0.72):]) for r in em[int(SH * 0.80):])
        comp = {"cog": [round(sx, 3), round(sy, 3)],
                "thirds": round(1.0 - min(1.0, dmin / 0.47), 3),
                "lr": round((left * 2 / tot) - 1.0, 3),
                "core": round(core * 100 / tot),
                "lowrow": round(bot * 100 / tot),
                "badge": round(badge * 100 / tot)}
    sharp = None
    try:
        gg = im.convert("L").resize((400, max(1, int(400 * H / W))))
        lp = gg.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128))
        lv = [v - 128 for v in lp.getdata()]
        gm = mean(lv)
        sharp = round(sum((v - gm) ** 2 for v in lv) / max(1, len(lv)), 1)
    except Exception:
        pass
    # ---- asli attention (spectral-residual saliency, Hou & Zhang 2007) ----
    # Edge-centroid se behtar: ye wahi jagah dikhata hai jahan aankh pehle jaati hai.
    sal = _saliency(im)

    # ---- rang ka taap-mizaaj (warm/cool) aur subject ka ubhaar ----
    chrom = warm = cool = 0
    for s, h in zip(sat, hue):
        if s < 0.18:
            continue
        chrom += 1
        if h < 0.19 or h >= 0.90:
            warm += 1
        else:
            cool += 1
    ch = max(1, chrom)
    # subject box ka ANDAAZA (rang + edge) — ye sirf tab dikhega jab OCR ke text boxes aur
    # YuNet ke face boxes na milen (scan me wo mil jaate hain aur isko replace kar dete
    # hain). Saliency ka blob yahan se isliye hataya gaya: apne hi 102 thumbnails par
    # uska "subject" face-box se sirf 7/38 baar mel khata tha.
    subj = None
    if em and cols:
        try:
            dom = max(cols, key=lambda c: c["pct"])["hex"]
            dr, dg, db = int(dom[1:3], 16), int(dom[3:5], 16), int(dom[5:7], 16)
            sc = []
            for y in range(SH):
                row = []
                for x in range(SW):
                    c = px[x, y]
                    dd = abs(c[0] - dr) + abs(c[1] - dg) + abs(c[2] - db)
                    row.append(dd / 3.0 * 0.65 + em[y][x] * 0.35 + (12 - abs(x - SW // 2) - abs(y - SH // 2)))
                sc.append(row)
            flat = sorted(v for r in sc for v in r)
            thr = flat[int(len(flat) * 0.78)]
            xs = [x for y in range(SH) for x in range(SW) if sc[y][x] >= thr]
            ys = [y for y in range(SH) for x in range(SW) if sc[y][x] >= thr]
            if xs and ys:
                subj = {"x": round(min(xs) / SW, 3), "y": round(min(ys) / SH, 3),
                        "w": round((max(xs) - min(xs)) / SW, 3), "h": round((max(ys) - min(ys)) / SH, 3)}
        except Exception:
            subj = None
    mL = mean(L)
    varL = sum((x - mL) ** 2 for x in L) / max(1, len(L))
    return {"w": W, "h": H, "bright": round(mL, 3), "contrast": round(math.sqrt(max(0.0, varL)), 3),
        "dyn": round(pctl(L, 0.95) - pctl(L, 0.05), 3), "sat": round(mean(sat), 3),
        "colors": cols, "clutter": clutter, "sharp": sharp,
        "blur": (sharp is not None and sharp < 60), "comp": comp, "subj": subj,
        "subj_src": ("rang+edge ka andaaza" if subj else None),
        # saliency map: soch ke liye hai, score me nahi. Apne data par validate hua:
        # subject dhoondhne me fail (7/38) — isliye "sal" score ka hissa nahi hai.
        "sal": (sal["m"] if sal else None), "sal_validated": False,
        "chrom_pct": round(chrom * 100 / (SW * SH)),
        "warm": round(warm * 100 / ch), "cool": round(cool * 100 / ch)}


def _saliency(im):
    """Spectral-residual saliency (Hou & Zhang 2007) — asli attention map, koi AI model
    nahi chahiye, FFT se banta hai. Deta hai: attention ka centroid, rule-of-thirds ka
    sach, "focus" (ek subject hai ya bheed), 3x3 grid ka mass, aur subject ka blob."""
    if np is None:
        return None
    try:
        N = 64
        g = np.asarray(im.convert("L").resize((N, N)), dtype=np.float64) + 1.0
        F = np.fft.fft2(g)
        A = np.log(np.abs(F) + 1e-8)
        P = np.angle(F)
        avg = np.zeros_like(A)
        for i in range(-1, 2):
            for j in range(-1, 2):
                avg += np.roll(np.roll(A, i, 0), j, 1) / 9.0
        R = A - avg
        S = np.abs(np.fft.ifft2((R + 1e-8) * np.exp(1j * P))) ** 2
        sm = np.zeros_like(S)                      # paper ka 3x3 average filter h
        for i in range(-1, 2):
            for j in range(-1, 2):
                sm += np.roll(np.roll(S, i, 0), j, 1) / 9.0
        # NOTE: yahan log NAHI lagata. Paper me log spectrum par lagta hai (jo upar ho
        # chuka hai); map par log lagane se peak dab jaati thi — 102 thumbnails par har
        # image ki concentration 0.147 (yaani bilkul uniform) aa rahi thi, ab farq
        # dikhta hai (0.13 se 0.46 tak).
        lo, hi = float(sm.min()), float(sm.max())
        if hi - lo <= 1e-9:
            return None
        sm = (sm - lo) / (hi - lo)
        tot = float(sm.sum()) or 1.0
        ys, xs = np.mgrid[0:N, 0:N]
        cx = float((sm * xs).sum() / tot) / N
        cy = float((sm * ys).sum() / tot) / N
        dmin = min(math.hypot(cx - tx, cy - ty) for tx in (1 / 3.0, 2 / 3.0) for ty in (1 / 3.0, 2 / 3.0))
        # conc: sabse tez 10% pixels me duniya ka kitna hissa simta hai — "ek clear subject
        # hai ya bheed" ka seedha, naapne-layak jawaab (entropy se zyada farq dikhta hai)
        flat = np.sort(sm.ravel())[::-1]
        kk = max(1, int(flat.size * 0.10))
        conc = round(float(flat[:kk].sum()) / tot, 3)
        G = 4
        cells = []
        for gy in range(G):
            for gx in range(G):
                blk = sm[gy * (N // G):(gy + 1) * (N // G), gx * (N // G):(gx + 1) * (N // G)]
                cells.append(round(float(blk.sum()) / tot, 4))
        ssum = sum(cells) or 1.0
        p = [c / ssum for c in cells]
        ent = -sum(x * math.log(x) for x in p if x > 0) / math.log(len(p))
        core = sum(cells[i] for i in (5, 6, 9, 10))          # bilkul beech ke 4 cell
        blob = None
        blob_pct = 0.0
        try:
            thr = max(0.55, float(np.percentile(sm, 92)))
            mask = (sm >= thr).astype(np.uint8)
            if cv2 is not None:
                n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
                if n and n > 1:
                    i = max(range(1, n), key=lambda kk2: stats[kk2, cv2.CC_STAT_AREA])
                    x, y, w, h, a = stats[i]
                    if a >= 8:
                        blob = {"x": round(float(x) / N, 3), "y": round(float(y) / N, 3),
                                "w": round(float(w) / N, 3), "h": round(float(h) / N, 3)}
                        blob_pct = round(float(a) / float(N * N) * 100, 1)
        except Exception:
            pass
        return {"subj": blob, "blob_pct": blob_pct,
                "m": {"cog": [round(cx, 3), round(cy, 3)],
                      "thirds": round(1.0 - min(1.0, dmin / 0.47), 3),
                      "conc": conc, "core": round(core * 100, 1), "entropy": round(ent, 3),
                      "peak": round(float(sm.max()), 3)}}
    except Exception:
        return None


def faces_of(path):
    """Chehra kitna bada hai, kahan hai, aur kitna saamne ka hai — CTR ke levers.
    v2: pehle YuNet (ONNX) — profile/ghuma hua/chhota chehra bhi pakadta hai, box tight
    deta hai; 2 scale par chalakar chhote chehre bhi gin-ta hai. Model na ho to Haar.
    Output: normalized box + area% + confidence + yaw/roll (kitna saamne hai)."""
    if cv2 is None or Image is None:
        return []
    im = Image.open(path).convert("RGB")
    W, H = im.size
    if max(W, H) < 64:
        return []
    arr = np.asarray(im, dtype=np.uint8)
    got = []
    yd = get_yunet()
    if yd is not None:
        for sc in (1.0, 1.6):
            w = max(32, min(1600, int(W * sc)))
            h = max(32, int(H * (w / float(W))))
            if (w, h) != (W, H):
                g = cv2.resize(arr, (w, h), interpolation=cv2.INTER_CUBIC if sc > 1 else cv2.INTER_AREA)
            else:
                g = arr
            try:
                with _FACE_LK:
                    yd.setInputSize((w, h))
                    _, fs = yd.detect(g)
            except Exception:
                continue
            if fs is None:
                continue
            for f in fs:
                x, y, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
                if fw < 8 or fh < 8:
                    continue
                conf = float(f[14]) if len(f) > 14 else 0.0
                yaw = float(f[15]) if len(f) > 15 else 0.0
                roll = float(f[16]) if len(f) > 16 else 0.0
                got.append({"x": x / w, "y": y / h, "w": fw / w, "h": fh / h,
                            "area": round(fw * fh * 100.0 / (w * h), 2),
                            "conf": round(conf, 2), "yaw": round(yaw, 1), "roll": round(roll, 1),
                            "frontal": bool(abs(yaw) <= 30 and abs(roll) <= 30)})
        got = _nms_faces(got)
    if not got:
        with _FACE_LK:
            got = _faces_haar(arr, W, H)
    got.sort(key=lambda d: -d["area"])
    return got[:6]


def _nms_faces(got, thr=0.35):
    """Do scale par ek hi chehra do baar na gine — IoU se duplicate hatana."""
    out = []
    for c in sorted(got, key=lambda d: -d["area"]):
        dup = False
        for k in out:
            ax = max(c["x"], k["x"]); ay = max(c["y"], k["y"])
            bx = min(c["x"] + c["w"], k["x"] + k["w"]); by = min(c["y"] + c["h"], k["y"] + k["h"])
            if bx <= ax or by <= ay:
                continue
            inter = (bx - ax) * (by - ay)
            union = c["w"] * c["h"] + k["w"] * k["h"] - inter
            if union > 0 and inter / union > thr:
                dup = True
                if c["area"] > k["area"]:
                    k.update(c)
                break
        if not dup:
            out.append(dict(c))
    return out


FACE_CLS = None


def _faces_haar(arr, W, H):
    """Purana rasta — sirf tab jab YuNet model na mil sake."""
    global FACE_CLS
    if cv2 is None:
        return []
    if FACE_CLS is None:
        try:
            FACE_CLS = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        except Exception:
            FACE_CLS = False
    if not FACE_CLS:
        return []
    try:
        sc = 640.0 / max(W, 1)
        g = cv2.resize(arr, (max(1, int(W * sc)), max(1, int(H * sc)))) if sc < 1 else arr
        f = FACE_CLS.detectMultiScale(g, 1.15, 5, minSize=(34, 34))
    except Exception:
        return []
    out = []
    for (x, y, w, h) in list(f)[:6]:
        out.append({"x": round(x / g.shape[1], 3), "y": round(y / g.shape[0], 3),
                    "w": round(w / g.shape[1], 3), "h": round(h / g.shape[0], 3),
                    "area": round(w * h * 100.0 / (g.shape[0] * g.shape[1]), 2),
                    "conf": 0.0, "yaw": 0.0, "roll": 0.0, "frontal": True, "haar": True})
    return out



def ocr_words(path, scale_to=None, gem_ok=None):
    """v3: Gemini OCR on (aur key ho) to pehle WO — padhai behtar aur local hisaab
    zero (GPU na chahiye). Wo fail ho ya jawaab na de → RapidOCR (PP-OCRv4) —
    bada/stylized thumbnail text Tesseract se saaf padhta hai (naapa: "HOW TO SEE A
    BLACK" asli line, Tesseract 9 tukde). RapidOCR kuch na de to Tesseract wala
    purana rasta. scale_to = itni chaudi karke padhna — 320px = YouTube ke asli
    browse size par "kaun padh sakta hai" ka test. gem_ok=None → khud faisla
    (setting + key + speed-batta); ocr_cached apna faisla bhejta hai."""
    if Image is None:
        return None
    if gem_ok is None:
        gem_ok = bool(OCR_GEM and gem_keys()) and not _gem_ocr_limited()
    if gem_ok:
        g = gem_ocr(path, scale_to)
        if g is not None:
            return g
    if cv2 is not None and np is not None and get_rapid() is not None:
        try:
            im = Image.open(path).convert("RGB")
            im.load()
            arr = cv2.cvtColor(np.asarray(im, dtype=np.uint8), cv2.COLOR_RGB2BGR)
            got = _rapid_words(arr, scale_to)
            if got:
                return got
        except Exception:
            pass
    return ocr_words_tess(path, scale_to)


def ocr_words_tess(path, scale_to=None):
    """Purana Tesseract rasta — fallback. scale_to = image ko itne px chaudi karke padho."""
    t = find_tesseract()
    if not t or Image is None:
        return None
    src = Image.open(path)
    src.load()
    w, h = src.size
    k = 2
    if scale_to:
        w = int(scale_to)
        h = max(1, int(scale_to * h / src.size[0]))
        k = 3
    if max(w, h) * k > MAX_OCR_SIDE:
        k = max(1, MAX_OCR_SIDE // max(w, h))
    img = src.convert("RGB")
    if (w, h) != src.size:
        img = img.resize((w, h), Image.LANCZOS)
    if k > 1:
        img = img.resize((w * k, h * k), Image.LANCZOS)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    stem = TMP_DIR / ("ocr_" + hashlib.md5((str(path) + "|" + str(scale_to or "")).encode()).hexdigest()[:12])
    tp = str(stem) + ".png"
    img.save(tp, "PNG")
    best = []
    for psm in ("11", "7", "3"):
        rc, out, err = run([t, tp, str(stem), "--psm", psm, "tsv"], timeout=180)
        tf = Path(str(stem) + ".tsv")
        if not tf.exists():
            continue
        words = []
        for ln in tf.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            c = ln.split("\t")
            if len(c) < 12:
                continue
            conf = pnum(c[10]) or 0
            txt = c[11].strip()
            # OCR ka kachra (ek letter, sirf nishani, kam confidence) gin-tantr ko bigaadta hai
            if not txt or conf < 45 or len(txt) < 2 or not re.search(r"[0-9A-Za-z]", txt):
                continue
            x, y, ww, hh = (pnum(c[i]) or 0 for i in (6, 7, 8, 9))
            words.append({"t": txt, "x": x // k, "y": y // k, "w": ww // k, "h": hh // k, "conf": conf})
        try:
            tf.unlink()
        except Exception:
            pass
        if len(words) > len(best):
            best = words
        if len(words) >= 2:
            break
    try:
        Path(tp).unlink()
    except Exception:
        pass
    return best


# --- Gemini vision OCR (28 Oct): machine par kuch chalta hi nahi ---
# RapidOCR/Tesseract CPU par chalte hain (GPU ki zaroorat nahi) magar ye tool ka sabse
# bhaari local kaam hai — kamzor/dost ki machine par slow, aur stylized text ke tukde
# karta hai. OCR_GEM on (default) aur key mojood ho to OCR Gemini ke vision model se
# hoti hai: padhai behtar, local hisaab zero. Badla: key ki free-tier quota lagti hai
# (~500 token/tasveer) — is liye speed-batta mojood hai: 10 minute me 60 se zyada
# Gemini-OCR calls ho jayein (bada channel-scan) to baaki calls apne aap local par.
OCR_GEM = True
try:
    OCR_GEM = (HERE / "ocrmode.txt").read_text(encoding="utf-8").strip() != "0"
except Exception:
    pass
_GEM_OCR_TS = []
_GEM_OCR_LK = threading.Lock()
_GEM_OCR_FAIL = [0]   # lagataar Gemini-OCR khamiyan (hang/503/limit)
_GEM_OCR_CUT = [0.0]  # is waqt tak Gemini OCR chhuka — seedha local engine


def ocr_gem_set(on):
    global OCR_GEM
    OCR_GEM = bool(on)
    try:
        (HERE / "ocrmode.txt").write_text("1" if OCR_GEM else "0", encoding="utf-8")
    except Exception:
        pass
    return {"ok": True, "on": OCR_GEM}


def _gem_ocr_limited():
    """10 minute ki khirki me 60 se zyada Gemini-OCR calls = bade scan ka bojh — uske
    baad call apne aap local engine par jaati hai (free-tier saari jaldi khatam na ho).
    Isi khidki me lagataar 3 Gemini-OCR fail (hang/503/limit) ka matlab model atka hai —
    10 minute ke liye seedha local engine, taake har frame par 45-45 second timeout na
    lage. Camera/kaam rukta nahi, padhai ka engine badalta hai — ye cmd par bhi likhta hai."""
    now = time.time()
    with _GEM_OCR_LK:
        if now < _GEM_OCR_CUT[0]:
            return True
        _GEM_OCR_TS[:] = [t for t in _GEM_OCR_TS if now - t < 600]
        if len(_GEM_OCR_TS) >= 60:
            return True
        _GEM_OCR_TS.append(now)
    return False


def gem_ocr(path, scale_to=None):
    """OCR Gemini ke vision model se (3.5/3.8-flash chain, pool keys). Model se boxes
    us ke 0-999 relative coordinates me maange jaate hain (Gemini ki apni grounding
    hadd hai — pixels maangne se galat aate hain) aur wapas pixel space me badal diye
    jaate hain. Return wahi word-list jo local engine deta hai (t,x,y,w,h,conf —
    scale_to space me). None = koshish nakam → caller local par chala jaaye."""
    if Image is None or not gem_keys():
        return None
    try:
        src = Image.open(path)
        src.load()
        w0, h0 = src.size
        if scale_to:
            w = int(scale_to)
            h = max(1, int(scale_to * h0 / w0))
        else:
            w, h = w0, h0
        img = src.convert("RGB")
        if (w, h) != src.size:
            img = img.resize((w, h), Image.LANCZOS)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        stem = TMP_DIR / ("gemocr_" + hashlib.md5((str(path) + "|" + str(scale_to or "") + "|" +
                                                   str(int(time.time()) // 3600)).encode()).hexdigest()[:12])
        jp = str(stem) + ".jpg"
        img.save(jp, "JPEG", quality=88)
        with open(jp, "rb") as jf:
            b64 = base64.b64encode(jf.read()).decode("ascii")
        try:
            Path(jp).unlink()
        except Exception:
            pass
    except Exception:
        return None
    ask = ("Ye ek YouTube thumbnail hai (tasveer ki chaui " + str(w) + " pixel, oonchai " + str(h) +
           " pixel). IS TASVEER MEIN LIKHE HAR shabd/number ko lafz lafz nikalo — chhota, "
           "stylized, 3D, rang-biranga, outline wala text bhi. Poora jawab SIRF ek JSON "
           'object hai: {"words":[{"t":"lafz","x":N,"y":N,"w":N,"h":N,"conf":N}]} — '
           "x,y = lafz ke box ka upar-bayan kone, w,h = box ki chaui/oonchai. Ye numbers "
           "0-999 ke RELATIVE coordinates hain (0 = tasveer ka bayan/ooncha kinara, 999 = "
           "daayen/neeche ka kinara), pixel nahi. conf = 0-100 me apni pakki soch. Ek lafz "
           'ki ek entry. Tasveer mein bilkul text na ho to {"words":[]}. Sirf wo text jo '
           "tasveer MEIN LIKHA HAI — scene ki cheezon/objects ko text na samjho.")
    out = None
    for _try in (0, 1):
        a2 = ask if _try == 0 else (ask + " PICHLI BAAR jawab kharab aaya tha — is baar SIRF "
                                      "JSON bhejo, usse pehle/baad ek lafz bhi nahi.")
        r = gem_try([GEM_MODEL] + GEM_MODEL_ALT,
                    [{"text": a2}, {"inlineData": {"mimeType": "image/jpeg", "data": b64}}],
                    maxtok=2500, temperature=0.1, timeout=25)
        if r.get("error"):
            with _GEM_OCR_LK:
                _GEM_OCR_FAIL[0] += 1
                if _GEM_OCR_FAIL[0] >= 3 and time.time() >= _GEM_OCR_CUT[0]:
                    _GEM_OCR_CUT[0] = time.time() + 600
                    _log("gem-ocr: lagataar %d khamiyan (%s) — 10 minute ke liye padhai local "
                         "engine (RapidOCR) se hogi; frame ka kaam rukega nahi" % (_GEM_OCR_FAIL[0], str(r.get("error"))[:80]))
            return None
        txt = (r.get("text") or "").strip()
        i, j = txt.find("{"), txt.rfind("}")
        if i < 0 or j <= i:
            continue  # jawab me JSON hi nahi — ek baar phir maango
        try:
            jso = json.loads(txt[i:j + 1])
        except Exception:
            continue
        out = []
        for wd in (jso.get("words") or [])[:80]:
            if not isinstance(wd, dict):
                continue
            t = str(wd.get("t") or "").strip()
            try:
                conf = float(wd.get("conf"))
            except Exception:
                conf = 0
            if not t or conf < 45 or len(t) < 2 or not re.search(r"[0-9A-Za-z]", t):
                continue
            try:
                rx, ry = float(wd.get("x")), float(wd.get("y"))
                rw_, rh_ = float(wd.get("w")), float(wd.get("h"))
            except Exception:
                continue
            if rw_ < 0 or rh_ < 0:
                continue
            x = max(0, min(int(rx * w / 1000.0), w - 2))
            y = max(0, min(int(ry * h / 1000.0), h - 2))
            ww = min(int(rw_ * w / 1000.0), w - x)
            hh = min(int(rh_ * h / 1000.0), h - y)
            if ww < 2 or hh < 2:
                continue
            out.append({"t": t, "x": x, "y": y, "w": ww, "h": hh, "conf": max(0, min(100, int(conf)))})
        break
    return out


def _ocr_ck(path, scale_to, eng):
    try:
        st = Path(path).stat()
        return hashlib.md5((str(Path(path).resolve()) + "|" + str(scale_to or "") + "|" + eng +
                           "|" + str(int(st.st_mtime)) + "|" + str(st.st_size)).encode()).hexdigest()[:16]
    except Exception:
        return None


def ocr_cached(path, scale_to=None):
    """OCR sabse mehnga kaam hai — ek hi file dobara na padhein. Engine ka naam cache key
    me hai: Gemini, RapidOCR aur Tesseract ka result ek dusre ke upar na baithein. Gemini
    OCR on (aur key) ho to pehle wahi; wo nakam ho to local result local key par cache
    hota hai — speed-batte ne bade scan ko pehle hi local par mod diya hota hai."""
    eng = "rapid" if (cv2 is not None and get_rapid() is not None) else "tess"
    gem_on = bool(OCR_GEM and gem_keys()) and not _gem_ocr_limited()
    if gem_on:
        eng = "gem"
    key = _ocr_ck(path, scale_to, eng)
    if key is None:
        return ocr_words(path, scale_to, gem_ok=gem_on)
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    f = OCR_DIR / (key + ".json")
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    if gem_on:
        w = gem_ocr(path, scale_to)
        if w is not None:
            f.write_text(json.dumps(w, ensure_ascii=False), encoding="utf-8")
            return w
        eng = "rapid" if (cv2 is not None and get_rapid() is not None) else "tess"
        key2 = _ocr_ck(path, scale_to, eng)
        if key2:
            f = OCR_DIR / (key2 + ".json")
            if f.exists():
                try:
                    return json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    pass
    w = ocr_words(path, scale_to, gem_ok=False)
    if w is not None:
        f.write_text(json.dumps(w, ensure_ascii=False), encoding="utf-8")
    return w


def _blocks(words):
    """Chhote-bhure OCR shabdon ko lines me, aur lines ko blocks me badal do —
    asli thumbnail ek do text blocks hota hai, alag-alag word nahi."""
    ws = sorted(words, key=lambda w: (w["y"] + w["h"] / 2.0, w["x"]))
    lines = []
    for wd in ws:
        cy = wd["y"] + wd["h"] / 2.0
        hit = None
        for ln in lines:
            if abs(ln["cy"] - cy) <= max(8, ln["h"] * 0.55):
                hit = ln
                break
        if hit is None:
            lines.append({"cy": cy, "h": wd["h"], "ws": [wd]})
        else:
            hit["ws"].append(wd)
            hit["h"] = max(hit["h"], wd["h"])
    out = []
    for ln in lines:
        cur = None
        for wd in sorted(ln["ws"], key=lambda w: w["x"]):
            if cur is not None and wd["x"] - (cur["x"] + cur["w"]) <= max(10, wd["h"] * 1.2):
                cur["w"] = wd["x"] + wd["w"] - cur["x"]
                cur["h"] = max(cur["h"], wd["y"] + wd["h"] - cur["y"])
            else:
                cur = {"x": wd["x"], "y": wd["y"], "w": wd["w"], "h": wd["h"]}
                out.append(cur)
    return out


CELLS = {(0, 0): "upar-bayan", (1, 0): "upar-beech", (2, 0): "upar-dahin",
         (0, 1): "bayan", (1, 1): "bilkul beech", (2, 1): "dahin",
         (0, 2): "neeche-bayan", (1, 2): "neeche-beech", (2, 2): "neeche-dahin"}


def ocr_clean(txt):
    """OCR ka text dikhaane ke liye saaf karo — "ajeeb o ghreeb" kachra nikaal kar.
    Rules: bina-alfazi tokens (|, -, ?, mix symbols), ek-akshar gadbad (i/a ke alawa),
    aur lagataar dohraaye gaye tukde hat te hain. NAEP (n, chars, h320…) hamesha RAW
    words se hi gine jaate hain — ye safai sirf dikhaane ke text ke liye hai, aur
    dobara chalane par bhi kuch nahi bigadta (idempotent)."""
    if not txt:
        return ""
    parts = re.split(r"\s*\|\s*", txt) if "|" in txt else re.split(r"[\r\n]+", txt)
    keep, prev = [], None
    for p in parts:
        t = re.sub(r"\s+", " ", p).strip()
        if not t or t == prev:
            continue
        al = sum(1 for ch in t if ch.isalnum())
        if al == 0:
            continue                                   # pura nishan — kachra
        if len(t) == 1 and t.lower() not in ("i", "a"):
            continue                                   # OCR ki akeli gadbad
        if al < max(2, len(t)) * 0.45:
            continue                                   # alfaz se zyada nishan
        keep.append(t)
        prev = t
    return " ".join(keep)[:400]


def ocr_screen_clean(txt):
    """Screen-OCR (frames wala) text ki safai — line-line rehti hai, timestamp ke saath.
    ocr_clean thumbnail-chip ke liye hai (jod kar 400 akshar); ye poora screen text hai,
    is liye yahan koi jodna nahi — sirf kachra lines hataati hain (poori line me alfaz
    se zyada nishan ho to wo line gayab). 60,000 akshar ki chhat, uske baad cut flag."""
    out, prev = [], None
    for ln in (txt or "").splitlines():
        t = re.sub(r"\s+", " ", ln).strip()
        if not t or t == prev:
            continue
        body = re.sub(r"^\d{1,2}:\d{2}[:\d]*\s*", "", t)  # timestamp hatakar body ka kachra check
        al = sum(1 for ch in body if ch.isalnum())
        if al == 0 or al < max(2, len(body)) * 0.45:
            continue
        out.append(t)
        prev = t
    s = "\n".join(out)
    return s[:60000], len(s) > 60000


def text_stats(path, an, words, faces=None):
    """OCR ke boxes se: kitna text, kitna bada, kitna contrast, kahan baitha hai."""
    if not words:
        return {"n": 0, "chars": 0, "maxh": 0, "minh": 0, "area": 0, "cr": None, "cr_med": None,
                "lines": 0, "blocks": 0, "pos": "", "text": ""}
    im = Image.open(path).convert("RGB")
    W, H = im.size
    px = im.load()

    def lum(x, y):
        c = px[x, y]
        return rlum(c)

    crs, rings, covs = [], [], []
    bl = _blocks(words)          # lines/paragraph boxes — contrast ek patti par naapta
    for wd in bl:                # hota hai, akele chhote word-box par nahi (zyada kachra)
        x0, y0 = max(0, wd["x"]), max(0, wd["y"])
        x1, y1 = min(W, wd["x"] + wd["w"]), min(H, wd["y"] + wd["h"])
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        g = _glyph_cr(im, x0, y0, x1, y1)
        if not g:
            continue
        crs.append(g["cr"]); rings.append(g["ring"]); covs.append(g["cov"])
    if not crs:                  # numpy/cv2 na ho to purana andaaza (box ke andar p5/p95)
        for wd in bl:
            x0, y0 = max(0, wd["x"]), max(0, wd["y"])
            x1, y1 = min(W, wd["x"] + wd["w"]), min(H, wd["y"] + wd["h"])
            if x1 - x0 < 6 or y1 - y0 < 6:
                continue
            ins = []
            for yy in range(y0, y1, 2):
                for xx in range(x0, x1, 2):
                    ins.append(lum(xx, yy))
            if len(ins) < 12:
                continue
            hi, lo = pctl(ins, 0.95), pctl(ins, 0.05)
            crs.append(round(cratio(hi, lo), 3))
    hs = [w["h"] for w in words]
    area = sum(w["w"] * w["h"] for w in words) * 100.0 / (W * H)
    scale = 320.0 / W
    big = max(bl, key=lambda b: b["w"] * b["h"]) if bl else None
    pos = ""
    badge = edge = facehit = False
    if big:
        cx, cy = (big["x"] + big["w"] / 2.0) / W, (big["y"] + big["h"] / 2.0) / H
        pos = CELLS[(min(2, int(cx * 3)), min(2, int(cy * 3)))]
        badge = cx > 0.72 and cy > 0.80
        edge = big["x"] < W * 0.03 or big["y"] < H * 0.03 or \
               big["x"] + big["w"] > W * 0.97 or big["y"] + big["h"] > H * 0.97
        for f in (faces or []):
            fx0, fy0 = f["x"] * W, f["y"] * H
            if not (big["x"] + big["w"] < fx0 or big["x"] > fx0 + f["w"] * W or
                    big["y"] + big["h"] < fy0 or big["y"] > fy0 + f["h"] * H):
                facehit = True
    return {"n": len(words), "chars": sum(len(w["t"]) for w in words),
            "maxh": max(hs), "minh": min(hs), "area": round(area, 1),
            # contrast 2 digit tak: 0.01 se chhar-chhaar ka farq aankh se nahi dikhta,
            # aur poora float UI me "14.200000000000001" jaisa shor banata hai
            "cr": (round(min(crs), 2) if crs else None),
            "cr_med": (round(med(crs), 2) if crs else None),
            "ring_cr": (round(med(rings), 2) if rings else None),
            "cov": (med(covs) if covs else None),      # box ka kitna % sach me glyph hai
            "lines": len({w["y"] for w in words}), "blocks": len(bl),
            # text ke ASLI block (fraction me) — composition isi se naapa jaayega, kisi
            # andaaze se nahi
            "blks": [{"x": round(b["x"] / float(W), 3), "y": round(b["y"] / float(H), 3),
                      "w": round(b["w"] / float(W), 3), "h": round(b["h"] / float(H), 3),
                      "a": round(b["w"] * b["h"] * 100.0 / (W * H), 1)} for b in bl][:12],
            "pos": pos, "badge": badge, "edge": edge, "facehit": facehit,
            "h320": round(max(hs) * scale, 1), "h168": round(max(hs) * (168.0 / W), 1),
            # "text" sirf dikhaane ke liye hai — is liye saaf version. Naap upar se
            # raw words se hi (n, chars, h320) — safai unhe chhuti hi nahi.
            "text": ocr_clean(" | ".join(w["t"] for w in words))}


def comp_of(ts, faces):
    """Composition ASLI cheezon se naapta hai: OCR ke text-block boxes + YuNet ke face
    boxes. Ye woh cheezein hain jo thumbnail par waqai maujood hain — koi saliency ka
    andaaza nahi. (Naapa gaya: spectral-residual aur Itti dono saliency maps ne apne hi
    38 face-wale thumbnails par subject sirf 7/38 aur 3/36 baar pakda — yaani thumbnails
    par bottom-up saliency subject dhoondhne ke liye kaam nahi karti, designed text hi
    jeetta hai. Isliye composition ab detections se aata hai.)
    Deta hai: main subject ka box + uska frame ka %, 4x4 grid me mass kahan simti hai
    (ek jagah = focal point, bikhri = bheed), rule-of-thirds se faasla, aur kaun si
    taraf bilkul khaali pari hai (dead space)."""
    els = []
    for f in (faces or []):
        if (f.get("area") or 0) >= 0.5 and f.get("w"):
            els.append((float(f["x"]), float(f["y"]), float(f["w"]), float(f["h"]), float(f["area"])))
    for b in ((ts or {}).get("blks") or []):
        if (b.get("a") or 0) >= 0.5 and b.get("w"):
            els.append((float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"]), float(b["a"])))
    if not els:
        return None
    tot = sum(e[4] for e in els) or 1.0
    G = 4
    grid = [[0.0] * G for _ in range(G)]
    for x, y, w, h, a in els:
        for gy in range(G):
            oy = max(0.0, min(y + h, (gy + 1) / float(G)) - max(y, gy / float(G)))
            if oy <= 0:
                continue
            for gx in range(G):
                ox = max(0.0, min(x + w, (gx + 1) / float(G)) - max(x, gx / float(G)))
                if ox > 0:
                    # element ka poora wazan uske box ke jitne hisse me utna hi jaata hai —
                    # warna chhote elements ka wazan apne aap kam ho jaata (grid ka sum 1
                    # hona chahiye, ye pehle galat tha)
                    grid[gy][gx] += a * (ox * oy) / max(1e-9, w * h)
    cells = [grid[gy][gx] / tot for gy in range(G) for gx in range(G)]
    dom = max(e[4] for e in els) / tot          # sabse bari cheez kitni dominent hai:
                                                # 1 = frame me ek hi subject, chhota = bheed
    ent = -sum(v * math.log(v) for v in cells if v > 0) / math.log(len(cells))
    cx = sum((gx + 0.5) / G * sum(grid[gy][gx] for gy in range(G)) for gx in range(G)) / tot
    cy = sum((gy + 0.5) / G * sum(grid[gy]) for gy in range(G)) / tot
    dmin = min(math.hypot(cx - tx, cy - ty) for tx in (1 / 3.0, 2 / 3.0) for ty in (1 / 3.0, 2 / 3.0))
    # subject = sabse bara element + jo usse chipka hua hai (text + chehra aksar ek hi
    # guchha hote hain; alag-alag guchhe = bheed)
    big = max(els, key=lambda e: e[4])
    bx0, by0, bx1, by1 = big[0], big[1], big[0] + big[2], big[1] + big[3]
    cl = [big]
    for e in els:
        if e is big:
            continue
        ex0, ey0, ex1, ey1 = e[0], e[1], e[0] + e[2], e[1] + e[3]
        if bx0 - 0.05 <= ex1 and ex0 <= bx1 + 0.05 and by0 - 0.05 <= ey1 and ey0 <= by1 + 0.05:
            cl.append(e)
    sx0 = min(e[0] for e in cl); sy0 = min(e[1] for e in cl)
    sx1 = max(e[0] + e[2] for e in cl); sy1 = max(e[1] + e[3] for e in cl)
    subj_pct = round((sx1 - sx0) * (sy1 - sy0) * 100.0, 1)
    strips = {"left": sum(grid[gy][0] for gy in range(G)) / tot,
              "right": sum(grid[gy][G - 1] for gy in range(G)) / tot,
              "top": sum(grid[0][gx] for gx in range(G)) / tot,
              "bottom": sum(grid[G - 1][gx] for gx in range(G)) / tot}
    side = min(strips, key=lambda k: strips[k])
    return {"els": len(els), "clusters": len(els) - len(cl), "dom": round(dom, 3),
            "subject": {"x": round(sx0, 3), "y": round(sy0, 3),
                        "w": round(max(0.0, sx1 - sx0), 3), "h": round(max(0.0, sy1 - sy0), 3)},
            "subj_pct": subj_pct, "mass": [round(c, 4) for c in cells],
            "top": round(max(cells), 3), "entropy": round(ent, 3),
            "cog": [round(cx, 3), round(cy, 3)],
            "thirds": round(1.0 - min(1.0, dmin / 0.47), 3),
            "empty": {"side": side, "pct": round(strips[side] * 100, 1)}}


def _glyph_cr(im, x0, y0, x1, y1, pad=8):
    """ASLI glyph-vs-background contrast. Purana tareeka box ke andar ka p5/p95 luminance
    tha — bold white text par 19:1 jaisa phula hua number milta tha. Ye asli kaam karta
    hai: (1) box ka background median-blur se nikalna (text mit jaata hai, background
    bachta hai), (2) usse farq karke glyph ka mask, (3) glyph ka asli rang vs uske APNE
    background ka WCAG ratio, (4) ring = box se bahar ki patti vs glyph — outline/shadow
    ka asli test. Naapa: black-hole thumbnail par purana 19.6:1 batata tha, asli ~13:1."""
    if np is None or Image is None:
        return None
    W, H = im.size
    rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
    rx1, ry1 = min(W, x1 + pad), min(H, y1 + pad)
    if rx1 - rx0 < 12 or ry1 - ry0 < 12:
        return None
    crop = np.asarray(im.crop((rx0, ry0, rx1, ry1)), dtype=np.float64)
    # DO alag maps, kyunki kaam alag hain:
    #  lum — gamma-space luminance (0..255): text/background ka FARQ yahan naapa jaata hai
    #  rl  — WCAG relative luminance (0..1): contrast ratio sirf isi se banta hai, warna
    #        0..255 par ratio 5000 tak nikal jaata tha (naapa gaya tha) aur 21 se zyada
    #        kabhi ho hi nahi sakta.
    lum = crop[:, :, 0] * 0.2126 + crop[:, :, 1] * 0.7152 + crop[:, :, 2] * 0.0722
    rl = (np.where(crop[:, :, 0] <= 10.31, crop[:, :, 0] / 3294.6,
                   ((crop[:, :, 0] + 14.02) / 269.02) ** 2.4) * 0.2126 +
          np.where(crop[:, :, 1] <= 10.31, crop[:, :, 1] / 3294.6,
                   ((crop[:, :, 1] + 14.02) / 269.02) ** 2.4) * 0.7152 +
          np.where(crop[:, :, 2] <= 10.31, crop[:, :, 2] / 3294.6,
                   ((crop[:, :, 2] + 14.02) / 269.02) ** 2.4) * 0.0722)
    # box ke coordinates, crop ke andar
    ix0, iy0, ix1, iy1 = x0 - rx0, y0 - ry0, x1 - rx0, y1 - ry0
    inner = np.zeros(lum.shape, dtype=bool)
    inner[iy0:iy1, ix0:ix1] = True
    # background estimate: badi median blur text ko mita deti hai
    k = max(5, int(min(iy1 - iy0, ix1 - ix0) * 0.6))
    k += 1 - (k % 2)
    try:
        u8 = np.asarray(im.crop((rx0, ry0, rx1, ry1)), dtype=np.uint8)
        bg = cv2.medianBlur(u8, min(k, 41)) if cv2 is not None else None
        if bg is None:
            raise RuntimeError
        bg = bg.astype(np.float64)
        bglum = bg[:, :, 0] * 0.2126 + bg[:, :, 1] * 0.7152 + bg[:, :, 2] * 0.0722
    except Exception:
        return None
    diff = np.abs(lum - bglum)
    ins = diff[inner]
    if ins.size < 24:
        return None
    # glyph ka mask: Otsu ka apna choose kiya hua split (circular nahi). Pehle p70 par
    # threshold tha, isliye "cov" har image me 0.30 hi raha tha — wo threshold ka natija
    # tha, text ka nahi.
    thr = None
    if cv2 is not None:
        try:
            d8 = np.clip(ins, 0, 255).astype(np.uint8)
            t, _tt = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if t > 0:
                thr = float(t)
        except Exception:
            thr = None
    if thr is None:
        thr = float(np.percentile(ins, 70))
    thr = max(16.0, thr)
    mask = inner & (diff >= thr)
    cov = float(mask.sum()) / max(1.0, float(inner.sum()))
    if cov < 0.015 or cov > 0.92:          # yaani text hai hi nahi, ya sab kuch text hai
        return None
    gl = float(np.median(rl[mask]))
    bgp = rl[inner & ~mask]
    if bgp.size < 12:
        return None
    bl_ = float(np.median(bgp))
    cr = cratio(gl, bl_)
    ring = np.zeros(lum.shape, dtype=bool)
    ring[:] = True
    ring[iy0:iy1, ix0:ix1] = False
    ringl = float(np.median(rl[ring]))
    return {"cr": round(cr, 2), "ring": round(cratio(gl, ringl), 2), "cov": round(cov, 3),
            "gl": round(gl * 255, 1), "bg": round(bl_ * 255, 1)}


def verdicts(an, ts, faces=None, comp=None):
    """Seedhe, saaf rules — UI me ye hi dikhte hain.
    `comp` de do to wahi composition dobara nahi ginta (measure_items use kar chuka hota
    hai); dobara ginne se 400-video channel par seconds ka shor hota hai."""
    v = []
    if not an or an.get("err"):
        return [{"s": "bad", "k": "analysis", "v": "Pillow nahi", "n": "pip install pillow"}]
    if ts["n"] == 0:
        v.append({"s": "warn", "k": "Thumbnail par text", "v": "kuch nahi mila",
                  "n": "bilkul text nahi bhi chalega (sirf strong image), par zyada log text dalte hain — competitor dekho"})
    elif ts["n"] <= TH["words_ok"]:
        v.append({"s": "ok", "k": "Text ki matra", "v": str(ts["n"]) + " shabd",
                  "n": "ideal range (1–" + str(TH["words_ok"]) + ")"})
    elif ts["n"] <= TH["words_warn"]:
        v.append({"s": "warn", "k": "Text ki matra", "v": str(ts["n"]) + " shabd", "n": "thoda zyada — aadha kar do"})
    else:
        v.append({"s": "bad", "k": "Text ki matra", "v": str(ts["n"]) + " shabd", "n": "bahut zyada — mobile par text kho jayega"})
    if ts["n"]:
        h = ts["h320"]
        if h >= TH["h_ok"]:
            v.append({"s": "ok", "k": "Sabse bada text (320px par)", "v": str(h) + "px", "n": "browse par saaf padha jayega"})
        elif h >= TH["h_mid"]:
            v.append({"s": "warn", "k": "Sabse bada text (320px par)", "v": str(h) + "px",
                      "n": "mushkil se padha jayega — kam se kam " + str(int(TH["h_ok"])) + "px karo"})
        else:
            v.append({"s": "bad", "k": "Sabse bada text (320px par)", "v": str(h) + "px", "n": "bohot chhota — YouTube par ye dikhega hi nahi"})
        c = ts.get("cr_med")
        if c is not None:
            extra = " | sabse kamzor line " + str(ts.get("cr")) + ":1"
            if ts.get("ring_cr") is not None:
                extra += " | outline ke bina aas-paas se " + str(ts["ring_cr"]) + ":1"
            if ts.get("cov") is not None:
                extra += " | line ka " + str(int(ts["cov"] * 100)) + "% sach me text hai"
            if c >= TH["cr_ok"]:
                v.append({"s": "ok", "k": "Text vs uska apna background", "v": str(c) + ":1",
                          "n": "WCAG AA pass — glyph ka rang uski apni patti se naapa gaya" + extra})
            elif c >= TH["cr_warn"]:
                v.append({"s": "warn", "k": "Text vs uska apna background", "v": str(c) + ":1",
                          "n": "thoda kam — text par outline/shadow lagao" + extra})
            else:
                v.append({"s": "bad", "k": "Text vs uska apna background", "v": str(c) + ":1",
                          "n": "text background me dub jayega" + extra})
        if ts.get("blocks", 0) > TH["blocks_ok"]:
            v.append({"s": "warn", "k": "Text ke tukde", "v": str(ts["blocks"]) + " alag blocks",
                      "n": "ek jagah ek hi baat likho — " + str(TH["blocks_ok"]) + " se zyada block nazar nahi aate"})
        if ts.get("badge"):
            v.append({"s": "warn", "k": "Duration badge se takraav", "v": "text neeche-dahin kone me hai",
                      "n": "YouTube ka time badge wahin hota hai — text dab jayega"})
        if ts.get("edge"):
            v.append({"s": "warn", "k": "Frame ka kinara", "v": "text kinare se chipka hai",
                      "n": "kuch devices/crop me ye hissa katta hai — 5% chhodo"})
        if ts.get("facehit"):
            v.append({"s": "warn", "k": "Chehra vs text", "v": "text chehre ke upar aa raha hai",
                      "n": "chehra hi sabse zyada click karata hai — us par text na rakho"})
        if ts.get("area", 0) > TH["area_ok"]:
            v.append({"s": "warn", "k": "Text ka area", "v": "frame ka " + str(ts["area"]) + "%",
                      "n": "itna text padhne ka mauqa hi nahi milta"})
    if faces:
        mx = max(f["area"] for f in faces)
        eng = " (Haar ka andaaza — model nahi mila)" if faces[0].get("haar") else ""
        if mx >= TH["face_ok"]:
            side = ""
            fr = [f for f in faces if (f.get("area") or 0) >= 3]
            if fr:
                side = ", " + str(len(fr)) + " saamne ka"
            v.append({"s": "ok", "k": "Chehra", "v": str(len(faces)) + " chehra, sabse bara " + str(mx) + "% frame ka" + side + eng,
                      "n": "insaan ka chehra CTR sabse zyada badhata hai"})
        elif mx >= TH["face_min"]:
            v.append({"s": "warn", "k": "Chehra", "v": "chehra bahut chhota (" + str(mx) + "%)" + eng,
                      "n": "subject ko bara karo — 25–40% frame lena chahiye"})
    else:
        v.append({"s": "warn", "k": "Chehra", "v": "koi chehra nahi mila",
                  "n": "insaan ka chehra na ho to subject bahut clear hona chahiye (chehra = sabse bara CTR lever)"})
    if an.get("blur"):
        v.append({"s": "warn", "k": "Clearness", "v": "image dhundhli (sharp " + str(an.get("sharp")) + ")",
                  "n": "asli photo/bari file use karo — chhoti file ko zoom na karo"})
    # Composition ab ASLI cheezon se naapa jaata hai: OCR ke text-block boxes aur YuNet
    # ke face boxes. Pehle ye "saliency map" se hota tha — wo apne hi data par fail hua
    # (38 face-wale thumbnails me se sirf 7 ka subject pakda), isliye uski jagah ye rakha.
    cp = comp if comp is not None else comp_of(ts, faces)
    if cp:
        third = cp.get("thirds")
        if third is not None and third >= TH["thirds_ok"]:
            v.append({"s": "ok", "k": "Composition", "v": "main cheezein rule-of-thirds ke paas hain (%d cheezein naapi)" % cp["els"],
                      "n": "aankh seedha subject par jaati hai"})
        elif third is not None and third < 0.25:
            v.append({"s": "warn", "k": "Composition", "v": "sab kuch bilkul beech ya kinare (%d cheezein)" % cp["els"],
                      "n": "subject ko ek taraf rakho — space me text aasani se baithega"})
        dm = cp.get("dom") or 0
        if dm < TH["dom_warn"]:
            v.append({"s": "warn", "k": "Ek subject ya bheed?",
                      "v": "koi ek cheez dominant nahi (sabse bara sirf %d%%, %d alag hisse)" % (int(dm * 100), cp["els"]),
                      "n": "frame me kaafi cheezein barabar hain — ek chehra/cheez itni bara karo ki sirf wahi dikhe"})
        elif dm >= 0.7 or cp["els"] <= 1:
            v.append({"s": "ok", "k": "Ek subject ya bheed?",
                      "v": "ek cheez dominant (frame ke mass ka %d%%)" % int(dm * 100),
                      "n": "thumbnail ka kaam ek hi cheez dikhana hai — ye wahi kar raha hai"})
    if an.get("lowrow", 0) > 34:
        v.append({"s": "warn", "k": "Neeche ka hissa", "v": "frame ke nichle hisse me bheed (" + str(an["lowrow"]) + "%)",
                  "n": "neeche ka area mobile par badge/caption se dhak jata hai — upar 70% me kaam rakho"})
    b = an["bright"]
    if b < TH["bright"][0]:
        v.append({"s": "warn", "k": "Brightness", "v": str(b), "n": "bahut dark — YouTube ke dark theme me dub jayega"})
    elif b > TH["bright"][1]:
        v.append({"s": "warn", "k": "Brightness", "v": str(b), "n": "bahut halka/dhundhla — rang dab jayenge"})
    else:
        v.append({"s": "ok", "k": "Brightness", "v": str(b), "n": "theek range me"})
    if an["dyn"] < TH["dyn_ok"]:
        v.append({"s": "warn", "k": "Contrast range (image ka)", "v": str(an["dyn"]), "n": "flat dikhega — ek bright subject + dark background try karo"})
    else:
        v.append({"s": "ok", "k": "Contrast range (image ka)", "v": str(an["dyn"]), "n": "kaafi depth hai"})
    if an["clutter"] is not None:
        if an["clutter"] > TH["clutter_ok"]:
            v.append({"s": "warn", "k": "Bheed (edges)", "v": str(an["clutter"]) + "%", "n": "bahut kuch ek frame me — chhota card banao"})
        else:
            v.append({"s": "ok", "k": "Bheed (edges)", "v": str(an["clutter"]) + "%", "n": "saaf frame hai"})
    if an["w"] < 1000:
        v.append({"s": "warn", "k": "File ki size", "v": str(an["w"]) + "x" + str(an["h"]),
                  "n": "YouTube 1280x720 maangta hai — chhoti file upload par compress ho jayegi"})
    return v


def feat(an, ts, faces=None, comp=None):
    """Score ke features — sab 0..1 par normal. Ise alag function isliye banaya hai ki
    asli CTR ke data par inhi features ke wazan (weights) fit kiye ja sakein
    (calibrate_weights). Pehle wazan code me likhe hue the, ab wo data se aa sakte hain.
    `comp` pehle se naapa ho to de do — wahi composition dobara ginne se bachne ke liye."""
    f = {}
    fa = [x for x in (faces or [])]
    comp = comp or comp_of(ts, fa) or (an or {}).get("comp") or {}
    h = float(ts.get("h320") or 0)
    f["big_text"] = min(1.0, h / 26.0)
    n = int(ts.get("n") or 0)
    f["n_text"] = 1.0 if n == 0 else (1.0 if n <= TH["words_ok"] else
                                      (0.45 if n <= TH["words_warn"] else 0.0))
    f["contrast"] = min(1.0, float(ts.get("cr_med") or 0) / TH["cr_full"])
    f["outline"] = 1.0 if float(ts.get("ring_cr") or 0) >= TH["ring_ok"] else 0.0
    f["face"] = _rng(max([x.get("area") or 0 for x in fa], default=0.0), TH["face_lo"], TH["face_hi"])
    f["frontal"] = 1.0 if any(x.get("frontal") and (x.get("area") or 0) >= 3 for x in fa) else 0.0
    b = float(an.get("bright") or 0)
    f["bright"] = 1.0 if TH["bright"][0] <= b <= TH["bright"][1] else 0.0
    f["dyn"] = min(1.0, float(an.get("dyn") or 0) / 0.70)
    f["clean"] = 1.0 if (an.get("clutter") is not None and an["clutter"] <= TH["clutter_ok"]) else 0.0
    # composition ASLI detections se (OCR ke text blocks + YuNet ke face boxes), saliency
    # ke andaaze se nahi. Naapa gaya: SR aur Itti dono saliency maps ne apne hi 38/36
    # face-wale thumbnails par subject sirf 7 aur 3 baar pakda — designed thumbnails par
    # bottom-up saliency subject nahi dhoondh paati (bada text jeetta hai).
    f["focus"] = _rng(float(comp.get("dom") or 0), TH["dom_lo"], TH["dom_hi"])
    f["subject"] = _rng(float(comp.get("subj_pct") or 0), TH["subj_lo"], TH["subj_hi"])
    f["thirds"] = _rng(float(comp.get("thirds") or 0), TH["thirds_lo"], TH["thirds_hi"])
    f["sharp"] = _rng(float(an.get("sharp") or 0), TH["sharp_lo"], TH["sharp_hi"])
    pen = 0.0
    if an.get("blur"):
        pen += 8
    if ts.get("badge") or ts.get("edge") or ts.get("facehit"):
        pen += 5
    if int(ts.get("blocks") or 0) > TH["blocks_ok"]:
        pen += 4
    if ts.get("area", 0) > TH["area_ok"]:
        pen += 4
    return f, pen


# Default (heuristic) wazan — tab tak jab tak apna asli CTR data (>=8 rows) na bane.
# Inka total 100 hai; base 6 aankh se dikhaane ke liye rakha hai, warna max 94 hota.
W_DEF = {"big_text": 20, "contrast": 14, "n_text": 8, "outline": 4, "face": 12,
         "frontal": 4, "bright": 5, "dyn": 5, "clean": 4, "focus": 6, "subject": 6,
         "thirds": 3, "sharp": 3}
BASE = 6


_CALREJ = [None]   # pichhli baar calibration FILE reject kyun hui — UI ko dikhane ke liye


def load_cal():
    """Apne channel ke asli CTR par fit huye wazan. Na mile to None.
    File mojood ho magar uska cross-validated R² theek na ho to bhi None — aise wazan
    lagana har video ka mean dene se bhi bura andaza hota."""
    try:
        d = json.loads(CAL_F.read_text(encoding="utf-8"))
        if isinstance(d, dict) and int(d.get("n") or 0) >= CAL_MIN_N and isinstance(d.get("w"), dict):
            cv = d.get("cv_r2")
            if cv is None or cv < CAL_MIN_CV:
                _CALREJ[0] = ("calibration.json likha hua hai magar cross-validated R² %s (n=%s) "
                              "— isliye wazan nahi chal rahe" % (cv, d.get("n")))
                return None
            _CALREJ[0] = None
            return d
    except Exception:
        pass
    return None


_CALV = [None, 0.0]


def cal_now():
    """Calibration file ko har score par dobara padhna bekaar hai — 5 minute ka cache."""
    now = time.time()
    if now - _CALV[1] > 300:
        _CALV[1] = now
        _CALV[0] = load_cal()
    return _CALV[0]


def score(an, ts, faces=None, cal=None):
    """0–100: features ka wazan. `cal` = apne CTR par fit kiye wazan (calibration.json);
    wo na ho to default heuristic wazan — aur UI me saaf likha jaata hai kaun sa chal raha.
    cal=False bhejo to jaan-boojhkar heuristic wazan chalein."""
    if not an or an.get("err"):
        return 0
    f, pen = feat(an, ts, faces)
    if cal is None:
        cal = cal_now()
    w = (cal or {}).get("w") if cal else None
    if not w:
        w = W_DEF
    s = BASE + sum(w.get(k, 0) * f[k] for k in f)
    return int(max(0, min(100, round(s - pen))))


def score_detail(an, ts, faces=None, cal=None, comp=None):
    """Score KAISE bana — har feature ka value (0..1), uska wazan, aur kitne number mile.
    UI me "ye score kaise bana" isi se khulta hai. Number dobara ginne ke liye ye wahi
    feat()/wazan wala rasta chalta hai jo score() chalta hai, isliye dono ka antak milta
    hai. `cal=False` = jaan-boojhkar heuristic wazan (purane scan ke record ke hisaab se)."""
    if not an or an.get("err"):
        return {"err": "thumbnail naap nahi ho saka"}
    f, pen = feat(an, ts, faces, comp)
    if cal is None:
        cal = cal_now()
    w = (cal or {}).get("w") if cal else None
    src = "calibrated" if w else "heuristic"
    n_cal = (cal or {}).get("n") if w else None
    if not w:
        w = W_DEF
    parts = sorted([{"k": k, "v": round(float(f[k]), 3), "w": w.get(k, 0),
                     "p": round(w.get(k, 0) * float(f[k]), 1)} for k in f],
                   key=lambda p: (-p["p"], p["k"]))
    raw = BASE + sum(w.get(k, 0) * f[k] for k in f)
    return {"base": BASE, "pen": pen, "src": src, "n_cal": n_cal,
            "raw": round(raw, 1), "score": int(max(0, min(100, round(raw - pen)))), "parts": parts}


def calib_weights(rows):
    """Asli CTR par score ke wazan fit karna (Ridge + 5-fold cross-validation).
    rows = [(features_dict, ctr_percent), ...]. Kam se kam CAL_MIN_N rows chahiye.
    Wapas deta hai {w, r2, cv_r2, n, fit} — ya None agar data kaafi na ho."""
    load_sk()
    if _RIDGE is None or _KFOLD is None or len(rows) < CAL_MIN_N:
        return None
    try:
        import numpy as _np
        keys = sorted(W_DEF)
        X = _np.array([[r[0].get(k, 0.0) for k in keys] for r in rows], dtype=float)
        y = _np.array([float(r[1]) for r in rows], dtype=float)
        if y.std() <= 1e-9:
            return None
        yz = (y - y.mean()) / y.std()
        m = _RIDGE(alpha=1.0)
        m.fit(X, yz)
        pred = m.predict(X)
        ss = float(((yz - pred) ** 2).sum())
        st = float(((yz - yz.mean()) ** 2).sum()) or 1.0
        r2 = 1.0 - ss / st
        # 5-fold cross-validated R² — ye batata hai ki fit asli hai ya yaad karne ka dhoka
        cv = []
        for tr, te in _KFOLD(n_splits=min(5, len(rows)), shuffle=True, random_state=0).split(X):
            if len(tr) < 4 or len(te) == 0:
                continue
            mm = _RIDGE(alpha=1.0).fit(X[tr], yz[tr])
            p = mm.predict(X[te])
            s2 = float(((yz[te] - p) ** 2).sum())
            t2 = float(((yz[te] - yz[tr].mean()) ** 2).sum()) or 1.0
            cv.append(1.0 - s2 / t2)
        w = {}
        pos = [max(0.0, v) for v in m.coef_]
        tot = sum(pos) or 1.0
        for k, v in zip(keys, pos):
            w[k] = round(v / tot * (100.0 - BASE), 1)
        # ye bhi likh rahe hain taaki jo feature CTR par ULTA chala gaya wo chhupa na jaaye —
        # wazan me to sirf positive hissa jaata hai, sach dono taraf ho sakta hai
        raw = {}
        for k, v in zip(keys, m.coef_):
            raw[k] = round(float(v), 3)
        return {"w": w, "raw": raw, "r2": round(r2, 3), "cv_r2": round(sum(cv) / len(cv), 3) if cv else None,
                "n": len(rows), "ctr_med": round(float(y.mean()), 2),
                "fit": "ridge+5fold", "at": int(time.time())}
    except Exception:
        return None



# ---- 4b. YouTube Studio ki CSV se ASLI CTR, aur usi par wazan fit karna ----
# YouTube ka CTR/retention sirf channel ke malik ko milta hai, aur wo bina OAuth wale API
# ke bahar nahi aata. Par Studio khud CSV de deta hai — isliye ye rasta: wo file yahan
# daalo, numbers apne videos par baithenge, aur wazan usi asli CTR par fit honge.
# Studio ke header language ke hisaab se badalte hain, isliye naam poori tarah nahi maane
# jaate — jo column mila wo dikhaaya jaata hai, jo nahi mila uski wajah.

STUDIO_COLS = (
    ("ctr", ("impressions click-through rate", "click-through rate", "impression click",
             "klickrate", "klick-rate", "क्लिक-थ्रू", "क्लिक दर", "click rate")),
    ("avd", ("average view duration", "avg view duration", "durchschnittliche aufrufdauer",
             "औसत वीडियो अवधि")),
    ("ret", ("average percentage viewed", "percentage viewed", "प्रदर्शित प्रतिशत")),
    ("imp", ("impressions", "impressionen", "प्रदर्शन")),
    ("views", ("views", "aufrufe", "दृश्य", "आपत्तियाँ")),
    ("likes", ("likes", "पसंद")),
    ("date", ("publication date", "published at", "upload date", "veröffentlichungsdatum")),
    ("vid", ("video id", "video-id", "video id (youtube)", "वीडियो आईडी")),
    ("title", ("video title", "video name", "video titel", "videotitel", "titel des videos",
               "वीडियो शीर्षक", "शीर्षक")),
)


def _nh(s):
    return re.sub(r"\s+", " ", str(s or "").strip().strip('"').strip("'").lower())


def _num(s):
    """'4,7 %' / '1,234' / '४.५' जैसी हर शक्ल से number. Na mile to None."""
    t = _nh(s).replace("%", "").replace("\u00a0", " ").replace("\u202f", " ").strip()
    if not t or t in ("-", "n/a", "na", "null", "none"):
        return None
    t = "".join(ch for ch in t if ch.isdigit() or ch in ".,-")
    if not t or t in ("-", ".", ","):
        return None
    neg = t.startswith("-")
    t = t.lstrip("-")
    if t.count(",") and t.count("."):
        t = t.replace(",", "") if t.rfind(",") < t.rfind(".") else t.replace(".", "").replace(",", ".")
    elif t.count(",") > 1 or (t.count(",") == 1 and len(t.split(",")[-1]) == 3):
        t = t.replace(",", "")
    elif t.count(",") == 1:
        t = t.replace(",", ".")
    try:
        v = float(t)
    except Exception:
        return None
    return -v if neg else v


def _secs(s):
    """'3:45' ya '1:02:10' → seconds. Number diya ho to seconds hi samjho."""
    t = str(s or "").strip()
    if not t:
        return None
    if ":" in t:
        p = t.split(":")
        try:
            n = [int(x) for x in p]
        except Exception:
            return None
        v = 0
        for x in n:
            v = v * 60 + x
        return v
    v = _num(t)
    return int(v) if v is not None else None


def csv_head(head):
    """Studio ke header row se column ka pata. Ek column = ek field ( warna ek hi header do
    field bhar deta hai), aur sabse lamba synonym jeetta hai ("impressions click-through
    rate" > "impressions"). Jo mila uska asli naam wapas deta hai taaki user khud check kar
    sake — andhere me match nahi kar rahe."""
    pats = []
    for field, syns in STUDIO_COLS:
        for s in syns:
            pats.append((s, field))
    cols, got = {}, {}
    for idx, h in enumerate(head):
        n = _nh(h)
        if not n:
            continue
        best = None
        for s, field in pats:
            if field in cols:
                continue
            exact = (n == s)
            sub = (len(s) > 4 and s in n)
            if not (exact or sub):
                continue
            score = (1000 if exact else 0) + len(s)
            if best is None or score > best[0]:
                best = (score, field)
        if best:
            cols[best[1]] = idx
            got[best[1]] = str(h).strip()[:60]
    return cols, got


def _csv_rows(text):
    """CSV/TSV dono chalein (Studio jis dialect me bhi bheje)."""
    import csv as _csv
    txt = (text or "").lstrip("\ufeff").strip()
    if not txt:
        return []
    try:
        d = _csv.Sniffer().sniff(txt[:4000], delimiters=",;\t")
        dq = d.delimiter
    except Exception:
        dq = "\t" if txt.count("\t") > txt.count(",") else ","
    return [r for r in _csv.reader(txt.splitlines(), delimiter=dq) if any(str(c).strip() for c in r)]


def find_vid_title(title, chan=None):
    """Title se video id (yt-dlp search). Sirf tab jab naam poora mel khaye — warna galat
    video par CTR baithne ka khatra, jo secha ka sabse bada dhoka hota hai."""
    want = _nh(title)
    if not want:
        return None
    y = find_ytdlp()
    rc, out, err = run([y, "--flat-playlist", "--no-warnings", "--print",
                        "%(id)s\t%(title)s\t%(channel)s", "ytsearch5:" + str(title)[:120]], timeout=90)
    best, amb = None, 0
    for ln in (out or "").splitlines():
        p = ln.split("\t")
        if len(p) < 2 or not p[0]:
            continue
        if _nh(p[1]) != want:
            continue
        if chan and _nh(p[2] if len(p) > 2 else "") != _nh(chan):
            continue
        amb += 1
        if best is None:
            best = {"vid": p[0], "title": p[1], "chan": p[2] if len(p) > 2 else ""}
    if not best:
        return None
    best["ambiguous"] = amb > 1
    return best


def own_import_csv(text, dry=False):
    """Studio ki CSV → own.json. dry=True sirf yehi batata hai kya-kya mila, kuch save nahi karta."""
    rows = _csv_rows(text)
    if len(rows) < 2:
        return {"error": "CSV khali lag raha hai — Studio ki file poori paste karo (header + rows)"}
    head = rows[0]
    cols, got = csv_head(head)
    rep = {"cols_found": got, "cols_missing": [f for f, _ in STUDIO_COLS if f not in cols],
           "header": [str(h).strip()[:40] for h in head][:14], "rows_in": len(rows) - 1}
    if "title" not in cols and "vid" not in cols:
        rep["error"] = ("CSV me video ka title ya id ka column nahi mila. Studio me: Analytics → "
                        "Content → Videos → Export CSV. Jo headers mile wo upar dikh rahe hain.")
        return rep
    if "ctr" not in cols and "avd" not in cols and "ret" not in cols:
        rep["error"] = ("CTR/average view duration ka column nahi mila — ye Analytics wali export "
                        "me hota hai, Content wali me nahi.")
        return rep
    own = own_load()
    ok, bad, resolved = [], [], 0
    for r in rows[1:]:
        def g(f):
            i = cols.get(f)
            return r[i] if (i is not None and len(r) > i) else ""
        title = str(g("title")).strip()
        vid = re.sub(r"[^0-9A-Za-z_-]", "", str(g("vid")))
        if len(vid) != 11:
            vid = ""
        ctr, avd, ret = _num(g("ctr")), _secs(g("avd")), _num(g("ret"))
        if not title and not vid:
            continue
        if ctr is None and avd is None and ret is None:
            bad.append({"title": title[:60], "why": "is line me CTR/AVD dono khali"})
            continue
        if not vid:
            f = find_vid_title(title)
            if not f:
                bad.append({"title": title[:60], "why": "YouTube par exact title se video nahi mila "
                                                        "(id wala column CSV me nahi tha)"})
                continue
            vid = f["vid"]
            resolved += 1
            if f.get("ambiguous"):
                bad.append({"title": title[:60], "why": "ek jaisa naam 2+ videos ka — pehle wala liya, "
                                                        "galat ho sakta hai (%s)" % vid})
        e = own.get(vid) or {}
        e.update({"title": title or e.get("title") or "", "src": "studio_csv",
                  "at": dt.datetime.now().isoformat(timespec="seconds")})
        if ctr is not None:
            e["ctr"] = ctr
        if avd is not None:
            e["avd"] = avd
        if ret is not None:
            e["ret"] = ret
        for k, f in (("imp", "imp"), ("views", "views"), ("likes", "likes")):
            v = _num(g(f))
            if v is not None:
                e[k] = v
        d = str(g("date")).strip()
        if d:
            e["pub"] = d[:24]
        if not dry:
            own[vid] = e
        ok.append({"vid": vid, "title": (title or "")[:70], "ctr": ctr, "avd": avd, "ret": ret})
    if not dry:
        try:
            OWN_F.parent.mkdir(parents=True, exist_ok=True)
            OWN_F.write_text(json.dumps(own, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e2:
            return {"error": "save nahi hua: " + str(e2)[:120]}
    rep.update({"ok": True, "matched": ok, "n_matched": len(ok), "n_bad": len(bad),
                "by_title": resolved, "unmatched": bad[:25], "dry": bool(dry),
                "own_total": len(own_load())})
    return rep


def cal_rows(job=None):
    """Apni videos ke features + unka ASLI CTR — calibration ke liye rows.
    Features wahin se aate hain jo har aur score par chalta hai: thumbnail download (cache),
    YuNet, OCR, comp_of, feat. Kisi par text/face ka box hi na mile to us row ko chhod deta
    hoon — adhoori features par fit karna khud-dhoka hoga. Naapa hua: ~0.5s/video (cache hit par kam)."""
    own = own_load()
    rows, miss = [], []
    todo = [(v, e) for v, e in sorted(own.items()) if re.fullmatch(r"[0-9A-Za-z_-]{11}", v or "")]
    if job is not None:
        job["total"] = len(todo)
    n = 0
    for vid, e in todo:
        n += 1
        if job is not None:
            job["done"] = n
            job["current"] = "features: %d/%d %s" % (n, len(todo), (e.get("title") or vid)[:40])
        ctr = e.get("ctr")
        if not isinstance(ctr, (int, float)) or not (0 < float(ctr) < 100):
            miss.append({"vid": vid, "why": "asli CTR nahi hai (Studio CSV daalo)"})
            continue
        p, kind = get_thumb(vid)
        if not p:
            miss.append({"vid": vid, "why": "thumbnail nahi mila (video delete ya private?)"})
            continue
        an = analyse(p)
        if not an or an.get("err"):
            miss.append({"vid": vid, "why": "thumbnail parse nahi hua"})
            continue
        fc = faces_of(p)
        w = ocr_cached(p)
        ts = text_stats(p, an, w or [], fc)
        if not comp_of(ts, fc):
            miss.append({"vid": vid, "why": "is par text/face ka koi box nahi — features adhoore"})
            continue
        f, pen = feat(an, ts, fc)
        rows.append((f, float(ctr)))
    return rows, miss


def cal_run(job=None):
    """Apne hi CTR par wazan fit karke calibration.json me likhna. Job ke through chale to
    UI ko progress dikhti hai (har video par CV chalta hai, ~0.5s/video)."""
    rows, miss = cal_rows(job)
    if len(rows) < CAL_MIN_N:
        return {"error": "asli CTR wale kam se kam %d video chahiye — abhi sirf %d ready hain"
                         % (CAL_MIN_N, len(rows)), "n": len(rows), "need": CAL_MIN_N,
                "unready": miss[:25]}
    cal = calib_weights(rows)
    if not cal:
        return {"error": "fit nahi ho paaya (CTR sabka same hai ya sklearn nahi hai)",
                "n": len(rows), "unready": miss[:25]}
    cal["src"] = "apne channel ka CTR (own.json)"
    cal["feat_v"] = 2
    cal["unready"] = len(miss)
    cv = cal.get("cv_r2")
    if cv is None or cv < CAL_MIN_CV:
        # cross-validation pass nahi hui: file nahi likhte, aur purane wazan hi chalte rahenge
        return {"error": ("fit 5-fold cross-validation par poora nahi utra: in-sample R² %s, "
                          "cross-validated R² %s (n=%d). Iska matlab ye wazan aapke asli CTR ko "
                          "predict nahi kar paate — sample chhota hai ya CTR ka in features se talluq "
                          "nahi. Purane (heuristic) wazan hi chal rahe hain; data badha kar dobara try karo."
                          % (cal.get("r2"), cv, cal.get("n"))),
                "n": cal.get("n"), "r2": cal.get("r2"), "cv_r2": cv,
                "raw": cal.get("raw"), "unready": miss[:25]}
    try:
        CAL_F.parent.mkdir(parents=True, exist_ok=True)
        CAL_F.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e2:
        return {"error": "calibration.json nahi likha ja saka: " + str(e2)[:120]}
    _CALV[0] = cal
    _CALV[1] = time.time()
    return {"ok": True, "cal": cal, "unready": miss[:25]}


def start_cal():
    jid = hashlib.md5(("cal" + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": 0, "current": "apni videos ke features naap raha hoon…"}
    threading.Thread(target=_do_cal, args=(jid,), daemon=True).start()
    return {"job": jid}


def _do_cal(jid):
    job = JOBS[jid]
    try:
        r = cal_run(job)
        job["result"] = r
        job["state"] = "done" if r.get("ok") else "error"
        if not r.get("ok"):
            job["error"] = r.get("error")
    except Exception as e:
        job["state"] = "error"
        job["error"] = repr(e)[:300]



# ---------------- 5. "behtar banao" — thumbnail ko dobara banana ----------------
# Ye koi AI image nahi banata: ye US photo ko theek karta hai — purana text hataakar,
# rang/contrast sudhaar kar, subject bara karke, aur 2–4 shabd aisi jagah bade karke
# likhkar jahan khaali jagah hai. Phir wahi numbers dobara naap-ta hai, isliye
# aapko saaf dikhta hai ki behtar hua ya nahi. (AI image ke liye neeche gen_panel.)

def _font(size):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def _fit(draw, txt, maxw, maxh, stroke):
    lo, hi, best = 14, 400, 14
    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            bb = draw.textbbox((0, 0), txt, font=_font(mid), stroke_width=stroke)
        except Exception:
            return best
        if bb[2] - bb[0] <= maxw and bb[3] - bb[1] <= maxh:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def _text_bands(words, W, H):
    """OCR ke shabd aksar adhoore hote hain ("BLACK" ko "LACK" padha, ya "MYSTERY" ko
    "KLYSTERY") — isliye jo boxes ek dusari ki line me chadh rahe hain unhe ek patti (band)
    me jod deta hoon aur thori taraf chouda deta hoon. Akele shabd par kaam karne se aadha
    headline bach jaata tha (24 Oct, aankh se dekha)."""
    ws = []
    for wd in words or []:
        x, y = int(wd.get("x") or 0), int(wd.get("y") or 0)
        w, h = int(wd.get("w") or 0), int(wd.get("h") or 0)
        if w < 3 or h < 3:
            continue
        ws.append([x, y, x + w, y + h, h])
    bands = []
    for b in ws:
        hit = [g for g in bands if min(b[3], g[3]) - max(b[1], g[1]) > min(b[4], g[4]) * 0.4]
        if hit:
            g = hit[0]
            g[0] = min(g[0], b[0]); g[1] = min(g[1], b[1])
            g[2] = max(g[2], b[2]); g[3] = max(g[3], b[3])
            g[4] = max(g[4], b[4])
        else:
            bands.append(list(b))
    out = []
    for g in bands:
        hh = g[4]
        pw = int((g[2] - g[0]) * 0.06) + int(hh * 0.25)
        ph = int(hh * 0.30)
        out.append((max(0, g[0] - pw), max(0, g[1] - ph),
                    min(W, g[2] + pw), min(H, g[3] + ph), hh))
    return [b for b in out if b[2] - b[0] > 6 and b[3] - b[1] > 6]


def _face_px(faces, W, H):
    """faces_of() ke hisaab se normalized boxes ko pixel boxes me badlo, thode bahar tak
    (baal/gardan bhi) — ye ilaqa scrub me chhedna nahi chahiye."""
    out = []
    for f in faces or []:
        try:
            x, y, w, h = (float(f.get(k) or 0) for k in ("x", "y", "w", "h"))
        except Exception:
            continue
        ex, ey = w * 0.30, h * 0.40
        b = (max(0, int((x - ex) * W)), max(0, int((y - ey) * H)),
             min(W, int((x + w + ex) * W)), min(H, int((y + h + ey) * H)))
        if b[2] > b[0] and b[3] > b[1]:
            out.append(b)
    return out


def _scrub_ok(words, W, H, prot):
    """Text ki koi line chehre par chadh rahi ho to scrub bilkul mat karo.
    24 Oct ko aankh se dekha: chehre ke upar inpaint lagane se aankhein aur muh dhundhle
    pad gaye the — adhoora bacha text usse behtar hai, aur as-is card to hai hi."""
    if not prot:
        return True
    for x0, y0, x1, y1, _hh in _text_bands(words, W, H):
        for (px0, py0, px1, py1) in prot:
            if min(x1, px1) - max(x0, px0) > 0 and min(y1, py1) - max(y0, py0) > 0:
                return False
    return True


def _glyph_mask(im, words, prot=None):
    """Text ki line ke andar sirf aksharon ke pixels.
    Pehle poore box ka average background maana jaata tha — busy tasveer (chehra, nebula)
    me wo hi fail hua. AB har pixel ka apna muqami (local) background medianBlur se nikalta
    hai, isliye rang-badlaav wale ilaqe me bhi sirf akshar pakde jaate hain. Jo chehre ke
    box me aaye use mask se kaat deta hoon."""
    if cv2 is None or np is None:
        return None
    try:
        W, H = im.size
        a = np.array(im.convert("RGB"))
        m = np.zeros((H, W), np.uint8)
        hhmax = 0
        for x0, y0, x1, y1, hh in _text_bands(words, W, H):
            hhmax = max(hhmax, hh)
            reg = a[y0:y1, x0:x1]
            k = int(max(9, hh * 0.6)) | 1
            bg = cv2.medianBlur(reg, min(k, 255))
            d = np.abs(reg.astype(np.int16) - bg.astype(np.int16)).sum(axis=2)
            g = (d > 60).astype(np.uint8) * 255
            g = cv2.morphologyEx(g, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
            n, _lab, st, _c = cv2.connectedComponentsWithStats(g, 8)
            keep = np.zeros_like(g)
            mina = max(8, int(hh * hh * 0.003))
            for i in range(1, n):
                bx, by, bw, bh, area = st[i]
                if area < mina:
                    continue
                if bh > (y1 - y0) * 0.98 and bw > (x1 - x0) * 0.9:
                    continue
                keep[by:by + bh, bx:bx + bw] = 255
            m[y0:y1, x0:x1] = np.maximum(m[y0:y1, x0:x1], keep)
        for (px0, py0, px1, py1) in prot or []:
            m[py0:py1, px0:px1] = 0
        if not hhmax:
            return None
        dd = max(3, int(hhmax * 0.08))
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dd, dd)))
        for (px0, py0, px1, py1) in prot or []:
            m[py0:py1, px0:px1] = 0
        return m if int((m > 0).sum()) else None
    except Exception:
        return None


def _spell_check(want, words):
    """Aapne jo shabd maange aur OCR ne scene me se jo padha — spelling ka shak.
    24 Oct ko do case aankh se dikhe jahan model ne jo maanga tha wo bigaad diya
    ("MYSTERY" -> "KLYSTERY", "THEY LAUGHED" -> "THEY LAUGEDED"), aur score ne phir bhi
    98 de diya — kyunke score sirf bara aur padhne layak text dekhta hai, spelling nahi.
    Score ko ye check isliye nahi chhuta: OCR khud shabd ke tukde karta hai ("BLACK" ->
    "BLA"+"CK"), to ye sirf card par ishara dikhata hai, faaisla aapki aankh karti hai.
      ok    = poora shabd mila
      close = koi mukammal token (tukda nahi) qareeb hai magar barabar nahi -> shak
      miss  = wo shabd OCR ko poora nahi dikha (ya model ne likha hi nahi)
    Sirf "close" card par dikhta hai: 24 Oct ko "BLACK" ka OCR "LACK" aaya tha (B chhoot
    gaya) — yaani shabd ka tukda padha gaya, spelling nahi bigri. Isliye prefix/suffix
    tukde flag nahi hote; warna shak ki awaaz har bar uthegi aur kaam se jaayegi."""
    toks = [re.sub(r"[^a-z0-9]", "", str(wd.get("t") or "").lower()) for wd in (words or [])]
    toks = [t for t in toks if len(t) > 1]
    out = []
    for w in want or []:
        if any(t == w or (len(w) > 3 and w in t) for t in toks):
            out.append({"w": w, "st": "ok", "got": w})
            continue
        best, br = "", 0.0
        for t in toks:
            if len(t) < len(w) - 1:
                continue          # chhota token tukda ho sakta hai — iska saboot nahi
            if w.startswith(t) or w.endswith(t):
                continue          # OCR ne shabd ka sirf ek tukda padha ("BLACK" -> "LACK",
                                  # 24 Oct ko naapa) — ye spelling ka saboot nahi, isliye chhodo
            r = difflib.SequenceMatcher(None, w, t).ratio()
            if r > br:
                best, br = t, r
        # "miss" par koi token nahi batate — 0.72 se neeche ka muqabla shor hai, saboot nahi.
        out.append({"w": w, "st": "close" if br >= 0.72 else "miss",
                    "got": best if br >= 0.72 else ""})
    return out


def _dertext_hard(im, words, prot=None):
    """Thumbnail par bana text hataa kar scene wapas bhar deta hai, taake hamare apne shabd
    khaali jagah par bithaye ja sakein.
    CHETAONI (24 Oct, images dekhne ke baad): pehle ye scrub region ko sikudha hua blur tha —
    "THEY LAUGHED" wale thumbnail par headline sirf dhundhla hua, upar poora rectangle dhabba
    chhoot gaya, aur sher ke jism par box jaisa nishaan aa gaya. Matlab ye scrub sahi text ko
    bhi kharab kar sakta tha. Isliye _do_ai me ye sirf us variant par lagta hai jisme hamare
    apne shabd bithane hain — raw jaisi hai waisi card hamesha alag banti hai.
    PHIR 6 TAREEKE AANKH SE DEKHE (24 Oct): flat bharne (2x2 resize / median / gauss) se
    rectangle jaise dhabbe; poore box par inpaint se halki streak. Sabse saaf: sirf-aksharon
    ka mask + cv2.inpaint — BBC wale asli thumbnail par "HOW TO BLACK HOLE" poora gaya, black
    hole bacha raha; sher wale scene me aasman ka gradient bacha. Fail: chehre ke upar.
    Isliye chehra/chhota text jahan text line chehre par chadhe wahan scrub hota hi nahi
    (_scrub_ok), aur mask me chehre ka ilaqa kaat diya jaata hai. cv2 na ho to naram fallback."""
    try:
        if cv2 is not None:
            m = _glyph_mask(im, words, prot)
            if m is not None:
                hh = max((int(wd.get("h") or 0) for wd in (words or [])), default=10)
                rad = max(4, int(hh * 0.09))
                return Image.fromarray(cv2.inpaint(np.array(im.convert("RGB")), m, rad,
                                                   cv2.INPAINT_TELEA))
    except Exception:
        pass
    W, H = im.size
    out = im.copy()
    for wd in words or []:
        x0 = max(0, int(wd["x"] * 0.94))
        y0 = max(0, int(wd["y"] * 0.88))
        x1 = min(W, int(wd["x"] + wd["w"]) + int(wd["w"] * 0.12) + 4)
        y1 = min(H, int(wd["y"] + wd["h"]) + int(wd["h"] * 0.25) + 4)
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        try:
            out.paste(out.crop((x0, y0, x1, y1)).filter(ImageFilter.MedianFilter(11)), (x0, y0))
        except Exception:
            pass
    return out


def _grade(im, sat=1.12, sharp=True):
    o = im.convert("RGB")
    try:
        o = ImageOps.autocontrast(o, cutoff=1)
    except Exception:
        pass
    if sharp:
        try:
            # sharpening ka radius size ke saath badhta hai — 1280 par pehle jaisa hi (radius 2),
            # 2048/4K par chhota radius dhundhla reh jaata tha.
            rad = max(1.0, min(4.0, 2.0 * o.size[0] / 1280.0))
            o = o.filter(ImageFilter.UnsharpMask(radius=rad, percent=85, threshold=3))
        except Exception:
            pass
    try:
        o = ImageEnhance.Color(o).enhance(sat)
    except Exception:
        pass
    return o


def _free_cell(im, an, faces):
    """Sabse khaali jagah dhoondo jahan bara text beth sake — subject ke ult taraf."""
    W, H = im.size
    sw, sh = 3, 3
    try:
        g = im.convert("L").filter(ImageFilter.FIND_EDGES).resize((sw, sh))
        px = g.load()
    except Exception:
        return (0, int(H * 0.6), W, H)
    cog = ((an or {}).get("comp") or {}).get("cog") or [0.5, 0.5]
    best, bs = (0, int(H * 0.6), W, H), -1e18
    for cy in range(sh):
        for cx in range(sw):
            x0, x1 = int(cx * W / sw), int((cx + 1) * W / sw)
            y0, y1 = int(cy * H / sh), int((cy + 1) * H / sh)
            mass = px[cx, cy]
            s = -float(mass) * 3.0
            s += 220 if (cx < sw / 2.0) != (cog[0] < 0.5) else 0      # subject ke ult
            s += 60 if cy != 2 else 0                                  # neeche wala kona badge wala
            for f in faces or []:
                fx0, fx1 = f["x"] * W, (f["x"] + f["w"]) * W
                fy0, fy1 = f["y"] * H, (f["y"] + f["h"]) * H
                if not (x1 < fx0 or x0 > fx1 or y1 < fy0 or y0 > fy1):
                    s -= 260
            if s > bs:
                bs, best = s, (x0, y0, x1, y1)
    return best


def _put_text(im, lines, box, scrim=False):
    """Bade, outline wale shabd box ke beech me — aur local background ke hisaab se rang."""
    W, H = im.size
    x0, y0, x1, y1 = box
    pad = int(min(x1 - x0, y1 - y0) * 0.06)
    x0, y0, x1, y1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    if x1 - x0 < 40 or y1 - y0 < 30:
        return im
    d = ImageDraw.Draw(im, "RGBA")
    if scrim:
        d.rectangle([x0 - 8, y0 - 8, x1 + 8, y1 + 8], fill=(0, 0, 0, 150))
    ins = []
    try:
        px = im.convert("L").load()
        for yy in range(y0, y1, max(1, (y1 - y0) // 24)):
            for xx in range(x0, x1, max(1, (x1 - x0) // 24)):
                ins.append(px[xx, yy] / 255.0)
    except Exception:
        ins = [0.2]
    bg = pctl(ins, 0.5) if ins else 0.2
    if bg > 0.45:
        fill, stroke = (18, 18, 18), (255, 255, 255)
    else:
        fill, stroke = (255, 255, 255), (10, 10, 10)
    txt = "\n".join(lines)
    stroke_w = 0
    for _ in range(6):
        size = _fit(d, txt, x1 - x0, y1 - y0, max(2, int(stroke_w)))
        stroke_w = max(2, int(size * 0.075))
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    try:
        for dy in ((6, (0, 0, 0, 120)), (0, None)):
            off, col = dy
            d.multiline_text((cx, cy + off), txt, font=_font(size), fill=fill if col is None else col,
                             stroke_width=stroke_w, stroke_fill=stroke if col is None else (0, 0, 0, 120),
                             align="center", anchor="mm")
    except Exception:
        pass
    return im


def _split_words(words):
    ws = [w for w in re.split(r"[^\w'-]+", words or "") if w][:4]
    if not ws:
        return []
    if len(ws) == 1:
        return [ws[0]]
    mid = (len(ws) + 1) // 2
    a, b = " ".join(ws[:mid]), " ".join(ws[mid:])
    if len(a) + len(b) > 22:
        return ws[:2]
    return [a, b]


def pick_words(title, avoid=""):
    """Title me se 2–3 shabd chunno jo thumbnail par pehle se na likhe hon —
    thumbnail title ko dohrane ke liye nahi, curiosity kholne ke liye hota hai."""
    av = set(re.findall(r"[a-z0-9']+", (avoid or "").lower()))
    toks = re.findall(r"[A-Za-z0-9']+", title or "")
    seen, out = set(), []
    for t in toks:
        k = t.lower()
        if k in STOP or k in av or len(k) < 3 or k in seen:
            continue
        seen.add(k)
        out.append(t.upper() if len(k) <= 12 else t[:12].upper())
        if len(out) >= 3:
            break
    return " ".join(out)


def make_variants(path, words, an=None, ts=None, faces=None, old_words=None, prog=None):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    if max(W, H) < 640:
        im = im.resize((1280, max(1, int(1280 * H / W))), Image.LANCZOS)
        W, H = im.size
    words = (words or "").strip()
    lines = _split_words(words)
    # 24 Oct: ab purana text cv2.inpaint se jaata hai (median blur se nahi) — asli BBC
    # thumbnail par "HOW TO ... BLACK HOLE" poora gaya, black hole bacha raha. Lekin text
    # line chehre par chadhe to scrub hota hi nahi, warna chehra dhundhla ho jaata hai.
    fpx = _face_px(faces, W, H)
    scrubbed = (not old_words) or _scrub_ok(old_words, W, H, fpx)
    clean = _dertext_hard(im, old_words, fpx) if scrubbed else im
    rm = "purana text hataa kar " if scrubbed else \
        "purana text chheda nahi (wo chehre ke upar tha — scrub se chehra dhundhla hota hai), "
    jobs = []
    if lines:
        jobs.append(("bara text", rm + str(len(lines)) +
                     " line me naye shabd sabse khaali jagah par, mote outline ke saath",
                     lambda: _put_text(_grade(clean), lines, _free_cell(clean, an, faces))))
        jobs.append(("bara text + parda", "text ke peeche halka kaala parda — contrast pakka rehta hai",
                     lambda: _put_text(_grade(im), lines, _free_cell(im, an, faces), scrim=True)))
    jobs.append(("saaf grade", "sirf rang/contrast/sharpen sudhara — koi naya text nahi",
                 lambda: _grade(clean)))
    subj = (an or {}).get("subj")
    if subj and subj["w"] < 0.72 and subj["w"] > 0.12:
        jobs.append(("subject bara", "subject ko crop karke frame me bara kiya (chehra/subject CTR ka sabse bara hissa hai)",
                     lambda: _zoom(_grade(im), subj)))
    out = []
    REG_DIR.mkdir(parents=True, exist_ok=True)
    base = hashlib.md5(str(path).encode()).hexdigest()[:8]
    for i, (name, why, fn) in enumerate(jobs):
        if prog:
            try:
                prog(i, len(jobs), name)
            except Exception:
                pass
        try:
            v = fn()
            v = v.resize((1280, 720), Image.LANCZOS) if v.size != (1280, 720) else v
        except Exception:
            continue
        p = REG_DIR / ("%s_%d_%s.png" % (base, i, re.sub(r"\W", "", name)[:10]))
        try:
            v.save(p, "PNG")
        except Exception:
            continue
        van = analyse(p)
        vf = faces_of(p)
        vw = ocr_cached(p)
        vts = text_stats(p, van, vw or [], vf)
        out.append({"name": name, "why": why, "path": str(p), "an": van, "ts": vts,
                    "faces": vf, "words": vw or [], "score": score(van, vts, vf)})
    out.sort(key=lambda d: -d["score"])
    return out[:4]


def _zoom(im, subj):
    W, H = im.size
    cx = (subj["x"] + subj["w"] / 2.0) * W
    cy = (subj["y"] + subj["h"] / 2.0) * H
    w = min(W, max(W * 0.45, subj["w"] * W * 1.45))
    h = w * 9.0 / 16.0
    if h > H:
        h, w = H, H * 16.0 / 9.0
    x = max(0, min(W - w, cx - w / 2.0))
    y = max(0, min(H - h, cy - h / 2.0))
    try:
        return im.crop((int(x), int(y), int(x + w), int(y + h))).resize((1280, 720), Image.LANCZOS)
    except Exception:
        return im


def geninfo():
    """Thumbnail banane ke raste ka haal: Runware key + model list, aur local GPU/ComfyUI/model
    file — sab khud dhoondta hai."""
    g = {"gpu": None, "comfy": False, "sdexe": None, "models": [], "pillow": bool(Image)}
    try:
        rc, o, e = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], timeout=25)
        if rc == 0 and o.strip():
            g["gpu"] = o.strip().splitlines()[0]
    except Exception:
        pass
    try:
        http_get("http://127.0.0.1:8188/system_stats", timeout=3)
        g["comfy"] = True
    except Exception:
        pass
    for exe in ("sdc", "sd-cli", "stable-diffusion-cli"):
        p = shutil.which(exe)
        if p:
            g["sdexe"] = p
            break
    for pat in ("*.gguf", "*.safetensors", "*.ckpt"):
        for f in (HERE / "models").glob(pat) if (HERE / "models").exists() else []:
            g["models"].append({"f": f.name, "mb": f.stat().st_size // (1024 * 1024)})
    try:
        g["runware"] = rw_info()
    except Exception:
        g["runware"] = {"key": False, "models": []}
    return g


# ---------------- 3c. Runware: nayi thumbnail AI se (optional key, sabse sasta model) ----------------
#
# Model chunne se pehle 24 Oct ko Runware par asli 1024x576 test kiye — cost includeCost:true
# se aaya (Runware ka apna hisaab), aur "text sahi likha ya nahi" ClickLab ki APNI naapi se
# (OCR + 320px legibility + score). Natije:
#   runware:z-image@turbo     $0.0006  1.3-2s   OCR "GRAVITY" sahi, score 98   <- default
#     (yaahi model UI me 4 soch banaye: 24 Oct ki asli batch me 3 tasks $0.0006 chale, ek
#      $0.0012 — Runware ka apna hisaab. Isliye UI price range dikhata hai, aur har result
#      par asli cost likhi hoti hai.)
#   bfl:flux@3-image-klein    $0.0025  2.7s     text bigaadta hai ("GRAVI")
#   prunaai:1@1               $0.0044  3.3s     text sahi, par 7x mehnga
#   prunaai:p-image@ideogram  $0.0113  9s       text ka kachra, score 32
#   google:nano-banana@2-lite $0.0336  --       16:9 size hi support nahi
# Isliye rule wahi raha: SCENE AI se (sabse sasta model), SHABD Pillow se — text 100% sahi,
# contrast pakka, aur wohi text engine jo outline/position ka hisaab rakhta hai. "text bhi AI
# se" ka option bhi hai; benchmark khud bata dega ki wo behtar tha ya nahi.

RUNWARE = "https://api.runware.ai/v1"
KEY_FILE = HERE / "runware_key.txt"
# Pollinations — bina key ka muft tasveer rasta. Control Runware se kam hai: reference
# aur strength yahan chalta hi nahi, service bheer me ho to der kar sakti hai. Isliye
# UI isay "muft rasta" kehta hai aur history me model ka naam "Pollinations (muft)"
# likha jata hai — chupa kar Runware jaisa pesh nahi kiya jaayega.
POLL = "https://image.pollinations.ai/prompt/"
# ---- Gemini (free tier) — "model ka andaza", naap nahi ----
# Vision model thumbnail ke baare me jo kehta hai wo uski RAYE hai, paimana nahi. Ye
# numbers un cheezon ke liye hai jo ginti nahi dekh sakti (aankh pehle kahan jaati hai,
# mood kaisa lagta hai). Har output par saaf "model ka andaza" likha jayega. Key
# optional hai: env GEMINI_API_KEY → tool folder ki gemini_key.txt → UI ka key box.
# Key na ho to ye feature kaam hi nahi karta — dikhawa nahi karta.
GEM_API = "https://generativelanguage.googleapis.com/v1beta/models/"
GEM_MODEL = "gemini-3.5-flash"
# 3.x models soch (thinking) default ON rakhte hain — chhote maxOutputTokens me
# saari token soch me kharch ho kar jawab khaali aata hai. gem_call thinking off
# bhejta hai. 2.5-flash naye accounts par "no longer available" 404 deta hai
# (live test 28 Oct) — chain me rakhne se asli galti ke upar 404 ka dhuan chhata
# hai, is liye hata diya. Sahara sirf 3.8-flash hai.
GEM_MODEL_ALT = ["gemini-3.8-flash"]
GEM_IMG_MODEL = "gemini-nano-banana-2.1"
# Nano Banana 2.1 Google ka current recommended image model hai (docs 27 Oct 2026);
# hamari dono keys ki model-list me maujood hai. Limits PER-MODEL hoti hain
# (rate-limits docs), isliye gem_try 429 par bhi agle model par jaata hai —
# chain: recommended → purana flash → lite (alag quota bucket) → legacy 2.5.
GEM_IMG_ALT = ["gemini-3.1-flash-image", "gemini-3.1-flash-lite-image", "gemini-2.5-flash-image"]
GEM_KEY_FILE = HERE / "gemini_key.txt"
AI_DIR = OUT / "ai"
AI_F = OUT / "ai.json"
AIDEF = "z"
AIM = {
    "z": {"id": "runware:z-image@turbo", "name": "Z-Image Turbo", "usd": 0.0006, "hi": 0.0012,
          "note": "default — sabse sasta, 2 second, text bhi saaf"},
    "k": {"id": "bfl:flux@3-image-klein", "name": "FLUX.3 Klein", "usd": 0.0025, "hi": 0.0025,
          "note": "asli photo jaisa look; text Pillow se lagao"},
    "p": {"id": "prunaai:1@1", "name": "P-Image", "usd": 0.0044, "hi": 0.0044,
          "note": "text sabse sahi likhta hai, 7x mehnga"},
}
AIN = ("text, words, letters, sentences, captions, watermark, logo, brand mark, signature, username, "
       "blurry, soft focus, out of focus, low quality, jpeg artifacts, banding, extra fingers, six fingers, "
       "distorted face, plastic skin, dead eyes, deformed hands, clutter, busy background, too many objects, "
       "letters on clothing, random symbols, cartoon, anime, painting look, oversaturated HDR mush, vignette, "
       "black border, frame, collage artifacts, split seams")
NSHOTS = 4          # ek click me 4 ALAG soch (charon ka art direction mukhtalif) - jeetne wala benchmark khud chunta hai

# ---- size: Runware ke models ka apna sakht cap (schema se naapa) ----
#   runware:z-image@turbo  width/height 128-2048, multiples of 16  -> 2048x1152 sabse bara
#   prunaai:1@1            256-1440
#   4K (3840x2160) in models se SEEDHA nahi banta; uska ek hi rasta upscale hai (neeche UP).
# Prices 24 Oct ko usi model par naapi gayi (includeCost:true) — size ke saath price badhti hai.
# Runware ek hi model ke liye alag-alag task par alag daam leta hai (ek batch me $0.0006 aur
# $0.0012 dono dekhe), isliye har size ka NEECHE wala daam RESP aur upar wala RESPH hai.
RES = {"sd": (1024, 576), "hd": (1536, 864), "mx": (2048, 1152)}
RESP = {"sd": 0.0006, "hd": 0.0013, "mx": 0.0032}      # z-image par sabse sasti asli naapi
RESPH = {"sd": 0.0012, "hd": 0.0025, "mx": 0.0032}     # usi model par sabse mehngi asli naapi
RESL = {"sd": "1024×576 — test karne ke liye (naapa $0.0006–0.0012)",
        "hd": "1536×864 — behtar detail (naapa $0.0013–0.0025)",
        "mx": "2048×1152 — model ka maximum (naapa $0.0032)"}
# 4K: upscale model (prunaai:p-image@upscale) — naapa: 640×360 se 3842×2180 = $0.010, 13 second.
UP = "prunaai:p-image@upscale"
UPUSD = 0.010
UPMP = 8              # target megapixels = 3840×2160 level

# ---- charon ALAG art directions (user: "wider socho, bachu wale nahi") ----
# Ek hi topic, char mukhtalif camera/lens/lighting/composition soch. Har direction ka apna
# poora cinematic kaam hai — subject, lens, light, rang, aur text ke liye khaali teesra hissa.
DIRS = [
    {"n": "Hero close-up", "w": "chehra/hero subject sabse aage — feed me sabse tez dikhta hai",
     "p": ("extreme close-up of the main subject, tight crop filling the right two thirds of the frame, "
           "85mm portrait lens look at f/1.8, razor-sharp focal point on the eyes or the single hero object, "
           "creamy shallow depth of field falling into deep shadow, hard dramatic rim light from the upper left "
           "plus a soft dark fill, one gentle light bloom behind the subject, no clutter, the whole left third "
           "kept dark, calm and empty so a headline can sit there later, deep contrast, teal-and-orange "
           "cinematic grade, rich but believable saturation, fine film grain")},
    {"n": "Wide establishing", "w": "poora scene dramatic scale par — topic ki dahreed dikhata hai",
     "p": ("ultra-wide 24mm establishing shot of the whole scene at dramatic scale, a small human figure for "
           "scale, huge sky or vast environment dominating the frame, strong depth with a dark foreground element "
           "in the lower corner, golden-hour key light with long hard shadows and atmospheric haze, subject placed "
           "on the right third line, upper left kept as clean open sky for a headline, deep tonal range, cinematic "
           "colour grade, epic but instantly readable at thumbnail size")},
    {"n": "Split moment", "w": "do alag duniya ek frame me — sawal paida karta hai (CTR ka tez tareeka)",
     "p": ("dramatic split composition divided down the vertical middle of the frame: left half bright, calm and "
           "orderly, right half dark, chaotic and intense, clean hard separation line between the two halves, "
           "complementary colour clash of warm against cool, both halves readable at a single glance, one clear "
           "subject on each side, top left kept clean and quiet for a headline, hard directional light, high "
           "contrast, cinematic grade, no text anywhere")},
    {"n": "Macro detail", "w": "ek cheez ka qareebi detail — curiosity aur quality dono",
     "p": ("extreme macro close-up of the single most important object in the scene, the object placed on the "
           "right third and cropped boldly, razor-sharp surface texture with visible micro-detail, shallow focus "
           "falloff into pure darkness, one hard specular highlight tracing its edge, the left third pure negative "
           "space for a headline, hyper-detailed, zero clutter, cold dark background with a single warm light "
           "source, cinematic grade, product-photography precision")},
]
TAIL = (", professional YouTube thumbnail photography, 16:9 widescreen framing, subject instantly readable when "
        "shown three centimetres wide, strong separation between subject and background, dramatic but honest "
        "lighting, no stock-photo cliché")


# Dhange (categories) — 27 Oct: ek Hindi video ki transcript se, jisne professional designers ke
# tareeqe ek-ek karke bataye (shocking scene, bare numbers, simplicity, sawal, bara chehra, bara
# object, top-text, compare, aur pro ka asli tareeka: 2-3 categories ka MIX). Har dhanga = scene
# ki recipe (model English me behtar samajhta hai) + Roman Urdu naam + wajah. Ye IDEEIN hain —
# kisi thumbnail ka chehra/rang/layout copy karne ka hukm nahi; STYLEONLY wahi shart model ko
# samjhata hai jab reference diya ho. VIP = usi video ki design theory (rule-of-thirds, left-to-right
# aankh, max 3 elements, teen layers, palette discipline, shadows, grain) — har prompt par lagti hai.
METHODS = [
    {"k": "shock", "n": "Hairan karne wala manzar",
     "w": "ek ajeeb si cheez normal scene me — viewer ek second sochne par majboor, phir click (MrBeast ka core)",
     "p": ("one impossible, slightly wrong thing happening inside an otherwise completely normal real scene — "
           "an everyday object in a place it should never be, or an absurd pairing photographed as if it is "
           "totally real — exactly one clear absurd focal point on the right third, everything around it calm "
           "and ordinary, photojournalistic realism, hard daylight, the left third quiet and dark for a headline")},
    {"k": "bignum", "n": "Itna bara number",
     "w": "jitna bara utna acha — baray number ki dehshat (₹/$/views) hi kahani hai",
     "p": ("an enormous physical number rendered as a real object in the scene — a giant banknote stack, a "
           "towering pile, a huge counter — the number itself is the hero and fills the right half, one small "
           "human beside it for scale, awe and disbelief, crisp daylight; the giant number must be spelled "
           "correctly and read instantly at thumbnail size, everything else plain")},
    {"k": "question", "n": "Sawal chhod ke bhaago",
     "w": "adhoora lamha — jawab tasveer me nahi, isliye click karna padega",
     "p": ("a visual cliffhanger: a moment caught mid-action with the decisive second missing — a hand reaching "
           "for something just out of frame, a door half open, a before without its after — the frame asks a "
           "question it cannot answer itself, tense side lighting, deep shadows, the space where the answer "
           "would be kept dark and empty")},
    {"k": "mix", "n": "2-3 dhange ek saath (pro ka tareeka)",
     "w": "asli pro ek category nahi, kai merge karta hai — MrBeast har video ke 10 versions banwata hai",
     "p": ("one frame fusing three proven thumbnail tricks at once: a giant real number or object, a genuinely "
           "shocked human face, and one impossible-but-real situation — the layers must read in a single glance: "
           "hero on the right third, supporting element on the left third, one clear story, zero clutter, "
           "premium cinematic grade")},
    {"k": "simple", "n": "Kami hi kaafi hai (simplicity)",
     "w": "bheer me shor ke ulat — ek hi cheez, saaf scene; dimaag usse turant padh leta hai",
     "p": ("radical simplicity: one single object floating on a clean, quiet, evenly lit background, huge empty "
           "space around it, no props, no clutter, no background story — museum-exhibit lighting from one soft "
           "source, muted palette with exactly one accent colour, calm and expensive; in a noisy feed this reads "
           "as premium")},
    {"k": "bigface", "n": "Bara, asli chehra",
     "w": "kisi bare creator jaisa bara expression — magar koi copy kiya hua shakhs nahi, naya insaan",
     "p": ("a large expressive human face with a genuine strong emotion — disbelief, shock, a knowing look — "
           "placed on the right third at rule-of-thirds height, bright razor-sharp eyes, clean dark background, "
           "studio rim light from the upper left; an original person, not any known celebrity, the face alone "
           "carries the whole message")},
    {"k": "bigobj", "n": "Chhota main, bohot bara object",
     "w": "main character ko kisi bhaari object ke andar/paas — aisi cheezein normal life me nahi dikhtin",
     "p": ("the main person placed inside or beside a giant oversized everyday object that dwarfs them — a huge "
           "coin, a giant phone, a product box the size of a building — the scale contrast is the whole point, "
           "low wide angle exaggerating the object, the person small but clearly visible and expressive on the "
           "left third, photorealistic, hard light with long shadows")},
    {"k": "toptext", "n": "Upar title-jaisa khula hissa",
     "w": "top par headline baithne layak saaf patti — title se linked text ka structure (likhta tool khud hai)",
     "p": ("a clean, dark, calm band kept empty across the top of the frame, reserved for a headline, with the "
           "subject anchored below it on the right third — the composition is built so a linked headline can sit "
           "on top; strong tonal separation between the subject and the quiet band, cinematic grade")},
    {"k": "compare", "n": "Cheez vs cheez",
     "w": "sasta vs mehnga, purana vs naya — same angle, farak inkaar ke qabil na rahe",
     "p": ("a hard split down the middle of the frame comparing two extremes of the same thing — cheap versus "
           "expensive, old versus new, tiny versus huge — left side visibly duller and worse, right side "
           "brighter and better, the exact same camera angle on both sides so the difference is undeniable, "
           "warm clashing against cool, high contrast")},
]
VIP = (", design discipline of a top thumbnail studio: rule-of-thirds placement, the first thing the viewer "
       "must see sits left of centre because eyes scan thumbnails left to right, never more than three elements "
       "in the frame, three balanced depth layers (foreground, midground, background), palette locked to one "
       "dominant colour plus black, grey and white for contrast plus exactly one complementary accent, generous "
       "soft drop shadows under hero elements because shadows are what give a thumbnail its life, subtle film "
       "grain and fine texture so it reads printed and premium, expensive editorial retouching, nothing amateur")
STYLEONLY = (", the reference image is inspiration for its IDEA AND COMPOSITION ONLY: use a completely different "
             "face and subject, completely different colours and a different layout — borrow the trick, never "
             "trace or copy the person, the palette or the arrangement")


def rw_key():
    """Key: pehle env RUNWARE_API_KEY, phir tool folder ki runware_key.txt. Dono na ho to
    tool bina AI ke poora chalta hai (⚡ Tier A ko kisi key ki zaroorat nahi)."""
    k = (os.environ.get("RUNWARE_API_KEY") or "").strip()
    if not k:
        try:
            k = (KEY_FILE.read_text(encoding="utf-8-sig") or "").strip().splitlines()[0].strip()
        except Exception:
            k = ""
    return k


def rw_set(k):
    k = (k or "").strip()
    if not k:
        try:
            if KEY_FILE.exists():
                KEY_FILE.unlink()
        except Exception:
            pass
        return {"ok": True, "set": False}
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(k + "\n", encoding="utf-8")
    return {"ok": True, "set": True, "hint": k[:5] + "…" + k[-3:]}


def rw_info():
    k = rw_key()
    ms = [{"k": kk, "name": v["name"], "id": v["id"], "usd": v["usd"], "hi": v.get("hi", v["usd"]),
           "note": v["note"]} for kk, v in AIM.items()]
    lo = AIM[AIDEF]["usd"] * NSHOTS
    hi = AIM[AIDEF].get("hi", AIM[AIDEF]["usd"]) * NSHOTS
    rs = [{"k": kk, "label": RESL[kk], "w": v[0], "h": v[1], "usd": RESP[kk], "hi": RESPH[kk],
           "x": round(RESPH[kk] / RESP["sd"], 1)} for kk, v in RES.items()]
    return {"key": bool(k), "hint": (k[:5] + "…" + k[-3:]) if k else "", "file": str(KEY_FILE),
            "models": ms, "def": AIDEF, "shots": NSHOTS, "batch": round(lo, 5),
            "batch_hi": round(hi, 5), "res": rs, "defres": "sd",
            "up": {"model": UP, "usd": UPUSD, "mp": UPMP, "out": "3840×2160 level"},
            "gem": bool(gem_key()), "gemn": len(gem_keys()), "gemmodel": GEM_MODEL, "gemimg": GEM_IMG_MODEL,
            "agy": bool(agy_bin()),
            "ocr_gem": bool(OCR_GEM and gem_keys()), "ocr_gem_on": bool(OCR_GEM),
            "dirs": [{"n": d["n"], "w": d["w"]} for d in DIRS],
            "methods": [{"k": x["k"], "n": x["n"], "w": x["w"]} for x in METHODS],
            "strdef": 0.55}


def rw_call(model, prompt, neg="", w=1024, h=576, ref="", tmo=150, strength=None):
    """Runware ka ek image request. Sirf FLAT shape chalta hai (inputs/settings nested bhejo to
    'missingParameter positivePrompt' aata hai). Size: 128-2048, multiples of 16 (schema se naapa).
    Reference ke liye: `seedImage` + `strength` — NAPE ka farak (24 Oct, z-image, same prompt):
        koi ref nahi      -> ref se farak 0.134    (image ka koi asar nahi)
        imageUrls bheja   -> farak 0.155           (ye param is model par ASAR ANDAAZ nahi karta!)
        seedImage 0.3     -> farak 0.013           (ref se bahut qareeb)
        seedImage 0.55    -> farak 0.031           (inspired, naya)   <- default
        seedImage 0.85    -> farak 0.092           (bas naya, ref ka rang-roop chala jaata hai)
    Isliye yahan seedImage use hota hai, imageUrls nahi."""
    item = {"taskType": "imageInference", "taskUUID": str(uuid.uuid4()), "model": model,
            "positivePrompt": prompt, "width": w, "height": h, "outputFormat": "jpeg",
            "includeCost": True}
    if neg:
        item["negativePrompt"] = neg
    if ref:
        item["seedImage"] = ref
        item["strength"] = round(max(0.05, min(0.95, float(strength if strength is not None else 0.55))), 2)
    body = [{"taskType": "authentication", "apiKey": rw_key()}, item]
    req = urllib.request.Request(RUNWARE, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": "clicklab"})
    try:
        with urllib.request.urlopen(req, timeout=tmo) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return {"error": "Runware HTTP " + str(e.code)}
    except Exception as e:
        return {"error": "Runware se baat nahi hui (net check karo): " + str(e)[:140]}
    er = j.get("errors") or []
    if er:
        return {"error": str((er[0] or {}).get("message") or "Runware error")[:220]}
    d = (j.get("data") or [{}])[0]
    u = d.get("imageURL") or (d.get("imageUrls") or [""])[0]
    if not u:
        return {"error": "Runware ne image nahi di"}
    return {"url": u, "cost": d.get("cost")}


def ai_prompt(idea, words="", text_ai=False, di=0, meth="", refmode=False, nb=False):
    """Poora, detail kaam — ek line ka generic prompt nahi. Teen hisse:
       1) subject: kya dikhana hai (user ka idea, jo video ke ASLI title/tags se bhara jaata hai)
       2) us direction ka poora cinematic kaam: lens, light, composition, rang, khaali teesra hissa
       3) text ka rule: shabd ya to Pillow lagayega (default) ya AI se, aur phir bhi ek hi headline. text_ai=False me "no text" ki poori koshish hoti hai taaki Pillow wale shabd khaali jagah baithen.
          SAHIH BAAT (24 Oct, images aankh se dekhne ke baad): pehle main kehta tha ye model 7-13 "nakli akhshar" khud bana deta hai — wo GALAT tha. Wo ginti OCR ki thi aur jo shabd gin rahe the wo model ne SAHI likhe the. Isliye _do_ai me raw jaisi hai waisi ek variant banti hai, aur scrub + apne shabd wala dusra — faaisla benchmark aur user ki aankh karti hai, OCR ki ginti nahi."""
    s = re.sub(r"\s+", " ", (idea or "").strip())[:300]
    if not s:
        return ""
    mo = next((x for x in METHODS if x["k"] == meth), None)
    d = mo or DIRS[int(di) % len(DIRS)]
    if text_ai:
        if nb:
            # Nano Banana (Gemini/Antigravity) ka poora thumbnail prompt: text shuru se
            # design ka hissa hai, prompt ke aakhir me juda hua hukam nahi — 28 Oct ki
            # agy batch me text-wale card par bilkul text nahi aaya tha, kyunke headline
            # ka hukam lambe prompt ke bilkul aakhir me tha aur model ne use ignore kar
            # diya. In models ko natural, mukammal instruction behtar samajh aata hai.
            p = ("Design a complete YouTube thumbnail artwork (not a plain photograph): a bold, "
                 "high-contrast, eye-catching scene about: " + s + ". The headline is part of the "
                 "design from the first pixel: render the exact words \"" + (words or s)[:40] +
                 "\" as huge thick condensed block letters with a heavy dark outline, spelled "
                 "letter-perfect, placed in the darkest empty third of the frame where they stay "
                 "fully readable even at small size. That headline is the ONLY text anywhere in the "
                 "artwork — no watermark, no logo, no other words.") + " " + d["p"] + TAIL + VIP
        else:
            p = "a YouTube thumbnail photograph about: " + s + ". " + d["p"] + TAIL + VIP
    else:
        # "no text" ki shart yahan isliye hai taaki jo scene bane us par Pillow wale
        # shabd khaali, geheri jagah baithen — warna wo AI ke khud likhe hue headline se
        # takra jaate hain. (24 Oct ki purani comment kehti thi ki model har scene me 8-11
        # bikhre hue akhshar "bana hi deta hai" — wo OCR ginti ka jhoot tha, images dekhne
        # par pata chala ki wo shabd SAHI the.) ASLI wajah jo ab bhi sach hai: idea me
        # title/thumbnail ke shabd hote hain — model unhe tasveer me likh deta hai. Isliye
        # yahan wo hissa kaat diya jaata hai aur topic ko "subject, words to draw nahi" bol
        # kar diya jaata hai.
        s2 = re.sub(r"(thumbnail par likha hua|text on thumb|on the thumbnail|jo likha hua)[^;|]*",
                    "", s, flags=re.I).strip(" -,.")
        bn = bool(mo and mo["k"] == "bignum")  # baray number wale dhangay me number hi hero hai, "no numbers" us par lagu nahi
        p = ("a clean photograph with absolutely no text, no words, no letters, no letterforms, "
             + ("" if bn else "no numbers, ") +
             "no captions, no subtitles, no watermark, no signage, no logos anywhere "
             "in the frame. The subject of this photograph (a thing to SHOW, not words to draw) is: "
             + s2 + ". " + d["p"] + TAIL + VIP +
             " remember: the topic appears only as objects and scene, never as lettering; "
             "zero letterforms anywhere, the empty third stays truly empty and dark"
             + (", the single giant number is the only numerals allowed and it is spelled perfectly" if bn else ""))
    if refmode:
        p += STYLEONLY
    if text_ai and words and not nb:
        p += (", the only text in the image is one short headline in huge thick condensed block letters with a "
              "heavy dark outline, spelled exactly and perfectly legible, saying: \"" + words[:40] + "\"")
    elif not (text_ai and nb):
        # nb + text_ai ka headline prompt ke andar hi hai — yahan "no text" jodna us se takraata
        p += (". absolutely no text, no words, no letters, no numbers, no captions, no watermark, no signage "
              "anywhere in the frame; the empty third must stay truly empty and dark")
    return p[:1900]


def img_datauri(path, maxside=2048, q=92):
    """Local file -> data URI (Runware `inputs.image` / `seedImage` yahi khaata hai)."""
    if not Image:
        return ""
    try:
        im = Image.open(path).convert("RGB")
        if max(im.size) > maxside:
            sc = maxside / float(max(im.size))
            im = im.resize((int(im.size[0] * sc), int(im.size[1] * sc)), Image.LANCZOS)
        import io
        b = io.BytesIO()
        im.save(b, "JPEG", quality=q)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return ""


def ai_ref(ref):
    """Apni thumbnail chhota jpeg bana kar data-URI — model ko scene ka idea dene ke liye."""
    p, _e = resolve_ref(ref)
    if not p:
        return ""
    return img_datauri(p, 1024, 85)


def _px(path):
    im = Image.open(path).convert("L").resize((64, 36), Image.LANCZOS)
    return list(im.getdata())


def _hist(path):
    from collections import Counter
    im = Image.open(path).convert("HSV").resize((96, 54), Image.LANCZOS)
    c = Counter()
    for r, g, b in im.getdata():
        c[(r // 32, g // 64, b // 64)] += 1
    t = float(sum(c.values())) or 1.0
    return {k: v / t for k, v in c.items()}


def imgdiff(p1, p2):
    """Do tasveeron ka farak (0-100): px = banawas ka farak, col = rang-roop ka farak.
    'inspired, copy nahi' ka ye matlab hai — legal faisla insaan ka, naap hamara."""
    try:
        a, b = _px(p1), _px(p2)
        px = round(sum(abs(x - y) for x, y in zip(a, b)) / len(a) / 255.0 * 100)
        ha, hb = _hist(p1), _hist(p2)
        ks = set(ha) | set(hb)
        col = round(sum(abs(ha.get(k, 0.0) - hb.get(k, 0.0)) for k in ks) / 2 * 100)
        return {"px": px, "col": col}
    except Exception:
        return None


def rw_up4(img, mp=UPMP):
    """Runware ka ASLI upscale (taskType 'upscale'). Naapa: 640×360 se 3842×2180 = $0.010, 13 second.
    Model ka apna cap 2048 px hai — 4K ka sirf yahi asli rasta hai."""
    item = {"taskType": "upscale", "taskUUID": str(uuid.uuid4()), "model": UP,
            "inputs": {"image": img}, "targetMegapixels": int(mp), "outputType": "URL",
            "includeCost": True}
    body = [{"taskType": "authentication", "apiKey": rw_key()}, item]
    req = urllib.request.Request(RUNWARE, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": "clicklab"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return {"error": "Runware HTTP " + str(e.code)}
    except Exception as e:
        return {"error": "Runware se baat nahi hui: " + str(e)[:140]}
    er = j.get("errors") or []
    if er:
        return {"error": str((er[0] or {}).get("message") or "upscale error")[:220]}
    d = (j.get("data") or [{}])[0]
    u = d.get("imageURL") or (d.get("imageUrls") or [""])[0]
    if not u:
        return {"error": "upscale ne image nahi di"}
    return {"url": u, "cost": d.get("cost")}


def up4(src, mode="ai"):
    """4K master do raston par: 'ai' = Runware ka asli upscale (paid, detail paida hoti hai),
    'free' = Pillow Lanczos (muft, bas tasveer badi hoti hai). Dono ka sharpness NAAP kar dikhata
    hai — farak chupa nahi jaayega."""
    p, err = resolve_ref(src)
    if not p:
        return {"error": err or "file nahi mila"}
    if not Image:
        return {"error": "Pillow nahi mila"}
    AI_DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"\W", "", Path(p).stem)[:30] or "img"
    out = AI_DIR / ("%s_%s_4k.jpg" % (stem, mode))
    cost = 0.0
    if mode == "ai":
        if not rw_key():
            return {"error": "is raste ke liye Runware key chahiye (~$0.010). Muft wala rasta neeche hai."}
        r = rw_up4(img_datauri(p, 2048, 92))
        if r.get("error"):
            return r
        try:
            out.write_bytes(http_get(r["url"], timeout=240))
        except Exception as e:
            return {"error": "upscaled image download nahi hua: " + str(e)[:100]}
        cost = float(r.get("cost") or 0)
    else:
        try:
            im = Image.open(p).convert("RGB")
            w = 3840
            h = max(1, int(round(w * im.size[1] / float(im.size[0]))))
            im.resize((w, h), Image.LANCZOS).save(out, "JPEG", quality=94)
        except Exception as e:
            return {"error": "muft upscale fail: " + str(e)[:120]}
    try:
        im2 = Image.open(out)
        W, H = im2.size
    except Exception:
        W = H = 0
    an = analyse(str(out))
    return {"ok": True, "path": str(out), "w": W, "h": H, "mode": mode, "usd": round(cost, 5),
            "sharp": an.get("sharp"), "src": str(p), "model": UP if mode == "ai" else "Pillow Lanczos"}


def load_ai():
    try:
        return json.loads(AI_F.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_ai(v):
    AI_F.parent.mkdir(parents=True, exist_ok=True)
    AI_F.write_text(json.dumps(v[:60], ensure_ascii=False, indent=1), encoding="utf-8")


def poll_get(prompt, w, h):
    """Pollinations se ek tasveer — koi key nahi. Free community service hai, isliye
    control kam: reference/strength yahan bheja hi nahi jaata. Jo size maango utna hi
    maangta hai; tasveer native hi save hoti hai (sikodi nahi jaati)."""
    seed = uuid.uuid4().int % 1000000
    u = (POLL + urllib.parse.quote(prompt[:1500]) +
         "?width=%d&height=%d&nologo=true&seed=%d" % (int(w), int(h), int(seed)))
    return http_get(u, timeout=240)


def _keypool(env_names, path):
    """Keys ka pool: pehle env vars, phir file ki har non-khaali line (ek line = ek key).
    Same key do baar pool me nahi aati. 11 accounts ki 11 keys ek saath paste karne ke liye."""
    ks = []
    for n in env_names:
        k = (os.environ.get(n) or "").strip()
        if k and k not in ks:
            ks.append(k)
    try:
        if path.exists():
            for ln in path.read_text(encoding="utf-8-sig").splitlines():
                k = ln.strip().strip(",;").strip()
                if k and k not in ks:
                    ks.append(k)
    except Exception:
        pass
    return ks


def _keysave(path, text, add=False):
    """Pool save karta hai: ek line = ek key; comma-separated paste bhi split ho jaata hai.
    add=True par file ki purani lines ke neeche jud jaati hain (duplicate apne aap chhoot
    jaate hain) — 11 nayi keys add karne ke liye yehi rasta hai. Khaali text aur add=False
    → file hata do."""
    out = []
    if add:
        try:
            if path.exists():
                for ln in path.read_text(encoding="utf-8-sig").splitlines():
                    k = ln.strip().strip(",;").strip()
                    if k and k not in out:
                        out.append(k)
        except Exception:
            pass
    for ln in (text or "").replace(",", "\n").replace(";", "\n").splitlines():
        k = ln.strip()
        if k and k not in out:
            out.append(k)
    if not out:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        return {"ok": True, "set": False, "n": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return {"ok": True, "set": True, "n": len(out), "hint": out[0][:6] + "…" + out[0][-3:]}


def gem_keys():
    return _keypool(["GEMINI_API_KEY"], GEM_KEY_FILE)


def gem_key():
    """Gemini key: env GEMINI_API_KEY, phir folder ki gemini_key.txt. Free tier par bhi
    apni chhoti si daily limit hoti hai, isliye key ki zaroorat padti hai.
    File me kai lines ho sakti hain — pool me se pehli key status/preview ke liye."""
    ks = gem_keys()
    return ks[0] if ks else ""


def gem_set_key(k, add=False):
    return _keysave(GEM_KEY_FILE, k, add)


_gem_cur = [0]  # round-robin cursor: pichhli kaamyabi wahi se aage chalu hoti hai


def gem_call(model, parts, maxtok=1500, temperature=0.4, mods=None, timeout=120):
    """Gemini ka ek generateContent call. mods=['TEXT','IMAGE'] wale model tasveer bhi
    de sakte hain. Jawab JSON me nahi, text ya image bytes me milta hai.

    Kai keys pool me ho sakti hain (ek line = ek key): ek account ki limit khatam hone par
    (HTTP 403/429 ya khaali jawab) agla key apne aap azmaata hai — user ko kuch nahi karna."""
    ks = gem_keys()
    if not ks:
        return {"error": "Gemini key set nahi — env GEMINI_API_KEY, gemini_key.txt, ya UI ka key box."}
    gc = {"maxOutputTokens": int(maxtok), "temperature": temperature,
          "thinking_config": {"thinking_budget": 0}}  # 3.x ki soch chhote jawab ko khaali na kare
    if mods:
        gc["responseModalities"] = list(mods)
    body = json.dumps({"contents": [{"role": "user", "parts": parts}], "generationConfig": gc}).encode()
    n = len(ks)
    last = {"error": "Gemini se baat nahi hui"}
    for i in range(n):
        idx = (_gem_cur[0] + i) % n
        url = GEM_API + model + ":generateContent?key=" + urllib.parse.quote(ks[idx])
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": "clicklab"})
        try:
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    j = json.loads(r.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e0:
                m0 = ""
                try:
                    m0 = str(((json.loads(e0.read().decode("utf-8", "replace")).get("error") or {}).get("message")) or "")
                except Exception:
                    pass
                if e0.code == 400 and "thinking" in m0.lower():
                    # is model ko thinking_config manzoor nahi — bina uske ek baar azmao
                    gc.pop("thinking_config", None)
                    req = urllib.request.Request(
                        url, data=json.dumps({"contents": [{"role": "user", "parts": parts}],
                                              "generationConfig": gc}).encode(),
                        headers={"Content-Type": "application/json", "User-Agent": "clicklab"})
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        j = json.loads(r.read().decode("utf-8", "replace"))
                else:
                    raise
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                msg = str(((json.loads(e.read().decode("utf-8", "replace")).get("error") or {}).get("message")) or "")[:200]
            except Exception:
                pass
            last = {"error": "Gemini HTTP %d%s" % (e.code, (": " + msg) if msg else "")}
            if n > 1 and (e.code in (403, 429) or (e.code == 400 and "api key" in msg.lower())):
                continue  # limit khatam ya key kharab — agla key azmao (400 me sirf key-wali baat par)
            return last
        except Exception as e:
            return {"error": "Gemini se baat nahi hui: " + str(e)[:140]}
        cand = (j.get("candidates") or [{}])[0]
        txt = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if p.get("text"))
        img = None
        for p in (cand.get("content") or {}).get("parts", []):
            d = p.get("inlineData") or p.get("inline_data") or {}
            if d.get("data"):
                try:
                    img = base64.b64decode(d["data"])
                except Exception:
                    img = None
                break
        if not txt and not img:
            if n > 1:
                continue  # free tier limit ke waqt khaali jawab aata hai — agla key azmao
            return {"error": "Gemini ne jawab khaali bheja — pool ki %d keys ki daily limit khatam ho sakti hai ya model ka naam badal gaya ho" % n}
        _gem_cur[0] = idx
        return {"text": txt, "img": img}
    return last


def gem_try(cands, parts, **kw):
    """Models ek kram me try karo: ek par 404 (model uplabdh nahi), 503 (model abhi
    vyast), read-timeout (model jawab de hi nahi raha — atka hua) ya 429 us model ki
    apni daily limit khatam (limits per-model hoti hain — agle model ke paas abhi bhi
    quota ho sakta hai; gem_call ne pool ki SAARI keys us model par azma li hain) —
    in par agle model par jao. Baaki galti (kharab key/network cut) par wahi error
    lautata hoon — use model badal ke chhupana nahi."""
    last = None
    errs = []
    for m in cands:
        r = gem_call(m, parts, **kw)
        if not r.get("error"):
            r["model"] = m
            return r
        e = str(r.get("error")).lower()
        errs.append("%s → %s" % (m, str(r.get("error"))[:80]))
        if "http 404" in e or "http 503" in e or "timed out" in e or "http 429" in e:
            last = r
            continue
        return r
    if last is not None and len(errs) > 1:
        # poori zanjeer fail hui to aakhri error se pehli asli galti chhupana
        # nahi — user ko poora raasta dikhana hai (honest errors rule).
        last = dict(last)
        last["error"] = "Gemini ke model kaam na kar sake: " + " | ".join(errs)
    return last or {"error": "Gemini ka koi model jawab na de saka"}


GEM_LOOK_ASK = (
    "You are reviewing ONE YouTube thumbnail. Title (may be empty): __TITLE__\n"
    "Answer in Roman Urdu (Hinglish), blunt, no praise padding, max 180 words. "
    "Use exactly these 5 headings, one line each:\n"
    "1) PAHLI NAZAR: in the first 2 seconds the eye lands on ___ (say what, and whether that is the right thing to see)\n"
    "2) CHHOTE SIZE PAR: at 210px mobile-feed size, is the text readable, and what does it say\n"
    "3) MOOD: what emotion this thumbnail projects, in 3 words\n"
    "4) TITLE SE MISMATCH: anything the title promises that the thumbnail hides, if any\n"
    "5) EK SABSE BADA FIX: the single change that would most raise click-through, concrete\n"
    "If you are guessing rather than certain, write 'andaza' next to that line. "
    "This is a model opinion, not a measurement — do not invent numbers.")


def gem_look(ref, title=""):
    """Thumbnail dikha kar Gemini se 5-sawal ka feedback. Label hamesha 'model ka andaza'."""
    p, err = resolve_ref(ref)
    if not p:
        return {"error": err or "file nahi mila"}
    du = img_datauri(p, 1024, 85)
    parts = [{"text": GEM_LOOK_ASK.replace("__TITLE__", (title or "(koi title nahi diya)")[:200])},
             {"inlineData": {"mimeType": "image/jpeg", "data": du.split(",", 1)[1]}}]
    r = gem_try([GEM_MODEL] + GEM_MODEL_ALT, parts, maxtok=1200, temperature=0.4)
    if r.get("error"):
        return r
    return {"ok": True, "text": (r.get("text") or "").strip(), "model": r.get("model") or GEM_MODEL}


def gem_gen(prompt, w, h):
    """Gemini ke image model se ek tasveer (free tier, apni key par). Size ka control
    Runware jitna sakht nahi — model qareebi aspect deta hai, jo aaye wahi save hota hai."""
    parts = [{"text": "Generate one image: " + prompt[:1500] +
              ". Output aspect ratio 16:9 landscape, target size %dx%d." % (int(w), int(h))}]
    r = gem_try([GEM_IMG_MODEL] + GEM_IMG_ALT, parts, maxtok=2048, temperature=0.9, mods=["TEXT", "IMAGE"])
    if r.get("error"):
        return r
    if not r.get("img"):
        return {"error": "Gemini ne tasveer nahi bheji (text hi aaya) — free tier par ye ho sakta hai"}
    return {"bytes": r["img"]}


def gem_edit(ref, instruction):
    """Gemini ke image model ko USKI BHEJI TASVEER ke saath instruction — model wahi
    scene edit karke lautata hai (Tier A ka doosra rasta: marammat model se).
    Size ka control model ke reham par hai — 16:9 kaha jaata hai, qareebi aspect aata
    hai; jo aaya wahi save hota hai aur ClickLab ki apni engine se naapa jaata hai."""
    p, err = resolve_ref(ref)
    if not p:
        return {"error": err or "file nahi mila"}
    du = img_datauri(p, 1024, 85)
    if not du:
        return {"error": "thumbnail model ko bheja hi nahi ja saka"}
    parts = [{"text": "This is a YouTube thumbnail. " + instruction[:900] +
              " Output one image only, 16:9 landscape."},
             {"inlineData": {"mimeType": "image/jpeg", "data": du.split(",", 1)[1]}}]
    r = gem_try([GEM_IMG_MODEL] + GEM_IMG_ALT, parts, maxtok=2048, temperature=0.85, mods=["TEXT", "IMAGE"])
    if r.get("error"):
        return r
    if not r.get("img"):
        return {"error": "Gemini ne is baar tasveer nahi lautayi (sirf text aaya)"}
    return {"bytes": r["img"], "model": r.get("model") or GEM_IMG_MODEL}


# ---- Antigravity CLI: Google AI subscription ka jugad (API key ki zaroorat nahi) ----
# 27 Oct 2026, live test: Google ki official policy hai ke AI Pro/Ultra subscription ka quota
# API keys par LAGU NAHI hota — wo sirf Gemini app / AI Studio / Antigravity me chalta hai.
# Antigravity CLI (agy) usi subscription se login karta hai (ek baar Google OAuth), aur uska
# built-in image tool Nano Banana 2 use karta hai (docs: /docs/models "Additional models").
# Quota: Pro/Ultra par har 5 ghante refresh + weekly limit; limit "kaam" (tokens) se gini jaati
# hai — is liye ek tasveer ~1 minute aur kaafi quota kha jaati hai. Ye rasta tab behtar hai
# jab API keys ki free-limit khatam ho aur 1-2 tasveeren foran chahiye; bade batch ke liye
# Runware tez aur sasta hai. Headless contract (docs/cli/headless + apna live test):
#   agy -p <prompt> --output-format json  -> ek JSON envelope: {status, response, error, ...}
#   agent file khud likhta hai — humein absolute path de kar usi file ka byte uthana hai.
AGY_CACHE = {"p": None, "t": 0.0}


def agy_bin():
    """agy executable dhoondo (PATH ya standard install dir); na mile to None."""
    now = time.time()
    if AGY_CACHE["p"] is not None and now - AGY_CACHE["t"] < 600:
        return AGY_CACHE["p"]
    p = shutil.which("agy") or shutil.which("agy.exe") or shutil.which("agy.cmd")
    if not p:
        la = os.environ.get("LOCALAPPDATA") or ""
        if la:
            cand = Path(la) / "agy" / "bin" / "agy.exe"
            if cand.exists():
                p = str(cand)
    AGY_CACHE["p"] = p
    AGY_CACHE["t"] = now
    return p


def agy_gen(prompt, w, h):
    """Antigravity agent se ek tasveer (uska image tool = Nano Banana 2) — subscription
    quota, bina API key. Agent file disk par likhta hai; hum use exact path de dete hain
    aur baad me wahi byte utha lete hain. Slow hai (~60s) is liye timeout sakht hai."""
    b = agy_bin()
    if not b:
        return {"error": "Antigravity CLI (agy) is machine par nahi mila — ek baar install karo "
                         "(PowerShell): irm https://antigravity.google/cli/install.ps1 | iex — "
                         "phir ek baar `agy` khol kar us Google account se login karo jis par "
                         "Google AI subscription hai. Uske baad ye rasta bina kisi key ke chalta hai."}
    AI_DIR.mkdir(parents=True, exist_ok=True)
    out = AI_DIR / ("_agy_%s.jpg" % hashlib.md5((prompt + str(dt.datetime.now())).encode()).hexdigest()[:10])
    ask = ('Use your generative image capability to create exactly one image for this description: '
           + prompt[:1500] + '. Aspect ratio 16:9 landscape, target %dx%d (a YouTube thumbnail). ' % (int(w), int(h))
           + 'After it is generated, make sure the final image file exists at exactly this absolute path: "'
           + str(out) + '" (PNG or JPEG both fine). Do not create any other files. Then reply with exactly: IMGSAVED '
           + str(out))
    try:
        # Pipe capture Windows par atakta hai: agy ka background daemon (node) stdout handle
        # inherit kar leta hai aur child ke marne ke baad bhi pipe EOF nahi hoti — communicate
        # hamesha ke liye atak jaata hai (live 28 Oct: batch 1/4 par 10 min stuck). Isliye
        # output file me likhwate hain: file padhne ke liye kisi handle ke band hone ka
        # intezaar nahi karna padta. stdin DEVNULL = koi interactive prompt atakayega nahi.
        ofp = str(out) + ".out"
        with open(ofp, "w", encoding="utf-8", errors="replace") as ofh:
            r = subprocess.run([b, "-p", ask, "--output-format", "json",
                                "--dangerously-skip-permissions", "--print-timeout", "4m"],
                               stdin=subprocess.DEVNULL, stdout=ofh, stderr=subprocess.DEVNULL,
                               timeout=300, cwd=str(AI_DIR))
        try:
            sout = open(ofp, encoding="utf-8", errors="replace").read()
            os.remove(ofp)
        except Exception:
            sout = ""
    except subprocess.TimeoutExpired:
        out.unlink(missing_ok=True)
        return {"error": "Antigravity ne 5 minute me tasveer nahi di — agent slow tha, dobara try karo"}
    except Exception as e:
        return {"error": "agy chal hi nahi saka: " + str(e)[:120]}
    env = {}
    for ln in (sout or "").splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                env = json.loads(ln)
            except Exception:
                pass
    if not out.exists():
        em = (env.get("error") or "").strip()
        out.unlink(missing_ok=True)
        return {"error": "Antigravity se tasveer ki file nahi bani" +
                         (": " + em[:150] if em else (" (agy exit %d — login bhaag gaya to `agy` khol kar dobara sign-in karo)" % r.returncode))}
    try:
        raw = out.read_bytes()
        out.unlink(missing_ok=True)
    except Exception as e:
        return {"error": "tasveer file padhi nahi ja saki: " + str(e)[:80]}
    if len(raw) < 1000:
        return {"error": "Antigravity ki file bohot chhoti thi (asli tasveer nahi bani)"}
    return {"bytes": raw, "model": "nano-banana-2 (antigravity)"}


# ---- Gemini: gehri CTR analysis (model ki raye, naap nahi — label UI me saaf) ----
# Pehla gem_look 5 sawal ka chhota feedback tha. Ye poora jaiza hai: har wo pehlu
# alag alag jancha jaye jo click jeetata hai (pehli nazar, chehra, 210px par text,
# rang, bant-khabar, tajassus, title-se-milan), phir usi video ke liye zyada
# chalne wale title aur qareebi behtar topics. Jawab sakht JSON me maanga gaya hai
# taaki UI factor-table bana sake; JSON na bane to raw jawab dikha jaayega.
GEM_DEEP_ASK = (
    "You are a ruthless YouTube CTR strategist studying ONE thumbnail in extreme depth. "
    "Title of the video (may be empty): __TITLE__\n"
    "Judge it the way viewers actually see it: a ~210px-wide mobile feed tile glanced at for 0.3 seconds. "
    "Examine EVERY factor that decides whether this thumbnail wins the click. Be concrete — point at what "
    "sits where in this frame; never give generic advice that would fit any thumbnail.\n"
    "Factors — use exactly these keys, all seven, in this order:\n"
    "first_glance: where the eye lands in the first 0.3s and whether that is the right thing to see\n"
    "face_emotion: face/hero-subject presence, expression, gaze, size in frame\n"
    "text_210px: which exact words survive at 210px, their size, outline, contrast, how many\n"
    "color_contrast: palette clash, subject/background separation, grade quality\n"
    "composition: thirds, negative space, clutter, framing of the hero element\n"
    "curiosity_gap: what question the image plants, and whether the answer stays withheld\n"
    "title_match: what the title promises vs what the image shows — pure repeat, or a gap?\n"
    "Then: the 3 things that are genuinely working, then the 3 things killing the most clicks ordered by damage.\n"
    "Then write 5 ALTERNATIVE TITLES for this same video that would out-click the given one: same honest "
    "topic, nothing the video cannot deliver, under 60 characters, in the SAME LANGUAGE as the given title "
    "(if no title was given, use the language the thumbnail's text is in).\n"
    "Then 3 ADJACENT TOPIC ANGLES that could outperform this video for the same audience, each with a one-line angle.\n"
    "All human-readable strings in Roman Urdu (Hinglish), blunt, no praise padding, no invented numbers except "
    "the 0-10 factor scores. s is an integer 0-10 per factor.\n"
    "Return ONLY minified valid JSON, no markdown fences, exactly this shape:\n"
    '{"factors":[{"k":"first_glance","s":7,"why":"...","fix":"..."} (all 7 keys in order)],'
    '"strengths":["...","...","..."],"killers":["...","...","..."],"verdict":"max 2 lines",'
    '"titles":[{"t":"...","why":"..."} x5],"topics":[{"t":"...","angle":"..."} x3]}')


def _json_block(txt):
    """Model ke jawab se JSON nikalo: code fences aur aage-peeche ki harkat bardasht.
    Parse na ho to None — jawab raw dikhaya jaayega, chhupaya nahi jaayega."""
    t = (txt or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.M).strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        j = json.loads(t[a:b + 1])
    except Exception:
        return None
    return j if isinstance(j, dict) else None


def gem_deep(ref, title=""):
    """Gemini se thumbnail ki gehri CTR-analysis + us video se zyada chal saken titles
    aur qareebi behtar topics. Ye model ki raye hai, paimana nahi — UI label saaf likhta hai."""
    p, err = resolve_ref(ref)
    if not p:
        return {"error": err or "file nahi mila"}
    du = img_datauri(p, 1024, 85)
    if not du:
        return {"error": "thumbnail model ko bheja hi nahi ja saka"}
    parts = [{"text": GEM_DEEP_ASK.replace("__TITLE__", (title or "(koi title nahi diya)")[:300])},
             {"inlineData": {"mimeType": "image/jpeg", "data": du.split(",", 1)[1]}}]
    r = gem_try([GEM_MODEL] + GEM_MODEL_ALT, parts, maxtok=4000, temperature=0.5)
    if r.get("error"):
        return r
    txt = (r.get("text") or "").strip()
    model = r.get("model") or GEM_MODEL
    j = _json_block(txt)
    if not j:
        return {"ok": True, "raw": txt, "model": model}
    return {"ok": True, "deep": j, "model": model}


def start_ai(idea, words, mk=AIDEF, ref="", text_ai=False, res="sd", strength=None, eng="rw", meth="auto"):
    if not Image:
        return {"error": "Pillow nahi mila — setup.bat chalao"}
    if eng == "gem":
        if not gem_key():
            return {"error": "Gemini raste ke liye key chahiye (free tier par bhi apni key lagti hai) — "
                             "neeche Gemini key box me daalo. Bina key ka rasta Pollinations hai magar 27 Oct 2026 se wo bhi 402/503 wapas karta hai — try kar sakte hain, umeed kam rakhein."}
    elif eng == "agy":
        if not agy_bin():
            return {"error": "Antigravity CLI (agy) is machine par nahi mila. Ek baar ka setup: PowerShell me "
                             "chalao `irm https://antigravity.google/cli/install.ps1 | iex`, phir `agy` khol kar "
                             "us Google account se login karo jis par Google AI subscription hai. Uske baad ye "
                             "rasta hamesha bina API key ke chalega."}
    elif eng != "poll" and not rw_key():
        return {"error": "Runware ki API key set nahi. Upar 'Key' box me daalo (ya is folder me "
                         "runware_key.txt banao). Key ke bina bhi ⚡ Behtar banao chalta hai — wo "
                         "aapki hi photo sudharta hai, koi kharcha nahi."}
    idea = (idea or "").strip()
    if not idea and not (ref or "").strip():
        return {"error": "batao kya banana hai — idea likho (ya apni thumbnail ka path/reference do)"}
    res = res if res in RES else "sd"
    jid = hashlib.md5((idea + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": NSHOTS,
                 "current": ("Pollinations se tasveer maang raha hoon… (muft rasta)" if eng == "poll"
                             else "Gemini se tasveer maang raha hoon… (free tier)" if eng == "gem"
                             else "Antigravity se tasveer maang raha hoon… (aapki subscription — ~1 min/tasveer)" if eng == "agy"
                             else "Runware se tasveer maang raha hoon…"),
                 "kind": "ai"}
    threading.Thread(target=_do_ai, args=(jid, idea, (words or "").strip(), mk, ref or "",
                                         bool(text_ai), res, strength, eng, meth or "auto"), daemon=True).start()
    return {"job": jid}


def _do_ai(jid, idea, words, mk, ref, text_ai, res="sd", strength=None, eng="rw", meth="auto"):
    job = JOBS[jid]
    m = AIM.get(mk) or AIM[AIDEF]
    if eng == "poll":
        # label poori zindagi saaf rahe: ye muft rasta hai, Runware ka koi model nahi
        m = {"id": "pollinations", "name": "Pollinations (muft)", "usd": 0.0}
    elif eng == "agy":
        m = {"id": "antigravity", "name": "Antigravity — Nano Banana 2 (aapki subscription)", "usd": 0.0}
    elif eng == "gem":
        m = {"id": "gemini", "name": "Gemini " + GEM_IMG_MODEL.replace("gemini-", "") + " (free tier, apni key)", "usd": 0.0}
    w, h = RES.get(res) or RES["sd"]
    out, cost, errs = [], 0.0, []
    refu = ai_ref(ref) if ref else ""
    refp = resolve_ref(ref)[0] if ref else None      # inspired vs copy ka naap isi file se hoga
    st = (round(max(0.05, min(0.95, float(strength if strength is not None else 0.55))), 2) if ref else None)
    stamp = dt.datetime.now().strftime("%H%M%S")
    # 27 Oct: meth = thumbnail ka dhanga (category). "auto" = har shot ek ALAG category —
    # pro ka wala tareeka jo transcript me tha (MrBeast har idea ke kai versions alag
    # categories se banwata hai, phir jeetne wala chunta hai). User ne ek dhanga chun liya
    # ho to chaaron shots wahi category ke alag-alag takes bante hain (video ka doosra
    # sabaq: ek hi idea ke kai versions, behtareen ka intekhab).
    pool = [x for x in METHODS if x["k"] == meth] or METHODS
    if meth in ("", "auto") and not words and idea:
        # shabd khaali chhode to idea/title ke bare keywords apne aap chuno — audience
        # wahin rukti hai jo apne keywords dhoondti hai (wahi engine jo Behtar banao me
        # istemal hota aaya hai).
        words = pick_words(idea, "") or words
    for i in range(NSHOTS):
        mo = pool[i % len(pool)]
        di = i % len(DIRS)
        ectx = "soch %d/%d (%s): " % (i + 1, NSHOTS, mo["n"])  # har error pehle se ye bataye kaun si koshish thi
        job["current"] = "scene %d/%d — %s (%s, %dx%d, %s)" % (
            i + 1, NSHOTS, mo["n"], m["name"], w, h,
            "muft" if eng == "poll" else "free tier" if eng == "gem" else "subscription quota" if eng == "agy" else "~$" + str(RESP.get(res, "?")))
        pr = ai_prompt(idea or (ref and "the same scene, only cleaner and brighter") or "",
                       words, text_ai, di, mo["k"], bool(ref), nb=eng in ("gem", "agy"))
        r = None  # r sirf Runware branch me banta hai; muft/subscription raston par shared code
                  # (neeche "usd") ko None-safe chahiye — warna NameError se pura thread mar
                  # jaata tha aur job hamesha adhee batch par atka rehta (28 Oct, agy batch 040033).
        if eng in ("poll", "gem", "agy"):
            # muft/free/subscription raste: seedha image bytes. Reference aur strength yahan hota hi
            # nahi — isliye ye raaste "apni soch se naya scene" ke liye hain, inspired
            # work ke liye nahi (wo sirf Runware par naapa hua hai).
            raw = None
            try:
                if eng == "gem":
                    g = gem_gen(pr, w, h)
                    if g.get("error"):
                        errs.append(ectx + str(g["error"])[:90])  # error me "Gemini" prefix pehle se hai — dobara mat lagao
                elif eng == "agy":
                    g = agy_gen(pr, w, h)
                    if g.get("error"):
                        errs.append(ectx + str(g["error"])[:120])  # error me "Antigravity" prefix pehle se hai
                    else:
                        raw = g["bytes"]
                else:
                    raw = poll_get(pr, w, h)
            except Exception as e:
                errs.append(ectx + ("Gemini se tasveer nahi aayi: " if eng == "gem"
                             else "Antigravity se tasveer nahi aayi: " if eng == "agy"
                             else "Pollinations se tasveer nahi aayi: ") + str(e)[:90])
            job["done"] = i + 1
            if raw is None:
                continue
        else:
            r = rw_call(m["id"], pr, "" if text_ai else AIN, w, h, ref=refu, strength=st)
            if r.get("error") and re.search(r"length|too long|maximum|max\b", r["error"], re.I):
                # prompt model ki hadd se bara ho to wo khap bata deta hai — chhota kar ke phir koshish
                errs.append(ectx + "prompt chhota kar ke dobara: " + r["error"][:70])
                r = rw_call(m["id"], pr[:700], "" if text_ai else AIN, w, h, ref=refu, strength=st)
            job["done"] = i + 1
            if r.get("error"):
                # Runware ki English error ko apni zubaan mein samjhaao — user ko dobara kya karna hai ye saaf ho
                _raw = str(r["error"])
                if re.search(r"internal error|not processed", _raw, re.I):
                    errs.append(ectx + "Runware ka internal error — ye task fail hua, baaki chalte rahenge. Thori der baad 'wahi dobara' dabayein. (" + _raw[:80] + ")")
                else:
                    errs.append(ectx + _raw[:120])
                continue
            cost += float(r.get("cost") or 0)
            try:
                raw = http_get(r["url"], timeout=120)
            except Exception as e:
                errs.append(ectx + "image download nahi hua: " + str(e)[:80])
                continue
        try:
            AI_DIR.mkdir(parents=True, exist_ok=True)
            fp = AI_DIR / ("%s_%d_raw.jpg" % (stamp, i))
            fp.write_bytes(raw)
        except Exception:
            continue
        try:
            im = Image.open(fp).convert("RGB")       # native size — 1280 par zabardasti chhota nahi karta
        except Exception:
            continue
        dif = imgdiff(str(fp), refp) if refp else None
        an0 = analyse(str(fp))
        fc0 = faces_of(str(fp))
        # AI ka text: 24 Oct tak ye faaisla sirf OCR ginti se hota tha, aur nateeja GALAT
        # nikla. "7-13 nakli akhshar" jo gin rahe the wo asal me wo shabd the jo AI ne SAHI
        # likhe the — batch 121834 ke raw maine aankh se dekh liye ("MYSTERY OF BLACK
        # HOLES", spelling poori sahi, composition theek). Phir maine ye faaisla OCR ke
        # confidence + shabdon ke match se karne ki koshish ki, aur usi batch par replay
        # kiya: OCR "BLACK" ko "BLA" + "CK" me tod deta hai, isliye 3 me se sirf 1 shabd
        # mila — haalaanki tasveer me text bilkul theek tha. Yaani "AI ka text theek hai ya
        # nahi" local OCR se pakka nahi pata chalta; ye dekhne ka kaam hai, naapne ka.
        # Isliye ab kuch bhi chup-chaap bigaada nahi jaata: raw jaisi hai waisi ek variant,
        # aur scrub + apne shabd wala dusra. Kaun jeeta — benchmark aur aapki aankh faaisla
        # karti hai, mera andaaza nahi. (Scrub = _dertext_hard; AI aur ⚡ dono ek hi scrub karte hain: sirf-aksharon ka mask + cv2.inpaint; text line chehre par chadhe to scrub hota hi nahi (_scrub_ok)).
        airaw = [w for w in (ocr_cached(str(fp)) or [])
                 if int(w.get("h") or 0) >= 8 and int(w.get("w") or 0) <= im.size[0] * 0.85]
        cfs = [int(w.get("conf") or 0) for w in airaw]
        want = [re.sub(r"[^a-z0-9]", "", x.lower())
                for x in re.findall(r"[A-Za-z0-9']{3,}", str(words or ""))]
        got = " ".join(str(w.get("t") or "") for w in airaw)
        hit = sum(1 for x in want if x in got.lower())
        spell = _spell_check(want, airaw)
        shak = [s for s in spell if s["st"] == "close"]
        confavg = int(round(sum(cfs) / len(cfs))) if cfs else 0
        has_text = bool(airaw)
        fpx = _face_px(fc0, im.size[0], im.size[1])
        scrub = has_text and _scrub_ok(airaw, im.size[0], im.size[1], fpx)
        scene = _dertext_hard(im, airaw, fpx) if scrub else im
        if not has_text:
            scrub_note = "scene me likha hua tha hi nahi, isliye scrub ki zaroorat nahi pari"
        elif scrub:
            scrub_note = ("AI ka text muft scrub se hata diya gaya (sirf aksharon ka mask + inpaint). "
                          "Jahan text kisi cheez ke upar tha wahan ka hissa dhundhla ho sakta hai — "
                          "score gire to as-is card behtar hai")
        else:
            scrub_note = ("AI ka text chehre ke upar chadh raha tha — scrub se chehra dhundhla ho "
                          "jaata hai (24 Oct, aankh se dekha), isliye text chheda hi nahi gaya; "
                          "naye shabd khaali jagah par bithaye hain")
        lines = [] if text_ai else _split_words(words)
        shots = []
        if has_text:
            shots.append(("AI ka text (as-is)",
                          "AI ne jo likha wo jaisa ka vaisa — na scrub, na overlay. OCR ne isme ye padha: \"" + (got[:60] or "kuch nahi") +
                          "\" (OCR confidence " + str(confavg) + "/100, aur aapke " + str(len(want)) + " me se " + str(hit) +
                          " shabd mile). OCR stylized text ko tukde tod kar padhta hai, isliye kam match ka matlab ye zaroori nahi ki text galat hai — card par tasveer khud kholi, dekh kar chuno" +
                          (" — SPELLING KA SHAK: " + "; ".join("aapne \"" + s["w"] + "\" maanga, OCR ne scene me \"" + s["got"] + "\" padha" for s in shak) +
                           ". Ye bilkul 24 Oct ke do asli cases jaisa hai (\"MYSTERY\"→\"KLYSTERY\", \"THEY LAUGHED\"→\"THEY LAUGEDED\"): score bara aur saaf text ko acha number deta hai, spelling nahi jaan patta — is card par tasveer khol kar akshar gino" if shak else ""),
                          im))
        if lines:
            shots.append(("scene + text (Pillow)",
                          "scene AI se, bade shabd Pillow se — spelling 100% sahi aur contrast pakka" +
                          " (" + scrub_note + ")" +
                          ("" if (not has_text or scrub) else
                           " — dhyan rahe: purana text abhi bhi scene par hai, ye card tabhi lo jab naye shabd khaali jagah par bithe dikh rahe hon"),
                          _put_text(_grade(scene), lines, _free_cell(im, an0, fc0))))
            if not has_text:
                shots.append(("bina text", "sirf scene — raw me koi text tha hi nahi, isliye scrub ki zaroorat nahi pari" + " — yahan shabd jaan-boojh kar nahi daale, isliye text ke number score me nahi aaye. Text bithana ho to 'Behtar banao' tab me le jao", _grade(im)))
        elif has_text and scrub:
            shots.append(("bina text", "sirf scene, aur us par AI ka text muft scrub se hata diya gaya (sirf aksharon ka mask + inpaint) — jahan text kisi cheez ke upar tha wahan ka hissa dhundhla ho sakta hai, isliye score dekh kar chuno" + " — yahan shabd jaan-boojh kar nahi daale, isliye text ke number score me nahi aaye. Text bithana ho to 'Behtar banao' tab me le jao", _grade(scene)))
        elif has_text:
            # text chehre ke upar hai: scrub se chehra dhundhla hota hai, aur "bina text" ka
            # koi jawab hi nahi bachta. Do same tasveerein bhejna jhoot hoga, isliye sirf
            # as-is card hai — aur neeche aiNote batata hai ki scrub kyun nahi hua.
            pass
        else:
            shots.append(("bina text", "sirf scene — yahan koi text maanga hi nahi gaya tha, ya AI ne likha hi nahi" + " — yahan shabd jaan-boojh kar nahi daale, isliye text ke number score me nahi aaye. Text bithana ho to words box me likho ya 'Behtar banao' tab me le jao", _grade(im)))
        for nm, why, v in shots:
            p = AI_DIR / ("%s_%d_%s.jpg" % (stamp, i, re.sub(r"\W", "", nm)[:12]))
            try:
                v.save(p, "JPEG", quality=94)
            except Exception:
                continue
            van = analyse(str(p))
            vf = faces_of(str(p))
            vw = ocr_cached(str(p)) or []
            vts = text_stats(str(p), van, vw, vf)
            vts["read320"] = len(ocr_cached(str(p), 320) or [])
            noise = 0
            if nm == "bina text":
                # Is variant me shabd jaan-boojh kar nahi daale. Jo OCR kuch pakadta hai wo
                # scene ka AI-shor hota hai — usse text ke number de dena score ko jhoota
                # kar deta hai (ek baar to yahi wajah bani ki bina-text jeet gaya). Isliye
                # yahan text ke saare number zero, aur shor ki ginti alag dikhi jaati hai.
                noise = vts.get("n") or 0
                for kk in ("n", "chars", "maxh", "minh", "area", "lines", "blocks"):
                    vts[kk] = 0
                for kk in ("cr", "cr_med", "ring_cr", "h320", "h168"):
                    vts[kk] = None
                vts.update({"text": "", "pos": "", "badge": False, "edge": False,
                            "facehit": False, "read320": 0, "noise": noise})
                vw = []
            out.append({"name": nm, "why": why, "path": str(p), "idea": idea[:160], "ref": bool(ref),
                        "mk": mk, "model": m["name"], "usd": (r or {}).get("cost"), "at": dt.datetime.now()
                        .isoformat(timespec="seconds"), "an": van, "ts": vts, "faces": vf,
                        "words": vw, "read320": vts["read320"], "noise": noise,
                        "dir": mo["n"], "dirwhy": mo["w"], "shot": i, "res": res,
                        "w": (van.get("w") or im.size[0]), "h": (van.get("h") or im.size[1]),
                        "strength": st, "dref": dif, "airaw": len(airaw), "scrub": scrub,
                        # purane records (scrubv nahi hai) ke baare me ye nahi pata ki scrub
                        # kyun nahi hua — isliye card par wo wajah sirf naye records par dikhti hai.
                        "scrubv": 2,
                        "conf": confavg, "hit": hit, "wantn": len(want), "otext": got[:80],
                        # maange hue shabd + OCR se unka muqabla — spelling ka shak card par
                        # dikhane ke liye (score spelling nahi jaan patta, 24 Oct ke cases dekhe).
                        "want": want, "spell": spell,
                        "score": score(van, vts, vf)})
    out.sort(key=lambda d: -d["score"])
    out = out[:NSHOTS * 2]
    if not out:
        job["state"] = "error"
        # saari koshishein fail huin to sirf pehli error mat dikhao — poori listing + ye batao ke aage kya karein
        _e = errs[:4]
        _msg = (("sab %d koshishein fail huin: " % NSHOTS) if len(_e) > 1 else "") + " · ".join(_e) if _e else "kuch nahi bana"
        if any(re.search(r"429|quota|limit", x, re.I) for x in _e):
            if eng == "agy":
                _msg += " — Antigravity ki subscription quota khatam lagti hai (wo har 5 ghante refresh hoti hai, saath mein weekly limit bhi hai). Tab tak engine menu me Runware (paid, $0.0006/image) chuno, ya thori der baad 'wahi dobara' dabayein."
            else:
                _alt = "Runware (paid, $0.0006/image)" + (" ya Antigravity (aapki Google AI subscription — bina key)" if agy_bin() and eng != "agy" else "")
                _msg += " — ye free tier ki daily limit hai, kal apne aap khul jaayegi. Abhi chahiye to engine menu me " + _alt + " chuno."
        elif any(re.search(r"402|payment", x, re.I) for x in _e):
            _msg += " — Pollinations ne free tier badal diya hai (402 = ab wo bhi key maangta hai). Filhal Runware (paid, $0.0006/image) sabse bharosemand rasta hai."
        elif any(re.search(r"503|unavailable|getaddrinfo|timed out|timeout", x, re.I) for x in _e):
            _msg += " — service bahar lag rahi hai (ya internet ka rasta ruk gaya). Thori der baad 'wahi dobara' dabayein, ya doosra engine chuno."
        job["error"] = _msg[:600]
        return
    for d in out:
        d["id"] = hashlib.md5((d["path"] + d["name"]).encode()).hexdigest()[:8]
    hist = load_ai()
    hist[:0] = out
    save_ai(hist)
    job["result"] = {"items": out, "cost": round(cost, 5), "model": m["name"], "mk": mk,
                     "errs": errs[:2], "n": len(out), "res": res, "size": "%dx%d" % (w, h),
                     "strength": st, "dirs": [x["n"] for x in pool[:NSHOTS]]}
    job["state"] = "done"


def clear_ai():
    n = 0
    # history ke alawa _raw.jpg bhi yahi bante hain, isliye poora AI_DIR khali karo —
    # warna har "purani hatao" ke baad kachra disk par bacha rehta hai.
    try:
        for p in sorted(AI_DIR.glob("*")):
            try:
                if p.is_file():
                    p.unlink()
                    n += 1
            except Exception:
                pass
    except Exception:
        pass
    try:
        if AI_F.exists():
            AI_F.unlink()
    except Exception:
        pass
    return {"ok": True, "files": n}


# ---------------- 4. aggregate over competitors ----------------

STOP = set("the a an and or of to in is are for on with your you my it this that how what why we i be do does how's vs at as from".split())


def ngrams(titles, minc=2, top=12):
    c = Counter()
    for t in titles:
        ws = re.findall(r"[a-zA-Z0-9']+", t.lower())
        seen = set()
        for n in (1, 2, 3):
            for i in range(len(ws) - n + 1):
                g = " ".join(ws[i:i + n])
                if n > 1 and (g.split()[0] in STOP or g.split()[-1] in STOP):
                    continue
                if g not in seen:
                    seen.add(g)
                    c[g] += 1
    return [{"p": p, "n": n} for p, n in c.most_common(400) if n >= minc][:top]


def agg(items):
    its = [i for i in items if i.get("an")]
    n = len(its) or 1
    with_t = sum(1 for i in its if i["ts"]["n"] > 0)
    fams = Counter()
    for i in its:
        for c in i["an"].get("colors", []):
            fams[c["fam"]] += c["pct"] / 100.0
    tl = [len(i["title"]) for i in items]
    titles = [i["title"] for i in items]
    return {"n": len(items), "with_text_pct": round(with_t * 100 / n),
            "med_words": med([i["ts"]["n"] for i in its]),
            "med_maxh320": med([i["ts"].get("h320", 0) for i in its if i["ts"]["n"]]),
            "med_cr": med([i["ts"]["cr_med"] for i in its if i["ts"].get("cr_med")]),
            "med_bright": round(med([i["an"]["bright"] for i in its]), 3),
            "med_dyn": round(med([i["an"]["dyn"] for i in its]), 3),
            "med_clutter": med([i["an"]["clutter"] for i in its if i["an"].get("clutter") is not None]),
            "med_views": med([i["views"] for i in items]),
            "top_views": max(items, key=lambda i: i["views"])["title"] if items else "",
            "fams": [{"f": f, "n": round(v * 100 / n)} for f, v in fams.most_common(8)],
            "title": {"med_len": med(tl), "max_len": max(tl) if tl else 0,
                      "num_pct": round(sum(1 for t in titles if re.search(r"\d", t)) * 100 / n),
                      "caps_pct": round(sum(1 for t in titles if re.search(r"\b[A-Z]{4,}\b", t)) * 100 / n),
                      "br_pct": round(sum(1 for t in titles if re.search(r"[\[\]|]| - ", t)) * 100 / n),
                      "q_pct": round(sum(1 for t in titles if "?" in t) * 100 / n)},
            "phrases": ngrams(titles)}


# ---------------- 4b. gehri analysis: kaun si cheez sach me chalti hai ----------------

def vpd(it):
    """views per day — purani video ke 7M views aur 30 din purani ke 300K me
    300K wala behtar hai, isliye views ko umr se baantna zaroori hai."""
    return (it.get("views") or 0) / max(1, it.get("days") or 1)


def dup_pct(title, text):
    """Thumbnail ka text title ko hi dohra raha ho to jagah barbaad —
    thumbnail title ko poora nahi karta, curiosity kholta hai."""
    a = set(w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if len(w) > 2 and w not in STOP)
    b = set(w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in STOP)
    if not b:
        return None
    return round(len(a & b) * 100 / len(b))


STOPX = STOP | set("video videos watch new full official abhi dekhna subscribe channel part".split())


def _words(s):
    s = (s or "").lower()
    out = [w for w in re.findall(r"[a-z0-9\u0600-\u06ff\u0900-\u097f']{2,}", s)]
    return [w for w in out if w not in STOPX]


def sem_match(thumb, title, tags, desc, topic):
    """ASLI semantic tulna (TF-IDF + cosine). Pehle sirf dup_pct tha — do shabd jo ek jaise
    na likhe hon ("black hole" vs "event horizon") unka koi rishta nahi pakadta tha. Ye
    title+tags+description+topic ke shabdon ka weight nikaal kar dekhta hai ki thumbnail
    ka text unme kitna dhaka hai, aur kaun se bare keyword thumbnail par GAIB hain.
    sklearn na ho to word-overlap par wapas chala jaata hai (aur method me likhta hai)."""
    docs = [" ".join(_words(thumb)), " ".join(_words(title)),
            " ".join(_words(" ".join(tags or []))), " ".join(_words((desc or "")[:2500])),
            " ".join(_words(topic))]
    load_sk()
    if _TFIDF is None:
        sets = [set(d.split()) for d in docs]
        if not sets[0]:
            return None
        out = {"method": "overlap"}
        for i, k in enumerate(("t_title", "t_tags", "t_desc", "t_topic"), 1):
            out[k] = round(len(sets[0] & sets[i]) / float(len(sets[0])), 3) if sets[i] else None
        return out
    try:
        if not docs[0] or not any(docs[1:]):
            return None
        tv = _TFIDF(stop_words=None, token_pattern=r"(?u)\S+", sublinear_tf=True, min_df=1)
        M = tv.fit_transform(docs)
        names = tv.get_feature_names_out()
        w = M.toarray()
        def cos(a, b):
            na = math.sqrt(float((a * a).sum())); nb = math.sqrt(float((b * b).sum()))
            if na <= 0 or nb <= 0:
                return None
            return round(max(0.0, float((a * b).sum()) / (na * nb)), 3)
        out = {"method": "tfidf", "n_terms": int(len(names))}
        for i, k in enumerate(("t_title", "t_tags", "t_desc", "t_topic"), 1):
            out[k] = cos(w[0], w[i]) if docs[i] else None
        # kaun se bare keyword (title+tags+desc ka sabse zyada weight) thumbnail par nahi hain
        imp = w[1:].sum(axis=0)
        order = sorted(range(len(names)), key=lambda j: -imp[j])
        miss = [names[j] for j in order if w[0][j] == 0 and imp[j] > 0][:8]
        hit = [names[j] for j in order if w[0][j] > 0 and imp[j] > 0][:8]
        out["miss"] = miss
        out["hit"] = hit
        tt = [out[k] for k in ("t_title", "t_tags", "t_desc", "t_topic") if out[k] is not None]
        out["t_max"] = max(tt) if tt else None
        return out
    except Exception:
        return None


def _mwu(a, b):
    """Mann-Whitney U, do-tarfa, normal approximation + ties ka sujhao. scipy ki zaroorat
    nahi. Do groups ke medians ka farq asli hai ya sirf n chhota hone ka dhoka — ye wahi
    batata hai. p < 0.05 = ishara; isse upar ka number sirf tab tak sach hai."""
    a = [float(x) for x in a]; b = [float(x) for x in b]
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return None
    allv = a + b
    order = sorted(range(len(allv)), key=lambda k: allv[k])
    ranks = [0.0] * len(allv)
    i = 0
    tie = 0.0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[order[j + 1]] == allv[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = r
        t = j - i + 1
        if t > 1:
            tie += t ** 3 - t
        i = j + 1
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    n = n1 + n2
    sd2 = (n1 * n2 / 12.0) * ((n + 1) - tie / float(n * (n - 1))) if n > 1 else 0.0
    if sd2 <= 0:
        return None
    z = (abs(u1 - mu) - 0.5) / math.sqrt(sd2)
    if z <= 0:
        return 1.0
    p = math.erfc(z / math.sqrt(2.0))          # erfc(z/sqrt2) = 2*(1-Phi(z)) = do-tarfa p
    return min(1.0, max(0.0, p))               # raw bhejo — dikhane kaand display sambhalega


def fp(p):
    """p-value ka imaandar rakaam: chhote p ko '0' mat dikhaо — woh galat lagta hai,
    '<0.001' sahi hai. None → '—'."""
    if p is None:
        return "—"
    if p < 0.001:
        return "<0.001"
    return ("%.3f" % p).rstrip("0").rstrip(".")


def _dist_age(i, j):
    """Do videos kitne miltte-julte hain: umr aur channel ke size se. Matched control
    ke liye — warna "chapters wale 5.4x" ka matlab sirf itna ho sakta hai ki chapters
    badi channels ki lambi videos par hote hain."""
    return (abs(math.log10(max(1, i.get("days") or 1)) - math.log10(max(1, j.get("days") or 1))) +
            abs(math.log10(max(1, i.get("subs") or 1)) - math.log10(max(1, j.get("subs") or 1))) * 0.6)


def _matched_lift(items, sel, pred, k=3):
    """Har video ka 'expected' uski umr aur channel ke size se milti-julti kareeb 3 videos
    ka median hai. Phir dekhta hai wo apne expected se kitna upar/neeche gaya. Ye raw lift
    se kaafi zyada sach hai, kyun ki umr aur channel ka asar isme nikal jata hai."""
    oth = [i for i in items if not pred(i) and vpd(i) > 0]
    if len(oth) < k:
        return None, 0
    rs = []
    for i in sel:
        if vpd(i) <= 0:
            continue
        cands = sorted(oth, key=lambda j: _dist_age(i, j))[:k]
        if len(cands) < 2:
            continue
        e = med([vpd(j) for j in cands])
        if e and e > 0:
            rs.append(vpd(i) / e)
    if len(rs) < 3:
        return None, len(rs)
    return round(med(rs), 2), len(rs)


def _buck(items, label, keyf, buckets):
    """Har bucket ka median views/day + do alag, imandaar tulna:
      lift      = baqi sab ke muqable (bucket khud baseline me NAHI — purana code khud
                  apne aandhar tha, isliye har lift 1 ke taraf khichati thi)
      m_lift    = umr aur channel ke size se milti-julti videos ke muqable (matched)
      p         = Mann-Whitney U se do-tarfa significance
    n < TH[min_n] wale bucket ko dikhaya hi nahi jaata.
    keyf us feature par pool banata hai jiska naap HO SAKTA hai: jis video ka comp/sem/
    cr naapa hi nahi gaya (thumbnail nahi mila, OCR ne koi box nahi diya) use baseline me
    bhi nahi gina jaata — warna "unknown" videos ke saath tulna ho raha hota. (Ye pool
    pehle ignore ho raha tha — isliye comp=None wale video par scan crash hua tha.)"""
    pool = [i for i in items if keyf(i)]
    rows = []
    for name, pred in buckets:
        sel = [i for i in pool if pred(i)]
        if len(sel) < TH["min_n"]:
            continue
        vs = [v for v in (vpd(i) for i in sel) if v > 0]
        oth = [v for v in (vpd(i) for i in pool if not pred(i)) if v > 0]
        if len(vs) < TH["min_n"] or len(oth) < TH["min_n"]:
            continue
        base = med(oth) or 1
        ml, mn = _matched_lift(pool, sel, pred)
        p = _mwu(vs, oth)
        rows.append({"k": label, "b": name, "n": len(sel), "views": med([i.get("views") or 0 for i in sel]),
                     "vpd": med(vs), "lift": round(med(vs) / base, 2), "base_out": round(base, 1),
                     "m_lift": ml, "m_n": mn, "p": p,
                     "sig": bool(p is not None and p < 0.05), "n_base": len(oth)})
    return rows


def deep(items):
    its = [i for i in items if i.get("an")]
    rows = []
    rows += _buck(its, "Chehra", lambda i: i.get("faces"),
                  [("chehra hai", lambda i: len(i.get("faces") or []) > 0),
                   ("chehra nahi", lambda i: not (i.get("faces") or []))])
    rows += _buck(its, "Chehre ka size", lambda i: i.get("faces"),
                  [("10% se kam", lambda i: i.get("faces") and max(f["area"] for f in i["faces"]) < 10),
                   ("10–30%", lambda i: i.get("faces") and 10 <= max(f["area"] for f in i["faces"]) < 30),
                   ("30% se bara", lambda i: i.get("faces") and max(f["area"] for f in i["faces"]) >= 30)])
    rows += _buck(its, "Text ke shabd", lambda i: i.get("ts"),
                  [("0 (sirf image)", lambda i: i["ts"]["n"] == 0), ("1–2", lambda i: 1 <= i["ts"]["n"] <= 2),
                   ("3–5", lambda i: 3 <= i["ts"]["n"] <= 5), ("6+", lambda i: i["ts"]["n"] >= 6)])
    rows += _buck(its, "Bada text (320px par)", lambda i: i["ts"]["n"],
                  [("chhota (<%dpx)" % TH["h_mid"], lambda i: i["ts"].get("h320", 0) < TH["h_mid"]),
                   ("%d–%dpx" % (int(TH["h_mid"]), int(TH["h_ok"])), lambda i: TH["h_mid"] <= i["ts"].get("h320", 0) < TH["h_ok"]),
                   ("%dpx+" % int(TH["h_ok"]), lambda i: i["ts"].get("h320", 0) >= TH["h_ok"])])
    rows += _buck(its, "Text ka asli contrast", lambda i: i["ts"].get("cr_med"),
                  [("%.1f:1 se kam" % TH["cr_ok"], lambda i: (i["ts"].get("cr_med") or 99) < TH["cr_ok"]),
                   ("%.1f:1 se upar" % TH["cr_ok"], lambda i: (i["ts"].get("cr_med") or 0) >= TH["cr_ok"])])
    rows += _buck(its, "Outline/shadow ka asar", lambda i: i["ts"].get("ring_cr") is not None,
                  [("outline se alag dikhta hai", lambda i: (i["ts"].get("ring_cr") or 0) >= TH["ring_ok"]),
                   ("outline ke bina dub raha", lambda i: (i["ts"].get("ring_cr") or 99) < TH["ring_ok"])])
    rows += _buck(its, "Chehra saamne ka", lambda i: i.get("faces"),
                  [("chehra seedha camera ki taraf", lambda i: any(f.get("frontal") for f in (i.get("faces") or []))),
                   ("chehra hai par ghuma hua/pitch", lambda i: bool(i.get("faces")) and not any(f.get("frontal") for f in (i.get("faces") or [])))])
    # NOTE: yahan pehle do "saliency" buckets the (entropy aur blob). Dono hataye gaye:
    # apne hi 102 thumbnails par naapa gaya ki saliency map ka subject face-box se sirf
    # 7/38 mel khata, aur uski entropy har image me 0.98–0.999 thi (koi farq hi nahi
    # dikhta tha). Uski jagah upar "Composition" aur " dominance" ke buckets asli OCR +
    # face boxes par hain.
    rows += _buck(its, "Thumbnail↔topic ka semantic match", lambda i: (i.get("sem") or {}).get("t_topic") is not None,
                  [("thumbnail topic se match karta hai (>=0.15)",
                    lambda i: ((i.get("sem") or {}).get("t_topic") or 0) >= 0.15),
                   ("thumbnail topic se kata hua (<0.15)",
                    lambda i: ((i.get("sem") or {}).get("t_topic") or 0) < 0.15)])
    rows += _buck(its, "Brightness", lambda i: i["an"].get("bright") is not None,
                  [("bahut dark", lambda i: i["an"]["bright"] < TH["bright"][0]),
                   ("theek (%.2f–%.2f)" % TH["bright"], lambda i: TH["bright"][0] <= i["an"]["bright"] <= TH["bright"][1]),
                   ("bahut halka", lambda i: i["an"]["bright"] > TH["bright"][1])])
    rows += _buck(its, "Bheed (edges)", lambda i: i["an"].get("clutter") is not None,
                  # ye teen hisse apne hi corpus ke percentiles par hain: p50=4, p90=8,
                  # poora maximum 12 tha (isliye purana "<=12% saaf" wala bucket sabko
                  # "saaf" kehta tha — usme koi information hi nahi thi)
                  [("saaf (<=4%% = aadhe se kam)", lambda i: i["an"]["clutter"] <= 4),
                   ("4–%d%% (aadhe se zyada, top 10%% se kam)" % TH["clutter_ok"],
                    lambda i: 4 < i["an"]["clutter"] <= TH["clutter_ok"]),
                   ("%d%%+ (poore corpus ka top 10%%)" % TH["clutter_ok"], lambda i: i["an"]["clutter"] > TH["clutter_ok"])])
    rows += _buck(its, "Rang", lambda i: i["an"].get("sat") is not None,
                  [("pheeka (sat<0.20)", lambda i: i["an"]["sat"] < 0.20),
                   ("0.20–0.40", lambda i: 0.20 <= i["an"]["sat"] < 0.40),
                   ("teeikh (>=0.40)", lambda i: i["an"]["sat"] >= 0.40)])
    rows += _buck(its, "Taap-mizaaj", lambda i: i["an"].get("warm") is not None,
                  [("garam rang (warm)", lambda i: i["an"]["warm"] >= 50),
                   ("thande rang (cool)", lambda i: i["an"]["warm"] < 50)])
    rows += _buck(its, "Composition (asli boxes se)", lambda i: (i.get("comp") or {}).get("thirds") is not None,
                  [("rule-of-thirds par (>= %.2f)" % TH["thirds_ok"], lambda i: i["comp"]["thirds"] >= TH["thirds_ok"]),
                   ("beech/behtar (%.2f–%.2f)" % (TH["thirds_lo"], TH["thirds_ok"]),
                    lambda i: TH["thirds_lo"] <= i["comp"]["thirds"] < TH["thirds_ok"]),
                   ("bilkul beech ya kinare (< %.2f)" % TH["thirds_lo"], lambda i: i["comp"]["thirds"] < TH["thirds_lo"])])
    rows += _buck(its, "Ek subject ya bheed (dominance)", lambda i: (i.get("comp") or {}).get("dom") is not None,
                  [("ek cheez dominant (>=%.2f)" % TH["dom_hi"], lambda i: i["comp"]["dom"] >= TH["dom_hi"]),
                   ("chalta-phirta (%.2f–%.2f)" % (TH["dom_warn"], TH["dom_hi"]),
                    lambda i: TH["dom_warn"] <= i["comp"]["dom"] < TH["dom_hi"]),
                   ("bheed, koi dominant nahi (<%.2f)" % TH["dom_warn"], lambda i: i["comp"]["dom"] < TH["dom_warn"])])
    rows += _buck(its, "Subject ka size (asli boxes)", lambda i: (i.get("comp") or {}).get("subj_pct") is not None,
                  [("chhota (under %d%%)" % TH["subj_lo"], lambda i: i["comp"]["subj_pct"] < TH["subj_lo"]),
                   ("%d–%d%%" % (TH["subj_lo"], TH["subj_hi"]),
                    lambda i: TH["subj_lo"] <= i["comp"]["subj_pct"] < TH["subj_hi"]),
                   ("%d%%+ bara subject" % TH["subj_hi"], lambda i: i["comp"]["subj_pct"] >= TH["subj_hi"])])
    rows += _buck(items, "Title ki lambai", lambda i: i.get("title"),
                  [("50 chars se kam", lambda i: len(i["title"]) < 50), ("50–70", lambda i: 50 <= len(i["title"]) <= 70),
                   ("70+ chars", lambda i: len(i["title"]) > 70)])
    rows += _buck(items, "Title me number", lambda i: i.get("title"),
                  [("number hai", lambda i: bool(re.search(r"\d", i["title"]))),
                   ("number nahi", lambda i: not re.search(r"\d", i["title"]))])
    rows += _buck(items, "Title me sawal", lambda i: i.get("title"),
                  [("sawal hai", lambda i: "?" in i["title"]), ("sawal nahi", lambda i: "?" not in i["title"])])
    rows += _buck(items, "Thumbnail title dohrata hai", lambda i: i.get("dup") is not None,
                  [("dohraata hai (>25%)", lambda i: (i.get("dup") or 0) > 25),
                   ("naya shabd deta hai", lambda i: (i.get("dup") or 0) <= 25)])
    # ---- listing (ASLI tags + description jo us video par lage hain) ----
    rows += _buck(items, "Tags ki tadaad", lambda i: i.get("tags") is not None,
                  [("0 tags", lambda i: len(i.get("tags") or []) == 0),
                   ("1–10", lambda i: 1 <= len(i.get("tags") or []) <= 10),
                   ("11–25", lambda i: 11 <= len(i.get("tags") or []) <= 25),
                   ("26+ tags", lambda i: len(i.get("tags") or []) >= 26)])
    rows += _buck(items, "Description ki lambai", lambda i: i.get("dlen") is not None,
                  [("40 chars se kam", lambda i: (i.get("dlen") or 0) < 40),
                   ("40–300", lambda i: 40 <= (i.get("dlen") or 0) < 300),
                   ("300–1000", lambda i: 300 <= (i.get("dlen") or 0) < 1000),
                   ("1000+ chars", lambda i: (i.get("dlen") or 0) >= 1000)])
    rows += _buck(items, "Chapters", lambda i: i.get("nch") is not None,
                  [("bageen (jo bhi hain)", lambda i: (i.get("nch") or 0) > 0),
                   ("kuch nahi", lambda i: (i.get("nch") or 0) == 0)])
    rows += _buck(items, "Comments", lambda i: i.get("cmts") is not None,
                  [("1000+ comment", lambda i: (i.get("cmts") or 0) >= 1000),
                   ("kam comments", lambda i: (i.get("cmts") or 0) < 1000)])
    rows += _buck(items, "Listing score (is tool ka)", lambda i: i.get("ls") is not None,
                  [("70+ (saf)", lambda i: (i.get("ls") or 0) >= 70),
                   ("45–69", lambda i: 45 <= (i.get("ls") or 0) < 70),
                   ("45 se kam", lambda i: (i.get("ls") or 0) < 45)])
    # ---- "pattern" sirf wahi, jiske paas kaafi sample AUR significance ho ----
    # Pehle n>=3 par "Chapters 5.4x" jaisi baten dikhati thi — 3 videos ka median
    # 90% cases me apne aap 2x-6x aa jata hai. Ab Mann-Whitney p < 0.05 lazmi hai,
    # aur matched (umar/channel se control) lift bhi dikhti hai.
    good = [r for r in rows if r["n"] >= TH["min_n"] and r.get("sig")]
    good.sort(key=lambda r: -(r.get("m_lift") or r["lift"]))
    pat = []
    for r in good[:6]:
        ml = r.get("m_lift")
        if (ml or r["lift"]) >= 1.25:
            pat.append({"s": "ok", "t": "%s: %s — %dx (n=%d, p=%s%s)" % (
                r["k"], r["b"], (ml or r["lift"]), r["n"], fp(r["p"]),
                "" if ml is None else ", umar/channel control ke baad")})
    for r in good[::-1][:4]:
        ml = r.get("m_lift")
        if (ml or r["lift"]) <= 0.8:
            pat.append({"s": "bad", "t": "%s: %s — %sx kam (n=%d, p=%s) — ye cheez nuqsan de rahi hai" % (
                r["k"], r["b"], (ml or r["lift"]), r["n"], fp(r["p"]))})
    weak = [r for r in rows if r["n"] >= TH["min_n"] and not r.get("sig") and
            (r["lift"] >= 1.4 or r["lift"] <= 0.7)]
    for r in sorted(weak, key=lambda r: -abs(math.log(max(0.05, r["lift"]))))[:6]:
        pat.append({"s": "warn", "t": "%s: %s — %sx dikhta hai par ye sirf ishara hai (n=%d, p=%s) — count karke pakka nahi kiya ja sakta" % (
            r["k"], r["b"], r["lift"], r["n"], fp(r["p"]))})
    bn = {}
    for key, lab in (("h320", "text_size"), ("cr_med", "text_contrast"), ("n", "words")):
        vals = [i["ts"].get(key) for i in its if i["ts"]["n"] and i["ts"].get(key) is not None]
        if len(vals) >= 4:
            bn[lab] = {"p10": pctl(vals, .10), "p25": pctl(vals, .25), "med": med(vals),
                       "p75": pctl(vals, .75), "p90": pctl(vals, .90), "n": len(vals)}
    for key, lab in (("bright", "brightness"), ("dyn", "depth"), ("clutter", "clutter"), ("sat", "saturation")):
        vals = [i["an"].get(key) for i in its if i["an"].get(key) is not None]
        if len(vals) >= 4:
            bn[lab] = {"p10": pctl(vals, .10), "p25": pctl(vals, .25), "med": med(vals),
                       "p75": pctl(vals, .75), "p90": pctl(vals, .90), "n": len(vals)}
    fvals = [max(f["area"] for f in i["faces"]) for i in its if i.get("faces")]
    if len(fvals) >= 4:
        bn["face_pct"] = {"p10": pctl(fvals, .10), "p25": pctl(fvals, .25), "med": med(fvals),
                          "p75": pctl(fvals, .75), "p90": pctl(fvals, .90), "n": len(fvals)}
    bn["_face_pct_of_all"] = round(len(fvals) * 100 / (len(its) or 1))
    # ---- listing ke asli naap (is topic ki top videos par jo laga hua hai) ----
    for key, lab in (("tags", "tags_count"), ("dlen", "desc_chars"), ("ls", "listing_score"),
                     ("cmts", "comments"), ("likes", "likes"), ("subs", "channel_subs")):
        vals = [len(i[key]) if key == "tags" else i.get(key) for i in items if i.get(key) is not None]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if len(vals) >= 4:
            bn[lab] = {"p10": pctl(vals, .10), "p25": pctl(vals, .25), "med": med(vals),
                       "p75": pctl(vals, .75), "p90": pctl(vals, .90), "n": len(vals)}
    got = [i for i in items if i.get("tags") is not None]
    if got:
        bn["_tags_zero"] = len([i for i in got if not i.get("tags")])
        bn["_chaps_pct"] = round(len([i for i in got if (i.get("nch") or 0) > 0]) * 100 / len(got))
        bn["_meta_n"] = len(got)
    base = med([v for v in (vpd(i) for i in items) if v > 0]) or 1
    out = []
    for i in sorted(items, key=lambda i: -vpd(i))[:3]:
        if vpd(i) >= base * 2.5:
            out.append({"title": i["title"][:90], "url": i.get("url", ""), "views": i.get("views", 0),
                        "days": i.get("days"), "vpd": round(vpd(i)), "words": i["ts"]["n"],
                        "maxh": i["ts"].get("h320"), "faces": len(i.get("faces") or []),
                        "bright": i["an"].get("bright"), "thumb": i.get("thumb")})
    return {"vpd_med": round(base, 1), "buckets": rows, "pattern": pat, "bench": bn, "breaks": out}


# ---------------- scan job ----------------

def measure_items(items, topic, got, job, descs, CAL, meta=True):
    # Ek scan ke har item ki POORI naap: us video ka asli listing metadata (tags,
    # description, chapters, likes, comments, subscriber), thumbnail download, OCR, chehre,
    # composition, aur ant me score. Pehle ye poora kaam _do_scan ke andar ek closure tha;
    # ab alag function hai taaki channel scan (section 7) bhi wahi chalaye — do alag raste
    # hote to ek hi cheez ka matlab do hota aur har sudhaar do jagah karna padta.
    # `descs` caller banata hai (semantic tulna ko poora description chahiye), `got`
    # enrich() ka aaya hua views/date hai, aur progress job me dikhti rahe isliye job pass
    # hota hai. Koi nayi cheez isme nahi jodi gayi — sirf wahi jo pehle chalta tha.
    done_n = [0]

    def one(i_it):
        i, it = i_it
        job["current"] = "thumbnail %d/%d: %s" % (i + 1, len(items), (it["title"] or "")[:44])
        g = got.get(it["id"], {})
        it.update({"views": g.get("views", 0), "upload": g.get("upload", ""),
                   "pt": g.get("pt", ""),
                   "days": g.get("days"), "dur": g.get("dur", 0), "channel": g.get("channel", ""),
                   "url": "https://www.youtube.com/watch?v=" + it["id"]})
        # publishedAt epoch banakar "pubts" me rakh do — ghari ka pattern usi se
        # gina jaata hai (waqt-jodna bahaal kaam isi field par karta hai).
        if g.get("pt"):
            try:
                it["pubts"] = int(dt.datetime.strptime(g["pt"][:19], "%Y-%m-%dT%H:%M:%S")
                                  .replace(tzinfo=dt.timezone.utc).timestamp())
            except Exception:
                pass
        if meta:
            # ASLI listing: tags/description/chapters — jo us channel ne khud lagaye hain.
            # Ye kaam thumbnail download ke saath ek hi thread me hota hai, isliye
            # wall time me almost kuch add nahi hota (0.45s/video, ek baar, phir cache).
            m = meta_of(it["id"])
            if not m.get("err"):
                it["tags"] = m["tags"]
                it["dlen"] = len(m["desc"])
                it["dprev"] = m["desc"][:260]
                it["likes"] = m["likes"]
                it["cmts"] = m["cmts"]
                it["subs"] = m["subs"]
                it["nch"] = len(m["chaps"])
                it["cat"] = m["cat"]
                it["cc"] = m["cc"]
                # chhapne ka waqt (ghari tak) — sirf is video ki apni metadata se aaya
                # hai, koi andaza nahi. Naam "pubts" rakha hai kyunki item par "ts"
                # pehle se thumbnail ke text-stats ke liye istemaal hota hai.
                if m.get("ts"):
                    it["pubts"] = int(m["ts"])
                with _lock:
                    descs[it["id"]] = (m["desc"] or "")[:2500]
                if not it.get("dur"):
                    it["dur"] = m["dur"]
                s = seo_check(it["title"], m)
                it["ls"] = s["ls"]
                it["lchk"] = s["chk"]
                it["tmiss"] = s["miss"]
                it["thit"] = s["hit"]
            else:
                it["merr"] = m["err"]
        p, kind = get_thumb(it["id"])
        it["thumb"] = str(p) if p else None
        it["kind"] = kind
        if p:
            it["an"] = analyse(p)
            it["faces"] = faces_of(p)
            w = ocr_cached(p)
            it["ts"] = text_stats(p, it["an"], w or [], it["faces"])
            it["words"] = w or []
            it["comp"] = comp_of(it["ts"], it["faces"])
            if it["comp"]:
                # subject ka box: color/edge ke ANDAAZE se behtar OCR+face ke ASLI
                # boxes — UI ko wahi dikhana hai jo waqai frame me hai
                it["an"]["subj"] = it["comp"]["subject"]
                it["an"]["subj_src"] = "ocr+face boxes"
            it["dup"] = dup_pct(it["title"], it["ts"].get("text"))
            it["sem"] = sem_match(it["ts"].get("text"), it["title"], it.get("tags"),
                                  descs.get(it["id"]) or it.get("dprev"), topic)
            it["score"] = score(it["an"], it["ts"], it["faces"], CAL)
            # Har naapi gayi video par ab "kya theek nahi hai" (vr) aur "score kaise bana"
            # (sd) bhi store hota hai. Pehle verdicts sirf "Meri Thumbnail" ke check par
            # bante the, isliye Competitors/Channel cards par kacche numbers dikhte the aur
            # user ko khud samajhna padta tha kaunsa number bura hai. Ye dono pehle se
            # naape hue an/ts/faces se bante hain — koi nayi measurement nahi, isliye scan
            # ka waqt lagbhag nahi badalta (naapa: 0.02s/video).
            it["vr"] = verdicts(it["an"], it["ts"], it["faces"], it.get("comp"))
            it["sd"] = score_detail(it["an"], it["ts"], it["faces"], CAL, it.get("comp"))
            if it["ts"]["n"]:
                r = ocr_cached(p, 320)               # 320px par bhi padha ja sakta hai?
                it["ts"]["read320"] = len(r or [])
        else:
            it["an"] = None
            it["ts"] = {"n": 0}
        with _lock:
            done_n[0] += 1
            job["done"] = done_n[0]
        return it
    with cf.ThreadPoolExecutor(max_workers=WORKERS2) as ex:
        return list(ex.map(one, enumerate(items)))


def sid_of(topic, n, wide, meta):
    return hashlib.md5((topic + "|" + str(n) + "|" + ("w" if wide else "n") +
                        ("+m" if meta else "-m")).encode()).hexdigest()[:16]


def start_scan(topic, n, wide, meta=True):
    n = max(3, min(MAXN, int(n or DEF_N)))
    sid = sid_of(topic, n, wide, meta)
    f = SCN_DIR / (sid + ".json")
    if f.exists() and (dt.datetime.now() - dt.datetime.fromtimestamp(f.stat().st_mtime)).total_seconds() < TTL:
        return {"cached": True, "id": sid}
    jid = hashlib.md5((topic + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": n, "current": "search…", "sid": sid}
    threading.Thread(target=_do_scan, args=(jid, topic, n, sid, wide, meta), daemon=True).start()
    return {"job": jid, "id": sid}


def _do_scan(jid, topic, n, sid, wide, meta=True):
    job = JOBS[jid]
    try:
        items = search_wide(topic, n, wide, job)
        job["total"] = len(items)
        job["current"] = "views/date dekh raha hoon…"
        got = enrich([i["id"] for i in items], job)
        # jo views/dates naap nahi aa sake wo chhupate nahi — scan me likh dete hain,
        # UI chip dikhata hai (views/day unka nahi ginta, baki sab theek ginta hai).
        try:
            vm = sum(1 for i in items if not (got.get(i["id"]) or {}).get("views"))
            if vm:
                fl = job.setdefault("filt", {})
                fl["views_missing"] = vm
                if job.get("api_fill"):
                    fl["api_fill"] = job["api_fill"]
        except Exception:
            pass
        job["done"] = 0                                  # ab thumbnail/OCR ka phase shuru
        THUMB_DIR.mkdir(parents=True, exist_ok=True)

        descs = {}                                   # pura description, sirf semantic tulna ke liye
        CAL = load_cal()                             # apne asli CTR par fit kiye wazan (agar bane hon)
        # poora naap ab module-level measure_items me hai — topic scan aur channel scan
        # DONO wahi chalate hain, do alag raste nahi (warna ek hi naap ka matlab do hota).
        items = measure_items(items, topic, got, job, descs, CAL, meta)
        items.sort(key=lambda i: -(i.get("views") or 0))
        SCN_DIR.mkdir(parents=True, exist_ok=True)
        f = SCN_DIR / (sid + ".json")
        yn = get_yunet()
        CALD = {"n": CAL.get("n"), "r2": CAL.get("r2"), "cv_r2": CAL.get("cv_r2"),
                # `w` bhi scan ke saath likha jaata hai: us din jo wazan chale the sirf
                # wahi us scan ke scores ka matlab hain, aaj badle wazan nahi.
                "w": CAL.get("w"), "src": CAL.get("src")} if CAL else None
        data = {"id": sid, "topic": topic, "n": n, "wide": bool(wide), "meta": bool(meta),
                "ts": dt.datetime.now().isoformat(timespec="seconds"),
                "ocr": bool(find_tesseract()), "pillow": bool(Image), "cv": bool(cv2),
                # ye isliye likha ja raha hai taaki UI wahi bole jo waqai chala, aur user
                # khud dekh sake ki score kis wazan par bana (heuristic ya asli CTR par fit)
                "eng": {"face": ("YuNet (cv2.FaceDetectorYN)" if yn else
                                 ("Haar cascade (kamzor — models download nahi hua)" if cv2 else None)),
                        "ocr": ("RapidOCR PP-OCRv4" if _RAPID_CLS else
                                ("Tesseract (kamzor — rapidocr_onnxruntime nahi hai)" if find_tesseract() else None)),
                        "sem": _TFIDF is not None, "stat": "mann-whitney (pure python)"},
                "filt": job.get("filt") or {}, "cal": CALD,
                "items": items, "agg": agg(items), "deep": deep(items)}
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = repr(e)[:300]
        # poora traceback na bachao to crash ka pata hi nahi chalta — UI aakhri kuch line dikhata hai
        job["tb"] = traceback.format_exc()[-1200:]


# ================= 6c. TRENDING — YouTube ka apna chart (Data API v3) =================
# Ab tak jo scan bante the wo SEARCH se the — matlab hum puchte the "is topic me kaun
# chala". Trending iska ulta hai: YouTube khud batata hai ke aaj us mulk me algorithm
# ne kya upar push kiya. Dono ka matlab alag hai, isliye ye apna rasta hai aur UI me
# saaf "official chart" likha jaata hai — topic scan jaisa dikhakar ye nahi bechta.
#
# Qaaida (poore tool jaisa): ye YouTube ka APNA diya hua data hai (official API), koi
# andaza nahi. Lekin ye key maangta hai: free quota 10,000 units/day, aur videos.list
# (50 videos tak) = sirf 1 unit — yaani ek trending scan = 1 unit, poori tarah muft.
# Key na ho to feature kaam nahi karta aur UI me wohi saaf baat dikhegi — dikhawa nahi.
# Key ka rasta baaki sab jaisa: env YT_API_KEY → tool folder ka youtube_key.txt → UI box.
#
# topicDetails usi ek call me aa jaata hai (extra quota nahi): YouTube ka laga hua
# official topic tag (Wikipedia/Wikidata entity). Ye bhi YouTube ka APNA label hai —
# isliye UI me "official topic tag" likha jaata hai, hamara andaaza nahi.
YT_API = "https://www.googleapis.com/youtube/v3/"
YT_KEY_FILE = HERE / "youtube_key.txt"
TREND_REGIONS = {"PK": "Pakistan", "IN": "Bharat", "US": "America (USA)", "GB": "UK",
                 "CA": "Canada", "AU": "Australia", "AE": "UAE", "SA": "Saudi Arabia",
                 "TR": "Turkey", "DE": "Germany", "FR": "France", "BR": "Brazil",
                 "JP": "Japan", "KR": "Korea", "NG": "Nigeria", "ZA": "South Africa",
                 "ID": "Indonesia", "MY": "Malaysia", "BD": "Bangladesh", "SG": "Singapore"}


def yt_keys():
    return _keypool(["YT_API_KEY", "YOUTUBE_API_KEY"], YT_KEY_FILE)


def yt_key():
    """Pehli key — status/hint ke liye. API calls pool se hoti hain (yt_get dekho)."""
    ks = yt_keys()
    return ks[0] if ks else ""


def yt_set_key(k, add=False):
    return _keysave(YT_KEY_FILE, k, add)


_yt_cur = [0]  # round-robin cursor


def yt_get(endpoint, params):
    """Data API ka ek GET. JSON jawab seedha — error bhi API ke message ke saath, taaki
    UI me asli wajah dikhe (quota khatam / key ghalat / region nahi), andhera error nahi.

    Pool me kai keys ho sakti hain (ek line = ek key): ek key ka daily quota (10,000 units)
    khatam hone par agli key apne aap lag jaati hai — har account ka apna quota hota hai."""
    ks = yt_keys()
    if not ks:
        return {"error": "YouTube Data API key set nahi — env YT_API_KEY, youtube_key.txt, ya Trending card ka key box."}
    n = len(ks)
    last = None
    for i in range(n):
        idx = (_yt_cur[0] + i) % n
        p = dict(params)
        p["key"] = ks[idx]
        url = YT_API + endpoint + "?" + urllib.parse.urlencode(p)
        try:
            j = json.loads(http_get(url, timeout=40).decode("utf-8", "replace"))
            _yt_cur[0] = idx
            return j
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                msg = str(((json.loads(e.read().decode("utf-8", "replace")).get("error") or {}).get("message")) or "")[:200]
            except Exception:
                pass
            last = {"error": "YouTube API HTTP %d%s" % (e.code, (": " + msg) if msg else "")}
            if (e.code in (403, 429) or "quota" in msg.lower() or "ratelimit" in msg.lower()) and n > 1:
                continue  # is key ka quota khatam — agli key azmao
            return last
        except Exception as e:
            return {"error": "YouTube API se baat nahi hui: " + str(e)[:140]}
    return last


def _iso_dur(s):
    """PT1H2M3S jaisa ISO duration → seconds. Na-paaya to 0 (jhooth nahi ginta)."""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", (s or "").strip())
    if not m:
        return 0
    h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + sec


def yt_views(ids):
    """views/date ka doosra rasta: Data API videos.list (50 id = 1 unit, muft). Jab
    yt-dlp bot-block kare tab kaam aata hai — jawab YouTube ka apna number hai, koi
    andaaza nahi. Key na ho ya API ne inkaar kiya to None (enrich khud sambhal lega)."""
    if not yt_key():
        return None
    got = {}
    for i in range(0, len(ids), 50):
        r = yt_get("videos", {"part": "snippet,contentDetails,statistics",
                              "id": ",".join(ids[i:i + 50])})
        if r.get("error"):
            return got or None
        for v in r.get("items") or []:
            vid = (v.get("id") or "")[:11]
            if len(vid) != 11:
                continue
            st = v.get("statistics") or {}
            sn = v.get("snippet") or {}
            up = re.sub(r"\D", "", sn.get("publishedAt") or "")[:8]
            d = None
            if len(up) == 8:
                try:
                    d = dt.date(int(up[:4]), int(up[4:6]), int(up[6:]))
                except Exception:
                    d = None
            got[vid] = {"views": int(st.get("viewCount") or 0),
                        "upload": (up[:4] + "-" + up[4:6] + "-" + up[6:]) if d else "",
                        # poora waqt (ISO publishedAt) — API deta hai, chhupana nuqsan
                        # hai: upload-pattern ghari ke hisaab se tabhi gina ja sakta hai.
                        "pt": (sn.get("publishedAt") or "")[:25],
                        "dur": _iso_dur((v.get("contentDetails") or {}).get("duration") or ""),
                        "channel": sn.get("channelTitle") or "",
                        "days": max(1, (dt.date.today() - d).days) if d else None}
    return got or None


def _topic_tag(u):
    """topicDetails ka Wikipedia/Wikidata link → insaan-readable naam. YouTube ka laga
    hua official tag hai; sirf parda hataya gaya hai, matlab badla nahi."""
    try:
        s = urllib.parse.urlparse(u or "").path.split("/")[-1]
        s = urllib.parse.unquote(s or "")
        s = s.split("#")[-1]
        s = re.sub(r"[_/]+", " ", s).strip()
        return s[:60]
    except Exception:
        return ""


def yt_trend(region, n):
    """chart=mostPopular = YouTube ka apna trending chart us mulk ke liye. Ek call me
    50 videos tak (1 unit). Views/date/lambai API se aate hain — isliye enrich() ki
    zaroorat nahi, aur ye numbers YouTube ka apna diya hua official data hai."""
    items, got = [], {}
    tok = None
    while len(items) < n:
        p = {"part": "snippet,statistics,contentDetails,topicDetails", "chart": "mostPopular",
             "regionCode": region, "maxResults": min(50, n - len(items)), "hl": "en"}
        if tok:
            p["pageToken"] = tok
        j = yt_get("videos", p)
        if j.get("error"):
            return j
        for v in j.get("items") or []:
            vid = v.get("id") if isinstance(v.get("id"), str) else (v.get("id") or {}).get("videoId")
            if not vid or vid in got:
                continue
            sn = v.get("snippet") or {}
            st = v.get("statistics") or {}
            cd = v.get("contentDetails") or {}
            dur = _iso_dur(cd.get("duration"))
            pub = (sn.get("publishedAt") or "")[:10]
            d = None
            try:
                d = dt.date.fromisoformat(pub)
            except Exception:
                d = None
            it = {"id": vid, "title": (sn.get("title") or "").strip(),
                  "chan": sn.get("channelTitle") or "", "fdur": dur}
            tq = []
            for w in ((v.get("topicDetails") or {}).get("topicCategories") or [])[:6]:
                nm = _topic_tag(w.get("webPredictionUri") if isinstance(w, dict) else w)
                if nm:
                    tq.append(nm)
            if tq:
                it["tq"] = tq
            got[vid] = {"views": int(st.get("viewCount") or 0), "upload": pub, "dur": dur,
                        "channel": sn.get("channelTitle") or "",
                        "days": max(1, (dt.date.today() - d).days) if d else None}
            items.append(it)
        tok = j.get("nextPageToken")
        if not tok:
            break
    if not items:
        return {"error": "chart se ek bhi video nahi mila — region ya quota dekho"}
    return {"items": items, "got": got}


def sid_trend(region, n):
    return hashlib.md5(("trend|" + region + "|" + str(n)).encode()).hexdigest()[:16]


def start_trend(region, n):
    region = region if region in TREND_REGIONS else "PK"
    n = max(5, min(50, int(n or 25)))
    sid = sid_trend(region, n)
    f = SCN_DIR / (sid + ".json")
    if f.exists() and (dt.datetime.now() - dt.datetime.fromtimestamp(f.stat().st_mtime)).total_seconds() < TTL:
        return {"cached": True, "id": sid}
    if not yt_key():
        # Job banana bekar hai — bina key ke API chalu hi nahi ho sakti. Saaf wajah do.
        return {"error": "YouTube Data API key set nahi — Trending card ka box, ya youtube_key.txt, ya YT_API_KEY. "
                         "Trending ke liye ye free key chahiye (quota 10,000 units/din); baaki poora tool bina key ke chalta hai."}
    jid = hashlib.md5(("trend" + region + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": n, "current": "YouTube ka trending chart maang raha hoon…", "sid": sid}
    threading.Thread(target=_do_trend, args=(jid, region, n, sid), daemon=True).start()
    return {"job": jid, "id": sid}


def _do_trend(jid, region, n, sid):
    job = JOBS[jid]
    try:
        r = yt_trend(region, n)
        if r.get("error"):
            job["state"] = "error"
            job["error"] = r["error"]
            return
        items, got = r["items"], r["got"]
        job["total"] = len(items)
        job["current"] = "%d videos chart se liye (official Data API)" % len(items)
        job["done"] = 0
        job["filt"] = {"chart_se_aaye": len(items), "source": "YouTube Data API chart=mostPopular"}
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        descs = {}
        CAL = load_cal()
        # wahi poora naap jo topic/channel scan chalate hain — do raste nahi. Trend ka
        # topic label jaan-boojh kar "TRENDING" rakha hai taaki "topic match" naap ka
        # matlab saaf rahe (yahan ye chart ke against hai, search topic ke against nahi).
        topic = "TRENDING " + TREND_REGIONS[region] + " — YouTube ka apna chart"
        items = measure_items(items, topic, got, job, descs, CAL, True)
        items.sort(key=lambda i: -(i.get("views") or 0))
        SCN_DIR.mkdir(parents=True, exist_ok=True)
        f = SCN_DIR / (sid + ".json")
        yn = get_yunet()
        CALD = {"n": CAL.get("n"), "r2": CAL.get("r2"), "cv_r2": CAL.get("cv_r2"),
                "w": CAL.get("w"), "src": CAL.get("src")} if CAL else None
        data = {"id": sid, "topic": topic, "n": n, "wide": False, "meta": True,
                "trend": {"region": region, "name": TREND_REGIONS[region],
                          "src": "YouTube Data API v3, chart=mostPopular (official chart)"},
                "ts": dt.datetime.now().isoformat(timespec="seconds"),
                "ocr": bool(find_tesseract()), "pillow": bool(Image), "cv": bool(cv2),
                "eng": {"face": ("YuNet (cv2.FaceDetectorYN)" if yn else
                                 ("Haar cascade (kamzor — models download nahi hua)" if cv2 else None)),
                        "ocr": ("RapidOCR PP-OCRv4" if _RAPID_CLS else
                                ("Tesseract (kamzor — rapidocr_onnxruntime nahi hai)" if find_tesseract() else None)),
                        "sem": _TFIDF is not None, "stat": "mann-whitney (pure python)"},
                "filt": job.get("filt") or {}, "cal": CALD,
                "items": items, "agg": agg(items), "deep": deep(items)}
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = repr(e)[:300]
        job["tb"] = traceback.format_exc()[-1200:]


# ================= 6d. Bahar ki garmahat — Reddit + Google Trends (dono UNOFFICIAL) ====
# Ideas page ke liye bahar ke do signal. Imaandari sabse aage:
#   Reddit ka public JSON — koi key nahi, lekin official API nahi hai; Reddit kabhi
#     block karta hai to saaf error dikhega. Jo dikhega wo LOGON ne likha hai —
#     community demand ka signal, koi naap nahi.
#   Google Trends via pytrends — third-party library, unofficial; interest 0-100 ka
#     NISBAT hai, exact search ginti nahi. pytrends na mile to feature saaf-saaf
#     "install karo" bolega — chupchap gayab nahi hoga.
RD_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _rd_json(topic, limit):
    u = ("https://www.reddit.com/search.json?limit=%d&sort=top&t=year&q=%s"
         % (limit, urllib.parse.quote(topic)))
    req = urllib.request.Request(u, headers={"User-Agent": RD_BROWSER_UA,
                                            "Accept": "application/json",
                                            "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode("utf-8", "replace"))
    out = []
    for c in ((j.get("data") or {}).get("children") or []):
        dd = c.get("data") or {}
        if not (dd.get("title") or "").strip():
            continue
        out.append({"t": str(dd["title"]).strip()[:160], "sub": str(dd.get("subreddit") or "")[:40],
                    "score": int(dd.get("score") or 0), "cmts": int(dd.get("num_comments") or 0),
                    "url": "https://reddit.com" + str(dd.get("permalink") or "")})
    return out


def _rd_rss(topic, limit):
    """RSS aakhri rasta: JSON 403 karta hai to bhi ye chalta hai. Sach: RSS me vote aur
    jawab ki ginti NAHI hoti — isliye yahan wo None jaate hain aur UI me dikhte hi nahi,
    sirf sawal dikhte hain. Number ka dawa kabhi nahi."""
    import xml.etree.ElementTree as ET
    u = ("https://www.reddit.com/search.rss?limit=%d&sort=top&t=year&q=%s"
         % (limit, urllib.parse.quote(topic)))
    req = urllib.request.Request(u, headers={"User-Agent": RD_BROWSER_UA,
                                            "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.iter():
        if not e.tag.endswith("}entry"):
            continue
        title = ""
        link = ""
        sub = ""
        pub = ""
        for ch in e:
            tag = ch.tag.split("}")[-1]
            if tag == "title":
                title = (ch.text or "").strip()
            elif tag == "link":
                link = ch.attrib.get("href") or (ch.text or "")
            elif tag == "category":
                sub = (ch.attrib.get("term") or "").replace("r/", "")
            elif tag in ("published", "updated"):
                pub = (ch.text or "")[:10]
        if not title:
            continue
        out.append({"t": title[:160], "sub": sub[:40], "score": None, "cmts": None,
                    "url": str(link)[:200], "date": pub})
    return out


def rd_search(topic, limit=25):
    topic = (topic or "").strip()
    if not topic:
        return {"error": "topic daalo"}
    limit = max(5, min(50, int(limit or 25)))
    codes = []
    for fn, via in ((_rd_json, "json"), (_rd_rss, "rss")):
        try:
            posts = fn(topic, limit)
            if posts:
                return {"ok": True, "posts": posts[:limit], "via": via}
            codes.append(via + ":khali")
        except urllib.error.HTTPError as e:
            codes.append(via + ":" + str(e.code))
        except Exception as e:
            codes.append(via + ":" + str(e)[:40])
    if any(c.endswith(":429") for c in codes):
        return {"error": "Reddit ne abhi roka hai (bahut jaldi-ba-jaldi maanga) — 1–2 minute baad dobara try karo"}
    return {"error": "Reddit jawab nahi de saka (" + ", ".join(codes) + ") — ye public feed unofficial hai, "
                     "Reddit beech-beech me block karta hai. Ye tool ka naap nahi rokta, sirf ye hisala abhi nahi khula."}


def tr_interest(topic):
    """Google Trends ka 12-mahine ka interest + related queries. Sirf tab jab pytrends
    installed ho; warna saaf message. Numbers 0-100 nisbat hain — isliye UI me direction
    (barh raha/gir raha) dikhate hain, koi 'exact searches' ka jhooth nahi."""
    topic = (topic or "").strip()[:80]
    if not topic:
        return {"error": "topic daalo"}
    try:
        from pytrends.request import TrendReq
    except Exception:
        return {"error": "pytrends install nahi hai — `pip install pytrends` se ye hisala khul jayega "
                         "(wo bhi Google ka unofficial data hi rahega)"}
    try:
        # retries/backoff_factor NAHI dete: pytrends wo urllib3 ke purane Retry kwargs se
        # banata hai jo urllib3 2.x me hata diye gaye — inke bina bhi kaam chalta hai.
        tr = TrendReq(hl="en-US", tz=330, timeout=(10, 30))
        tr.build_payload([topic], timeframe="today 12-m")
        df = tr.interest_over_time()
        if df is None or df.empty or topic not in df.columns:
            return {"error": "Google Trends ne is topic ka data nahi diya (bahut naya ya bahut chhota topic ho sakta hai)"}
        vals = [int(x) for x in df[topic].values][-90:]
        rq = []
        try:
            r = tr.related_queries() or {}
            ent = r.get(topic) or {}
            for k in ("top", "rising"):
                dft = ent.get(k)
                if dft is not None and len(dft):
                    for _, row in dft.head(6).iterrows():
                        q = str(row.get("query") or "").strip()
                        if q:
                            rq.append({"q": q[:60], "v": int(row.get("value") or 0), "k": k})
        except Exception:
            pass
        half = max(1, len(vals) // 2)
        a = sum(vals[:half]) / float(half)
        b = sum(vals[half:]) / float(max(1, len(vals) - half))
        dirn = "barh raha" if b > a * 1.15 else ("gir raha" if b < a * 0.85 else "ek jaisa")
        return {"ok": True, "series": vals, "dir": dirn, "rel": rq[:12],
                "from": str(df.index[0].date()), "to": str(df.index[-1].date())}
    except Exception as e:
        return {"error": "Google Trends (pytrends) jawab nahi de saka: " + str(e)[:160] +
                         " — ye unofficial library hai, Google bheer me block kar deta hai; thori der baad dobara try karo"}


# ================= 7. POORA CHANNEL: naam / link / channel id se =================
# Topic scan ka engine yahi chalta hai; farq sirf itna hai ke videos topic ki search se
# nahi, ek channel ki apni listing se aate hain. Isliye channel kholne ke baad har cheez
# (thumbnail naap, OCR, asli tags, Deep Analysis, ideas, CSV) bilkul waisi hi milti hai
# jaisi topic scan me — do alag raste nahi rakhe gaye, warna ek hi naap ka matlab do hota.
#
# Probe (26 Oct, isi machine par, yt-dlp se naapa gaya):
#   results?search_query=..&sp=EgIQAg%253D%253D  (flat) -> 50 channels 3.5s me. Har entry
#       me channel_id, naam, subscriber (channel_follower_count), verified, description,
#       thumbnail aati hai. "kul videos" is me NAHI aata (playlist_count khali).
#   <channel>/videos aur /shorts (flat) -> id, title, duration (100 videos ~3s). is tab me
#       view_count aur upload_date KHALI aate hain — isliye views/date har video se alag
#       lene padte hain (enrich + meta_of, dono disk-cache karte hain).
#   <channel>/about -> naam, @handle, subscriber, description, channel ke apne tags.
#       "Joined" date aur channel ka "total views" yt-dlp ko NAHI milta (view_count = None),
#       isliye neeche "kul views" = jitne videos humne padhe unka jama hai, poora channel
#       nahi — aur ye baat UI me likhi jaati hai.
#   kisi bhi video ke poore -J JSON me "monet" ka ek bhi field ya substring NAHI mila
#       (poore JSON me gina: 0). YouTube monetization public nahi karta — isliye ye sirf
#       ANDAAZA hai, naap nahi; aur RPM/CPM bhi public nahi (creator-reported ranges hain).

CH_DIR = OUT / "chc"
CH_TTL = 24 * 3600          # channel listing + search ek din purani chalegi
CHN_DEF = 400               # channel ki saari gini gayi long videos naapi jaati hain (partial naap default nahi)
CHN_MAX = 400               # listing cap (CH_WALK) se zyada ki gunthish nahi — uske aage "+" dikhta hai
CH_SHORT_MAX = 400          # shorts bhi poori listing tak naape jaate hain, sirf gine nahi jaate
CH_WALK = 400               # listing ginne ke liye itne ids tak chalo; uske aage ">400" likha jaata hai

# SponsorBlock — logon ka banaya hua data (community marks), YouTube ya is tool ka naap
# nahi. Sirf sponsor aur self-promo segments lete hain (ads jaisa); intro/outro/filler
# jaan-boojh ke bahar hain. Jis video par koi mark nahi wo API me aati hi nahi — isliye
# UI hamesha "koi mark nahi" likhega, "0 seconds ads" kabhi nahi.
SPON_URL = "https://sponsor.ajay.app/api/skipSegments"
SPON_CATS = ["sponsor", "selfpromo"]

# YouTube ka category (categories[0]) ASLI field hai jo har video par laga hota hai — pehle
# wahi dekha jaata hai. Keyword table sirf doosri taraf se madad ke liye hai, aur RPM ki
# ranges public creator-reported ranges hain (YouTube RPM public nahi karta).
NICHES = [
    ("finance/business", ("loan", "business", "money", "stock", "shares", "invest", "salary", "income",
                          "finance", "crypto", "startup", "tax", "gold", "petrol", "price", "earning"),
     (4.0, 12.0)),
    ("tech/gadgets", ("phone", "mobile", "gadget", "review", "laptop", "specs", "5g", "app", "wifi",
                      "iphone", "android", "software", "update", "tech"), (3.0, 8.0)),
    ("education/exam", ("exam", "result", "admission", "syllabus", "course", "class", "physics",
                        "chemistry", "math", "history", "geography", "science", "study", "sir"), (2.0, 6.0)),
    ("news/politics", ("news", "breaking", "government", "election", "update", "today", "pm", "cm"),
     (1.0, 3.0)),
    ("how-to/tools", ("how", "trick", "tricks", "settings", "download", "install", "apply", "online",
                      "registration", "form", "check", "kaise"), (2.0, 5.0)),
    ("health/fitness", ("health", "weight", "diet", "exercise", "workout", "doctor", "disease", "tips"),
     (2.0, 6.0)),
    ("gaming", ("game", "gaming", "minecraft", "pubg", "fire", "fortnite", "gameplay"), (1.5, 4.0)),
    ("entertainment/vlog", ("vlog", "comedy", "funny", "reaction", "interview", "song", "movie",
                            "trailer", "challenge"), (1.0, 3.0)),
    ("devotional/motivation", ("motivation", "motivational", "status", "wazifa", "quran", "islamic",
                               "bayyan", "durood", "naat"), (0.5, 2.0)),
    ("science/documentary", ("documentary", "space", "galaxy", "universe", "planet", "black", "hole",
                             "explainer", "mystery"), (2.0, 6.0)),
    ("cooking", ("recipe", "cooking", "khana", "cook", "biryani"), (1.0, 3.0)),
    ("kids", ("cartoon", "kids", "nursery", "rhyme", "habby"), (1.0, 2.5)),
]
SHORT_RPM = (0.05, 0.30)    # shorts ka RPM longs se kaafi kam hota hai (public ranges)
CAT_NICHE = {"Science & Technology": "science/documentary", "Education": "education/exam",
             "News & Politics": "news/politics", "Film & Animation": "entertainment/vlog",
             "People & Blogs": "entertainment/vlog", "Entertainment": "entertainment/vlog",
             "Gaming": "gaming", "Howto & Style": "how-to/tools", "Autos & Vehicles": "finance/business",
             "Music": "entertainment/vlog", "Comedy": "entertainment/vlog",
             "Travel & Events": "entertainment/vlog"}


def _cget(key, ttl=CH_TTL):
    try:
        p = CH_DIR / (key + ".json")
        if p.exists() and (dt.datetime.now() - dt.datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() < ttl:
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _cput(key, data):
    try:
        CH_DIR.mkdir(parents=True, exist_ok=True)
        (CH_DIR / (key + ".json")).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def ch_search(q, n=50):
    """Naam se channel dhoondho — YouTube ke apne 'Channel' filter se (sp=EgIQAg==).
    Sirf wahi channels laate hain jinke channel_id hain; subscriber/verified/description
    YouTube ka diya hua hai, mera likha hua nahi."""
    q = (q or "").strip()
    if not q:
        return []
    n = max(1, min(60, int(n or 50)))
    key = "sch_" + hashlib.md5((q + "|" + str(n)).encode()).hexdigest()[:16]
    c = _cget(key)
    if c is not None:
        return c
    y = find_ytdlp()
    url = ("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q) +
           "&sp=EgIQAg%253D%253D")
    rc, out, err = run([y, "--no-update", "--no-warnings", "--flat-playlist", "-J",
                        "--playlist-end", str(n), url], timeout=200)
    try:
        j = json.loads(out or "")
    except Exception:
        j = None
    got = []
    for e in ((j or {}).get("entries") or []):
        if not e or not e.get("channel_id"):
            continue
        cu = e.get("channel_url") or ("https://www.youtube.com/channel/" + e["channel_id"])
        h = re.search(r"@[\w.\-]{2,}", (e.get("uploader_url") or "") + " " + cu)
        got.append({"id": e["channel_id"], "name": (e.get("channel") or e.get("title") or "").strip(),
                    "handle": (h.group(0) if h else ""), "url": cu,
                    "subs": e.get("channel_follower_count") or 0,
                    "ver": bool(e.get("channel_is_verified")),
                    "desc": re.sub(r"\s+", " ", e.get("description") or "")[:220],
                    "thumb": ((e.get("thumbnails") or [{}])[-1] or {}).get("url") or ""})
    _cput(key, got)
    return got


def ch_info(url):
    """Channel ka about page: naam, @handle, subscriber, description, channel ke apne tags.
    (Joined date aur channel ka total views yt-dlp ko nahi milta — isliye yahan nahi hai.)"""
    key = "inf_" + hashlib.md5(url.encode()).hexdigest()[:16]
    c = _cget(key)
    if c is not None:
        return c
    y = find_ytdlp()
    rc, out, err = run([y, "--no-update", "--no-warnings", "-J", url.rstrip("/") + "/about"], timeout=150)
    try:
        j = json.loads(out or "")
    except Exception:
        j = None
    if not isinstance(j, dict):
        return {"err": "channel ka page nahi khula: " + re.sub(r"\s+", " ", (err or ""))[:160]}
    d = {"id": j.get("channel_id") or "", "name": j.get("channel") or j.get("title") or "",
         "handle": j.get("uploader_id") or (j.get("id") if str(j.get("id") or "").startswith("@") else ""),
         "url": j.get("channel_url") or url, "subs": j.get("channel_follower_count") or 0,
         "desc": re.sub(r"\s+", " ", j.get("description") or "")[:500],
         "tags": [str(t) for t in (j.get("tags") or [])][:20],
         "got": dt.datetime.now().isoformat(timespec="seconds")}
    _cput(key, d)
    return d


_MON = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def chan_joined(url):
    """Channel ki \"Joined\" date — YouTube ke APNE About page se. Ye date YouTube
    page par dikhata hai par Data API me nahi deta, isliye public HTML padh kar
    nikalti hai. Na mile to None — dikhane wala jagah khud fallback sambhalta hai
    (sabse purani listing), aur source label hamesha saath rehta hai."""
    if not url:
        return None
    key = "join_" + hashlib.md5(url.split("?")[0].encode()).hexdigest()[:16]
    c = _cget(key, 604800)          # positive: 7 din kaafi hai (joined date badalti nahi)
    if isinstance(c, dict):
        return c
    if _cget(key, 21600) is False:  # negative sirf 6 ghante — network kabhi bhi rok sakta hai
        return None
    try:
        req = urllib.request.Request(url.rstrip("/").split("?")[0] + "/about?hl=en",
                                     headers={"User-Agent": RD_BROWSER_UA,
                                              "Accept-Language": "en-US,en;q=0.6"})
        html = urllib.request.urlopen(req, timeout=25).read(500000).decode("utf-8", "ignore")
        m = re.search(r"Joined ([A-Z][a-z]{2,8}) (\d{1,2}), (\d{4})", html)
        mo = _MON.get(m.group(1)) if m else None
        if not mo:
            _cput(key, False)
            return None
        d = {"d": dt.date(int(m.group(3)), mo, int(m.group(2))).isoformat(), "src": "about"}
    except Exception:
        _cput(key, False)
        return None
    _cput(key, d)
    return d


def joined_or_oldest(ch, its):
    """joined = About page ki date; na mile to scan me sabse purani upload date,
    label ke saath — dono ka matlab alag hai, isliye src field hamesha bhar bhejte
    hain. Dono na milein to None (UI me \"—\" aur wajah likhi aayegi)."""
    j = chan_joined((ch or {}).get("url") or "")
    if j:
        return j
    ds = sorted([str(i.get("upload") or "")[:10] for i in (its or [])
                 if re.match(r"^\d{4}-\d{2}-\d{2}$", str(i.get("upload") or ""))])
    if ds:
        return {"d": ds[0], "src": "oldest"}
    return None


def api_join(sid):
    """Perane channel scans ke liye joined date le aao (button par). Scan file me
    likh deta hoon — dobara khulne par dobara network nahi."""
    p = SCN_DIR / (sid + ".json")
    if not p.exists():
        return {"err": "scan file nahi mila"}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"err": "scan file padhi nahi ja saki"}
    if d.get("kind") != "channel":
        return {"err": "ye topic scan hai — isme ek channel ki joined date nahi hoti"}
    ch = d.get("ch") or {}
    j0 = ch.get("joined")
    if j0 and j0.get("src") == "about":
        return {"ok": True, "joined": j0, "already": True}
    j = chan_joined(ch.get("url") or "") or j0  # oldest wali purani entry upgrade ho sakti hai
    if not j:
        j = joined_or_oldest({"url": ""}, d.get("items"))  # about dobara mat kholo, sirf listing
    if not j:
        return {"err": "About page se date nahi mili, aur na koi video date — isliye kuch likhne layak nahi"}
    upgraded = bool(j0 and j.get("src") == "about" and j0.get("src") != "about")
    ch["joined"] = j
    d["ch"] = ch
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "joined": j, "upgraded": upgraded}


# ---------------- Competitor bank: aapki chuni hui videos ka apna record ----------------
# Har record us waqt ke scan ka snapshot hai (title/views us din ke) — ye baat UI me
# bhi likhi jaati hai. Bank file plain JSON hai, thumb_output me, taake zip me bhi
# saath chale.
CMPB_F = OUT / "cmpbank.json"


def cmpb_load():
    try:
        d = json.loads(CMPB_F.read_text(encoding="utf-8"))
        return d if isinstance(d.get("items"), list) else {"items": []}
    except Exception:
        return {"items": []}


def cmpb_put(d):
    OUT.mkdir(parents=True, exist_ok=True)
    CMPB_F.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _cmpb_enrich(rec, it, sc):
    # Ek video ka record us scan ke asli numbers se bharta hai — save aur seed dono
    # yahi karte hain, taake dono ka record ek jaisa ho.
    rec["title"] = (it.get("title") or "")[:200]
    rec["chan"] = (it.get("channel") or "")[:120]
    rec["views"] = it.get("views") or 0
    rec["days"] = it.get("days")
    rec["upl"] = str(it.get("upload") or "")[:10] or None
    rec["vpd"] = round(vpd(it), 1)
    rec["thumb"] = it.get("thumb") or ""
    ch = sc.get("ch") or {}
    if sc.get("kind") == "channel":
        rec["chan"] = rec.get("chan") or (ch.get("name") or "")
        rec["chanurl"] = ch.get("url") or ""
        rec["subs"] = ch.get("subs") or 0
        rec["joined"] = ch.get("joined") or joined_or_oldest(ch, sc.get("items"))
        ds = sorted([str(x.get("upload") or "")[:10] for x in (sc.get("items") or [])
                     if re.match(r"^\d{4}-\d{2}-\d{2}$", str(x.get("upload") or ""))])
        if ds:
            rec["lastup"] = {"d": ds[-1], "src": "scan"}


def cmpb_save(d):
    vid = (d.get("vid") or "")[:11]
    if len(vid) != 11:
        return {"err": "video id nahi mila — bank me save nahi hua"}
    sid = (d.get("id") or "")[:16]
    rec = {"vid": vid, "at": dt.datetime.now().isoformat(timespec="seconds"),
           "style": (d.get("style") or "")[:30], "nic": (d.get("nic") or "")[:80],
           "note": (d.get("note") or "")[:400], "scan": sid}
    p = SCN_DIR / (sid + ".json")
    if sid and p.exists():
        try:
            sc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            sc = None
        if sc:
            it = next((x for x in (sc.get("items") or []) if (x.get("id") or "")[:11] == vid), None)
            if it:
                _cmpb_enrich(rec, it, sc)
    b = cmpb_load()
    b["items"] = [x for x in b["items"] if (x.get("vid") or "")[:11] != vid]
    b["items"].insert(0, rec)
    b["items"] = b["items"][:500]
    cmpb_put(b)
    return {"ok": True, "n": len(b["items"]), "rec": rec}


def cmpb_del(vid):
    b = cmpb_load()
    n0 = len(b["items"])
    b["items"] = [x for x in b["items"] if (x.get("vid") or "")[:11] != (vid or "")[:11]]
    cmpb_put(b)
    return {"ok": True, "gone": n0 - len(b["items"]), "n": len(b["items"])}


def cmpb_seed(d):
    # Ek click me: us scan ki jeeti hui videos bank me bhar do. Jeet ka rule wahi hai
    # jo screen par likha hai — views/day median se 2× ya zyada. Style classifier ka
    # andaza bhar jaata hai aur note me saaf likha jaata hai ke wo andaza hai — user
    # baad me theek kar sakta hai. Jo videos pehle se bank me hain wo dobara nahi judti.
    # Ye bhi sirf button ke click se hota hai — koi background kaam nahi.
    sid = (d.get("id") or "")[:16]
    try:
        k = max(1, min(int(d.get("k") or 10), 50))
    except Exception:
        k = 10
    p = SCN_DIR / (sid + ".json")
    if not p.exists():
        return {"error": "scan file nahi mili — pehle koi scan chuno"}
    try:
        sc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "scan file padhi nahi ja saki"}
    its = sc.get("items") or []
    vs = sorted(vpd(x) for x in its if vpd(x) > 0)
    if len(vs) < 6:
        return {"error": "jeet ka naap kam se kam 6 napri videos maangta hai — is scan me %d hain" % len(vs)}
    med = vs[len(vs) // 2]
    if med <= 0:
        return {"error": "median views/day zero hai — jeet ka rule is scan par nahi chal sakta"}
    sty = sc.get("sty") or {}
    b = cmpb_load()
    have = {(x.get("vid") or "")[:11] for x in b["items"]}
    win = [x for x in its if vpd(x) >= 2.0 * med]
    win.sort(key=lambda x: -vpd(x))
    added = 0
    for it in win:
        vid = (it.get("id") or "")[:11]
        if len(vid) != 11 or vid in have:
            continue
        rec = {"vid": vid, "at": dt.datetime.now().isoformat(timespec="seconds"),
               "style": str(sty.get(vid) or sty.get((it.get("id") or "")) or "unknown")[:30],
               "nic": (sc.get("topic") or "")[:80]}
        rec["note"] = ("auto-bhara: is scan ki jeeti hui video (views/day median ke 2x+). "
                       "Style classifier ka andaza hai — galat ho to theek kar dein.")[:400]
        rec["scan"] = sid
        _cmpb_enrich(rec, it, sc)
        b["items"].insert(0, rec)
        have.add(vid)
        added += 1
        if added >= k:
            break
    b["items"] = b["items"][:500]
    cmpb_put(b)
    return {"ok": True, "added": added, "win": len(win), "n": len(b["items"])}


def ch_lists(url, cap=CH_WALK):
    """Channel ki apni /videos aur /shorts listing (flat = sirf id/title/duration, tezi se).
    Shorts tab na hone par YouTube error deta hai — uska matlab shorts 0 hain, crash nahi."""
    y = find_ytdlp()
    out = {"videos": [], "shorts": [], "terr": ""}

    def tab(path):
        rc, o, e = run([y, "--no-update", "--no-warnings", "--flat-playlist", "-J", "--ignore-errors",
                        "--playlist-end", str(int(cap)), url.rstrip("/") + path], timeout=300)
        try:
            j = json.loads(o or "")
        except Exception:
            return [], re.sub(r"\s+", " ", (e or ""))[:160]
        vs = []
        for it in ((j or {}).get("entries") or []):
            if not it or not it.get("id"):
                continue
            vs.append({"id": it["id"], "title": (it.get("title") or "").strip(),
                       "dur": pnum(it.get("duration")) or 0,
                       # flat listing me YouTube view_count aur timestamp (andazanan upload
                       # ka waqt) deta hai — ye ASLI gin hai, isliye bina naap ki hui video
                       # par bhi Views/date dikha sakte hain. Na milne par None.
                       "views": pnum(it.get("view_count")),
                       "ts": pnum(it.get("timestamp"))})
        return vs, ("" if "does not have" not in (e or "") else "is channel ka koi shorts tab nahi")

    out["videos"], e1 = tab("/videos")
    out["shorts"], out["terr"] = tab("/shorts")
    return out


def walk_pack(ls):
    """Listing ko scan file me rakhne layak chhota shape (id/title/duration/views).
    Ye poora naap NAHI hai — sirf gin ki list hai, taaki Content table me channel ki
    poori listing dikhe aur saaf likha rahe ke kis par naap hua aur kis par nahi.
    Views flat listing me YouTube khud deta hai (jo deta hai; na milne par None)."""
    def p(vs, sh):
        return [{"id": v["id"], "t": v["title"], "d": v.get("dur") or 0, "ts": v.get("ts"),
                 "w": v.get("views"), "s": sh} for v in vs if v.get("id")]
    return {"got": dt.datetime.now().isoformat(timespec="seconds"),
            "terr": ls.get("terr") or "", "cap": CH_WALK,
            "v": p(ls.get("videos") or [], 0), "s": p(ls.get("shorts") or [], 1)}


def ensure_walk(sid, force=False):
    """Purani channel scan file me listing nahi bachi thi — YouTube se flat listing
    dhoondh kar usi file me likh do (24 ghante ka cache). Ye sirf ginna hai, koi
    naap nahi: views/date/thumbnail ke poore naap ke liye us video par kaam chalta hai.
    Listing na milne par kuch likhe bina None wapas — taaki adhoori listing file me
    paakad na jaye aur agli baar phir try ho sake."""
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("walk") and not force:
        return d["walk"]
    url = ((d.get("ch") or {}).get("url") or "").strip()
    if d.get("kind") != "channel" or not url:
        return None
    key = "walk_" + hashlib.md5(url.encode()).hexdigest()[:16]   # key filesystem-safe
    wk = None if force else _cget(key, CH_TTL)
    if not wk:
        wk = walk_pack(ch_lists(url))
        if not (wk["v"] or wk["s"]):
            return None
        _cput(key, wk)
    d["walk"] = wk
    ch = d.setdefault("ch", {})
    ch["tot_videos"] = len(wk["v"])
    ch["tot_shorts"] = len(wk["s"])
    ch["walk_cap"] = CH_WALK
    d["cst"] = chan_stats(d)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return wk


def extend_chan(sid, k=20, kind="long", ids=None):
    """Usi channel scan me jo videos ab tak naap se bahar rah gayi thin un par wahi
    engine chalao (views/date + asli metadata + thumbnail/OCR/score) aur natija usi
    scan file me jod do. Koi naya formula nahi — jo channel scan chalata tha wahi.
    `ids` do to bas wahi videos; warna listing ke order me aage se."""
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    d = json.loads(f.read_text(encoding="utf-8"))
    wk = d.get("walk") or ensure_walk(sid)
    if not wk:
        return {"err": "channel ki listing dobara nahi mil saki — naya channel scan chalao"}
    have = set(i.get("id") for i in (d.get("items") or []))
    pool = ([v for v in wk["v"] if kind in ("long", "all")] +
            [v for v in wk["s"] if kind in ("short", "all")])
    if ids:
        want = set(ids)
        pool = [v for v in wk["v"] + wk["s"] if v["id"] in want]
    # 60 ki hadd purani thi — ab poori listing (CH_WALK) tak naap sakte hain, kyun ki
    # ab har khep ka natija foran file me likha jaata hai aur table zinda rehta hai.
    todo = [v for v in pool if v["id"] not in have][:max(1, min(CH_WALK, int(k or 20)))]
    if not todo:
        return {"err": "naap ke liye koi nayi video bachi hi nahi (ya listing khaali hai)"}
    jid = hashlib.md5(("ext|" + sid + "|" + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": len(todo), "current": "views/date…", "sid": sid,
                 "eta": meas_eta(len(todo))}
    threading.Thread(target=_do_extend, args=(jid, sid, todo), daemon=True).start()
    return {"job": jid, "id": sid, "n": len(todo), "eta": meas_eta(len(todo))}


def chan_recalc(d):
    """Scan file ka har hissa items se dobara nikalta hai — is liye naap ke beech me
    bhi file apne aap se milti hui rehti hai (adhura record kabhi nahi dikhta)."""
    items = d.get("items") or []
    longs = [i for i in items if not i.get("sh")]
    shorts = [i for i in items if i.get("sh")]
    d["agg"] = agg(longs)
    d["deep"] = deep(longs)
    ch = d.setdefault("ch", {})
    ch["analyzed_long"] = len(longs)
    ch["analyzed_short"] = len(shorts)
    d["cov"] = ("channel me se %d videos analyze hui (listing me se sabse nayi), "
                "baaki sirf gini gayi hain" % (len(longs) + len(shorts)))
    d["ts2"] = dt.datetime.now().isoformat(timespec="seconds")
    d["cst"] = chan_stats(d)
    return d


def ts_backfill(sid):
    """Purane scan ki videos me chhapne ka waqt bhar do. Wo field purani metadata cache
    me thi hi nahi, is liye poori naap dobara karne ki zaroorat nahi — sirf un videos ki
    metadata dobara padhi jaati hai jinke paas waqt nahi hai. Thumbnail/OCR/chehra
    bilkul dobara nahi chalta, is liye ye kaam naap se kaafi sasta hai."""
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    d = json.loads(f.read_text(encoding="utf-8"))
    todo = [i for i in (d.get("items") or []) if not i.get("pubts")]
    if not todo:
        return {"err": "har video ka waqt pehle se mojood hai"}
    jid = hashlib.md5(("tsb|" + sid + "|" + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": len(todo),
                 "current": "chhapne ka waqt…", "sid": sid}
    threading.Thread(target=_do_tsback, args=(jid, sid), daemon=True).start()
    return {"job": jid, "id": sid, "n": len(todo)}


def _do_tsback(jid, sid):
    job = JOBS[jid]
    try:
        f = SCN_DIR / (sid + ".json")
        d = json.loads(f.read_text(encoding="utf-8"))
        items = d.get("items") or []
        todo = [i for i in items if not i.get("pubts")]
        got = [0]

        def one(it):
            job["current"] = "chhapne ka waqt: " + str(it.get("title") or "")[:44]
            m = meta_of(it["id"])
            if m.get("ts"):
                it["pubts"] = int(m["ts"])
                got[0] += 1
            with _lock:
                job["done"] += 1
                if job["done"] % 24 == 0:
                    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(max_workers=min(WORKERS, max(1, len(todo)))) as ex:
            list(ex.map(one, todo))
        # Scan file ka waqt-wala hissa items se hi nikalta hai, is liye recalc zaroori
        # hai — warna panel purani ginti hi dikhata rahega.
        chan_recalc(d)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        job["found"] = got[0]
        job["elapsed"] = round(time.perf_counter() - t0, 1)
        job["current"] = "%d me se %d videos ka poora waqt mila" % (len(todo), got[0])
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = str(e)


def spon_get(vid):
    """SponsorBlock se ek video ke marks. API docs ke mutabiq jis video par in categories
    ka koi segment nahi wo 404 deta hai — wo "koi mark nahi" hai, galti nahi. (29 Oct ko
    live test: ek videoID per request chalta hai, batch forms nahi chalte — is liye ye
    ek-ek video maangta hai aur do requests ke beech thaharta hai.)"""
    url = (SPON_URL + "?videoID=" + urllib.parse.quote(vid) +
           "&category=" + "&category=".join(urllib.parse.quote(c) for c in SPON_CATS))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise


def spon_measure(sid):
    """Channel scan ki saari gini gayi videos (naapi hui aur sirf gini gayi — sab) par
    SponsorBlock ke sponsor/self-promo marks jodo. Ye community ka data hai — naap nahi;
    jo video bina marks ki hain un par kuch nahi likha jaayega."""
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    d = json.loads(f.read_text(encoding="utf-8"))
    wk = d.get("walk") or ensure_walk(sid)
    if wk:
        ids = [v.get("id") for v in wk["v"] + wk["s"]]
    else:
        ids = [i.get("id") for i in (d.get("items") or [])]
    ids = [i for i in ids if i]
    if not ids:
        return {"err": "is scan me koi video id nahi mili"}
    jid = hashlib.md5(("spon|" + sid + "|" + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": len(ids),
                 "current": "SponsorBlock se marks…", "sid": sid}
    threading.Thread(target=_do_spon, args=(jid, sid, ids), daemon=True).start()
    return {"job": jid, "id": sid, "n": len(ids)}


def _do_spon(jid, sid, ids):
    # Ek request ek video ka (SponsorBlock ke naye API me batch forms nahi chalte —
    # live test se pata chala), aur do request ke beech thahao — ye community server
    # hai, is par bojh daalna nahi. Har 24 videos ke baad file likhi jaati hai taake
    # adhoora kaam bhi foran table me dikhe.
    job = JOBS[jid]
    try:
        f = SCN_DIR / (sid + ".json")
        d = json.loads(f.read_text(encoding="utf-8"))
        sp = d.setdefault("spon", {})
        got = [0]
        miss = [0]
        t0 = time.perf_counter()
        for a, vid in enumerate(ids):
            job["current"] = "SponsorBlock: %d/%d" % (a + 1, len(ids))
            segs_raw = None
            try:
                segs_raw = spon_get(vid)
            except Exception:
                miss[0] += 1
            if segs_raw:
                segs = [[round(s["segment"][0]), round(s["segment"][1]), s.get("category") or ""]
                        for s in segs_raw if s.get("segment")]
                if segs:
                    sp[vid] = {"sec": sum(s[1] - s[0] for s in segs), "n": len(segs), "segs": segs[:30]}
                    got[0] += 1
            with _lock:
                job["done"] = a + 1
                if (a + 1) % 24 == 0:
                    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.3)
        with _lock:
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        job["found"] = got[0]
        job["failed"] = miss[0]
        job["elapsed"] = round(time.perf_counter() - t0, 1)
        job["current"] = ("%d videos par marks mile, %d par koi mark nahi" %
                          (got[0], len(ids) - got[0] - miss[0])) + \
                         ((", %d par server jawab nahi de saka (wo adhoore chhod do — dobara chala sakte ho)" % miss[0])
                          if miss[0] else "")
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = str(e)


def meas_eta(n):
    """Naap ka waqt andazan. Ye andaza hawa se nahi bana: 25 Oct ko is machine par
    alag naapa gaya — ek nayi video ka metadata (yt-dlp) ~3s, aur uska thumbnail/OCR/
    chehra ~0.5-1s. Kaam WORKERS aur WORKERS2 threads par parallel chalta hai. Range
    is liye deta hoon ke YouTube ki raftaar hi sab se bara mutasir karne wala hai."""
    lo = n * (ENRICH_SEC / WORKERS + MEASURE_SEC / WORKERS2)
    return [int(round(lo * 0.7)), int(round(lo * 2.5))]


def _do_extend(jid, sid, todo):
    job = JOBS[jid]
    try:
        f = SCN_DIR / (sid + ".json")
        d = json.loads(f.read_text(encoding="utf-8"))
        name = (d.get("ch") or {}).get("name") or d.get("topic") or ""
        items = [{"id": v["id"], "title": v["t"], "chan": name, "fdur": v.get("d") or 0,
                  "sh": v.get("s") or 0} for v in todo]
        old = list(d.get("items") or [])
        # Do charhan hain: (1) YouTube se metadata, (2) thumbnail/OCR/naap. Bar
        # seedha barhta rahe isliye total dono ka jod rakha hai — warna client me
        # bar bharkar dobara khaali hota dikhta, jo jhooth lagta.
        job["total"] = len(items) * 2
        job["current"] = "pehli charhan: YouTube se views/date le raha hoon…"
        t0 = time.perf_counter()
        got = enrich([i["id"] for i in items], job)
        # jo views/dates naap nahi aa sake wo chhupate nahi — scan me likh dete hain,
        # UI chip dikhata hai (views/day unka nahi ginta, baki sab theek ginta hai).
        try:
            vm = sum(1 for i in items if not (got.get(i["id"]) or {}).get("views"))
            if vm:
                fl = job.setdefault("filt", {})
                fl["views_missing"] = vm
                if job.get("api_fill"):
                    fl["api_fill"] = job["api_fill"]
        except Exception:
            pass
        job["t_meta"] = round(time.perf_counter() - t0, 1)
        job["done"] = len(items)
        job["current"] = "doosri charhan: thumbnail/OCR/chehra naap raha hoon…"
        descs = {}
        t1 = time.perf_counter()
        new = []
        # Chhoti khep (batch) me naap karke har khep ke baad file likh dete hain. Is se
        # table zinda rehta hai: jo video naap ho gayi wo foran row me nazar aa jaati
        # hai, poore job ka intezaar nahi karna padta. Job paanch minute ka bhi ho to
        # bekaar nahi lagta — pehla natija bees second me saamne aa jaata hai.
        for i in range(0, len(items), WORKERS2):
            chunk = items[i:i + WORKERS2]
            # measure_items apna done/total khud likhta hai (0..chunk). Is liye ek alag
            # chhota record dekar apna cumulative count khud sambhaal leta hoon — warna
            # bar har khep par 1..8 par wapas chala jaata, jo user ko atakna lagta.
            sub = {"state": "run", "done": 0, "total": len(chunk), "current": ""}
            new += measure_items(chunk, name, got, sub, descs, load_cal())
            job["current"] = sub.get("current") or job.get("current", "")
            job["done"] = len(items) + min(len(items), i + len(chunk))
            d["items"] = old + new
            chan_recalc(d)
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            job["elapsed"] = round(time.perf_counter() - t1, 1)
        job["t_measure"] = round(time.perf_counter() - t1, 1)
        job["sec_per_video"] = round((job["t_meta"] + job["t_measure"]) / max(1, len(items)), 2)
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = repr(e)[:300]
        job["tb"] = traceback.format_exc()[-1200:]


def ch_resolve(q):
    """Naam, @handle, UC-id ya URL — jo diya ho us se channel nikalo.
    Naam par pehla result tabhi lo jab naam mel khaye; warna chand options bhejo taaki
    user khud chune (galat channel par poora analysis bekaar jata hai)."""
    q = (q or "").strip()
    if not q:
        return {"err": "channel ka naam / link / id likho"}
    if re.fullmatch(r"UC[\w\-]{22}", q):
        u = "https://www.youtube.com/channel/" + q
        return {"url": u, "id": q, "how": "channel id se"}
    if q.startswith("@") and len(q) > 2 and re.fullmatch(r"@[\w.\-]+", q):
        u = "https://www.youtube.com/" + q
        return {"url": u, "id": q, "how": "@handle se"}
    if re.match(r"https?://", q):
        m = re.search(r"/(channel/UC[\w\-]{22}|@[\w.\-]+)", q)
        if not m:
            m = re.search(r"(UC[\w\-]{22})", q)
            if m:
                return {"url": "https://www.youtube.com/channel/" + m.group(1), "id": m.group(1),
                        "how": "link se channel id"}
            return {"err": "link me channel nahi pehchaan gaya (@handle ya /channel/UC… chahiye)"}
        seg = m.group(1)
        sid = seg.split("/")[-1]
        return {"url": "https://www.youtube.com/" + seg, "id": sid, "how": "link se"}
    cs = ch_search(q, 8)
    if not cs:
        return {"err": "koi channel nahi mila — poora naam ya @handle likho"}
    # MEL KA NIYAM (dono taraf se): "tech" likha aur "Tech Burner" ka naam pura query
    # contain karta hai — lekin "tech" se poora naam nahi banta, isliye wo auto-pick
    # NAHI hoga (warna galat channel par poora analysis chala jata). Auto-pick tabhi
    # jab query channel ke naam/poore handle se mel khaye AUR naam ka har token query
    # me ho ("easy tech info" -> "Easy Tech Info" sahi hai), aur wo mel akela ho.
    qt = set(t for t in toks(q) if t)
    if not qt:
        return {"need": True, "q": q, "cands": cs[:10], "note": "kuch samajh nahi aaya — chuno"}
    sc = []
    for c in cs:
        nt = set(t for t in toks(c.get("name") or "") if t)
        hn = re.sub(r"[^a-z0-9]", "", (c.get("handle") or "").lower())
        qn = re.sub(r"[^a-z0-9]", "", q.lower())
        if hn and qn and (qn == hn.lstrip("@") or qn == hn):
            sc.append((2.0, c))
            continue
        if not nt:
            continue
        fwd = len(qt & nt) / float(len(qt))      # query ka har token naam me hai?
        rev = len(qt & nt) / float(len(nt))      # naam ka har token query me hai?
        sc.append((min(fwd, rev), c))
    sc.sort(key=lambda x: -x[0])
    bs, best = (sc[0] if sc else (0.0, None))
    second = sc[1][0] if len(sc) > 1 else 0.0
    if best and bs >= 0.6 and (bs > second or bs >= 2.0):
        return {"url": best["url"], "id": best["id"],
                "how": ("poora @handle mel" if bs >= 2.0 else "naam se mel (%d%%)" % round(bs * 100))}
    return {"need": True, "q": q, "cands": cs[:10],
            "note": "naam se pakka mel nahi hua (ya do channels ka mel barabar hai) — "
                    "neeche se khud chun kar channel kholo"}


def sid_of_chan(cid, n):
    return hashlib.md5(("chan|" + str(cid) + "|" + str(n)).encode()).hexdigest()[:16]


def start_chan(q, n=CHN_DEF):
    n = max(5, min(CHN_MAX, int(n or CHN_DEF)))
    r = ch_resolve(q)
    if r.get("need") or r.get("err"):
        return r
    sid = sid_of_chan(r["id"], n)
    f = SCN_DIR / (sid + ".json")
    if f.exists() and (dt.datetime.now() - dt.datetime.fromtimestamp(f.stat().st_mtime)).total_seconds() < TTL:
        return {"cached": True, "id": sid}
    jid = hashlib.md5((str(q) + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": n, "current": "channel dhoondh raha hoon…", "sid": sid}
    threading.Thread(target=_do_chan, args=(jid, r, n, sid), daemon=True).start()
    return {"job": jid, "id": sid, "chan": r}


def _do_chan(jid, r, n, sid):
    job = JOBS[jid]
    try:
        info = ch_info(r["url"])
        if info.get("err"):
            job["state"] = "error"
            job["error"] = info["err"]
            return
        job["current"] = "channel ki listing gin raha hoon…"
        ls = ch_lists(r["url"])
        wk = walk_pack(ls)          # poori listing (id/title/views) scan file me — UI ke liye
        vids = ls["videos"][:n]
        shs = ls["shorts"][:CH_SHORT_MAX]
        job["total"] = len(vids) + len(shs)
        job["current"] = "views/date dekh raha hoon… (%d videos)" % (len(vids) + len(shs))
        items = []
        for v in vids:
            items.append({"id": v["id"], "title": v["title"], "chan": info.get("name") or "",
                          "fdur": v.get("dur") or 0, "sh": 0})
        for v in shs:
            items.append({"id": v["id"], "title": v["title"], "chan": info.get("name") or "",
                          "fdur": v.get("dur") or 0, "sh": 1})
        got = enrich([i["id"] for i in items], job)
        # jo views/dates naap nahi aa sake wo chhupate nahi — scan me likh dete hain,
        # UI chip dikhata hai (views/day unka nahi ginta, baki sab theek ginta hai).
        try:
            vm = sum(1 for i in items if not (got.get(i["id"]) or {}).get("views"))
            if vm:
                fl = job.setdefault("filt", {})
                fl["views_missing"] = vm
                if job.get("api_fill"):
                    fl["api_fill"] = job["api_fill"]
        except Exception:
            pass
        job["done"] = 0
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        descs = {}
        CAL = load_cal()
        job["current"] = "thumbnail/OCR naap raha hoon…"
        items = measure_items(items, info.get("name") or "", got, job, descs, CAL)
        longs = [i for i in items if not i.get("sh")]
        shorts = [i for i in items if i.get("sh")]
        yn = get_yunet()
        CALD = {"n": CAL.get("n"), "r2": CAL.get("r2"), "cv_r2": CAL.get("cv_r2"),
                # `w` bhi scan ke saath likha jaata hai: us din jo wazan chale the sirf
                # wahi us scan ke scores ka matlab hain, aaj badle wazan nahi.
                "w": CAL.get("w"), "src": CAL.get("src")} if CAL else None
        data = {"id": sid, "kind": "channel", "topic": (info.get("name") or r["id"]),   # UI kind se label karega, topic me emoji nahi
                "n": n, "wide": False, "meta": True,
                "ts": dt.datetime.now().isoformat(timespec="seconds"),
                "ocr": bool(find_tesseract()), "pillow": bool(Image), "cv": bool(cv2),
                "eng": {"face": ("YuNet (cv2.FaceDetectorYN)" if yn else
                                 ("Haar cascade (kamzor — models download nahi hua)" if cv2 else None)),
                        "ocr": ("RapidOCR PP-OCRv4" if _RAPID_CLS else
                                ("Tesseract (kamzor — rapidocr_onnxruntime nahi hai)" if find_tesseract() else None)),
                        "sem": _TFIDF is not None, "stat": "mann-whitney (pure python)"},
                "filt": {}, "cal": CALD,
                # ye baat UI me likhni zaroori hai: numbers unhi videos ke hain jo
                # analyze hui (latest N), poore channel par nahi.
                "cov": "channel me se %d videos analyze hui (listing me se sabse nayi), "
                       "baaki sirf gini gayi hain" % (len(longs) + len(shorts)),
                "ch": {"id": info.get("id") or r["id"], "name": info.get("name") or "",
                       "handle": info.get("handle") or "", "url": info.get("url") or r["url"],
                       "subs": info.get("subs") or 0, "desc": info.get("desc") or "",
                       "tags": info.get("tags") or [], "how": r.get("how") or "",
                       "tot_videos": len(ls["videos"]), "tot_shorts": len(ls["shorts"]),
                       "walk_cap": CH_WALK, "terr": ls.get("terr") or "",
                       "analyzed_long": len(longs), "analyzed_short": len(shorts)},
                "walk": wk,
                "items": items, "agg": agg(longs), "deep": deep(longs)}
        # channel ki creation date: About page ki joined date, na mile to sabse
        # purani listing — src label ke saath, dono ka matlab alag hai.
        data["ch"]["joined"] = joined_or_oldest(data["ch"], items)
        data["cst"] = chan_stats(data)
        SCN_DIR.mkdir(parents=True, exist_ok=True)
        (SCN_DIR / (sid + ".json")).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        # history: har channel scan ek snapshot hai. Scan id deterministic hai isliye
        # dobara scan par file overwrite hoti hai — snapshot alag rehta hai, aur wahi
        # doosra point banta hai jis se barhott gin jaati hai.
        try:
            hist_add(data, "scan")
        except Exception:
            pass
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = repr(e)[:300]
        job["tb"] = traceback.format_exc()[-1200:]


def _udate(it):
    s = it.get("upload") or ""
    for f in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(s, f).date()
        except Exception:
            pass
    return None


def niche_of(items, ch=None):
    """Niche do tarfa: (1) YouTube ka ASLI category field jo videos par laga hai, (2)
    titles+tags ke keywords. Dono alag dikhte hain — koi ek "sach" nahi hai."""
    cats = {}
    for i in items:
        c = i.get("cat")
        if c:
            cats[c] = cats.get(c, 0) + 1
    real = max(cats.items(), key=lambda kv: kv[1])[0] if cats else ""
    real_niche = CAT_NICHE.get(real, "")
    txt = []
    for i in items:
        txt.append(i.get("title") or "")
        for t in (i.get("tags") or [])[:12]:
            txt.append(t)
    for t in ((ch or {}).get("tags") or []):
        txt.append(t)
    low = " ".join(txt).lower()
    sc = []
    for name, kws, band in NICHES:
        hits = {}
        for k in kws:
            c = low.count(k)
            if c:
                hits[k] = c
        if hits:
            sc.append({"niche": name, "n": sum(hits.values()), "kw": sorted(hits.items(), key=lambda kv: -kv[1])[:8],
                       "band": band})
    sc.sort(key=lambda x: -x["n"])
    # category YouTube ka ASLI field hai (har video par laga), keyword mera hisaab hai.
    # RPM ka band isliye pehle keywords se liya jaata hai jab woh kaafi mazboot hon
    # (15+ hits), warna channel ke apne category se — aur kaunsa rasta chala wo likha
    # jaata hai, taaki kamai ka andaza "kis baat par" tikta hai ye chhupa na rahe.
    cat_band = None
    for name, kws, band in NICHES:
        if name == real_niche:
            cat_band = band
            break
    strong = bool(sc) and sc[0]["n"] >= 15
    if strong:
        band, band_src = sc[0]["band"], "keywords (%d hits) se niche: %s" % (sc[0]["n"], sc[0]["niche"])
    elif cat_band:
        band, band_src = cat_band, "YouTube ke category field (%s) se niche: %s" % (real, real_niche)
    else:
        band, band_src = (1.5, 4.0), "na keywords se niche bana na category — general public range"
    return {"real_cat": real, "real_n": cats.get(real, 0), "real_niche": real_niche,
            "cat_niches": len(cats), "items_n": len(items),
            "kw_niche": sc[0]["niche"] if sc else "", "kw": (sc[0]["kw"] if sc else []),
            "kw_n": (sc[0]["n"] if sc else 0), "alt": [x["niche"] for x in sc[1:4]],
            "band": band, "band_src": band_src, "all": sc[:5]}


def rpm_of(data, kind="long", ns=None):
    """RPM ka range: pehle user ne apna Studio RPM diya ho (wo ASLI hota hai), warna
    niche ki public range. Return (lo, hi, source).
    `ns` niche_of() ka result hai — chan_stats use khud banata hai aur bhej deta hai,
    warna ye data["cst"] dhoondhta jo us waqt abhi banta hi hai (aur phir hamesha
    general range par gir jata)."""
    ch = data.get("ch") or {}
    cust = _cget("rpm_" + str(ch.get("id") or ""), 10 * 365 * 24 * 3600) or {}
    if cust.get(kind):
        v = float(cust[kind])
        return (round(v * 0.85, 2), round(v * 1.15, 2),
                "aapka apna Studio RPM" + ((" (" + str(cust.get("note")) + ")") if cust.get("note") else ""))
    if ns is None:
        ns = (data.get("cst") or {}).get("niche") or {}
    band = ns.get("band") or (1.5, 4.0)
    if kind == "short":
        return (SHORT_RPM[0], SHORT_RPM[1], "shorts ki public creator-reported range")
    return (band[0], band[1], "longs: " + (ns.get("band_src") or "general public range"))


def earn_block(data, longs, shorts, ns, last30_views=0):
    """Kamai ka poora hisaab ek hi jagah. Range isliye, ek number nahi: YouTube RPM/CPM
    public nahi karta, ye creator-reported ranges hain. User apna Studio RPM de de to
    src me 'aapka apna Studio RPM' likha aa jata hai aur andaza tang ho jata hai."""
    lo1, hi1, s1 = rpm_of(data, "long", ns)
    lo2, hi2, s2 = rpm_of(data, "short", ns)

    def band_sum(xs, lo, hi, src):
        v = sum([(i.get("views") or 0) for i in xs])
        return {"views": v, "lo": round(v / 1000.0 * lo, 2), "hi": round(v / 1000.0 * hi, 2),
                "rpm_lo": lo, "rpm_hi": hi, "src": src, "n": len(xs)}
    return {"earn": {"long": band_sum(longs, lo1, hi1, s1), "short": band_sum(shorts, lo2, hi2, s2),
                     "per_video_lo": round(med([(i.get("views") or 0) / 1000.0 * lo1 for i in longs]), 2) if longs else 0,
                     "per_video_hi": round(med([(i.get("views") or 0) / 1000.0 * hi1 for i in longs]), 2) if longs else 0,
                     "cpm_note": "RPM = aapki jeb me (YouTube ka 45% kaatne ke baad). CPM = advertiser ne "
                                 "1000 views par kitna diya (aapki jeb ka poora nahi). Dono public nahi hote."},
            "last30_earn": {"lo": round(last30_views / 1000.0 * lo1, 2),
                            "hi": round(last30_views / 1000.0 * hi1, 2)}}


def chan_stats(data):
    """Channel ke KPI — sab kuch items se ASLI gin kar. Shorts aur longs alag-alag gine
    jaate hain (ye channel ki listing se aata hai, duration se andaza nahi lagaya).
    Earnings ka section jaan-boojh kar ANDAAZA hai: YouTube RPM/CPM public nahi karta."""
    its = data.get("items") or []
    ch = data.get("ch") or {}
    longs = [i for i in its if not i.get("sh")]
    shorts = [i for i in its if i.get("sh")]
    vs = [v for v in (vpd(i) for i in longs) if v > 0]
    vw = [i.get("views") or 0 for i in longs]
    sv = sorted(vs)
    out = {"n": len(its), "long_n": len(longs), "short_n": len(shorts),
           "tot_videos": ch.get("tot_videos", 0), "tot_shorts": ch.get("tot_shorts", 0),
           "walk_cap": CH_WALK, "subs": ch.get("subs") or 0,
           "views_sum": sum(vw), "views_med": int(med(vw)), "views_max": max(vw) if vw else 0,
           "vpd_med": round(med(vs), 1), "vpd_p90": (sv[int(len(sv) * 0.9)] if len(sv) >= 5 else 0),
           "dur_med": int(med([i.get("dur") or 0 for i in longs])),
           "short_share": round(100.0 * (ch.get("tot_shorts") or 0) /
                                max(1, (ch.get("tot_videos") or 0) + (ch.get("tot_shorts") or 0)), 1)}
    # --- upload ki raftaar (cadence): dates ASLI hain, unhi se gaps ---
    ds = sorted([d for d in (_udate(i) for i in its) if d])
    out["first"] = str(ds[0]) if ds else ""
    out["last"] = str(ds[-1]) if ds else ""
    gaps = [(ds[i + 1] - ds[i]).days for i in range(len(ds) - 1)]
    gaps = [g for g in gaps if g >= 0]
    out["gap_med"] = (int(med(gaps)) if gaps else None)
    out["per_week"] = (round(len(ds) / max(1.0, ((ds[-1] - ds[0]).days + 1) / 7.0), 2) if len(ds) >= 2 else None)
    today = dt.date.today()
    out["days_since"] = (today - ds[-1]).days if ds else None
    out["last30"] = len([d for d in ds if (today - d).days <= 30])
    out["last90"] = len([d for d in ds if (today - d).days <= 90])
    if gaps:
        out["steady"] = round(100.0 * len([g for g in gaps if g <= 21]) / len(gaps), 1)
    # --- abhi ki raftaar: nayi 10 vs us se purani 10 (vpd umr se normalise karta hai) ---
    # IMAANDAAR BAAT: views/day shuru ke dinon me apne aap sabse zyada hota hai (video abhi
    # feed me hota hai), isliye nayi videos ka vpd purani se zyada aana *lazmi* hai — ye
    # channel ki growth ka saboot nahi. Asli growth ka pata tab chalta hai jab EK HI video
    # ke views do alag din record kiye jayein (wo data mere paas nahi, aapke paas Studio me
    # hai). Isliye ye sirf "abhi ki raftaar" hai, neeche ye baat UI me likhi jaati hai.
    def cohort(xs):
        c = [v for v in (vpd(i) for i in xs) if v > 0]
        return {"n": len(c), "med": round(med(c), 1), "views": int(med([i.get("views") or 0 for i in xs]))}
    byage = sorted([i for i in longs if _udate(i)], key=lambda i: _udate(i), reverse=True)
    if len(byage) >= 20:
        a, b = cohort(byage[:10]), cohort(byage[10:20])
        out["new10"] = a
        out["old10"] = b
        out["trend"] = round(a["med"] / b["med"], 2) if b["med"] else None
        out["trend_note"] = ("nayi 10 vs agli purani 10 ka views/day — views/day shuru ke "
                             "dinon me apne aap zyada hota hai, isliye ye upar jaana growth "
                             "ka saboot NAHI hai. Ye sirf abhi ki raftaar dikhaata hai.")
    # --- hit / flop ka nisbat (channel ke apne median se) ---
    m = med(vs) or 0
    if m > 0 and len(vs) >= 8:
        out["hit_n"] = len([v for v in vs if v >= 2 * m])
        out["hit_pct"] = round(100.0 * out["hit_n"] / len(vs), 1)
        out["flop_n"] = len([v for v in vs if v <= 0.3 * m])
        out["flop_pct"] = round(100.0 * out["flop_n"] / len(vs), 1)
    # --- din ke hisaab se kaunsa din acha chalta hai (sirf tab jab n kaafi ho) ---
    NB = ["Somvaar", "Mangal", "Budh", "Jumeraat", "Jumma", "Hafta", "Etvaar"]
    wb = {}
    for i in longs:
        d = _udate(i)
        if not d:
            continue
        v = vpd(i)
        if v > 0:
            wb.setdefault(d.weekday(), []).append(v)
    out["weekdays"] = sorted([{"d": NB[k], "n": len(x), "vpd": round(med(x), 1)} for k, x in wb.items()
                              if len(x) >= 4], key=lambda r: -r["vpd"])
    # --- lambai ke buckets: is channel me kis length ki video zyada chalti hai ---
    LB = [("1–3 min", lambda d: 60 < d <= 180), ("3–10 min", lambda d: 180 < d <= 600),
          ("10–20 min", lambda d: 600 < d <= 1200), ("20–45 min", lambda d: 1200 < d <= 2700),
          ("45 min+", lambda d: d > 2700)]
    rows = []
    for lab, pred in LB:
        sel = [i for i in longs if pred(i.get("dur") or 0)]
        if len(sel) < 3:
            continue
        vv = [v for v in (vpd(i) for i in sel) if v > 0]
        rows.append({"k": lab, "n": len(sel), "views": int(med([i.get("views") or 0 for i in sel])),
                     "vpd": round(med(vv), 1) if vv else 0})
    out["lens"] = sorted(rows, key=lambda r: -r["vpd"])
    # --- sabse zyada chalne wali videos (absolute views) ---
    out["top"] = [{"id": i["id"], "title": (i.get("title") or "")[:90], "views": i.get("views") or 0,
                   "days": i.get("days"), "vpd": round(vpd(i), 1), "url": i.get("url") or "",
                   "sh": i.get("sh", 0)} for i in sorted(its, key=lambda i: -(i.get("views") or 0))[:8]]
    # --- monetization: public nahi, isliye sirf wo sach jo public hai ---
    out["monet"] = {"public": False,
                    "why": "YouTube kisi video ke public data me monetization ka koi field nahi deta "
                           "(poore video JSON me 'monet' ka ek bhi word nahi mila — gina gaya).",
                    "subs_ok": bool((ch.get("subs") or 0) >= 1000),
                    "pyp": "Subscriber 1000+ = Partner Program ke liye zaroori shart me se ek poori hui "
                           "dikhti hai; doosri shart (12 mahine me 4000 ghante views / shorts ke 10M views) "
                           "public data se verify nahi hoti.",
                    "watch_hours_upper": int(sum([(i.get("dur") or 0) * (i.get("views") or 0) / 3600.0
                                                for i in longs])),
                     # ye UPAR ki had hai (har ne poora video dekha ho to kitne ghante bane).
                     # Asli watch time is se kam hota hai, isliye ye sirf itna batata hai ke
                     # 4000-ghante ki shart ke liye gunzaish hai ya nahi — verify nahi hoti.
                     "pyp_hours_note": "4000 ghante wali shart ke liye ye upar ki had hai; asli "
                                       "watch time is se kaafi kam hota hai (log beech me chhod dete hain)."}
    ns = niche_of(its, ch)
    out["niche"] = ns
    # --- kamai ka andaza (range, ek number nahi) ---
    out["last30_views"] = sum([(i.get("views") or 0) for i in its
                               if (_udate(i) and (today - _udate(i)).days <= 30)])
    eb = earn_block(data, longs, shorts, ns, out["last30_views"])
    out["earn"] = eb["earn"]
    out["last30_earn"] = eb["last30_earn"]
    return out


def _medof(its, key):
    xs = [v for v in (i.get(key) for i in its) if isinstance(v, (int, float))]
    return round(med(xs), 1) if xs else None


def _medof2(its, path):
    xs = []
    for i in its:
        d = i
        ok = True
        for p in path:
            d = (d or {}).get(p)
            if d is None:
                ok = False
                break
        if ok and isinstance(d, (int, float)):
            xs.append(d)
    return round(med(xs), 1) if xs else None


# Title aur pattern ki ginati — sab kuch seedha title ke text se ginta hai, koi
# andaza nahi. "Common words" ka matlab sirf itna hai ki audience ka space same
# hai; chori ka davaa nahi. Stopword list chhota aur Hinglish-mix ka hai — isme
# se koi content-shabd ghatak nahi nikalta, sirf jodo-or-sand ka kachra.
_STOPW = set("""the and for you your this that with from about how why what when
which who are was were have has had will would can could should shall may might
must into than then them they their there here over under again more most some
such only own same too via ka ki ke ko me mein mera meri apna apni ye yeh wo voh
is us un par pe se hain hai tha thi ek aur or ya agar kya kaise kab kahan nahi
bina liye wala wale wali kar karo karna karta karti krna hota hote rahe raha
sab tak bas hi to na not new best top video videos vlog vlogs part full hd short
free online karta hain karne liya karte ga ge gi de do le lo mil bana banane
""".split())
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2190-\u21FF]")
_CAPS_OK = ("AI", "TOP", "SEO", "USA", "UK", "IIT", "UPSC", "GS", "PC", "MSC", "PHD", "CEO", "IPL", "MBA", "BBA", "BTECH")


def _ttl_words(titles):
    cnt = {}
    for t in titles:
        seen = set()
        for w in re.findall(r"[a-z0-9\u0900-\u097F]+", (t or "").lower()):
            if len(w) < 3 or w in _STOPW or w.isdigit() or w in seen:
                continue
            seen.add(w)
            cnt[w] = cnt.get(w, 0) + 1
    return cnt


def _ttl_stats(titles):
    ts = [t for t in titles if t]
    if not ts:
        return None
    n = len(ts)
    ch = sorted(len(t) for t in ts)
    wd = sorted(len(t.split()) for t in ts)

    def pct(f):
        return round(100.0 * len([t for t in ts if f(t)]) / n, 1)

    def caps(t):
        return any(len(w) >= 3 and w.isupper() and w.upper() not in _CAPS_OK
                   for w in re.findall(r"[A-Za-z]+", t))
    return {"n": n, "chars": int(med(ch)), "words": round(med(wd), 1),
            "num": pct(lambda t: bool(re.search(r"\d", t))),
            "caps": pct(caps),
            "q": pct(lambda t: "?" in t),
            "pipe": pct(lambda t: any(s in t for s in ("|", "–", "•", ">>", "||", "【"))),
            "brack": pct(lambda t: "[" in t or "(" in t),
            "emoji": pct(lambda t: bool(_EMOJI.search(t)))}


def ch_cmp(sids):
    """Do ya zyada channel scans ki saath-saath tulna. Har line par winner nikaalta hai;
    views/day par Mann-Whitney U se p bhi deta hai (n kaafi ho to) — taaki 'behtar' ka
    matlab sirf bada number na ho."""
    cols = []
    for sid in sids:
        f = SCN_DIR / (sid + ".json")
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        s = d.get("cst") or chan_stats(d)
        # engagement: likes+comments ko views ka percent, sirf longs ka median — summary
        # strip aur scoreboard ko yahi chahiye; ye poori tarah asli gin hai.
        ens = [100.0 * ((i.get("likes") or 0) + (i.get("cmts") or 0)) / i["views"]
               for i in (d.get("items") or []) if not i.get("sh") and (i.get("views") or 0) > 0]
        s["en_med"] = round(med(ens), 2) if ens else None
        lo, hi, src = rpm_of(d, "long")
        cols.append({"id": sid, "kind": d.get("kind") or "topic", "name": (d.get("ch") or {}).get("name") or d.get("topic"),
                     "handle": (d.get("ch") or {}).get("handle") or "", "url": (d.get("ch") or {}).get("url") or "",
                     "cid": (d.get("ch") or {}).get("id") or "",
                     "subs": s.get("subs") or 0, "st": s, "rpm": (lo, hi, src),
                     "its": [i for i in (d.get("items") or []) if not i.get("sh")],
                     "topic": d.get("topic") or "", "ts": d.get("ts") or "",
                     "jn": (d.get("ch") or {}).get("joined"), "last": s.get("last")})
    if len(cols) < 2:
        return {"err": "tulna ke liye do channel scans chahiye"}
    def val(c, k):
        s = c["st"]
        if k == "subs":
            return c["subs"]
        if k == "earn30":
            return (s.get("last30_earn") or {}).get("hi", 0)
        return s.get(k)
    rows = []
    for k, lab, fmtv, hibest in [
        ("subs", "Subscriber", lambda v: "{:,}".format(int(v or 0)), True),
        ("tot_videos", "Kul videos (gine gaye)", lambda v: str(int(v or 0)), True),
        ("tot_shorts", "Shorts (gine gaye)", lambda v: str(int(v or 0)), None),
        ("short_share", "Shorts ka hissa %", lambda v: str(v or 0) + "%", None),
        ("views_med", "Median views", lambda v: "{:,}".format(int(v or 0)), True),
        ("vpd_med", "Median views/day", lambda v: "{:,.1f}".format(float(v or 0)), True),
        ("en_med", "Median engagement % (likes+comments ÷ views)", lambda v: "{:.2f}%".format(float(v or 0)), True),
        ("hit_pct", "Hit rate % (median se 2x+)", lambda v: str(v or 0) + "%", True),
        ("flop_pct", "Flop rate % (median se 30% se kam)", lambda v: str(v or 0) + "%", False),
        ("per_week", "Uploads / hafta", lambda v: str(v or 0), None),
        ("days_since", "Aakhri upload kitne din pehle", lambda v: str(v if v is not None else "-"), False),
        ("last30", "Pichhle 30 din me uploads", lambda v: str(v or 0), True),
        # trend tab hi hai jab 20+ longs upload-date ke saath mili ho — warna ye line
        # khamosh rehti hai (bataana behtar hai ke ginna possible nahi tha).
        ("trend", "Nayi vs purani videos (views/day) — 20+ longs chahiye", lambda v: (str(v) + "x") if v else "nahin gin sakta", True),
        ("views_sum", "Padhi gayi videos ke kul views", lambda v: "{:,}".format(int(v or 0)), True),
        ("last30_views", "Pichhle 30 din ki videos ke views", lambda v: "{:,}".format(int(v or 0)), True),
        ("earn30", "Kamai ka andaza 30 din (USD, oopar wali had)", lambda v: ("${:,.0f}".format(float(v or 0))), True),
    ]:
        vals = [val(c, k) for c in cols]
        nums = [v for v in vals if isinstance(v, (int, float))]
        best = None
        if hibest is not None and len(nums) >= 2 and len(set(nums)) > 1:
            best = int(max(range(len(vals)), key=lambda i: (vals[i] if isinstance(vals[i], (int, float)) else -1e18))) \
                if hibest else int(min(range(len(vals)), key=lambda i: (vals[i] if isinstance(vals[i], (int, float)) else 1e18)))
        disp = [fmtv(v) for v in vals]
        # 400 listing cap: jitna gina ja sakta tha utna hi gin kar aaya hai, isliye
        # "400" ka matlab "kam se kam 400" hai. Ye + nahi lagaya to number jhooth bolega.
        if k in ("tot_videos", "tot_shorts"):
            for i, c in enumerate(cols):
                if (vals[i] or 0) >= (c["st"].get("walk_cap") or CH_WALK):
                    disp[i] = disp[i] + "+"
        rows.append({"k": k, "lab": lab, "vals": disp, "raw": vals, "best": best})
    # listing ki safai aur thumbnail ki banawas bhi to compare karni hai
    for k, lab, f in deep_cmp_rows(cols):
        rows.append({"k": k, "lab": lab, "vals": [f(c) for c in cols], "raw": [], "best": None})
    sig = []
    a = [v for v in (vpd(i) for i in cols[0]["its"]) if v > 0]
    for c in cols[1:]:
        b = [v for v in (vpd(i) for i in c["its"]) if v > 0]
        p = _mwu(a, b) if len(a) >= 6 and len(b) >= 6 else None
        sig.append({"b": c["name"], "a_med": round(med(a), 1), "b_med": round(med(b), 1), "n_a": len(a),
                    "n_b": len(b), "p": p, "ratio": round(med(a) / med(b), 2) if med(b) else None,
                    "note": "views/day ki poori distribution par Mann-Whitney U (dono ke samples alag hain)"})
    def _charts(c):
        """Charts ka maal: har video ka views/day (dot-strip), mahine ke uploads
        (rhythm), style ke median (radar), history snapshots (subs line), aur
        Timing & pattern tab ka saamaan: hafte ka din (saari dates se), ghari ka
        naqsha (sirf un long videos se jin ka exact waqt mila), length ke buckets,
        title style. Jo cheez gin nahi saki wo None/[] hi rahegi — client us card
        par sach likhega."""
        its = c["its"]
        vd = [round(v, 1) for v in (vpd(i) for i in its) if v > 0]
        mb = {}
        dow = [0] * 7
        dn = 0
        for i in its:
            dd = _udate(i)
            if dd:
                k = dd.strftime("%Y-%m")
                mb[k] = mb.get(k, 0) + 1
                dow[dd.weekday()] += 1
                dn += 1
        up = [{"m": k, "n": mb[k]} for k in sorted(mb)[-24:]]
        # Ghari ka naqsha sirf long videos par (chhote ke upload din ka pattern
        # beech me aa kar "best time" ka jawab bigaad dete hain) — aur sirf un
        # par jinke paas exact timestamp hai; tm_n batata hai kitne gin gaye.
        longs = [i for i in its if not i.get("sh")]
        tm = [0] * 168
        tn = 0
        for i in longs:
            pt = i.get("pubts")
            if not pt:
                continue
            try:
                dd = dt.datetime.fromtimestamp(int(pt))
            except Exception:
                continue
            tm[dd.weekday() * 24 + dd.hour] += 1
            tn += 1
        dbuck = [0] * 6
        durs = []
        for i in longs:
            du = i.get("dur") or 0
            if du > 0:
                mnt = du / 60.0
                durs.append(mnt)
                dbuck[0 if mnt < 2 else 1 if mnt < 5 else 2 if mnt < 10 else 3 if mnt < 15 else 4 if mnt < 20 else 5] += 1
        sty = {"words": _medof2(its, ["ts", "n"]), "h320": _medof2(its, ["ts", "h320"]),
               "cr": _medof2(its, ["ts", "cr_med"]),
               "face": round(100.0 * len([i for i in its if (i.get("faces") or [])]) / max(1, len(its)), 1),
               "tags": medofn(c, "tags"), "score": _medof(its, "score"),
               "chp": round(100.0 * len([i for i in its if i.get("nch")]) / max(1, len(its)), 1)}
        hist = None
        if c.get("cid"):
            try:
                hist_ensure(c["cid"])
                sn = sorted(_hist_load(c["cid"])["snaps"], key=lambda x: str(x.get("ts") or ""))
                pts = [{"t": s.get("ts"), "subs": s.get("subs"), "tv": s.get("tv"), "tsh": s.get("tsh")}
                       for s in sn if isinstance(s.get("subs"), (int, float))]
                if len(pts) >= 2:
                    hist = pts
            except Exception:
                hist = None
        return {"vd": vd, "up": up, "sty": sty, "hist": hist, "dow": dow, "dow_n": dn,
                "tm": tm, "tm_n": tn, "long_n": len(longs), "dur": dbuck,
                "dur_med": round(med(durs), 1) if durs else None,
                "ttl": _ttl_stats([i.get("title") or "" for i in its]),
                "en_med": c["st"].get("en_med"), "vpd_med": c["st"].get("vpd_med")}
    # "Common title words": kaunsa shabd kis channel ke kitne ALAG titles me baitha
    # hai. Kam se kam do channels me 2-2 titles — tabhi common gin'ta hai. Ye sirf
    # yahi batata hai ki dono ek hi space me khel rahe hain; chori ka davaa nahi.
    wcnt = [_ttl_words([i.get("title") or "" for i in c["its"]]) for c in cols]
    common = []
    cand = set()
    for wc in wcnt:
        cand |= set(wc)
    for w in cand:
        cc = [wc.get(w, 0) for wc in wcnt]
        if sum(1 for x in cc if x >= 2) >= 2:
            common.append({"w": w, "c": cc})
    common.sort(key=lambda x: (-min(x["c"]), -sum(x["c"]), x["w"]))
    common = common[:14]

    return {"cols": [{"id": c["id"], "name": c["name"], "handle": c["handle"], "url": c["url"],
                      "subs": c["subs"], "topic": c["topic"], "ts": c["ts"], "rpm": c["rpm"],
                      "kind": c["kind"],
                      "n": c["st"].get("n"), "long_n": c["st"].get("long_n"),
                      "short_n": c["st"].get("short_n"), "tot_videos": c["st"].get("tot_videos"),
                      "tot_shorts": c["st"].get("tot_shorts"),
                      "joined": c.get("jn"), "last": c.get("last")} for c in cols],
            "rows": rows, "sig": sig, "charts": [_charts(c) for c in cols], "common": common,
            "note": "Winner ki line sirf numbers ki hai; significance column hi batata hai ke farq "
                    "itna bada hai ke ittefaq na ho. Views/day = views / umr (din), taaki purani aur "
                    "nayi videos ek jaisi toli ja sakein."}


def deep_cmp_rows(cols):
    """Listing ki safai + thumbnail ki banawas ke median har channel ka — topic scan wale
    bench se hi, dobara formula nahi likha."""
    out = []

    def medof(c, key):
        xs = []
        for i in c["its"]:
            v = i.get(key)
            if isinstance(v, (int, float)):
                xs.append(v)
        return round(med(xs), 1) if xs else None

    def medof2(c, path):
        xs = []
        for i in c["its"]:
            d = i
            ok = True
            for p in path:
                d = (d or {}).get(p)
                if d is None:
                    ok = False
                    break
            if ok and isinstance(d, (int, float)):
                xs.append(d)
        return round(med(xs), 1) if xs else None

    out.append(("tags_n", "Median asli tags (listing)", lambda c: str(medofn(c, "tags") or 0)))
    out.append(("dlen", "Median description chars", lambda c: str(medof(c, "dlen") or 0)))
    out.append(("ls", "Median listing score (0–100)", lambda c: str(medof(c, "ls") or 0)))
    out.append(("nch", "Chapters wali videos %", lambda c: str(round(100.0 * len([i for i in c["its"] if i.get("nch")]) / max(1, len(c["its"])), 1)) + "%"))
    out.append(("words", "Thumbnail par median shabd", lambda c: str(medof2(c, ["ts", "n"]) or 0)))
    out.append(("h320", "Median bada text @320px", lambda c: str(medof2(c, ["ts", "h320"]) or 0)))
    out.append(("cr", "Median text contrast", lambda c: str(medof2(c, ["ts", "cr_med"]) or 0)))
    out.append(("face", "Chehra wali videos %", lambda c: str(round(100.0 * len([i for i in c["its"] if (i.get("faces") or [])]) / max(1, len(c["its"])), 1)) + "%"))
    out.append(("score", "Median thumbnail score", lambda c: str(medof(c, "score") or 0)))
    return out


def medofn(c, key):
    xs = [len(i.get(key) or []) for i in c["its"] if isinstance(i.get(key), list)]
    return round(med(xs), 1) if xs else None


def refresh_earn(cid):
    """User ne apna RPM badal diya to us channel ke purane scans ka kamai ka hisaab dobara
    laga do — warna screen par purana andaza likha reh jata (scan file to jam chuki hai)."""
    n = 0
    if not cid or not SCN_DIR.exists():
        return 0
    for f in SCN_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (d.get("ch") or {}).get("id") != cid or not d.get("cst"):
            continue
        longs = [i for i in (d.get("items") or []) if not i.get("sh")]
        shorts = [i for i in (d.get("items") or []) if i.get("sh")]
        ns = (d["cst"].get("niche") or {})
        eb = earn_block(d, longs, shorts, ns, d["cst"].get("last30_views") or 0)
        d["cst"]["earn"] = eb["earn"]
        d["cst"]["last30_earn"] = eb["last30_earn"]
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        n += 1
    return n


def set_rpm(cid, long_rpm=None, short_rpm=None, note=""):
    """User apna YouTube Studio ka RPM daal de to kamai ka andaza ASLI ban jata hai.
    Sirf wahi value store hoti hai jo user ne di — chhup kar kuch nahi bharta."""
    key = "rpm_" + str(cid)
    d = _cget(key, 10 * 365 * 24 * 3600) or {}
    if long_rpm is not None:
        d["long"] = float(long_rpm)
    if short_rpm is not None:
        d["short"] = float(short_rpm)
    if note:
        d["note"] = str(note)[:80]
    d["got"] = dt.datetime.now().isoformat(timespec="seconds")
    _cput(key, d)
    return d


_SCNCACHE = {}             # file ka (mtime,size) -> banaya hua summary. Har boot par
                           # 30MB+ scan JSON dobara parse karne ki zaroorat nahi — file
                           # badli hi nahi to purana summary kaafi hai (age har baar
                           # dobara gin liya jaata hai, sasta hai).


def list_scans():
    out = []
    if SCN_DIR.exists():
        for f in SCN_DIR.glob("*.json"):
            try:
                st = f.stat()
                hit = _SCNCACHE.get(f.name)
                if hit and hit[0] == (st.st_mtime, st.st_size):
                    out.append(dict(hit[1], age=int((dt.datetime.now() - dt.datetime.fromtimestamp(st.st_mtime)).total_seconds())))
                    continue
                d = json.loads(f.read_text(encoding="utf-8"))
                entry = {"id": d["id"], "topic": d["topic"], "n": d["n"], "wide": bool(d.get("wide")),
                            # kept = filters ke baad bachi hui ginti. UI ko yahi dikhana chahiye,
                            # maangi hui nahi — warna ek hi screen par do alag "videos" number aa jate hain.
                            "kept": len(d.get("items") or []),
                            # kind/ch: channel scan ko topic scan se alag dikhane ke liye (naam,
                            # @handle, subscriber) — ye YouTube ka diya hua data hai.
                            "kind": d.get("kind") or "topic",
                            "ch": ({"id": (d.get("ch") or {}).get("id") or "",
                                    "name": (d.get("ch") or {}).get("name") or "",
                                    "handle": (d.get("ch") or {}).get("handle") or "",
                                    "subs": (d.get("ch") or {}).get("subs") or 0,
                                    "tot_videos": (d.get("ch") or {}).get("tot_videos") or 0,
                                    "tot_shorts": (d.get("ch") or {}).get("tot_shorts") or 0}
                                   if d.get("kind") == "channel" else None),
                            "meta": bool(d.get("meta")), "ts": d["ts"]}
                entry["age"] = int((dt.datetime.now() - dt.datetime.fromtimestamp(st.st_mtime)).total_seconds())
                _SCNCACHE[f.name] = (st.st_mtime, st.st_size, {k: v for k, v in entry.items() if k != "age"})
                out.append(entry)
            except Exception:
                pass
    out.sort(key=lambda x: x["age"])          # naya scan sabse upar
    return out


HIST_MAX = 60               # ek channel ke itne snapshot (usse purane hat jate hain)


def _hist_path(cid):
    return HIST_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", str(cid))[:80] + ".json")


def _hist_load(cid):
    f = _hist_path(cid)
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d.get("snaps"), list):
                # purani history files me `meas` field tha hi nahi; src se pata chal
                # jaata hai ki us snapshot ne kya naapa tha. Migration sirf tab likhti
                # hai jab kuch badle.
                chg = False
                for x in d["snaps"]:
                    if "meas" not in x:
                        x["meas"] = {"manual": [], "refresh": ["views"]}.get(
                            str(x.get("src") or ""))
                        chg = True
                if chg:
                    try:
                        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    except Exception:
                        pass
                return d
        except Exception:
            pass
    return {"cid": str(cid), "name": "", "handle": "", "snaps": []}


def _iso(s):
    """ISO string -> datetime. Na samajh aaye to None (kabhi bhi date galat interpret
    karke farak ginna, na ginne se bura hai)."""
    try:
        return dt.datetime.fromisoformat(str(s))
    except Exception:
        return None


def _gap_days(a, b):
    x, y = _iso(a), _iso(b)
    if not x or not y:
        return None
    return round((y - x).total_seconds() / 86400.0, 2)


def _hist_snap(d, src, ts=None):
    """Scan file se snapshot ka shape. Ye sirf wahi hai jo us waqt file me tha:
    channel ke public counts + sirf unhi videos ke numbers jo us waqt NAAPi gayi thin
    (listing me baaki sirf gini gayi thin — unka koi naap nahi, isliye wo growth me
    nahi aate). `vm` = wo waqt jab per-video numbers actually naape gaye the (ts2 =
    aakhri measurement, warna scan ka waqt). Do snapshots ka `vm` barabar ho to
    per-video numbers dobara naape hi nahi gaye — farak 0 nahi, "dobara napa gaya
    nahi" likha jaayega."""
    ch = d.get("ch") or {}
    its = d.get("items") or []
    vids = {}
    for it in its:
        vid = it.get("id")
        if not vid:
            continue
        vids[vid] = {"v": it.get("views"), "l": it.get("likes"), "c": it.get("cmts"),
                     "d": it.get("days"), "s": 1 if it.get("sh") else 0,
                     "t": (it.get("title") or "")[:90]}
    tot = lambda k: sum((v.get(k) or 0) for v in vids.values() if v.get(k) is not None)
    vm = str(d.get("ts2") or d.get("ts") or "")
    ups = [i.get("upload") for i in its if i.get("upload")]
    # `meas` = is snapshot me kaunsa per-video number ASLI me dobara naapa gaya. Iske
    # bina views-refresh ke baad likes/comments ka farak 0 dikhega — jo jhoot hai,
    # kyunki wo dobara padhe hi nahi gaye the. scan/backfill me poora scan naap raha
    # tha (meas None), manual me sirf public counts ([]), refresh me sirf views.
    meas = {"manual": [], "refresh": ["views"]}.get(str(src))
    return {"ts": str(ts or vm), "vm": vm, "sid": d.get("id") or "", "src": src,
            "meas": meas,
            "subs": int(ch.get("subs") or 0), "tv": int(ch.get("tot_videos") or 0),
            "tsh": int(ch.get("tot_shorts") or 0), "nm": len(vids),
            "views": tot("v"), "likes": tot("l"), "cmts": tot("c"),
            "first": min(ups) if ups else "", "last": max(ups) if ups else "",
            "vids": vids}


def hist_add(d, src="scan", ts=None):
    """Ek scan file ka snapshot us channel ki history me jod do. Same scan id + same
    waqt dobara na judne paye (isliye (sid, ts) se dedupe). Channel scan ka scan id
    deterministic hota hai (cid+n se banta hai) — isliye dobara scan karne par file
    overwrite hoti hai, magar history me dono readings alag-alag points ban jate hain.
    Yehi history ka asli kaam hai: waqt ke saath barhna."""
    ch = d.get("ch") or {}
    cid = ch.get("id") or ""
    if d.get("kind") != "channel" or not cid:
        return 0
    try:
        HIST_DIR.mkdir(parents=True, exist_ok=True)
        h = _hist_load(cid)
        h["name"] = ch.get("name") or h.get("name") or ""
        h["handle"] = ch.get("handle") or h.get("handle") or ""
        sn = [x for x in h["snaps"] if (x.get("sid"), x.get("ts")) !=
              (d.get("id") or "", str(ts or d.get("ts2") or d.get("ts") or ""))]
        sn.append(_hist_snap(d, src, ts))
        sn.sort(key=lambda x: str(x.get("ts") or ""))
        h["snaps"] = sn[-HIST_MAX:]
        h["updated"] = dt.datetime.now().isoformat(timespec="seconds")
        _hist_path(cid).write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
        return 1
    except Exception:
        return 0


def hist_ensure(cid):
    """Jo channel scans file me pehle se pare hain un se snapshot banao (ek hi baar).
    Back-fill ka matlab: har snapshot us scan ke US waqt ka data hai jab wo scan hua
    tha — aaj ka nahi. Isliye pehla point asli hai, andaza nahi."""
    n = 0
    if not SCN_DIR.exists():
        return n
    for f in SCN_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("kind") != "channel" or (d.get("ch") or {}).get("id") != cid:
            continue
        h = _hist_load(cid)
        key = (d.get("id") or "", str(d.get("ts2") or d.get("ts") or ""))
        if any((x.get("sid"), x.get("ts")) == key for x in h["snaps"]):
            continue
        if hist_add(d, "backfill"):
            n += 1
    return n


def hist_take(sid):
    """Naya snapshot abhi ke liye: channel ke public counts (subscriber, kitni
    uploads) YouTube se dobara padho. Per-video numbers usi scan file se aate hain jo
    pehle se naapi gayi hai — wo numbers NAPE nahi gaye, isliye `vm` wahi purana rahega
    aur UI saaf likhega "per-video numbers dobara nape gaye". Listing 24 ghante tak
    cache se chalti hai (CH_TTL); cache purani ho to listing dobara padhni padti hai
    (~1 minute)."""
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("kind") != "channel":
        return {"err": "ye channel scan nahi hai — history sirf channel scans ke liye hai"}
    cid = (d.get("ch") or {}).get("id") or ""
    url = ((d.get("ch") or {}).get("url") or "").strip()
    if not cid or not url:
        return {"err": "is scan me channel ki id/URL nahi hai"}
    ch = d.setdefault("ch", {})
    t0 = time.perf_counter()
    got = {"subs": False, "list": "", "terr": ""}
    try:
        info = ch_info(url)
        if info.get("subs"):
            ch["subs"] = int(info["subs"])
            got["subs"] = True
    except Exception:
        pass
    key = "walk_" + hashlib.md5(url.encode()).hexdigest()[:16]
    wk = _cget(key, CH_TTL)
    if wk:
        got["list"] = "cache"
    else:
        try:
            wk = walk_pack(ch_lists(url))
            if not (wk["v"] or wk["s"]):
                wk = None
                got["terr"] = "channel ki listing dobara nahi mil saki"
            else:
                got["list"] = "fresh"
                _cput(key, wk)
        except Exception as e:
            wk = None
            got["terr"] = "listing ka fetch fail: " + repr(e)[:80]
    if wk:
        d["walk"] = wk
        ch["tot_videos"], ch["tot_shorts"] = len(wk["v"]), len(wk["s"])
        ch["walk_cap"] = CH_WALK
    now = dt.datetime.now().isoformat(timespec="seconds")
    try:
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    hist_ensure(cid)
    hist_add(d, "manual", now)
    h = _hist_load(cid)
    return {"ok": True, "cid": cid, "n": len(h["snaps"]), "got": got,
            "elapsed": round(time.perf_counter() - t0, 1)}


def _pair(p, s, topn=15):
    """Do snapshots ke beech ka sirf wohi farak jo ginne layak hai: jo video DONO me
    naapi gayi unki views/likes/comments ka farak (matched set). Jo video sirf naye
    snapshot me hai wo alag ginna jaata hai — uska purana value hi nahi, isliye
    'barhott' usme ginna jhoot hoga. Naya upload ka pata upload-date se chalta hai:
    video ki umar (days) snapshot ke beech ke waqt se kam hai to wo upload us
    interval me hua."""
    pv, sv = p.get("vids") or {}, s.get("vids") or {}
    both = [k for k in sv if k in pv]
    only_new = [k for k in sv if k not in pv]
    only_old = [k for k in pv if k not in sv]
    gap = _gap_days(p.get("ts"), s.get("ts"))
    # `meas` = naye snapshot me kaunsa per-video number naya naapa gaya tha (None =
    # poora scan). Jo metric dobara napa hi nahi gaya, uska farak 0 nahi hota — wo
    # None jaata hai aur UI use "not re-measured" kehta hai. 0 likhna jhoot hota:
    # aisa lagega ki likes barh hi nahi rahe, jabki unhe padha hi nahi gaya.
    meas = s.get("meas")
    ok_v = meas is None or "views" in meas
    ok_l = meas is None or "likes" in meas
    ok_c = meas is None or "cmts" in meas
    dv = dl = dc = 0
    n_match = 0
    gain = []
    for k in both:
        a, b = pv[k], sv[k]
        if a.get("v") is None or b.get("v") is None:
            continue
        n_match += 1
        g = ((b["v"] or 0) - (a["v"] or 0)) if ok_v else None
        if g is not None:
            dv += g
        e = {"id": k, "t": (b.get("t") or a.get("t") or "")[:80], "s": b.get("s") or 0,
             "v0": a.get("v"), "v1": b.get("v"), "dv": g, "d": b.get("d"), "gap": gap,
             "r": (round(b["v"] / a["v"], 3) if (ok_v and a.get("v")) else None)}
        if ok_l and a.get("l") is not None and b.get("l") is not None:
            e["dl"] = (b["l"] or 0) - (a["l"] or 0)
            dl += e["dl"]
        if ok_c and a.get("c") is not None and b.get("c") is not None:
            e["dc"] = (b["c"] or 0) - (a["c"] or 0)
            dc += e["dc"]
        gain.append(e)
    gain.sort(key=lambda x: -(x["dv"] or 0))
    ups = []
    for k in only_new:
        b = sv[k]
        nwup = bool(b.get("d") is not None and gap is not None and b["d"] < gap - 0.5)
        ups.append({"id": k, "t": (b.get("t") or "")[:80], "s": b.get("s") or 0,
                    "v": b.get("v"), "d": b.get("d"), "up": nwup})
    ups.sort(key=lambda x: -(x.get("v") or 0))
    return {"a": p.get("ts"), "b": s.get("ts"), "gap": gap, "vm_same": (p.get("vm") == s.get("vm")),
            "meas": meas, "n_match": n_match,
            "dv": (dv if ok_v else None), "dl": (dl if ok_l else None),
            "dc": (dc if ok_c else None),
            "top": gain[:topn],
            "dn": [x for x in reversed(gain) if (x["dv"] or 0) < 0][:5],
            "new_n": len(only_new), "new_up_n": sum(1 for x in ups if x["up"]),
            "new": ups[:topn], "gone_n": len(only_old)}


HIST_REF_MAX = 120          # ek refresh me max itni videos ke views dobara


def hist_refresh(sid, k=25):
    """Views ka dobara naap: is scan me se sabse nayi K videos ke aaj ke views YouTube
    se dobara lo — wahi engine jo channel scan chalata hai (`enrich` -> `_grab`), koi
    naya formula nahi. Purane values khojte nahi: pichla snapshot history me already
    mehfooz hai, aur is call ke baad ek naya snapshot judta hai, is liye do snapshots
    ke beech ka per-video farak ASLI naap hai. Har item par `vts` likha jaata hai ki
    wo number kis waqt padha gaya tha — UI wahin se batata hai kaunsa number kitna
    purana hai. `chan_recalc` ke baad scan file ka har hissa (outliers, percentiles,
    medians) inhi nayi values par chalta hai."""
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("kind") != "channel":
        return {"err": "ye channel scan nahi hai"}
    cid = (d.get("ch") or {}).get("id") or ""
    if not cid:
        return {"err": "is scan me channel ki id nahi hai"}
    items = d.get("items") or []
    if not items:
        return {"err": "is scan me koi naapi gayi video nahi hai"}
    k = max(0, min(HIST_REF_MAX, int(k or 0)))
    # sabse nayi uploads pehle (upload date ke hisaab se); jinki date nahi wo aakhir me
    order = sorted(items, key=lambda i: (0 if i.get("upload") else 1,
                                         -(int(i.get("pubts") or 0)),
                                         str(i.get("upload") or "")))
    todo = order[:k] if k else order
    ids = [i["id"] for i in todo if i.get("id")]
    if not ids:
        return {"err": "kisi video ki id nahi mili"}
    job = {"state": "run", "done": 0, "total": len(ids), "current": "views dobara padh raha hoon…"}
    t0 = time.perf_counter()
    try:
        got = enrich(ids, job)
    except Exception as e:
        return {"err": "views ka fetch fail: " + repr(e)[:120]}
    now = dt.datetime.now().isoformat(timespec="seconds")
    upd = 0
    byid = {i.get("id"): i for i in items if i.get("id")}
    for vid, g in (got or {}).items():
        it = byid.get(vid)
        if not it or g.get("views") is None:
            continue
        it["views"] = g["views"]
        if g.get("upload"):
            it["upload"] = g["upload"]
        if g.get("pt") and not it.get("pubts"):
            # views refresh ke saath waqt bhi mil jata hai — free (API ke ek hi
            # jawab se). pubts epoch hai, ghari ka pattern usi se gin'ta hai.
            it["pt"] = g["pt"]
            try:
                it["pubts"] = int(dt.datetime.strptime(g["pt"][:19], "%Y-%m-%dT%H:%M:%S")
                                  .replace(tzinfo=dt.timezone.utc).timestamp())
            except Exception:
                pass
        if g.get("days") is not None:
            it["days"] = g["days"]
        if g.get("dur"):
            it["dur"] = g["dur"]
        it["vts"] = now
        upd += 1
    if not upd:
        return {"err": "kisi bhi video ke views nahi mil sake — thori der baad dobara try karo"}
    chan_recalc(d)
    try:
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    hist_ensure(cid)
    hist_add(d, "refresh", now)
    h = hist_get(sid)
    return {"ok": True, "asked": len(ids), "updated": upd,
            "elapsed": round(time.perf_counter() - t0, 1), "hist": h}


def hist_get(sid):
    """History ka poora view: har snapshot + usse pichle snapshot ka farak. Per-video
    detail sirf aakhri 3 jodiyon ke liye bheji jaati hai (baaki sirf ginati) — warna
    response me sirf ginati hoti hai aur client ke paas poora data chala jaata hai."""
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return {"err": "wo scan file nahi mili"}
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("kind") != "channel":
        return {"err": "ye channel scan nahi hai"}
    cid = (d.get("ch") or {}).get("id") or ""
    if not cid:
        return {"err": "is scan me channel ki id nahi hai"}
    hist_ensure(cid)
    h = _hist_load(cid)
    sn = sorted(h["snaps"], key=lambda x: str(x.get("ts") or ""))
    rows = []
    for i, s in enumerate(sn):
        r = {"ts": s.get("ts"), "vm": s.get("vm"), "src": s.get("src"), "sid": s.get("sid"),
             "subs": s.get("subs"), "tv": s.get("tv"), "tsh": s.get("tsh"), "nm": s.get("nm"),
             "views": s.get("views"), "likes": s.get("likes"), "cmts": s.get("cmts"),
             "first": s.get("first"), "last": s.get("last")}
        if i:
            p = sn[i - 1]
            r["gap"] = _gap_days(p.get("ts"), s.get("ts"))
            r["vm_same"] = p.get("vm") == s.get("vm")
            r["d_subs"] = (s.get("subs") or 0) - (p.get("subs") or 0)
            r["d_up"] = ((s.get("tv") or 0) + (s.get("tsh") or 0)) - \
                        ((p.get("tv") or 0) + (p.get("tsh") or 0))
            m = _pair(p, s, topn=0)
            r["n_match"] = m["n_match"]
            if not r["vm_same"]:
                r["d_views"] = m["dv"]
                r["d_likes"] = m["dl"]
                r["d_cmts"] = m["dc"]
            r["new_n"] = m["new_n"]
            r["gone_n"] = m["gone_n"]
        rows.append(r)
    pairs = []
    for i in range(max(1, len(sn) - 3), len(sn)):
        pairs.append(_pair(sn[i - 1], sn[i]))
    span = _gap_days(sn[0].get("ts"), sn[-1].get("ts")) if len(sn) > 1 else None
    return {"cid": cid, "name": h.get("name") or (d.get("ch") or {}).get("name") or "",
            "handle": h.get("handle") or (d.get("ch") or {}).get("handle") or "",
            "scan": sid, "n": len(sn), "span": span, "snaps": rows, "pairs": pairs,
            "updated": h.get("updated") or ""}


def _backfill_views(d):
    """Purane scan jinme `vr`/`sd` ke bina likhe gaye the — wo cheezein unme bhar do.
    Ye koi nayi measurement nahi: verdicts aur score_detail pehle se scan file me mojud
    an/ts/faces/comp par chalte hain. Isliye purana scan bhi bina dobara scan ke poora
    dikhta hai. Jo scan us waqt jo wazan use kar raha tha (`cal.w` record hai) wahi
    dobara use hota hai — aaj ke wazon se purana score dobara ginna jhoot hoga; record
    na mile to aaj ka calibration try hota hai aur farak UI ko bata diya jaata hai."""
    n = 0
    cal = d.get("cal")
    # record me `w` ho to wahi wazan (exact); na ho to aaj ka calibration, aur farak
    # hone par UI ko bata diya jaata hai (sd.drift).
    cal = cal if (cal or {}).get("w") else None
    for it in (d.get("items") or []):
        an = it.get("an")
        if not an or an.get("err") or it.get("vr"):
            continue
        try:
            ts = it.get("ts") or {}
            cp = it.get("comp") or comp_of(ts, it.get("faces") or [])
            it["vr"] = verdicts(an, ts, it.get("faces"), cp)
            sd = score_detail(an, ts, it.get("faces"), cal, cp)
            if it.get("score") is not None and sd.get("score") != it.get("score"):
                # imandari: batado ki ye breakdown aaj ke wazon se hai, us waqt ke nahi
                sd["drift"] = it.get("score")
            it["sd"] = sd
            n += 1
        except Exception:
            continue
    return n


def load_scan(sid):
    if not re.fullmatch(r"[0-9a-f]{16}", sid or ""):
        return None
    f = SCN_DIR / (sid + ".json")
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    # purane scan me engine/sample/wazan ka record nahi hua tha — chup-chaap 0 dikhana
    # jhoot hoga, isliye UI ko bataya jaata hai ki ye record us waqt hota hi nahi tha
    d["legacy"] = not (d.get("eng") or d.get("filt") or d.get("cal"))
    # jo scan is daur se pehle likhe gaye unme vr/sd nahi honge — bina dobara scan ke
    # bhar do, warna purane scan par naya "kya theek hai / score kaise bana" khali aayega
    d["backfilled"] = _backfill_views(d)
    # OCR ka kachra (adhoore nishan, akela "|") user ko kabhi nahi dikhna chahiye —
    # jo scan is safai se pehle bane the unka text yahi saaf kar ke bheja jaata hai,
    # file chhedi nahi jaati. Nayi scans text_stats me hi saaf banti hain.
    for it in d.get("items") or []:
        t = (it.get("ts") or {}).get("text")
        if t:
            it["ts"]["text"] = ocr_clean(t)
    return d


# ---------------- meri thumbnail ----------------

VID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([0-9A-Za-z_-]{11})")


def xplat_get(url):
    """TikTok/Instagram ka video link → uska thumbnail + us platform ka APNA diya hua
    data (views, uploader, lambai). Aalaada koi API/key nahi — wahi yt-dlp jo poore
    tool me hai. Sach: TikTok/IG ke views YouTube ke views jaise nahi gine jaate
    (algorithm aur 'view' ki paribhasha alag), isliye ye numbers sirf dikhate hain,
    tulna thumbnail KE NAAP se hota hai — jo dono platforms par ek jaisa naapa jaata."""
    try:
        host = (urllib.parse.urlparse(url).netloc or "").lower()
    except Exception:
        host = ""
    plat = "TikTok" if "tiktok.com" in host else ("Instagram" if "instagram.com" in host else "")
    if not plat:
        return {"error": "ye TikTok/Instagram ka link nahi lagta"}
    key = "xp_" + hashlib.md5(url.encode()).hexdigest()[:16]
    d = _cget(key, ttl=7 * 24 * 3600)
    if d is None:
        cmd = ["yt-dlp", "-J", "--no-warnings", "--playlist-items", "1"]
        # Instagram (kabhi-kabhi TikTok bhi) login maangta hai. cookies.txt tool ke folder
        # me ho to wo istaal hota hai — browser extension "Get cookies.txt LOCALLY" se
        # nikaalna kaafi hai. Na ho to neeche saaf error dikhega, jhooth nahi.
        ck = HERE / "cookies.txt"
        if ck.exists():
            cmd += ["--cookies", str(ck)]
        cmd.append(url)
        r = run(cmd, timeout=90)
        if r[0] != 0:
            err_all = (r[2] or r[1] or "")
            # yt-dlp ki asli wajah "ERROR:" line me hoti hai — poonchh ka poora
            # boilerplate kaat ke sirf wo line lo, warna asli wajah dikhegi hi nahi.
            line = next((l for l in err_all.splitlines() if "ERROR" in l), "")
            msg = (line or err_all)[-400:].strip()[:300]
            if "authentication" in msg.lower() and not ck.exists():
                msg += " — Instagram login maangta hai: tool ke folder me cookies.txt daalo (browser extension \"Get cookies.txt LOCALLY\" se nikalti hai)"
            return {"error": "yt-dlp is link se kuch nahi nikaal saka: " + msg}
        try:
            j = json.loads(r[1])
        except Exception:
            return {"error": "yt-dlp ka jawab samajh nahi aaya"}
        if isinstance(j.get("entries"), list) and j["entries"]:
            j = j["entries"][0]
        th = j.get("thumbnail") or ((j.get("thumbnails") or [{}])[-1] or {}).get("url") or ""
        if not th:
            return {"error": "us video ka thumbnail yt-dlp ko nahi mila (private/deleted ho sakta hai)"}
        d = {"plat": plat, "th": th, "views": j.get("view_count"), "id": str(j.get("id") or "")[:40],
             "title": str(j.get("title") or "")[:200], "up": str(j.get("uploader") or "")[:80],
             "dur": int(j.get("duration") or 0)}
        _cput(key, d)
    fp = THUMB_DIR / "xplat" / (key + ".jpg")
    if not fp.exists():
        try:
            THUMB_DIR.mkdir(parents=True, exist_ok=True)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(http_get(d["th"], timeout=30))
        except Exception as e:
            return {"error": "thumbnail download nahi ho saka: " + str(e)[:120]}
    d["path"] = str(fp)
    return d


def resolve_ref(ref):
    ref = (ref or "").strip().strip('"')
    if not ref:
        return None, "kuch nahi diya"
    m = VID_RE.search(ref)
    vid = m.group(1) if m else (ref if re.fullmatch(r"[0-9A-Za-z_-]{11}", ref) else None)
    if vid:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        p, kind = get_thumb(vid)
        return (str(p), "youtube:" + vid + ":" + kind) if p else (None, "us video ka thumbnail nahi mila")
    try:
        host = (urllib.parse.urlparse(ref).netloc or "").lower()
    except Exception:
        host = ""
    if "tiktok.com" in host or "instagram.com" in host:
        d = xplat_get(ref)
        if d.get("error"):
            return None, d["error"]
        return (d["path"], d["plat"].lower() + ":" + d.get("id", ""))
    p = Path(ref)
    if p.exists() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        return (str(p), "file")
    return None, "file nahi mila — poora path daalo (C:\\...\\thumb.jpg) ya YouTube ka link"


def do_check(ref, title=""):
    path, kind = resolve_ref(ref)
    if not path:
        return {"error": kind}
    an = analyse(path)
    w = ocr_cached(path)
    fc = faces_of(path)
    ts = text_stats(path, an, w or [], fc)
    # video id nikaalo (link/id se) — us par apna asli CTR/retention save karne ke liye
    r = (ref or "").strip()
    mm = re.search(r"(?:youtu\.be/|v=|/shorts/|/embed/)([0-9A-Za-z_-]{11})", r)
    vid = mm.group(1) if mm else (r if re.fullmatch(r"[0-9A-Za-z_-]{11}", r) else "")
    # YouTube ka link/id hai to us video ke ASLI tags + description laao (cached, ~0.45s
    # ek baar) — semantic tulna title ki andaaz se nahi, us par jo sach me laga hai us se.
    tags, desc, meta_ok = [], "", False
    if vid:
        m = meta_of(vid)
        if not m.get("err"):
            tags, desc, meta_ok = m["tags"], (m["desc"] or "")[:2500], True
    sem = sem_match(ts.get("text") or "", title or "", tags, desc, title or "")
    comp = comp_of(ts, fc)
    # TikTok/Instagram ka link tha to us platform ka apna diya hua data saath bhejo —
    # sirf dikhane ke liye, YouTube ke numbers se tulna karne ke liye nahi.
    xp = None
    if (kind or "").split(":")[0] in ("tiktok", "instagram"):
        dd = xplat_get(ref)
        if not dd.get("error"):
            xp = {k: dd.get(k) for k in ("plat", "views", "up", "dur", "title")}
    if comp:
        an["subj"] = comp["subject"]          # asli boxes — rang/edge ka andaaza nahi
        an["subj_src"] = "ocr+face boxes"
    cal = cal_now()
    return {"path": path, "kind": kind, "vid": vid, "xplat": xp, "own": own_load().get(vid) or {},
            "an": an, "ts": ts, "words": w or [], "faces": fc, "comp": comp, "sem": sem,
            "meta_ok": meta_ok,
            "tags": tags, "read320": len(ocr_cached(path, 320) or []),
            "dup": (dup_pct(title, ts.get("text") or "") if title else None),
            "score": score(an, ts, fc, cal), "cal": cal or {"n": 0},
            "eng": {"face": "YuNet" if get_yunet() else "Haar",
                    "ocr": ("Gemini vision → " if (OCR_GEM and gem_keys()) else "") + ("RapidOCR" if _RAPID_CLS else "tesseract")},
            "verdicts": verdicts(an, ts, fc, comp), "sd": score_detail(an, ts, fc, cal, comp),
            "sty": _sty_pix(path),
            "ocr_on": bool(w is not None), "cv": bool(cv2)}


# ---------------- regenerate (Tier A: wohi photo, behtar banakar) ----------------

def start_regen(ref, words, title=""):
    path, kind = resolve_ref(ref)
    if not path:
        return {"error": kind}
    jid = hashlib.md5((path + str(dt.datetime.now())).encode()).hexdigest()[:10]
    JOBS[jid] = {"state": "run", "done": 0, "total": 4, "current": "thumbnail padh raha hoon…", "kind": "regen"}
    threading.Thread(target=_do_regen, args=(jid, path, words or "", title or ""), daemon=True).start()
    return {"job": jid}


def _do_regen(jid, path, words, title=""):
    job = JOBS[jid]
    try:
        an = analyse(path)
        fc = faces_of(path)
        ow = ocr_cached(path) or []
        ts = text_stats(path, an, ow, fc)
        before = score(an, ts, fc)
        oldt = " ".join(wd["t"] for wd in ow)
        # behtar shabd title se chuno jo thumbnail par pehle se na hon (title dohrana nuqsan deh hai)
        job["current"] = "text ka hisaab laga raha hoon…"
        sug = pick_words(title, oldt) or pick_words(oldt, "") or oldt[:24]
        want = (words or "").strip() or sug
        job["current"] = "behtar version bana raha hoon…"
        vs = make_variants(path, want, an, ts, fc, old_words=ow,
                           prog=lambda i, n, name: job.update(
                               {"done": i, "total": n,
                                "current": "version " + str(i + 1) + "/" + str(n) + ": " + name +
                                           " bana kar dobara nap raha hoon…"}))
        # ---- Gemini rasta (key set ho to): local marammat ke saath-sath usi photo ke
        # do "model se banaye" version. Scene model se, shabd aur naap ClickLab ki apni
        # engine se — taake dono qisam ek hi paimana par tik kar aage-peeche hon. ----
        gem_err = ""
        if gem_key():
            job["total"] = len(vs) + len(GEM_REGEN_EDITS)
            job["current"] = "Gemini se usi photo ke behtar version maang raha hoon…"
            gvs, gem_errs = _gem_variants(jid, path, want, len(vs))
            vs.extend(gvs)
            vs.sort(key=lambda d: -d["score"])
            if gem_errs:
                gem_err = " · ".join(gem_errs)
        job["result"] = {"path": path, "before": before, "an": an, "ts": ts, "faces": fc,
                         "old": [wd["t"] for wd in ow], "suggest": sug, "used": want, "title": title,
                         "variants": vs, "gen": geninfo(), "gem": bool(gem_key()), "gem_err": gem_err}
        job["done"] = len(vs)
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = repr(e)[:300]
        # poora traceback na bachao to crash ka pata hi nahi chalta — UI aakhri kuch line dikhata hai
        job["tb"] = traceback.format_exc()[-1200:]


GEM_REGEN_EDITS = [
    ("Gemini: saaf scene, behtar grade",
     "Remove every letter, word, caption, watermark and logo from this thumbnail. Keep the exact same "
     "scene, subject and framing. Fill the space where the text was with calm, dark, clean background. "
     "Rework the color like a professional colorist: stronger contrast, clean separation between subject "
     "and background, punchy but believable colors, crisp faces. Output one image only.",
     "Gemini ne text hata kar jagah saaf ki aur rang/contrast colorist jaise sudhare — scene wahi raha"),
    ("Gemini: subject bara, mobile-ready",
     "Re-frame this thumbnail keeping the same person/subject identity and the same scene: make the main "
     "face or hero subject about 40 percent larger, place it on the right third, keep the left third dark "
     "and empty so a headline can sit there later, remove all text, and raise contrast/sharpness so it "
     "reads clearly at 210px on a phone. Output one image only.",
     "Gemini ne chehra/subject bara kiya, left hissa headline ke liye khaali chhoda, mobile-jaisa contrast"),
    # 27 Oct: user ki shart — regen me koi purana chehra/rang/layout copy na ho. Ye teesra
    # rasta SIRF us thumbnail ka tareeka (style) leta hai: naya chehra, naye rang, naya layout.
    ("Gemini: sirf tareeka lo — naya chehra, naye rang, naya layout",
     "Use this thumbnail only for its COMPOSITION IDEA and energy: recreate the same kind of visual "
     "trick (scale contrast, curiosity gap, or shock) with a COMPLETELY NEW person or subject, "
     "completely different colours, and a different layout. Do not reuse the face, the colour scheme, "
     "or the exact arrangement. Remove all text. Bold professional grade, deep soft shadows for depth, "
     "subtle grain, mobile-readable. Output one image only.",
     "Gemini ne uska tareeka (style) uthaya — chehra, rang aur layout sab naya, poora copy nahi"),
]


def _gem_variants(jid, path, want, base_done=0):
    """Tier A ke baad ka doosra rasta: asli thumbnail model ko dikha kar uske do behtar
    version maangna. Model aksar text phir bhi likh deta hai — wahi scrub hota hai jo
    AI tab karta hai (chehra mehfooz), aur chune shabd usi Pillow engine se likhe
    jaate hain jo local variants me use hota hai. Har version ko wahin ka naap lagta
    hai jo original ko laga tha. Key na ho to ye poora hissa chalta hi nahi."""
    out, errs = [], []
    base = hashlib.md5(str(path).encode()).hexdigest()[:8]
    for i, (name, instr, why) in enumerate(GEM_REGEN_EDITS):
        job = JOBS.get(jid) or {}
        job["current"] = "Gemini version " + str(i + 1) + "/" + str(len(GEM_REGEN_EDITS)) + ": " + name + "…"
        g = gem_edit(path, instr)
        job["done"] = base_done + i + 1
        if g.get("error"):
            # error text me "Gemini ..." prefix pehle se hota hai — dobara lagana "Gemini: Gemini"
            # banata hai. Isliye yahan edit ka apna chhota naam lagao taake pata chale kaun si koshish fail hui.
            errs.append(name.split(": ", 1)[-1][:30] + ": " + str(g["error"])[:90])
            continue
        try:
            REG_DIR.mkdir(parents=True, exist_ok=True)
            fp = REG_DIR / ("%s_gem%d.jpg" % (base, i))
            fp.write_bytes(g["bytes"])
            im = Image.open(fp).convert("RGB")
        except Exception as e:
            errs.append("Gemini ki tasveer padhi nahi ja saki: " + str(e)[:80])
            continue
        if im.size != (1280, 720):
            im = im.resize((1280, 720), Image.LANCZOS)
        an0 = analyse(str(fp))
        fc0 = faces_of(str(fp))
        w0 = ocr_cached(str(fp)) or []
        fpx = _face_px(fc0, im.size[0], im.size[1])
        if w0 and _scrub_ok(w0, im.size[0], im.size[1], fpx):
            im = _dertext_hard(im, w0, fpx)
        lines = _split_words(want)
        note = why
        if lines:
            try:
                im = _put_text(_grade(im), lines, _free_cell(im, an0, fc0))
                note += " · naye shabd usi engine se likhe jo local versions me use hota hai"
            except Exception:
                pass
        try:
            p2 = REG_DIR / ("%s_gem%d_final.png" % (base, i))
            im.save(p2, "PNG")
        except Exception:
            continue
        van = analyse(str(p2))
        vf = faces_of(str(p2))
        vw = ocr_cached(str(p2)) or []
        vts = text_stats(str(p2), van, vw, vf)
        out.append({"name": name, "why": note, "path": str(p2), "an": van, "ts": vts,
                    "faces": vf, "words": vw, "score": score(van, vts, vf),
                    "gem": g.get("model") or GEM_IMG_MODEL})
    return out, errs


# ---------------- variants ----------------

def load_var():
    try:
        return json.loads(VAR_F.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_var(v):
    VAR_F.parent.mkdir(parents=True, exist_ok=True)
    VAR_F.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- jeete hue topics → 10 ideas ----------------
# Sab kuch usi scan ke NAAPPE hue data se: "jeet" = views/day (umr ka hisaab lekar), aur
# har suggestion ke saath wo jeetne wala title/tag likha hai jis par wo bana hai. Naye
# shabd corpus ke bahar se nahi liye jaate — model ka kaam yahan sirf ranking hai,
# material banana nahi. Isliye har idea padh kar aap check kar sakte ho ke ye kahan se aaya.

WIN_N = 12                      # jeeton ki ginti (channel cap ke baad)
WIN_CAP = 2                     # ek channel se zyada se zyada itne jeete — warna ek channel poori list le leta hai
TPAT = [("number", "title me koi ginti (7, 10, 100000…)"),
        ("question", "sawal wala title (?)"),
        ("how", "how/why/what/kya/kaise se shuru"),
        ("caps", "BARE AKSHAR me emphasis"),
        ("pipe", "title me | ya · se tukre"),
        ("colon", "title me : (topic — hook)"),
        ("bracket", "[ ] ya ( ) ka istemal")]


def tpat(title):
    """Title ke wo patterns jo sach me gine ja sakte hain — koi 'attractive tha' wala
    andaaza nahi. Har pattern ka count jeeton vs neechewalon me alag alag hota hai."""
    t = title or ""
    return {"number": bool(re.search(r"(?i)\b\d{1,3}(?:[.,]\d+)?\b|\b\d+\s*(k|m|b|crore|lakh|million|billion|trillion|%)\b", t)),
            "question": "?" in t,
            "how": bool(re.match(r"(?i)\s*(how|why|what|when|which|who|kya|kaise|kyun|kyu)\b", t)),
            "caps": len(re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", t)) >= 1,
            "pipe": bool(re.search(r"[|｜·•]", t)),
            "colon": ":" in t,
            "bracket": bool(re.search(r"[\[(（]", t))}


def _doc_of(i):
    """Ek video ka wo poora text jisme se topic/keywords nikalte hain: uska title + us par
    LAGE hue asli tags (jo us channel ne khud lagaye the)."""
    return re.sub(r"\s+", " ", ((i.get("title") or "") + " " + " ".join(str(t) for t in (i.get("tags") or [])))).strip()


def _ntxt(s):
    """Phrase milane ke liye saaf text: sab non-alnum jagah space, ek space, kinare par
    space — taaki 'black hole' 'black holes' ke andar na gine."""
    return " " + re.sub(r"[^a-z0-9\u0600-\u06ff\u0900-\u097f]+", " ", (s or "").lower()).strip() + " "


def _segs(title):
    """Title ko uske ASLI tukron me kaato ( | : - jahan creator ne khud tukre hain). Ye
    woh hisse hain jo jeetne wale titles me sach me likhe mile — banaye nahi jaate."""
    out = []
    for p in re.split(r"\s*[|｜·•।]\s*|\s*[:]\s*|\s+[–—-]{1,}\s+", title or ""):
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p)
    return out


def _hooks(seed, hits, chset):
    """Jeetne wale titles ke wo ASLI tukre jo is topic ka naam ya channel ka naam nahi hain —
    yaani hook. Har hook ke saath wo video jahan se aaya (uska vpd) hota hai, taaki
    suggestion ka source check kiya ja sake."""
    ws, out, seen = set(_words(seed)), [], set()
    for i in hits:
        for s in _segs(i.get("title")):
            if not (8 <= len(s) <= 60) or s.lower() in seen:
                continue
            sw = set(_words(s))
            if not sw or (sw & ws) or (sw & chset):
                continue
            seen.add(s.lower())
            out.append({"s": s, "vpd": round(vpd(i), 1), "src": i.get("id"),
                        "src_title": re.sub(r"\s+", " ", (i.get("title") or ""))[:110]})
    out.sort(key=lambda x: -x["vpd"])
    return out


def _thumb_texts(hits):
    """Thumbnail par jo text sach me padha gaya (OCR) — jeetne wale thumbnails ke ASLI
    shabd. Ye "kya likhna chahiye" ka jawab corpus se deta hai, meri taraf se kuch nahi.
    Sirf wo lines rakhi jaati hain jo padhne layak hain: OCR aksar adhoora tukra deta
    hai ("ade", "193", "END") — wo nahi chahiye."""
    out, seen = [], set()
    for i in hits:
        t = ((i.get("ts") or {}).get("text") or "")
        for p in re.split(r"\s*[|｜·•]\s*", t):
            p = re.sub(r"\s+", " ", p).strip()
            if not (4 <= len(p) <= 40) or p.lower() in seen:
                continue
            if not re.search(r"[a-z\u0600-\u06ff\u0900-\u097f]{4,}", p.lower()):
                continue                              # sirf number/nishani ya 3 akshar ka tukra
            if re.fullmatch(r"[\d.,\s%$+#-]+", p):
                continue
            seen.add(p.lower())
            out.append({"t": p, "vpd": round(vpd(i), 1), "src": i.get("id"),
                        "h320": (i.get("ts") or {}).get("h320")})
    keep = []
    for a in out:                                     # kisi aur line ka tukra ho to chhod do
        if any(b is not a and a["t"].lower() in b["t"].lower() for b in out):
            continue
        keep.append(a)
    keep.sort(key=lambda x: (0 if " " in x["t"] else 1, -x["vpd"]))
    return keep[:8]


def _mk_titles(seed, hits, pats, chset):
    """3 title suggestions. Ye shabd banaye nahi jaate — hook usi scan ke jeetne wale
    titles ke tukron se liye jaate hain, aur har suggestion ke saath wo video likha hai
    jahan se wo structure aaya (uska views/day bhi)."""
    sc = re.sub(r"\s+", " ", seed).strip()
    sc = " ".join(w[:1].upper() + w[1:] for w in sc.split(" "))
    hs = _hooks(seed, hits, chset)
    pset = {p["k"] for p in pats if p["wr"] > p["lr"] and p["win"] >= 2}
    sep = " | " if "pipe" in pset else (": " if "colon" in pset else " — ")
    out = []
    for h in hs[:2]:
        out.append({"t": (sc + sep + h["s"])[:100], "pat": "topic + hook (jeetne wale title ka tukra)",
                    "src": h["src"], "src_vpd": h["vpd"], "src_title": h["src_title"],
                    "why": "hook \"%s\" us video ke title se liya gaya jiska views/day %s tha — poora structure wahi, sirf topic badla." % (h["s"], h["vpd"])})
    tt = _thumb_texts(hits)
    if len(out) < 3 and tt:
        out.append({"t": (sc + sep + tt[0]["t"])[:100], "pat": "topic + wo text jo jeetne wale THUMBNAIL par likha tha",
                    "src": tt[0]["src"], "src_vpd": tt[0]["vpd"], "src_title": "",
                    "why": "thumbnail par \"%s\" likha tha (OCR, us video ka views/day %s). Title me wahi hook try karo — thumbnail ka text title me dohrane se jagah barbaad hoti hai." % (tt[0]["t"], tt[0]["vpd"])})
    if len(out) < 3:
        # ginti wala pattern: wo ginti jo inhi jeeton ke titles me sabse zyada chalti hai.
        # Kam az kam 3 jagah mili ho tabhi ye pattern "chalta hai" kaha ja sakta hai.
        nums = [int(m) for i in hits for m in re.findall(r"(?<![\d.])(\d{1,2})(?![\d.])", i.get("title") or "")
                if 2 <= int(m) <= 99]
        base = next((i for i in hits if len(re.sub(r"\s+", " ", i.get("title") or "").strip()) <= 90), None)
        bt = re.sub(r"\s+", " ", (base.get("title") or "").strip()) if base else ""
        if len(nums) >= 3 and base and bt:
            hn = int(med(nums))
            bt2 = re.sub(r"(?<![\d.])(\d{1,2})(?![\d.])", str(hn), bt, count=1)
            if len(bt2) <= 100:
                out.append({"t": bt2, "pat": "jeetne wala title, sirf ginti badli",
                            "src": base.get("id"), "src_vpd": round(vpd(base), 1), "src_title": bt[:110],
                            "why": "structure #%s ke title par (uska views/day %s); ginti %d is %d jeetne wale titles me sabse zyada chalti thi." %
                                 (base.get("id"), round(vpd(base), 1), hn, len(nums))})
    if len(out) < 3:
        base = hits[0]
        bt = re.sub(r"\s+", " ", (base.get("title") or ""))[:100]
        out.append({"t": bt, "pat": "jeetne wala title (asli — iski nakal karo, copy mat karo)",
                    "src": base.get("id"), "src_vpd": round(vpd(base), 1), "src_title": bt,
                    "why": "is topic ke liye is scan me sabse zyada chala title — koi naya pattern nahi bana, kyunki is topic ke jeeton me aur koi pattern nazar nahi aaya."})
    return out[:3]


def ideas_of(sid, k=10):
    """Scan ke andar se jeete hue topics nikaalo aur un par naye ideas banao.
    Jeet = views/day (views ko umr se baantna, warna 5 saal purani video jeet jaati hai).
    Har idea ke saath: wo jeetne wale videos jo is topic par hain, unke ASLI tags,
    unke titles se naape gaye patterns, aur un thumbnails par jo text sach me padha gaya."""
    d = load_scan(sid or "")
    if not d:
        return None
    k = max(3, min(20, int(k or 10)))
    its = [i for i in (d.get("items") or []) if i.get("views") and i.get("thumb")]
    if len(its) < 6:
        return {"error": "is scan me %d videos hain — ideas ke liye kam se kam 6 chahiye" % len(its)}
    srt = sorted(its, key=lambda i: -vpd(i))
    # Jeet ka farak tab tak matlab rakhta hai jab "baaki" videos bache rahein —
    # chhote scan me sab jeete hue mat chuno, kam se kam 3 muqablay ke liye chhodo.
    wcap = max(3, min(WIN_N, len(its) - 3))
    win, per = [], {}
    for i in srt:
        c = (i.get("channel") or "").lower()[:40]
        if len(win) >= wcap or per.get(c, 0) >= WIN_CAP:
            continue
        win.append(i)
        per[c] = per.get(c, 0) + 1
    wids = {i.get("id") for i in win}
    tail = [i for i in srt if i.get("id") not in wids]
    half = max(3, len(tail) // 2)
    losers = tail[-half:]

    # ---- title ke patterns: jeeton me kitne, neechewalon me kitne (ginti, sawal, | , :) ----
    pats = []
    for key, lab in TPAT:
        w = sum(1 for i in win if tpat(i.get("title")).get(key))
        l = sum(1 for i in losers if tpat(i.get("title")).get(key))
        pats.append({"k": key, "lab": lab, "win": w, "win_n": len(win), "lose": l, "lose_n": len(losers),
                     "wr": round(100.0 * w / max(1, len(win)), 1), "lr": round(100.0 * l / max(1, len(losers)), 1)})
    pats.sort(key=lambda p: -(p["wr"] - p["lr"]))

    rest = tail                                   # jeeton ke alawa baaki sab videos
    # ---- ASLI tags: jo jeeton par lage hain vs jo baaki videos par lage hain ----
    def tset(i):
        out = []
        for t in (i.get("tags") or []):
            t = re.sub(r"\s+", " ", str(t).strip().lower())
            if 2 < len(t) <= 40:
                out.append(t)
        return list(set(out))
    tw, tr = Counter(), Counter()
    for i in win:
        for t in tset(i):
            tw[t] += 1
    for i in rest:
        for t in tset(i):
            tr[t] += 1
    tags_rank = [{"t": t, "win": tw[t], "rest": tr.get(t, 0)} for t in tw]
    tags_rank.sort(key=lambda x: (-(x["win"] / float(max(1, len(win))) - x["rest"] / float(max(1, len(rest)))),
                                  -x["win"], x["t"]))

    # ---- candidate phrases dhoondhna. TF-IDF ka kaam sirf *umer* (candidate) nikalna hai:
    # jeeton ke titles se aise shabd/jod jo baaki me kam hain. Ranking TF-IDF ke
    # weight se nahi hoti — har umer ki ASLI ginti ki jaati hai (kitne jeeton me likha hai
    # vs kitne baaki videos me), kyunke TF-IDF ke bigrams palte bhi aa sakte hain
    # ("hole black") jo kisi ne likhe hi nahi hote. umer sirf TITLES se nikalti hai: tags
    # alag alag line ke hote hain, unhe jod kar banne wala 3-gram ("youtuber khan sir")
    # kisi ne likha hi nahi hota. ginti phir title + tags dono me hoti hai. ----
    pool_terms, method = [], "ginti (shabdon ki ginti — sklearn nahi mila)"
    load_sk()
    if _TFIDF is not None:
        try:
            dW = [re.sub(r"\s+", " ", i.get("title") or "") for i in win]
            dR = [re.sub(r"\s+", " ", i.get("title") or "") for i in rest]
            tv = _TFIDF(stop_words=None, token_pattern=r"(?u)\b[^\W\d_]{3,}\b",
                        ngram_range=(1, 3), sublinear_tf=True, min_df=1)
            A = tv.fit_transform(dW + dR).toarray()
            nw = len(dW)
            for j, nm in enumerate(list(tv.get_feature_names_out())):
                if int((A[:nw, j] > 0).sum()) >= 2:
                    pool_terms.append(str(nm).strip())
            method = "TF-IDF (sklearn) se umer sirf titles se; phir title+tags me asli ginti"
        except Exception:
            pool_terms = []
    if not pool_terms:
        cw = Counter()
        for i in win:
            for w in set(_words(i.get("title") or "")):
                cw[w] += 1
        pool_terms = [w for w, c in cw.items() if c >= 2]

    dlow = {i.get("id"): _ntxt(_doc_of(i)) for i in its}
    chset = set()
    for i in its:
        chset |= set(_words(i.get("channel") or ""))

    def sup_of(phrase):
        """Ye phrase (poora, is tarteeb se) kitne jeeton me likha hai aur kitne baaki me."""
        p = " " + re.sub(r"[^a-z0-9\u0600-\u06ff\u0900-\u097f]+", " ", (phrase or "").lower()).strip() + " "
        w = sum(1 for i in win if p in dlow.get(i.get("id"), ""))
        r = sum(1 for i in rest if p in dlow.get(i.get("id"), ""))
        return w, r

    cand, seenp = [], set()

    def addc(phrase, src):
        p = re.sub(r"\s+", " ", str(phrase)).strip().lower()
        if not (4 <= len(p) <= 60) or p in seenp:
            return
        toks = set(_words(p))
        if not toks or len(toks & chset) >= max(1, int(round(0.6 * len(toks)))):
            return                                  # channel ka naam topic nahi hota
        w, r = sup_of(p)
        if w < 2:
            return                                  # kam se kam 2 jeeton par hona chahiye
        rw, rr = w / float(max(1, len(win))), r / float(max(1, len(rest)))
        if rw <= rr:
            return                                  # baaki me barabar/zyada hai to ye naya idea nahi
        if " " in p:
            rev = " ".join(reversed(p.split(" ")))
            if sup_of(rev)[0] > w:
                return                              # palta hua phrase zyada chalta hai = TF-IDF ka shor
            seenp.add(rev)
        seenp.add(p)
        cand.append({"p": p, "win": w, "rest": r, "wr": round(100.0 * rw, 1),
                     "rr": round(100.0 * rr, 1), "diff": round(rw - rr, 3), "src": src})

    for t in pool_terms:
        addc(t, "jeeton ke titles+tags se nikla phrase")
    for x in tags_rank:
        addc(x["t"], "jeeton par lage ASLI tags me se")
    # "bang" akela "big bang" ka tukra hai, "holes" akela "black holes" ka. Jab tukra
    # utne hi jeeton me milta hai jitna poora phrase, to wo extra kuch nahi batata —
    # tukra chhod do, poora phrase rakho.
    keep = []
    for a in cand:
        ta = set(_words(a["p"]))
        if any(b is not a and b["win"] >= a["win"] and len(set(_words(b["p"]))) > len(ta)
               and ta <= set(_words(b["p"])) for b in cand):
            continue
        keep.append(a)
    cand = keep
    cand.sort(key=lambda c: (-c["diff"], -c["win"], -len(_words(c["p"])), c["p"]))

    def wrow(i):
        # ek jeete hue video ka chhota record — table aur card, dono ke liye ek hi source
        return {"id": i.get("id"), "title": re.sub(r"\s+", " ", (i.get("title") or ""))[:120],
                "channel": i.get("channel"), "url": i.get("url"), "views": i.get("views"),
                "days": i.get("days"), "vpd": round(vpd(i), 1), "thumb": i.get("thumb"),
                "score": i.get("score"), "words": (i.get("ts") or {}).get("n"),
                "h320": (i.get("ts") or {}).get("h320"), "subs": i.get("subs"),
                "tags_n": len(i.get("tags") or []), "nch": i.get("nch"),
                "text": ((i.get("ts") or {}).get("text") or "")[:120]}

    ideas, used_h, used_t = [], [], []
    for c in cand:
        if len(ideas) >= k:
            break
        sd = c["p"]
        ws = set(_words(sd))
        if not ws:
            continue
        hits = [i for i in win if ws <= set(_words(_doc_of(i)))]
        if len(hits) < 2:
            continue
        hid = frozenset(i.get("id") for i in hits)
        if hid in used_h:
            continue                                        # wahi jeetne wale videos = wahi idea
        if any(len(ws & u) >= 0.5 * len(ws | u) for u in used_t):
            continue                                        # pehle bane idea ka hi doosra roop
        comp = [i for i in its if ws <= set(_words(_doc_of(i)))]
        cv = [vpd(i) for i in comp]
        tg, seen2 = [], set()
        for i in hits:
            for t in tset(i):
                if t in seen2:
                    continue
                seen2.add(t)
                tg.append({"t": t, "win": tw.get(t, 1), "rest": tr.get(t, 0)})
        tg.sort(key=lambda x: (-(x["win"] - x["rest"]), -x["win"], x["t"]))
        tg = tg[:25]
        # keywords: inhi jeeton ke titles/tags me jo saathi shabd sabse zyada chalte hain
        kw = Counter()
        for i in hits:
            for w in set(_words(_doc_of(i))) - ws - chset:
                kw[w] += 1
        kw = [w for w, _n in sorted(kw.items(), key=lambda x: (-x[1], x[0]))][:15]
        wn = [((i.get("ts") or {}).get("n") or 0) for i in hits]
        hh = [((i.get("ts") or {}).get("h320") or 0) for i in hits]
        base = hits[0]
        used_h.append(hid)
        used_t.append(ws)
        ideas.append({
            "n": len(ideas) + 1, "topic": sd, "src": c["src"], "win_sup": c["win"], "rest_sup": c["rest"],
            "win_rate": c["wr"], "rest_rate": c["rr"], "diff": c["diff"],
            "from": [wrow(i) for i in hits[:5]],
            "titles": _mk_titles(sd, hits, pats, chset),
            "hooks": _hooks(sd, hits, chset)[:6],
            "thumb_texts": _thumb_texts(hits),
            "tags": [x["t"] for x in tg], "tag_rows": tg[:15], "keywords": kw,
            "compete": len(comp), "compete_vpd_med": round(med(cv), 1) if cv else 0,
            "win_vpd_med": round(med([vpd(i) for i in win]), 1),
            "rest_vpd_med": round(med([vpd(i) for i in rest]), 1),
            "thumb_brief": {"n_hits": len(hits), "words_med": int(med(wn)), "h320_med": round(med(hh), 1),
                            "faces": sum(1 for i in hits if i.get("faces"))},
            "ref": base.get("thumb"), "ref_id": base.get("id"), "ref_url": base.get("url"),
            "ref_title": re.sub(r"\s+", " ", (base.get("title") or ""))[:120],
            "ref_vpd": round(vpd(base), 1), "ref_score": base.get("score"),
            "prompt": (sd + " " + " ".join(kw[:6])).strip(),
        })
    return {"id": d.get("id"), "topic": d.get("topic"), "n": len(its), "win_n": len(win),
            "rest_n": len(rest), "lose_n": len(losers), "method": method, "patterns": pats,
            "win_vpd_med": round(med([vpd(i) for i in win]), 1),
            "rest_vpd_med": round(med([vpd(i) for i in rest]), 1),
            "winners": [wrow(i) for i in win],
            "tags": tags_rank[:30], "phrases": cand[:30], "ideas": ideas, "short": len(ideas) < k,
            "note": "jeet ka naap views/day hai (views ÷ umr), aur ek channel se zyada se zyada %d jeete shamil hain — warna ek hi channel poori list le leta. Jo phrase baaki videos me bhi utna hi chalta hai wo idea nahi mana jaata — naya wahi hai jo jeeton me zyada aur baaki me kam ho." % WIN_CAP}


# ---------------- copy the idea (ek video → tags/keywords → taqatwar ideas) ----------------

IDEA_ASK = (
    "Ye ek YouTube video ka ASLI metadata hai (title, uske asli tags, description ka tukda, "
    "aur user ka scan topic). Is se do cheezein chahiye — sirf ek valid JSON object, koi markdown nahi:\n"
    '{"topics":[{"t":"...","why":"..."}]} — 3 aise topics jo is video ke audience se MATCH karte hain '
    '(yani log is video ke zariye ye topics already dhoondh rahe hain), aur\n'
    '{"ideas":[{"t":"...","angle":"...","words":"..."}]} — 6 TAQATWAR naye video ideas jo inhi '
    'tags/keywords par based hon, original se aage nikalte hue (nakal nahi). "t" = poora video title '
    '(topic English ka ho to title English), "angle" = ek line kyun jeetega (hook/curiosity kya hai), '
    '"words" = thumbnail par likhne ke 2 se 4 shabd.\n'
    "Saari explanation Roman Urdu me likho. Sirf JSON output karo, kuch aur nahi.")


def idea_pack(vid, topic=""):
    """Ek video ka idea-packet: ASLI tags (YouTube listing se) + gine-gaye keywords
    (title+tags+description se) = fact; aur Gemini se matched topics + taqatwar ideas
    = "model ka andaza" — kabhi naapon me nahi milte. Key na ho to sirf facts bhejte
    hain aur saaf likhte hain ke ideas ke liye key chahiye."""
    m = meta_of(vid)
    if m.get("err"):
        return {"ok": False, "error": m["err"]}
    title = m.get("title") or ""
    tags = [str(t).strip() for t in (m.get("tags") or []) if str(t).strip()][:30]
    cw = Counter()
    for w in toks(title):
        cw[w] += 1
    for t in tags:
        for w in toks(str(t)):
            cw[w] += 2
    for w in toks((m.get("desc") or "")[:1500]):
        cw[w] += 1
    kws = [w for w, _n in cw.most_common(60) if len(w) > 2][:18]
    out = {"ok": True, "vid": vid, "title": title, "ch": m.get("ch") or "",
           "tags": tags, "keywords": kws, "ideas": [], "topics": [], "model": ""}
    if not gem_key():
        out["no_key"] = True
        return out
    ctx = ("VIDEO TITLE: " + title[:300] + "\nCHANNEL: " + (m.get("ch") or "")[:80] +
           "\nASLI TAGS: " + ", ".join(tags[:30]) +
           "\nDESCRIPTION (excerpt): " + re.sub(r"\s+", " ", (m.get("desc") or ""))[:1200] +
           (("\nUSER SCAN TOPIC: " + topic[:120]) if topic else ""))
    r = gem_try([GEM_MODEL] + GEM_MODEL_ALT,
                [{"text": ctx + "\n\n" + IDEA_ASK}], maxtok=3000, temperature=0.8)
    if not r.get("error"):
        out["model"] = r.get("model") or ""
        J = _json_block(r.get("text") or "")
        if J:
            out["topics"] = [{"t": str(x.get("t") or "")[:120], "why": str(x.get("why") or "")[:200]}
                             for x in (J.get("topics") or [])[:3] if isinstance(x, dict)]
            out["ideas"] = [{"t": str(x.get("t") or "")[:160], "angle": str(x.get("angle") or "")[:220],
                             "words": str(x.get("words") or "")[:40]}
                            for x in (J.get("ideas") or [])[:6] if isinstance(x, dict) and str(x.get("t") or "").strip()]
        else:
            out["error"] = "model ka jawab JSON me na padha ja saka — dobara try karein"
    else:
        out["error"] = r.get("error")
    return out


# ---------------- share zip (dost ko bhejne layak fresh copy) ----------------

def share_zip():
    """ClickLab-share.zip — sirf tool ka maal: code, bat, docs, requirements.
    JAAN BOOJH KAR BAHIR: API keys (har *_key.txt user ki apni hoti hain), aur
    thumb_output/ = user ki poori history (scans, thumbnails, OCR, transcripts) —
    dost fresh shuru kare, apni keys khud daale. Jo file '_' se shuru hoti hai wo
    kaam ke beech ka kachra hai — wo bhi nahi. Zip ka apna record bhi nahi."""
    import zipfile
    buf = io.BytesIO()
    inc = []
    for f in sorted(HERE.iterdir()):
        n = f.name
        if f.is_dir() or n.startswith("_") or n.endswith(".zip") or n.endswith("_key.txt"):
            continue
        if n == "clicklab.py" or n.endswith(".bat") or n.endswith(".md") or \
           n in ("requirements.txt", "thresholds_measured.json"):
            inc.append(f)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in inc:
            zf.write(f, "ClickLab/" + f.name)
        zf.writestr("ClickLab/SHURU_KARNE_SE_PEHLE.txt",
                    "Yeh zip fresh copy hai — isme jaan boojh kar NAHI daala gaya:\n"
                    "  * koi API key (gemini_key.txt, runware_key.txt, youtube_key.txt) — ye har user ki apni hoti hain\n"
                    "  * thumb_output/ — ye pichle user ki poori history hai (scans, OCR, transcripts, banaye thumbnails)\n\n"
                    "Shuru karne ka tareeqa: Python 3 + (pip install -r requirements.txt) → ClickLab.bat par double-click.\n"
                    "Poora setup, accounts aur har API ka hisaab SETUP.md me hai (kaunsi key kis kaam ke liye, kya bina key chalta hai).\n"
                    "Sabse kam setup: sirf ek Gemini key (aistudio par free) — poora naap engine + OCR (Gemini vision se, machine par kuch nahi\n"
                    "chalta) + \"Gemini se dekhwa lo\" chal jaata hai. Runware = paid tasveerein ($0.0006/image se), YouTube Data API =\n"
                    "Trending/official tags (free quota), Antigravity = Nano Banana 2 aapki Google AI subscription par (API key nahi).\n"
                    "Keys ke bina bhi zyada tool chalta hai; jo kaam key maangta hai uski jagah saaf likha hota hai.\n")
    data = buf.getvalue()
    try:
        (HERE / "ClickLab-share.zip").write_bytes(data)   # folder me bhi taaza record rahe
    except Exception:
        pass
    return data


# ---------------- export (ek click me file) ----------------

def _csvc(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        v = "; ".join(str(x) for x in v)
    elif isinstance(v, float):
        v = round(v, 4)
    return '"' + str(v).replace('"', '""') + '"'


EXP_COLS = [
    ("rank", "views/day se position"), ("scan_id", ""), ("topic", ""),
    ("video_id", ""), ("title", ""), ("channel", ""), ("url", "YouTube ka seedha link"),
    ("published", ""), ("published_time", "asli upload ka waqt (API/yt-dlp se mila, to hi bhara gaya)"),
    ("age_days", ""), ("views", ""), ("views_per_day", "ranking isi se hoti hai"),
    ("duration_s", ""), ("subscribers", ""), ("likes", ""), ("comments", ""), ("chapters", ""),
    ("tags_count", "asli tags, jo us video par lage hain"), ("tags", "jo us channel ne khud lagaye"),
    ("desc_chars", ""), ("listing_score", "listing ki safai 0-100 (CTR nahi)"),
    ("thumb_score", "0-100, us scan ke wazon se"), ("score_weights", "us scan me kaunse wazan chale"),
    ("thumb_file", ""), ("thumb_text_ocr", "thumbnail par jo text sach me padha gaya"),
    ("text_words", ""), ("text_max_h_px_at_320", ""), ("text_readable_at_320", "320px par kitne shabd padhe gaye"),
    ("text_contrast_min", "WCAG, glyph vs uska asli background"), ("text_contrast_median", ""),
    ("outline_contrast", ""), ("text_coverage", "text box ka kitna % sach me glyph hai"),
    ("text_blocks", ""), ("faces_count", "YuNet"), ("face_max_area_pct", "frame ka kitna % chehra"),
    ("subject_pct", "subject ka frame %"), ("dominance", "1 = ek subject, chhota = bheed"),
    ("rule_of_thirds", ""), ("brightness", ""), ("dynamic_range", ""), ("clutter", ""),
    ("sharpness", ""), ("match_topic", ""), ("match_tags", ""), ("match_title", ""), ("match_desc", ""),
    ("missing_keywords", "listing ke bare keyword thumbnail par gaib"),
]


def export_scan(sid, fmt="csv"):
    """Scan ka poora result file me. CSV flat hai taaki Excel/Sheets me pivot ban sake, aur
    JSON me wahi sab kuch hai jo scan file me hai. Jo value naapi hi nahi gayi wo khaali chhodi
    jaati hai — zero ya andaaza nahi bhara jaata."""
    d = load_scan(sid or "")
    if not d:
        return None
    items = sorted(d.get("items") or [],
                   key=lambda i: -float(i.get("views") or 0) / max(1, int(i.get("days") or 1)))
    if fmt == "json":
        keep = ("id", "title", "channel", "url", "views", "days", "dur", "subs", "likes", "cmts",
                "nch", "tags", "dlen", "ls", "lchk", "score", "cal", "kind", "eng", "an", "faces",
                "ts", "pubts", "pt", "comp", "sem", "dup", "thumb")
        out = {k: v for k, v in d.items() if k != "items"}
        out["items"] = []
        for n, i in enumerate(items, 1):
            row = {k: i.get(k) for k in keep}
            row["vpd"] = round(float(i.get("views") or 0) / max(1, int(i.get("days") or 1)), 1)
            row["rank"] = n
            out["items"].append(row)
        return json.dumps(out, ensure_ascii=False, indent=1).encode("utf-8"), "json", \
            "application/json; charset=utf-8"
    lines = [",".join(c[0] for c in EXP_COLS)]
    for n, i in enumerate(items, 1):
        ts, an, cmp_, sm = i.get("ts") or {}, i.get("an") or {}, i.get("comp") or {}, i.get("sem") or {}
        fc = i.get("faces") or []
        vpd = float(i.get("views") or 0) / max(1, int(i.get("days") or 1))
        ptv = i.get("pt") or ""
        if not ptv and i.get("pubts"):
            try:
                ptv = dt.datetime.utcfromtimestamp(int(i["pubts"])).isoformat(sep=" ", timespec="minutes") + "Z"
            except Exception:
                ptv = ""
        vals = [n, d.get("id") or "", d.get("topic") or "", i.get("id"), i.get("title"), i.get("channel"),
                i.get("url"), i.get("upload"), ptv, i.get("days"), i.get("views"), round(vpd, 1),
                i.get("dur"), i.get("subs"), i.get("likes"), i.get("cmts"), i.get("nch"),
                len(i.get("tags") or []), i.get("tags"), i.get("dlen"), i.get("ls"), i.get("score"),
                ((i.get("cal") or {}).get("n") and "calibrated n=%s" % i["cal"]["n"]) or "heuristic",
                i.get("thumb"), ts.get("text"), ts.get("n"), ts.get("h320"), ts.get("read320"),
                ts.get("cr"), ts.get("cr_med"), ts.get("ring_cr"), ts.get("cov"), ts.get("blocks"),
                len(fc), max([f.get("area") or 0 for f in fc], default=None),
                cmp_.get("subj_pct"), cmp_.get("dom"), cmp_.get("thirds"),
                an.get("bright"), an.get("dyn"), an.get("clutter"), an.get("sharp"),
                sm.get("t_topic"), sm.get("t_tags"), sm.get("t_title"), sm.get("t_desc"), sm.get("miss")]
        lines.append(",".join(_csvc(v) for v in vals))
    # BOM: Excel UTF-8 sahi padhe (Roman Urdu/English dono theek)
    return ("\ufeff" + "\r\n".join(lines) + "\r\n").encode("utf-8"), "csv", "text/csv; charset=utf-8"


# ---------------- http ----------------

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".bmp": "image/bmp"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", disp=None):
        b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if disp:
            # file download: browser khuli window me na khole, save kare
            self.send_header("Content-Disposition", disp)
        self.send_header("Content-Length", str(len(b)))
        # no-store: poori app isi ek page me hai aur server har badlav ke baad restart hota
        # hai. Bina iske browser purana page pakad kar baithta hai (yahan koi ETag ya
        # Last-Modified nahi hai), aur naya code dikhta hi nahi — user ko "hard refresh"
        # karna padta hai, jo is tool me har baar ka kaam ho jata.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)
        start_warm()

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return {}

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        d = self._body()
        try:
            if u.path == "/api/upload":
                name = re.sub(r"[^\w.\-]", "", (d.get("name") or "thumb.png"))
                b = d.get("b64") or ""
                import base64
                raw = base64.b64decode(b.split(",", 1)[-1])
                CHK_DIR.mkdir(parents=True, exist_ok=True)
                p = CHK_DIR / (dt.datetime.now().strftime("%H%M%S_") + name)
                p.write_bytes(raw)
                return self._send(200, {"path": str(p)})
            if u.path == "/api/regen":
                return self._send(200, start_regen(d.get("ref") or "", d.get("words") or "", d.get("title") or ""))
            if u.path == "/api/aigen":
                return self._send(200, start_ai(d.get("idea") or "", d.get("words") or "",
                                               d.get("mk") or AIDEF, d.get("ref") or "",
                                               bool(d.get("text_ai")), d.get("res") or "sd",
                                               d.get("strength"), d.get("eng") or "rw",
                                               d.get("method") or "auto"))
            if u.path == "/api/gemkey":
                return self._send(200, gem_set_key(d.get("key") or "", bool(d.get("add"))))
            if u.path == "/api/ocrmode":
                return self._send(200, ocr_gem_set(bool(d.get("on"))))
            if u.path == "/api/ytkey":
                return self._send(200, yt_set_key(d.get("key") or "", bool(d.get("add"))))
            if u.path == "/api/gemlook":
                return self._send(200, gem_look(d.get("ref") or "", d.get("title") or ""))
            if u.path == "/api/gemdeep":
                return self._send(200, gem_deep(d.get("ref") or "", d.get("title") or ""))
            if u.path == "/api/stfix":
                # User ne classifier ki style theek kar di — scan file me likh do,
                # taake agli baar user ki theek hi lage, classifier nahi.
                return self._send(200, sty_fix(d.get("id") or "", d.get("vid") or "",
                                              d.get("fix") or ""))
            if u.path == "/api/cmpbsave":
                # Video ko competitor bank me save karo — style/niche user chunta hai.
                return self._send(200, cmpb_save(d))
            if u.path == "/api/cmpbdel":
                return self._send(200, cmpb_del(d.get("vid") or ""))
            if u.path == "/api/cmpbseed":
                return self._send(200, cmpb_seed(d))
            if u.path == "/api/upscale":
                return self._send(200, up4(d.get("ref") or d.get("path") or "", d.get("mode") or "free"))
            if u.path == "/api/own":
                return self._send(200, own_set(d.get("vid") or "", d.get("ctr"), d.get("ret"),
                                              d.get("note") or ""))
            if u.path == "/api/own_csv":
                return self._send(200, own_import_csv(d.get("csv") or "", bool(d.get("dry"))))
            if u.path == "/api/calibrate":
                return self._send(200, start_cal())
            if u.path == "/api/rpm":
                # user ka apna Studio RPM mil jaye to kamai ka andaza band ho kar ASLI
                # calculation ban jata hai — isliye sirf di hui value store hoti hai.
                r = set_rpm(d.get("cid") or "", d.get("long"), d.get("short"), d.get("note") or "")
                # purane scans ka kamai ka hisaab foran badal do ( warna purana andaza dikhega)
                r["scans_updated"] = refresh_earn(d.get("cid") or "")
                return self._send(200, r)
            if u.path == "/api/aikey":
                return self._send(200, rw_set(d.get("key") or ""))
            if u.path == "/api/aiclear":
                return self._send(200, clear_ai())
            if u.path == "/api/variant":
                vs = load_var()
                d["ts"] = dt.datetime.now().isoformat(timespec="seconds")
                d["id"] = hashlib.md5(str(dt.datetime.now()).encode()).hexdigest()[:8]
                vs.insert(0, d)
                save_var(vs[:200])
                return self._send(200, {"ok": True, "n": len(vs)})
            if u.path == "/api/variant_del":
                vs = [v for v in load_var() if v.get("id") != d.get("id")]
                save_var(vs)
                return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(500, {"error": repr(e)[:300]})
        self._send(404, {"error": "??"})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        # cmd/console me har API call dikhe — chupchap nahi guzarti; aur jo kaam
        # ghonton chalta hai uski barqadar progress usi ke neeche chhapti hai.
        if u.path.startswith("/api/"):
            _log("%s %s" % (time.strftime("%H:%M:%S"), u.path + (("?" + u.query) if u.query else "")))
        try:
            if u.path == "/":
                return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/api/sys":
                # UI ko wahi thresholds/engine bataye jo server par sach me chal rahe hain,
                # taaki page me koi hand-picked number dobara na likha jaaye.
                c = load_cal()
                own = own_load()
                ready = sum(1 for v in own.values()
                            if isinstance(v.get("ctr"), (int, float)) and 0 < float(v["ctr"]) < 100)
                fe = face_engine()
                return self._send(200, {
                    "th": TH, "base": BASE, "w_def": W_DEF, "w_on": (c or {}).get("w") or W_DEF,
                    "cal": c, "heuristic": not c, "cal_rejected": _CALREJ[0], "need": CAL_MIN_N,
                    "own_rows": len(own),
                    "own_ready": ready, "ridge": _RIDGE is not None, "tfidf": _TFIDF is not None,
                    "eng": {"face": ("YuNet (cv2.FaceDetectorYN)" if fe == "yunet" else
                                     ("Haar cascade — kamzor, model download nahi hua" if fe == "haar" else "kuch nahi")),
                            "ocr": ("RapidOCR PP-OCRv4" if _RAPID_CLS else
                                    ("Tesseract — kamzor, rapidocr nahi hai" if find_tesseract() else "kuch nahi")),
                            "sem": ("TF-IDF (sklearn)" if _TFIDF else
                                  ("abhi load ho raha hai" if not _SK_DONE else "koi semantic model nahi")),
                            "cv": bool(cv2), "np": bool(np)},
                    "warm": eng_state(), "eta": meas_eta(1), "workers": [WORKERS, WORKERS2]})
            if u.path == "/api/cal":
                c = load_cal()
                own = own_load()
                ready = sum(1 for v in own.values()
                            if isinstance(v.get("ctr"), (int, float)) and 0 < float(v["ctr"]) < 100)
                return self._send(200, {"cal": c, "heuristic": not c, "cal_rejected": _CALREJ[0], "need": CAL_MIN_N,
                                        "own_rows": len(own), "own_ready": ready,
                                        "ridge": _RIDGE is not None, "def_w": W_DEF})
            if u.path == "/api/ping":
                # sasta sehat-ka-pata: bat file aur launcher isi se poochhte hain ke
                # ClickLab pehle se chal raha hai ya nahi — koi scan parse nahi hota.
                return self._send(200, {"ok": True, "app": "clicklab"})
            if u.path == "/api/scans":
                return self._send(200, {"scans": list_scans(), "yt": bool(yt_key()), "ytn": len(yt_keys()), "trg": TREND_REGIONS})
            if u.path == "/api/styles":
                return self._send(200, styles_get())
            if u.path == "/api/kwfind":
                return self._send(200, kw_find((q.get("niche") or "").strip(),
                                              (q.get("style") or "").strip()))
            if u.path == "/api/tr":
                # Transcription — sirf user ki request par (button), ek baar cache.
                # ocr=1 wala rasta un videos ke liye jin par subtitles hi nahi:
                # screen par likha text frames se padha jaata hai (upar tr_ocr).
                # Per-vid lock: dobara dabane par doosra OCR job nahi chalta — wo
                # pehle wale ke khatam hone ka intezaar karta hai, phir cache se le leta hai.
                if pnum(q.get("ocr")):
                    vid = re.sub(r"[^A-Za-z0-9_-]", "", q.get("id") or "")[:12]
                    lk = _tr_lock(vid)
                    if not lk.acquire(blocking=False):
                        _log("tr-ocr %s: ye kaam pehle se chal hi raha hai — naya job shuru nahi, "
                             "usi ke khatam hone ka intezaar (phir seedha cache)" % vid)
                        lk.acquire()
                    try:
                        r = tr_ocr(vid)
                    finally:
                        lk.release()
                    # screen-OCR ka kachra user ko nahi dikhna chahiye — cache file
                    # jaisi hai waisi rehti hai; safai bhejte waqt hoti hai, LINE-LINE
                    # (timestamp ke saath) — jod kar 400 akshar karna yahan ghalat tha,
                    # wo thumbnail-chip ka kaam hai; is se poora text 2 lines ban raha tha.
                    if r.get("text"):
                        r["text"], r["cut"] = ocr_screen_clean(r["text"])
                    return self._send(200, r)
                return self._send(200, tr_get(q.get("id") or ""))
            if u.path == "/api/trp":
                # screen-OCR ki live progress (frame X/Y) — UI andhere me na ghume
                vid = re.sub(r"[^A-Za-z0-9_-]", "", q.get("id") or "")[:12]
                p = _TRP.get(vid)
                return self._send(200, p if p else {"none": 1})
            if u.path == "/api/verdict":
                # Jeetne walon ka model-verdict — sirf button par; chain upar vd_get me.
                return self._send(200, vd_get(q.get("id") or "", bool(pnum(q.get("force")))))
            if u.path == "/api/sty":
                # Style jeet — andaza classifier ek baar, phir file me; jeet ka
                # naap (views/day) client ke paas already hai.
                return self._send(200, sty_measure(q.get("id") or ""))
            if u.path == "/api/trend":
                return self._send(200, start_trend((q.get("region") or "PK").strip().upper()[:2],
                                                   pnum(q.get("n")) or 25))
            if u.path == "/api/reddit":
                return self._send(200, rd_search((q.get("topic") or "").strip(), pnum(q.get("n")) or 25))
            if u.path == "/api/trends":
                return self._send(200, tr_interest((q.get("topic") or "").strip()))
            if u.path == "/api/scan":
                topic = (q.get("topic") or "").strip()
                if not topic:
                    return self._send(400, {"error": "topic daalo"})
                n = max(5, min(MAXN, pnum(q.get("n")) or DEF_N))
                return self._send(200, start_scan(topic, n, q.get("wide") == "1", q.get("meta") != "0"))
            if u.path == "/api/chsearch":
                # YouTube ka Channel filter: naam se channels ki list (subscriber/verified
                # YouTube ka diya hua hai). Result cache hota hai (chc/).
                return self._send(200, {"q": q.get("q") or "", "chans": ch_search(q.get("q") or "",
                                                                                 pnum(q.get("n")) or 50)})
            if u.path == "/api/chscan":
                # channel kholo: listing -> har video ka asli data -> thumbnail/OCR naap ->
                # scan file (wahi engine jo topic scan ke liye chalta hai). Job banata hai.
                n = max(5, min(CHN_MAX, pnum(q.get("n")) or CHN_DEF))
                return self._send(200, start_chan(q.get("q") or q.get("url") or "", n))
            if u.path == "/api/hist":
                sid = q.get("id") or ""
                if pnum(q.get("take")):
                    r = hist_take(sid)
                    if r.get("ok"):
                        r["hist"] = hist_get(sid)
                    return self._send(200, r)
                if pnum(q.get("refresh")):
                    return self._send(200, hist_refresh(sid, pnum(q.get("refresh"))))
                return self._send(200, hist_get(sid))
            if u.path == "/api/chcmp":
                ids = [x for x in re.split(r"[,\s]+", q.get("id") or "") if x]
                r = ch_cmp(ids)
                return self._send(200, r if r.get("cols") else (r or {"error": "channel scans nahi mile"}))
            if u.path == "/api/chwalk":
                # Channel ki POORI listing (gini hui, naap se bahar wali bhi). Ye sirf gin
                # hai: views flat listing se (YouTube ka diya), title/duration bhi wahi se.
                # Naap (tags/OCR/score/likes) usi video ka chalta hai jab us par kaam ho.
                sid = q.get("id") or ""
                wk = ensure_walk(sid, bool(pnum(q.get("force"))))
                if not wk:
                    return self._send(200, {"err": "is scan ke liye channel ki listing dobara nahi mil saki"})
                f = SCN_DIR / (sid + ".json")
                have = []
                if f.exists():
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                        have = [i.get("id") for i in (d.get("items") or [])]
                    except Exception:
                        pass
                rows = wk["v"] + wk["s"]
                return self._send(200, {"rows": rows, "terr": wk.get("terr") or "",
                                        "cap": wk.get("cap") or CH_WALK, "got": wk.get("got") or "",
                                        "n_long": len(wk["v"]), "n_short": len(wk["s"]),
                                        "measured": have})
            if u.path == "/api/tback":
                return self._send(200, ts_backfill(q.get("id", "")))
            if u.path == "/api/join":
                return self._send(200, api_join(q.get("id", "")))
            if u.path == "/api/cmpb":
                return self._send(200, cmpb_load())
            if u.path == "/api/chmore":
                # Jo videos ab tak sirf gini gayi hain un par wahi naap chalao (job banega).
                ids = [x for x in re.split(r"[,\s]+", q.get("ids") or "") if x] or None
                return self._send(200, extend_chan(q.get("id") or "", pnum(q.get("n")) or 20,
                                                   q.get("kind") or "long", ids))
            if u.path == "/api/spon":
                # SponsorBlock ke community marks (job banega) — ads jaisa bojh dekhne ke liye.
                return self._send(200, spon_measure(q.get("id") or ""))
            if u.path == "/api/progress":
                j = JOBS.get(q.get("id") or "")
                if not j:
                    return self._send(404, {"state": "gone"})
                return self._send(200, j)
            if u.path == "/api/data":
                d = load_scan(q.get("id") or "")
                # purane scan ka cached cst purane niche formula ka hai — ek baar
                # taaza karke file me wapas likh do, phir har load fast rahega.
                if d and d.get("cst") and d.get("items") and "items_n" not in (d["cst"].get("niche") or {}):
                    try:
                        d["cst"] = chan_stats(d)
                        f = SCN_DIR / (re.sub(r"[^0-9a-f]", "", q.get("id") or "") + ".json")
                        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    except Exception:
                        pass
                return self._send(200, d or {"none": True})
            if u.path == "/api/ideas":
                r = ideas_of(q.get("id") or "", pnum(q.get("k")) or 10)
                return self._send(200, r or {"error": "ye scan nahi mila"})
            if u.path == "/api/idea":
                # ek video ka idea-packet — tags/keywords ASLI hain, ideas model ka andaza
                return self._send(200, idea_pack((q.get("vid") or "").strip(),
                                                (q.get("topic") or "").strip()))
            if u.path == "/api/sharezip":
                # dost ko bhejne layak fresh zip — bina keys, bina history (rules upar share_zip me)
                return self._send(200, share_zip(), "application/zip",
                                  'attachment; filename="ClickLab-share.zip"')
            if u.path == "/api/export":
                r = export_scan(q.get("id") or "", (q.get("fmt") or "csv").lower())
                if not r:
                    return self._send(404, {"error": "ye scan nahi mila"})
                body, ext, ctype = r
                sid = re.sub(r"[^0-9a-f]", "", q.get("id") or "")[:16] or "scan"
                return self._send(200, body, ctype,
                                  'attachment; filename="clicklab_%s.%s"' % (sid, ext))
            if u.path == "/api/del":
                f = SCN_DIR / (re.sub(r"[^0-9a-f]", "", q.get("id") or "") + ".json")
                if f.exists():
                    f.unlink()
                return self._send(200, {"ok": True})
            if u.path == "/api/check":
                return self._send(200, do_check(q.get("ref") or "", q.get("title") or ""))
            if u.path == "/api/meta":
                vid = (q.get("vid") or "").strip()
                m = meta_of(vid)
                if m.get("err"):
                    return self._send(200, {"ok": False, "vid": vid, "error": m["err"]})
                return self._send(200, {"ok": True, "vid": vid, "meta": m,
                                        "seo": seo_check(m.get("title"), m), "eng": eng_of(m),
                                        "own": own_load().get(vid) or {}, "usd": 0})
            if u.path == "/api/own":
                return self._send(200, {"own": own_load()})
            if u.path == "/api/pick":
                # "Is se inspire ho kar naya" ke liye: us video ke title se 2-3 behtar shabd,
                # jo uske thumbnail par pehle se likhe nahi. Sirf title/OCR text se — koi guess nahi.
                return self._send(200, {"words": pick_words(q.get("title") or "", q.get("avoid") or "")})
            if u.path == "/api/variants":
                return self._send(200, {"variants": load_var()})
            if u.path == "/api/variants.csv":
                vs = load_var()
                rows = [["created", "topic", "variant", "title", "thumbnail", "note"]]
                for v in vs:
                    for side in ("A", "B"):
                        t = v.get("t" + side.lower(), "")
                        i = v.get("i" + side.lower(), "")
                        if not t and not i:
                            continue
                        rows.append([v.get("ts", ""), v.get("topic", ""), side, t, i, v.get("note", "")])
                csv = "\n".join(",".join('"' + str(c).replace('"', '""') + '"' for c in r) for r in rows)
                return self._send(200, csv.encode("utf-8"), "text/csv; charset=utf-8")
            if u.path == "/api/tools":
                g = geninfo()
                return self._send(200, {"ytdlp": bool(find_ytdlp()), "tesseract": bool(find_tesseract()),
                                        "pillow": bool(Image), "cv": bool(cv2), "gen": g})
            if u.path == "/api/geninfo":
                return self._send(200, geninfo())
            if u.path == "/api/ai":
                return self._send(200, {"items": load_ai(), "info": rw_info()})
            if u.path == "/img":
                p = Path(q.get("path") or "")
                if not p.exists() or p.suffix.lower() not in MIME:
                    return self._send(404, {"error": "image nahi mili"})
                return self._send(200, p.read_bytes(), MIME[p.suffix.lower()])
        except Exception as e:
            return self._send(500, {"error": repr(e)[:300]})
        self._send(404, {"error": "??"})


def pick_port():
    for i in range(8):
        try:
            s = ThreadingHTTPServer(("127.0.0.1", PORT + i), H)
            return s, PORT + i
        except OSError:
            continue
    return ThreadingHTTPServer(("127.0.0.1", 0), H), None


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClickLab — title + thumbnail, measured</title>
<!-- favicon inline: isliye ke browser /favicon.ico na maange aur console me 404 na aaye.
     Mark: gradient tile + cursor arrow with click burst — ClickLab ka apni nishani. -->
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='%232fd7ff'/><stop offset='1' stop-color='%2300b4e6'/></linearGradient></defs><rect width='32' height='32' rx='8' fill='url(%23g)'/><path d='M9 6l15 9-6.4 1.6L15 24 9 6z' fill='%23fff'/><path d='M22.5 4.5l1-2M26.5 9l2.2-1.1M26 14l2.6-.4' stroke='%23fff' stroke-width='1.6' stroke-linecap='round'/></svg>">
<!-- Typography: Plus Jakarta Sans (display) + Inter (body). Net na ho to system-ui par
     safely gir jaata hai — tool offline bhi wahi chalega, bas font system ka. -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<!-- Font kabhi render-blocking NAHI — network slow ya fonts.googleapis.com band ho
     to bhi page foran ban jaye (neeche system-ui fallback maujood hai). Font aa
     gaya to chupke se lag jaayega; na aaya to tool phir bhi poora chalta hai. -->
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<noscript><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet"></noscript>
<style>
/* RANG / SIZE — ek hi token source. Koi component apna rang/size khud nahi likhta;
   jo purane naam (--card, --br, --grn…) code me already hain wo sab inhi tokens ka alias hain,
   isliye do alag palettes kabhi nahi ban sakti. */
:root{
 /* ClickLab ka apna palette — "Obsidian Kinetic": obsidian canvas, tonal surfaces (E1/E2), aur ek hi signal rang —
    Electric Cyan (#00d2ff). Baaki rang kaam ke hain, decoration ke nahi:
    emerald = behtareen, amber = friction, red = masla, indigo = doosra data
    track. Ye wahi system hai jo design brief (obsidian_kinetic_studio/DESIGN.md)
     me likha hai. Ek hi jagah hai — koi component apna rang khud nahi likhta. */
 --bg:#0f1117;--panel:#1a1d26;--panel2:#222736;--panel3:#2b3143;--line:#2e364b;--line2:#1f2433;
  /* inbg = input ka background (surface se gehra — design brief ka input rule),
     rowbg = table row ka hover. Dono ka ek hi source. */
  --inbg:#141721;--rowbg:#1e2333;
 --tx:#f8fafc;--tx2:#94a3b8;--mut:#8695ab;
 --acc:#00d2ff;--acc2:#7fe6ff;--nic:#3b82f6;--ok:#10b981;--warn:#f59e0b;--bad:#ff6b6b;
 /* accrgb = --acc ka hi rang, channels (rgb) me: heatmap aur series ki shaffafat
    is se banti hai taake rang ka dusra koi source na ho. */
 --accrgb:0,210,255;
 /* --- rang ke baqi roop, ek hi jagah ---
    okrgb/warnrgb/badrgb: har shaffaf (alpha) parat inhi se banti hai, kahin bhi
      raw rgb dobara likhna mana hai.
    acc-hi = accent ka hover step. edge/edge2/mut2 = border aur text ka ooncha
      (elevated) ramp. ink/scrim/scrim-chip/barbg = tasveer ke upar aur upar-patti
      ke peeche ke andhere parde. sh1/sh2/sh2u/sh3 = unchai ka scale.
      fs-* = likhai ki seedhi seedhi (scale) — analysis tool hai, isliye density
      feature hai, numbar chhote-nahi-balki-ghane rakhe gaye hain.
    grad = brand ka gradient (sirf brand tile, primary button, active indicator,
      focus glow me). grad-soft = uska 14% wala fill. glow = primary ka bharson.
      e/e2 = easing curves, d1/d2/d3 = durations — har motion inhi se. */
 --okrgb:16,185,129;--warnrgb:245,158,11;--badrgb:255,107,107;
 --acc-hi:#33ddff;--edge:#3d4a63;--edge2:#4c5c7a;--mut2:#64748b;
 --ink:#002530;--scrim:rgba(5,7,11,.66);--scrim-chip:rgba(5,7,11,.86);--barbg:rgba(11,13,19,.8);
 /* Chaiye ki unchai ka scale — design brief ke "Crisp Glass Tonalities" se:
     E2 par halka ambient + upar ka inner highlight, modal par cyan ka diffuse wash. */
  --sh1:0 1px 2px rgba(0,0,0,.45);--sh2:0 4px 20px -2px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.05);--sh2u:0 -4px 18px rgba(0,0,0,.45);--sh3:0 16px 40px -8px rgba(0,210,255,.08),0 8px 24px rgba(0,0,0,.6);
 /* Radius profile brief se: base components 4px, containers 8px, overlays 12px,
     pills sirf status/score/tag ke liye (shape ka farq saaf rahe). */
  --r0:4px;--rp:999px;
 --fs-micro:9.5px;--fs-label:11px;--fs-dense:12px;--fs-body:13px;--fs-item:14px;
 --fs-sub:15px;--fs-card:16px;--fs-h2:20px;--fs-kpi:26px;--fs-kpi-sm:17px;
 --card2:var(--panel2);--br:var(--line);--grn:var(--ok);--amb:var(--warn);--red:var(--bad);
 --r1:6px;--r2:8px;--r3:12px;
 --grad:linear-gradient(180deg,#2fd7ff,#00b4e6);--grad-soft:linear-gradient(180deg,rgba(0,210,255,.14),rgba(0,180,230,.10));
 --glow:0 0 0 1px rgba(var(--accrgb),.45),0 0 16px rgba(var(--accrgb),.35);
 --e:cubic-bezier(.22,.61,.36,1);--e2:cubic-bezier(.16,1,.3,1);--d1:.16s;--d2:.28s;--d3:.5s;
 --glass:rgba(13,16,23,.82);
 --disp:"Plus Jakarta Sans","Inter",system-ui,sans-serif;--body:"Inter","Segoe UI",system-ui,sans-serif;
  --sh:var(--sh1);--tap:40px;--mono:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.5 var(--body);-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
/* scrollbar bhi theme ka — default white nahi */
::-webkit-scrollbar{width:11px;height:11px}::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--panel3);border-radius:var(--r2);border:3px solid var(--bg)}::-webkit-scrollbar-thumb:hover{background:var(--edge2)}
h1,h2,h3,h4{font-family:var(--disp);letter-spacing:-.025em;font-weight:700}
img{max-width:100%}a{color:var(--acc)}code{font-family:var(--mono);font-size:.92em;background:var(--panel2);padding:1px 5px;border-radius:var(--r1)}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:var(--r0)}
::selection{background:rgba(var(--accrgb),.28)}
layout{display:flex;min-height:100vh}
.app{flex:1;min-width:0}
body.navoff nav{display:none}
#navc,#navo{flex:0 0 auto}
@media(max-width:900px){#navc,#navo{display:none}}
#main .card>p{max-width:110ch}
nav{width:256px;border-right:1px solid var(--line);background:var(--glass);backdrop-filter:blur(16px) saturate(1.3);padding:12px 12px 24px;position:sticky;top:0;height:100vh;overflow:auto;flex-shrink:0}
nav .brand{display:flex;align-items:center;gap:10px;font-family:var(--disp);font-weight:700;font-size:var(--fs-card);letter-spacing:-.01em;padding:6px 10px 14px}
nav .brand .mk{width:28px;height:28px;border-radius:var(--r2);background:var(--grad);display:grid;place-items:center;box-shadow:var(--glow);flex:0 0 28px;transform-style:preserve-3d;transition:transform var(--d2) var(--e2)}
nav .brand small{color:var(--mut);font-weight:500;font-size:var(--fs-label);letter-spacing:.06em;text-transform:uppercase}
nav .grp{color:var(--mut);font-size:var(--fs-label);letter-spacing:.14em;text-transform:uppercase;margin:18px 13px 6px}
/* reference ka nav item: flat rounded row, hover par surface uthna, koi translate nahi */
nav a{display:flex;align-items:center;gap:12px;min-height:40px;padding:10px 12px;border-radius:var(--r2);color:var(--tx2);cursor:pointer;
 font-size:var(--fs-item);font-weight:500;text-decoration:none;border:1px solid transparent;position:relative;
 transition:background var(--d1) var(--e),color var(--d1) var(--e)}
nav a svg{flex:0 0 18px;color:var(--mut)}
nav a:hover{background:var(--panel);color:var(--tx)}
/* chuna hua item: reference ka active state — E2 surface + cyan left rail + cyan text */
nav a.on{background:var(--panel2);color:var(--acc);font-weight:600;border:0;border-radius:0 var(--r2) var(--r2) 0;border-left:2px solid var(--acc);padding-left:14px}
nav a.on svg{color:var(--acc)}
/* sidebar ka channel mini-card (reference ka top block) — asli scan data se bharta hai */
nav .navcard{padding:10px 12px;border-radius:var(--r2);background:var(--panel);border:1px solid rgba(46,54,75,.6);margin:2px 0 6px}
nav .navcard .nm{font-size:var(--fs-item);font-weight:600;color:var(--tx);display:flex;align-items:center;gap:6px;min-width:0}
nav .navcard .nm span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
nav .navcard .mt{color:var(--mut);font-size:var(--fs-label);margin-top:3px;font-variant-numeric:tabular-nums}
nav .navcard .hc{display:inline-flex;align-items:center;gap:6px;margin-top:7px;padding:3px 9px;border-radius:var(--rp);
 background:var(--panel2);border:1px solid rgba(46,54,75,.6);color:var(--mut);font-size:var(--fs-label)}
nav .navcard .hc i{width:6px;height:6px;border-radius:50%;background:var(--acc);box-shadow:0 0 8px var(--acc)}
nav .navfoot{margin-top:22px;padding-top:12px;border-top:1px solid rgba(46,54,75,.6);display:flex;flex-direction:column;gap:2px}
nav .navfoot a{min-height:34px;padding:7px 12px;font-size:var(--fs-dense);color:var(--mut)}
#top{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
 padding:10px 24px;border-bottom:1px solid var(--line);background:var(--barbg);backdrop-filter:blur(16px) saturate(1.3)}
#top .ttl{font-family:var(--disp);font-weight:600;font-size:var(--fs-sub);max-width:44ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#top .sp{flex:1}
/* badi screens par adhi jagah khali chhodna professional nahi lagta — pehle yahan
   1280px ki cap thi. Ab content viewport ke saath barehta hai (1760px tak), aur
   bade screens par grid columns apne aap zyanti bhar jaati hain (auto-fill neeche).
   Text blocks apni chhoti max-width (ch) se phir bhi parhne layak rehte hain. */
main{padding:22px 34px 70px;max-width:2100px;margin:0 auto}
/* Wide screens par panels poori width bhar-te hain; sirf lambi prose (notes) ki
 line-lambai padhne-layak limit par rehti hai — panel nahi, text cap hota hai. */
h2+.sub,.card>.sub{max-width:190ch}
h2{margin:0 0 2px;font-size:var(--fs-h2)}h2 svg{vertical-align:-3px;color:var(--mut)}.sub{color:var(--mut);font-size:var(--fs-dense);margin-bottom:14px}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0}
select,button,input[type=text],input[type=number],textarea,.btn{background:var(--inbg);color:var(--tx);border:1px solid var(--line);border-radius:var(--r2);padding:9px 12px;font-size:var(--fs-body);font-family:inherit}
/* .btn = wahi button jaisa, magar <a> par (link jo kaam kare: YouTube par le jana).
   Do alag dikhne wale controls nahi chahiye the, isliye class se share kiya hai. */
.btn{cursor:pointer;min-height:38px;display:inline-flex;align-items:center;gap:7px;transition:background .14s ease,border-color .14s ease,transform .06s ease;text-decoration:none}
.btn:hover{background:var(--panel3);border-color:var(--edge)}.btn:active{transform:scale(.97)}
.btn svg{flex:0 0 16px}
.btn.sm{padding:4px 10px;font-size:var(--fs-dense);min-height:30px;border-radius:var(--r1)}
input[type=text]{min-width:300px}textarea{min-width:100%;min-height:64px}
input,select,textarea{color-scheme:dark}
/* focus = accent ka ring, halka bharson ke saath — keyboard aur pointer dono ke liye
   ek hi signal (niche :focus-visible ka pure outline rule bhi active hai) */
input[type=text]:focus,textarea:focus,select:focus{border-color:var(--acc);box-shadow:0 0 0 2px rgba(var(--accrgb),.35);outline:none}
button{cursor:pointer;min-height:38px;display:inline-flex;align-items:center;gap:7px;transition:background .14s ease,border-color .14s ease,transform .06s ease}
button:hover{background:var(--panel3);border-color:var(--edge)}button:active{transform:scale(.97)}
button svg{flex:0 0 16px}
input[type=range]{width:190px;accent-color:var(--acc);vertical-align:middle}
/* checkbox/radio bhi brand ke — native control ka rang hi badalta hai */
input[type=checkbox],input[type=radio]{accent-color:var(--acc)}
button.go{background:var(--grad);color:var(--ink);border:0;font-weight:700;min-height:var(--tap);box-shadow:0 4px 18px -6px rgba(var(--accrgb),.55);transition:filter var(--d1) var(--e),transform .08s var(--e),box-shadow var(--d1) var(--e)}
button.go:hover{filter:brightness(1.1) saturate(1.1);transform:translateY(-1px);border:0;box-shadow:var(--glow)}button.go:active{transform:scale(.97)}button.go:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
button.gh{background:transparent}
button.dg{color:var(--bad)}
button.iconbtn{min-width:38px;padding:8px;justify-content:center}
button.sm{padding:4px 10px;font-size:var(--fs-dense);min-height:30px;border-radius:var(--r1)}
button.sm.go{min-height:30px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr));gap:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r2);padding:16px;box-shadow:var(--sh)}
.card h3{margin:0 0 6px;font-size:var(--fs-sub);letter-spacing:-.012em;color:var(--tx);font-weight:500}.card .sub{margin-bottom:6px}
/* Card header: reference ka pattern — icon+title baayein, controls dayein, neeche hairline */
.chd{display:flex;align-items:center;gap:10px;padding-bottom:10px;margin:-2px 0 12px;border-bottom:1px solid rgba(46,54,75,.6)}
.chd svg{color:var(--acc);flex:0 0 20px}
.chd b{font-family:var(--disp);font-weight:600;font-size:var(--fs-sub);letter-spacing:-.01em}
.chd .sp{flex:1}
.chd .pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:var(--rp);font-size:var(--fs-label);font-weight:700;
 background:rgba(0,210,255,.12);color:var(--acc);border:1px solid rgba(0,210,255,.3)}
.chd .pill i{width:6px;height:6px;border-radius:50%;background:currentColor;animation:pls 2s infinite}
@keyframes pls{0%,100%{opacity:1}50%{opacity:.35}}
/* Page-header card: reference ka page-header — title + status + telemetry, upar glow strip */
.ph{position:relative;overflow:hidden;background:var(--panel);border:1px solid rgba(46,54,75,.6);border-radius:var(--r3);
 padding:18px 20px;margin:0 0 16px;box-shadow:0 4px 20px -2px rgba(0,0,0,.45)}
.ph:before{content:"";position:absolute;left:0;right:0;top:0;height:2px;background:linear-gradient(90deg,transparent,var(--acc),transparent);opacity:.7}
.ph h1{margin:0;font-family:var(--disp);font-weight:700;font-size:26px;letter-spacing:-.02em;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ph .sub{margin:6px 0 0;max-width:80ch}
.ph .row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px}
.ph .telem{display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:var(--r2);background:var(--panel2);
 border:1px solid rgba(46,54,75,.6);font-size:var(--fs-label);color:var(--mut)}
.ph .telem b{color:var(--tx);font-family:var(--disp);font-variant-numeric:tabular-nums;font-size:var(--fs-item)}
/* Home dashboard: hero split + performer rows — reference ka a-master pattern, sirf asli data se */
.hsplit{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:14px 0}
.hsplit>*{min-width:0}
@media(max-width:1000px){.hsplit{grid-template-columns:1fr}}
.prow{display:flex;gap:12px;align-items:center;padding:10px;border-radius:var(--r2);background:var(--panel2);
 border:1px solid rgba(46,54,75,.5);transition:border-color var(--d1) var(--e)}
.prow:hover{border-color:rgba(0,210,255,.4)}
.prow img{width:128px;aspect-ratio:16/9;object-fit:cover;border-radius:var(--r1);flex:0 0 128px}
.prow .pm{flex:1;min-width:0}
.prow .pm>b{display:block;font-size:var(--fs-item);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.prow .pm .d{color:var(--mut);font-size:var(--fs-label);margin-top:3px}
.prow .pv{text-align:right;flex:0 0 auto}
.prow .pv b{font-family:var(--disp);font-size:var(--fs-sub);color:var(--acc);font-variant-numeric:tabular-nums}
.prow .pv span{display:block;color:var(--mut);font-size:var(--fs-label)}
.vsbar{height:6px;border-radius:3px;background:var(--panel2);overflow:hidden;margin:10px 0 4px}
.vsbar i{display:block;height:100%;background:var(--grad)}
.mrow{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px;padding-top:10px;border-top:1px solid rgba(46,54,75,.4)}
.mrow>div{background:var(--panel2);border:1px solid rgba(46,54,75,.4);border-radius:var(--r1);padding:8px 10px}
.mrow span{display:block;color:var(--mut);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em}
.mrow b{font-family:var(--disp);font-size:var(--fs-sub);font-variant-numeric:tabular-nums}
.hbig{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:var(--r2);display:block}
/* Outlier radar cards (reference ka top-performer pattern): upar gradient strip,
   status badge, aur teen chhote metric box — sab isi scan ke asli numbers se.
   Track ka max 430px hai (is se bade card blur/pixelated lagte hain) aur cards
   poori width par barabar bikharte hain; .radar>* par min-width:0 grid ke
   auto-minimum ko maarta hai — bina iske kuch browsers me aakhri card screen se
   bahar khinch jaata tha (yehi wo clipping thi jo baar-baar dikhi). */
.radar{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;justify-content:space-evenly;margin:12px 0}
.radar{grid-template-columns:repeat(auto-fit,minmax(230px,min(430px,100%)))}
.radar>*{min-width:0}
.grid>*,.ideas>*,.sk-grid>*,.cmpsum>*,.stdk>*,.mrow>*,.v>*{min-width:0}
.olc{position:relative;background:var(--panel);border:1px solid rgba(46,54,75,.6);border-radius:var(--r3);
 overflow:hidden;cursor:pointer;transition:border-color var(--d1) var(--e),box-shadow var(--d1) var(--e)}
.olc:hover{border-color:rgba(0,210,255,.4);box-shadow:0 0 18px -6px rgba(0,210,255,.25)}
.olc:before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:var(--grad);z-index:2}
.olc img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block}
.olbadge{position:absolute;top:9px;right:9px;z-index:3;font-family:var(--disp);font-size:10.5px;font-weight:700;
 letter-spacing:.08em;padding:4px 9px;border-radius:var(--rp);background:rgba(15,17,23,.78);color:var(--acc);
 border:1px solid rgba(0,210,255,.45);backdrop-filter:blur(6px)}
.olbadge.brk{color:#0F1117;background:var(--acc);border-color:var(--acc)}
.olb{padding:10px 12px 12px}
.olt{font-size:var(--fs-label);font-weight:600;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.olm{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:9px}
.olm>div{background:var(--panel2);border:1px solid rgba(46,54,75,.4);border-radius:var(--r1);padding:6px 7px;min-width:0;overflow-wrap:anywhere}
.olm span{display:block;color:var(--mut);font-size:9.5px;text-transform:uppercase;letter-spacing:.07em}
.olm b{font-family:var(--disp);font-size:var(--fs-label);font-variant-numeric:tabular-nums}
/* KPI tile: reference frame — label upar, bara tabular number, hover par halki cyan edge */
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;margin:12px 0}
.kpi div{background:var(--panel);border:1px solid rgba(46,54,75,.6);border-radius:var(--r3);padding:13px 16px;min-width:0;
 transition:border-color var(--d1) var(--e),box-shadow var(--d1) var(--e)}
.kpi div:hover{border-color:rgba(0,210,255,.35);box-shadow:0 0 16px -4px rgba(0,210,255,.18)}
.kpi .kl{display:block;color:var(--mut);font-size:var(--fs-label);font-weight:600;margin-bottom:5px}
.kpi b{display:block;font-size:var(--fs-kpi);line-height:1.2;color:var(--tx);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.kpi b.g{color:var(--ok)}.kpi b.w{color:var(--warn)}.kpi b.r{color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:var(--fs-body)}
/* chhoti screen par lambi table page ko chaudha nahi karti — table khud andar se sarakta hai */
@media (max-width:760px){table{display:block;max-width:100%;overflow-x:auto}}
th{color:var(--mut);text-align:left;font-weight:400;padding:9px 12px;border-bottom:1px solid var(--line);font-size:var(--fs-dense);letter-spacing:0}
td{padding:10px 12px;border-bottom:1px solid var(--line2);vertical-align:middle}
tr:hover td{background:var(--rowbg)}td a{color:var(--tx2);text-decoration:none}td a:hover{color:var(--acc)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-size:var(--fs-dense)}
.hi{color:var(--grn);font-weight:700}.mid{color:var(--amb)}.lo{color:var(--red)}
.tag{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:var(--rp);padding:3px 9px;font-size:var(--fs-dense);color:var(--acc2);margin:3px 4px 3px 0;cursor:pointer}
.tag:hover{border-color:var(--acc)}.tag .x{color:var(--red);margin-left:6px}
.err{color:var(--red);font-size:var(--fs-body)}.spin{color:var(--mut);font-size:var(--fs-body)}
.pbar{height:8px;background:var(--card2);border-radius:var(--r0);overflow:hidden;margin:8px 0;max-width:460px}.pbar i{display:block;height:100%;background:var(--acc);transition:width .4s}
.sec{font-size:var(--fs-sub);margin:22px 0 6px}.sec small{color:var(--mut);font-weight:400}
.thumb{width:100%;display:block;border-radius:var(--r2);border:1px solid var(--br);cursor:pointer}
.sw{display:inline-block;width:13px;height:13px;border-radius:var(--r0);border:1px solid var(--br);vertical-align:-2px;margin-right:4px}
.v{display:grid;grid-template-columns:190px 1fr 74px;gap:8px;padding:8px 0;border-bottom:1px solid var(--line2);font-size:var(--fs-body)}
.v b.ok{color:var(--grn)}.v b.warn{color:var(--amb)}.v b.bad{color:var(--red)}
.v .n{color:var(--mut);font-size:var(--fs-dense)}
.sizes{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}
.size{background:var(--bg);border:1px solid var(--br);border-radius:var(--r2);padding:8px}
.size .lab{color:var(--mut);font-size:var(--fs-label);margin-bottom:5px}
.size img{display:block;border-radius:var(--r1)}
.yt{background:var(--panel);border:1px solid var(--br);border-radius:var(--r2);padding:10px;display:flex;gap:10px;align-items:flex-start}
.yt img{border-radius:var(--r2);flex-shrink:0}
.yt .t{font:500 15.5px/1.35 Roboto,Segoe UI,Arial,sans-serif;color:var(--tx)}
.yt .m{color:var(--mut);font-size:var(--fs-dense);margin-top:4px}
.yt.mob{max-width:340px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
/* zoom view badi screen par: thumbnail column 44% se zyada na bade (warna adhi
   screen sirf tasveer), baaki jagah analysis poori le — dono columns bhare rehte hain */
.ztwo{grid-template-columns:minmax(360px,min(44%,760px)) minmax(0,1fr)}
@media(max-width:1000px){.two{grid-template-columns:1fr}}
.oword{position:absolute;border:1.5px solid var(--acc);border-radius:var(--r0);pointer-events:none}
.owrap{position:relative;display:inline-block}
.chip{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:var(--rp);padding:3px 8px;font-size:var(--fs-dense);margin:2px 3px 2px 0;line-height:1.45}
.chip b{color:var(--acc)}
.fsteps{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 16px}
.fstep{border:1px solid var(--line);border-radius:var(--rp);padding:5px 11px;font-size:var(--fs-dense);color:var(--mut);background:var(--panel)}
.fstep.on{border-color:var(--acc);color:var(--acc)}
.fstep.dn{cursor:pointer;color:var(--tx2)}
.chip.kwk{cursor:pointer;user-select:none;font-family:inherit}
.chip.kwk.on{border-color:var(--acc);color:var(--tx)}
.trbox{max-height:460px;overflow:auto;white-space:pre-wrap;background:var(--panel2);border:1px solid var(--line);border-radius:var(--r2);padding:10px 12px;font-size:var(--fs-dense);line-height:1.6;margin:6px 0 2px}
.srow{display:flex;align-items:center;gap:8px;margin:6px 0}
.svbar{position:relative;flex:1;min-width:0;min-height:26px;background:var(--panel2);border:1px solid var(--line);border-radius:var(--r1);overflow:hidden}
.svbar i{position:absolute;left:0;top:0;bottom:0;background:rgba(45,212,191,.18)}
.svbar span{position:relative;padding:3px 8px;font-size:var(--fs-dense);display:block}
.styx{width:64px;height:36px;object-fit:cover;border-radius:4px;border:1px solid var(--line);flex:none}
.crow{display:flex;align-items:center;gap:8px;padding:6px 2px;border-bottom:1px solid var(--line);font-size:var(--fs-dense)}
.crk{width:20px;text-align:center;color:var(--mut);font-weight:700;flex:none}
.fbox{position:absolute;border:1.5px solid var(--nic);border-radius:var(--r0);pointer-events:none}
.fbox span{position:absolute;top:-13px;left:0;font-size:var(--fs-micro);color:var(--nic);white-space:nowrap}
.bar2{height:5px;background:var(--card2);border-radius:var(--r0);overflow:hidden;min-width:60px;max-width:120px;display:inline-block;vertical-align:-1px}
.bar2 i{display:block;height:100%;background:var(--acc2)}
.lift{font-weight:800;font-variant-numeric:tabular-nums}
.ck{display:grid;grid-template-columns:16px 1fr;gap:8px;padding:7px 0;border-bottom:1px solid var(--line2);font-size:var(--fs-body)}
.ck i{font-style:normal;font-weight:800}.ck b{color:var(--tx)}.ck .n{color:var(--mut);font-size:var(--fs-dense);margin-top:2px}
pre.desc{white-space:pre-wrap;word-break:break-word;font:12px/1.55 var(--mono);color:var(--tx2);max-height:360px;overflow:auto;margin:0;background:var(--bg);border:1px solid var(--br);border-radius:var(--r2);padding:10px}
.rvs{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
.rvimg{background:var(--bg);border:1px solid var(--br);border-radius:var(--r2);padding:7px}
.rvimg .lab{color:var(--mut);font-size:var(--fs-label);margin-bottom:4px}
.rvimg img{display:block;border-radius:var(--r1)}
.bwrap{position:relative;display:inline-block}
.bwrap img{display:block;border-radius:var(--r2)}
/* score badge = brief ka "neon score badge": dark backdrop + currentColor ka 1px
   edge aur halka glow — rang JS score se aata hai, CSS sirf edge banata hai. */
.badge{position:absolute;right:4px;bottom:4px;background:var(--scrim-chip);color:var(--tx);font-size:var(--fs-dense);border-radius:var(--r0);padding:2px 6px;font-variant-numeric:tabular-nums;border:1px solid currentColor;box-shadow:0 0 10px -3px currentColor}
/* ---- naye components (ideas / comparison / nav) ---- */
.ytbtn{border:1px solid var(--line);background:var(--panel2);color:var(--tx2);text-decoration:none}
.ytbtn:hover{border-color:var(--acc);color:var(--acc)}
.ideas{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(420px,100%),1fr));gap:16px}
.idea{background:var(--panel);border:1px solid var(--line);border-radius:var(--r2);padding:16px;box-shadow:var(--sh);display:flex;flex-direction:column;gap:12px}
.idea .rank{display:flex;align-items:center;gap:10px}
.idea .rank i{font-style:normal;width:30px;height:30px;border-radius:50%;background:rgba(var(--accrgb),.12);border:1px solid rgba(var(--accrgb),.35);display:inline-flex;align-items:center;justify-content:center;font-weight:800;color:var(--acc2);font-variant-numeric:tabular-nums;flex:0 0 30px}
.idea h4{margin:0;font-size:var(--fs-card);letter-spacing:-.01em;line-height:1.35}
.idea .why{background:var(--bg);border-left:2px solid var(--acc2);border-radius:0 var(--r1) var(--r1) 0;padding:8px 11px;color:var(--tx2);font-size:var(--fs-dense)}
.sug{border:1px solid var(--line);border-radius:var(--r2);padding:9px 11px;margin:6px 0;background:var(--panel2);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.sug .t{font-weight:600;flex:1;min-width:220px;word-break:break-word}
.sug .n{color:var(--mut);font-size:var(--fs-dense);font-variant-numeric:tabular-nums}
.lbl{color:var(--mut);font-size:var(--fs-label);letter-spacing:.08em;text-transform:uppercase;margin:10px 0 4px}
.skel{background:linear-gradient(100deg,var(--panel2) 25%,var(--panel3) 50%,var(--panel2) 75%);background-size:220% 100%;animation:sh 1.3s linear infinite;border-radius:var(--r2)}
@keyframes sh{0%{background-position:120% 0}100%{background-position:-120% 0}}
.sb{position:absolute;left:6px;top:6px;background:var(--scrim-chip);border:0;border-radius:var(--r0);padding:2px 6px;font-size:var(--fs-label);font-weight:500;font-variant-numeric:tabular-nums}
.cmp2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:820px){.cmp2{grid-template-columns:1fr}}
details{border:1px solid var(--line);border-radius:var(--r2);background:var(--inbg);padding:0}
details>summary{cursor:pointer;padding:9px 12px;font-size:var(--fs-dense);color:var(--tx2);list-style:none;display:flex;align-items:center;gap:8px}
details>summary::-webkit-details-marker{display:none}
details>summary:before{content:"▸";color:var(--mut)}details[open]>summary:before{content:"▾"}
details>div{padding:0 12px 12px}
@media(max-width:900px){.stt thead th{position:static}.stv{min-width:0;gap:10px}.sth{width:118px;flex:0 0 118px}.stdet{padding:12px}}
 @media(max-width:900px){layout{flex-direction:column}nav{width:auto;height:auto;position:static;border-right:0;border-bottom:1px solid var(--line);padding:10px 12px}
 nav a{min-height:44px}nav .grp{margin:10px 0 4px}main,#top{padding-left:14px;padding-right:14px}
 /* inline min-width form fields ko phone se bada karke page overflow karwa deta hai */
 input[type=text]{min-width:0!important;width:100%}select{min-width:0!important;max-width:100%}
 button{min-height:var(--tap)}button.sm{min-height:36px}}
/* ============ Studio jaisa Content table (videos ki listing) ============
   YouTube Studio ke "Content" table jaisa: thumbnail + duration badge, neeche title aur
   grey meta line, daae taraf tabular numbers, header par click karke sort, upar type/sort/
   search ke chips, aur row par click se usi row ke neeche detail. Channel aur topic — dono
   ki listing isi ek component se banti hai (do alag dikhne wale tables nahi). */
/* overflow:hidden sticky column-head ko maar daalta hai, isliye corner khud round kiye */
.st{border:1px solid var(--line);border-radius:var(--r2);background:var(--panel);margin:14px 0}
.st-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 14px;border-bottom:1px solid var(--line);background:var(--panel);border-radius:var(--r2) var(--r2) 0 0}
.st-bar .sp{flex:1}
.st-bar .cnt{color:var(--mut);font-size:var(--fs-dense)}
.stq{background:var(--inbg);border:1px solid var(--line);border-radius:var(--rp);padding:8px 14px;font-size:var(--fs-body);min-width:190px}
.stq:focus{border-color:var(--acc);box-shadow:0 0 0 2px rgba(var(--accrgb),.35);outline:0}
/* Studio ka segmented control: chuna hua hissa cyan-tinted pill (brief ka tab style) */
.seg{display:inline-flex;border:1px solid var(--line);border-radius:var(--rp);overflow:hidden;background:var(--inbg)}
.seg button{background:transparent;border:0;border-radius:0;padding:7px 15px;font-size:var(--fs-dense);color:var(--tx2);min-height:34px}
.seg button:hover{background:var(--panel3);color:var(--tx)}
.seg button.on{background:rgba(var(--accrgb),.16);color:var(--acc2);font-weight:600;box-shadow:inset 0 0 0 1px rgba(var(--accrgb),.45)}
.pill{display:inline-flex;align-items:center;gap:7px;background:transparent;border:1px solid var(--line);border-radius:var(--rp);padding:7px 13px;font-size:var(--fs-dense);color:var(--tx2);min-height:34px}
.pill:hover{border-color:var(--edge2);color:var(--tx)}
.pill i{font-style:normal;color:var(--mut);font-size:var(--fs-label)}
table.stt{width:100%;border-collapse:collapse}
.stt thead th{position:sticky;top:57px;z-index:6;background:var(--panel);border-bottom:1px solid var(--line);
 padding:9px 11px;font-size:var(--fs-dense);color:var(--mut);font-weight:400;text-align:right;white-space:nowrap;cursor:pointer;user-select:none;transition:color .12s ease}
.stt thead th.l{text-align:left}
.stt thead th.no{cursor:default}
/* Bulk-select (reference ka video-library pattern): checkbox, chuni row par cyan rail,
   aur neeche fixed drawer jisme chuninda videos ke asli actions hain */
.stt input[type=checkbox]{width:15px;height:15px;accent-color:var(--acc);cursor:pointer;vertical-align:middle}
.stt tbody tr.sel{box-shadow:inset 2px 0 0 var(--acc)}
.selbar{position:fixed;left:258px;right:0;bottom:0;z-index:40;display:flex;align-items:center;gap:10px;flex-wrap:wrap;
 padding:12px 20px;background:var(--panel2);border-top:1px solid rgba(0,210,255,.35);box-shadow:0 -10px 30px rgba(0,0,0,.5)}
.selbar b{font-family:var(--disp);font-size:var(--fs-item)}
.selbar .mut{color:var(--mut);font-size:var(--fs-label)}
@media(max-width:900px){.selbar{left:0;padding:10px 14px}}
/* Drawer ke peeche aakhri row na chhupe — drawer dikhe tab neeche jagah chhodo */
body:has(#selbar) main{padding-bottom:78px}
.stt thead th:hover{color:var(--tx)}
.stt thead th.sorted{color:var(--tx)}
.stt thead th.sorted:after{content:"\25BE";margin-left:6px;font-size:var(--fs-label);color:var(--acc)}
.stt thead th.sorted.up:after{content:"\25B4"}
.stt tbody tr.srow{cursor:pointer;transition:background .1s ease}
/* row hover = brief ka rule: gehra rowbg + 2px cyan left border (inset shadow) */
.stt tbody tr.srow:hover td{background:var(--rowbg);box-shadow:inset 2px 0 0 var(--acc)}
.stt tbody tr.srow.open td{background:var(--panel2);border-bottom-color:transparent}
.stt td{padding:10px 11px;border-bottom:1px solid var(--line2);vertical-align:middle;text-align:right;
 font-variant-numeric:tabular-nums;font-size:var(--fs-body);white-space:nowrap}
.stt td.l{text-align:left;white-space:normal}
.stt td b{font-weight:500}
.stt td .d{display:block;color:var(--mut);font-size:var(--fs-label);font-weight:400;margin-top:3px}
.stv{display:flex;gap:12px;align-items:flex-start;min-width:225px}
.sth{position:relative;width:140px;flex:0 0 140px}
.sth img{width:100%;display:block;border-radius:var(--r2);border:1px solid var(--line);background:var(--ink)}
.sth .dur{position:absolute;right:4px;bottom:4px;background:var(--scrim-chip);color:var(--tx);font-size:var(--fs-label);
 font-weight:500;border-radius:var(--r0);padding:2px 5px}
.sth .sh{position:absolute;left:5px;top:5px;background:var(--scrim-chip);color:var(--tx);font-size:var(--fs-label);font-weight:700;
 border-radius:var(--r0);padding:2px 6px}
.sti{min-width:0;padding-top:2px}
.sti .t{font-size:var(--fs-item);font-weight:500;line-height:1.35;color:var(--tx);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.sti .m{color:var(--mut);font-size:var(--fs-dense);margin-top:5px;line-height:1.55}
.sti .m .sep{opacity:.5;padding:0 4px}
.stt tr.std td{padding:0;white-space:normal;text-align:left;border-bottom:1px solid var(--line2);background:var(--bg)}
.stdet{padding:16px;display:grid;grid-template-columns:minmax(300px,400px) minmax(0,1fr);gap:18px}
.stdet>div{min-width:0}
/* chips ko wrap karne ke liye — bina iske ek lambi na-tootne wali line ban jati hai */
.tagrow{display:flex;flex-wrap:wrap;gap:6px}
@media(max-width:1000px){.stdet{grid-template-columns:1fr}}
.stdk{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:8px;margin-bottom:12px}
.stdk div{background:var(--panel);border:1px solid var(--line);border-radius:var(--r2);padding:8px 10px}
.stdk b{display:block;font-size:var(--fs-sub);font-weight:500;color:var(--tx)}
.stdk span{color:var(--mut);font-size:var(--fs-label)}
.stempty{padding:30px;text-align:center;color:var(--mut);font-size:var(--fs-body)}
.stft{padding:9px 14px;color:var(--mut);font-size:var(--fs-dense);border-top:1px solid var(--line);background:var(--panel);border-radius:0 0 var(--r3) var(--r3)}
/* page by page — Studio jaisa. Sirf dikhne ka farq, ginti poori listing par. */
.stpg{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 14px;background:var(--panel2);border-top:1px solid var(--line)}
.stpg .pgi{color:var(--mut);font-size:var(--fs-dense)}.stpg .pgi b{color:var(--tx)}
.stpg button[disabled]{opacity:.35;cursor:default}
.smx{margin-top:4px}.smx .lbl:first-child{margin-top:0}.smx table{margin-top:6px}
.smx .chip b{color:var(--tx);font-weight:600}
/* Upload-ka-waqt ka panel: Studio ke upar baithta hai, is liye us se halka surface. */
.tp{border:1px solid var(--line);border-radius:var(--r2);background:var(--panel2);padding:12px 14px;margin:0 0 12px}
.tp .kpi{margin:10px 0 4px;grid-template-columns:repeat(auto-fit,minmax(120px,1fr))}.tp .kpi div{padding:9px 12px}
.tp .kpi b{font-size:var(--fs-kpi-sm)}
.tp .hm{display:grid;grid-template-columns:74px repeat(24,minmax(0,1fr));gap:2px;margin-top:6px}
.tp .hm b{font-size:var(--fs-label);color:var(--mut);font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:1px 0}
.tp .hm u{text-decoration:none;font-size:var(--fs-micro);color:var(--mut);text-align:center;font-variant-numeric:tabular-nums}
/* cell = asli <button>: keyboard se bhi chun sake. Global button style (38px uncha,
   padding, gap) in chhote cells ke liye yahan wapas theek kiya gaya hai. */
.tp .hm button.hc{min-height:0;padding:0;border:0;border-radius:var(--r0);display:block;position:relative;
 aspect-ratio:1/1;min-width:0;gap:0}
.tp .hm button.hc:hover{outline:1px solid var(--tx);outline-offset:1px}
.tp .hm button.hc.on{outline:2px solid var(--tx);outline-offset:1px}
.tp .hm button.hc span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
 font-size:var(--fs-micro);color:var(--tx);font-variant-numeric:tabular-nums;pointer-events:none}
.tp .wk{display:flex;gap:2px;align-items:flex-end;height:54px;margin-top:6px}
.tp .wk i{flex:1;min-width:2px;background:rgba(var(--accrgb),.55);border-radius:var(--r0) var(--r0) 0 0}
.tp .wk i:hover{background:var(--acc)}
.tp .tpon{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px;color:var(--acc);font-size:var(--fs-dense)}
.tp .tpact{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px}
@media (max-width:760px){.tp .hm{grid-template-columns:56px repeat(24,minmax(0,1fr))}.tp .hm b{font-size:var(--fs-micro)}}
/* bina-naap rows aur un par naap chalane ki patti — Table ka hisaab saaf rahe */
.stact{display:flex;gap:10px;align-items:flex-start;padding:10px 14px;background:var(--panel2);border-bottom:1px solid var(--line);font-size:var(--fs-body);color:var(--mut)}
.stact b{color:var(--tx)}.stact svg{flex:0 0 auto;margin-top:2px;color:var(--acc)}
.stact button.sm{margin:2px 0 0 4px}.stact .pbar{max-width:460px}
/* deep analysis ki wo rows jin par click ka kaam hai — hover aur cursor wahi batate
   hain ke line clickable hai. */
.stt tr[onclick]{cursor:pointer}.stt tr[onclick]:hover{background:var(--panel3)}
.stt tr.un td{color:var(--mut)}.stt tr.un .t{color:var(--mut);font-weight:400}
.stt tr.un:hover td{background:var(--panel2)}.stt tr.un .sth img{opacity:.7;filter:saturate(.8)}
.stt .nb{white-space:nowrap;font-size:var(--fs-dense);padding:5px 9px}
/* Tulna: 10 channels ke saath table chaudha hota hai — channel ka naam chipka rehta hai
   aur scroll sirf table ke andar hota hai, page ka kinara kabhi nahi chhu-ta. */
.stt th.stk,.stt td.stk{position:sticky;left:0;z-index:5;background:var(--panel);text-align:left;
 min-width:178px;max-width:230px;white-space:normal;border-right:1px solid var(--line)}
.stt thead th.stk{z-index:8;background:var(--panel2)}
.stt tbody tr:hover td.stk{background:var(--panel2)}
/* scroller khud box hota hai: table jitna bhi chaudha ho, page ka kinara nahi chhu-ta;
   columns andar sarakte hain aur channel ka naam left par tikta rehta hai */
.stscr{overflow-x:auto;overscroll-behavior-x:contain}
.stscr table.stt{width:max-content;min-width:100%}
.stscr .stt th.no,.stscr .stt td:not(.stk){min-width:88px;padding:8px;font-size:var(--fs-dense)}
/* scroller ke andar header upar chipakne ki koshish gap khol deti hai (scroll container
   khud scroll nahi karta) — yahan sirf left/pehla column chipkta hai, header normal. */
.stscr .stt thead th:not(.stk){position:static}
/* header ka pehla cell sirf left par chipke, upar ki sticky offset scroller ke andar
   pehli data line ke naam ke oopar aa jaati hai */
.stscr .stt thead th.stk{top:auto}
.stscr .stt .mb{width:52px}
/* mobile: Maap table ka pehla column tang, aur "matlab" wali doosri line chhupi
   rehti hai — line par tap karne par khulti hai. Table safe hai (scroll andar),
   bas width ka sahi hissa mile. */
.mmh{display:none}
@media(max-width:560px){.stt th.stk,.stt td.stk{min-width:132px;max-width:158px}
.stt .mm{display:none}.stt tr.mx .mm{display:block}
#cmbox .stt td.l.stk{cursor:pointer}.mmh{display:inline}}
/* cell ke andar chhota bar (Studio apne metric cards me aisa hi bar dikhata hai) */
.mb{display:inline-block;height:4px;width:56px;background:var(--panel3);border-radius:var(--r0);overflow:hidden;vertical-align:2px;margin-left:9px}
.mb i{display:block;height:100%;background:var(--acc)}
/* tulna me haara hua number halki bar ke saath — jeeta neeli */
.mb i.q{background:var(--mut)}
/* channel ka naam tulna ke header me */
.stt thead th .m{color:var(--mut);font-size:var(--fs-label);font-weight:400;margin-top:4px;line-height:1.5}
.stt thead th a.chl{color:var(--tx);font-weight:500;text-decoration:none}
.stt thead th a.chl:hover{text-decoration:underline}
.tagme{display:inline-block;background:var(--acc);color:var(--bg);font-size:var(--fs-label);font-weight:700;
 border-radius:var(--r0);padding:2px 6px;margin-right:7px;vertical-align:2px}
/* channel chunne ke goli-akaar button (checkbox hi chalta hai, bas dikhta badal jaata hai) */
.pk{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--inbg);
 border-radius:var(--rp);padding:8px 13px;font-size:var(--fs-body);cursor:pointer;min-height:38px;transition:background .16s,border-color .16s,color .16s}
.pk:hover{background:var(--panel3)}
.pk:has(input:checked){background:rgba(var(--accrgb),.14);border-color:var(--acc);color:var(--tx)}
.pk:has(input:checked) span{color:var(--mut2)}
.pk input{accent-color:var(--acc);width:15px;height:15px}
.pk b{font-weight:500}
.pk span{color:var(--mut);font-size:var(--fs-dense)}
.pk:active{transform:scale(.97)}
/* Channel comparison ka Studio-jaisa vistaar: summary strip, verdict, charts.
   Naya component nahi — wahi panel/line/tokens ka parivaar. */
.cmpsum{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));gap:10px;margin:12px 0}
.cmpc{border:1px solid var(--line);border-top-width:2px;border-radius:var(--rp);padding:10px 12px;background:var(--panel)}
/* Timing & pattern tab: heat cards aur common-words chips — sab existing tokens par */
.hmcard{border:1px solid var(--line2);border-radius:var(--r0);padding:8px 10px;margin-top:10px}
.hmcard h4{margin:0 0 2px;font-size:var(--fs-sub);display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.cwch{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.cwch>span{border:1px solid var(--line);border-radius:var(--r0);padding:3px 8px;font-size:var(--fs-dense);background:var(--panel)}
.cwch i{font-style:normal;font-weight:600}
.vsr{padding:8px 0;border-bottom:1px solid var(--line2)}
.vsr:last-child{border-bottom:0}
.vsr .vl{font-size:var(--fs-sub);font-weight:600}
.vsr .vl .vm{color:var(--mut);font-weight:400;font-size:var(--fs-label)}
.vbar{display:flex;align-items:center;gap:8px;margin-top:5px}
.vbar .vn{flex:none;width:150px;color:var(--mut);font-size:var(--fs-label);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vbar .vt{flex:1;height:10px;background:var(--panel3);border-radius:3px;position:relative;overflow:hidden}
.vbar .vt i{position:absolute;left:0;top:0;height:100%;border-radius:3px}
.vbar .vv{flex:none;min-width:74px;text-align:right;font-weight:600;font-size:var(--fs-dense)}
.vcap{color:var(--mut);font-size:var(--fs-label);margin:3px 0 0 112px}
@media(max-width:520px){.vcap{margin-left:0}.vbar .vn{width:84px}}
.stt tr.sec td{background:var(--panel2);text-align:left;font-weight:600;font-size:var(--fs-sub);padding:7px 11px}
.cmpc h4{margin:0 0 8px;font-size:var(--fs-sub);display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.cdot{display:inline-block;width:9px;height:9px;border-radius:50%;flex:none}
/* Channel ka naam heading jaisi tight letter-spacing me sikud jaata hai —
   do-word naam "TechBurner" jaisa padha jaata hai. Naam par normal spacing
   aur thoda word-spacing: ye sirf channel-naam ke liye, heading ke liye nahi. */
.cnm{min-width:0;overflow-wrap:anywhere;letter-spacing:0;word-spacing:.12em}
.cmpc .kv{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:var(--fs-dense);padding:4px 0;border-top:1px solid var(--line2)}
.cmpc .kv b{font-variant-numeric:tabular-nums;text-align:right}
.dchip{font-size:10.5px;font-weight:600;padding:1px 5px;border-radius:var(--r0);margin-left:6px;white-space:nowrap}
.dchip.u{color:var(--ok);background:rgba(16,185,129,.13)}
.dchip.d{color:var(--bad);background:rgba(255,107,107,.13)}
.dchip.n{color:var(--mut);background:rgba(134,149,171,.12)}
.vfind{display:flex;gap:9px;align-items:flex-start;padding:8px 0;border-top:1px solid var(--line2);font-size:var(--fs-body)}
.vfind .dot{flex:none;width:8px;height:8px;border-radius:50%;margin-top:7px}
.vfind .sp{flex:1;min-width:8px}
.vfind button{flex:none;margin-left:8px}
.ovg{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}
@media(max-width:1080px){.ovg{grid-template-columns:1fr}}
.chm{width:100%;height:auto;display:block;margin-top:8px}
.chm .grid{stroke:var(--line2);fill:none}
.chm .axl{fill:var(--mut);font-size:10px}
.lgd{display:flex;flex-wrap:wrap;gap:10px;font-size:var(--fs-dense);color:var(--tx2);margin-top:8px}
.lgd i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
/* sirf icon wala button — row ke andar bar jagah na ghase */
.stt td button.ic{padding:7px 9px;min-height:0;line-height:1}
/* Baaki tabs ke sade tables bhi usi Studio family me aa jayein — naya component nahi,
   sirf wahi hover/header wala behaviour jo .stt me hai. .std (row ke neeche ka detail)
   ko hover se bahar rakha hai warna khud par highlight ban jata. */
tbody tr:not(.std):hover td{background:var(--rowbg);box-shadow:inset 2px 0 0 var(--acc)}
td.win{position:relative;background:rgba(var(--accrgb),.07)}
/* ---------- toast: ek jagah, upar chadh kar, type ke rang token se ---------- */
/* Pehle toast khud-ba-khud inline style likhta tha aur doosra aane par pichhla hata
   deta tha — do message ek saath dikhne chahiye (ek fail + ek bachat), isliye stack. */
#tst{position:fixed;right:16px;bottom:16px;z-index:80;display:flex;flex-direction:column-reverse;gap:8px;max-width:min(420px,calc(100vw - 32px))}
.tst{display:flex;gap:10px;align-items:flex-start;background:var(--panel2);border:1px solid var(--line);
 border-left:3px solid var(--mut);border-radius:var(--r2);padding:10px 12px;box-shadow:var(--sh2);
 font-size:var(--fs-body);color:var(--tx);cursor:pointer;animation:tin .18s ease-out}
.tst svg{flex:0 0 16px;margin-top:1px}
.tst.ok{border-left-color:var(--ok)}.tst.ok svg{color:var(--ok)}
.tst.warn{border-left-color:var(--warn)}.tst.warn svg{color:var(--warn)}
.tst.bad{border-left-color:var(--bad)}.tst.bad svg{color:var(--bad)}
.tst.info svg{color:var(--acc)}
.tst b{display:block;font-weight:500;margin-bottom:2px}
.tst .x{margin-left:auto;color:var(--mut);flex:0 0 auto}
@keyframes tin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
/* ---------- skeleton: loading par khali "…" nahi, wahi shape jo aage bharne wala hai ---------- */
/* .skel pehle se defined tha magar kahin istemal nahi ho raha tha — page load par
   content aate hi koodta tha (layout shift). Ab har bhaari view pehle ye dikhata hai. */
.sk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr));gap:16px}
.sk-card{border:1px solid var(--line);border-radius:var(--r2);padding:12px;background:var(--panel)}
.sk-th,.sk-ln,.sk-row{display:block}
.sk-th{width:100%;aspect-ratio:16/9;border-radius:var(--r2)}
.sk-ln{height:11px;border-radius:var(--r0);margin:9px 0}
.sk-row{height:38px;border-radius:var(--r2);margin:7px 0}
.sk-kpi{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}
.sk-kpi i{display:block;width:132px;height:62px;border-radius:var(--r2)}
/* ---------- command palette (Ctrl+K): 12 views + saare scans ek jagah ---------- */
.ov{position:fixed;inset:0;z-index:90;background:var(--scrim);display:flex;
 align-items:flex-start;justify-content:center;padding:11vh 16px 16px}
.pal{width:min(620px,100%);background:var(--panel);border:1px solid var(--line);border-radius:var(--r3);
 box-shadow:var(--sh3);overflow:hidden}
.pal.wide{width:min(880px,100%)}
.pal input{width:100%;border:0;border-bottom:1px solid var(--line);background:var(--panel);
 padding:15px 16px;font-size:var(--fs-sub);border-radius:0}
.pal input:focus{outline:0}
.pal-list{max-height:56vh;overflow:auto;padding:6px 0}
.pal-g{color:var(--mut);font-size:var(--fs-label);letter-spacing:.14em;text-transform:uppercase;padding:9px 16px 4px}
.pal-i{display:flex;gap:11px;align-items:center;padding:9px 16px;cursor:pointer;font-size:var(--fs-item);min-height:40px}
.pal-i svg{flex:0 0 16px;color:var(--mut)}
.pal-i i{color:var(--mut);font-size:var(--fs-dense);font-style:normal;margin-left:auto;font-family:var(--mono)}
.pal-i.sel{background:var(--panel3)}
.pal-i.sel svg{color:var(--acc)}
.pal-ft{border-top:1px solid var(--line);padding:8px 16px;color:var(--mut);font-size:var(--fs-label);display:flex;gap:14px}
kbd{font-family:var(--mono);font-size:var(--fs-label);background:var(--panel2);border:1px solid var(--line);
 border-bottom-width:2px;border-radius:var(--r0);padding:1px 5px;color:var(--tx2)}
/* ---------- khali haal: sirf line nahi, agla qadam button ke saath ---------- */
.es{border:1px dashed var(--line);border-radius:var(--r2);padding:26px;text-align:center;background:var(--panel)}
.es svg{color:var(--mut)}
.es h3{margin:10px 0 4px;font-size:var(--fs-card);font-weight:500}
.es p{color:var(--mut);font-size:var(--fs-body);max-width:56ch;margin:0 auto 14px}
/* ---------- card par masle (verdicts) aur score ka hisaab ---------- */
.iss{margin:8px 0 0;border-top:1px solid var(--line2);padding-top:8px}
.iss-h{display:flex;gap:8px;align-items:center;font-size:var(--fs-dense);color:var(--mut);cursor:pointer;min-height:28px;
 width:100%;background:none;border:0;padding:0;text-align:left;font-family:inherit}
.iss-h:hover{color:var(--tx2)}
.iss-h svg{flex:0 0 14px}
.iss-n{display:flex;gap:6px;align-items:flex-start;font-size:var(--fs-dense);padding:5px 0;line-height:1.4}
.iss-n svg{flex:0 0 14px;margin-top:1px}
.iss-n.warn svg{color:var(--warn)}.iss-n.bad svg{color:var(--bad)}.iss-n.ok svg{color:var(--ok)}
.iss-n b{font-weight:500;color:var(--tx2)}
.iss-n span{color:var(--mut)}
.iss-more{color:var(--acc);font-size:var(--fs-dense);cursor:pointer;display:inline-block;margin-top:4px;min-height:0;
 background:none;border:0;padding:0;font-family:inherit;text-align:left;text-decoration:underline}
/* row par triage: kitne masle hain — rang se turant pata chalta hai */
.ipill{display:inline-block;margin-top:5px;font-size:var(--fs-label);padding:1px 7px;border-radius:var(--rp);
 border:1px solid var(--line);color:var(--mut);white-space:nowrap}
.ipill.warn{color:var(--amb);border-color:rgba(var(--warnrgb),.35);background:rgba(var(--warnrgb),.08)}
.ipill.bad{color:var(--bad);border-color:rgba(var(--badrgb),.35);background:rgba(var(--badrgb),.08)}
.ipill.ok{color:var(--ok);border-color:rgba(var(--okrgb),.3);background:rgba(var(--okrgb),.07)}
/* score kaise bana: har feature ka value × wazan = kitne number */
.why-t{width:100%;border-collapse:collapse;font-size:var(--fs-dense)}
.why-t th{padding:6px 8px;font-size:var(--fs-label)}
.why-t td{padding:5px 8px;border-bottom:1px solid var(--line2)}
.why-bar{display:inline-block;height:5px;width:70px;background:var(--panel3);border-radius:var(--r0);overflow:hidden;vertical-align:2px;margin-left:7px}
.why-bar i{display:block;height:100%;background:var(--acc)}
.why-sum{display:flex;gap:16px;flex-wrap:wrap;color:var(--mut);font-size:var(--fs-dense);margin-top:8px}
.why-sum b{color:var(--tx2);font-family:var(--mono)}
/* ---------- chuni hui cheezon par bulk kaam ---------- */
.selbar{position:sticky;bottom:0;z-index:25;display:flex;gap:10px;align-items:center;flex-wrap:wrap;
 background:var(--panel2);border:1px solid var(--line);border-radius:var(--r2);padding:9px 13px;margin:10px 0;
 box-shadow:var(--sh2u)}
.selbar b{font-weight:600}
.selbar .sp{flex:1}
.card.sel{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
.stt tr.pick td{background:rgba(var(--accrgb),.09)}
.stt tr.cur td{outline:1px solid var(--acc);outline-offset:-1px}
/* ---------- keyboard / screen reader ---------- */
/* score ka number khud clickable hai — Studio me number par click se detail khulti hai */
.badge.bb{border:1px solid currentColor;padding:2px 6px;min-height:0;display:inline-flex;align-items:center;font-family:inherit}
.badge.bb:hover{background:var(--ink);text-decoration:underline}
.ttl .sep{opacity:.5}
/* baaki naap: chhupa kuch nahi, bas tarteeb — native details hi keyboard se chalta hai */
details.kdet{margin:2px 0 10px}
details.kdet>summary{cursor:pointer;color:var(--mut);font-size:var(--fs-dense);min-height:28px;
 display:inline-flex;gap:6px;align-items:center;list-style:none}
details.kdet>summary::-webkit-details-marker{display:none}
details.kdet>summary:hover,details.kdet[open]>summary{color:var(--tx2)}
.skip{position:absolute;left:-9999px;top:0;z-index:95;background:var(--acc);color:var(--bg);
 padding:9px 14px;border-radius:0 0 var(--r2) 0;font-weight:600}
.skip:focus{left:0}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.kb{display:inline-flex;gap:4px;align-items:center;color:var(--mut);font-size:var(--fs-dense)}
/* ================================================================
   PREMIUM LAYER — "Obsidian Kinetic" ka motion aur depth. Sab kuch ek hi
   jagah: background light, page entry, scroll reveal, card lift,
   modal entrance. Har motion --e/--e2/--d* se chalta hai, aur
   prefers-reduced-motion (neeche) sab ko bujha deta hai.
   ================================================================ */
/* Page ke peeche fixed light — ab flat obsidian canvas + upar se halka cyan wash
   (brief: "razor-sharp, minimal reflection"). Ghoomte hue blobs is style me
   nahi chhode. Pointer events khatam. */
.aur{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none}
.aur:before{content:"";position:absolute;inset:0;
 background:linear-gradient(180deg,rgba(0,210,255,.05),transparent 24%),radial-gradient(1100px 480px at 50% -12%,rgba(0,210,255,.07),transparent 70%)}
/* Page entry: main ke direct children ek-ek karke uthte hain (stagger). Sirf
   opacity+translate — GPU-safe, CLS nahi. Har view switch par ye dobara chalta
   hai kyunke naye nodes hote hain. */
main>*{animation:rise .5s var(--e2) both}
main>*:nth-child(2){animation-delay:.05s}main>*:nth-child(3){animation-delay:.1s}
main>*:nth-child(4){animation-delay:.15s}main>*:nth-child(5){animation-delay:.2s}
main>*:nth-child(6){animation-delay:.25s}main>*:nth-child(n+7){animation-delay:.3s}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
/* Grid ke andar ke cards aspas aate hi uthte hain (scroll reveal). JS .rv lagata
   hai, IntersectionObserver .in — JS na chale to kuch chhupa nahi, sab normal. */
.rv{opacity:0;transform:translateY(14px)}
.rv.in{opacity:1;transform:none;transition:opacity .5s var(--e2),transform .5s var(--e2)}
/* Cards par sirf border/glow ka transition — lift nahi (brief: emissive hover) */
.card,.idea{transition:border-color var(--d2) var(--e),box-shadow var(--d2) var(--e)}
/* Cards: lift nahi — brief ka "emissive hover": upar ka kinara cyan aur soft glow. */
.card:hover,.idea:hover{border-color:rgba(var(--accrgb),.4);box-shadow:0 0 16px rgba(0,210,255,.12),var(--sh1)}
/* KPI numbers: Plus Jakarta ka data-metric roop (brief: 700 weight, tight spacing) */
.kpi b{font-family:var(--disp);font-weight:700}
.kpi>div{transition:border-color var(--d2) var(--e),box-shadow var(--d2) var(--e)}
.kpi>div:hover{border-color:rgba(var(--accrgb),.35);box-shadow:0 0 12px rgba(0,210,255,.10)}
/* Progress bar brand gradient se — page score ka visual signal */
.pbar i{background:var(--grad)}
/* Empty state: pehli baar kholne wala screen — is par hi bahar walon ki pehli
   nazar padti hai. Icon ke peeche gradient ka halo, heading display font me. */
.es{position:relative;overflow:hidden}
.es:before{content:"";position:absolute;left:50%;top:-140px;width:460px;height:300px;transform:translateX(-50%);
 background:radial-gradient(closest-side,rgba(var(--accrgb),.14),transparent);pointer-events:none}
.es h3{font-size:22px;letter-spacing:-.02em}
.es svg{color:var(--acc2)}
/* Command palette / modal: halka sa upar se aana + backdrop fade */
.pal{animation:pin .22s var(--e2) both}
.ov{animation:ofade .2s ease both}
@keyframes pin{from{opacity:0;transform:translateY(-10px) scale(.985)}to{opacity:1;transform:none}}
@keyframes ofade{from{opacity:0}to{opacity:1}}
/* Details/summary ka marker brand ho jaye */
details>summary:before{color:var(--acc2)}
/* Table header sort: chune hue column ka indicator brand se */
/* sort indicator brand accent me — upar wale :after ka hi override, cascade se jeetta hai */
.stt thead th.sorted:after{color:var(--acc2)}
/* Toast side se fisle kar aata hai */
@keyframes tin{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
</style></head><body>
<!-- background light: halka static cyan wash (CSS .aur) — decorative, screen-reader ke liye chhupa -->
<div class="aur" aria-hidden="true"></div>
<!-- keyboard user ke liye: seedha content par, 12 nav links tab tak chhoo kar na guzare -->
<a class="skip" href="#main">Skip to main content</a>
<layout><nav id="nav" aria-label="Main navigation"></nav><div class="app"><header id="top"></header><main id="main" tabindex="-1"><div class="spin">Loading…</div></main></div></layout>
<script>
let SCANS=[],cur="",D=null,MINE=null,TOPIC="",TITLE="",RG=null,ABTH="",PEND="",TOOLS={},AQ={idea:"",words:"",ref:"",mk:"",res:"",str:null,eng:"rw",meth:"auto"},AIINFO={},AIH=[],AIRES=null,SYS={th:{},w_on:{}},IDEAS=null,IDEAR={},YTOK=false,YTN=0,TRG={PK:"Pakistan"};
const $=s=>document.querySelector(s);
const fmt=n=>n>=1e9?(n/1e9).toFixed(2)+"B":n>=1e6?(n/1e6).toFixed(1)+"M":n>=1e3?(n/1e3).toFixed(1)+"K":Math.round(n||0);
const esc=s=>(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
async function j(u){const r=await fetch(u);const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);return d}
async function jp(u,b){const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);return d}
// Loading: "…" dikhane par page koodta hai — har cheez aate hi neeche sarakti hai
// (layout shift), aur user ko lagta hai tool atka hai. Skeleton wahi shape dikhata
// hai jo bharne wala hai, isliye layout pehle hi settle ho jata hai.
function skelKpi(n){let s="";for(let i=0;i<(n||7);i++)s+='<i class="skel"></i>';return '<div class="sk-kpi">'+s+'</div>'}
function skelGrid(n){let s="";for(let i=0;i<(n||6);i++)s+='<div class="sk-card"><i class="skel sk-th"></i>'+
 '<i class="skel sk-ln" style="width:'+(55+((i*17)%35))+'%"></i><i class="skel sk-ln" style="width:'+(28+((i*29)%45))+'%"></i></div>';
 return '<div class="sk-grid">'+s+'</div>'}
function skelTable(n){let s="";for(let i=0;i<(n||9);i++)s+='<div class="skel sk-row"></div>';return s}
// chhote output box (AI ideas, CSV ka natija, channel listing) ke liye jagah dikhao.
// Pehle wahan sirf "…" tha, jisse lagta tha tool atak gaya hai.
function skelLines(n,txt){let s='<div class="sr" role="status" aria-live="polite">'+esc(txt||"Loading…")+'</div>';
 for(let i=0;i<(n||3);i++)s+='<i class="skel sk-ln" style="width:'+(92-i*17)+'%;margin:9px 0"></i>';return s}
function spin(what){$("#main").innerHTML='<div class="sr" role="status" aria-live="polite">'+esc(what||"Loading…")+'</div>'+
 skelKpi(7)+skelGrid(6)}
// Toast: ek hi jagah stack, type ka rang token se, click par band. Pehle ek hi toast
// hota tha (doosra aane par pehla gayab) aur uska style inline likha hua tha.
function toast(m,kind,ttl){
 let w=$("#tst");if(!w){w=document.createElement("div");w.id="tst";
  w.setAttribute("role","status");w.setAttribute("aria-live","polite");document.body.appendChild(w)}
 while(w.children.length>4)w.firstChild.remove();
 const k=["ok","warn","bad","info"].indexOf(kind)>=0?kind:"info";
 const d=document.createElement("div");d.className="tst "+k;
 d.innerHTML=ico(k==="ok"?"check":k==="info"?"info":"alert",16)+
  "<div>"+(ttl?"<b>"+esc(ttl)+"</b>":"")+esc(m)+"</div>"+'<span class="x">'+ico("x",14)+"</span>";
 d.onclick=()=>d.remove();w.appendChild(d);
 setTimeout(()=>{d.style.transition="opacity .25s";d.style.opacity="0";setTimeout(()=>d.remove(),260)},k==="bad"?9000:5200);
 return d}
// Galati ka standard taur — message + kya karein. Kahin bhi "fail: [object]" na dikhe.
function failToast(e,what){toast((what?what+": ":"")+(e&&e.message?e.message:e)||"nothing to report","bad","Could not complete")}
const clip=(s,n)=>{s=String(s==null?"":s);return s.length>n?s.slice(0,n-1)+"…":s};
const pfmt=p=>{if(p==null)return "—";if(p<0.001)return "<0.001";return String(Math.round(p*1000)/1000)};
// ---------- ek hi overlay system: score ka hisaab, shortcuts, palette ----------
function modal(title,inner,cls){
 const old=$("#ov");if(old)old.remove();
 const ov=document.createElement("div");ov.className="ov";ov.id="ov";
 ov.setAttribute("role","dialog");ov.setAttribute("aria-modal","true");ov.setAttribute("aria-label",title);
 ov.innerHTML='<div class="'+(cls||"pal")+'">'+
  '<div style="padding:12px 16px;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center">'+
  '<b style="font-size:var(--fs-sub);flex:1">'+esc(title)+'</b><button class="sm gh" onclick="closeModal()">'+
  ico("x",14)+'Close <kbd>Esc</kbd></button></div>'+
  '<div style="max-height:62vh;overflow:auto;padding:14px 16px">'+inner+"</div></div>";
 ov.onmousedown=e=>{if(e.target===ov)closeModal()};
 document.body.appendChild(ov);
 const f=ov.querySelector("input,button.go");if(f)f.focus();
 return ov}
function closeModal(){const o=$("#ov");if(o)o.remove()}
// ---------- khali haal: sirf ek line nahi, agla qadam button ke saath ----------
function esCard(o){return '<div class="es">'+ico(o.i||"info",26)+"<h3>"+esc(o.t)+"</h3><p>"+o.p+"</p>"+(o.b||"")+"</div>"}
// ---------- card par pehle MASLE, kacche number nahi ----------
// Server har naapi gayi video par verdicts bhejta hai (kya kharab hai + uska ilaaj).
// Pehle wo sirf "Meri Thumbnail" tak me limited tha; cards par 15 kacche chips the
// jinse ye samajhna user ka kaam tha ki kaunsa number bura hai. Ab ulta hai:
// pehle faisla, poora naap "poora analysis" me.
function issCnt(it){const v=it.vr||[];const b=v.filter(x=>x.s==="bad").length,w=v.filter(x=>x.s==="warn").length;
 return {bad:b,warn:w,n:b+w,has:v.length>0}}
// Table me har row par triage: kitne masle. Sirf number nahi — rang se pata chalta hai
// ki turant dekhna hai ya chhoda ja sakta hai. Poora list row kholne par milta hai.
function issPill(it){const c=issCnt(it);if(!c.has)return "";
 const s=c.bad?"bad":c.warn?"warn":"ok";
 const t=(it.vr||[]).filter(x=>x.s!=="ok").map(x=>x.k+" — "+x.n).join("\n")||"no issues found on this thumbnail";
 return '<span class="ipill '+s+'" title="'+esc(t)+'">'+(s==="ok"?"clean":c.n+(c.n===1?" issue":" issues"))+"</span>"}
function issList(it,i,full){
 const all=it.vr||[];
 if(!all.length)return "";
 const bad=all.filter(x=>x.s!=="ok");
 // Card ka sabse upar wala hissa: kitne masle + score ka hisaab. Number par click
// se poora breakdown khulta hai — "ye 31 kaise aaya" ka jawab screen par hi hai.
 const hd='<button class="iss-h" onclick="whyAt('+i+')" title="how this score was built — the contribution of every feature">'+
  ico("bars",14)+(bad.length?bad.length+(bad.length===1?" issue found":" issues found")+" · score breakdown":"no issues · score breakdown")+"</button>";
 if(!bad.length)return '<div class="iss">'+hd+'<div class="iss-n ok">'+ico("check",14)+
  "<span>no issues found on this thumbnail</span></div></div>";
 const ord={bad:0,warn:1};
 bad.sort((a,b)=>(ord[a.s]-ord[b.s])||(b.p||0)-(a.p||0));
 const show=full?bad:bad.slice(0,3);
 let h=hd+show.map(x=>{
  const val=String(x.v==null?"":x.v).split(" | ")[0];
  return '<div class="iss-n '+x.s+'" title="'+esc(x.k+" — "+x.v+" — "+x.n)+'">'+ico("alert",14)+
   '<span><b>'+esc(x.k)+"</b> "+esc(full?x.v:clip(val,30))+'<br><span>'+esc(full?x.n:clip(x.n,86))+"</span></span></div>"}).join("");
 if(!full&&bad.length>3)h+='<button class="iss-more" onclick="zoom('+i+')">+'+(bad.length-3)+" more issues — open the full analysis</button>";
 return '<div class="iss">'+h+"</div>"}
// ---------- "ye score kaise bana" — har feature ka value × wazan = kitne number ----------
function whyCard(it){
 const s=it.sd||{};
if(!s.parts)return esCard({i:"info",t:"No score breakdown for this video",
  p:"This scan is from before score breakdowns were saved to the file. Run the scan again and every video gets a per-feature breakdown.",
  b:'<button class="go" onclick="goScan()">'+ico("refresh",14)+"Run the scan again</button>"});
 const mx=Math.max.apply(null,s.parts.map(p=>p.p).concat([1]));
 let h='<table class="why-t"><thead><tr><th scope="col">what was measured</th><th scope="col" class="num">how good</th>'+
  '<th scope="col" class="num">weight</th><th scope="col" class="num">points</th></tr></thead><tbody>'+
  s.parts.map(p=>'<tr><td>'+esc(WLAB[p.k]||p.k)+'</td><td class="num">'+Math.round(p.v*100)+'%</td><td class="num">'+p.w+
   '</td><td class="num">'+(p.p>0?"+":"")+p.p+'<span class="why-bar"><i style="width:'+Math.max(2,Math.round(p.p/mx*100))+'%"></i></span></td></tr>').join("")+
   "</tbody></table>"+
  '<div class="why-sum"><span>base <b>'+s.base+'</b></span><span>issue penalty <b>-'+s.pen+"</b></span>"+
  "<span>subtotal <b>"+s.raw+'</b></span><span>final <b>'+s.score+"/100</b></span></div>"+
  '<div class="sub" style="margin-top:10px">'+(s.src==="calibrated"
?"weights <b>fitted on your own "+(s.n_cal||0)+" real CTR records</b> — this is your channel's own measurement."
   :"weights are an engineering estimate (heuristic). Import your own Studio CSV and the weights refit to it — <a style=\"color:var(--acc)\" onclick=\"closeModal();go('own')\">Connect your CTR</a>.")+
   (s.drift!=null?'<br>This scan’s score was <b>'+s.drift+"</b> at the time; this breakdown is recounted with today’s weights, which is why the numbers differ.":"")+
   "</div>";
 return h}
function whyAt(i){const it=(D&&D.items)||[];const it2=it[i];if(!it2)return toast("that video is not in this scan","bad");
 modal("Score breakdown — "+clip(it2.title,64),
  '<div class="sub" style="margin-bottom:10px">'+esc(it2.channel||"")+" · score <b class=\""+scC(it2.score)+"\">"+
  (it2.score==null?"—":it2.score)+"/100</b></div>"+whyCard(it2),"pal wide")}
// ---------- Ctrl+K: 12 tabs + har scan + har kaam ek box me ----------
// Ab tak har cheez left sidebar me dhundhni padti thi (do dropdown + 12 links).
// Ek palette: lafz likho, Enter. Wahi kaam jo mouse se hota tha, ab do keyboard par.
let PALF=[],PALI=0,STCUR=-1;
function palItems(){
 const it=[];
 Object.keys(VW).forEach(k=>it.push({g:"Go to",t:VW[k].t,i:VW[k].i,run:()=>go(k)}));
 SCANS.filter(s=>s.kind==="channel").forEach(s=>it.push({g:"Channel scan",
  t:(s.ch||{}).name||s.topic,s:fmt((s.ch||{}).subs||0)+" subscribers · "+s.kept+" measured",i:"eye",
  run:()=>{cur=s.id;D=null;IDEAS=null;WALK=null;SEL.clear();stSelUpd();go("ch")}}));
 SCANS.filter(s=>s.kind!=="channel").forEach(s=>it.push({g:"Topic scan",t:s.topic,
  s:s.kept+" videos",i:"search",run:()=>{cur=s.id;D=null;IDEAS=null;WALK=null;SEL.clear();stSelUpd();go("cmp")}}));
 it.push({g:"Actions",t:"New topic scan",i:"plus",run:()=>newScan()});
 it.push({g:"Actions",t:"Open a new channel",i:"plus",run:()=>goNewChan()});
 if(cur){it.push({g:"Actions",t:"CSV file for this scan",i:"dl",run:()=>{location="/api/export?id="+cur+"&fmt=csv"}});
  it.push({g:"Actions",t:"JSON for this scan",i:"dl",run:()=>{location="/api/export?id="+cur+"&fmt=json"}});
  it.push({g:"Actions",t:"Delete this scan",i:"trash",run:()=>delScan()})}
 it.push({g:"Help",t:"Keyboard shortcuts",i:"keyboard",run:()=>keyHelp()});
 it.push({g:"Help",t:"How the tool works",i:"info",run:()=>go("help")});
 return it}
function palMatch(q,items){
 q=(q||"").toLowerCase().trim();if(!q)return items.slice(0,30);
 const ws=q.split(/\s+/);
 return items.map(x=>{const hay=(x.t+" "+(x.g||"")+" "+(x.s||"")).toLowerCase();
  let sc=0;for(const w of ws){const h=hay.indexOf(w);if(h<0)return null;
   sc+=(x.t.toLowerCase().indexOf(w)===0?8:h===0?3:1)}
  return {x:x,sc:sc}}).filter(Boolean).sort((a,b)=>b.sc-a.sc).slice(0,30).map(y=>y.x)}
function palDraw(q){
 PALF=palMatch(q,palItems());PALI=0;const el=$("#pl");if(!el)return;
 if(!PALF.length){el.innerHTML='<div class="pal-g">nothing matched — try different words</div>';return}
 const m={};PALF.forEach(x=>{(m[x.g]=m[x.g]||[]).push(x)});
 el.innerHTML=Object.keys(m).map(g=>'<div class="pal-g">'+esc(g)+"</div>"+
  m[g].map(x=>{const n=PALF.indexOf(x);
   return '<div class="pal-i'+(n===PALI?" sel":"")+'" data-n="'+n+'" onclick="palRun('+n+')">'+
    ico(x.i||"ext",16)+"<span>"+esc(x.t)+(x.s?' <i>'+esc(x.s)+"</i>":"")+"</span></div>"}).join("")).join("")}
function palHl(){const el=$("#pl");if(!el)return;
 el.querySelectorAll(".pal-i").forEach(x=>x.classList.toggle("sel",+x.dataset.n===PALI));
 const s=el.querySelector(".pal-i.sel");if(s)s.scrollIntoView({block:"nearest"})}
function palRun(n){const x=PALF[n==null?PALI:n];if(!x)return;closeModal();x.run()}
function palette(){
const ov=modal("Go to",""+'<input id="pq" placeholder="type a tab, channel, topic or action…" autocomplete="off"'+
  ' aria-label="Go to">'+
  '<div class="pal-list" id="pl" role="listbox" aria-label="Results"></div>'+
  '<div class="pal-ft"><span>↑↓ select</span><span>Enter go</span><span>Esc close</span></div>',"pal");
 const q=ov.querySelector("#pq");
 q.oninput=()=>palDraw(q.value);
 q.onkeydown=e=>{
  if(e.key==="ArrowDown"){e.preventDefault();PALI=Math.min(PALF.length-1,PALI+1);palHl()}
  else if(e.key==="ArrowUp"){e.preventDefault();PALI=Math.max(0,PALI-1);palHl()}
  else if(e.key==="Enter"){e.preventDefault();palRun()}
  else if(e.key==="Escape"){closeModal()}};
 palDraw("")}
const KS=[["Ctrl / ⌘ + K","one box for everything — views, scans, actions"],
 ["Ctrl / ⌘ + B","hide / show the side menu"],
 ["/","the same palette, one key"],["?","this list"],["Esc","close any dialog"],
 ["n","new topic scan"],["Shift + N","open a new channel"],
 ["e","CSV file for this scan"],["s","focus the table search box"],
 ["j / k","next / previous row in the table"],["Enter","open the selected row's detail"]];
function keyHelp(){modal("Keyboard shortcuts",
 '<table class="why-t"><tbody>'+KS.map(x=>'<tr><td><kbd>'+esc(x[0])+"</kbd></td><td>"+esc(x[1])+"</td></tr>").join("")+
 "</tbody></table><div class=\"sub\" style=\"margin-top:10px\">These shortcuts follow the YouTube Studio pattern — the whole tool without a mouse. A shortcut only fires while you are not typing in a box.</div>","pal")}
function onKey(e){
 if(e.key==="Escape"){closeModal();return}
 const t=e.target||{},tag=(t.tagName||"").toLowerCase();
 const typing=tag==="input"||tag==="textarea"||tag==="select"||t.isContentEditable;
 const kk=(e.key||"").toLowerCase();
 if((e.ctrlKey||e.metaKey)&&kk==="k"){e.preventDefault();palette();return}
 if((e.ctrlKey||e.metaKey)&&kk==="b"){e.preventDefault();navTog();return}
 if(typing)return;
 if(kk==="/"){e.preventDefault();palette();return}
 if(kk==="?"){e.preventDefault();keyHelp();return}
 if(kk==="n"){e.preventDefault();if(e.shiftKey)goNewChan();else newScan();return}
 if(kk==="e"){if(!cur)return toast("open a scan first","warn");
  location="/api/export?id="+cur+"&fmt=csv";return}
 if(kk==="s"){const q=document.querySelector(".stq");if(q){e.preventDefault();q.focus();q.select()}return}
 if(kk==="j"||kk==="k"||kk==="arrowdown"||kk==="arrowup"){
  const rows=[].slice.call(document.querySelectorAll("#stbox tr.srow"));if(!rows.length)return;
  e.preventDefault();
  const step=(kk==="j"||kk==="arrowdown")?1:-1;
  let idx=rows.findIndex(r=>r.classList.contains("cur"));
  idx=idx<0?(step>0?0:rows.length-1):Math.max(0,Math.min(rows.length-1,idx+step));
  rows.forEach((r,i)=>r.classList.toggle("cur",i===idx));
  rows[idx].scrollIntoView({block:"nearest"})}
 if(kk==="enter"){const r=document.querySelector("#stbox tr.cur");if(!r)return;
  e.preventDefault();
  if(r.classList.contains("un")){const b=r.querySelector("button[data-id]");if(b)b.click()}
  else if(r.dataset.id)stOpen(r.dataset.id)}}
document.addEventListener("keydown",onKey);
const imgu=p=>"/img?path="+encodeURIComponent(p);
const cc=v=>v==null?"":"var(--"+(v>=70?"grn":v>=45?"amb":"red")+")";
// thresholds server se aate hain (TH) — page me koi hand-picked number dobara na likha jaaye,
// warna UI aur code ke numbers alag ho jaate hain (jo pehle tha).
const THv=(k,d)=>{const t=(typeof SYS!=="undefined"&&SYS.th)?SYS.th[k]:null;return t==null?d:t};
const calTag=()=>{const c=(typeof SYS!=="undefined")?SYS.cal:null;
return c?'<span class="chip">score weights <b>calibrated</b> — fitted on real CTR from '+c.n+' of my videos, R² '+c.r2+' / cross-validated '+(c.cv_r2==null?"—":c.cv_r2)+'</span>'
  :'<span class="chip">score weights <b>heuristic</b> (estimates) — import your own CTR to make them real → <b>Your CTR and score calibration</b></span>'+
   (SYS&&SYS.cal_rejected?'<span class="chip">'+ico("alert",14)+esc(SYS.cal_rejected)+'</span>':'')};
// scan ka sample kaise chuna gaya — ye sirf tab dikhega jab us scan ne sach me record kiya ho
function smp(d){if(d.legacy||!d.eng&&!d.filt)return '<span class="chip">this scan did not record its engine, sample or weights (older scan) — run a new scan and all of it will be shown here</span>';
 const f=d.filt||{},e=d.eng||{};
return '<span class="chip">measurement: <b>'+esc(e.face||"?")+'</b> + <b>'+esc(e.ocr||"?")+'</b></span>'+
  '<span class="chip">sample: <b>'+d.items.length+'</b> videos from <b>'+(f.channel_alag||"?")+'</b> different channels · removed: '+(f.shorts_hataaye||0)+' shorts, '+(f.ek_channel_zayada||0)+' over one channel, '+(f.duplicate||0)+' duplicates</span>'+
  (f.views_missing?'<span class="chip">'+ico("alert",14)+'<b>'+f.views_missing+'</b> videos ke views/date ka naap YouTube ne abhi rok diya (bot check) — inka views/day nahi gina gaya; baki naap theek hain. Thodi der baad dobara scan se ye bhar jayenge</span>':'')+
  (f.api_fill?'<span class="chip">'+f.api_fill+' videos ke views/date YouTube Data API se liye (YouTube ke hi official numbers, free quota ka 1 unit)</span>':'')+
  (f.manga&&f.mila!=null&&f.mila<f.manga?'<span class="chip">'+ico("alert",14)+'aap ne <b>'+f.manga+'</b> maangi thi — YouTube ke search me is topic par sirf <b>'+f.mila+'</b> alag videos mile (maine '+(f.topup_queries||0)+' extra searches aur dheele filter bhi kar dekh liye). Ye poori taaadad hai, chhupi hui nahi</span>':'')+
  (f.shorts_relaxed?'<span class="chip">'+ico("alert",14)+'ginti poori karne ke liye short videos bhi shamil karne pare — ye is scan me count hui hain</span>':
   (f.cap_relaxed?'<span class="chip">'+ico("alert",14)+'ginti poori karne ke liye ek-channel ki had dhili karni pari — results ek hi channel ki taraf jhuk sakte hain</span>':
   (f.relaxed?'<span class="chip">'+ico("alert",14)+'the sample was small enough that the per-channel cap had to be relaxed — results may lean on a single channel</span>':'')))+
  (d.cal&&d.cal.n?'<span class="chip">this scan’s weights: <b>calibrated</b> ('+d.cal.n+' of my videos, R² '+d.cal.r2+')</span>'
   :'<span class="chip">this scan’s weights: <b>heuristic</b> — not fitted to your CTR at the time</span>')+calTag()}
const chip=(l,v,st)=>'<span class="chip">'+l+(v==null?"":' <b'+(st?' style="color:'+st+'"':'')+'>'+v+'</b>')+'</span>';
// float ka shor: 14.200000000000001 nahi, 14.2 dikhao. Sirf display hai, naapi gayi value nahi badalti.
const f2=v=>v==null?"—":String(Math.round(v*100)/100);
const kpi=(l,v,st)=>'<div><span class="kl">'+l+'</span><b'+(st?' style="color:'+st+'"':'')+'>'+v+'</b></div>';
const vpd=it=>Math.round((it.views||0)/Math.max(1,it.days||1));
const scC=v=>v>=70?"hi":v>=45?"mid":"lo";
// floating noise (0.21550000000000002) dikhne se bachne ke liye — medians even
// count par average hote hain, raw float kabhi-kabhi poora lamba aa jata hai.
function nf(x){x=Number(x);if(!isFinite(x))return "—";return String(Math.round(x*1000)/1000)}
function pchip(B,key,lab,val,who){const b=B&&B[key];if(!b||val==null)return "";let p=95;
 for(const k of [["p10",10],["p25",25],["med",50],["p75",75],["p90",90]]){if(val<=b[k[0]]){p=k[1];break}}
 return '<span class="chip">'+lab+' <b style="color:var(--acc2)">'+(p>=95?"top 10%":p+"th%")+'</b> — '+(who||"yours")+' '+nf(val)+', their median '+nf(b.med)+'</span>'}

// icons: controls me emoji nahi — inline SVG, currentColor se theme follow karta hai
const IC={back:"M19 12H5m7 7-7-7 7-7",plus:"M12 5v14M5 12h14",trash:"M4 7h16M9 7V4h6v3m-9 0 1 13h10l1-13M10 11v6M14 11v6",
 search:"M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.35-4.35",bars:"M4 20V11M10 20V4M16 20v-6M2 20h20",
 image:"M4 5h16v14H4Zm0 10 4-4 4 4 3-3 5 5M8.5 9.5a1 1 0 1 0 .01 0",palette:"M12 3a9 9 0 1 0 0 18c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.3-.5-.8-.5-1.2 0-1.1.9-2 2-2h1.5A4.5 4.5 0 0 0 21 10c0-3.9-4-7-9-7ZM7.5 12a1 1 0 1 0 .01 0M11 8.5a1 1 0 1 0 .01 0M15.5 9.5a1 1 0 1 0 .01 0",
 pen:"M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z",ab:"M4 18 8 6l4 12M5.6 14h4.8M16 6v12M16 12h2a3 3 0 1 0 0-6h-2",
 trend:"M22 7 14 15l-4-4-8 8M16 7h6v6",info:"M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v6M12 7.5h.01",
 spark:"m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9ZM18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9Z",
 trophy:"M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0ZM7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3",
 ext:"M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3",dl:"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
 copy:"M9 9h11v11H9zM5 15H4V4h11v1",check:"M20 6 9 17l-5-5",x:"M18 6 6 18M6 6l12 12",refresh:"M20 12a8 8 0 1 1-3-6.2M20 4v5h-5",
 eye:"M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
 target:"M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z",
 file:"M14 3v5h5M14 3H6v18h12V8Z",down:"m6 9 6 6 6-6",up:"M12 19V5M5 12l7-7 7 7",clock:"M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2",
 alert:"M12 3 2 20h20L12 3Zm0 6v5m0 3.5h.01",filter:"M3 5h18l-7 8v6l-4 2v-8L3 5Z",
 list:"M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",
 keyboard:"M3 7h18v10H3zM7 11h.01M11 11h.01M15 11h.01M7.5 14.5h9",
  gear:"M12 18a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1h.09a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z",
  help:"M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-2.2-10.6a2.3 2.3 0 1 1 3.4 2.5c-.8.5-1.2 1.1-1.2 2m0 2.6h.01",
  home:"M3 11l9-8 9 8M5 9.5V20h14V9.5M9.5 20v-5.5h5V20",
   layers:"M12 2 2 7l10 5 10-5-10-5ZM2 17l10 5 10-5M2 12l10 5 10-5",menu:"M4 6h16M4 12h16M4 18h16",chevL:"m15 6-6 6 6 6",chevR:"m9 6 6 6-6 6"};
const ico=(n,s)=>{const d=IC[n];if(!d)return"";const w=s||16;
 return '<svg viewBox="0 0 24 24" width="'+w+'" height="'+w+'" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="'+d+'"/></svg>'};
// Ek button jo us video ko YouTube par le jaye (naya tab). Pehle sirf title ka link tha,
// jise button samajhna mushkil tha — ab har card par saaf button hai.
const ytb=(u,l)=>'<a class="btn sm ytbtn" target="_blank" rel="noopener" href="'+esc(u||"#")+'" title="open this video in a new YouTube tab">'+ico("ext",14)+(l||"Open on YouTube")+'</a>';
// Har video par YouTube kholne ka button aur usi ka link copy karne ka button —
// dono har jagah, kyunki link bhejna/notes me daalna aksar kholne se pehle chahiye.
const ytc=(u)=>'<button class="btn sm" onclick="cpLink(\''+esc(u||"")+'\')" title="is video ka YouTube link copy karo" aria-label="link copy karo">'+ico("copy",14)+'Link copy</button>';
function cpLink(u){if(!u)return toast("is video ka link nahi mila");cpText(u);toast("video ka link copy — kahin bhi paste karein")}
// Har view ka ek hi source: label, icon, aur function. Pehle nav me label dobara likhe the,
// isliye UI aur routing alag ho sakte the.
let view="home";
const VW={home:{f:homev,t:"Home",i:"home"},cmp:{f:cmp,t:"Competitors",i:"search"},
 fun:{f:funv,t:"Topic funnel",i:"filter"},
 ch:{f:chanv,t:"Channel analytics",i:"eye"},hist:{f:histv,t:"Channel history",i:"clock"},act:{f:actv,t:"Scan history",i:"list"},cmpc:{f:cmpc,t:"Channel comparison",i:"trophy"},deep:{f:deepv,t:"Deep analysis",i:"bars"},
 ideas:{f:ideasv,t:"Winning topics to ideas",i:"trophy"},bank:{f:bankv,t:"Competitor bank",i:"layers"},mine:{f:mine,t:"My thumbnail",i:"image"},
 ai:{f:aipg,t:"AI thumbnail",i:"palette"},tl:{f:tl,t:"Title lab",i:"pen"},ab:{f:ab,t:"A/B variants",i:"ab"},hub:{f:hubv,t:"Testing hub",i:"ab"},
 own:{f:ownpg,t:"Your CTR and calibration",i:"trend"},gen:{f:genpg,t:"How thumbnails get generated",i:"spark"},
 help:{f:help,t:"How the tool works",i:"info"}};
const NAVG=[["Main",["home"]],["Channel",["ch","act","hist","cmpc","bank"]],["Work",["cmp","fun","deep","ideas","mine","ai","hub","own"]],["Help",["gen","help"]]];
// Sidebar ka channel card — reference ke sidebar-top-block ki jagah, lekin sirf asli
// data se: naam, subscribers, gini/mapi videos aur naap ki sachchi halat. Koi number
// ghad ke nahi bhara.
function navCard(s){if(!s)return '<div class="nm"><span>Koi scan khula nahi</span></div>'+
  '<div class="mt">Naya channel ya topic scan shuru karo</div>';
 if(s.kind==="channel"){const c=s.ch||{};const tot=(c.tot_videos||0);
  return '<div class="nm"><span>'+(c.name||s.topic)+"</span></div>"+
   '<div class="mt">'+fmt(c.subs||0)+' subscriber · '+capn(tot,400)+' videos · '+s.kept+' measured</div>'+
   '<span class="hc"><i></i>'+(s.kept>=tot&&tot>0?"naap poora hua":"naap adhoora — "+s.kept+"/"+capn(tot,400))+"</span>"}
 return '<div class="nm"><span>'+esc(s.topic)+"</span></div>"+
  '<div class="mt">'+s.kept+(s.wide?"+wide":"")+' videos · competitors ke thumbnails</div>'+
  '<span class="hc"><i></i>topic scan</span>'}
function nav(){
 // Do alag selector: ek CHANNEL ke liye, ek TOPIC SCAN ke liye. Pehle ek hi dropdown
 // me dono mix the — user ko galat cheez kholne ka dar. Ab har kaam apni jagah.
 const chs=SCANS.filter(s=>s.kind==="channel"),tops=SCANS.filter(s=>s.kind!=="channel");
 const copt=s=>{const c=s.ch||{},n=esc(c.name||s.topic);
  // Select tang hai isliye poora hisaab title (tooltip) me hai; saamne sirf naam aur
  // kitni videos gini gayi — wahi jo user channel chunte waqt dekhta hai.
  return '<option value="'+s.id+'"'+(s.id===cur?" selected":"")+
   ' title="'+n+' · '+fmt(c.subs||0)+' subscriber · '+capn(c.tot_videos,400)+' longs · '+capn(c.tot_shorts,400)+
   ' shorts · '+s.kept+' measured">'+n+' · '+capn(c.tot_videos,400)+' videos</option>'};
 const topt=s=>'<option value="'+s.id+'"'+(s.id===cur?" selected":"")+'>'+esc(s.topic)+
   ' ('+s.kept+(s.wide?"+wide":"")+')</option>';
 $("#nav").innerHTML='<div class="brand"><span class="mk"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true" focusable="false"><path d="M7 2l13 10-7.3 1.3L10 21 7 2z" fill="#fff"/><path d="M18.5 2.5l.9-1.7M21.5 6.5l1.9-.9M21 10.8l2.3-.3" stroke="#fff" stroke-width="1.7" stroke-linecap="round"/></svg></span>ClickLab <small>v3</small><button class="iconbtn gh" id="navc" aria-label="Side menu chhupao" title="Side menu chhupao (Ctrl+B)" style="margin-left:auto">'+ico("chevL",16)+'</button></div>'+
  '<div class="navcard">'+navCard(SCANS.find(x=>x.id===cur))+'</div>'+
   '<div class="grp">Choose a channel</div><select id="csel" style="width:100%" aria-label="Choose a channel">'+
  (chs.length?chs.map(copt).join(""):'<option value="">(no channel open yet)</option>')+'</select>'+
  '<div class="bar" style="margin:8px 0"><button class="sm" onclick="goNewChan()">'+ico("plus",14)+'new channel</button>'+
  '<button class="sm dg" onclick="delChan()">'+ico("trash",14)+'remove</button></div>'+
  '<div class="grp">Choose a topic scan</div><select id="sel" style="width:100%" aria-label="Choose a topic scan">'+
  (tops.length?tops.map(topt).join(""):'<option value="">(no topic scan yet)</option>')+'</select>'+
  '<div class="bar" style="margin:8px 0"><button class="sm" onclick="newScan()">'+ico("plus",14)+'new topic</button>'+
  '<button class="sm dg" onclick="delScan()">'+ico("trash",14)+'remove</button></div>'+
  NAVG.map(g=>'<div class="grp">'+g[0]+'</div>'+g[1].map(v=>{const x=VW[v];
   return '<a data-v="'+v+'" tabindex="0" role="link" class="'+(view===v?"on":"")+'"'+(view===v?' aria-current="page"':"")+'>'+ico(x.i)+x.t+'</a>'}).join("")).join("")+
   // Sidebar ka bottom block (reference frame): Settings/Help yahin se milein, aur
   // ye baat ke saara data isi folder me rehta hai — koi cloud nahi.
   '<div class="navfoot"><a data-v="gen" tabindex="0" role="link" class="'+(view==="gen"?"on":"")+'">'+ico("gear",15)+"Settings</a>"+
   '<a data-v="help" tabindex="0" role="link" class="'+(view==="help"?"on":"")+'">'+ico("help",15)+"Help & feedback</a>"+
   '<div class="mt" style="padding:6px 12px 0">saara data isi folder me — koi cloud nahi</div></div>';
 const nc=$("#navc");if(nc)nc.onclick=navTog;
 $("#csel").onchange=e=>{cur=e.target.value;D=null;IDEAS=null;go("ch")};
 $("#sel").onchange=e=>{cur=e.target.value;D=null;IDEAS=null;go("cmp")};
 document.querySelectorAll("nav a[data-v]").forEach(a=>{a.onclick=()=>go(a.dataset.v);
  a.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();go(a.dataset.v)}}});
}
// Side menu chhupane/dikhane ka toggle — Ctrl+B se bhi. Choice localStorage me rehti hai,
// agle session me wahi state rehti hai. Chhupane par poora viewport content ko milta hai.
function navTog(){const off=document.body.classList.toggle("navoff");
 try{localStorage.setItem("cl_nav",off?"off":"on")}catch(e){}nav();topbar()}
// Topbar ka doosra lafz scan ke mutabiq. "Competitors" likha aata tha bhale hi ye kisi
// channel ka apna scan ho — page ki heading se alat. Wahi kaha jata hai jo heading kehti hai.
function vlbl(s){const g=(VW[view]||VW.cmp).t;if(!s||view!=="cmp")return g;
 return s.kind==="channel"?"Thumbnails for this channel":"Competitors"}
function topbar(){
 const s=SCANS.find(x=>x.id===cur);
 $("#top").innerHTML=(document.body.classList.contains("navoff")?'<button class="iconbtn gh" id="navo" aria-label="Side menu dikhao" title="Side menu dikhao (Ctrl+B)">'+ico("menu",18)+"</button>":"")+'<button class="iconbtn gh" id="bk" aria-label="Go back" title="Go back (the browser Back key works too)">'+ico("back",18)+'</button>'+
  '<span class="ttl">'+(s?esc(s.kind==="channel"?(s.ch||{}).name||s.topic:s.topic)+' <span class="sep">·</span> <span style="color:var(--mut);font-weight:400">'+esc(vlbl(s))+"</span>":esc(vlbl(s)))+'</span>'+
  (s?(s.kind==="channel"?'<span class="chip" title="the listing is counted up to 400 videos; the measurement covers only the videos that were measured, the rest are counted only">channel · '+capn((s.ch||{}).tot_videos,400)+' videos · '+capn((s.ch||{}).tot_shorts,400)+' shorts · '+s.kept+' measured</span>'
    :'<span class="chip" title="'+s.n+' were requested; filters kept '+s.kept+' (shorts removed, no more than one per channel, duplicates removed)">'+s.kept+' videos</span>'):"")+'<span class="sp"></span>'+
  '<button class="sm gh" onclick="go(\'act\')" title="Scan history — open or restore any past scan" aria-label="Scan history">'+ico("clock",15)+'History</button>'+
   '<button class="sm gh" onclick="palette()" title="Go anywhere from one box" aria-label="Search where to go">'+ico("search",15)+'<kbd>Ctrl K</kbd></button>'+
   '<button class="sm gh" onclick="keyHelp()" title="Everything without a mouse" aria-label="Keyboard shortcuts">'+ico("keyboard",15)+'<kbd>?</kbd></button>'+
(s?'<a class="ytbtn sm" href="/api/export?id='+cur+'&fmt=csv" download title="Save the full scan as a CSV file">'+ico("dl",14)+'CSV</a>'+
     '<a class="ytbtn sm" href="/api/export?id='+cur+'&fmt=json" download title="Raw data as a JSON file, including every measured value">'+ico("dl",14)+'JSON</a>':"")+
(view==="ch"||view==="cmpc"||view==="hist"?'<button class="go sm" onclick="goNewChan()">'+ico("plus",14)+'New channel</button>'
   :'<button class="go sm" onclick="newScan()">'+ico("plus",14)+'New topic</button>');
 $("#bk").onclick=back;const nb=$("#navo");if(nb)nb.onclick=navTog;
}
// browser ka Back kaam kare isliye hash/history se route hota hai (#/deep/<scanid>),
// aur har view ka direct link ban jata hai — pehle is page me history ka ek line bhi nahi tha.
let _mine=0;
function setHash(){const h="#/"+view+(cur?"/"+cur:"");if(location.hash===h)return;_mine=1;
 try{history.pushState({v:view,scan:cur},"",h)}catch(e){location.hash=h}}
function fromHash(){const p=(location.hash||"").replace(/^#\/?/,"").split("/").filter(Boolean);
 if(p.length&&VW[p[0]])view=p[0];
 if(p[1]&&SCANS.some(x=>x.id===p[1])){if(p[1]!==cur){cur=p[1];D=null}}
 if(!p.length){if(!SCANS.some(x=>x.id===cur))cur=SCANS.length?SCANS[0].id:""}}
// RTN: har render ka token. Jo view async kaam karke baad me #main likhta hai, wo
// pehle check karta hai ke ye abhi bhi wahi render hai — warna purana view naye view
// ko clobber kar deta hai (nav alag, content alag).
let RTN=0;
function render(){RTN++;nav();topbar();(VW[view]||VW.cmp).f()}
function go(v){if(!VW[v])return;if(v!==view){SEL.clear();stSelUpd()}view=v;setHash();render()}
function back(){if(history.length>1)history.back();else go("cmp")}
window.addEventListener("popstate",()=>{fromHash();render()});
window.addEventListener("hashchange",()=>{if(_mine){_mine=0;return}fromHash();render()});
// ---------- Premium motion helpers (CSS "premium layer" ke saath jugalbandi) ----------
// Scroll reveal: grid ke andar ke cards aspas aate hi uthte hain. JS .rv lagata hai,
// IntersectionObserver .in. Reduced-motion par kuch nahi hota; aur JS ke bina CSS
// .rv nahi lagta — content kabhi chhupa nahi rehta.
const _RM=matchMedia("(prefers-reduced-motion: reduce)");
const _RVT=".grid>.card,.ideas>.idea,.grid2>*,.rvs>.rvimg";
const _rvIO=new IntersectionObserver(es=>{for(const e of es)if(e.isIntersecting){e.target.classList.add("in");_rvIO.unobserve(e.target)}},{rootMargin:"0px 0px -6% 0px"});
function _markRv(n){if(!n.classList||n.classList.contains("rv")||n.classList.contains("in"))return;
 n.classList.add("rv");_rvIO.observe(n)}
new MutationObserver(ms=>{if(_RM.matches)return;for(const m of ms)for(const n of m.addedNodes){
 if(n.nodeType!==1)continue;
 if(n.matches&&n.matches(_RVT))_markRv(n);
 if(n.querySelectorAll)n.querySelectorAll(_RVT).forEach(_markRv)}}).observe($("#main"),{childList:true,subtree:true});
// Brand tile 3D tilt: pointer par perspective+rotate — ek chhota 3D signal, pointer
// hat-te hi wapas seedha. Delegation se nav dobara banne par bhi chalta hai.
document.addEventListener("pointermove",e=>{if(_RM.matches)return;
 const t=e.target.closest?e.target.closest("nav .brand .mk"):null;if(!t)return;
 const r=t.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
 t.style.transform="perspective(340px) rotateX("+(-y*14).toFixed(1)+"deg) rotateY("+(x*14).toFixed(1)+"deg)"},{passive:true});
document.addEventListener("pointerout",e=>{const t=e.target.closest?e.target.closest("nav .brand .mk"):null;
 if(t)t.style.transform=""},{passive:true});


// ---------- Channel History ----------------------------------------------------
// Har snapshot usi waqt ki asli reading hai (thumb_output/hist/<channel id>.json).
// Growth sirf do ALAG snapshots ke beech gin jaati hai, aur sirf unhi videos ki jo
// DONO me naapi gayi thin. Jo cheez nahi hai wo yahan dikhti hi nahi: koi forecast
// nahi, koi "estimated" number nahi, aur jab per-video numbers dobara nape nahi gaye
// to farak 0 nahi likha jaata — "not re-measured" likha jaata hai.

function histT(x){const d=new Date(x);return isNaN(d.getTime())?"—":d.toLocaleString()}
function histDur(g){if(g==null)return "an unknown interval";
 const m=Math.round(g*1440);
 if(m<1)return "less than a minute";if(m<90)return m+" minutes";
 if(m<2880)return (m/60).toFixed(1)+" hours";if(m<64800)return (m/1440).toFixed(1)+" days";
 return Math.round(m/1440)+" days"}
function exact(n){return n==null?"—":Number(n).toLocaleString("en-US")}
function histD(x){const d=new Date(x);return isNaN(d.getTime())?"—":d.toLocaleDateString()}
function hdl(v){if(v==null)return '<span class="sub">—</span>';
 const c=v>0?"var(--ok)":(v<0?"var(--bad)":"var(--mut2)");
 return '<b style="color:'+c+'">'+(v>0?"+":"")+fmt(v)+'</b>'}
function hdlh(v){if(v==null)return '<span class="sub">—</span>';
 const c=v>0?"var(--ok)":(v<0?"var(--bad)":"var(--mut2)");
 return '<b style="color:'+c+'">'+(v>0?"+":"")+v+'</b>'}
function hchart(vals,ts,cl,lab){
 const W=660,Hh=152,PL=56,PR=14,PT=16,PB=26;
 const vs=vals.map(v=>(v==null?null:Number(v))),have=vs.filter(v=>v!=null&&!isNaN(v));
 if(!have.length)return '<div class="sub" style="margin-top:6px">No values recorded for '+esc(lab)+'.</div>';
 let lo=Math.min.apply(null,have),hi=Math.max.apply(null,have);
 const flat=hi===lo;
 if(flat){lo=hi-1;hi=hi+1}   // flat series: line center par, axis par sirf asli value
 const N=vals.length,ix=[],jx=[];
 vs.forEach((v,i)=>{if(v!=null&&!isNaN(v)){ix.push(i);jx.push(i)}});
 const X=i=>N<2?(PL+(W-PL-PR)/2):PL+(W-PL-PR)*i/(N-1);
 const Y=v=>PT+(Hh-PT-PB)*(1-(v-lo)/(hi-lo));
 let g="";
 if(flat){const y0=Y(hi);
  g+='<line x1="'+PL+'" y1="'+y0.toFixed(1)+'" x2="'+(W-PR)+'" y2="'+y0.toFixed(1)+'" stroke="var(--edge)" stroke-width="1"/>'+
     '<text x="6" y="'+(y0+3.5).toFixed(1)+'" style="font-size:var(--fs-micro);fill:var(--mut2)">'+fmt(hi)+'</text>'+
     '<text x="'+(PL+8)+'" y="'+(PT+11)+'" style="font-size:var(--fs-micro);fill:var(--mut2)">nothing changed between these snapshots — the numbers were not fetched again</text>'}
 else for(let q=0;q<=2;q++){const v=lo+(hi-lo)*q/2,y=Y(v);
  g+='<line x1="'+PL+'" y1="'+y.toFixed(1)+'" x2="'+(W-PR)+'" y2="'+y.toFixed(1)+'" stroke="var(--edge)" stroke-width="1"/>'+
     '<text x="6" y="'+(y+3.5).toFixed(1)+'" style="font-size:var(--fs-micro);fill:var(--mut2)">'+fmt(Math.round(v))+'</text>'}
 let pts=[],dots="";
 jx.forEach(i=>{pts.push(X(i).toFixed(1)+","+Y(vs[i]).toFixed(1));
  dots+='<circle cx="'+X(i).toFixed(1)+'" cy="'+Y(vs[i]).toFixed(1)+'" r="3.4" fill="'+cl+'"><title>'+
   esc(lab+" · "+fmt(vs[i])+" · "+histT(ts[i]))+'</title></circle>'});
 const x0=X(ix[0]).toFixed(1),x1=X(ix[ix.length-1]).toFixed(1),base=(Hh-PB).toFixed(1);
 const area=pts.length>1?'<polygon points="'+x0+','+base+' '+pts.join(" ")+' '+x1+','+base+'" fill="rgba(var(--accrgb),.10)"/>':"";
 const line=pts.length>1?'<polyline points="'+pts.join(" ")+'" fill="none" stroke="'+cl+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>':"";
 let xl='<text x="'+PL+'" y="'+(Hh-7)+'" style="font-size:var(--fs-micro);fill:var(--mut2)">'+esc(histD(ts[0]))+'</text>';
 if(N>1)xl+='<text x="'+(W-PR)+'" y="'+(Hh-7)+'" text-anchor="end" style="font-size:var(--fs-micro);fill:var(--mut2)">'+esc(histD(ts[N-1]))+'</text>';
 return '<svg viewBox="0 0 '+W+' '+Hh+'" role="img" aria-label="'+esc(lab)+' over time" style="width:100%;height:auto;display:block">'+
  area+line+g+dots+xl+'</svg>'}
function histBar(){
 return '<div class="card"><div class="bar" style="flex-wrap:wrap">'+
  '<button class="go sm" onclick="histTake()">'+ico("refresh",14)+'Take a snapshot now</button>'+
  '<select id="hknum" aria-label="How many recent videos to re-measure">'+
   '<option value="10">10 recent videos</option><option value="25" selected>25 recent videos</option>'+
   '<option value="50">50 recent videos</option><option value="0">every measured video</option></select>'+
  '<button class="sm" onclick="histRef()">'+ico("eye",14)+'Re-measure their views</button>'+
  '<span class="sp"></span><a class="ytbtn sm" href="/api/export?id='+cur+'&fmt=json" download>'+ico("dl",14)+'Scan JSON</a></div>'+
  '<div class="sub" style="margin-top:8px"><b>Take a snapshot</b> re-reads the public counts of this channel (subscribers, how many uploads exist) plus a fresh listing if it is older than a day — a few seconds. It does not re-measure per-video numbers. <b>Re-measure views</b> pulls current view counts for the newest uploads through the same engine that built this scan (about 1 second per video, 8 at a time) and writes a snapshot afterwards — that is what turns history into real per-video growth. Snapshots are also written automatically every time a channel scan runs.</div>'+
  '<div id="hstat"></div></div>'}
function histHstat(m,cls){const e=$("#hstat");if(!e)return;
 e.innerHTML='<div class="'+(cls||"sub")+'" style="margin-top:8px">'+esc(m)+'</div>'}
async function histTake(){histHstat("Reading the channel again — subscriber count and upload listing…");
 let r;try{r=await j("/api/hist?id="+encodeURIComponent(cur)+"&take=1")}catch(e){return histHstat("Snapshot failed: "+e.message,"err")}
 if(r.err){histHstat(r.err,"err");return}
 histHstat("Snapshot saved in "+r.elapsed+"s — "+(r.got.subs?"subscriber count read fresh":"subscriber count could not be read")+" · listing from "+(r.got.list==="cache"?"cache (under a day old)":"YouTube again")+(r.got.terr?" · "+r.got.terr:""));
 histv()}
async function histRef(){const k=(($("#hknum")||{}).value)||"25";
 histHstat("Re-reading view counts for "+(k==="0"?"every measured video":k+" recent videos")+" — about 1 second per video, this stays on the page…");
 let r;try{r=await j("/api/hist?id="+encodeURIComponent(cur)+"&refresh="+encodeURIComponent(k))}
 catch(e){return histHstat("Re-measure failed: "+e.message,"err")}
 if(r.err){histHstat(r.err,"err");return}
 histHstat(r.updated+" videos re-measured in "+r.elapsed+"s — their new view counts are now the current numbers in every panel, and a snapshot was written.");
 histv()}
function histGrow(p){
 if(!p)return "";
 if(p.vm_same)return '<div class="sub" style="margin:6px 0 10px">This pair re-read public counts only. The per-video numbers in both snapshots are the same reading, so per-video growth is <b>not measured</b> — it would be 0 only because nothing was fetched again. Use “Re-measure their views” above to get real growth.</div>';
 const rows=(p.top||[]).map(e=>'<tr><td><a href="'+esc("https://www.youtube.com/watch?v="+e.id)+'" target="_blank" rel="noopener">'+esc(clip(e.t,72))+'</a>'+
  (e.s?' <span class="chip">short</span>':'')+'</td><td class="num" title="'+(e.v0==null?"no earlier reading":exact(e.v0))+'">'+fmt(e.v0)+'</td>'+
  '<td class="num" title="'+(e.v1==null?"no reading":exact(e.v1))+'">'+fmt(e.v1)+'</td>'+
  '<td class="num"'+(e.dv!=null?' title="'+(e.dv>0?"+":"")+exact(e.dv)+' views"':'')+'>'+(e.dv==null?'<span class="sub">not re-measured</span>':'<b style="color:'+(e.dv>0?"var(--ok)":(e.dv<0?"var(--bad)":"var(--mut2)"))+'">'+(e.dv>0?"+":"")+fmt(e.dv)+'</b>')+'</td>'+
  '<td class="num">'+(e.dv!=null&&e.gap>=0.5?fmt(Math.round(e.dv/e.gap)):'<span class="sub" title="the two readings are under half a day apart — a daily rate would be noise">—</span>')+'</td>'+
  '<td class="num"'+(e.r!=null?' title="'+exact(e.v0)+' → '+exact(e.v1)+' = '+e.r.toFixed(4)+'×"':'')+'>'+(e.r!=null?e.r.toFixed(2)+"×":"—")+'</td>'+
  '<td class="num">'+(e.dl!=null?hdlh(e.dl):"—")+'</td></tr>').join("");
 const ups=(p.new||[]).map(e=>'<tr><td><a href="'+esc("https://www.youtube.com/watch?v="+e.id)+'" target="_blank" rel="noopener">'+esc(clip(e.t,72))+'</a>'+
  (e.s?' <span class="chip">short</span>':'')+'</td><td class="num">'+(e.d!=null?e.d+" days":"—")+'</td>'+
  '<td class="num">'+(e.v!=null?fmt(e.v):"—")+'</td><td>'+(e.up?'<span class="chip" style="color:var(--ok)">uploaded in this window</span>':'<span class="chip">older video, coverage grew</span>')+'</td></tr>').join("");
 let h='<div class="sub" style="margin:6px 0 10px">Between '+esc(histT(p.a))+' and '+esc(histT(p.b))+' — '+
  (p.gap!=null?histDur(p.gap)+' apart, ':'')+'<b>'+p.n_match+'</b> videos were measured in both snapshots, so growth below is only those '+p.n_match+
  ' videos. Views gained <b>'+(p.dv==null?"not re-measured":(p.dv>=0?"+":"")+fmt(p.dv))+'</b>'+
  (p.dl!=null?' · likes '+(p.dl>=0?"+":"")+fmt(p.dl):"")+
  (p.dc!=null?' · comments '+(p.dc>=0?"+":"")+fmt(p.dc):"")+'.'+
  (p.meas&&p.meas.length?(' Only '+p.meas.join(" and ")+' were re-read between these two snapshots; every other metric was not fetched again, so it is left blank instead of counted as zero.'):"")+
  (p.meas&&!p.meas.length?" Only public counts were re-read between these two snapshots — no per-video number was fetched again.":"")+
  (p.gap!=null&&p.gap<0.5?" A per-day rate is left out here — at this gap it would be noise, not a rate.":"")+'</div>';
 if(rows)h+='<div class="stscr"><table><tr><th scope="col">video</th><th scope="col" class="num">views then</th><th scope="col" class="num">views now</th><th scope="col" class="num">gained</th><th scope="col" class="num">per day</th><th scope="col" class="num">ratio</th><th scope="col" class="num">likes</th></tr>'+rows+'</table></div>';
 else h+='<div class="sub">No video was measured in both snapshots, so no per-video growth can be computed.</div>';
 if(p.dn&&p.dn.length)h+='<div class="sub" style="margin-top:6px">Lowest movers: '+p.dn.map(e=>esc(clip(e.t,32))+' '+(e.dv>0?"+":"")+fmt(e.dv)).join(" · ")+'</div>';
 if(ups)h+='<div class="stt" style="margin-top:12px">Videos present in the newer snapshot but not the older one — '+p.new_n+' ('+p.new_up_n+' uploaded inside this window, the rest are older videos that were only measured now)</div>'+
  '<div class="stscr"><table><tr><th scope="col">video</th><th scope="col" class="num">age at snapshot</th><th scope="col" class="num">views</th><th scope="col">what it is</th></tr>'+ups+'</table></div>';
 if(p.gone_n)h+='<div class="sub" style="margin-top:6px">'+p.gone_n+' videos measured in the older snapshot are missing from the newer one — deleted, made private, or outside the listing window.</div>';
 return h}
// Channel ki pehchaan ki line — creation date (source ke saath) aur aakhri
// upload. Ye line sirf tab banti hai jab scan ka channel data haath me ho.
function histMeta(){const c=(D&&D.id===cur&&D.ch)||{};if(!c.name)return "";
 const s=(D.cst||{});
 return '<div class="sub"><b>'+esc(c.name)+'</b>'+(c.subs?' · '+fmt(c.subs)+' subscribers':"")+
  ' · channel bana: '+(c.joined?'<b>'+fD(c.joined.d)+'</b>'+(c.joined.src==="about"?" (YouTube ke About page se)":" (listing ki sabse purani upload se — channel is se purana bhi ho sakta hai)"):'<b>—</b> (is scan me abhi nahi — Channel analytics wale view ke <b>fetch joined date</b> button se aa jayegi, ek hi baar)')+
  (s.last?' · aakhri upload (is scan ki listing me): <b>'+fD(s.last)+'</b>'+(s.days_since!=null?' ('+s.days_since+' din pehle)':""):"")+
  (s.per_week?' · raftaar: <b>'+s.per_week+'</b> video/hafta':"")+'</div>'}
// Month ledger — user ne poocha: "usi channel ke views aur subscribers ka start se
// mahine-baar gain/drop". Do honest series, dono ke label alag: (a) snapshots ke
// beech ka mahine-baar ASLI badlav (sirf un mahinon me jab readings thin), (b)
// upload-month cohorts — us mahine chhapi videos ke AAJ ke views (ye time-series
// nahi hai, ye sirf ek scan ka cross-section hai). Dono ka apna sach likha hai.
function histMonth(H){
 const sn=H.snaps||[];let h="";
 const mb={};
 sn.forEach((x,i)=>{if(!i||!x.ts)return;const m=String(x.ts).slice(0,7);
  const b=mb[m]||(mb[m]={subs:0,views:0,hasV:false,ups:0,n:0,meas:0});
  if(x.d_subs!=null)b.subs+=x.d_subs;
  if(x.d_views!=null){b.views+=x.d_views;b.hasV=true}
  if(x.d_up!=null)b.ups+=x.d_up;
  if(x.n_match)b.meas+=x.n_match;b.n++});
 const ms=Object.keys(mb).sort();
 h+='<div class="sec">Month by month — the channel against itself <small> — only months with real readings appear; a month without a reading is absent here, not zero</small></div>';
 if(ms.length<2)h+='<div class="card"><div class="sub">Month-over-month change needs readings in at least two months. '+(ms.length?'So far only '+esc(ms[0])+' has readings.':'No snapshot pairs exist yet.')+' Run a channel scan again later, or use “Take a snapshot now” / “Re-measure their views” above — every new reading extends this table by itself.</div></div>';
 else{let rows="";ms.forEach(m=>{const b=mb[m];
   rows+='<tr><td>'+esc(m)+'</td><td class="num">'+hdl(b.subs)+'</td>'+
    '<td class="num">'+(b.hasV?hdl(b.views):'<span class="sub">views not re-measured in this month</span>')+'</td>'+
    '<td class="num">'+hdl(b.ups)+'</td><td class="num">'+b.n+'</td><td class="num">'+(b.meas||"—")+'</td></tr>'});
  h+='<div class="card"><div class="stt">What actually changed inside each month — the sum of the reading-pairs that fell in it</div>'+
   '<div class="stscr"><table><tr><th scope="col">month</th><th scope="col" class="num">subscribers Δ</th><th scope="col" class="num">views gained (videos measured in both readings)</th><th scope="col" class="num">uploads Δ</th><th scope="col" class="num">readings</th><th scope="col" class="num">matched videos</th></tr>'+rows+'</table></div>'+
   '<div class="sub">Subscriber deltas are YouTube’s public counts at each reading. Views gained counts only videos measured in both readings of a pair — the same rule as the pair tables above. A month with no row had no reading: its change is unknown, not zero. This is the only honest month-by-month series a snapshot history can give, and it grows on its own every time a snapshot is taken.</div></div>'}
 if(D&&D.id===cur&&Array.isArray(D.items)&&D.items.length){
  const cm={};D.items.forEach(it=>{if(!it.upload)return;const m=String(it.upload).slice(0,7);
   const b=cm[m]||(cm[m]={n:0,v:0});b.n++;b.v+=Number(it.views)||0});
  const cs=Object.keys(cm).sort();
  if(cs.length>1){let tot=0;cs.forEach(m=>{tot+=cm[m].v});let cum=0,prev=null,rows="";
   cs.forEach(m=>{const b=cm[m];cum+=b.v;
    rows+='<tr><td>'+esc(m)+'</td><td class="num">'+b.n+'</td><td class="num">'+fmt(b.v)+'</td>'+
     '<td class="num">'+(tot?(b.v/tot*100).toFixed(1)+"%":"—")+'</td>'+
     '<td class="num">'+(prev==null?'<span class="sub">first</span>':hdl(b.v-prev))+'</td>'+
     '<td class="num">'+fmt(cum)+'</td></tr>';prev=b.v});
   const cvals=[],cts=[];cs.forEach(m=>{cvals.push(cm[m].v);cts.push(m+"-15T12:00:00")});
   h+='<div class="card" style="margin-top:12px"><div class="stt">Upload-month cohorts — what each upload month holds today (from this one scan: '+fmt(D.items.length)+' measured videos)</div>'+
    hchart(cvals,cts,"var(--acc)","views held by videos uploaded in each month")+
    '<div class="stscr" style="margin-top:10px"><table><tr><th scope="col">upload month</th><th scope="col" class="num">videos</th><th scope="col" class="num">views today</th><th scope="col" class="num">share of channel</th><th scope="col" class="num">vs previous month</th><th scope="col" class="num">cumulative</th></tr>'+rows+'</table></div>'+
    '<div class="sub">This is <b>not</b> “views gained during that month” — one scan only shows today’s totals per upload cohort; the month-by-month change lives in the readings table above. Read it as: videos published in month X hold Y views as of this scan. The “vs previous month” column compares one upload cohort against the next — it shows which upload months built the channel, not what happened inside a month.</div></div>'}}
 return h}
function histRep(H){
 const sn=H.snaps||[],last=sn[sn.length-1]||{},ps=H.pairs||[],pr=ps[ps.length-1];
 let h='<h2>Channel History</h2>'+
  '<div class="sub">A snapshot is a real reading of this channel at one moment: subscriber and upload counts from YouTube, plus per-video views, likes and comments from our own measurements. Nothing here is modelled, projected or back-filled with today’s numbers. Growth is computed only between two actual snapshots, and only for videos that were measured in both — videos present in one snapshot alone are counted separately, never folded into a growth figure.</div>'+
  histBar()+histMeta();
 if(!sn.length)return h+'<div class="card"><div class="sub">No snapshot exists for this channel yet. Take one above to start the series.</div></div>';
 const ts=sn.map(x=>x.ts);
 h+='<div class="kpi">'+kpi("snapshots on record",String(H.n),"var(--acc)")+
  kpi("time span",H.span!=null?H.span.toFixed(1)+" days":"one point only",H.span?"var(--acc)":"var(--warn)")+
  kpi("subscribers now",fmt(last.subs||0),"var(--acc)")+
  kpi("subscribers Δ since previous",last.d_subs!=null?hdl(last.d_subs):"first point",
      (last.d_subs||0)>0?"var(--ok)":((last.d_subs||0)<0?"var(--bad)":"var(--mut2)"))+
  kpi("uploads now",fmt((last.tv||0)+(last.tsh||0)),"var(--acc)")+
  kpi("uploads Δ",last.d_up!=null?hdl(last.d_up):"first point",(last.d_up||0)>0?"var(--ok)":"var(--mut2)")+
  kpi("videos measured",fmt(last.nm||0),"var(--acc)")+
  kpi("views gained (matched videos)",pr?(pr.dv==null?'<span class="sub">not re-measured</span>':(pr.dv>=0?"+":"")+fmt(pr.dv)):"—",
      pr&&pr.dv!=null?(pr.dv>0?"var(--ok)":"var(--mut2)"):"var(--mut2)")+
  kpi("matched in both",pr?String(pr.n_match):"—","var(--acc)")+'</div>';
 if(H.n<2)return h+'<div class="sec">What history needs <small> — one reading is a fact, two readings are a trend</small></div>'+
  '<div class="card"><div class="sub">Only one snapshot exists for this channel, taken '+esc(histT(sn[0].ts))+'. Every number in the other panels is real; there is simply nothing to compare it against yet. Two things build the series: <b>“Take a snapshot now”</b> (seconds, gives you subscribers and upload counts over time) and <b>“Re-measure their views”</b> (about a second per video, gives you per-video growth). A channel scan run again later adds a snapshot automatically. Snapshots are stored in <code>thumb_output/hist/</code> and are never overwritten.</div></div>'+histMonth(H);
 h+='<div class="sec">Trend across snapshots <small> — every dot is one real snapshot; nothing between dots is interpolated except the connecting line</small></div>'+
  '<div class="card"><div class="stt">Subscribers</div>'+hchart(sn.map(x=>x.subs),ts,"var(--acc)","subscribers")+
  '<div class="stt" style="margin-top:12px">Uploads on the channel (long-form + Shorts, as listed by YouTube)</div>'+
  hchart(sn.map(x=>(x.tv||0)+(x.tsh||0)),ts,"var(--acc)","uploads")+
  '<div class="stt" style="margin-top:12px">Total views of measured videos</div>'+hchart(sn.map(x=>x.views),ts,"var(--acc)","total views of measured videos")+
  '<div class="sub" style="margin-top:6px">A flat segment means the numbers were not fetched again between those two snapshots — it does not mean the channel was flat. The per-video table below says exactly which pairs are real measurements.</div></div>';
 h+='<div class="sec">Growth between the last two snapshots <small> — '+esc(histT(pr?pr.a:""))+' → '+esc(histT(pr?pr.b:""))+'</small></div>'+
  '<div class="card">'+histGrow(pr)+'</div>';
 if(ps.length>1){let old="";ps.slice(0,-1).forEach(p=>{old+='<div class="stt" style="margin-top:10px">'+esc(histT(p.a))+' → '+esc(histT(p.b))+
  (p.gap!=null?' · '+histDur(p.gap)+' apart':'')+' · matched '+p.n_match+' · views '+(p.dv==null?"not re-measured":(p.dv>=0?"+":"")+fmt(p.dv))+
  (p.new_n?(' · new '+p.new_n+" ("+p.new_up_n+" uploaded)"):"")+(p.gone_n?' · gone '+p.gone_n:"")+'</div>'+histGrow(p)});
  h+='<details class="kdet"><summary>'+ico("clock",14)+'Earlier snapshot pairs ('+(ps.length-1)+')</summary><div class="card">'+old+'</div></details>'}
 h+=histMonth(H);
 let rows=sn.map((x,i)=>'<tr><td>'+esc(histT(x.ts))+'</td><td>'+esc(x.src||"")+(x.vm&&x.vm!==x.ts?' <span class="chip" title="per-video numbers were taken at '+esc(histT(x.vm))+'">measured '+esc(histD(x.vm))+'</span>':'')+
  '</td><td class="num">'+fmt(x.subs||0)+'</td><td class="num">'+hdl(x.d_subs)+'</td>'+
  '<td class="num">'+fmt((x.tv||0)+(x.tsh||0))+'</td><td class="num">'+hdl(x.d_up)+'</td>'+
  '<td class="num">'+fmt(x.nm||0)+'</td><td class="num">'+fmt(x.views||0)+'</td>'+
  '<td class="num">'+(x.d_views!=null?hdl(x.d_views):(i===0?'<span class="sub">first</span>':'<span class="sub">not re-measured</span>'))+'</td>'+
  '<td class="num">'+(x.n_match!=null?x.n_match:"—")+'</td></tr>').join("");
 h+='<div class="sec">Snapshot log <small> — every reading ever stored for this channel: '+H.n+'</small></div>'+
  '<div class="stscr"><table><tr><th scope="col">taken at</th><th scope="col">how</th><th scope="col" class="num">subscribers</th><th scope="col" class="num">Δ subs</th>'+
  '<th scope="col" class="num">uploads</th><th scope="col" class="num">Δ uploads</th><th scope="col" class="num">videos measured</th><th scope="col" class="num">total views</th>'+
  '<th scope="col" class="num">Δ views (matched)</th><th scope="col" class="num">matched</th></tr>'+rows+'</table></div>'+
  '<div class="sub">“how” is written honestly: <b>scan</b> = a channel scan ran at that moment, <b>backfill</b> = the reading that was already stored when History was first opened, <b>manual</b> = public counts re-read on request, <b>refresh</b> = per-video views re-measured on request. Channel uploads are counted from the YouTube listing, capped at '+fmt(400)+' per type; anything beyond that is not counted anywhere in this app.</div>';
 return h}
async function histv(){const _t=RTN;
 const s=SCANS.find(x=>x.id===cur);
 if(!s||s.kind!=="channel"){$("#main").innerHTML='<h2>Channel History</h2>'+
   '<div class="card"><div class="sub">History follows one channel across time. Pick a channel in the sidebar, or open a new one. A topic scan is a single moment across many channels, so there is nothing to measure growth between.</div>'+
   '<div class="bar"><button class="go sm" onclick="goNewChan()">'+ico("plus",14)+'Open a channel</button>'+
   '<button class="sm" onclick="go(\'cmp\')">'+ico("search",14)+'Browse topics instead</button></div></div>';return}
 spin("Reading history…");
 try{await ensureData()}catch(e){}
 if(_t!==RTN)return;
 let H;try{H=await j("/api/hist?id="+encodeURIComponent(cur))}
 catch(e){if(_t!==RTN)return;$("#main").innerHTML='<h2>Channel History</h2><div class="err">'+esc(e.message)+'</div>';return}
 if(_t!==RTN)return;
 if(H.err){$("#main").innerHTML='<h2>Channel History</h2><div class="err">'+esc(H.err)+'</div>';return}
 $("#main").innerHTML=histRep(H)}
// ---------- Scan history & rollback (audit trail) ----------
// Har scan ek immutable snapshot hai — ye view un sab ka record hai: kaab chala, kis
// par chala, kitni videos naapi gayi. "Restore" ka matlab sirf itna hai ke wahi purana
// scan dobara current ban jaye — dobara-scan nahi, koi data nahi badalta, isliye ye
// har row par safe hai. (Design brief ka "instant rollback", hamare data par.)
let _actF="all",_actQ="";
// ts scan ka asli waqt hai (ISO ya epoch); mtime age file chhne ka waqt — audit
// trail me asli scan-time se sort karna hi theek hai.
function actTs(s){const t=typeof s.ts==="number"?s.ts*1000:Date.parse(s.ts||"");return isNaN(t)?0:t}
function actAgo(sec){sec=sec||0;const d=Math.floor(sec/86400),h=Math.floor(sec%86400/3600),m=Math.floor(sec%3600/60);
 return d>0?d+"d "+h+"h ago":h>0?h+"h "+m+"m ago":m>0?m+"m ago":"just now"}
function actF(f){_actF=f;actv()}
function actCl(){_actQ="";_actF="all";actv()}
function actRestore(id){const s=SCANS.find(x=>x.id===id);if(!s)return;
 // Pehle se current scan par "restore" koi kaam nahi — bas wahi view khol do.
 if(cur!==id){cur=id;D=null;IDEAS=null;WALK=null;SEL.clear();stSelUpd()}
 go(s.kind==="channel"?"ch":"cmp");toast("Restored — this scan is now the current one","ok")}
async function actDel(id){if(!confirm("Remove this scan? Its saved data goes with it."))return;
 await j("/api/del?id="+encodeURIComponent(id));
 if(cur===id){cur="";D=null}await boot();if(view==="act")actv();toast("removed")}
function actv(){
 const tot=SCANS.length,tp=SCANS.filter(s=>s.kind!=="channel").length,cn=tot-tp,
  meas=SCANS.reduce((a,s)=>a+(s.kept||0),0),cnt={all:tot,topic:tp,chan:cn};
 let L=SCANS.slice();
 if(_actF==="topic")L=L.filter(s=>s.kind!=="channel");
 if(_actF==="chan")L=L.filter(s=>s.kind==="channel");
 const q=_actQ.toLowerCase().trim();
 if(q)L=L.filter(s=>((s.topic||"")+" "+((s.ch||{}).name||"")).toLowerCase().indexOf(q)>=0);
 L.sort((a,b)=>actTs(b)-actTs(a));
 let h='<h2>'+ico("list",20)+' Scan history</h2>'+
  '<div class="sub">Every scan this tool has run, newest first. <b>Restore</b> makes an older scan the current one — nothing is re-scanned and no stored data changes.</div>';
 // Upar KPI row (brief ka pattern): pehle poora record, phir filter, phir table.
 h+='<div class="kpi">'+kpi("total scans",String(tot),"var(--acc)")+kpi("topic scans",String(tp))+
  kpi("channel scans",String(cn))+kpi("videos measured",fmt(meas),"var(--grn)")+'</div>';
 h+='<div class="bar"><div class="seg" role="group" aria-label="Filter tabs">'+
  [["all","All"],["topic","Topic"],["chan","Channel"]].map(x=>'<button class="'+(_actF===x[0]?"on":"")+'" onclick="actF(\''+x[0]+'\')">'+x[1]+' <b>'+cnt[x[0]]+'</b></button>').join("")+
  '</div><input id="aq" class="stq" placeholder="Search a channel or topic…" value="'+esc(_actQ)+'" aria-label="Search scans"></div>';
 if(!L.length){h+='<div class="es">'+(SCANS.length?
   '<h3>Nothing matches this filter</h3><div class="sub">Clear the search or show all scans again.</div><div class="bar" style="justify-content:center"><button class="sm" onclick="actCl()">Show all scans</button></div>':
   '<h3>No scans yet</h3><div class="sub">Run a topic scan or open a channel — every scan is saved here automatically.</div><div class="bar" style="justify-content:center"><button class="go sm" onclick="newScan()">'+ico("plus",14)+'New topic scan</button><button class="sm" onclick="goNewChan()">'+ico("plus",14)+'Open a channel</button></div>')+'</div>';
  $("#main").innerHTML=h;const q0=$("#aq");if(q0)q0.oninput=e=>{_actQ=e.target.value;actv()};return}
 h+='<div class="st"><table class="stt"><thead><tr><th class="l no">When</th><th class="l no">Target</th><th class="l no">Type</th><th class="no">Measured</th><th class="no">Actions</th></tr></thead><tbody>'+
  L.map(s=>{const chn=s.kind==="channel",nm=esc(chn?(s.ch||{}).name||s.topic:s.topic),
   sub=chn?esc((s.ch||{}).handle||"")+" · "+fmt((s.ch||{}).subs||0)+" subscribers":
    (s.n!=null?esc(String(s.n))+" requested · filters kept "+s.kept:"topic scan"),
   // ts ya to epoch-seconds number hai ya ISO string (dono purani builds me mile)
   when=new Date(typeof s.ts==="number"?s.ts*1000:(s.ts||0)),tms=when.getTime(),
   abs=isNaN(tms)?"—":when.toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}),
   // Relative time bhi usi ts se — warna file ke chhune ka time aur scan ka time
   // ek hi row me alag lagte. ts na mile to mtime wali age hi sahi.
   rel=actAgo(isNaN(tms)?s.age:Math.max(0,(Date.now()-tms)/1000)),
   badge=chn?'<span class="ipill" style="color:var(--nic);border-color:rgba(59,130,246,.4)">CHANNEL</span>':
    '<span class="ipill" style="color:var(--acc);border-color:rgba(var(--accrgb),.4)">TOPIC</span>',
   chips=(s.wide?'<span class="chip">wide net</span>':"")+(s.meta?'<span class="chip">with metadata</span>':"");
  return '<tr class="srow" onclick="actRestore(\''+esc(s.id)+'\')" title="restore this scan as the current one">'+
   '<td class="l"><b>'+abs+'</b><span class="d">'+rel+'</span></td>'+
   '<td class="l"><b>'+nm+'</b><span class="d">'+sub+'</span></td>'+
   '<td class="l">'+badge+(s.id===cur?' <span class="ipill ok">current</span>':"")+(chips?'<span class="d">'+chips+'</span>':"")+'</td>'+
   '<td><b>'+s.kept+'</b></td>'+
   '<td><button class="sm" onclick="event.stopPropagation();actRestore(\''+esc(s.id)+'\')">restore</button> '+
   '<button class="sm dg" onclick="event.stopPropagation();actDel(\''+esc(s.id)+'\')" title="remove this scan — permanent">'+ico("trash",13)+'</button></td></tr>'}).join("")+
  "</tbody></table></div>";
 h+='<div class="sub" style="margin-top:10px">Restoring only points the tool at an older saved scan. To delete one instead use <b>remove</b> — that one is permanent.</div>';
 $("#main").innerHTML=h;
 const qi=$("#aq");if(qi){qi.oninput=e=>{_actQ=e.target.value;actv()};
  if(_actQ){qi.focus();qi.setSelectionRange(_actQ.length,_actQ.length)}}}

// ---------- Home Dashboard ----------
// Reference suite ke dashboard (a_master) ka frame, lekin sirf un cheezon se bhara
// hua jo ClickLab sach me naapta hai: scans, measured videos, latest/tez video vs
// usi scan ka median, jeete hue topics. Jo data hai hi nahi (revenue, watch-time,
// audience) us ka koi tile nahi — jhootha number dikhane se behtar hai jagah chhod dena.
function medv(a){if(!a.length)return 0;const s=a.slice().sort((x,y)=>x-y);return s[Math.floor(s.length/2)]}
// "Jeetne wali" ka ek hi matlab hai, har jagah: views/day us scan ke median se 2× ya
// zyada. Rule screen par likha hota hai — koi chupa hua filter nahi. 6 se kam naapi
// gayi videos par median ka matlab nahi banta, is liye wahan ye feature chup rehta hai.
function winOf(d){const its=(d&&d.items)||[];const a=its.map(vpd).filter(x=>x>0);
 if(a.length<6)return{on:false,win:[],med:0};const med=medv(a);
 const win=its.filter(it=>vpd(it)>=2*med);return{on:true,win:win,med:med}}
function cmpF(v){CMPF=v;CPG=0;cmp()}
function winSelAll(){if(!D)return;const W=winOf(D);if(!W.on||!W.win.length)return;
 W.win.forEach(it=>SEL.add(it.id));stSelUpd();
 toast(W.win.length+" jeetne wali videos chun li gayi — CSV aur titles neeche wale bar se nikal jayenge")}
// Model-verdict: sirf un hi videos ka title/tags/thumbnail-text model ko diya jaata
// hai jo is scan me naapi gayi hain (jeetne wali + median se neeche). Model pattern
// aur hypothesis deta hai — wajah sabit nahi karta, is liye har block ka label saaf
// hai. Provider chain server par hai (Gemini → muft Pollinations → dono ki asli
// galti); "via" me likha aata hai ke jawab kis ne diya. Jawab disk par cache —
// "naya jawab" button force ke saath dobara mangwata hai.
let VDQ=false;
function vdSec(d){
 if(VDQ)return '<div class="sec">Jeetne walon ka model-verdict</div><div class="sub">model se baat ho rahi hai — pehle Gemini (aapki key), wahan limit lage to muft Pollinations rasta; dono na chale to asli galti yahi dikhegi.</div>';
 const v=(D.vd&&D.vd.id===d.id)?D.vd.data:null;
 if(!v||v.error)return '<div class="bar" style="margin-top:12px"><button class="go" onclick="vdGo()">'+ico("spark",14)+"Jeetne walon ka model-verdict laao</button>"+
  (v&&v.error?'<span class="err" style="flex:1">'+esc(v.error)+'</span>':
  '<span class="sub">model sirf inhi '+W_N(d)+' jeetne wali aur median se neechi videos ka title/tags/thumbnail-text padhega — pattern aur hypothesis dega, wajah sabit nahi karega. Ek baar aaye to file me cache rehta hai; padhne me dobara koi kharcha nahi.</span>')+'</div>';
 const vd=v.verdict||{},per=vd.per_video||{};
 const idxOf={};d.items.forEach((it,i)=>idxOf[it.id]=i);
 return '<div class="sec">Jeetne walon ka model-verdict <small> — model ki raay, is scan ke naape gaye data par; sahy-sambandh hai, wajah sabit nahi</small></div>'+
  '<div class="card"><div class="sub">'+esc(v.note||"")+'<br>jawab dene wala: <b>'+esc(v.via||"?")+'</b>'+(v.cached?' · ye pehle ka cached jawab hai — dobara koi kharcha nahi':"")+(v.gem_err?'<br>Gemini wali koshish: '+esc(v.gem_err):"")+'</div>'+
  (vd.patterns&&vd.patterns.length?'<div class="stt" style="margin-top:8px">Jo cheez jeetne walon me common hai (model ka kehna)</div><ul class="sub">'+vd.patterns.map(p=>"<li>"+esc(p)+"</li>").join("")+"</ul>":"")+
  (Object.keys(per).length?'<div class="stt" style="margin-top:8px">Har jeetne wali ke baare me (hypothesis — proof nahi)</div>'+
    Object.keys(per).map(id=>{const i=idxOf[id],it=i!=null?d.items[i]:null;
     return '<div class="sub" style="margin:5px 0"><b>'+(i!=null?'<a style="color:var(--acc)" onclick="zoom('+i+')">'+esc((it.title||"").slice(0,70))+"</a>":esc(id))+'</a></b> — '+esc(per[id])+"</div>"}).join(""):"")+
  (vd.missing&&vd.missing.length?'<div class="stt" style="margin-top:8px">Jo cheez neechi videos me nahi — aazma kar dekho</div><ul class="sub">'+vd.missing.map(p=>"<li>"+esc(p)+"</li>").join("")+"</ul>":"")+
  (v.raw?'<div class="stt" style="margin-top:8px">Model ka jawab plain text me (JSON nahi ban paya — jaisa aaya waisa)</div><div class="trbox">'+esc(v.raw)+"</div>":"")+
  '<div class="bar" style="margin-top:8px"><button class="sm" onclick="vdGo(true)">'+ico("refresh",13)+"naya jawab laao (dobara model se)</button></div></div>"}
function W_N(d){const W=winOf(d);return W.on?W.win.length:0}
// "Jeet ka formula" — koi model nahi, sirf apne hi naape gaye numbers ka tulna:
// jeetne wala group (median se 2×+) banam baaki naapi gayi videos. Ye card pattern
// dikhata hai, wajah dawa nahi karta — is liye har row ke saath label hai aur group
// 5 se chhota ho to card dikhta hi nahi (chhote group ka "farak" andhla hota hai).
function formulaOf(d,W){if(!W.on||W.win.length<5)return"";
 const meas=d.items.filter(it=>vpd(it)>0),win=meas.filter(it=>vpd(it)>=2*W.med),rest=meas.filter(it=>vpd(it)<2*W.med);
 if(win.length<5||rest.length<5)return"";
 const G=g=>({n:g.length,
  len:medv(g.map(it=>(it.title||"").length)),
  num:Math.round(100*g.filter(it=>/\d/.test(it.title||"")).length/g.length),
  caps:Math.round(100*g.filter(it=>/[A-Z]{3,}/.test(it.title||"")).length/g.length),
  q:Math.round(100*g.filter(it=>/\?|kaise|kyun|kyu\b|kya\b/i.test(it.title||"")).length/g.length),
  tagp:Math.round(100*g.filter(it=>Array.isArray(it.tags)&&it.tags.length>0).length/g.length),
  tn:(()=>{const a=g.filter(it=>it.ts).map(it=>it.ts.n||0);return a.length>=5?medv(a):null})(),
  ta:(()=>{const a=g.filter(it=>it.ts).map(it=>it.ts.area||0);return a.length>=5?medv(a):null})(),
  facep:Math.round(100*g.filter(it=>(it.faces||[]).length>0).length/g.length),
  fs:(()=>{const a=g.filter(it=>(it.faces||[]).length).map(it=>Math.max(...it.faces.map(f=>f.area||0)));return a.length>=5?medv(a):null})()});
 const A=G(win),Bx=G(rest);
 const anyTags=meas.some(it=>Array.isArray(it.tags));
 const r=(lab,va,vb,fmtv)=>{const f=(x)=>x==null?"—":(fmtv||String)(x);
  return '<tr><td class="l no">'+lab+'</td><td class="no"><b>'+f(va)+'</b></td><td class="no">'+f(vb)+'</td></tr>'};
 return '<div class="sec">Jeet ka formula? <small> — sirf apne naape ka tulna: jeetne wali ('+A.n+') banam baaki naapi gayi ('+Bx.n+'). Sah-sambandh dikha sakta hai, wajah sabit nahi karta — group chhote hain to farak ka bharosa kam.</small></div>'+
  '<div class="card"><div class="stt">Ye cheezein dono group me kitni hain</div>'+
  '<div class="stscr"><table class="stt"><thead><tr><th scope="col" class="l no">feature</th><th scope="col" class="no">jeetne wali ('+A.n+')</th><th scope="col" class="no">baaki ('+Bx.n+')</th></tr></thead><tbody>'+
  r("title ki lambai (median akshar)",A.len,Bx.len)+
  r("title me number",A.num,Bx.num,x=>x+"%")+
  r("title me CAPS shabd (3+ bade akshar)",A.caps,Bx.caps,x=>x+"%")+
  r("title me sawal (kaise/kya/? )",A.q,Bx.q,x=>x+"%")+
  (anyTags?r("tags diye hue videos",A.tagp,Bx.tagp,x=>x+"%"):'<tr><td>tags</td><td colspan="2">is scan me tags laaye hi nahi gaye — scan ke waqt "asli tags + description" band tha; is feature par kuch nahi kaha ja sakta</td></tr>')+
  r("thumbnail par text ke shabd (median)",A.tn,Bx.tn)+
  r("thumbnail par text ka area % (median)",A.ta,Bx.ta,x=>x==null?"—":x+"%")+
  r("chehra wale thumbnails",A.facep,Bx.facep,x=>x+"%")+
  r("chehre ka size (frame ka % area, median)",A.fs,Bx.fs,x=>x==null?"—":x+"%")+
  '</tbody></table></div><div class="sub" style="margin-top:6px">Ye ginti hamari hai, faisla aapka: farak dikhna matlab ye nahi ke usse views badhte hain — ho sakta hai dono kisi teesri cheez ka natija hon. Pakke test ke liye: apne channel par ek feature badal kar do-saaf snapshot lein aur views/day ka farak khud naapein (Me/History wala rasta).</div></div>'}
async function vdGo(force){if(!D)return;VDQ=true;cmp();
 let r;try{r=await j("/api/verdict?id="+encodeURIComponent(cur)+(force?"&force=1":""))}catch(e){r={error:e.message}}
 VDQ=false;D.vd={id:cur,data:r};cmp();
 if(r.error)toast("model verdict: "+r.error)}
async function homev(){const _t=RTN;
 if(!SCANS.length){
  $("#main").innerHTML='<h2>'+ico("home",22)+' Home</h2>'+
   esCard({i:"spark",t:"Abhi koi scan nahi — shuruaat yahin se hoti hai",
    p:"<b>Topic scan:</b> kisi topic ki top videos ke thumbnails naapo — pata chalega log asal me kya kar rahe hain. <b>Channel scan:</b> apne poore channel ki har video naapo. Har scan yahin save hota hai aur Home par number bankar dikhta hai.",
    b:'<div class="bar"><button class="go" onclick="newScan()">'+ico("plus",14)+'New topic scan</button><button class="go" onclick="goNewChan()">'+ico("search",14)+'Open a channel</button></div>'});
  return}
 spin();const d=await ensureData();if(_t!==RTN)return;
 const tot=SCANS.reduce((a,s)=>a+(s.kept||0),0),
  nch=SCANS.filter(s=>s.kind==="channel").length,tp=SCANS.length-nch,
  last=Math.max.apply(null,SCANS.map(actTs));
 let h='<div class="ph"><h1>'+ico("home",22)+' Home'+
  '<span class="ipill" style="color:var(--acc);border-color:rgba(var(--accrgb),.4)">'+SCANS.length+" scans on record</span></h1>"+
  '<div class="sub">Har number kisi naape gaye scan ka hai. "Benchmark" ka matlab hamesha <b>usi scan ke videos ka median</b> hai — koi internet ka average nahi.</div>'+
  '<div class="row"><button class="go" onclick="newScan()">'+ico("plus",14)+'New topic scan</button>'+
  '<button class="go" onclick="goNewChan()">'+ico("search",14)+'Open a channel</button>'+
  '<button class="sm" onclick="go(\'act\')">'+ico("clock",14)+'Scan history</button>'+
  '<span class="telem">'+ico("check",14)+'<b>'+fmt(tot)+'</b>&nbsp;videos measured</span>'+
  '<span class="telem">'+ico("clock",14)+'last scan '+(last?actAgo((Date.now()-last)/1000):"—")+"</span></div></div>";
 h+='<div class="kpi">'+kpi("scans on record",String(SCANS.length),"var(--acc)")+
    kpi("videos measured",fmt(tot))+kpi("channel scans",String(nch))+kpi("topic scans",String(tp))+"</div>";
 const its=((D&&D.items)||[]).filter(it=>it.views!=null&&it.thumb),
  med=medv(its.map(vpd).filter(x=>x>0)),chn=d&&d.kind==="channel";
 if(its.length){
  const pub=its.filter(it=>it.pubts).sort((a,b)=>b.pubts-a.pubts),
   fast=its.slice().sort((a,b)=>vpd(b)-vpd(a)),
   hero=chn?(pub[0]||null):fast[0];
  let left;
  if(hero){
   const hv=vpd(hero),idx=(D.items||[]).indexOf(hero),
    pct=med?Math.min(100,Math.round(hv/(med||1)*100)):0,rate=med?hv/med:null;
   left='<div class="card"><div class="chd">'+ico(chn?"clock":"trophy",20)+"<b>"+
    (chn?"Aap ki latest video vs benchmark":"Is scan ki sab se tez video vs benchmark")+
    '</b><span class="sp"></span><span class="pill"><i></i>'+its.length+" measured</span></div>"+
    '<img class="hbig" loading="lazy" alt="" src="'+imgu(hero.thumb)+'">'+
    '<div style="margin-top:10px"><b style="font-size:var(--fs-sub)">'+esc(hero.title)+'</b>'+
    '<div class="sub" style="margin-top:4px">'+esc((hero.channel||"").slice(0,60))+
    (hero.upload?" · chhapne ka din "+esc(hero.upload):"")+"</div>"+
    '<div class="mrow"><div><span>views (asli)</span><b>'+fmt(hero.views)+"</b></div>"+
    '<div><span>views/day</span><b style="color:var(--acc)">'+fmt(hv)+"</b></div>"+
    '<div><span>score</span><b style="color:'+(hero.score!=null?cc(hero.score):"var(--tx)")+'">'+
    (hero.score!=null?hero.score+"/100":"—")+"</b></div></div>";
   if(med)left+='<div class="vsbar"><i style="width:'+pct+'%"></i></div><div class="sub">'+
    "benchmark (isi scan ka median views/day) <b>"+fmt(med)+"</b> — ye video <b style=\"color:"+
    (rate>=1?"var(--grn)":"var(--bad)")+"\">"+(rate>=1?"×"+rate.toFixed(1)+" tez":"×"+rate.toFixed(2)+" — median se kam")+"</b></div>";
   left+='<div class="bar" style="margin-top:10px">'+ytb(hero.url)+ytc(hero.url)+
    (idx>=0?'<button class="go" onclick="zoom('+idx+')">'+ico("eye",14)+"poora analysis</button>":"")+
    '<button class="sm" onclick="go(\''+(chn?"ch":"cmp")+'\')">'+ico("list",14)+"poora table</button></div></div>"}
  else left='<div class="card"><div class="chd">'+ico("clock",20)+"<b>Latest video vs benchmark</b></div>"+
    '<div class="sub">Is channel ki videos me publish ka poora waqt metadata me nahi mila, is liye "latest" theek se nahi chun sakta. Channel Analytics me <b>waqt bharo</b> se sirf metadata dobara padhi jaati hai — ye card bhar jaata hai.</div>'+
    '<div class="bar" style="margin-top:10px"><button class="go" onclick="go(\'ch\')">'+ico("eye",14)+"Channel Analytics</button></div></div>";
  let right='<div class="card"><div class="chd">'+ico("trend",20)+"<b>Top performers — views/day se</b>"+
   '<span class="sp"></span><span class="pill">median '+(med?fmt(med):"—")+"</span></div>"+
   fast.slice(0,3).map((it,i)=>{const v=vpd(it);
    return '<div class="prow" style="margin-bottom:8px"><img loading="lazy" alt="" src="'+imgu(it.thumb)+'">'+
     '<div class="pm"><b>'+(i+1)+". "+esc(it.title)+'</b><div class="d">'+
     esc((it.channel||"").slice(0,40))+" · "+fmt(it.views)+" views / "+(it.days||"?")+" din</div></div>"+
     '<div class="pv"><b>'+fmt(v)+'</b><span>views/day'+(med?" · ×"+(v/med).toFixed(1):"")+"</span></div></div>"}).join("")+
   '<div class="bar" style="margin-top:10px"><button class="sm" onclick="go(\'deep\')">'+
    ico("bars",14)+"kaunsi cheez sach me chalti hai — Deep Analysis</button></div></div>";
  h+='<div class="hsplit">'+left+right+"</div>";
  h+='<div class="card" style="margin-top:14px"><div class="chd">'+ico("trophy",20)+
   "<b>Jeete hue topics → naye ideas</b>"+
   '<span class="sp"></span><button class="sm" onclick="go(\'ideas\')">poora Ideas page</button></div>'+
   '<div id="hideas"><div class="sub">jeeton ki title/tags se preview nikaal raha hoon…</div></div></div>';
 }
 else h+='<div class="card" style="margin-top:14px"><div class="chd">'+ico("info",20)+
   (cur?"<b>Is scan par abhi kafi naap nahi hai</b>":"<b>Koi scan khula nahi hai</b>")+"</div>"+
   '<div class="sub">'+(cur?"Home ke video cards ke liye videos ka views-naap chahiye. Channel scan me <b>Poora channel naap lo</b>, ya topic scan dobara chalao — baqi cards tab bhi nahi bane.":"Neeche Recent scans ki list se koi scan kholo, ya ek naya scan chalao — dashboard usi naap se bharta hai.")+'</div>'+
   '<div class="bar" style="margin-top:10px">'+(cur?'<button class="go" onclick="go(\'ch\')">'+ico("eye",14)+"Channel Analytics</button>":
    '<button class="go" onclick="newScan()">'+ico("plus",14)+'New topic scan</button><button class="go" onclick="goNewChan()">'+ico("search",14)+"Open a channel</button>")+"</div></div>";
 const L=SCANS.slice().sort((a,b)=>actTs(b)-actTs(a)).slice(0,5);
 h+='<div class="card" style="margin-top:14px"><div class="chd">'+ico("clock",20)+"<b>Recent scans</b>"+
  '<span class="sp"></span><button class="sm" onclick="go(\'act\')">poori Scan history</button></div>'+
  '<div class="st stscr"><table class="stt"><thead><tr><th class="l no">When</th><th class="l no">Target</th><th class="l no">Type</th><th class="no">Measured</th><th class="no">Action</th></tr></thead><tbody>'+
  L.map(s=>{const chn2=s.kind==="channel",t=actTs(s),
   abs2=t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}):"—";
   return '<tr class="srow" onclick="actRestore(\''+esc(s.id)+'\')" title="restore this scan as the current one">'+
    '<td class="l"><b>'+abs2+'</b><span class="d">'+(t?actAgo((Date.now()-t)/1000):"")+"</span></td>"+
    '<td class="l"><b>'+esc(chn2?(s.ch||{}).name||s.topic:s.topic)+"</b></td><td class=\"l\">"+
    (chn2?'<span class="ipill" style="color:var(--nic);border-color:rgba(59,130,246,.4)">CHANNEL</span>':
     '<span class="ipill" style="color:var(--acc);border-color:rgba(var(--accrgb),.4)">TOPIC</span>')+
    (s.id===cur?' <span class="ipill ok">current</span>':"")+'</td><td><b>'+s.kept+"</b></td>"+
    '<td><button class="sm" onclick="event.stopPropagation();actRestore(\''+esc(s.id)+'\')">restore</button></td></tr>'}).join("")+
  "</tbody></table></div></div>";
 $("#main").innerHTML=h;
 // Ideas strip: /api/ideas ka chhota preview (sirf jeete hue) — poora kaam Ideas page par hi
 if($("#hideas")){j("/api/ideas?id="+encodeURIComponent(cur)+"&k=3").then(x=>{
   const el=$("#hideas");if(!el)return;
   if(x.error){el.innerHTML='<div class="sub">'+esc(x.error)+"</div>";return}
   el.innerHTML=(x.winners||[]).slice(0,3).map(v=>'<div class="prow" style="margin:0 0 8px">'+
    '<img loading="lazy" alt="" src="'+imgu(v.thumb||"")+'">'+
    '<div class="pm"><b>'+esc(v.title)+'</b><div class="d">'+esc((v.channel||"").slice(0,40))+
    " · "+fmt(v.views)+" views / "+(v.days||"?")+" din</div></div>"+
    '<div class="pv"><b>'+fmt(v.vpd)+'</b><span>views/day</span></div></div>').join("")+
    '<div class="sub">'+x.n+" videos me se "+x.win_n+" jeete chune gaye — in ke tags/titles se banne wale "+
    x.ideas.length+" ideas Ideas page par hain.</div>"}).catch(()=>{
   const el=$("#hideas");if(el)el.innerHTML='<div class="sub">ideas ka preview abhi na ban saka — Ideas page par jaayein to wahan ban jayega.</div>'})}
}


async function boot(){try{if(localStorage.getItem("cl_nav")==="off")document.body.classList.add("navoff")}catch(e){}const d=await j("/api/scans");SCANS=d.scans;YTOK=d.yt===true;YTN=d.ytn||0;if(d.trg)TRG=d.trg;try{TOOLS=await j("/api/tools")}catch(e){}
 try{SYS=await j("/api/sys")}catch(e){}
 // Engine bhaari hain is liye background me tayyar hote hain — tool foran khulta hai.
 // Jab tak wo aa na jayen status line ka engine naam dobara poocha jaata hai, taake
 // galat naam dikhne ke bajaye sahi naam thori der baad aa jaye.
 if(SYS&&SYS.warm&&(SYS.warm.ocr_loading||SYS.warm.sk_loading)){let n=0;
  const t=setInterval(async()=>{try{const x=await j("/api/sys");if(x&&x.warm){SYS=x;
   if((SYS.warm.ocr&&SYS.warm.sk)||++n>12){clearInterval(t);if(!D&&view==="cmp")render()}}}
   catch(e){clearInterval(t)}},1200)}
 if(!SCANS.some(s=>s.id===cur))cur=SCANS.length?SCANS[0].id:"";
 fromHash();render()}
function newScan(){TOPIC="";D=null;cur="";go("cmp");const e=$("#tq");if(e)e.focus()}
// Channel dhoondhne ka raga alag: Channel Analytics ke form me le jao, aur box
// kholte hi focus wahi lage (topic scan ka form idhar #tq hai, wahan #cq).
function goNewChan(){D=null;cur="";CHC=null;go("ch");
 let n=0;const t=setInterval(()=>{const e=$("#cq");if(e){e.focus();clearInterval(t)}
  if(++n>25)clearInterval(t)},120)}
async function delScan(){if(!cur)return;if(!confirm("Ye scan hatao?"))return;await j("/api/del?id="+cur);cur="";D=null;await boot();toast("hata diya")}
async function delChan(){const s=($("#csel")||{}).value||"";if(!s)return toast("pehle channel chuno jo hatana hai","warn");
 if(!confirm("Ye channel hatao? Is ka scan aur uski history delete ho jayegi — wapas lane ke liye channel dobara scan karna padega."))return;
 await j("/api/del?id="+encodeURIComponent(s));if(cur===s){cur="";D=null}await boot();toast("channel hata diya")}
// ---------- Jeete hue topics → ideas ----------
// "Jeet" ka naap views/day hai, aur har suggestion ka source wo video hai jahan se wo
// tag/title/text aaya. Ye view khud koi text nahi banata — jo dikhta hai wo scan me hai.
async function aiInfo(){if(AIINFO&&AIINFO.models&&AIINFO.models.length)return;
 try{AIINFO=((await j("/api/ai"))||{}).info||{}}catch(e){AIINFO=AIINFO||{}}}
async function ideasv(){const _t=RTN;
 if(!cur){noScan();return}
 if(IDEAS&&IDEAS.id!==cur){IDEAS=null;IDEAR={}}
 await aiInfo();if(_t!==RTN)return;
 const kk=(IDEAS&&IDEAS.k_want)||10;
 $("#main").innerHTML='<h2>'+ico("trophy",22)+' Jeete hue topics → ideas</h2>'+
  '<div class="sub">Ye tab us scan ke videos ko <b>views/day</b> (views ÷ umr) se napta hai, sabse zyada chalne wale <b>jeete hue</b> chunta hai — ek channel se zyada se zyada 2, warna ek hi channel poori list le leta hai. Phir inhi jeeton ke <b>titles</b>, un par lage <b>asli tags</b> (jo us channel ne khud lagaye the) aur un thumbnails par likhe <b>asli text</b> (OCR) se naye topics, titles, tags, keywords aur thumbnails banata hai. Har cheez ke saath wo video likha hai jahan se wo aayi hai — aap khud khol kar dekh sakte hain.</div>'+
  '<div class="card"><div class="bar"><label class="sub">kitne ideas <select id="ik"><option value="6">6</option><option value="10">10</option><option value="15">15</option></select></label>'+
  '<button class="go" id="igo">'+ico("trophy",16)+'jeeton se ideas nikaalo</button><span class="sub" id="ist"></span></div>'+
  '<div class="sub">Jo topic baaki videos me bhi utna hi chalta hai wo idea nahi mana jaata — naya wahi hai jo <b>jeeton me zyada</b> aur baaki me kam ho. Neeche ke title patterns <b>sah-observed</b> hain (jeeton me zyada dikhe), is chhote n par unka saboot nahi — jo patterns statistically significant nikle the, sirf wahi <a style="color:var(--acc)" onclick="go(&quot;deep&quot;)">Deep Analysis</a> me p aur n ke saath likhe hain.</div></div>'+
  '<div id="iout">'+skelLines(4,"ideas ban rahe hain…")+'</div>'+
   '<div class="card" style="margin-top:14px"><h3>Bahar ki garmahat — Reddit + Google Trends</h3>'+
   '<div class="sub">Ye ideas ke liye madad hai, naap nahi. <b>Reddit</b>: log aapke topic me asal me kya poochh rahe hain — community ka likha hua, Reddit ke public JSON se (<b>unofficial</b>; Reddit kabhi block karta hai to saaf error dikhega, jhooth nahi). <b>Google Trends</b>: topic ka search interest 12 mahine me upar ja raha hai ya neeche — <b>pytrends</b> se (<b>unofficial</b>; ye 0–100 ka nisbat hai, exact search ginti nahi). Dono me koi API key nahi, koi paisa nahi.</div>'+
   '<div class="bar"><input type="text" id="hq" placeholder="topic (wahi jo scan ka hai, ya koi aur)" style="min-width:340px" value="'+esc(TOPIC)+'" onkeydown="if(event.key===String.fromCharCode(13))hotGo()">'+
   '<button class="go" onclick="hotGo()">dhoondo</button></div><div id="hqout"></div></div>';
 if($("#ik"))$("#ik").value=String(kk);
 $("#igo").onclick=ideaRun;
 if(IDEAS)renderIdeas();else ideaRun();
}
async function ideaRun(){
 const k=Number(($("#ik")||{}).value||10),b=$("#igo"),s=$("#ist"),o=$("#iout");
 if(b)b.disabled=true;if(s)s.textContent="nap raha hoon… (jeet-chunal, title patterns, asli tags, TF-IDF se topics)";
 if(o)o.innerHTML=skelLines(4,"kuch aur idea ban raha hai…");
 let d;try{d=await j("/api/ideas?id="+encodeURIComponent(cur)+"&k="+k)}
 catch(e){if(b)b.disabled=false;if(s)s.textContent="";if(o)o.innerHTML='<div class="err">'+esc(e.message)+'</div>';return}
 if(b)b.disabled=false;
 if(d.error){if(s)s.textContent="";if(o)o.innerHTML='<div class="err">'+esc(d.error)+'</div>';return}
 d.k_want=k;IDEAS=d;IDEAR={};renderIdeas();
 if(s)s.textContent=d.n+" videos · "+d.win_n+" jeete vs "+d.rest_n+" baaki · "+d.ideas.length+" ideas banaye";
}
function renderIdeas(){const o=$("#iout");if(!o||!IDEAS)return;o.innerHTML=ideaTbl(IDEAS)+ideaCards(IDEAS)}
// Bahar ki garmahat: Reddit (community ke sawal) + Google Trends (interest ka direction).
// Dono unofficial hain — ye baat har section ke sir-e-khwan par likhi jaati hai.
async function hotGo(){const t=(($("#hq")||{}).value||TOPIC||"").trim();if(!t)return toast("topic likho");
 const o=$("#hqout");if(o)o.innerHTML=skelLines(3,"Reddit aur Google Trends dono se poochha ja raha hai… (10–20 second lag sakte hain)");
 const rd=await j("/api/reddit?topic="+encodeURIComponent(t)).catch(e=>({error:e.message}));
 const tr=await j("/api/trends?topic="+encodeURIComponent(t)).catch(e=>({error:e.message}));
 if(!$("#hqout"))return;
 let h="";
 if(rd.error)h+='<div class="sec">Reddit</div><div class="err">✗ '+esc(rd.error)+'</div>';
 else h='<div class="sec">Reddit — log asal me kya poochh rahe hain <small> — community ka likha hua (Reddit public feed, unofficial); ye demand ka signal hai, koi naap nahi</small></div>'+
  '<div class="card">'+(rd.posts||[]).slice(0,12).map(p=>'<div class="v"><b class="'+(p.score!=null&&p.score>=500?"ok":"warn")+'">'+(p.score!=null?fmt(p.score):"—")+'</b><div><a href="'+esc(p.url)+'" target="_blank" rel="noopener" style="color:var(--tx);text-decoration:none;font-weight:600">'+esc(p.t)+'</a>'+
   '<div class="sub">r/'+esc(p.sub)+(p.score!=null?' · upar vote '+fmt(p.score)+' · '+p.cmts+' jawab':'')+(p.date?' · '+esc(p.date):'')+' · saal bhar ke top me se</div></div></div>').join("")+'</div>'+
   (rd.via==="rss"?'<div class="sub">Ye Reddit ke <b>RSS feed</b> se aaya hai (JSON feed ne is network par 403 diya). Sach: RSS me vote aur jawab ki ginti nahi hoti — isliye wo dikh hi nahi rahe, sirf sawal dikh rahe hain. Number ka koi dawa nahi.</div>':"")+
   '<div class="sub">In sawalon ko title me seedha istaal kar sakte hain — jo cheez log poochh rahe hain wahi video banane par milti hai. Ye data Reddit ka diya hua hai, humne sirf dikhaya hai.</div>';
 if(tr.error)h+='<div class="sec" style="margin-top:10px">Google Trends</div><div class="err">✗ '+esc(tr.error)+'</div>';
 else{const s=tr.series||[],mx=Math.max.apply(null,s)||1;
  h+='<div class="sec" style="margin-top:10px">Google Trends — 12 mahine ka interest <small> — pytrends se (Google ka unofficial data); ye 0–100 ka nisbat hai, exact search ginti nahi</small></div>'+
   '<div style="display:flex;align-items:flex-end;gap:1px;height:56px;background:var(--panel2);border-radius:var(--r1);padding:4px">'+s.map(v=>'<i style="display:block;flex:1;height:'+Math.max(2,Math.round(v*56/mx))+'%;background:var(--acc);opacity:.75;border-radius:1px"></i>').join("")+'</div>'+
   '<div class="sub">dira: <b style="color:'+(tr.dir==="barh raha"?"var(--grn)":tr.dir==="gir raha"?"var(--red)":"var(--mut)")+'">'+esc(tr.dir)+'</b> (aakhri aadha vs pehla aadha) · '+esc(tr.from)+' se '+esc(tr.to)+' tak · '+s.length+' hafte dikhaye gaye</div>'+
   ((tr.rel||[]).length?'<div class="sub" style="margin-top:6px"><b>Related queries (Google ka apna diya hua, unofficial):</b></div><div>'+tr.rel.map(q=>'<span class="chip">'+esc(q.q)+(q.k==="rising"?' <b style="color:var(--grn)">uddne wala</b>':" · "+q.v)+'</span>').join("")+'</div>':"")+
   '<div class="sub" style="margin-top:6px">Ye chart sirf ye batata hai ke topic ka interest upar hai ya neeche — views ki guarantee nahi. "uddne wala" queries naye shuru hone wale topics hain; in par topic scan chalana asli kaam hai.</div>';}
 o.innerHTML=h}
function ideaTbl(d){
 const w=(d.winners||[]).map((v,i)=>'<tr><td>'+(i+1)+'</td><td class="l"><div class="bwrap"><img src="'+imgu(v.thumb||"")+'" style="width:132px;border-radius:var(--r1)" loading="lazy">'+
  (v.score!=null?'<span class="badge" style="color:'+cc(v.score)+'">'+v.score+'</span>':"")+'</div></td>'+
  '<td class="l"><a href="'+esc(v.url||"#")+'" target="_blank" rel="noopener" style="color:var(--tx);text-decoration:none;font-weight:600">'+esc(v.title)+'</a>'+
  '<div class="sub">'+esc(v.channel||"")+' · '+fmt(v.views)+' views / '+(v.days||"?")+' din · subs '+(v.subs?fmt(v.subs):"—")+' · asli tags '+(v.tags_n||0)+(v.nch?" · chapters "+v.nch:"")+(v.words!=null?' · text '+v.words+' shabd, '+(v.h320||0)+'px@320':"")+'</div>'+
  (v.text?'<div class="sub">us ke thumbnail par likha: “'+esc(v.text)+'”</div>':"")+'</td>'+
  '<td class="num" style="color:var(--acc);font-weight:700">'+fmt(v.vpd)+'</td><td>'+ytb(v.url,"kholo")+ytc(v.url)+'</td></tr>').join("");
 const p=(d.patterns||[]).map(x=>{const dd=Math.round(x.wr-x.lr);
  return '<tr><td class="l">'+esc(x.lab)+'</td><td>'+x.win+'/'+x.win_n+'</td><td>'+x.lose+'/'+x.lose_n+'</td>'+
  '<td class="num lift" style="color:'+(dd>0?"var(--grn)":dd<0?"var(--red)":"var(--mut)")+'">'+(dd>0?"+":"")+dd+'%</td></tr>'}).join("");
 const tg=(d.tags||[]).slice(0,18).map(x=>'<tr><td class="l">'+esc(x.t)+'</td><td style="color:var(--grn)">'+x.win+'</td><td>'+x.rest+'</td></tr>').join("");
 const ph=(d.phrases||[]).map(x=>'<tr><td class="l">'+esc(x.p)+'</td><td>'+x.win+'</td><td>'+x.rest+'</td><td class="l sub">'+esc(x.src||"")+'</td></tr>').join("");
 return '<div class="kpi">'+kpi("videos napay gaye",d.n)+kpi("jeete (views/day se)",d.win_n,"var(--grn)")+
  kpi("jeeton ka median views/day",fmt(d.win_vpd_med),"var(--acc)")+kpi("baaki ka median views/day",fmt(d.rest_vpd_med))+'</div>'+
 '<div class="sub">topics dhoondne ka tareeqa: <b>'+esc(d.method||"—")+'</b> — sirf umer (candidates) nikalne ke liye, phir har candidate ka support <b>asli ginti</b> se naapa gaya hai (jeeton ke kitne videos me hai aur baaki ke kitne me). Jiska support exact nahi mila, wo idea nahi bana.</div>'+
 '<div class="st"><div class="st-bar"><b>Jeete hue — poori list <small> — ye wahi videos hain jin ke titles, tags aur thumbnail-text se neeche ke ideas bane hain</small></b><span class="sp"></span></div>'+
 '<table class="stt"><thead><tr><th scope="col" class="no">#</th><th scope="col" class="l no">thumbnail</th><th scope="col" class="l no">title / channel / us par kya likha</th><th scope="col" class="no">views/day</th><th scope="col" class="no"></th></tr></thead><tbody>'+w+'</tbody></table></div>'+
 '<div class="cmp2"><div><div class="sec">Title patterns — jeeton me vs baaki me</div><table class="stt"><thead><tr><th scope="col" class="l no">pattern</th><th scope="col" class="no">jeete</th><th scope="col" class="no">baaki</th><th scope="col" class="no">farak</th></tr></thead><tbody>'+p+'</tbody></table>'+
 '<div class="sub">ye sirf ginti hai, isliye ye n = '+d.n+' par saboot nahi. Neeche ke titles inhi patterns ke <b>asli jeeton se utaar kar</b> banaye gaye hain, isliye har title ke neeche source video likha hai.</div></div>'+
 '<div><div class="sec">Jeeton par lage ASLI tags — kitne videos me mile</div><table class="stt"><thead><tr><th scope="col" class="l no">tag</th><th scope="col" class="no">jeeton me</th><th scope="col" class="no">baaki me</th></tr></thead><tbody>'+tg+'</tbody></table>'+
 '<div class="sub">ye tags un channels ne khud lagaye the (yt-dlp se liye gaye), isliye ye topic ki sabse bharosemand listing hai — mera likha hua nahi.</div></div></div>'+
 '<details><summary>aur topics jo dhundhe gaye — candidate phrases aur unka asli support</summary><table class="stt"><thead><tr><th scope="col" class="l no">phrase</th><th scope="col" class="no">jeeton me</th><th scope="col" class="no">baaki me</th><th scope="col" class="l no">kahan se mila</th></tr></thead><tbody>'+ph+'</tbody></table>'+
 '<div class="sub">jo phrase neeche idea nahi bana, wo isliye nahi bana ke wo baaki videos me bhi utna hi chal raha tha, ya kisi poore phrase ka tukra tha.</div></details>'}
function ideaCards(d){
 return '<div class="sec">'+d.ideas.length+' ideas — topic, titles, tags, keywords, thumbnails <small> — har idea us evidence se bana hai jo uske andar likha hai</small></div><div class="ideas">'+
  d.ideas.map((I,i)=>ideaCard(I,i,d)).join("")+'</div>'}
function ideaCard(I,i,d){
 const tb=I.thumb_brief||{};
 const ev='<span class="chip">jeeton me <b>'+I.win_sup+'/'+d.win_n+'</b> ('+I.win_rate+'%)</span>'+
  '<span class="chip">baaki videos me <b>'+I.rest_sup+'/'+d.rest_n+'</b> ('+I.rest_rate+'%)</span>'+
  '<span class="chip">farak <b style="color:'+(I.diff>0?"var(--grn)":"var(--red)")+'">'+(I.diff>0?"+":"")+Math.round(I.diff*100)+'%</b></span>'+
  '<span class="chip">is topic par scan me hi <b>'+I.compete+'</b> videos hain — un ka median '+fmt(I.compete_vpd_med)+' views/day</span>'+
  '<span class="chip">jeeton ka median <b style="color:var(--acc)">'+fmt(I.win_vpd_med)+'</b> · baaki '+fmt(I.rest_vpd_med)+'</span>';
 const src='<span class="chip">'+esc(I.src||"")+'</span>'+(I.from||[]).map(x=>'<span class="tag" title="'+esc(x.title)+'" onclick="window.open(&quot;'+esc(x.url||"#")+'&quot;,&quot;_blank&quot;)">'+fmt(x.vpd)+' vpd · '+esc((x.channel||"").slice(0,18))+'</span>').join("");
 const ti=(I.titles||[]).map((s,k)=>'<div class="sug"><span class="t">'+esc(s.t)+'</span><span class="n">'+s.t.length+' ch</span>'+
  '<button class="sm" onclick="ideaCopy('+i+','+k+')">'+ico("copy",14)+'copy</button>'+
  '<div class="why" style="flex:1 0 100%"><b>'+esc(s.pat||"")+'</b> — '+esc(s.why||"")+
  (s.src_title?'<br><span class="sub">source: '+(s.src_vpd!=null?fmt(s.src_vpd)+' views/day · ':"")+esc(s.src_title)+'</span>':"")+'</div></div>').join("");
 const tg=(I.tag_rows||[]).map(x=>'<span class="tag" title="jeeton me '+x.win+' videos me laga, baaki me '+x.rest+'">'+esc(x.t)+' <b>'+x.win+'</b></span>').join("");
 const kw=(I.keywords||[]).map(x=>'<span class="tag">'+esc(x)+'</span>').join("");
 const tt=(I.thumb_texts||[]).map(x=>'<span class="chip" title="us jeetne wale ke thumbnail par OCR se padha gaya — '+fmt(x.vpd)+' views/day">“'+esc(x.t)+'” <b>'+fmt(x.vpd)+'</b></span>').join("");
 const fr=(I.from||[]).map(x=>'<div class="sub" style="margin-top:6px">· '+fmt(x.vpd)+' views/day — '+esc((x.title||"").slice(0,90))+'</div>').join("");
 const key=!!(AIINFO&&AIINFO.key);
 const gen='<div class="bar" style="margin-top:4px"><label class="sub">reference se kitna door <select id="istr'+i+'">'+
   '<option value="0.30">0.30 — bilkul naya scene</option><option value="0.55" selected>0.55 — inspired (default)</option><option value="0.80">0.80 — reference ke qareeb</option></select></label>'+
   (key?'<button class="go" onclick="ideaGen('+i+')">'+ico("palette",16)+'is topic par thumbnail banao</button>'
       :'<button class="go" disabled>'+ico("palette",16)+'AI ab nahi banega</button>')+
   '<button class="sm" onclick="ideaAI('+i+')">'+ico("ext",14)+'AI tab me kholo (model / size / text)</button></div>'+
   (key?'<div class="sub">reference = us jeetne wale ka thumbnail jiska views/day <b>'+fmt(I.ref_vpd)+'</b> tha; strength slider yahi decide karta hai ke naya scene kitna naya ho. Har bani tasveer ko <b>wahi OCR + analysis</b> se napa jata hai jo competitors ko napa gaya tha, aur us jeetne wale ke median se saath rakha jata hai. Kharcha Runware ke apne hisaab se neeche dikhta hai.</div>'
       :'<div class="sub">Runware key set nahi — <b>nayi</b> tasveer AI se tabhi banegi. Key <a style="color:var(--acc)" onclick="go(&quot;ai&quot;)">AI tab</a> me daal dein to ye button chalne lagega; tab tak <b>Behtar banao</b> (apni ya kisi bhi competitor ki photo sudharna) bilkul muft hai.</div>');
 return '<div class="card idea"><div class="rank"><i>'+I.n+'</i><h4>'+esc(I.topic)+'</h4></div>'+
  '<div>'+ev+'</div><div>'+src+'</div>'+
  '<div class="lbl">behtar titles — inhi jeeton ke structure se utaar kar</div>'+ti+
  '<div class="bar"><button class="sm" onclick="ideaCopyTags('+i+')">'+ico("copy",14)+'saare tags copy (YouTube ke tag box me paste karein)</button>'+
  '<button class="sm" onclick="ideaCopyKw('+i+')">'+ico("copy",14)+'keywords copy</button></div>'+
  '<div class="lbl">us topic ke liye tags — jo jeeton par lage the (asli)</div>'+(tg||'<span class="sub">is topic par koi asli tag nahi mila</span>')+
  (kw?'<div class="lbl">keywords (jo shabd inhi jeeton me saath me aate hain)</div>'+kw:"")+
  '<div class="lbl">in '+tb.n_hits+' jeeton ke thumbnails ka mizaj (naapa hua)</div>'+
  '<span class="chip">shabd median <b>'+tb.words_med+'</b></span><span class="chip">text height median <b>'+(tb.h320_med||0)+'px @320</b></span>'+
  '<span class="chip">chehra wale <b>'+tb.faces+'/'+tb.n_hits+'</b></span>'+
  (tt?'<div class="lbl">un par jo ASLI text padha gaya (OCR) — scene ka idea yahin se</div>'+tt:"")+
  '<div class="lbl">ye idea kin jeeton se bana (source videos)</div>'+fr+
  gen+'<div id="ires'+i+'"></div></div>'}
function ideaCopy(n,k){const I=((IDEAS||{}).ideas||[])[n]||{};cpText(((I.titles||[])[k]||{}).t||"")}
function ideaCopyTags(n){const I=((IDEAS||{}).ideas||[])[n]||{};cpText((I.tags||[]).join(", "))}
function ideaCopyKw(n){const I=((IDEAS||{}).ideas||[])[n]||{};cpText((I.keywords||[]).join(", "))}
function cpText(s){s=s||"";const ok=()=>toast("copy ho gaya — paste kar dein");
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(s).then(ok,()=>fallback(s));return}fallback(s)}
function fallback(s){const t=document.createElement("textarea");t.value=s;t.style.position="fixed";t.style.opacity="0";document.body.appendChild(t);t.select();
 try{document.execCommand("copy");toast("copy ho gaya — paste kar dein")}catch(e){toast("copy nahi ho saka — text khud chun kar paste kar dein","warn")}t.remove()}
function ideaAI(n){const I=((IDEAS||{}).ideas||[])[n]||{};
 AQ.idea=I.prompt||I.topic||"";AQ.words=((I.thumb_texts||[])[0]||{}).t||"";AQ.ref=I.ref||"";
 AQ.str=Number(($("#istr"+n)||{}).value||0.55);AIRES=null;go("ai")}
async function ideaGen(n){
 const I=((IDEAS||{}).ideas||[])[n]||{},el=$("#ires"+n);if(!el)return;
 await aiInfo();
 if(!AIINFO||!AIINFO.key){el.innerHTML='<div class="err">Runware key set nahi — AI tab me key daal dein.</div>';return}
 const s=Number(($("#istr"+n)||{}).value||0.55);
 const words=((I.thumb_texts||[])[0]||{}).t||"";
 el.innerHTML='<div class="sub">'+esc(I.topic)+' par '+(AIINFO.shots||4)+' alag soch ban rahi hai — reference us jeetne wale ka thumbnail hai jiska views/day '+fmt(I.ref_vpd)+' tha</div>'+skelLines(4,"AI naye thumbnail bana raha hai…");
 let d;try{d=await jp("/api/aigen",{idea:I.prompt||I.topic,words:words,mk:AIINFO.def||"z",ref:I.ref||"",text_ai:false,res:"sd",strength:s})}
 catch(e){el.innerHTML='<div class="err">✗ '+esc(e.message)+'</div>';return}
 if(d.error){el.innerHTML='<div class="err">✗ '+esc(d.error)+'</div>';return}
 for(let t=0;t<200;t++){await new Promise(r=>setTimeout(r,900));let p;
  try{p=await j("/api/progress?id="+d.job)}catch(e){continue}
  if(p.state==="done"){IDEAR[n]=p.result;el.innerHTML=ideaRes(n);return}
  if(p.state==="error"){el.innerHTML='<div class="err">✗ '+esc(p.error)+'</div>';return}
  const pc=p.total?Math.round(p.done*100/p.total):0;
  el.innerHTML='<div class="sub">'+esc(p.current||"…")+' — '+p.done+'/'+p.total+' · har soch ko wahi OCR + analysis se napa jata hai jo competitors ko napa tha</div><div class="pbar"><i style="width:'+pc+'%"></i></div>'}
 el.innerHTML='<div class="err">bahut lamba laga — model badal kar AI tab me dobara try karein</div>'}
function ideaRes(n){
 const R=IDEAR[n]||{},I=((IDEAS||{}).ideas||[])[n]||{},tb=I.thumb_brief||{},its=R.items||[];
 const cards=its.map((v,i)=>{const t=v.ts||{},h=t.h320||0,w=t.n||0;
  const wc=w<=THv("words_ok",4)?"var(--grn)":w<=THv("words_warn",8)?"var(--amb)":"var(--red)";
  const hc=h>=THv("h_ok",18)?"var(--grn)":h>=THv("h_mid",12)?"var(--amb)":"var(--red)";
  return '<div class="rvimg" style="flex:1 1 360px"><div class="lab">'+esc(v.name||"soch "+(i+1))+' · banawas score <b style="color:'+cc(v.score)+'">'+(v.score==null?"—":v.score)+'</b>'+(v.usd?' · kharcha $'+Number(v.usd).toFixed(4):"")+'</div>'+
   '<div class="rvs" style="margin:6px 0"><div><div class="lab">320px (jaise desktop browse me dikhti hai)</div><img src="'+imgu(v.path)+'" style="width:320px;max-width:100%"></div>'+
   '<div><div class="lab">210px (mobile feed)</div><img src="'+imgu(v.path)+'" style="width:210px"></div></div>'+
   '<div class="sub">'+esc(v.why||"")+aiNote(v)+'</div>'+
   '<div class="lbl">us topic ke jeeton se saamne-saamne (wo naap jo un '+tb.n_hits+' videos par liye gaye)</div>'+
   '<span class="chip">shabd: is me <b style="color:'+wc+'">'+w+'</b> · jeeton ka median '+(tb.words_med||0)+'</span>'+
   '<span class="chip">text height @320: is me <b style="color:'+hc+'">'+h+'px</b> · jeeton ka median '+(tb.h320_med||0)+'px</span>'+
   '<span class="chip">banawas score: is me <b style="color:'+cc(v.score)+'">'+(v.score==null?"—":v.score)+'</b> · reference wale jeetne wale ka '+(I.ref_score==null?"—":I.ref_score)+'</span>'+
   '<div style="margin-top:6px">'+chipsOf(v)+'</div>'+
   '<div class="bar" style="margin-top:8px"><button class="sm" onclick="ideaUse('+n+','+i+')">'+ico("eye",14)+'poora analysis + behtar version</button>'+
   '<a class="btn sm" href="'+imgu(v.path)+'" download="'+esc((v.name||"thumbnail")+".jpg")+'">'+ico("dl",14)+'file download</a></div></div>'}).join("");
 return '<div class="lbl">ban gayi '+its.length+' soch (AI tasveerein) — '+esc(I.topic)+' · reference: '+esc((I.ref_title||"").slice(0,70))+'</div>'+
  '<div class="rvs" style="align-items:flex-start">'+cards+'</div>'+
  '<div class="bar" style="margin-top:10px"><button class="go" onclick="ideaGen('+n+')">'+ico("refresh",16)+'dobara banao (upar wali strength ke saath)</button>'+
  '<button class="sm" onclick="ideaAI('+n+')">'+ico("ext",14)+'AI tab me kholo — model, size, aur AI se text likhwaana</button></div>'+
  '<div class="sub">Score 0–100 thumbnail ki <b>banawas</b> ki jaanch hai, chalne ka saboot nahi. Asli CTR sirf channel ke malik ko milta hai — isliye ye tulna us jeetne wale ke <b>naape hue</b> numbers se hai, aur jeet ka naap views/day hai.</div>'}
function ideaUse(n,i){const v=((IDEAR[n]||{}).items||[])[i]||{};if(!v.path)return toast("wo file nahi mili");PEND=v.path;go("mine")}

// Scan ke baad result kholna. Pehle seedha boot() karke go("cmp") hota tha — aur
// boot() ke andar fromHash() URL me bithay PURANE scan ka id dekh kar cur ko wapas
// usi par palat deta tha, yani naya scan ban kar bhi Competitors page purana scan
// (ya kuch bhi nahi) dikhata. Isliye boot ke BAAD cur ko dobara naye scan par set
// karna zaroori hai. Ye funnel aur trend — sab raste isi se jaate hain.
async function openScan(id){await boot();cur=id;D=null;go("cmp")}
async function runScan(topic,n,wide,meta){
 spin();const d=await j("/api/scan?topic="+encodeURIComponent(topic)+"&n="+n+"&wide="+(wide?1:0)+"&meta="+(meta===false?0:1));
 if(d.cached){await openScan(d.id);return}
 for(let i=0;i<1200;i++){await new Promise(r=>setTimeout(r,1200));const p=await j("/api/progress?id="+d.job);
  if(p.state==="done"){await openScan(d.id);return}
  if(p.state==="error"){$("#main").innerHTML='<div class="err">✗ '+esc(p.error)+'</div>';return}
  const pc=p.total?Math.round(p.done*100/p.total):0;
  $("#main").innerHTML='<h2>'+ico("search",18)+' Scanning…</h2><div class="sub">'+esc(p.current||"…")+' — '+p.done+"/"+p.total+' · '+n+' videos'+(wide?" · wide search":"")+
   '<br>har thumbnail par OCR hota hai — wo <code>thumb_output/ocrc/</code> me cache ho jata hai, isliye dobara wahi topic seconds me khulta hai.</div><div class="pbar"><i style="width:'+pc+'%"></i></div>'}
 $("#main").innerHTML='<div class="err">Bahut lamba — n kam karke dobara.</div>'}
// Trending scan: wahi progress screen, bas source official chart hai. Result ek normal
// scan ki tarah hi khulta hai — do raste nahi, warna ek hi cheez ka matlab do hota.
async function runTrend(){const r=(($("#trg")||{}).value||"PK"),n=parseInt(($("#trn")||{}).value||"25",10);spin();
 let d;try{d=await j("/api/trend?region="+encodeURIComponent(r)+"&n="+n)}catch(e){$("#main").innerHTML='<div class="err">✗ '+esc(e.message)+'</div>';return}
 if(d.error){$("#main").innerHTML=trErrBox(d.error);return}
 if(d.cached){await openScan(d.id);return}
 for(let i=0;i<1200;i++){await new Promise(x=>setTimeout(x,1200));let p;try{p=await j("/api/progress?id="+d.job)}catch(e){continue}
  if(p.state==="done"){await openScan(d.id);return}
  if(p.state==="error"){$("#main").innerHTML=trErrBox(p.error||"trend scan fail hua");return}
  const pc=p.total?Math.round(p.done*100/p.total):0;
  $("#main").innerHTML='<h2>'+ico("trend",18)+' Trending scan — '+esc(TRG[r]||r)+'</h2><div class="sub">'+esc(p.current||"…")+' — '+p.done+"/"+p.total+
   ' videos · source: YouTube Data API ka apna chart (official)</div><div class="pbar"><i style="width:'+pc+'%"></i></div>'}
 $("#main").innerHTML='<div class="err">Bahut lamba — ruk gaya.</div>'}
// Trending API ki asli galti jaisi hai waisi dikhti hai; agar quota/403 ka case ho to
// saath me ye bhi likha jata hai ke muft rasta (topic scan, bina API) maujood hai —
// taake user phans na jaye. Koi chhupana nahi: API ne inkaar kiya, wajah aur muft raasta dono dikhe.
function trErrBox(m){const q=/quota|403|daily/i.test(m||"");
 return '<div class="err">✗ '+esc(m||"?")+'</div>'+(q?
  '<div class="sub">Sach: YouTube Data API ke free quota ne aaj ka hissa khatam kar diya (10,000 units/din, roz 00:00 Pacific par fresh hota hai — agli subah yahan se phir chalega). Tab tak kaam ruke nahi: <b>Topic Scan bilkul muft hai</b> — wo search se videos laata hai (yt-dlp, usme API ka ek unit bhi nahi lagta), aur "jeetne wali" filter se us topic ki sabse chalti videos khud napa ja sakti hain.</div>'+
  '<div class="bar"><input type="text" id="tq" placeholder="topic daalo — muft topic scan (API quota nahi lagta)" style="min-width:340px" onkeydown="if(event.key===\'Enter\')goScan()"><button class="go" onclick="goScan()">Topic Scan karo</button></div>':"")}
async function ytKey(del){const k=del?"":((($("#yk")||{}).value)||"").trim();if(!del&&!k)return toast("pehle key likho");
 try{const r=await jp("/api/ytkey",{key:k,add:!del});await boot();if((location.hash+"").indexOf("#/ai")===0)await aipg();toast(r.set?(r.n>1?("YouTube key pool me "+r.n+" keys ho gayi — ek ka quota khatam ho to agli key apne aap lagegi"):("YouTube API key save ho gayi — "+r.hint)):"key pool hata diya")}catch(e){failToast(e,"YouTube key save karna")}}

async function ensureData(){if(D)return D;if(!cur)return null;const d=await j("/api/data?id="+cur);if(d.none)return null;D=d;TOPIC=d.topic;return d}

// ---------- topic funnel ----------
// Socha hua raasta: niche → style → keywords → jeetne wale videos. Tool apne aap
// ek bhi search nahi karta — har kadam ka kaam sirf button dabane par hota hai,
// taake sirf usi cheez par kharcha ho jiska jawab chahiye (user ki shart:
// "overall manual button next, credits waste nahi").
let FUNM=null,FUN={st:1,niche:"",custom:"",style:"",kw:null,sel:[],main:""};
function funGo(s){FUN.st=s;funv()}
function funPickN(i){FUN.niche=FUNM.niches[i]||"";FUN.style="";funv()}
function funNext1(){const c=(($("#fnc")||{}).value||"").trim();if(c){FUN.custom=c;FUN.niche=c;FUN.style=""}
 if(!FUN.niche)return toast("pehle niche chuno ya khud likho");FUN.st=2;funv()}
function funFit(){const S=FUNM.styles,n=(FUN.niche||"").toLowerCase();
 return Object.keys(S).filter(k=>S[k].any||S[k].nic.some(x=>x.toLowerCase()===n))}
function funPickS(k){FUN.style=k;funv()}
function funNext2(){FUN.st=3;funv()}
async function funKw(){const b=$("#fkw");if(b)b.disabled=true;
 try{const d=await j("/api/kwfind?niche="+encodeURIComponent(FUN.niche)+"&style="+encodeURIComponent(FUN.style));
  FUN.kw=d;FUN.sel=(d.kws||[]).slice(0,6).map(k=>k.w);FUN.main=FUN.sel[0]||"";funv()}
 catch(e){if(b)b.disabled=false;failToast(e,"keywords dhoondna")}}
function funTgl(w){const i=FUN.sel.indexOf(w);if(i>=0)FUN.sel.splice(i,1);else FUN.sel.push(w);
 if(FUN.sel.indexOf(FUN.main)<0)FUN.main=FUN.sel[0]||"";funv()}
function funNext3(){if(!FUN.sel.length)return toast("kam se kam ek keyword chuno");
 if(FUN.sel.indexOf(FUN.main)<0)FUN.main=FUN.sel[0];FUN.st=4;funv()}
function funRun(){const n=parseInt(($("#fn")||{}).value||"25",10);runScan(FUN.main||FUN.niche,n,true,true)}
function funv(){
 if(!FUNM){$("#main").innerHTML='<div class="sr">style catalog la raha hoon…</div>';
  j("/api/styles").then(d=>{FUNM=d;funv()}).catch(e=>{$("#main").innerHTML='<div class="err">✗ '+esc(e.message)+'</div>'});return}
 const st=FUN.st,S=FUNM.styles;
 const STEPS=["1 Niche","2 Style","3 Keywords","4 Videos"];
 let h='<h2>'+ico("filter",18)+' Topic funnel</h2>'+
  '<div class="sub">Niche se videos tak, ek-ek kadam. Tool apne aap kuch search nahi karta — jab tak aap "aage barho" na dabaao, ek bhi kharcha nahi hoga. Jo pasand na aaye us par credit nahi jayega.</div>'+
  '<div class="fsteps">'+STEPS.map((s,i)=>'<span class="fstep'+(i+1===st?" on":"")+(i+1<st?" dn":"")+'"'+(i+1<st?' onclick="funGo('+(i+1)+')" title="is kadam par wapas jao"':"")+'>'+s+'</span>').join("")+'</div>';
 if(st===1){
  h+='<div class="card"><h3>Niche chuno</h3><div class="sub">Ye list style catalog se aati hai — jo styles aapne di thin, unhi me likhe niches. Yahan tak koi search nahi hui, sirf chunaav hai.</div>'+
   '<div>'+FUNM.niches.map((x,i)=>'<button class="chip kwk'+(FUN.niche===x?" on":"")+'" onclick="funPickN('+i+')">'+esc(x)+'</button>').join("")+'</div>'+
   '<div class="bar" style="margin-top:12px"><input type="text" id="fnc" placeholder="ya apni niche khud likho (catalog se bahar)" value="'+esc(FUN.custom||"")+'" style="min-width:340px">'+
   '<button class="go" onclick="funNext1()">Aage barho →</button></div>'+
   (FUN.niche?'<div class="sub" style="margin-top:8px">chuni hui niche: <b>'+esc(FUN.niche)+'</b></div>':"")+'</div>';
 }else if(st===2){
  const fit=funFit();
  h+='<div class="card"><h3>Is niche me kaunsi styles chalti hain</h3><div class="sub">Catalog ke mutabiq <b>'+esc(FUN.niche)+'</b> ke liye '+fit.length+' styles fit hain. Ye catalog ka chunaav hai — kaunsi style <b>sach me jeet rahi hai</b>, wo step 4 ke scan ke naapon se pata chalega ("Style jeet" isi flow me jud raha hai).</div>'+
   '<div><button class="chip kwk'+(FUN.style===""?" on":"")+'" onclick="funPickS(&quot;&quot;)"><b>style mat chhaanto</b> — sirf niche se search</button>'+
   fit.map(k=>'<button class="chip kwk'+(FUN.style===k?" on":"")+'" onclick="funPickS(&quot;'+k+'&quot;)">'+esc(S[k].n)+(S[k].any?' <b>· any niche</b>':"")+'</button>').join("")+'</div>'+
   '<div class="bar" style="margin-top:12px"><button class="sm" onclick="funGo(1)">← Peeche</button><button class="go" onclick="funNext2()">Aage barho →</button></div></div>';
 }else if(st===3){
  h+='<div class="card"><h3>Sirf is niche'+(FUN.style?" + "+esc((S[FUN.style]||{}).n||""):"")+' ke keywords</h3>';
  if(!FUN.kw){
   h+='<div class="sub">Abhi tak is kadam par koi search nahi hui. Jab tay ho tab button dabao: tool YouTube ke apne suggest box aur chand results ke titles ko gin kar keyword bank banayega — koi model nahi, koi naya naap nahi, API key ki zaroorat nahi. Kharcha: kuch second.</div>'+
    '<div class="bar"><button class="go" id="fkw" onclick="funKw()">Keywords dhoondo</button></div>'+
    '<div class="bar"><button class="sm" onclick="funGo(2)">← Peeche</button></div></div>';
  }else{
   h+='<div class="sub">'+esc(FUN.kw.note||"")+'</div><div>'+
    (FUN.kw.kws.length?FUN.kw.kws.map(k=>'<button class="chip kwk'+(FUN.sel.indexOf(k.w)>=0?" on":"")+'" onclick="funTgl(&quot;'+esc(k.w)+'&quot;)">'+esc(k.w)+' <b>×'+k.n+'</b></button>').join(""):'<div class="sub">kuch nahi mila — peeche jaakar "style mat chhaanto" karke dobara try karo.</div>')+'</div>'+
    '<div class="lbl">Scan kis keyword par chalega</div>'+
    '<select id="fmain" onchange="FUN.main=this.value">'+FUN.sel.map(w=>'<option value="'+esc(w)+'"'+(w===FUN.main?" selected":"")+'>'+esc(w)+'</option>').join("")+'</select>'+
    '<div class="sub" style="margin-top:8px">×N ka matlab: ye shabd utni baar suggest box ya in titles me aaya. Ginti ke bina koi shabd bank me nahi.</div>'+
    '<div class="bar" style="margin-top:12px"><button class="sm" onclick="funGo(2)">← Peeche</button><button class="sm" onclick="funKw()">Dobara dhoondo</button><button class="go" onclick="funNext3()">Aage barho →</button></div></div>';
  }
 }else{
  h+='<div class="card"><h3>Jeetne wale topics aur poori videos</h3>'+
   '<div class="sub">Scan wahi engine chalega jo Competitors use karta hai — koi naya naap nahi. Topic = chuna hua keyword, wide search on (asli spread ke liye), asli tags + description bhi aayenge (YouTube ka khud ka metadata — wahi tags aage keyword bank ko <b>asli</b> banate hain).</div>'+
   '<div class="lbl">Scan ka topic</div><div class="sub"><b>'+esc(FUN.main||FUN.niche)+'</b>'+
   (FUN.sel.length>1?' · baaki '+(FUN.sel.length-1)+' keywords par alag scan chalane ke liye step 3 par wapas jao — credit bachane ka yahi tareeqa hai':"")+'</div>'+
   '<div class="sub">Sach: ye "trending chart" nahi — search me <b>sabse zyada chali hui</b> aapki topic ki videos hain (ranking views/day se). Official chart poore mulk ka hota hai, apne maqsad ka nahi — isliye funnel ne ye raasta chuna; chart wala rasta Trending card par pehle se hai.</div>'+
   '<div class="bar"><select id="fn">'+[12,25,50].map(v=>'<option value="'+v+'"'+(v===25?" selected":"")+'>'+v+' videos</option>').join("")+'</select>'+
   '<button class="go" onclick="funRun()">Videos laao</button></div>'+
   '<div class="sub">Scan khulte hi: har card par "is video ka full analysis" — thumbnail ke naap, title, asli tags, description. Deep Analysis batata hai is niche me kaunsi cheez sach me chalti hai, aur Winning topics se ideas bante hain. Transcription aur "Style jeet" isi flow me jud rahe hain.</div>'+
   '<div class="bar"><button class="sm" onclick="funGo(3)">← Peeche</button><button class="sm" onclick="go(&quot;deep&quot;)">Deep analysis</button><button class="sm" onclick="go(&quot;ideas&quot;)">Winning topics</button></div></div>';
 }
 $("#main").innerHTML=h;
}

// ---------- competitors ----------
function noScan(){
 const n=localStorage.getItem("tn")||"50",w=localStorage.getItem("tw")!=="0",m=localStorage.getItem("tm")!=="0";
 $("#main").innerHTML='<h2>'+ico("search",18)+' Competitors</h2><div class="sub">Abhi koi scan nahi hai. Topic daalo — tool us topic ke top videos ke thumbnails laakar ginta hai ki log asal me kya kar rahe hain (text ka size, contrast, rang, chehra, composition, title ki lambai). Phir Deep Analysis batata hai inme se kaun si cheez sach me chalti hai, aur "Meri Thumbnail" isi benchmark se tulna karta hai.</div>'+
  '<div class="card"><h3>Naya scan</h3><div class="bar"><input type="text" id="tq" placeholder="apna niche / topic (jaise: black hole documentary)" style="min-width:340px" value="'+esc(TOPIC)+'" onkeydown="if(event.key===\'Enter\')goScan()">'+
  '<select id="tn">'+[12,25,50].map(v=>'<option value="'+v+'"'+(String(v)===String(n)?" selected":"")+'>'+v+' videos</option>').join("")+'</select>'+
  '<label class="sub" style="cursor:pointer"><input type="checkbox" id="tw" '+(w?"checked":"")+'> wide search</label>'+
   '<label class="sub" style="cursor:pointer"><input type="checkbox" id="tm" '+(m?"checked":"")+'> asli tags + description bhi lao</label>'+
  '<button class="go" onclick="goScan()">Scan karo</button></div>'+
  '<div class="sub"><b>wide search on rakho.</b> Sirf topic se search karo to aksar ek hi channel ka purana catalog aa jata hai — 50 videos me 40 usi channel ki. Wide me topic ke saath YouTube ke 5 related suggestions milakar set bharta hai (round-robin, duplicate hataa kar) — alag alag channels, asli spread. 50 videos ki poori scan (download + OCR + analysis) lagbhag 1 minute legi — naapi hui 42 second. Data <code>thumb_output/scans/</code> me bacha rehta hai, aur OCR <code>thumb_output/ocrc/</code> me — dobara wahi topic seconds me khulta hai.</div>'+
   '<div class="sub"><b>asli tags + description</b> on rehne chahiye. Wo har video ka poora metadata bhi laata hai — tags, description, chapters, likes, comments, subscriber count — jo us channel ne <b>khud lagaya</b> hai, koi andaaza nahi. Ye YouTube ke public data se ek-ek video par hota hai: naapa hua <b>~0.45 second per video</b> (50 videos ≈ 25 second, aur wo bhi thumbnail download ke saath parallel, isliye total time me almost add nahi hota). Har video ek baar <code>thumb_output/metac/</code> me save ho jata hai — dobara scan me ek second bhi nahi lagta. Band karne par listing ka koi data nahi aayega, baaki sab pehle jaisa.</div>'+
  '<div class="sub">Note: ranking <b>views/day</b> se hoti hai, raw views se nahi — 30 din purani video ke 300K views, 3 saal purani ke 7M se behtar hain.</div></div>'+
   '<div class="card" style="margin-top:14px"><h3>Trending — YouTube ka apna chart '+(YTOK?(YTN>1?'<span class="hi">✓ pool me '+YTN+' keys — quota khatam hone par agli key apne aap</span>':'<span class="hi">✓ key set hai</span>'):'<span class="lo">key set nahi — ye abhi kaam nahi karega</span>')+'</h3>'+
   '<div class="sub">Ye search ka ulta hai: hum poochhte nahi ke "is topic me kaun hai", balki YouTube ka <b>apna chart</b> lete hain ke aaj us mulk me algorithm ne kin videos ko upar rakha hai. Naap (thumbnail, OCR, score, Deep Analysis) bilkul wahi chalta hai jo topic scan par — farak sirf videos ka source hai, aur wo source <b>official YouTube Data API</b> hai: views, date, lambai sab YouTube ka diya hua data, koi scraping andaaza nahi. Free quota 10,000 units/day aur ek trending scan = <b>1 unit</b> — bartan ki bhatti nahi, chammach.</div>'+
   '<div class="bar"><select id="trg">'+Object.keys(TRG).map(k=>'<option value="'+k+'">'+esc(TRG[k])+' ('+k+')</option>').join("")+'</select>'+
   '<select id="trn">'+[10,25,50].map(v=>'<option value="'+v+'"'+(v===25?" selected":"")+'>'+v+' videos</option>').join("")+'</select>'+
   '<button class="go" onclick="runTrend()">Trending scan karo</button></div>'+
    '<div class="bar"><textarea id="yk" rows="3" spellcheck="false" placeholder="YouTube Data API keys − ek line me ek key. 11 keys bhi ek saath paste kar do: pool me add ho jaayengi (duplicate apne aap chhoot jaayengi), aur ek key ka din ka quota (10,000 units) khatam ho to tool apne aap agli key laga deta hai" style="min-width:420px;min-height:64px;font-family:var(--mono);font-size:12px"></textarea><button class="sm" onclick="ytKey()">pool me add karo</button>'+(YTOK?'<button class="sm gh" onclick="ytKey(1)">pool hatao</button>':"")+'</div>'+
    (YTOK&&YTN>1?'<div class="sub">Pool me abhi '+YTN+' keys hain − har key ka apna alag daily quota hota hai, isliye pool jitni keys, utna zyada din ka quota. Tool ye nahi jaanta key kis account ki hai; bas ek khatam hone par agli line apne aap lag jaati hai.</div>':"")+
   '<div class="sub"><b>Sach jo jaanna zaroori hai:</b> trending chart algorithm ka push hai — poore mulk ka aaj ka mood, aapke topic ka benchmark nahi. Is scan ka "topic match" number chart ke against hai isliye usse zyada mat tollo; views/day, thumbnails ke naap aur Deep Analysis hi asli kaam hain. Chart ki videos par YouTube ke <b>official topic tags</b> (Wikipedia entities) bhi aate hain — item card par "topic tag (official)" me dikhte hain, aur wo YouTube ka label hai hamara andaaza nahi. Key free tier par bhi chahiye, kyunki quota aapke Google account se juda hota hai.</div></div>'}
function goScan(){const t=$(("#tq")||{}).value||TOPIC||"";if(!t)return toast("topic likho");
 const n=parseInt(($("#tn")||{}).value||"50",10),w=!!($("#tw")||{}).checked,m=!!($("#tm")||{}).checked;
 localStorage.setItem("tn",String(n));localStorage.setItem("tw",w?"1":"0");localStorage.setItem("tm",m?"1":"0");
 TOPIC=t;runScan(t,n,w,m)}
// Outlier radar — reference suite ke "top performers" cards ka pattern, lekin sirf
// isi scan ke naape gaye numbers se. Chhe se kam naap ya median na ho to ye strip
// dikhti hi nahi: adhoore data par "outlier" ka label lagana jhooth hoga.
function radarOf(d){const its=(d.items||[]).filter(it=>it.views!=null&&it.thumb),
 a=its.map(vpd).filter(x=>x>0);if(its.length<6||a.length<6)return "";
 const med=medv(a);if(!med)return "";
 const hi=its.map(it=>({it:it,v:vpd(it)})).filter(o=>o.v/med>=1.5).sort((x,y)=>y.v/med-x.v/med).slice(0,4);
 if(!hi.length)return "";
 return '<div class="sec">Outlier radar <small> — is scan ke andar sab se alag chalne wali videos (views/day, isi scan ke median se)</small></div>'+
  '<div class="radar">'+hi.map(o=>{const lift=o.v/med,brk=lift>=3,ix=(d.items||[]).indexOf(o.it);
   return '<div class="olc" onclick="zoom('+ix+')" title="is video ka poora analysis kholo">'+
    '<span class="olbadge'+(brk?" brk":"")+'">'+(brk?"BREAKOUT":"SURGING")+'</span>'+
    '<img loading="lazy" alt="" src="'+imgu(o.it.thumb)+'">'+
    '<div class="olb"><div class="olt">'+esc(o.it.title)+'</div>'+
    '<div class="olm"><div><span>views/day</span><b style="color:var(--acc)">'+fmt(o.v)+'</b></div>'+
    '<div><span>median se</span><b>&times;'+lift.toFixed(1)+'</b></div>'+
    '<div><span>views</span><b>'+fmt(o.it.views)+'</b></div></div></div></div>'}).join("")+'</div>'+
  '<div class="sub">is scan ka median views/day ('+a.length+' videos): <b>'+fmt(med)+'</b> — BREAKOUT &times;3 se upar, SURGING &times;1.5 se upar. Ye koi site-wide comparison nahi, sirf isi scan ke andar ka farak hai.</div>'}

// Style jeet: style ka ANDAZA pixels se (tool ka classifier — galat bhi ho sakta
// hai), jeet ka NAAP views/day se (har video ka asli gina hua data). Dono screen
// par alag-alag likhe hain. Aapki theek ki hui style scan file me rehti hai aur
// agli baar classifier se pehle lagti hai.
const STYL={lineart:"line art (safed zameen, kaali lines — whiteboard/stickman)",dark:"dark zameen (blackboard/cinematic)",photo:"asli footage jaisa (photo/rang-biranga)",flat:"flat cartoon / motion graphics (teeikh rang)",unknown:"pehchaan nahi hua"};
function stySec(d){
 if(!d.sty)return '<div class="card"><h3>Style jeet <small> — is topic me kaunsi production style sach me chal rahi hai</small></h3>'+
  '<div class="sub">tool har thumbnail ke pixels dekh kar style ka <b>andaza</b> lagata hai (zameen ka rang, lines, rangon ki gehrai) — ye classifier hai, guarantee nahi. Jeet ka naap views/day se hoga, jo har video ka asli data hai. Jab tak aap button na dabao, ye kaam nahi hota.</div>'+
  '<button class="go" onclick="styGo()">'+ico("palette",14)+'Style jeet naap lo</button></div>';
 const g={};(d.items||[]).forEach(it=>{const b=(d.sty||{})[it.id];if(!b)return;(g[b]=g[b]||[]).push(it)});
 const rows=Object.keys(STYL).filter(k=>g[k]).map(k=>{const a=g[k].map(vpd).filter(x=>x>0);
   return {k:k,n:g[k].length,med:a.length?medv(a):0,ex:g[k].slice(0,3)}}).sort((x,y)=>y.n-x.n||y.med-x.med);
 const tot=rows.reduce((s,r)=>s+r.n,0)||1;
 const best=rows.filter(r=>r.k!=="unknown"&&r.med>0).sort((x,y)=>y.med-x.med)[0];
 return '<div class="sec">Style jeet <small> — style ka andaza pixels se (tool ka classifier); jeet ka naap views/day se (asli data)</small></div>'+
  rows.map(r=>'<div class="srow"><div class="svbar"><i style="width:'+Math.round(r.n*100/tot)+'%"></i><span>'+STYL[r.k]+' — <b>'+r.n+' video'+(r.n>1?'s':'')+' ('+Math.round(r.n*100/tot)+'%)</b> · median views/day '+(r.med?'<b style="color:var(--acc)">'+fmt(r.med)+'</b>':'—')+'</span></div>'+
   r.ex.map(it=>'<img loading="lazy" class="styx" alt="" src="'+imgu(it.thumb)+'" title="'+esc(it.title)+'">').join("")+'</div>').join("")+
  (best?('<div class="sub">Is scan me sab se zyada chalne ka naap: <b>'+STYL[best.k]+'</b> (median views/day '+fmt(best.med)+'). Ye us scan ki videos ka naap hai — poore topic ka hukum nahi.</div>'):"")+
  '<div class="sub">Sach: ye buckets pixel patterns se bane hain — galat b ho sakte hain. Har video ki style theek karne ka rasta us ke full analysis me hai; aapki theek ki hui style agli naap me classifier se pehle lagti hai.</div>'}
async function styGo(){spin();let r;try{r=await j("/api/sty?id="+cur)}catch(e){return failToast(e,"style naap")}
 if(r.err)return toast(r.err);D.sty=r.sty;cmp();toast("style naap liye gaye — ye andaza hai, guarantee nahi")}
function styFixRow(it){const c=(D&&D.sty||{})[it.id];
 return '<div class="sec">Style theek karo <small> — tool ka andaza'+(c?(' <b>'+esc(STYL[c]||c)+'</b>'):" (abhi naapa gaya nahi)")+' — galat ho to sahi style yahan chuno; ye scan file me bachegi</small></div>'+
  '<div>'+Object.keys(STYL).map(k=>'<button class="chip kwk'+(c===k?" on":"")+'" onclick="styFix(\''+it.id+'\',\''+k+'\')">'+STYL[k]+'</button>').join(" ")+'</div>';}
async function styFix(vid,k){try{await jp("/api/stfix",{id:cur,vid:vid,fix:k})}catch(e){return failToast(e,"style fix")}
 D.sty=D.sty||{};D.sty[vid]=k;toast("theek kar di — agli naap me ye style pehle se lagegi")}

// Behtareen competitors: inhi results me se channel-wise asli views/day se ranking.
// Ye sirf isi scan ki videos ka naap hai — poore channel ka hukum dene ke liye
// "poora channel kholo" (wo scan naya kaam hai, sirf aapke click par).
function compSec(d){if(d.kind==="channel")return "";
 const g={};(d.items||[]).forEach(it=>{const c=it.channel||"(bina channel)";const a=g[c]=g[c]||{n:0,vs:[],best:null,days:[]};
  a.n++;const v=vpd(it);if(v>0)a.vs.push(v);if(it.days!=null)a.days.push(it.days);if(!a.best||v>vpd(a.best))a.best=it});
 const rows=Object.keys(g).map(c=>{const a=g[c];const med=a.vs.length?medv(a.vs):0;const fresh=a.days.length?Math.min(...a.days):null;
  return {c:c,n:a.n,med:med,best:a.best,fresh:fresh}}).filter(r=>r.med>0).sort((x,y)=>y.med-x.med).slice(0,10);
 if(!rows.length)return "";
 return '<div class="sec">Behtareen competitors <small> — in results me se kaun se channel behtar chal rahe hain (asli views/day se)</small></div>'+
  rows.map((r,i)=>'<div class="crow"><span class="crk">'+(i+1)+'</span><div style="flex:1;min-width:0"><b>'+esc(r.c)+'</b> — '+r.n+' video'+(r.n>1?'s':'')+' is scan me · median views/day <b style="color:var(--acc)">'+fmt(r.med)+'</b>'+
   (r.best?(' · sabse chalti: <i>'+esc((r.best.title||"").slice(0,60))+'</i> ('+fmt(vpd(r.best))+'/day)'):'')+
   (r.fresh!=null?(' · nayi video '+r.fresh+' din pehle'):'')+
   (r.n===1?' · <b>kam bharosa — sirf 1 video dikhi</b>':'')+'</div>'+
   '<button class="sm" data-q="'+esc(r.c)+'" onclick="openChanQ(this.dataset.q)">poora channel kholo</button></div>').join("")+
  '<div class="sub">Ye ranking isi scan ki videos ke views/day se hai — channel ke poore data se nahi. "Poora channel kholo" us channel ki poori listing ka scan kholega — naya kaam, sirf aapke click par.</div>'}
function openChanQ(q){CQ=q;CHC=null;cur="";D=null;go("ch");goChan()}
async function cmp(){const _t=RTN;if(!cur){noScan();return}spin();const d=await ensureData();if(_t!==RTN)return;if(!d){noScan();return}const a=d.agg,B=(d.deep||{}).bench||{};
 if(CMPFID!==d.id){CMPFID=d.id;CMPF="all";CPG=0;} // scan badla to filter bhi naye scan se
 const W=winOf(d);
 // Cards filter: "sirf jeetne wali" ka matlab wahi rule jo screen par likha hai —
 // index absolute rakha jata hai taake zoom/Behtar banao usi video par jaayein.
 let idxs=d.items.map((x,i)=>i);
 if(CMPF==="win"&&W.on)idxs=idxs.filter(i=>W.win.indexOf(d.items[i])>=0);
 const np=Math.max(1,Math.ceil(idxs.length/CPS));
  CPG=Math.max(0,Math.min(CPG,np-1));
  const cards=idxs.slice(CPG*CPS,CPG*CPS+CPS).map(i=>cardOf(d.items[i],i)).join("");
 $("#main").innerHTML=cmpHead(d)+'<div class="sub">'+d.items.length+' videos · scan '+esc(d.ts)+
  ' · '+(d.wide?"wide search (topic + related suggestions se merge)":"sirf topic ka search")+' '+smp(d)+
  ' · <a style="color:var(--acc)" onclick="deepv()">'+ico("bars",14)+'Deep Analysis kholo</a></div>'+
  kpiStrip(d,a,B)+radarOf(d)+
  issAgg(d.items)+'<div class="card"><h3>Ye log aise thumbnail banate hain</h3>'+
  '<div class="sub">Rang (ye colour in sab thumbnails me kitna faila hai — apna rang alag rakho to feed me dikhega): '+
   a.fams.map(f=>'<span class="chip">'+esc(f.f)+' <b>'+f.n+'%</b></span>').join("")+'</div>'+
   '<div class="sub">Titles: median <b>'+a.title.med_len+'</b> chars · max <b>'+a.title.max_len+'</b> · <b>'+a.title.num_pct+'%</b> me number · <b>'+a.title.caps_pct+'%</b> me CAPS · <b>'+a.title.br_pct+'%</b> me " | " / brackets · <b>'+a.title.q_pct+'%</b> me sawal</div>'+
   '<div class="sub">Baar-baar aane wale title shabd: '+a.phrases.map(p=>'<span class="tag" onclick="mkTitle(\''+esc(p.p)+'\')">'+esc(p.p)+' ×'+p.n+'</span>').join("")+'</div></div>'+
  stySec(d)+compSec(d)+
  '<div class="sub" style="margin-top:10px">Score (0–100) thumbnail ki <b>banawas</b> ki jaanch hai — chalne ka saboot nahi. Chalta kya hai wo <a style="color:var(--acc)" onclick="deepv()">Deep Analysis</a> batata hai (har pattern ko views/day se napta hai).</div>'+
  '<div class="sec" id="cpsec">'+(CMPF==="win"&&W.on?'Sirf jeetne wali <small> — rule: views/day is scan ke median ('+fmt(W.med)+') se 2× ya zyada; ye sirf is scan ki naapi gayi videos ka tulna hai</small>':'Sabke thumbnails <small> — click karke poora analysis · "Behtar banao" se usi photo ka behtar version, "AI se banao" se bilkul naya</small>')+'</div>'+
   '<div class="bar">'+issToggle()+'<div class="seg"><button id="cv-cards" class="'+(CMPV==="cards"?"on":"")+'" onclick="cmpView(\'cards\')">'+ico("image",14)+'Cards</button>'+
   '<button id="cv-table" class="'+(CMPV==="table"?"on":"")+'" onclick="cmpView(\'table\')">'+ico("bars",14)+'Table (Studio)</button></div>'+
   (CMPV!=="table"&&W.on?'<div class="seg"><button class="'+(CMPF==="all"?"on":"")+'" onclick="cmpF(\'all\')">sab ('+d.items.length+')</button><button class="'+(CMPF==="win"?"on":"")+'" onclick="cmpF(\'win\')">'+ico("spark",14)+'sirf jeetne wali ('+W.win.length+')</button></div>':"")+
   (CMPV!=="table"&&CMPF==="win"&&W.win.length?'<button class="sm" onclick="winSelAll()">'+ico("check",13)+'saari jeetne wali select karo</button>':"")+
   '<span class="sub">Cards = thumbnail par nazar · Table = numbers par sort/filter</span></div>'+
   (CMPV!=="table"&&CMPF==="win"&&W.on?formulaOf(d,W)+vdSec(d):"")+
   (CMPV==="table"?stBlock():'<div class="grid" id="cpgrid">'+cards+'</div>'+cpPg(idxs.length,CPS,d.items.length,CMPF==="win"&&W.on?"sirf jeetne wali:":""));
 // Studio jaisa table = numbers par kaam. Is me wo saari rows bhi aani chahiye jo
 // abhi sirf gini gayi hain, warna 211 me se 23 hi nazar aate hain aur poora
 // channel chhota lagta hai. Listing aate hi table apne aap bhar jaata hai —
 // page ko dobara refresh karna nahi padta.
 if(d.kind==="channel")stWalk();stMetaHook()}
function stWalk(){
 if(!cur||(WALK&&WALK.id===cur))return;
 const b=document.getElementById("stbox");
 if(b)b.innerHTML='<div class="stempty">Counting the full listing — the first run takes about 10 seconds '+
  '(one yt-dlp request), then it stays in the file for 24 hours</div>';
 walkGet(cur).then(r=>{if(r&&D&&D.id===cur){if(view==="cmp")cmp();else if(view==="ch")chanv()}})}
// Card par pehle 17 kacche numbers hote the — kaunsa number bura hai aur uska ilaaj
// kya hai, ye faisla user ko khud karna padta tha. Ab card pehle masla batata hai
// (server ne har naapi gayi video par verdicts likhe hain), aur poora naap ek
// toggle ke peeche hai. Dono raste hain, faisla user ka.
function numChips(it){
 const words=it.ts&&it.ts.n?it.ts.n:0;
 const wc=words===0?"":words<=4?"var(--grn)":words<=8?"var(--amb)":"var(--red)";
 const cr=it.ts&&it.ts.cr_med!=null?it.ts.cr_med:null;
 const crc=cr==null?"":cr>=THv("cr_ok",4.5)?"var(--grn)":cr>=THv("cr_warn",3)?"var(--amb)":"var(--red)";
 const fc=(it.faces||[]).length,fm=fc?Math.round(Math.max.apply(null,it.faces.map(x=>x.area))):0;
 return chip("views/day",fmt(vpd(it)),"var(--acc)")+chip("text",words,wc)+
  (it.ts&&it.ts.h320?chip("bada text",it.ts.h320+"px@320"):"")+
  (cr!=null?chip("contrast",f2(cr),crc):"")+
  (it.ts&&it.ts.ring_cr!=null?chip("outline",f2(it.ts.ring_cr)+":1"):"")+
  (fc?chip("chehra",fm+"%",fm>=THv("face_ok",8)?"var(--grn)":""):"")+
  (it.an&&it.an.blur?chip("blur","hai","var(--red)"):"")+
  ((it.comp||{}).dom!=null?chip("subject",(it.comp||{}).subj_pct+"% · dom "+Math.round((it.comp||{}).dom*100)+"%",(it.comp||{}).dom>=THv("dom_lo",0.32)?"var(--grn)":"var(--amb)"):"")+
  ((it.comp||{}).thirds!=null?chip("thirds",f2((it.comp||{}).thirds),(it.comp||{}).thirds>=THv("thirds_ok",0.6)?"var(--grn)":""):"")+
  ((it.sem||{}).t_topic!=null?chip("topic match",f2((it.sem||{}).t_topic),(it.sem||{}).t_topic>=0.15?"var(--grn)":"var(--amb)"):"")+
  (it.dup!=null?chip("title dohrata",it.dup+"%",it.dup>25?"var(--red)":""):"")+
  (it.tags!=null?chip("asli tags",(it.tags||[]).length,it.tags.length?"var(--grn)":"var(--red)"):"")+
   ((it.tq||[]).length?'<span class="chip" title="YouTube ka APNA lagaya topic tag (Data API topicDetails se) — official label hai, hamara andaaza nahi">topic tag (official): '+esc(it.tq[0])+(it.tq.length>1?" +"+(it.tq.length-1):"")+'</span>':"")+
  (it.dlen!=null?chip("description",fmt(it.dlen)+" ch",it.dlen>=200?"var(--grn)":it.dlen>=40?"var(--amb)":"var(--red)"):"")+
  (it.ls!=null?chip("listing score",it.ls,cc(it.ls)):"")+
  (it.nch?chip("chapters",it.nch,"var(--grn)"):"")+
  (it.an?chip("bright",it.an.bright):"")+
  (it.an&&it.an.colors&&it.an.colors[0]?'<span class="chip"><span class="sw" style="background:'+it.an.colors[0].hex+'"></span>'+it.an.colors[0].fam+' '+it.an.colors[0].pct+'%</span>':"")}
// Cards ka pager Table mode wale pager jaisa hi hai — ek hi kaam, ek hi look.
function cpPg(n,ps,tot,fl){
 if(n<=ps)return '<div class="stpg"><span class="pgi">'+(fl?'<b>'+fl+'</b> ':'')+'saare '+n+' cards ek page par'+
  (n<=24?' — scan chhota hai, page ki zaroorat nahi':' — aap ne "saare ek saath" chuna hai, is liye ye saath ban rahe hain. Bada scan hone par page bhaari ho sakta hai; kam wala option chuno to tez chalega.')+'</span></div>';
 const np=Math.ceil(n/ps),p=CPG;
 const bt=(l,g,dis)=>'<button class="sm"'+(dis?' disabled':"")+' onclick="'+g+'">'+l+'</button>';
 return '<div class="stpg">'+bt(ico("back",13)+" Pichhla","cpGo(-1)",p<=0)+
  '<span class="pgi">'+(fl?'<b>'+fl+'</b> ':'')+'page <b>'+(p+1)+'</b> / '+np+' &nbsp; card '+(p*ps+1)+'-'+Math.min(n,(p+1)*ps)+' dikhi'+(tot&&tot!==n?' — ye poori scan ke '+tot+' me se '+n+' hain (filter ke baad); neeche agla page bhi hai':', kul '+n)+'</span>'+
  '<select class="pill" onchange="cpS(this.value)" title="ek page me kitne cards">'+[12,24,48].map(v=>
   '<option value="'+v+'"'+(ps===v?" selected":"")+'>'+v+' har page</option>').join("")+
   '<option value="9999">saare cards ek saath</option></select>'+
  bt("Agla "+ico("down",13),"cpGo(1)",p>=np-1)+'</div>'}
function cpTo(){const e=document.getElementById("cpsec");
 if(e)e.scrollIntoView({block:"start",behavior:"smooth"})}
function cpGo(d){const W=(D&&CMPF==="win")?winOf(D):{on:false};const n=W.on?W.win.length:((D&&D.items||[]).length),np=Math.max(1,Math.ceil(n/CPS));
 CPG=Math.max(0,Math.min(np-1,CPG+d));cmp();cpTo()}
function cpS(v){CPS=Math.min(9999,parseInt(v,10)||24);CPG=0;cmp();cpTo()}

function cardOf(it,i){
 return '<div class="card"><div class="bwrap" style="width:100%"><img class="thumb" src="'+imgu(it.thumb||"")+'" onclick="zoom('+i+')" loading="lazy" alt="">'+
  (it.score!=null?'<button class="badge bb" onclick="whyAt('+i+')" title="ye score kaise bana — poora hisaab dekho" style="color:'+cc(it.score)+'">'+it.score+'/100</button>':"")+'</div>'+
  '<div style="margin-top:8px"><a target="_blank" rel="noopener" href="'+it.url+'" style="color:var(--tx);text-decoration:none;font-size:var(--fs-body)">'+esc(it.title)+'</a></div>'+
  '<div class="sub" style="margin-top:4px">'+esc((it.channel||"").slice(0,26))+' · '+fmt(it.views)+' views / '+(it.days||"?")+'d · '+esc(it.kind||"")+'</div>'+
  (CMPM==="num"?'<div style="margin-top:6px">'+numChips(it)+"</div>":issList(it,i,false))+
  '<div class="bar" style="margin:9px 0 0">'+
  '<button class="sm go" onclick="regenAt('+i+')">'+ico("refresh",14)+'Behtar banao</button>'+
  '<button class="sm" onclick="aiAt('+i+')">'+ico("palette",14)+'AI se banao</button>'+
  '<button class="sm" onclick="gdpAt('+i+')">'+ico("bars",14)+'Gehri analysis</button>'+
  '<button class="sm" onclick="zoom('+i+')">'+ico("eye",14)+'poora analysis</button>'+
  '<button class="sm" onclick="cbOpen('+i+')">'+ico("layers",14)+(CBV.has(it.id)?"bank me hai":"Competitor banao")+'</button>'+
  '<a class="btn sm ytbtn" target="_blank" rel="noopener" href="'+esc(it.url||"#")+'" title="is video ko YouTube par naye tab me kholo" aria-label="YouTube par kholo">'+ico("ext",14)+"</a>"+ytc(it.url)+
  '</div><div id="gdp'+i+'"></div></div>'}
// Poore scan ka aggregate: is topic ke logon me sabse zyada kya kharabi hai. Ye ginti
// har video ke APNE naap se hai — koi andaza joda nahi gaya.
function issAgg(items){
 const m={};let naped=0,saaf=0;
 items.forEach(it=>{if(!it.vr)return;naped++;let has=0;
  (it.vr||[]).forEach(v=>{if(v.s==="ok")return;has++;
   m[v.k]=m[v.k]||{n:0,fix:v.n,bad:0};m[v.k].n++;if(v.s==="bad")m[v.k].bad=1});
  if(!has)saaf++});
 const top=Object.keys(m).map(k=>({k:k,n:m[k].n,s:m[k].bad?"bad":"warn",fix:m[k].fix})).sort((a,b)=>b.n-a.n).slice(0,6);
 if(!top.length||!naped)return "";
 return '<div class="card"><h3>'+ico("alert",16)+' In thumbnails me sabse zyada kya kharab hai</h3>'+
  '<div class="sub">'+naped+' naapi gayi videos me se <b>'+saaf+'</b> par tool ko koi masla nahi mila. Neeche har ginti us video ke apne naap se gini gayi hai.</div>'+
  top.map(x=>'<div class="iss-n '+x.s+'">'+ico("alert",14)+'<span><b>'+esc(x.k)+"</b> — "+x.n+"/"+naped+" videos me ("+Math.round(x.n/naped*100)+"%)"+
   "<br><span>"+esc(x.fix)+"</span></span></div>").join("")+
  '<div class="sub" style="margin-top:8px">Apni thumbnail inhi maslon se mila kar dekhne ke liye <a style="color:var(--acc)" onclick="closeModal();go(\'mine\')">Meri Thumbnail</a> — wahi rules wahan apni file par chalte hain.</div></div>'}
function cmpHead(d){
 // Heading hamesha sach batati hai: topic scan ka naam "Competitors" hai, channel scan
 // ka us channel ka apna analysis. Pehle channel scan par bhi "Competitors — <channel>"
 // likhta tha, jisse lagta tha tool ne galat cheez khol di.
 const ch=d.kind==="channel";
 return '<h2>'+ico(ch?"eye":"search",18)+" "+(ch?"Is channel ke thumbnails":"Competitors")+" — "+
  esc(ch?(d.ch&&d.ch.name)||d.topic:d.topic)+"</h2>"}
function issToggle(){
 return '<div class="seg"><button id="cm-iss" class="'+(CMPM==="iss"?"on":"")+'" onclick="cmpMode(\'iss\')">'+
  ico("alert",14)+'Masle dikhao</button><button id="cm-num" class="'+(CMPM==="num"?"on":"")+'" onclick="cmpMode(\'num\')">'+
  ico("bars",14)+"Poore naap</button></div>"}
function cmpMode(v){CMPM=v;cmp()}
// Ek line me 12 barabar number — isme dikhta hi nahi tha kaunsa zaroori hai.
// Studio ka tarteeb: faisla banane wale number aage, baaki naap ek khulne-band
// hone wale hisse me. Chhupa kuch nahi jaata — bas pehchan badalti hai.
function kpiStrip(d,a,B){
 const its=d.items||[],np=its.filter(i=>i.vr);
 const ms=np.filter(i=>(i.vr||[]).some(v=>v.s!=="ok")).length;
 const bd=np.filter(i=>(i.vr||[]).some(v=>v.s==="bad")).length;
 let h='<div class="kpi">'+kpi("videos naapi gayi",fmt(np.length),"var(--acc)")+
  (function(){const W=winOf(d);return W.on?kpi("jeetne wali (2×+)",W.win.length+" / "+its.length,W.win.length?"var(--grn)":""):kpi("jeetne wali","— (6+ naap chahiye)")})()+
  (np.length?kpi("inme masla hai",ms+" / "+np.length,ms?"var(--amb)":"var(--grn)"):"")+
  (np.length?kpi("badi kharabi",bd,bd?"var(--red)":"var(--grn)"):"")+
  kpi("median views/day",fmt((d.deep||{}).vpd_med||0),"var(--acc)")+
  kpi("median score",medsc(its))+
  kpi("bada text @320",(a.med_maxh320||0)+"px",(a.med_maxh320||0)>=THv("h_ok",18)?"var(--grn)":"var(--red)")+
  kpi("median contrast",a.med_cr||"—",(a.med_cr||0)>=THv("cr_ok",4.5)?"var(--grn)":"var(--amb)")+'</div>';
 const more=[kpi("text wale",a.with_text_pct+"%"),kpi("median shabd",a.med_words),
  kpi("chehra wale",((B._face_pct_of_all)||0)+"%"),kpi("median brightness",a.med_bright)];
 if(B.tags_count)more.push(kpi("median tags",B.tags_count.med,B.tags_count.med>=10?"var(--grn)":"var(--amb)"));
 if(B.desc_chars)more.push(kpi("median description",fmt(B.desc_chars.med)+" ch"));
 if(B._chaps_pct!=null)more.push(kpi("chapters wale",B._chaps_pct+"%",B._chaps_pct>=50?"var(--grn)":"var(--amb)"));
 if(B.listing_score)more.push(kpi("median listing score",B.listing_score.med,cc(B.listing_score.med)));
 return h+'<details class="kdet"><summary>'+ico("bars",14)+"baaki naap ("+more.length+') — poora hisaab kholo</summary>'+
  '<div class="kpi">'+more.join("")+"</div></details>"}
function medsc(its){const v=its.map(i=>i.score).filter(x=>x!=null).sort((a,b)=>a-b);return v.length?Math.round(v[v.length>>1]):"—"}
function mkTitle(p){TITLE=(TITLE?p+" ":"")+TITLE;go("tl")}
function chipsOf(it){const t=it.ts||{},a=it.an||{};
 return chip("shabd",t.n)+chip("320px par padhe gaye",t.read320)+chip("bada text @320",t.h320)+chip("text contrast",f2(t.cr_med))+chip("outline contrast",f2(t.ring_cr))+
  chip("text ke blocks",t.blocks)+(t.pos?chip("text kahan",t.pos):"")+(t.badge?chip("duration badge se takraav","haan","var(--red)"):"")+
  (t.edge?chip("text kinare se chipka","haan","var(--red)"):"")+(t.facehit?chip("text chehre par","haan","var(--red)"):"")+
  chip("text ka area",t.area+"%")+(it.dup!=null?chip("title dohrata",it.dup+"%"):"")+
  chip("brightness",a.bright)+chip("tonal depth",a.dyn)+chip("range",a.sat)+chip("bheed (edges)",a.clutter)+chip("sharpness",a.sharp)+(a.blur?chip("blur","HAI","var(--red)"):"")+
  (a.comp?chip("rule of thirds",f2(a.comp.thirds))+chip("center of gravity",a.comp.cog.map(x=>f2(x)).join(",")):"")+
  (a.warm!=null?chip("taap-mizaaj warm/cool",a.warm+"/"+a.cool):"")+chip("chehre",(it.faces||[]).length)+
  (a.subj?chip("subject ka box",Math.round(a.subj.w*100)+"%×"+Math.round(a.subj.h*100)+"%"):"")}
// ---------- COMPETITOR BANK ----------
// User ne kisi video ko "competitor" mana → style/niche woh khud chunta hai.
// Numbers us din ke scan ke asli numbers hain (save ke waqt copy hue), style/
// niche user ki raaye hai — dono ka source alag hai, is liye UI me alag likha.
let CBB=null,CBF=-1,CBV=new Set();
async function cbGet(force){if(!CBB||force){try{CBB=await j("/api/cmpb")}catch(e){CBB={items:[]}}}
 CBV=new Set((CBB.items||[]).map(x=>x.vid||""));return CBB}
function cbOpen(i){CBF=i;zoom(i)}
function cbFormAt(i){if(CBF!==i||!D)return "";const it=D.items[i];
 const st=(D.sty||{})[it.id]||"",had=CBB&&CBV.has(it.id);
 const nics=[...new Set(SCANS.map(s=>s.topic||"").filter(x=>x))].slice(0,40);
 const prev=(CBB&&CBB.items||[]).find(x=>x.vid===it.id)||{};
 return '<div class="sec">Competitor bank me save karo <small> — style aur niche aap chunte hain; numbers us scan ke asli numbers hain</small></div>'+
 '<div class="card"><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'+
 '<label class="sub" style="display:block">Thumbnail ka style<select id="cbs"><option value="">— chuno —</option>'+
 Object.keys(STYL).filter(k=>k!=="unknown").map(k=>'<option value="'+k+'"'+(k===st?" selected":"")+'>'+esc(STYL[k])+'</option>').join("")+'</select></label>'+
 '<label class="sub" style="display:block">Niche / category<input type="text" id="cbn" list="cbnl" placeholder="jaise: UPSC current affairs, tech review" value="'+esc(prev.nic||"")+'"><datalist id="cbnl">'+nics.map(x=>'<option value="'+esc(x)+'">').join("")+'</datalist></label>'+
 '</div><label class="sub" style="display:block;margin-top:8px">Note — kya copy karna hai (optional)<textarea id="cbt" rows="2" style="width:100%" placeholder="jaise: title formula — number + curiosity; thumbnail me sirf 3 bade shabd">'+esc(prev.note||"")+'</textarea></label>'+
 '<div class="bar" style="margin-top:9px"><button class="go" onclick="cbSave('+i+')">'+ico("plus",14)+(had?"bank me update karo":"Competitor banao — bank me save karo")+'</button>'+
 '<button class="sm" onclick="CBF=-1;zoom('+i+')">band karo</button></div>'+
 (st?'<div class="sub">Style ka box tool ke classifier ke andaze ("'+esc(STYL[st]||st)+'") se bhar diya hai — galat ho to badal dein. Aapka chuna hua aapki raaye hai, tool ka naap nahi.</div>':
  '<div class="sub">Is video par tool ne style pehchana nahi — khud chun lein. Bank me jo likha hai wo aapki raaye hai; numbers us din ke scan se.</div>')+'</div>'}
async function cbSave(i){const it=D.items[i];
 const st=(document.getElementById("cbs")||{}).value||"",ni=((document.getElementById("cbn")||{}).value||"").trim(),no=((document.getElementById("cbt")||{}).value||"").trim();
 if(!st)return toast("style chuno — bank ka maayne hi style/niche ke saath hai","warn");
 let r;try{r=await jp("/api/cmpbsave",{id:cur,vid:it.id,style:st,nic:ni,note:no})}catch(e){return failToast(e,"bank save")}
 if(!r||r.err)return toast((r&&r.err)||"bank me save nahi hua");
 await cbGet(true);CBF=-1;toast("competitor bank me save ho gaya — kul "+r.n+" record");zoom(i)}
async function cbDelV(vid){let r;try{r=await jp("/api/cmpbdel",{vid:vid})}catch(e){return failToast(e,"bank delete")}
 if(!r||r.err)return toast((r&&r.err)||"delete nahi hua");await cbGet(true);toast("bank se hata diya");bankv()}
 async function cbSeed(){if(!cur)return toast("pehle koi scan chuno — ye button usi scan ki jeeti hui videos bharta hai","warn");
  const k=parseInt(($("#cbk")||{}).value||"10",10);const bb=$("#cbseed");if(bb)bb.disabled=true;
  let r;try{r=await jp("/api/cmpbseed",{id:cur,k:k})}catch(e){if(bb)bb.disabled=false;return failToast(e,"jeeton se bank bharo")}
  if(!r||r.error){if(bb)bb.disabled=false;return toast((r&&r.error)||"bank nahi bhara")}
  await cbGet(true);
  toast(r.added?(r.added+" jeeti hui videos bank me jud gayi — kul "+r.n+" record. Style classifier ka andaza hai — zoom me theek kar dein."):"kuch naya nahi mila — saari jeeti hui videos pehle se bank me hain");bankv()}
async function cbGo(vid,sid){if(!sid||!SCANS.some(s=>s.id===sid))return toast("is record ka scan ab is machine par nahi — record ki detail (title/style/niche) yahi mehfooz hai","warn");
 if(cur!==sid){cur=sid;D=null;IDEAS=null}
 const d=await ensureData();const ix=((d&&d.items)||[]).findIndex(x=>x.id===vid);
 if(ix<0)return toast("video us scan me nahi mila — shayad scan delete ho gaya hai","warn");
 go("cmp");await cmp();zoom(ix)}
async function bankv(){const _t=RTN;spin();const b=await cbGet(true);if(_t!==RTN)return;
 let h='<h2>'+ico("layers",18)+' Competitor bank</h2>'+
 '<div class="sub">Jo videos aap ne competitor maane — style aur niche aapne chune, numbers us din ke scan ke asli numbers hain. Channel ki creation date aur aakhri upload usi scan ki reading hai (source saath likha hai). Kuch bhi background me apne aap nahi judta — sirf aap ke click se: ya to ek-ek karke "Competitor banao", ya neeche ke button se ek scan ki jeeti hui videos ek click me.</div>';
 const inSc=!!(cur&&SCANS.some(s=>s.id===cur));
 const seedBar=inSc?('<div class="card"><h3>Ek click me bharo — is scan ki jeeti hui videos</h3>'+
  '<div class="sub">Jeet ka rule wahi jo Competitors par likha hai: views/day is scan ke median se 2× ya zyada. Style ka box tool ke classifier ke andaze se bhar jaata hai — record ke note me ye saaf likha hota hai, aur aap zoom me "bank me hai — style/niche update" se theek kar sakte hain. Niche = scan ka topic. Jo videos pehle se bank me hain wo dobara nahi judengi. Ye bhi sirf aap ke click se hota hai — koi kharcha, koi model nahi.</div>'+
  '<div class="bar"><label class="sub">kitni videos <select id="cbk"><option value="5">5 sabse badi jeet</option><option value="10" selected>10</option><option value="20">20</option><option value="50">saari jeeti hui (50 tak)</option></select></label>'+
  '<button class="go" id="cbseed" onclick="cbSeed()">'+ico("layers",14)+'jeeton se bank bharo</button></div></div>'):"";
 const items=b.items||[];
 if(!items.length)return h+seedBar+'<div class="card"><div class="sub">Abhi bank khaali hai. Do raaste hain: kisi bhi video ke poore analysis (zoom) ya card par <b>Competitor banao</b> ka button — style/niche khud chun kar save karo; ya upar wale button se is scan ki saari jeeti hui videos ek click me bhar dein.</div></div>'
 h+=seedBar;
 h+='<div class="kpi">'+kpi("competitors",fmt(items.length),"var(--acc)")+
  kpi("alag channels",fmt(new Set(items.map(x=>x.chan||"")).size))+
  kpi("niches",fmt(new Set(items.map(x=>x.nic||"")).size))+'</div>';
 h+='<table><thead><tr><th scope="col">Video</th><th scope="col">Channel · bana · aakhri upload</th><th scope="col">Style (aapka chuna)</th><th scope="col">Niche</th><th scope="col" class="num">views / views-per-day (save ke waqt)</th><th scope="col">Note</th><th scope="col"></th></tr></thead><tbody>';
 items.forEach(r=>{const sid=r.scan||"";
  h+='<tr><td class="l">'+(r.thumb?'<div class="bwrap" style="width:150px"><img src="'+imgu(r.thumb)+'" loading="lazy" alt="" style="width:150px"></div>':"")+
   '<b style="display:block;margin-top:4px">'+esc(String(r.title||r.vid||"").slice(0,80))+'</b><span class="sub">video id '+esc(r.vid||"")+'</span></td>'+
   '<td class="l"><b>'+esc(r.chan||"—")+'</b>'+(r.subs?'<div class="sub">'+fmt(r.subs)+' subscribers</div>':"")+
   (r.joined?'<div class="sub">bana: <b>'+fD(r.joined.d)+'</b>'+(r.joined.src==="about"?" (About page se)":" (sabse purani listing se — is se purana channel milna lazmi nahi)")+" · umr "+((Date.now()-new Date(r.joined.d+"T12:00:00").getTime())/31557600000).toFixed(1)+" saal":"")+'</div>'+
   (r.lastup?'<div class="sub">aakhri upload (us scan me): <b>'+fD(r.lastup.d)+'</b>'+(r.lastup.src==="scan"?" (listing ki reading)":"")+'</div>':
    (r.upl?'<div class="sub">is video ki upload: <b>'+fD(r.upl)+'</b> — ye topic scan tha, poora channel nahi, is liye channel ki date yahan nahi</div>':""))+'</td>'+
   '<td class="l">'+(r.style&&r.style!=="unknown"?esc(STYL[r.style]||r.style):'<span class="sub">— classifier pehchaan nahi paaya; video khol kar "style/niche update" se khud chun lein</span>')+'</td><td class="l">'+esc(r.nic||"—")+'</td>'+
   '<td class="num">'+fmt(r.views||0)+' / <b style="color:var(--acc)">'+(r.vpd!=null?fmt(r.vpd):"—")+'</b><div class="sub">save: '+esc((r.at||"").slice(0,10))+' ke hisaab se</div></td>'+
   '<td class="l" style="max-width:260px">'+(r.note?esc(r.note):'<span class="sub">—</span>')+'</td>'+
   '<td class="l"><div class="bar" style="margin:0"><a class="btn sm ytbtn" target="_blank" rel="noopener" href="https://www.youtube.com/watch?v='+esc(r.vid)+'" title="is competitor ko YouTube par naye tab me kholo" aria-label="YouTube par kholo">'+ico("ext",13)+'</a><button class="sm" title="is video ka link copy karo" aria-label="link copy karo" onclick="cpLink(\'https://www.youtube.com/watch?v='+esc(r.vid)+'\')">'+ico("copy",13)+'</button>'+(sid?'<button class="sm" onclick="cbGo(\''+esc(r.vid)+'\',\''+esc(sid)+'\')">'+ico("eye",13)+"poora analysis</button>":"")+
    '<button class="sm" onclick="cbDelV(\''+esc(r.vid)+'\')">'+ico("trash",13)+"hatao</button></div></td></tr>"});
 h+='</tbody></table><div class="sub">Numbers save ke waqt ke hain — views badhte rehte hain, is liye aaj ka asli number dekhne ke liye <b>poora analysis</b> wala scan khol ke views taaza karo. Style/niche/notes aapke hain — hataane par sirf record jaata hai, scan nahi.</div>';
 $("#main").innerHTML=h}
function uplNote(it){if(!it.upload)return "";
 let t=' · upload <b>'+fD(it.upload)+'</b>';
 if(it.pubts){const d=new Date(it.pubts*1000);
  t+=' '+stHH(d.getHours())+':'+String(d.getMinutes()).padStart(2,"0")+(it.pt?" (asli waqt — API ne diya)":" (andazan waqt — listing ke timestamp se)")+
     (d.getDay()===0||d.getDay()===6?" · weekend par chhapa":"")}
 return t}
function zoom(i){const it=D.items[i],sc=100/((it.an&&it.an.w)||1);
 const tb=(it.words||[]).map(w=>'<div class="oword" style="left:'+(w.x*sc)+'%;top:'+(w.y*sc)+'%;width:'+(w.w*sc)+'%;height:'+(w.h*sc)+'%"></div>').join("");
 const fb=(it.faces||[]).map(f=>'<div class="fbox" style="left:'+(f.x*sc)+'%;top:'+(f.y*sc)+'%;width:'+(f.w*sc)+'%;height:'+(f.h*sc)+'%"><span>chehra '+Math.round(f.area)+'%</span></div>').join("");
 const cm=(D&&D.kind==="channel")?(function(){const c=D.ch||{},s=D.cst||{},j=c.joined;
  return ' · channel bana <b>'+(j?fD(j.d):"—")+'</b>'+(j?(j.src==="about"?" (About page se)":" (sabse purani listing se)"):"")+
   (s.last?' · aakhri upload <b>'+fD(s.last)+'</b>'+(s.days_since!=null?' ('+s.days_since+' din pehle)':""):"")+
   (s.per_week?' · raftaar <b>'+s.per_week+'</b> video/hafta (is listing se gin kar)':"")}()):"";
 $("#main").innerHTML='<h2>'+esc(it.title)+'</h2><div class="sub">'+esc(it.channel)+' · '+fmt(it.views)+' views / '+(it.days||"?")+'d · views/day <b style="color:var(--acc)">'+fmt(vpd(it))+'</b>'+uplNote(it)+cm+
  (it.score!=null?' · banawas score <b class="'+scC(it.score)+'">'+it.score+'/100</b> <button class="iss-more" onclick="whyAt('+i+')">ye score kaise bana?</button>':"")+'</div>'+
 '<div class="two ztwo"><div><div class="sub">teal box = jo text tool ne padha · pink box = chehra</div><div class="owrap" style="width:100%"><img style="width:100%;border-radius:var(--r2)" src="'+imgu(it.thumb)+'">'+tb+fb+'</div></div>'+
 '<div><div class="sec">Kya kharab hai — aur uska ilaaj</div><div class="card">'+
  (it.vr?issList(it,i,true):'<span class="sub">is video par verdict record nahi hua — scan dobara chalao to ye hisaab bhi aa jayega</span>')+'</div>'+
  '<div class="sec">Score ka poora hisaab</div><div class="card">'+whyCard(it)+'</div>'+
  '<div class="sec">Is par likha text (OCR)</div><div class="card">'+(it.ts&&it.ts.text?esc(it.ts.text):'<span class="sub">kuch nahi mila</span>')+'</div>'+
   ((D.spon||{})[it.id]?('<div class="sec">Ads ka bojh — SponsorBlock <small> — logon ke marks, is tool ka naap nahi</small></div><div class="sub">kul '+stDur(D.spon[it.id].sec)+' sponsor/self-promo'+(it.dur?' — video ka '+Math.round(D.spon[it.id].sec*100/it.dur)+'%':'')+
     (((D.spon[it.id]||{}).segs||[]).length?(' · segments: '+D.spon[it.id].segs.slice(0,10).map(s=>stTm(s[0])+'–'+stTm(s[1])+' '+esc(s[2])).join(" · ")):"")+'</div>'):
    (D&&D.spon?'<div class="sec">Ads ka bojh — SponsorBlock</div><div class="sub">is video par koi mark nahi — iska matlab ads ka na hona zaroori nahi, balki abhi kisi ne mark nahi kiya.</div>':""))+
  styFixRow(it)+
  cbFormAt(i)+
  trSecAt(i)+
 '<div class="sec">Iske poore numbers</div><div class="card">'+chipsOf(it)+'</div></div></div>'+
 '<div id="idead"></div><div id="gdpd"></div>'+
 '<div class="bar" style="margin-top:14px">'+ytb(it.url)+ytc(it.url)+'<button class="go" onclick="ideaAt('+i+')">'+ico("spark",14)+'Idea copy karo</button><button class="go" onclick="aiAt('+i+')">'+ico("palette",14)+'AI se banao</button><button class="go" onclick="regenAt('+i+')">'+ico("refresh",14)+'Behtar banao</button><button class="go" onclick="gdpAt('+i+',&quot;gdpd&quot;)">'+ico("bars",14)+'Gehri analysis</button><button class="sm" onclick="cbOpen('+i+')">'+ico("layers",14)+(CBV.has(it.id)?"bank me hai — style/niche update":"Competitor banao")+'</button><button class="sm" onclick="cmp()">'+ico("back",14)+'wapas</button></div>'+VQH(i);vq(i)}
function regenAt(i){const it=D.items[i];if(!it.thumb)return toast("is video ka thumbnail nahi mila");regen(it.thumb,it.title,"",it.title)}
function regenMine(){if(!MINE)return toast("pehle thumbnail check karo");regen(MINE.path,MINE.path,"",TITLE||"")}
// "Copy the idea": us video ka ASLI tags/keywords (YouTube listing se — fact), aur
// us par Gemini ke banaye hue matched topics + taqatwar ideas ("model ka andaza" —
// kabhi naapon me nahi milte). Har idea ke saath uska thumbnail banane ka seedha
// rasta: AI page wahi idea + wahi thumbnail-shabd liye khulta hai.
let IDEAPK=null;
async function ideaAt(i){const it=D.items[i],el=document.getElementById("idead");
 if(!el)return;el.innerHTML='<div class="card"><div class="sub">idea-packet ban raha hai — us video ke asli tags/keywords se… (pehli baar me metadata ki thodi der lag sakti hai)</div></div>';
 let d;try{d=await j("/api/idea?vid="+encodeURIComponent(it.id)+(TOPIC?("&topic="+encodeURIComponent(TOPIC)):""))}
 catch(e){el.innerHTML='<div class="card"><div class="err">idea service tak pahuncha hi nahi: '+esc(e.message)+'</div></div>';return}
 IDEAPK=d;el.innerHTML=ideaPkCard(d);el.scrollIntoView({block:"nearest",behavior:"smooth"})}
function ideaPkCard(d){
 if(!d.ok)return '<div class="card"><div class="err">'+esc(d.error||"idea packet nahi bana")+'</div></div>';
 let h='<div class="card"><h3>'+ico("spark",16)+'Idea packet — '+esc((d.title||"").slice(0,80))+'</h3>';
 h+='<div class="lbl">Asli tags — channel ne khud lagaye the (koi andaaza nahi)</div><div class="tagrow">'+
   ((d.tags||[]).length?d.tags.map(t=>'<span class="chip">'+esc(t)+'</span>').join(""):'<span class="sub">is video par koi tags nahi mile</span>')+'</div>'+
   ((d.tags||[]).length?'<div class="bar" style="margin:8px 0 0"><button class="sm" onclick="cpText((IDEAPK.tags||[]).join(\', \'))">'+ico("copy",13)+'saare tags copy</button></div>':"")+
   '<div class="lbl" style="margin-top:12px">Keywords — title+tags+description se gine gaye (ginti, andaza nahi)</div><div class="tagrow">'+
   ((d.keywords||[]).length?d.keywords.map(w=>'<span class="chip">'+esc(w)+'</span>').join(""):'<span class="sub">kuch nahi mila</span>')+'</div>'+
   ((d.keywords||[]).length?'<div class="bar" style="margin:8px 0 0"><button class="sm" onclick="cpText((IDEAPK.keywords||[]).join(\', \'))">'+ico("copy",13)+'saare keywords copy</button></div>':"");
 if((d.topics||[]).length){h+='<div class="lbl" style="margin-top:12px">Topics jo is video ke audience se milte hain <small class="sub"> — model ka andaza ('+esc(d.model||"gemini")+'), aapka faisla</small></div>'+
   d.topics.map(t=>'<div style="margin:6px 0"><b>'+esc(t.t)+'</b> <button class="iss-more" onclick="cpText(\''+esc(t.t).replace(/'/g,"")+'\')">copy</button><div class="sub">'+esc(t.why)+'</div></div>').join("")}
 if(d.no_key)h+='<div class="sub" style="margin-top:12px">Tags/keywords ASLI hain — in par strong ideas banane ke liye Gemini key chahiye (AI page par daal dein). Phir ye button ideas bhi dega.</div>';
 else if((d.ideas||[]).length){h+='<div class="lbl" style="margin-top:12px">Taqatwar video ideas inhi tags/keywords par <small class="sub"> — model ka andaza ('+esc(d.model||"gemini")+'), naap aapka; har idea ke saath thumbnail banane ka rasta</small></div>'+
   d.ideas.map((x,n)=>'<div style="margin:10px 0;padding:10px;border:1px solid var(--br);border-radius:var(--r2)"><b>'+(n+1)+'. '+esc(x.t)+'</b>'+
    (x.words?'<div class="tagrow" style="margin-top:4px"><span class="chip">thumbnail par: <b>'+esc(x.words)+'</b></span></div>':"")+
    '<div class="sub" style="margin-top:4px">'+esc(x.angle||"")+'</div>'+
    '<div class="bar" style="margin:8px 0 0"><button class="sm" onclick="ideaPkCopy('+n+')">'+ico("copy",13)+'Copy the idea</button>'+
    '<button class="sm go" onclick="ideaThumb('+n+')">'+ico("palette",13)+'Is idea ka thumbnail banao</button></div></div>').join("")}
 else if(d.error)h+='<div class="err" style="margin-top:10px">ideas nahi ban paye: '+esc(d.error)+'</div><div class="sub">tags/keywords phir bhi upar ASLI maujood hain — copy kar ke apne kaam lagayein.</div>';
 return h+"</div>"}
function ideaPkCopy(n){const x=(IDEAPK.ideas||[])[n];if(!x)return;cpText(x.t+(x.angle?" — "+x.angle:"")+(x.words?" | thumbnail text: "+x.words:""));toast("idea copy — notes me paste karein")}
function ideaThumb(n){const x=(IDEAPK.ideas||[])[n];if(!x)return;AQ.idea=x.t;AQ.words=x.words||"";AIRES=null;go("ai")}

// Transcription: video ke apne subtitles (YouTube ka diya hua). Ye kaam kabhi
// apne aap nahi hota — sirf button par, aur ek baar disk par cache. Jis video par
// subtitles hi nahi, wahan "nahi milte" saaf likha jayega, analysis jhootha nahi.
// Aise videos (khamosh, quiz, text-only slides) ke liye doosra rasta hai: screen par
// likha text frames ka OCR — dono ka matlab alag hai, is liye screen par bhi alag likha jaata hai.
let TRJ=null;
let TRP=null;
function trpStop(){if(TRP){clearInterval(TRP);TRP=null}}
function trpPoll(id){trpStop();TRP=setInterval(async()=>{let p;try{p=await j("/api/trp?id="+encodeURIComponent(id))}catch(e){return}
 const el=$("#trp");if(!el){trpStop();return}
 if(p.none)return;
 el.textContent=(p.stage==="ocr")?("progress: frame "+(p.done|0)+"/"+(p.total|0)+" OCR ho chuka — thora rukein"):("video ka sabse chhota format download ho raha hai — thora rukein");},4000)}
function trSecAt(i){const it=D.items[i],t=(D.tr||{})[it.id];
 if(TRJ&&TRJ.id===it.id)return '<div class="sec">'+(TRJ.ocr?"Screen text (OCR)":"Transcription")+'</div>'+
  '<div class="sub"><span id="trp">'+(TRJ.ocr?"video ka sabse chhota format download ho raha hai…":"subtitles laaye ja rahe hain…")+'</span>'+(TRJ.ocr?' — chhoti video par ~1 minute, lambi (15+ minute) par 5–10 minute tak lag sakte hain, lekin ek hi baar; phir hamesha cache. Neeche wale button dubara dabane se doosra job nahi chalta — wahi kaam complete hoke milta hai.':' ek hi baar; dobara khulne par cache se seconds me.')+'</div>'+
  '<div class="bar"><button class="go" disabled style="opacity:.5;cursor:progress">'+ico("file",14)+'Transcription laao</button>'+
  '<button class="sm" disabled style="opacity:.5;cursor:progress">'+ico("file",14)+'Screen text (OCR) laao</button></div>';
 if(t&&t.text){const ocr=t.kind==="ocr";
  return '<div class="sec">'+(ocr?'Screen text (OCR) <small> — frames se padha gaya screen ka likha text; ye video ki awaz nahi</small>':'Transcription <small> — video ke apne subtitles, tool ka likha hua nahi</small>')+'</div>'+
   '<div class="sub">'+esc(t.note||"")+(t.cached?' · ye pehle se cache me tha — dobara koi kharcha nahi':"")+(t.cut?' · text lamba tha, pehle 60,000 akshar dikhaye ja rahe hain':"")+(ocr&&t.frames?' · '+t.frames+' frames se padha gaya':"")+(ocr?' · neeche wala box scroll karein — har line time ke saath andar hai, sirf pehli kuch lines nahi':"")+'</div>'+
   '<div class="trbox">'+esc(t.text)+'</div>';}
 if(t&&t.error){return '<div class="sec">Transcription</div><div class="err">'+esc(t.error)+'</div>'+
   '<div class="bar"><button class="go" onclick="trGo('+i+')">'+ico("file",14)+'phir se koshish karo</button>'+
   '<button class="sm" onclick="trOcrGo('+i+')">'+ico("file",14)+'Screen text (OCR) laao</button></div>'+
   (t.no_ocr?'<div class="sub">is video par subtitles nahi, lekin screen par text likha hota hai (quiz/whiteboard type) to wo is rasta padha ja sakta hai — frames ka OCR, awaz nahi.</div>'
    :'<div class="sub">rate-limit ya network ki baat ho to thori der baad "phir se" dabayein; aur agar is video par subtitles hote hi na hon to screen-text OCR ka raasta hai — frames ka OCR, awaz nahi.</div>');}
 return '<div class="sec">Transcription <small> — sirf tab jab aap maange</small></div>'+
  '<div class="sub">is video ke subtitles laane ka kharcha: ek baar YouTube se subtitles (kuch second), phir hamesha cache. Kuch videos par subtitles hote hi nahi — wahan seedha likha jayega, jhooth nahi.</div>'+
  '<div class="bar"><button class="go" onclick="trGo('+i+')">'+ico("file",14)+'Transcription laao</button>'+
  '<button class="sm" onclick="trOcrGo('+i+')">'+ico("file",14)+'Screen text (OCR) laao</button></div>'+
  '<div class="sub">video khamosh hai ya sirf screen par text hai (quiz, slides)? Transcription khali aayega — doosra button us screen ka likha text frames se padhta hai (chhoti video par ~1 minute, lambi par 5–10 minute tak — live progress dikhegi; ek hi baar, phir cache).</div>';}
async function trGo(i){const it=D.items[i];D.tr=D.tr||{};TRJ={id:it.id};zoom(i);
 let r;try{r=await j("/api/tr?id="+encodeURIComponent(it.id))}catch(e){r={error:e.message}}
 TRJ=null;if(r.error&&/subtitles YouTube par nahi/.test(r.error))r.no_ocr=1;
 D.tr[it.id]=r;zoom(i);if(r.error)toast("transcription: "+r.error)}
async function trOcrGo(i){const it=D.items[i];D.tr=D.tr||{};TRJ={id:it.id,ocr:1};zoom(i);trpPoll(it.id);
 let r;try{r=await j("/api/tr?id="+encodeURIComponent(it.id)+"&ocr=1")}catch(e){r={error:e.message}}
 trpStop();TRJ=null;if(r.error)r.no_ocr=0;
 D.tr[it.id]=r;zoom(i);if(r.error)toast("screen text: "+r.error)}

// Bulk transcription: chuni hui videos ke subtitles ek-ek karke — server jo pehle se
// cache karta hai wo dobara network par jaata hi nahi, is liye bar-bar chalani par
// kharcha nahi hota. Limit is liye hai (subtitles 15/click, OCR 4/click) ke ek click
// ghanton me na badal jaye; baaki agle click me. Jo video bina subtitles ka nikla,
// uski row usi waqt OCR ka raasta dikha deti hai — baad me dhoondhna nahi padta.
let BQ=null;
function bulkTr(ocr){if(!SEL.size)return toast("pehle videos chuno (card par tick ya Table me select)");
 const cap=ocr?4:15,ids=[...SEL].slice(0,cap);
 BQ={ids,ocr,st:{},done:0,skipped:SEL.size-ids.length};
 (async()=>{for(const id of ids){BQ.st[id]="… chal raha hai";bqRender();
   let r;try{r=await j("/api/tr?id="+encodeURIComponent(id)+(ocr?"&ocr=1":""))}catch(e){r={error:e.message}}
   D.tr=D.tr||{};D.tr[id]=r;
   const _n=(r.text||"").length;  // safai ke baad 400 ka cap hai — cap lage to "400+" dikhao, warna user ko lagega sirf itna hi mila
   BQ.st[id]=r.ok?((r.cached?"pehle se cache me tha — 0 kharcha ✓ ":"aa gaya ✓ ")+(_n>=400?"400+ akshar (screen par aur bhi tha — dikhaya gaya hissa 400)":_n+" akshar"))
                 :("✗ "+String(r.error||"?").slice(0,110)+(/subtitles|429/i.test(String(r.error||""))?" — is par screen text OCR kaam kar sakta hai: video zoom karke 'Screen text (OCR)' button, ya neeche wala bulk OCR":""));
   BQ.done++;bqRender()}
  toast((ocr?"screen-text OCR":"subtitles")+" bulk khatam — "+ids.filter(x=>String(BQ.st[x]).indexOf("✓")>=0).length+"/"+ids.length+" ko mila"+(BQ.skipped?(" · "+BQ.skipped+" chhodi (limit "+cap+"/click — agle click me chalaayein)"):""))})();
 bqRender();}
function bqRender(){if(!BQ)return;let b=document.getElementById("bulkq");
 if(!b){b=document.createElement("div");b.id="bulkq";b.className="card";b.style.cssText="position:fixed;right:16px;bottom:56px;max-width:420px;max-height:60vh;overflow:auto;z-index:60";document.body.appendChild(b)}
 const nm=id=>{const it=((D&&D.items)||[]).find(x=>x.id===id);return it?(it.title||"").slice(0,52):id};
 b.innerHTML='<h3>Bulk '+(BQ.ocr?"screen-text OCR":"subtitles")+' — '+BQ.done+"/"+BQ.ids.length+'</h3>'+
  '<div class="sub">ek-ek karke, order wahi; jo pehle se cache me hai use koi network kharcha nahi. '+(BQ.ocr?"OCR video download + frames padhta hai — is liye ek video 1–3 minute le sakta hai, limit 4/click.":"Limit 15/click — baaki agle click me.")+(BQ.skipped?'<br><b>'+BQ.skipped+' chhodi gayi</b> (click ki limit '+ (BQ.ocr?4:15) +') — chahen to dobara chalaayein.':"")+'</div>'+
  BQ.ids.map(id=>'<div class="sub" style="margin:4px 0"><b>'+esc(nm(id))+'</b><br>'+esc(BQ.st[id]||"khamosh")+'</div>').join("")+
  '<div class="bar"><button class="sm" onclick="document.getElementById(\'bulkq\').remove();BQ=null">band karo</button></div>'}

// ---------- us video ki ASLI listing (tags/description/chapters) + CTR/retention ----------
// Sach: YouTube ka CTR aur retention sirf channel ke malik ko milta hai (Analytics API bhi
// owner-authorized hai). To do cheezein alag-alag dikhi jaati hain: (1) jo ASLI public data
// se naapa ja sakta hai (tags, description, chapters, likes, comments, engagement),
// (2) jo aapne apne Studio se daala — wo hi asli CTR/retention hai.
function VQH(i){return '<div class="sec">Us video ki ASLI listing <small> — tags, description, chapters, likes, comments: jo us channel ne khud lagaya hai, koi andaaza nahi</small></div><div id="vq"><div class="sub">YouTube se asli metadata aa raha hai… (pehli baar ~1 second, phir cache)</div></div>'}
function ideaOf(it){const tg=(it.tags||[]).slice(0,10).join(", ");
 const w=((it.ts||{}).text||"").replace(/\s+/g," ").slice(0,70);
 const d=(it.dprev||"").replace(/\s+/g," ").slice(0,200);
 return [it.title,tg?("the creator tagged it as: "+tg):"",d?("the video is described as: "+d):"",
  w?("its current thumbnail reads: "+w):""].filter(x=>x).join(" | ").slice(0,300)}
function pctOf(v,arr){if(v==null||!arr||arr.length<4)return null;const s=arr.filter(x=>x!=null).sort((a,b)=>a-b);
 if(!s.length)return null;let k=0;for(const x of s)if(x<=v)k++;return Math.round(k*100/s.length)}
function engLR(it){const v=it.views||0;return (it.likes&&v)?it.likes*100/v:null}
function engCR(it){const v=it.views||0;return (it.cmts&&v)?it.cmts*100/v:null}
function tscN(v){if(!v||!v.length)return 0;const ok=v.filter(x=>x.s==="ok").length,wn=v.filter(x=>x.s==="warn").length;return Math.round((ok+wn*0.4)*100/v.length)}
function idxOf(it,L){const ts=it.score!=null?it.score:0,ls=it.ls!=null?it.ls:0,ep=pctOf(engLR(it),L.lr||[]);
 const ctr=Math.round(ts*0.5+ls*0.25+(ep==null?50:ep)*0.25);
 const dur=it.dur||0;let r=50+(it.nch?12:-8);r+=Math.max(-15,Math.min(15,(ep==null?0:ep-50)*0.3));
 if(dur>1800)r-=10;else if(dur<300)r+=6;const ret=Math.round(Math.max(5,Math.min(95,r)));
 return {ctr:ctr,ret:ret,ep:ep}}
async function vq(i){const it=D.items[i],el=$("#vq");if(!el)return;
 let d={};try{d=await j("/api/meta?vid="+it.id)}catch(e){el.innerHTML='<div class="err">metadata nahi mila: '+esc(e.message)+'</div>';return}
 if(!d.ok){el.innerHTML='<div class="err">'+esc(d.error||"metadata nahi mila")+'</div>';return}
 const m=d.meta,S=d.seo||{},E=d.eng||{},O=d.own||{};
 const L={lr:D.items.map(engLR).filter(x=>x!=null)};
 const ep=pctOf(engLR(it),L.lr),IX=idxOf(it,L),TSN=tscore(it.title||""),TSC=tscN(TSN);
 const real=(v)=>v==null?'<span class="sub">—</span>':fmt(v);
 window._TQ=m.tags||[];
 const tg=(window._TQ).map((t,k)=>'<span class="tag" onclick="tagIn(window._TQ['+k+'])">'+esc(t)+'</span>').join("");
 const TCK='<h3>Title score — <span class="'+scC(TSC)+'">'+TSC+'/100</span> <span class="sub">(is tool ka formula, uske ASLI title par)</span></h3>'+
  TSN.map(v=>'<div class="ck"><i class="'+(v.s==="ok"?"hi":v.s==="warn"?"mid":"lo")+'">'+(v.s==="ok"?"✓":v.s==="warn"?"!":"✗")+'</i><div><b>'+esc(v.k)+'</b><div class="n">'+esc(v.v)+' — '+esc(v.nn)+'</div></div></div>').join("");
 const ch=(m.chaps||[]).map(c=>{const s=c.t|0,h=Math.floor(s/3600),mn=Math.floor(s/60)%60,tm=(h?h+":"+String(mn).padStart(2,"0"):mn)+":"+String(s%60).padStart(2,"0");return '<tr><td class="num">'+tm+'</td><td>'+esc(c.s)+'</td></tr>';}).join("");
 const ck=(S.chk||[]).map(c=>'<div class="ck"><i class="'+(c.s==="ok"?"hi":c.s==="warn"?"mid":"lo")+'">'+(c.s==="ok"?"✓":c.s==="warn"?"!":"✗")+'</i><div><b>'+esc(c.t)+'</b><div class="n">'+esc(c.n)+'</div></div></div>').join("");
 el.innerHTML='<div class="kpi">'+kpi("views (asli)",real(m.views))+kpi("likes (asli)",real(m.likes))+
  kpi("comments (asli)",real(m.cmts))+kpi("subscribers (asli)",m.subs==null?"—":fmt(m.subs))+
  kpi("tags (asli)",(m.tags||[]).length,(m.tags||[]).length?"var(--grn)":"var(--red)")+
  kpi("description",fmt((m.desc||"").length)+" ch")+kpi("chapters",(m.chaps||[]).length)+
  kpi("duration",(m.dur?Math.floor(m.dur/60)+"m"+(m.dur%60)+"s":"—"))+'</div>'+
  '<div class="card"><h3>Listing score — <span class="'+scC(S.ls)+'">'+S.ls+'/100</span> <span class="sub">(is video ki ASLI listing jaanchi gayi)</span></h3>'+
  '<div class="sub">Ye score us channel dwara <b>lagaye gaye tags, description aur chapters</b> se banta hai — jo data us video par maujood hai usi par, isliye ye 100% asli hai. Ye CTR nahi hai: listing ki safai ka naap hai.</div>'+ck+'</div>'+
  '<div class="sec">Us video ki TITLE ki jaanch <small> — is tool ka formula, uska ASLI title liya gaya</small></div><div class="card">'+TCK+'</div>'+
 '<div class="two"><div><div class="sec">ASLI tags — jo is video par lagaye gaye ('+(m.tags||[]).length+')</div><div class="card">'+(tg||'<span class="sub">is video par koi tag nahi lagaya gaya</span>')+'</div>'+
  '<div class="sub">Title ke jo shabd tags/description me maujood hain: '+(S.hit||[]).map(w=>'<span class="chip" style="color:var(--grn)">'+esc(w)+'</span>').join("")+'</div>'+
  '<div class="sub">Jo shabd sirf title me hain (kahin dohraye nahi gaye): '+(S.miss||[]).map(w=>'<span class="chip" style="color:var(--red)">'+esc(w)+'</span>').join("")+'</div></div>'+
  '<div><div class="sec">ASLI description — poori, jaisi usne likhi ('+((m.desc||"").length)+' ch)</div>'+
  '<div class="card"><pre class="desc">'+esc(m.desc||"(kuch nahi likha)")+'</pre></div>'+
  (ch?('<div class="sec">ASLI chapters ('+(m.chaps||[]).length+')</div><table><tr><th scope="col">time</th><th scope="col">jo usne likha</th></tr>'+ch+'</table>'):"")+
  '</div></div>'+
  '<div class="sec">CTR aur retention — imaandari se</div><div class="card"><h3>Asli CTR/retention: sirf aapke paan</h3>'+
  '<div class="sub">YouTube CTR aur retention <b>sirf channel ke malik</b> ko deta hai (YouTube Analytics API bhi owner-authorized hai). Kisi aur channel ki video ka CTR bahar se laane ka koi rasta nahi — jo tool dikhaye wo ya to <b>aapka daala hua asli number</b> hai, ya <b>napa hua index</b>. Dono neeche alag-alag label ke saath hain.</div>'+
  '<div class="kpi">'+kpi("engagement: likes/views",E.lr==null?"—":E.lr+"%",E.lr!=null&&E.lr>=3?"var(--grn)":"")+
  kpi("engagement: comments/views",E.cr==null?"—":E.cr+"%")+
  kpi("likes/views percentile",ep==null?"—":(ep+"% in "+D.items.length),ep!=null&&ep>=60?"var(--grn)":"")+
  kpi("thumbnail banawas",it.score==null?"—":it.score+"/100",cc(it.score))+kpi("listing score",S.ls+"/100",cc(S.ls))+'</div>'+
  '<div class="sub">Ye ginti ASLI counts se hai (likes ÷ views, comments ÷ views) — in 50 videos me uski position percentile me. Ye CTR ki jagah nahi, CTR ke saath sabse zyada related public signal hai.</div>'+
  '<div class="kpi" style="margin-top:10px">'+kpi("CTR index <span class=sub>(andaza)</span>",IX.ctr+"/100",cc(IX.ctr))+
  kpi("retention index <span class=sub>(andaza)</span>",IX.ret+"/100",cc(IX.ret))+'</div>'+
  '<div class="sub"><b>index ka matlab:</b> CTR index = thumbnail banawas 50% + listing 25% + likes/views percentile 25%. Retention index = chapters + video ki lambai + engagement percentile. Ye <b>in '+D.items.length+' videos ke andar relative position</b> hai, YouTube ka CTR/retention nahi — isliye sirf apne channel ke A/B tests se hi pakka pata chalta hai.</div>'+
  '<div class="bar" style="margin-top:10px"><input type="text" id="ownc" placeholder="apni video ka ASLI CTR % (Studio se), jaise 4.7" style="min-width:180px" value="'+(O.ctr!=null?O.ctr:"")+'">'+
  '<input type="text" id="ownr" placeholder="ASLI average view duration % / retention, jaise 42" style="min-width:180px" value="'+(O.ret!=null?O.ret:"")+'">'+
  '<button class="go" onclick="saveOwn(\''+it.id+'\')">asli number save karo</button></div>'+
  (O.ctr!=null||O.ret!=null?'<div class="sub" style="margin-top:6px">PEHLE SE SAVE HUA ASLI NUMBER ('+esc(it.id)+'): '+(O.ctr!=null?'CTR <b style="color:var(--grn)">'+O.ctr+'%</b> ':"")+(O.ret!=null?'retention <b style="color:var(--grn)">'+O.ret+'%</b> ':"")+'<span class="sub">daala gaya '+esc(O.at||"")+'</span></div>':"")+
  '<div class="sub" style="margin-top:6px">Note: ye numbers isi video ke liye hain ('+esc(it.id)+'). Apni video ka CTR/retention daalne ke liye "Meri Thumbnail" me uska link daal kar check karo — wahan bhi yahi form aayega.</div></div>'+
  '<div class="sec">Is video ke liye aapke paas kya option hai</div><div class="card">'+
  '<div class="bar"><button class="go" onclick="regenAt('+i+')">'+ico("refresh",14)+'Iski photo ka behtar version (muft)</button>'+
  '<button class="go" onclick="aiInsp('+i+')">'+ico("palette",14)+'Is se inspire ho kar naya (AI — naya scene + uske title ke shabd)</button>'+
  '<button class="sm" onclick="up4k(\''+it.thumb+'\')">'+ico("up",14)+'Is thumbnail ka 4K master</button>'+
  '<button class="sm" onclick="mkIdea(\''+esc(it.id)+'\')">'+ico("pen",14)+'Iske tags se title banao</button></div>'+
  '<div class="sub"><b>Behtar banao</b> = wohi photo, alag composition/bada text/contrast — koi naya scene nahi, isliye copyright ka sawal hi nahi. <b>AI se banao</b> = uske scene ka <b>idea</b> lekar naya scene (strength 0.55 par rakha hai: naqli se bachne ke liye). Copyright ka faisla aapka hai — tool sirf farak naap kar dikhata hai (neeche "inspired vs copy" ka number).</div>'+
  '<div id="u4"></div></div>'}
function tagIn(t){TITLE=(TITLE?TITLE+" ":"")+t;go("tl")}
function mkIdea(id){const it=D.items.filter(x=>x.id===id)[0];if(!it)return;
 const tg=(it.tags||[]).slice(0,6).join(" ");TITLE=tg||it.title;go("tl")}
async function aiInsp(i){const it=D.items[i];if(!it.thumb)return toast("is video ka thumbnail nahi mila");
 AQ.idea=ideaOf(it);AQ.ref=it.thumb;AQ.res="hd";AQ.words="";AIRES=null;
 // text bhi saath bhejte hain: us video ke title se 2-3 shabd jo uske thumbnail par pehle se
 // nahi likhe (server ka wahi chooser jo Behtar banao use karta hai) — warna result sirf khaali scene hota.
 try{const p=await j("/api/pick?title="+encodeURIComponent(it.title)+"&avoid="+encodeURIComponent((it.ts&&it.ts.text)||""));AQ.words=p.words||""}catch(e){}
 go("ai")}
async function saveOwn(vid){const c=($("#ownc")||{}).value||"",r=($("#ownr")||{}).value||"";
 if(!c&&!r)return toast("CTR ya retention likho");
 try{const d=await jp("/api/own",{vid:vid,ctr:c,ret:r});
  if(d.error)return toast(d.error,"bad","Number save nahi hua");toast("asli number save ho gaya — "+vid,"ok");vq(D.items.findIndex(x=>x.id===vid))}catch(e){failToast(e,"number save karna")}}
async function up4k(p){const el=$("#u4");if(el)el.innerHTML='<div class="sub">4K ban raha hai… (muft rasta: Pillow, 2-3 second)</div>';
 try{const d=await jp("/api/upscale",{ref:p,mode:"free"});
  if(d.error){if(el)el.innerHTML='<div class="err">'+esc(d.error)+'</div>';return}
  if(el)el.innerHTML='<div class="sec">4K master (muft: Pillow Lanczos)</div><div class="sub">'+d.w+'×'+d.h+' · sharpness '+d.sharp+' · <code>'+esc(d.path)+'</code> — ye sirf tasveer badi karta hai, nayi detail paida nahi hoti. Asli detail chahiye to AI wala rasta (~$0.010) neeche.</div><img src="'+imgu(d.path)+'" style="width:100%;max-width:900px;border-radius:var(--r2)">'+
   '<div class="bar"><button class="go" onclick="up4kAI(\''+p.replace(/'/g,"")+'\')">'+ico("up",14)+'AI se 4K (Runware upscale, ~$0.010)</button><a class="sm" href="'+imgu(d.path)+'" download>download</a></div>'}
 catch(e){if(el)el.innerHTML='<div class="err">'+esc(e.message)+'</div>'}}
async function up4kAI(p){const el=$("#u4");if(el)el.innerHTML='<div class="sub">Runware ka upscale chal raha hai (~13 second)…</div>';
 try{const d=await jp("/api/upscale",{ref:p,mode:"ai"});
  if(d.error){if(el)el.innerHTML='<div class="err">'+esc(d.error)+'</div>';return}
  if(el)el.innerHTML='<div class="sec">4K master (AI upscale — asli detail)</div><div class="sub">'+d.w+'×'+d.h+' · kharcha <b>$'+Number(d.usd).toFixed(4)+'</b> · sharpness '+d.sharp+' · model '+esc(d.model||"")+' · <code>'+esc(d.path)+'</code></div><img src="'+imgu(d.path)+'" style="width:100%;max-width:900px;border-radius:var(--r2)"><div class="bar"><a class="sm" href="'+imgu(d.path)+'" download>download</a></div>'}
 catch(e){if(el)el.innerHTML='<div class="err">'+esc(e.message)+'</div>'}}

// ---------- deep analysis: kaun sa pattern sach me chalta hai ----------
function liftBar(l){const w=Math.max(4,Math.min(100,Math.round(l*42))),c=l>=1.25?"var(--grn)":l<=0.8?"var(--red)":"var(--mut)";
 return '<span class="lift" style="color:'+c+'">'+l+'×</span> <span class="bar2"><i style="width:'+w+'%;background:'+c+'"></i></span>'}
const BLAB={text_size:"bada text @320px (px)",text_contrast:"text contrast (:1)",words:"text ke shabd",brightness:"brightness",depth:"tonal depth",clutter:"bheed (edges %)",saturation:"range",face_pct:"chehra (% of frame)"};
// ---------- Deep Analysis: poori channel ki samajh ----------
// Studio aur VidIQ ye do cheezein dete hain, aur is tool ke paas un ka data pehle se
// mojood hai: (1) outlier — har video ko USI channel ke median views/day se tolna
// (dusre channel ka median milana natija bigaad deta, is liye group har channel ka
// apna); (2) keywords — jo tags channel ne khud lagaye aur jo us ne title me likha:
// jo tag title me nahi wo chhuta hua keyword hai. Yahan koi andaze wala keyword
// nahi juda — jo gin-ta hai wo asli tags aur asli titles se aata hai.
function dxMed(a){if(!a.length)return 0;const t=a.slice().sort((x,y)=>x-y);const m=t.length>>1;
 return t.length%2?t[m]:(t[m-1]+t[m])/2}
function dxBar(p,al){return '<div style="height:9px;border-radius:var(--r0);width:'+
 Math.max(2,Math.round(Math.min(1,p)*100))+'%;background:rgba(var(--accrgb),'+(al||0.5)+')"></div>'}
// dxDiv: ratio ka chart. Beech ki rekha = 1.00x, yaani "apne ghere ke barabar".
// Dayen taraf zyada (1x se 3x tak), bayen taraf kam (1x se 0x tak). Sirf number
// dikhane se behtar: is se pata chalta hai ke farq kitni *badi* hai.
function dxDiv(r0){const r=Math.max(1/30,Math.min(30,r0)),rt=r>=1;
 // Ratio ka sahi paimana tauzani (log) hai, linear nahi: 2x aur 0.5x barabar
 // chourai ke hotay hain (ye hi ratio ka matlab hai), aur 4x aur 25x aapas me
 // alag dikhte hain — linear me dono ek jaise bhar jate, jo jhooth hota.
 // Upar ki hadd 30x hai (is data ki limit); asli maan har bar par likha hota hai.
 const t=Math.log(Math.max(r,1/r))/Math.log(30);
 const w=Math.max(1.5,Math.min(50,t*50)),ml=rt?50:50-w;
 const col=rt?(r>=1.5?"var(--ok)":"rgba(var(--accrgb),.75)"):"rgba(var(--badrgb),.7)";
 return '<div title="bar ka beech = 1.00x · ye video '+r0.toFixed(2)+'x (lambai log paimana par)"'+
  ' style="position:relative;height:9px;margin-top:4px;border-radius:var(--r0);background:var(--panel2);min-width:118px">'+
  '<i style="position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--edge)"></i>'+
  '<i style="position:absolute;top:0;bottom:0;left:'+ml.toFixed(1)+'%;width:'+w.toFixed(1)+'%;border-radius:var(--r0);background:'+col+'"></i></div>'}
function dxOut(items){
 const by={};items.forEach(it=>{if(it.views==null||it.days==null)return;
  const k=it.channel||"(channel ka naam nahi)";(by[k]=by[k]||[]).push(it)});
 const ok=Object.keys(by).filter(k=>by[k].length>=5),skip=Object.keys(by).filter(k=>by[k].length<5);
 if(!ok.length)return '<div class="sec">Outliers <small> — apne aap se tolna</small></div><div class="card">'+
  '<div class="sub">Kisi bhi channel ke paas 5 se kam naapi gayi videos hain — median ke liye itni chahiye hoti hain. '+
  'Is liye ye hissa abhi nahi ban sakta.</div></div>';
 const rows=[],bandsN={};
 ok.forEach(k=>{const arr=by[k],cm=dxMed(arr.map(it=>vpd(it))),ds=arr.map(it=>it.days||0).sort((a,b)=>a-b);
  const q=p=>ds[Math.max(0,Math.min(ds.length-1,Math.floor(ds.length*p)))];
  const lim=[q(0.25),q(0.5),q(0.75)],B4=[[-1,lim[0]],[lim[0]+1,lim[1]],[lim[1]+1,lim[2]],[lim[2]+1,1/0]];
  const lab=b=>(b[1]===1/0?b[0]+"+ din":(b[0]<0?0:b[0])+"–"+b[1]+" din");
  const bm=B4.map(b=>{const vs=arr.filter(it=>{const d=it.days||0;return d>=b[0]&&d<=b[1]}).map(it=>vpd(it));
   if(vs.length>=5){bandsN[lab(b)]=(bandsN[lab(b)]||0)+vs.length;return dxMed(vs)}return 0});
  arr.forEach(it=>{const v=vpd(it),d=it.days||0,bi=B4.findIndex(b=>d>=b[0]&&d<=b[1]);
   const med=bm[bi]||cm;if(!med)return;
   rows.push({it:it,ix:items.indexOf(it),ch:k,med:med,v:v,basis:bm[bi]?"umr":"channel",
    band:lab(B4[bi]),r:med?v/med:0,extra:Math.round((v-med)*(d||1))})})});
 if(!rows.length)return "";
 const B=[["3x se upar",r=>r.r>=3,"var(--ok)"],["2–3x",r=>r.r>=2&&r.r<3,"var(--ok)"],
  ["1.25–2x",r=>r.r>=1.25&&r.r<2,"var(--acc)"],["0.8–1.25x",r=>r.r>=0.8&&r.r<1.25,"var(--mut)"],
  ["0.5–0.8x",r=>r.r>=0.5&&r.r<0.8,"var(--warn)"],["aadhe se bhi kam",r=>r.r<0.5,"var(--bad)"]];
 const cnt=B.map(b=>rows.filter(b[1]).length),mx=Math.max.apply(null,cnt)||1;
 const dist='<table class="stt"><thead><tr><th scope="col" class="l no">apni umr ke median ke muqable</th><th scope="col" class="no">videos</th>'+
  '<th scope="col" class="l no">kinaar</th></tr></thead><tbody>'+B.map((b,i)=>
  '<tr><td class="l" style="color:'+b[2]+'">'+b[0]+'</td><td>'+cnt[i]+'</td><td class="l">'+dxBar(cnt[i]/mx)+'</td></tr>').join("")+
  '</tbody></table>';
 const row=r=>'<tr onclick="zoom('+r.ix+')"><td class="l"><b>'+esc((r.it.title||"").slice(0,58))+'</b>'+
  '<span class="sub"> · '+esc(r.ch.slice(0,22))+' · '+(r.it.days||"?")+' din · '+(r.it.views!=null?fmt(r.it.views)+" views":"?")+'</span></td>'+
  '<td>'+fmt(r.v)+'</td><td>'+fmt(r.med)+'<span class="sub"> · '+(r.basis==="umr"?"us ghere ka median ("+r.band+")":"poore channel ka median")+'</span></td>'+
  '<td><b style="color:'+(r.r>=1.5?"var(--ok)":r.r<0.8?"var(--bad)":"var(--tx)")+'">'+r.r.toFixed(2)+'×</b>'+dxDiv(r.r)+'</td>'+
  '<td>'+(r.extra>0?"+":r.extra<0?"−":"")+(Math.abs(r.extra)>=1000?fmt(Math.abs(r.extra)):Math.abs(r.extra))+'</td></tr>';
 const up=rows.slice().sort((a,b)=>b.r-a.r).slice(0,8),dn=rows.filter(r=>r.r<1).sort((a,b)=>a.r-b.r).slice(0,8);
 const tbl=(rs,lab,note)=>rs.length?'<div class="st"><div class="st-bar"><b>'+lab+'<small> — '+note+'</small></b>'+
  '<span class="sp"></span><span class="cnt">'+rs.length+
   ' lines · bar ka beech = apne ghere ke barabar (1.00x)</span></div>'+
  '<table class="stt"><thead><tr><th scope="col" class="l no">video</th><th scope="col" class="no">views/day</th><th scope="col" class="no">muqabla kis median se</th>'+
  '<th scope="col" class="no">median se</th><th scope="col" class="no">zyada/kam views</th></tr></thead><tbody>'+rs.map(row).join("")+'</tbody></table></div>':"";
 const fresh=rows.filter(r=>(r.it.days||0)<30).length;
 return '<div class="sec">Outliers — kaunsi video apne channel se kitna upar ya neeche hai '+
  '<small> — har video ko usi channel ki <b>usi umr ki</b> videos ke median views/day se napa gaya hai</small></div>'+
  '<div class="kpi">'+kpi("napni gayi videos",rows.length)+
  kpi("2x se upar",rows.filter(r=>r.r>=2).length,"var(--ok)")+
  kpi("1.25x se upar",rows.filter(r=>r.r>=1.25).length,"var(--ok)")+
  kpi("apne ghere ke barabar (0.8–1.25x)",rows.filter(r=>r.r>=0.8&&r.r<1.25).length,"var(--acc)")+
  kpi("aadhe se bhi kam",rows.filter(r=>r.r<0.5).length,"var(--bad)")+
  kpi("umr ke ghere jo bane",Object.keys(bandsN).length)+'</div>'+
  '<div class="two"><div><div class="sub">poori listing ka batwar — kitni videos kis hadd me hain</div>'+dist+'</div>'+
  '<div class="card"><div class="sub">Iska matlab kya hai, aur kya nahi</div>'+
  '<div class="sub">views/day is liye chuna ke purani aur nayi video ka farq khatam hota hai. "median se 2×" ka matlab ye '+
  'nahi ke algorithm ne ise push kiya — ho sakta hai topic, trending, ya playlist ka asar ho. Ye sirf ye batata hai ke '+
  '<b>apne hi channel me ye video apne normal se kitna hat kar hai</b>, aur kaunsi video ka pattern dobara use karna '+
  'chahiye ya uska tareeka chhod dena chahiye.</div>'+
  '<div class="sub">Umr ka ek jaal aur hai: 10 saal purani video ki views ruk chuki hoti hain, is liye wo aaj ke '+
  'median se hamesha haar jayegi. Is liye muqabla <b>pehle usi umr ke videos ke median se</b> hota hai: channel ki '+
  'listing umr ke char barabar hisson me banti hai (niche likhe ghere), aur jis hisse me 5 se kam videos niklein wahan '+
  'channel ka poora median lagta hai. Har row ke saamne likha hai kaunsa median lagaya gaya — ye koi model ya forecast '+
  'nahi, sirf apni hi listing ka batwar hai.</div>'+
  '<div class="sub" style="margin-top:6px">Umr ke ghere jo is channel ki listing se bane (din), aur har ghere me '+
  'kitni videos: '+
  (Object.keys(bandsN).length?Object.keys(bandsN).map(b=>esc(b)+' — '+bandsN[b]+' videos').join(" · "):
   'koi gher 5 videos pura nahi hua, is liye har jagah channel ka median laga hai')+'.</div>'+
  (fresh?'<div class="sub" style="margin-top:6px">in me se <b>'+fresh+'</b> videos 30 din se nayi hain — in ka views/day abhi '+
   'poora nahi betha, in par faisala mat karo.</div>':"")+
  (skip.length?'<div class="sub" style="margin-top:6px">ye channel bahar rahay (5 se kam videos): '+
   esc(skip.join(", ").slice(0,160))+'</div>':"")+
  '<div class="sub" style="margin-top:6px">Row par click = us video ka poora record.</div></div></div>'+
  tbl(up,"Sabse zyada upar","in ka tareeka dobara use karo")+tbl(dn,"Sabse zyada neeche","in ka tareeka chhodo")}
function dxKeys(items){
 const its=items.filter(it=>it.tags!==undefined);
 if(!its.length)return '<div class="sec">Keywords aur tags <small> — jo channel ne khud lagaya</small></div><div class="card">'+
  '<div class="sub">In videos ki metadata me tags nahi aa rahe. Tags ka poora data tab milta hai jab video ki apni '+
  'metadata padhi jaye — Table mode me har row khol kar ye dikhta hai.</div></div>';
 const tg={},hz={},tw={},zero=[],missed=[];
 const stop=" the a an of and in to for on with my is ka ki ke me se ek or how why what this that you your it its video new official part ft feat full hd live vlog top best vs and".split(" ");
 its.forEach(it=>{
  const tl=(it.title||"").toLowerCase(),seen={};
  (it.tags||[]).forEach(t=>{const k=String(t).trim().toLowerCase();if(!k||seen[k])return;seen[k]=1;
   const e=tg[k]=tg[k]||{n:0,in:0};e.n++;if(tl.indexOf(k)>=0)e.in++});
  if(!(it.tags||[]).length)zero.push(it);
  const d=(it.dprev||"")+" ";const re=/#([0-9A-Za-z_\u0900-\u097F]{2,30})/g;let m;
  while((m=re.exec(d)))hz[m[1].toLowerCase()]=(hz[m[1].toLowerCase()]||0)+1;
  (it.title||"").toLowerCase().replace(/[^0-9a-z\u0900-\u097F]+/g," ").split(" ").forEach(w=>{
   if(w.length<3||stop.indexOf(w)>=0)return;tw[w]=(tw[w]||0)+1})});
 const rank=o=>Object.keys(o).map(k=>({t:k,n:o[k]})).sort((a,b)=>b.n-a.n||(a.t<b.t?-1:1));
 const TT=rank(tg),KW=rank(tw),HZ=rank(hz);
 const never=TT.filter(x=>x.n>=3&&!x.in).slice(0,14);
 const medTags=dxMed(its.map(it=>(it.tags||[]).length));
 const noTitle=its.filter(it=>{const tl=(it.title||"").toLowerCase();
  return (it.tags||[]).length&&!((it.tags||[]).some(t=>tl.indexOf(String(t).trim().toLowerCase())>=0))}).length;
 const trow=x=>'<tr><td class="l">'+esc(x.t)+'</td><td>'+x.n+'</td><td>'+
  (x.in?'<b style="color:var(--ok)">'+x.in+'</b>':'<span style="color:var(--warn)">0</span>')+'</td></tr>';
 const krow=x=>'<tr><td class="l">'+esc(x.t)+'</td><td>'+x.n+'</td></tr>';
 const box=(title,note,inner)=>'<div class="st"><div class="st-bar"><b>'+title+'<small> — '+note+'</small></b>'+
  '<span class="sp"></span></div>'+inner+'</div>';
 const tbl=(rs,cols)=>'<table class="stt"><thead><tr>'+cols+'</tr></thead><tbody>'+
  rs.map(r=>r).join("")+'</tbody></table>';
 return '<div class="sec">Keywords aur tags — jo channel ne khud lagaya, aur jo us ne title me likha '+
  '<small> — asli tags aur asli titles se gina hua, koi generate kiya hua keyword nahi</small></div>'+
  '<div class="kpi">'+kpi("videos jin ki metadata padi",its.length)+kpi("kul alag tags",TT.length,"var(--acc)")+
  kpi("median tags per video",Math.round(medTags))+kpi("bina tag videos",zero.length,"var(--warn)")+
  kpi("jin me koi tag title me nahi",noTitle,"var(--bad)")+'</div>'+
  '<div class="two"><div>'+
  box("Sabse common tags","jitni videos me ye tag laga hai · title me kitni bar likha gaya",
   TT.length?tbl(TT.slice(0,18).map(trow),'<th scope="col" class="l no">tag</th><th scope="col" class="no">kitni videos me</th><th scope="col" class="no">title me</th>')
   :'<div class="sub">koi tag nahi mila.</div>')+
  box("Description ke shuru se hashtags","sirf pehle 260 akhar padhe gae hain — poora description row kholne par dikhta hai",
   HZ.length?tbl(HZ.slice(0,12).map(krow),'<th scope="col" class="l no">hashtag</th><th scope="col" class="no">kitni videos me</th>')
   :'<div class="sub">shuru ke 260 akhar me koi hashtag nahi mila.</div>')+
  '</div><div>'+
  box("Title me sabse common shabd","aapke apne titles se ginti — ye SEO ka score nahi, sirf ginti hai",
   KW.length?tbl(KW.slice(0,18).map(krow),'<th scope="col" class="l no">shabd</th><th scope="col" class="no">kitne titles me</th>')
   :'<div class="sub">koi shabd nahi bacha.</div>')+
  box("Chhuta hua keyword","tag laga hai magar title me kahin nahi likha — thumbnail par bhi ye dikhna chahiye",
   never.length?tbl(never.map(trow),'<th scope="col" class="l no">tag</th><th scope="col" class="no">kitni videos me</th><th scope="col" class="no">title me</th>')
   :'<div class="sub">jis tag ko 3 se zyada videos ne lagaya, wo sab title me bhi likha hai. Acha hai.</div>')+
  '</div></div>'+
  '<div class="sub" style="margin-top:10px">'+its.length+' videos me tags mile'+(zero.length?' · '+zero.length+' par ek bhi tag nahi':'')+
  ' · tags ki ginti usi video ki asli metadata se hai jo Table mode me har row ke liye padhi jati hai.</div>'}


// Engagement = har 1000 views par kitne LIKE, YouTube ke asli ginay se. Ye CTR ka
// mutamadil nahi hai: humare paas ye nahi ke kiton ne thumbnail dekh kar click kiya.
// Magar likes aur views dono zindagi bhar jama hote hain, is liye in ka nisbat umr
// se utna nahi badalta jitna khud views — yaani ye naap purani aur nayi videos ka
// imandar tulna kar sakta hai.
function dxQ(a,p){if(!a.length)return 0;const q=a.slice().sort((x,y)=>x-y);
 return q[Math.max(0,Math.min(q.length-1,Math.floor(q.length*p)))]}
function dxEng(items){
 const ok=items.filter(it=>((it.likes===0||it.likes)&&((it.views||0)>0)));
 if(ok.length<12)return "";
 const EN=it=>it.likes/Math.max(1,it.views)*1000;
 const vals=ok.map(EN),med=dxMed(vals),p25=dxQ(vals,0.25),p75=dxQ(vals,0.75);
 // Size ka asar nikaalne ke liye: listing ko views ke char barabar hisse, aur har
 // video ka engagement usi hisse ke median se nisbat (Outliers wala hi tareeqa).
 const vsz=ok.map(it=>it.views||0).sort((a,b)=>a-b);
 const qv=p=>vsz[Math.max(0,Math.min(vsz.length-1,Math.floor(vsz.length*p)))];
 const VB=[[-1,qv(0.25)],[qv(0.25)+1,qv(0.5)],[qv(0.5)+1,qv(0.75)],[qv(0.75)+1,1/0]];
 const VM=VB.map(b=>{const g=ok.filter(it=>{const v=it.views||0;return v>=b[0]&&v<=b[1]}).map(EN);
  return g.length>=8?dxMed(g):0});
 const REL=it=>{const v=it.views||0,bi=VB.findIndex(b=>v>=b[0]&&v<=b[1]);
  const m=(bi>=0&&VM[bi])?VM[bi]:med;return m?EN(it)/m:1};
 const FLOOR=5000,big=ok.filter(it=>(it.views||0)>=FLOOR).map(it=>({it:it,ix:items.indexOf(it),e:EN(it),g:REL(it)}))
  .sort((a,b)=>b.g-a.g);
 if(big.length<8)return "";
 const row=r=>'<tr onclick="zoom('+r.ix+')"><td class="l"><b>'+esc(String(r.it.title||"").slice(0,90))+'</b>'+
  '<div class="sub">'+esc((r.it.channel||"").slice(0,26))+' · '+(r.it.days||0)+' din · '+fmt(r.it.views||0)+' views'+
  ' · likes '+fmt(r.it.likes||0)+'</div></td><td class="num"><b>'+r.e.toFixed(1)+'</b></td>'+
  '<td class="num">'+(r.it.cmts?fmt(r.it.cmts):"—")+'</td>'+
  '<td class="num">'+r.g.toFixed(2)+'×'+dxDiv(r.g)+'</td></tr>';
 const HEAD='<th scope="col" class="l no">video</th><th scope="col" class="num">likes / 1000 views</th>'+
  '<th scope="col" class="num">comments</th><th scope="col" class="num">apni size ke ghere se</th>';
 const mk=(rs)=>'<table class="stt"><thead><tr>'+HEAD+'</tr></thead><tbody>'+rs.map(row).join("")+'</tbody></table>';
 // Apne data ki median se do hisse — koi man-girri had nahi banai gayi.
 const TR=[["thumbnail ki roshni (jitni badi utni ujli)",it=>(it.an&&typeof it.an.bright==="number")?it.an.bright:null],
  ["thumbnail ki bheed (edges %)",it=>(it.an&&typeof it.an.clutter==="number")?it.an.clutter:null],
  ["title me shabd",it=>(it.ts&&typeof it.ts.n==="number")?it.ts.n:null],
  ["description ki lambai (akhar)",it=>(typeof it.dlen==="number")?it.dlen:null],
  ["tags ki ginti",it=>(it.tags&&typeof it.tags.length==="number")?it.tags.length:null]];
 const TRW=TR.map(t=>{
  const pts=ok.map(it=>[t[1](it),REL(it)]).filter(p=>typeof p[0]==="number").sort((a,b)=>a[0]-b[0]);
  if(pts.length<12)return null;
  const cut=pts[Math.floor(pts.length/2)][0];
  // Agar ek hi value ka dher 25% se zyada hai to beech ka batwar man-girri hai.
  if(pts.filter(p=>p[0]===cut).length>pts.length*0.25)return null;
  const lo=pts.filter(p=>p[0]<cut).map(p=>p[1]),hi=pts.filter(p=>p[0]>=cut).map(p=>p[1]);
  if(lo.length<15||hi.length<15)return null;
  return {k:t[0],cut:cut,lo:dxMed(lo),hi:dxMed(hi),nl:lo.length,nh:hi.length,d:dxMed(hi)-dxMed(lo)};
 }).filter(Boolean);
 const trw=TRW.length?('<table class="stt"><thead><tr><th scope="col" class="l no">kya cheez</th>'+
  '<th scope="col" class="num">kam wali aadhi (x)</th><th scope="col" class="num">zyada wali aadhi (x)</th>'+
  '<th scope="col" class="num">phark</th><th scope="col" class="num">n</th></tr></thead><tbody>'+
  TRW.map(t=>'<tr><td class="l">'+esc(t.k)+'<div class="sub">batwan is number par: '+
   (Math.abs(t.cut)>=1000?fmt(Math.round(t.cut)):Math.round(t.cut*100)/100)+'</div></td>'+
   '<td class="num">'+t.lo.toFixed(2)+' <span class="sub">('+t.nl+')</span></td>'+
   '<td class="num">'+t.hi.toFixed(2)+' <span class="sub">('+t.nh+')</span></td>'+
   '<td class="num" style="color:var('+(t.d>0?'--ok':'--bad')+')">'+(t.d>0?"+":"")+(t.d*100).toFixed(0)+'%</td>'+
   '<td class="num">'+(t.nl+t.nh)+'</td></tr>').join("")+'</tbody></table>'):'<div class="sub">kafi data nahi.</div>';
 const nc=ok.filter(it=>it.cmts).length;
 return '<div class="sec">Engagement — har 1000 views par kitne likes '+
  '<small> — YouTube ke asli ginay se, koi andaza nahi</small></div>'+
  '<div class="kpi">'+kpi("videos jinke likes naap paye",ok.length)+
  kpi("median likes / 1000 views",med.toFixed(1),"var(--acc)")+
  kpi("p25 – p75 ka band",p25.toFixed(1)+" – "+p75.toFixed(1))+
  kpi("median se oopar",vals.filter(v=>v>med).length,"var(--ok)")+
  kpi("jin par comments bhi naap paye",nc,nc?"var(--ok)":"var(--warn)")+'</div>'+
  '<div class="st"><div class="st-bar"><b>Sabse zyada talqeen</b><span class="cnt">kam az kam '+
   fmt(FLOOR)+' views wali videos — apni size ke ghere ke median ke muqable · bar ka beech = us ghere ka median (1.00x)</span></div>'+mk(big.slice(0,8))+'</div>'+
   '<div class="st"><div class="st-bar"><b>Sabse kam talqeen</b><span class="cnt">wahi hadd, ulta taraf · bar ka beech = us ghere ka median (1.00x)</span></div>'+
  mk(big.slice(-8).reverse())+'</div>'+
  '<div class="st"><div class="st-bar"><b>Apne hi data ka batwar — kaunsi cheez talqeen ke saath saath aati hai</b>'+
  '<span class="cnt">do hisse channel ki apni median se; engagement usi size ki videos ke median se</span></div>'+trw+'</div>'+
  '<div class="card"><div class="sub">Iska matlab kya hai, aur kya nahi</div>'+
  '<div class="sub" style="margin-top:6px">Ye <b>CTR nahi hai</b> — CTR ka matlab hai kiton ne thumbnail dekh kar click kiya, '+
  'aur wo sirf aapke apne Studio me hota hai (neeche form se daal sakte ho). Ye naap uske baad ka hai: jis ne video dekhi '+
  'us ne kitni talqeen zahir ki. Likes aur views dono zindagi bhar jama hote hain, is liye ye nisbat umr se utna nahi '+
  'badalta jitna khud views badalta hai — is liye purani aur nayi videos ka tulna imandar hai.</div>'+
  '<div class="sub" style="margin-top:6px">'+(ok.length>big.length
  ?('Upar wali do list me <b>'+fmt(FLOOR)+' se kam views wali '+(ok.length-big.length)+' videos ko chhoda gaya</b> — 300 views par 15 likes ka matlab 50/1000 hota hai, jo shor hai signal nahi. ')
  :('Upar wali do list ke liye <b>'+fmt(FLOOR)+' se kam views wali koi video nikli hi nahi</b> — poori listing is hadd se upar hai, is liye koi bahar nahi hui. '))+
  'Batwar wali table <b>ham-raftari hai, wajah nahi</b>. Har video ka engagement <b>usi size ki videos ke median se</b> '+
  'napa gaya hai (listing ke views par char barabar hisse), taaki chhoti aur bari videos ka tulna seedha na hota rahe. '+
  'Phir bhi ye kehti hai ke jo thumbnails zyada ujle the un par likes zyada aaye — ye sabit nahi karti ke ujla thumbnail '+
  'banane se likes barh jayenge. Dislikes aur share ki ginti YouTube API se nahi aati, is liye wo shamil nahi.</div></div>'}

async function deepv(){const _t=RTN;if(!cur){noScan();return}spin();const d=await ensureData();if(_t!==RTN)return;if(!d){noScan();return}
 const G=d.deep||{};
 if(!G.buckets){$("#main").innerHTML='<h2>'+ico("bars",18)+' Deep Analysis</h2><div class="err">ye scan purani build ka hai — wahi topic dobara scan karo (OCR cache ki wajah se seconds lagenge).</div><div class="bar"><button class="go" onclick="newScan()">naya scan karo</button></div>';return}
 const pat=(G.pattern||[]).map(p=>'<div class="v"><b class="'+p.s+'">'+(p.s==="ok"?"✓":"✗")+'</b><div>'+esc(p.t)+'</div></div>').join("")||
  '<div class="sub">is set me koi pattern itna mazboot nahi nikla. 50 videos + wide search se n badhao, ya apne niche ka exact topic do (jaise "marathi vlog" ki jagah "tech review hindi").</div>';
 const grp={};(G.buckets||[]).forEach(r=>{(grp[r.k]=grp[r.k]||[]).push(r)});
 const gs=Object.keys(grp).map(k=>({k:k,rows:grp[k].sort((a,b)=>b.lift-a.lift)})).sort((a,b)=>(b.rows[0].lift||0)-(a.rows[0].lift||0));
 const tabs=gs.map(g=>{const tot=g.rows.reduce((s,r)=>s+r.n,0);
  return '<div class="st"><div class="st-bar"><b>'+esc(g.k)+'<small> — '+tot+' thumbnails me</small></b><span class="sp"></span></div><table class="stt"><thead><tr><th scope="col" class="l no">kaunsa tareeka</th><th scope="col" class="no">kitne</th><th scope="col" class="no">median views</th><th scope="col" class="no">views/day</th><th scope="col" class="l no">is set ke muqable</th></tr></thead><tbody>'+
   g.rows.map(r=>'<tr><td class="l">'+esc(r.b)+'</td><td>'+r.n+'</td><td>'+fmt(r.views)+'</td><td>'+fmt(r.vpd)+'</td><td class="l">'+liftBar(r.lift)+(r.n<4?' <span class="sub">(sample chhota — is par bharosa mat karo)</span>':"")+'</td></tr>').join("")+'</tbody></table></div>'}).join("");
 const br=(G.breaks||[]).map(b=>'<div class="card"><div class="bwrap" style="width:100%"><img class="thumb" src="'+imgu(b.thumb||"")+'">'+(b.vpd?'<span class="badge" style="color:var(--grn)">'+fmt(b.vpd)+'/day</span>':"")+'</div>'+
  '<div style="margin-top:7px;font-size:var(--fs-body)">'+esc(b.title)+'</div><div style="margin-top:6px">'+chip("views/day",fmt(b.vpd),"var(--grn)")+chip("umr",b.days+"d")+chip("text",b.words)+chip("bada text",b.maxh)+chip("chehre",b.faces)+chip("bright",b.bright)+'</div>'+
  '<div class="bar" style="margin-top:8px"><a class="sm" target="_blank" rel="noopener" href="'+b.url+'" style="text-decoration:none">youtube kholo</a></div></div>').join("");
 const bk=G.bench||{};
 const bt='<div class="st"><div class="st-bar"><b>Kaunsa naap kis had par</b><span class="sp"></span>'+
   '<span class="cnt">p10 se p90 tak · har line ka sample size saath me</span></div><table class="stt"><thead><tr><th scope="col" class="l no">naap</th><th scope="col" class="no">p10</th><th scope="col" class="no">p25</th><th scope="col" class="no">median</th><th scope="col" class="no">p75</th><th scope="col" class="no">p90</th><th scope="col" class="no">sample</th></tr></thead><tbody>'+
  Object.keys(BLAB).filter(k=>bk[k]).map(k=>'<tr><td class="l">'+BLAB[k]+'</td><td>'+bk[k].p10+'</td><td>'+bk[k].p25+'</td><td><b style="color:var(--acc)">'+bk[k].med+'</b></td><td>'+bk[k].p75+'</td><td>'+bk[k].p90+'</td><td>'+bk[k].n+'</td></tr>').join("")+'</tbody></table></div>';
 $("#main").innerHTML='<h2>'+ico("bars",18)+' Deep Analysis — '+esc(d.topic)+'</h2><div class="sub">'+d.items.length+' thumbnails · har pattern ko usi set ke <b>views/day</b> median se napa gaya hai (×1.0 = set ke barabar). '+
  'Ye ratio CTR ka sabse qareebi index hai: zyada impressions = zyada views, aur views/day purani/nayi video ka farq khatam karta hai.</div>'+
  '<div class="kpi">'+kpi("videos",d.items.length)+kpi("median views/day",fmt(G.vpd_med||0),"var(--acc)")+kpi("chehra wale",(bk._face_pct_of_all||0)+"%")+
  kpi("text wale",d.agg.with_text_pct+"%")+kpi("patterns nape",(G.buckets||[]).length)+'</div>'+
  '<div class="sec">Is topic me abhi kya chal raha hai <small> — 1.25× se upar = saaf jeet, 0.8× se neeche = nuqsan</small></div><div class="card">'+pat+'</div>'+
  (br?'<div class="sec">Jo apne aap toot-ta hai <small> — inka views/day set se 2.5× zyada hai; inhi ka pattern chhino</small></div><div class="grid">'+br+'</div>':"")+
  dxOut(d.items)+dxKeys(d.items)+dxEng(d.items)+
  '<div class="sec">Benchmark — itna karke aao <small> — "Meri Thumbnail" isi table me apni jagah dikhata hai</small></div>'+bt+
  '<div class="sec">Poora breakdown <small> — har cheez ke do-teen hisse, taaki pattern saaf dikhe</small></div>'+tabs+
  '<div class="sub" style="margin-top:14px">Sawal: kya ye sach me CTR hai? Nahi — ye observation hai, experiment nahi. Ye batata hai kaunsa tareeka inhi videos me zyada chala hai; pakka jawab sirf apne channel ke A/B se milta hai (A/B tab wahi ke liye hai).</div>'}

// ---------- behtar banao (regenerate) ----------
async function regen(ref,label,words,title){
 spin();let d;try{d=await jp("/api/regen",{ref:ref,words:words||"",title:title||""})}catch(e){$("#main").innerHTML='<div class="err">✗ '+esc(e.message)+'</div>';return}
 if(d.error){$("#main").innerHTML='<div class="err">✗ '+esc(d.error)+'</div>';return}
 for(let i=0;i<200;i++){await new Promise(r=>setTimeout(r,900));const p=await j("/api/progress?id="+d.job);
  if(p.state==="done"){RG=p.result;if(!RG||!(RG.variants||[]).length){$("#main").innerHTML='<div class="err">result nahi aaya — dobara dabao</div>';return}renderRegen(label);return}
  if(p.state==="error"){$("#main").innerHTML='<div class="err">✗ '+esc(p.error)+'</div>';return}
  const pc=p.total?Math.round(p.done*100/p.total):0;
  $("#main").innerHTML='<h2>'+ico("refresh",18)+' Behtar banao</h2><div class="sub">'+esc(label||"")+'</div><div class="sub">'+esc(p.current||"…")+' — '+p.done+'/'+p.total+
   ' · har version ko wapas OCR + analysis se napa jata hai</div><div class="pbar"><i style="width:'+pc+'%"></i></div>'}
 $("#main").innerHTML='<div class="err">bahut lamba laga — model badal kar dobara dabao. (Kaam server par chalta raha ho to page kholne par History me aa jaayega.)</div>'}
function renderRegen(label){const R=RG,b=R.before,B=(D&&D.deep&&D.deep.bench)||{};
 const vs=R.variants.map((v,i)=>{const df=v.score-b;
  return '<div class="card"><h3>'+esc(v.name)+' — <span style="color:'+cc(v.score)+'">'+v.score+'/100</span> '+
   (v.gem?'<span class="sub">(Gemini model: '+esc(v.gem)+')</span> ':"")+
   (df>0?'<span class="hi">+'+df+'</span>':df<0?'<span class="lo">'+df+'</span>':'<span class="sub">barabar</span>')+'</h3>'+
   '<div class="sub">'+esc(v.why)+'</div>'+
   '<div class="rvs"><div class="rvimg"><div class="lab">desktop browse 320px</div><img src="'+imgu(v.path)+'" style="width:320px;max-width:100%"></div>'+
   '<div class="rvimg"><div class="lab">mobile feed 210px</div><img src="'+imgu(v.path)+'" style="width:210px"></div>'+
   '<div class="rvimg"><div class="lab">asli size</div><img src="'+imgu(v.path)+'" style="width:560px;max-width:100%"></div></div>'+
   '<div style="margin-top:8px">'+chipsOf(v)+'</div>'+
   '<div class="bar" style="margin:10px 0 0"><button class="sm" onclick="useV('+i+')">iska poora analysis dekho</button>'+
   '<button class="sm" onclick="saveV('+i+')">'+ico("ab",14)+'A/B me save karo</button></div></div>'}).join("");
 $("#main").innerHTML='<h2>'+ico("refresh",18)+' Behtar banao</h2><div class="sub">'+esc(label||R.path)+'</div>'+
  '<div class="two"><div><div class="sub">abhi wali (score <b class="'+scC(b)+'">'+b+'/100</b>)</div>'+
   '<div class="bwrap"><img src="'+imgu(R.path)+'" style="width:100%;border-radius:var(--r2)"></div><div style="margin-top:8px">'+chipsOf({ts:R.ts,an:R.an,faces:R.faces,dup:null})+'</div></div>'+
  '<div><div class="sec">Kya badla</div><div class="card"><div class="sub">Tool ne wohi photo rakhi — sirf text hataakar/naya likhkar, rang/contrast/sharpen sudhaar kar, aur (subject chhota ho to) use bara karke — jitne tareeka is photo par laagu hue utne versions banaye. Har version ko <b>utne hi metrics se napa gaya</b> jitni original se: 320px par text, contrast, outline, chehra, blur, composition. Jo sabse upar hai wahi zyada chalne wala hai (CTR ka index, pakka sirf A/B se).</div>'+
  (R.gem?'<div class="sub" style="margin-top:6px">Gemini key set thi — isliye wohi photo ke do version <b>Gemini ke image model se bhi banwaye</b> (scene model se edit, shabd aur naap tool ki apni engine se). Wo bhi isi list me ek hi paimana par score hokar upar-neeche ho sakte hain.</div>':"")+
  (R.suggest?'<div class="sub" style="margin-top:6px">OCR ne purana text padha: <b>'+esc((R.old||[]).join(" "))+'</b> · tool ka sujhao: <b style="color:var(--acc)">'+esc(R.suggest)+'</b></div>':"")+
  '<div class="bar" style="margin-top:10px"><input type="text" id="rw" placeholder="khud likho: 2–4 shabd (khaali chhodo to apne aap chun lega)" value="'+esc(R.used||"")+'" style="min-width:320px">'+
  '<button class="sm" onclick=\'regen(RG.path,"dobara",$("#rw").value,RG.title||"")\'>'+ico("refresh",14)+'dobara banao</button></div></div>'+
  '<div class="sec">Local AI generation ka haal</div><div class="card">'+genbox((R.gen||{}))+'</div></div></div>'+
  '<div class="sec">'+R.variants.length+' behtar versions <small> — sabse upar wala sabse mazboot'+(R.gem?' · jinka naam "Gemini:" se shuru hota hai wo Gemini image model se banaye gaye hain, magar unka score bhi isi tool ke apne paimana se hai — isliye wo bhi upar aa sakte hain, neeche bhi':"")+'</small></div>'+vs+
  (R.gem_err?'<div class="err" style="margin-top:10px">Gemini rasta: '+esc(R.gem_err)+'</div>':"")+
  '<div class="bar" style="margin-top:14px"><button class="sm" onclick="cmp()">'+ico("back",14)+'competitors</button><button class="sm" onclick="deepv()">'+ico("bars",14)+'deep analysis</button>'+
  '<button class="sm" onclick="newScan()">'+ico("plus",14)+'naya topic</button></div>'}
function useV(i){PEND=RG.variants[i].path;go("mine")}
async function saveV(i){const v=RG.variants[i];ABTH=v.path;
 await jp("/api/variant",{topic:TOPIC,ta:TITLE||RG.title||"",ia:v.path,note:"behtar banaya ("+v.name+"): score "+RG.before+"→"+v.score});
 toast("A/B me save ho gaya — title Title Lab me likh kar dobara save karna")}
function genbox(g){const R=g.runware||{},ms=R.models||[];const lo=ms.length?Math.min.apply(null,ms.map(m=>m.usd)):0.0006;
 const hi=ms.length?Math.max.apply(null,ms.map(m=>m.hi||m.usd)):0.0012;
 return '<div class="sub">Thumbnail banane ke do raaste hain: <b>Tier A — Behtar banao</b> (wohi photo, deterministic recompose: 4-5 second, koi kharcha nahi, result 100% control me) aur <b>Tier B — AI Thumbnail</b> (Runware se nayi tasveer): '+(R.key?'<b class="hi">key set hai ('+esc(R.hint||"")+')</b>, sabse sasta model $'+lo+(hi>lo+1e-9?'–'+hi:'')+'/image':'<b class="lo">key set nahi</b> — tab tak AI band hai, Behtar banao chalta rahega')+'.</div>'+
  '<div class="sub" style="margin-top:6px">Is machine par: GPU <b>'+esc(g.gpu||"nvidia-smi nahi mila")+'</b> · ComfyUI (127.0.0.1:8188): '+(g.comfy?"chal raha hai":"nahi")+' · <code>models\\</code> folder: '+((g.models||[]).length)+' file. Local SD abhi <i>optional</i> hai — Runware test me sasta aur bharosemand nikla, isliye wohi default rasta hai.</div>'+
  '<div class="bar" style="margin-top:8px"><button class="sm" onclick="go(\'ai\')">'+ico("palette",14)+'AI Thumbnail kholo</button><button class="sm" onclick="genpg()">'+ico("spark",14)+'ye plan kaise chuna</button></div>'}
async function genpg(){const _t=RTN;let I={};try{I=(await j("/api/ai")).info||{}}catch(e){}
 if(_t!==RTN)return;
 const ms=(I.models||[]).map(m=>'<tr><td class="l"><b>'+esc(m.name)+'</b><br><span class="sub">'+esc(m.id)+'</span></td><td>$'+m.usd+(m.hi&&m.hi>m.usd?'<br><span class="sub">max $'+m.hi+'</span>':'')+'</td><td class="l">'+esc(m.note)+'</td></tr>').join("");
 $("#main").innerHTML='<h2>'+ico("spark",18)+' Thumbnail Generation — kaunsa rasta, kyun</h2>'+
  '<div class="sub">Aapne kaha: <i>model acha aur sasta, text bhi handle kare, minimum kharcha</i>. Isliye Runware ke 6 models <b>asli test</b> kiye — 1024×576 par, cost Runware ke apni deni se (<code>includeCost:true</code>), aur "text sahi likha ya nahi" ClickLab ki <b>apni naapi</b> se (OCR + 320px par padhna + score). Andaze par nahi, naape par faisala hua.</div>'+
  '<div class="card" ><h3>24 Oct ko naape gaye natije (1024×576, ek hi prompt)</h3>'+
  '<table><tr><th scope="col">model</th><th scope="col" class="num">ek image</th><th scope="col">asli test me kya hua</th></tr>'+
  '<tr><td><b>runware:z-image@turbo</b> <span class="hi">← default</span></td><td class="num">$0.0006<br><span class="sub">4-task batch me ek task $0.0012 gaya tha</span></td><td>1.3–2 second, OCR ne "GRAVITY" sahi padha, 320px par text nazar aaya, score <b>98</b>. Sabse sasta, sabse tez, text bhi saaf.</td></tr>'+
  '<tr><td>bfl:flux@3-image-klein</td><td class="num">$0.0025</td><td>asli photo jaisa look, par text bigaad diya ("GRAVI"). 4x mehnga.</td></tr>'+
  '<tr><td>prunaai:1@1</td><td class="num">$0.0044</td><td>text sahi, score 94 — par 7x mehnga. Tab chuno jab scene ka detail chahiye.</td></tr>'+
  '<tr><td>prunaai:p-image@ideogram</td><td class="num">$0.0113</td><td>9 second aur text ka kachra — score 32. Reject.</td></tr>'+
  '<tr><td>google:nano-banana@2-lite</td><td class="num">$0.0336</td><td>16:9 size hi support nahi karta (fixed list hai, usme 16:9 nahi). Reject.</td></tr>'+
  '<tr><td>bytedance:seedream@5.0-pro</td><td class="num">$0.048</td><td>1.5K size par. Is kaam ke liye zaroorat se zyada mehnga.</td></tr></table>'+
  '<div class="sub" style="margin-top:8px">Ye list tool ke andar bhi hai (neeche), taaki model badalne par asli per-image price dikhe.</div></div>'+
  '<div class="card" ><h3>Kharcha ka hisaab (minimum rakhne ke 3 tareeke)</h3>'+
  '<table><tr><th scope="col">tareeka</th><th scope="col">faida</th></tr>'+
  '<tr><td><b>jitna size chahiye utna maango — tool ab tasveer sikodta nahi</b></td><td>Teeno size Runware par maujood hain aur teeno ka daam 24 Oct ko <b>asli</b> naapa: <b>1024×576 = $0.0006</b>, <b>1536×864 = $0.0025</b>, <b>2048×1152 = $0.0032</b>. Purana version hamesha 1024 par banata tha phir Pillow se badhata tha (1280×720 seedha maangne par $0.0013 lagti thi) — ab size aap chunte ho aur tasveer usi size par save hoti hai. Benchmark har size par sasta hi hai (naapa: 0.14s at 1280, 0.18s at 1536, 0.29s at 2048). Zyada kaam ke liye <b>2048 kaafi</b> hai — YouTube browse/player apni taraf se 1280×720 tak hi rakhta hai, usse upar ka fayda zoom/print tak mehdood hai.</td></tr>'+
  '<tr><td><b>4K chahiye to wo alag kaam hai, generation nahi</b></td><td>In models ki apni hadd <b>2048 px</b> hai. Uske upar <b>upscale</b> se jaana padta hai — naapa hua <b>3842×2180, $0.010, 13 second</b> (<code>prunaai:p-image@upscale</code>, target 8 megapixel). Ek <b>muft</b> rasta bhi hai: Pillow Lanczos + sharpen — paisa zero, par usme nayi detail paida nahi hoti, sirf tasveer badi hoti hai. AI tab me har card par dono buttons hain aur daam saaf likha hai.</td></tr>'+
   '<tr><td><b>steps set nahi karte</b></td><td>steps badhane se cost badhti hai; default hi behtar nikla.</td></tr>'+
  '<tr><td><b>ek click me 4 soch</b></td><td>1024×576 par kul <b>$0.0024–0.0048</b> (24 Oct ki asli batch ka kul $0.0030) — yaani <b>1000 thumbnails ≈ $0.60–1.20</b>. Yahi kaam 2048×1152 par ~$2.60 padega. Ek video ke liye 4 try karna = aadha paisa.</td></tr></table>'+
  '<div class="sub" style="margin-top:8px">Har generation ke baad <b>asli cost</b> AI tab me dikhti hai — Runware ka apna hisaab, mera andaaza nahi.</div></div>'+
  '<div class="card" ><h3>Text ka rule — ye sabse zaroori faisala hai</h3>'+
  '<div class="sub">24 Oct ko aankh se dekha: ye model jo shabd maange jaayein wo aksar poori sahi spelling me likh deta hai ("IT IS HERE", "MYSTERY OF BLACK HOLES") — magar kabhi-kabhi misspell bhi kar deta hai ("MYSTERY"→"KLYSTERY", "THEY LAUGHED"→"THEY LAUGEDED"), aur local OCR se ye faaisla pakka taur par nahi hota (wo "BLACK" ko "BLA"+"CK" tod deta hai). Isliye default: <b>scene AI se, shabd Pillow se.</b> Wohi text engine jo Behtar banao use karta hai — khaali jagah dhoondta hai, outline lagata hai, aur 320px par padha jaane wala size chunta hai. Natije me spelling 100% sahi aur contrast pakka.</div>'+
  '<div class="sub" style="margin-top:6px">"text bhi AI se" ka checkbox majood hai (maine benchmark ke liye rakha hai, chupane ke liye nahi): AI se poora poster banwao, phir <b>score khud bata dega</b> ke wo behtar tha ya nahi. Abhi tak z-image hi wohi model hai jisne text khud bhi sahi likha.</div></div>'+
  '<div class="card" ><h3>Reference (i2i) ka sach</h3>'+
  '<div class="sub">24 Oct ko <b>naapa gaya</b> — ek hi prompt, ek hi model, sirf reference ka tareeka badla. Farak usi 0-100 scale par jo har AI card par dikhta hai: <b>koi reference nahi = 13</b> · <code>imageUrls</code> bheja = <b>16</b> · <code>seedImage</code> + strength 0.30 = <b>1</b> · <b>0.55 = 3 (default — inspired, naya)</b> · 0.85 = <b>9</b>. Matlab <b><code>imageUrls</code> is model par koi asar nahi karta</b> — purana version usi par chalta tha, isliye wahan ka "reference" asli me theatre tha. Ab <code>seedImage</code> bheja jaata hai, aur AI tab ka slider usi <b>strength</b> ka hai. Teeno calls ka daam same tha: <b>$0.0006</b> — reference muft hai, farak sirf strength ka.</div>'+
   '<div class="sub" style="margin-top:6px">Default 0.55 par reference ka sirf rang-roop mehsoos hota hai — scene, layout aur chehre naye bante hain, isliye copyright ka khatra kam rehta hai. Phir bhi har card par <b>apna asli naapa hua farak</b> dikhta hai taaki aap khud dekh lo (≤2 = remix, ≤8 = inspired, ≤15 = kaafi naya, usse zyada = bilkul naya). Text AI se kabhi nahi badalta — shabd badalne ka kaam Behtar banao karta hai, muft aur pakke.</div></div>'+
  '<div class="card" ><h3>Model chuno (asli price ke saath)</h3>'+
   (ms?'<table class="stt"><thead><tr><th scope="col" class="l no">model</th><th scope="col" class="no">ek image</th><th scope="col" class="l no">kab chuno</th></tr></thead><tbody>'+ms+'</tbody></table>':'<div class="sub">model list nahi mil payi.</div>')+
   '<div class="bar" style="margin-top:8px"><button class="go" onclick="go(\'ai\')">'+ico("palette",14)+'AI Thumbnail kholo</button></div></div>'+
  '<div class="card" ><h3>Local SD ka rasta abhi bhi khula hai</h3>'+
  '<div class="sub">Aapke paas <b>RTX 5070 Ti (16 GB)</b> + 64 GB RAM hai — SDXL/FLUX level ke liye kaafi. ComfyUI 127.0.0.1:8188 par chale ya <code>ClickLab\\models\\</code> me .gguf rakh do, tool pehchan leta hai (upar check: <b>'+(TOOLS.gen&&TOOLS.gen.comfy?"mil gaya":"nahi mila")+'</b>). Par filhaal wohi rasta mehnga padta hai: apni bijli, apna waqt, aur 6–7 GB model — jabki yahan ek image $0.0006 me 2 second me aa jaati hai. Local SD tab jodega jab offline kaam karna ho ya ek hi scene ke sau variations chahiye hon.</div></div>'+
  '<div class="sub" style="margin-top:12px">Aur wohi purani baat: generation se thumbnail ban jaata hai, jeetta nahi. Jeetne wala wahi hai jo <b>aapke topic ke benchmark</b> me upar aata hai — isliye har AI soch wahi se napi jaati hai jo har competitor se napi jaati hai.</div>'}

// ---------- AI thumbnail (Runware) ----------
function aiAt(i){const it=D.items[i];AQ.idea=(it.title||"").slice(0,200);AQ.ref=it.thumb||"";AIRES=null;go("ai")}
function aiMine(){if(!MINE)return toast("pehle thumbnail check karo");AQ.ref=MINE.path;AIRES=null;go("ai")}
function aiGet(){AQ.idea=($("#aiq")||{}).value||AQ.idea;AQ.words=($("#aiw")||{}).value||AQ.words;
 AQ.ref=($("#air")||{}).value||AQ.ref;AQ.mk=($("#aim")||{}).value||AQ.mk;
 AQ.res=($("#airz")||{}).value||AQ.res||"sd";AQ.eng=($("#aieng")||{}).value||AQ.eng||"rw";
 AQ.meth=($("#aimeth")||{}).value||AQ.meth||"auto";
 if($("#aistr"))AQ.str=Number($("#aistr").value)}
function strLbl(){const s=$("#aistr"),e=$("#strv");if(s&&e)e.textContent=s.value}
function aiCost(){const s=$("#aim");if(!s)return;const sh=AIINFO.shots||4;
 const eng=($("#aieng")||{}).value||"rw";
 if(eng==="poll"){const e=$("#aicost");if(e)e.innerHTML="Chuna hua: <b>Pollinations</b> — koi key nahi. Sach: 27 Oct 2026 ko isne <b>402/502/503 wapas kar dena shuru kiya</b> (unka free tier badal gaya) — zyada tar requests fail hongi. Reference/strength yun bhi chalta hi nahi, quality Runware se kam hai. Pakki kaam chahiye to Runware chuno ($0.0006/image).";const b=$("#aigo");if(b)b.innerHTML=ico("palette",14)+" "+sh+" alag dhange banao — muft (ab aksar fail)";return}
 if(eng==="agy"){const e=$("#aicost");if(e)e.innerHTML="Chuna hua: <b>Antigravity — Nano Banana 2 (aapki Google AI subscription)</b> — koi API key nahi chahiye; ye rasta usi Google account ki login se chalta hai jo aapne <code>agy</code> me ki. Sach: tasveer ~1 minute me banti hai aur quota kaam (tokens) se gini jaati hai — Pro plan par quota har 5 ghante refresh hoti hai par weekly limit bhi hai; bade batch ke liye Runware tez hai. Reference/strength aur 4K is raste par nahi chalta. Isliye ye tab best hai jab keys ki free-limit khatam ho aur 1-2 tasveeren foran chahiye.";const b=$("#aigo");if(b)b.innerHTML=ico("palette",14)+" "+sh+" alag dhange banao — subscription (~1 min each)";return}
 if(eng==="gem"){const e=$("#aicost");if(e)e.innerHTML="Chuna hua: <b>Gemini "+esc((AIINFO.gemimg||"").replace("gemini-",""))+" (free tier)</b> — apni key par, daily limit ke andar kharcha zero. Sach: size bilkul pixel-perfect nahi, model qareebi aspect deta hai; reference/strength yahan nahi chalta; limit khatam hone par pool ki agli key aur phir agli model ka quota apne aap azmaata hoon; sab khatam ho to saaf error dikhega. Key nahi set — pehle neeche Gemini key box me daalo."+(AIINFO.gem?"":' <span class="lo">(abhi key set nahi)</span>');const b=$("#aigo");if(b)b.innerHTML=ico("palette",14)+" "+sh+" alag dhange banao — free tier";return}
 const ms=AIINFO.models||[];
 const m=ms.filter(x=>x.k===s.value)[0]||{};
 const rz=(AIINFO.res||[]).filter(x=>x.k===((($("#airz")||{}).value)||AIINFO.defres||"sd"))[0]||{};
 const def=(s.value===(AIINFO.def||"z"));
 const pu=def?(rz.usd||m.usd||0):(m.usd||0),ph=def?Math.max(rz.hi||rz.usd||0,m.hi||0):(m.hi||m.usd||0);
 const lo=pu*sh,hi=ph*sh,rg=hi>lo+1e-9;
 const e=$("#aicost");if(e)e.innerHTML="Chuna hua: <b>"+esc(m.name||"")+"</b> · size <b>"+(rz.w||1024)+"×"+(rz.h||576)+"</b> — "+(rg?"$"+pu+"–"+ph:"$"+pu)+"/image, "+sh+" soch ka kul <b>$"+lo.toFixed(4)+(rg?"–$"+hi.toFixed(4):"")+"</b> (1000 thumbnails ≈ $"+(pu*1000).toFixed(2)+(rg?"–"+(ph*1000).toFixed(2):"")+")"+(def?"":" <span class='sub'>(size ka daam default model par naapa gaya hai; is model par bada size mehnga pad sakta hai)</span>");
 const b=$("#aigo");if(b)b.innerHTML=ico("palette",14)+" "+sh+" alag dhange banao — ~$"+lo.toFixed(4)+(rg?"–"+hi.toFixed(4):"")}
async function aiKey(del){aiGet();const k=del?"":((($("#aik")||{}).value)||"").trim();
 if(!del&&!k)return toast("pehle key likho");
 try{const r=await jp("/api/aikey",{key:k});await aipg();toast(r.set?("key save ho gayi — "+r.hint):"key hata di")}catch(e){failToast(e,"API key save karna")}}
async function gemKey(del){const k=del?"":((($("#gk")||{}).value)||"").trim();if(!del&&!k)return toast("pehle key likho");
 try{const r=await jp("/api/gemkey",{key:k,add:!del});await boot();await aipg();toast(r.set?(r.n>1?("Gemini key pool me "+r.n+" keys ho gayi — ek ki limit khatam ho to agli apne aap lagegi"):("Gemini key set ho gayi — "+r.hint)):("poora key pool hata diya"))}catch(e){failToast(e,"Gemini key save karna")}}
async function ogmSet(on){try{const r=await jp("/api/ocrmode",{on:!!on});toast(r.on?("Gemini OCR chalu — ab text vision model padhega (behtar padhai, machine par kuch nahi chalta; key ki quota lagegi)"):("Gemini OCR band — text local engine padhega (muft, bina quota)"))}catch(e){failToast(e,"OCR setting save karna")}}
async function gemLook(){if(!MINE)return toast("pehle thumbnail check karo");const o=$("#gemblk"),b=$("#gemgo");if(b)b.disabled=true;if(o)o.innerHTML='<div class="sub">Gemini dekh raha hai… 5–20 second lagte hain</div>';
 let d;try{d=await jp("/api/gemlook",{ref:MINE.path,title:TITLE||""})}catch(e){if(o)o.innerHTML='<div class="err">✗ '+esc(e.message)+'</div>';if(b)b.disabled=false;return}
 if(b)b.disabled=false;
 if(d.error){if(o)o.innerHTML='<div class="err">✗ '+esc(d.error)+'</div>';return}
 if(o)o.innerHTML='<div class="sec">Model ka andaza — Gemini <small> — ye naap nahi, ek vision model ki raye hai; asli numbers upar hi hain</small></div><div class="card">'+esc(d.text||"").replace(/\n/g,"<br>")+'<div class="sub" style="margin-top:6px">model: '+esc(d.model||"")+' · har baar thoda alag jawab de sakta hai — ye model hai, paimana nahi</div></div>';}
// ---------- Gemini gehri analysis — har video par: har pehlu ki jaanch, aur us se behtar title/topic ----------
// Factor scores 0-10 model khud deta hai; rang hamare hi color-scale (cc) se taaki baaki
// UI se mile. Model JSON me jawab na de to uska jawab jaisa aaya waisa dikha jaayega —
// chhupaya nahi jaata. Label har card par saaf: ye model ki gehri raye hai, naap nahi.
let GDEEPJ=null;
const GDPFN={first_glance:"Pehli nazar (0.3 second)",face_emotion:"Chehra/jazbaat",text_210px:"Text 210px par",color_contrast:"Rang/contrast",composition:"Bant-khabar (composition)",curiosity_gap:"Tajassus (curiosity gap)",title_match:"Title se milan"};
async function gdpAt(i,el){const id=el||("gdp"+i);const e=document.getElementById(id);if(!e)return;
 const it=(D&&D.items||[])[i]||{};if(!it.thumb)return toast("is video ka thumbnail nahi mila");
 e.innerHTML='<div class="sub">Gemini poora thumbnail barikey se dekh raha hai — 15–40 second lagte hain…</div>';
 let d;try{d=await jp("/api/gemdeep",{ref:it.thumb,title:it.title||""})}catch(err){e.innerHTML='<div class="err">✗ '+esc(err.message)+'</div>';return}
 if(d.error){e.innerHTML='<div class="err">✗ '+esc(d.error)+'</div>';return}
 e.innerHTML=gdpCard(d)}
async function gdpMine(){if(!MINE)return toast("pehle thumbnail check karo");const o=$("#gemblk"),b=$("#gdpgo");if(b)b.disabled=true;
 if(o)o.innerHTML='<div class="sub">Gemini gehri analysis kar raha hai — 15–40 second lagte hain…</div>';
 let d;try{d=await jp("/api/gemdeep",{ref:MINE.path,title:TITLE||""})}catch(err){if(b)b.disabled=false;if(o)o.innerHTML='<div class="err">✗ '+esc(err.message)+'</div>';return}
 if(b)b.disabled=false;
 if(d.error){if(o)o.innerHTML='<div class="err">✗ '+esc(d.error)+'</div>';return}
 if(o)o.innerHTML=gdpCard(d)}
function gdpCopy(k){cpText(((((GDEEPJ||{}).deep||{}).titles||[])[k]||{}).t||"")}
function gdpCard(d){GDEEPJ=d;const J=d.deep||null;
 const hdr='<div class="sec">Gemini Gehri Analysis <small> — poori jaanch, magar model ki raye hai, is tool ka naap nahi; CTR ka pakka faisala A/B test se hota hai</small></div>';
 if(!J)return hdr+'<div class="card">'+esc(d.raw||"khaali jawab").replace(/\n/g,"<br>")+'<div class="sub" style="margin-top:6px">model: '+esc(d.model||"")+' · model ne JSON me jawab nahi diya — jawab jaisa aaya waisa dikha raha hoon</div></div>';
 const F=(J.factors||[]).map(f=>{const s=Math.max(0,Math.min(10,Math.round(Number(f.s)||0)));
  return '<div style="margin:10px 0"><b>'+esc(GDPFN[f.k]||f.k||"")+'</b> <span style="color:'+cc(s*10)+'"><b>'+s+'/10</b></span>'+
   '<div class="pbar" style="margin:4px 0"><i style="width:'+(s*10)+'%"></i></div>'+
   '<div class="sub">'+esc(f.why||"")+'</div><div class="sub">ilaaj: <b>'+esc(f.fix||"")+'</b></div></div>'}).join("");
 const st=(J.strengths||[]).map(x=>'<div>✓ '+esc(x)+'</div>').join("");
 const kl=(J.killers||[]).map(x=>'<div>✗ '+esc(x)+'</div>').join("");
 const TS=(J.titles||[]).map((t,k)=>'<div style="margin:8px 0"><div class="bar" style="margin:0"><div style="flex:1"><b>'+esc(t.t||"")+'</b></div><button class="sm" onclick="gdpCopy('+k+')">copy</button></div><div class="sub">'+esc(t.why||"")+'</div></div>').join("");
 const TP=(J.topics||[]).map(t=>'<div style="margin:8px 0"><b>'+esc(t.t||"")+'</b><div class="sub">'+esc(t.angle||"")+'</div></div>').join("");
 return hdr+'<div class="card"><div class="sub">model: '+esc(d.model||"")+' · har baar thoda alag jawab de sakta hai — ye model hai, paimana nahi</div>'+
  (J.verdict?'<div class="lbl">Faisla</div><div>'+esc(J.verdict)+'</div>':"")+
  (F?'<div class="lbl">Har pehlu ki gehri jaanch</div>'+F:"")+
  (st?'<div class="lbl">Jo abhi acha kaam kar raha hai</div>'+st:"")+
  (kl?'<div class="lbl">Jo clicks maar raha hai (zyada nuqsan wala pehle)</div>'+kl:"")+
  (TS?'<div class="lbl">Isi video ke liye behtar title — jo is se zyada chale</div>'+TS:"")+
  (TP?'<div class="lbl">Is se behtar ho sakte hain ye qareebi topics</div>'+TP:"")+
  '</div>'}
async function aiClear(){if(!confirm("AI se bani sari tasveerein aur history hatao?"))return;
 await jp("/api/aiclear",{});AIRES=null;await aipg();toast("hata diya")}
function useAI(i){PEND=AIRES.items[i].path;go("mine")}
function drefNote(v){const p=(v.dref||{}).px,c=(v.dref||{}).col;if(p==null||c==null)return "";
 const w=p<=2?"reference ke barabar — ye uska remix hai, copyright ka khatra sabse zyada":
  p<=8?"inspired, naya — scene aur banawas alag hain (default strength ka natija)":
  p<=15?"kaafi naya — reference ka sirf rang-roop mehsoos hota hai":"bilkul naya — reference ka koi asar nahi dikhta";
 return '<div class="sub">Reference se <b>naapa gaya</b> farak: banawas <b>'+p+'/100</b> · rang-roop <b>'+c+'/100</b>. '+w+'. Copyright ka aakhri faisla aapka — tool sirf farak naapta hai, faisla nahi karta.</div>'}
async function up4kV(i,mode){const el=$("#u4v"+i);if(!el||!AIRES||!AIRES.items[i])return;
 el.innerHTML='<div class="sub">'+(mode==="ai"?"Runware ka upscale chal raha hai (~13 second, ~$0.010)…":"4K ban raha hai (Pillow Lanczos — muft, 2-3 second)…")+'</div>';
 try{const d=await jp("/api/upscale",{path:AIRES.items[i].path,mode:mode});
  if(d.error){el.innerHTML='<div class="err">'+esc(d.error)+'</div>';return}
  el.innerHTML='<div class="sec">4K master — '+(mode==="ai"?"AI upscale (asli detail paida hoti hai)":"Pillow Lanczos (muft; sirf badi hoti hai, nayi detail nahi)")+'</div>'+
   '<div class="sub">'+d.w+'×'+d.h+' · sharpness '+d.sharp+' · '+(d.usd?'kharcha <b>$'+Number(d.usd).toFixed(4)+'</b> · model '+esc(d.model||""):'koi kharcha nahi')+' · <code>'+esc(d.path)+'</code></div>'+
   '<img src="'+imgu(d.path)+'" style="width:100%;max-width:900px;border-radius:var(--r2)">'+
   '<div class="bar"><a class="sm" href="'+imgu(d.path)+'" download>download</a>'+(mode==="ai"?"":'<button class="sm" onclick="up4kV('+i+',&quot;ai&quot;)">'+ico("up",14)+'AI wala rasta (~$0.010)</button>')+'</div>'}
 catch(e){el.innerHTML='<div class="err">'+esc(e.message)+'</div>'}}
function useH(i){PEND=(AIH[i]||{}).path||"";go("mine")}
async function saveAI(i){const v=AIRES.items[i];ABTH=v.path;
 await jp("/api/variant",{topic:TOPIC,ta:TITLE||"",ia:v.path,note:"AI se banaya ("+(v.model||"")+" / "+v.name+"): score "+v.score});
 toast("A/B me save ho gaya — Title Lab me title likh kar dobara save karna")}
async function aipg(){const _t=RTN;spin();if(cur)ensureData().catch(()=>{});let d={items:[],info:{}};try{d=await j("/api/ai")}catch(e){}
 if(_t!==RTN)return;
 AIH=d.items||[];AIINFO=d.info||{};const I=AIINFO,mk=AQ.mk||I.def||"z",sh=I.shots||4;
 const ms=(I.models||[]).map(m=>'<option value="'+m.k+'"'+(m.k===mk?" selected":"")+'>'+esc(m.name)+' — $'+m.usd+(m.hi&&m.hi>m.usd?"–"+m.hi:"")+'/image</option>').join("");
 const bc=(I.batch||0).toFixed(4),bh=(I.batch_hi||I.batch||0).toFixed(4);
 const rsO=(I.res||[]).map(r=>'<option value="'+r.k+'"'+((AQ.res||I.defres||"sd")===r.k?" selected":"")+'>'+esc(r.label)+'</option>').join("");
 const rsSel=rsO?('<select id="airz" onchange="aiCost()" title="output size — daam Runware ke apne hisaab se naape hue">'+rsO+'</select>'):"";
 // 27 Oct: dhange = thumbnail categories (transcript wale tareeqe). auto = chaaron soch
// ALAG categories se (pro ka tareeka); ek chuno to chaaron usi category ke alag takes.
const methO=(I.methods||[]).map(x=>'<option value="'+x.k+'"'+((AQ.meth||"auto")===x.k?" selected":"")+' title="'+esc(x.w)+'">'+esc(x.n)+'</option>').join("");
const methSel=methO?('<select id="aimeth" title="thumbnail ka dhanga (category) — auto me chaaron soch ALAG-alag categories se banti hain (pro ka tareeka); ek chuno to chaaron usi dhange ke alag-alag takes">'+
 '<option value="auto"'+((AQ.meth||"auto")==="auto"?" selected":"")+'>auto — chaaron soch ALAG categories se (pro ka tareeka)</option>'+methO+'</select>'):"";
const stv=(AQ.str==null?(I.strdef==null?0.55:I.strdef):AQ.str);
 const stRow=('<div class="bar"><span class="sub">reference se kitna door: <b id="strv">'+stv+'</b></span>'+
  '<input type="range" id="aistr" min="0.10" max="0.90" step="0.05" value="'+stv+'" oninput="strLbl()">'+
  '<span class="sub">0.10 = bilkul naya scene (reference ka bas rang-roop) · <b>0.55 = inspired, naya — default</b> · 0.90 = reference ke qareeb. Reference khaali chhoda ho to is slider ka koi asar nahi.</span></div>');
 const hist=AIH.length?('<div class="sec">Ab tak ki sochें <small> — '+AIH.length+' files, <code>thumb_output/ai/</code> me</small></div>'+
  '<table class="stt"><thead><tr><th scope="col" class="l no">image</th><th scope="col" class="l no">kya tha</th><th scope="col" class="l no">soch</th><th scope="col" class="l no">model</th><th scope="col" class="no">kharcha</th><th scope="col" class="no">score</th><th scope="col" class="no"></th></tr></thead><tbody>'+
  AIH.slice(0,30).map((v,i)=>'<tr><td class="l"><img src="'+imgu(v.path)+'" style="width:150px;border-radius:var(--r1)"></td><td class="l">'+esc(v.name)+'</td>'+
   '<td class="l sub">'+esc(v.idea||"")+'</td><td class="l sub">'+esc(v.model||"")+'</td>'+
   '<td>'+(v.usd?"$"+Number(v.usd).toFixed(4):"—")+'</td><td style="color:'+cc(v.score)+'">'+(v.score||"—")+'</td>'+
   '<td class="l"><span class="tag" onclick="useH('+i+')">analysis</span></td></tr>').join("")+'</tbody></table>'):"";
 $("#main").innerHTML='<h2>'+ico("palette",18)+' AI Thumbnail — Runware (paid), Gemini (free tier, apni key), ya Pollinations (bina key — ab unstable)</h2>'+
  '<div class="sub">Rule: <b>scene AI se, shabd Pillow se</b> — model text likh deta hai (24 Oct ko maine khud dekha), magar spelling aur size ka zimmeda us par chhodne se behtar hai ke shabd wahi engine lagaye jo Behtar banao use karta hai (khaali jagah dhoondna, outline, 320px par padha jaane wala size). Ek click me <b>'+sh+' alag dhange (categories)</b> — designer video wale pro tareeqe, sabse saste model par, aur jeetne wala <b>aapke topic ke benchmark se khud chuna jata hai</b> — wahi naap jo har competitor par lagaye jaate hain. Model ka chunav kaise kiya gaya: <a style="color:var(--acc)" onclick="genpg()">'+ico("spark",14)+'Thumbnail Generation</a>.</div>'+
  '<div class="card"><h3>Runware key '+(I.key?'<span class="hi">✓ set hai — '+esc(I.hint||"")+'</span>':'<span class="lo">set nahi hai</span>')+'</h3>'+
  '<div class="bar"><input type="text" id="aik" placeholder="Runware API key yahan daalo — tool ke folder me runware_key.txt me save ho jaati hai" style="min-width:380px">'+
  '<button class="sm" onclick="aiKey()">save karo</button>'+(I.key?'<button class="sm" onclick="aiKey(1)">hatao</button>':"")+'</div>'+
  '<div class="sub">Key ke bina bhi tool poora chalta hai — Behtar banao sirf aapki apni photo sudharta hai, usme ek paisa nahi lagta. Sirf <b>nayi</b> tasveer banane ke liye key chahiye — magar nayi tasveer ka ek <b>muft rasta bhi tha: Pollinations</b> — 27 Oct 2026 ko usne 402/503 dena shuru kar diya (unka free tier badal gaya), filhal wo bharosemand nahi. Sabse sasta bharosemand rasta <b>Runware: $0.0006/image</b>. Kharcha default model par <b>$0.0006/image</b> — yaani <b>'+sh+' soch = $'+bc+(bh>bc?"–$"+bh:"")+'</b>, aur <b>1000 thumbnails ≈ $0.60</b>. Har generation ke baad <b>asli</b> cost neeche dikhti hai (Runware ka apna hisaab). Range isliye dikhata hoon: 24 Oct ki asli batch me 3 tasks $0.0006 chale, ek task $0.0012 — Runware prompt ke hisaab se price badhata hai, isliye main sirf apna andaaza nahi, uska apna number dikhata hoon. Key isi folder me rehti hai, isliye folder copy karne par wo saath chali jaati hai; naye machine par bas yahan se daal dena.</div></div>'+
    '<div class="card"><h3>Gemini key '+(I.gem?(I.gemn>1?'<span class="hi">✓ pool me '+I.gemn+' keys — limit khatam hone par agli apne aap</span>':"<span class=\"hi\">✓ set hai</span>"):'<span class="lo">set nahi hai</span>')+'</h3>'+
    '<div class="bar"><textarea id="gk" rows="3" spellcheck="false" placeholder="Ek line me ek key — chahein to saari 11 keys ek saath paste kar dein; purani ke saath add hoti jaati hain. Tool ke folder me gemini_key.txt me save hoti hain" style="min-width:380px;flex:1;font-family:ui-monospace,Consolas,monospace;font-size:12px"></textarea>'+
    '<button class="sm" onclick="gemKey()">pool me add karo</button>'+(I.gem?'<button class="sm" onclick="gemKey(1)">pool hatao</button>':"")+'</div>'+
    (I.gem&&I.gemn>1?'<div class="sub">Pool me abhi '+I.gemn+' keys hain — jab kisi ek key ki daily free limit khatam hoti hai to tool agli key par chala jaata hai. Yehi woh tareeka hai jab 10-12 accounts ki keys hain.</div>':"")+
   (I.gem?'<label class="sub" style="cursor:pointer;display:block;margin:8px 0"><input type="checkbox" id="ogm"'+(I.ocr_gem_on?' checked':'')+' onchange="ogmSet(this.checked)"> <b>Text Gemini ke vision model se padhwao (OCR)</b> — padhai local engine se behtar (stylized/3D text tukdon me nahi tootta) aur <b>machine par kuch bhi chalta hi nahi</b> — jis dost ke paas GPU nahi hai us par bhi aaram. Badle me key ki free-tier quota lagti hai (~500 token/tasveer); speed-batta built-in hai — bade channel-scan me 10 minute ke 60 se zyada padhai apne aap local par chali jaati hai. Band karne par OCR local engine karega — muft, unlimited, CPU par (GPU phir bhi zaroori nahi), bas kamzor machine par slow aur padhai kam.</label>':"")+
    '<div class="sub">Gemini teen kaam karta hai: (1) upar engine menu me <b>Gemini</b> chun kar tasveer — free tier par, apni key par, roz ki chhoti limit ke andar; (2) <b>Apni thumbnail</b> check ke baad "Gemini se dekhwa lo" — model se 5 sawalon ka feedback; (3) <b>OCR</b> — poore tool ki text-padhai (upar wale toggle se). Teeno par qaaida: jo model ka kaha hai wo <b>"model ka andaza"</b> label ke saath dikhega, hamare naape se kabhi nahi mila. Free tier par bhi key isliye chahiye kyunki limit aapki account se judi hoti hai.</div></div>'+
   '<div class="card"><h3>YouTube Data API key '+(YTOK?(YTN>1?'<span class="hi">✓ pool me '+YTN+' keys — quota khatam hone par agli apne aap</span>':'<span class="hi">✓ set hai</span>'):'<span class="lo">set nahi hai</span>')+'</h3>'+
   '<div class="bar"><textarea id="yk" rows="3" spellcheck="false" placeholder="YouTube Data API keys − ek line me ek key. 11 keys bhi ek saath paste kar do: pool me add ho jaayengi (duplicate apne aap chhoot jaayengi), aur ek key ka din ka quota (10,000 units) khatam ho to tool apne aap agli key laga deta hai" style="min-width:380px;flex:1;font-family:ui-monospace,Consolas,monospace;font-size:12px"></textarea>'+
   '<button class="sm" onclick="ytKey()">pool me add karo</button>'+(YTOK?'<button class="sm" onclick="ytKey(1)">pool hatao</button>':"")+'</div>'+
   (YTOK&&YTN>1?'<div class="sub">Pool me abhi '+YTN+' keys hain — har key ka apna alag daily quota hota hai, isliye jitni zyada keys utna zyada din ka quota. Ek trending scan sirf 1 unit khata hai — bartan ki bhatti nahi, chammach.</div>':"")+
   '<div class="sub">Ye key do kaam ke liye hai: <b>Trending scan</b> (YouTube ka apna chart — wo Competitors wale page par dikhta hai, jab tak koi scan khula nahi) aur <b>asli tags + description</b> (har video ka khud-lagaya metadata). Competitors ka topic scan aur channel scan bina is key ke bhi chalte hain — wo YouTube ka data bina-API raste laate hain, aur un numbers par saaf likha hota hai ki wo search-fetch hain, official nahi. Key free tier par bhi chahiye kyunki quota aapke Google account se juda hota hai — isliye kai accounts ki keys pool me daalne se din ka quota kai guna badh jaata hai.</div></div>'+
  '<div class="card"><h3>Kya banana hai</h3>'+
  '<textarea id="aiq" placeholder="scene ka idea — English me behtar chalta hai. Jaise: astronaut floating inside a giant black hole, glowing orange accretion disk, cinematic light, shocked human face on the right third">'+esc(AQ.idea)+'</textarea>'+
  '<div class="sub">Ye sirf <b>scene</b> ka idea hai. Kisi bhi competitor card par <b>AI se banao</b> dabao to uska title yahan aa jaata hai, aur <b>“Is se inspire ho kar naya”</b> uske title + <b>asli tags</b> + <b>asli description</b> se poora idea banata hai aur uska thumbnail reference bana kar (strength 0.55) us se inspire ho kar nayi tasveer banata hai — copy nahi. Idea khud likhne ki zaroorat nahi.</div>'+
  '<div class="bar"><input type="text" id="aiw" placeholder="thumbnail par KYA LIKHA JAAYE — 2 se 4 shabd (khaali chhodo = topic ke bare keywords apne aap chune jaayenge — audience wahin rukti hai)" value="'+esc(AQ.words)+'" style="min-width:380px">'+
  '<label class="sub" style="cursor:pointer"><input type="checkbox" id="ait"> text bhi AI se (spelling ka zimmeda AI par — benchmark khud bata dega behtar tha ya nahi)</label></div>'+
  '<div class="bar"><input type="text" id="air" placeholder="reference (optional): apni thumbnail ka path / competitor ka thumbnail / YouTube ka link" value="'+esc(AQ.ref)+'" style="min-width:420px">'+
  '<select id="aieng" onchange="aiCost()" title="tasveer kaun banaye — Runware (key, paid, poori control), Pollinations (bina key — ab unstable), Gemini free tier (apni key), ya Antigravity (aapki Google AI subscription, bina key)"><option value="rw"'+(AQ.eng==="poll"?"":" selected")+'>Runware — key chahiye, paid</option><option value="poll"'+(AQ.eng==="poll"?" selected":"")+'>Pollinations — bina key (free tier ab unstable — 402/503 mil sakta hai)</option><option value="gem"'+(AQ.eng==="gem"?" selected":"")+'>Gemini — free tier, apni key</option>'+(AIINFO.agy?'<option value="agy"'+(AQ.eng==="agy"?" selected":"")+'>Antigravity — aapki Google AI subscription (bina key)</option>':'')+'</select>'+
   '<select id="aim" onchange="aiCost()">'+ms+'</select>'+rsSel+methSel+'</div>'+stRow+
  '<div class="sub">Reference ka sach, 24 Oct ko <b>naapa gaya</b> (same prompt, same model, sirf reference badla; farak 0-100 me — wahi scale jo har card par dikhta hai): koi reference nahi = <b>13</b>, <code>imageUrls</code> bheja = <b>16</b> (yaani wo param is model par koi asar nahi karta — purana version isi par chalta tha, isliye "reference" theatre tha), <b>seedImage + strength 0.3 = 1</b> (reference ka remix), <b>0.55 = 3 — inspired, naya (default)</b>, 0.85 = 9 (rang-roop barkaraar, scene naya). Isliye yahan <b>seedImage</b> bheja jaata hai, aur upar ka slider usi ka hai; har card par apna <b>asli naapa hua farak</b> dikhta hai. Text ka faaisla OCR se hota hai, reference se nahi (reference ka sach: <a style="color:var(--acc)" onclick="genpg()">kaunsa plan chuna aur kyun</a>). Size aap chunte ho — teeno daam Runware ke apne hisaab se 24 Oct ko naape gaye (ek hi batch me daam alag-alag hota hai, isliye range): <b>1024×576 = $0.0006–0.0012</b>, <b>1536×864 = $0.0013–0.0025</b>, <b>2048×1152 = $0.0032</b>. Tool ab tasveer ko sikodta nahi, usi size par save karta hai (analysis sasta hai isliye). 4K uske upar alag kaam hai: <b>$0.010/image</b> (naapa: 3842×2180, 13 second) — aur ek muft rasta bhi hai (Pillow Lanczos: paisa nahi, par usme nayi detail paida nahi hoti, sirf tasveer badi hoti hai). Zyada kaam ke liye 2048 kaafi hai: YouTube browse par 1280×720 tak hi rakhta hai. <b>AI ka text — mera purana dawa GALAT tha (24 Oct; ab main images khud dekh sakta hoon).</b> Pehle kehta tha ye model har scene me 7–13 jagah bekaar ke letters banata hai, isliye tool har baar unhe dhundhla deta hai. Wo ginti OCR ki thi, aankh ki nahi. Teen raw files maine khud dekhi: "MYSTERY OF BLACK HOLES" teeno me, spelling poori sahi, composition theek — model wo likh deta hai jo maanga jaaye. <b>Asal nuksan mera scrub kar raha tha:</b> usne sahi text ko dhundhla kar "BLA CK HOLES" jaisa adhoora kar diya, aur Pillow wale naye shabd usi bache hue text se takra gaye. <b>Ab kuch bhi chup-chaap nahi bigada jaata.</b> Agar raw me text hai to aapko <b>donon</b> cards milte hain: ek par AI ka text jaisa tha waisa hi — na scrub, na overlay, aur us card par likha hota hai ke OCR ne kya padha aur kitna confidence mila; dusra par muft scrub karke aapke apne shabd. Kaun jeeta — <b>benchmark aur aapki aankh</b> faaisla karti hai, mera andaaza nahi. Ye isliye, kyunki maine koshish kar ke dekha: "AI ka text theek hai ya nahi" local OCR se pakka nahi nikalta — OCR "BLACK" ko "BLA" + "CK" me tod deta hai, isliye poori tarah sahi text bhi 3 me se sirf 1 match deta hai. Saaf, pakke text ka muft rasta ab bhi wahi hai: <b>Behtar banao</b> — wohi asli photo, shabd Pillow se, spelling 100%.</div>'+
  '<div class="bar"><span id="aicost" class="sub"></span><button class="go" id="aigo" onclick="goAI()">'+ico("palette",14)+''+sh+' alag dhange (categories) banao — ~$'+bc+'</button>'+
   '<a class="btn sm" href="/api/sharezip" download title="dost ko bhejne layak fresh zip — tool ka code, magar aapki API keys aur aapki history (thumb_output) ke baghair">'+ico("dl",14)+'Dost wala zip (bina keys/history)</a>'+
  (AIH.length?'<button class="sm" onclick="aiClear()">'+ico("trash",14)+'purani hatao</button>':"")+'</div></div>'+
  '<div id="aires">'+(AIRES?renderAI(AIRES):"")+'</div>'+hist;
 aiCost()}
async function goAI(){aiGet();const idea=(AQ.idea||"").trim(),ref=(AQ.ref||"").trim();
 if(!idea&&!ref)return toast("idea likho (ya reference daalo)");
 spin();let d;try{d=await jp("/api/aigen",{idea:idea,words:AQ.words||"",mk:AQ.mk||AIINFO.def||"z",ref:ref,text_ai:!!(($("#ait")||{}).checked),res:AQ.res||"sd",strength:AQ.str,eng:AQ.eng||"rw",method:AQ.meth||"auto"})}
 catch(e){$("#main").innerHTML='<div class="err">✗ '+esc(e.message)+'</div><div class="bar"><button class="sm" onclick="aipg()">'+ico("back",14)+'wapas</button></div>';return}
 if(d.error){$("#main").innerHTML='<div class="err">✗ '+esc(d.error)+'</div><div class="bar"><button class="sm" onclick="aipg()">'+ico("back",14)+'wapas</button></div>';return}
 const lim=(AQ.eng==="agy"?750:200); // Antigravity ~1 min/tasveer hai — 4 ka batch 10 min bhi le sakta hai; 3 min ka purana limit use khatam kar deta tha
 for(let i=0;i<lim;i++){await new Promise(r=>setTimeout(r,900));const p=await j("/api/progress?id="+d.job);
  if(p.state==="done"){AIRES=p.result;await aipg();return}
  if(p.state==="error"){$("#main").innerHTML='<div class="err">✗ '+esc(p.error)+'</div><div class="bar"><button class="sm" onclick="aipg()">'+ico("back",14)+'wapas</button></div>';return}
  const pc=p.total?Math.round(p.done*100/p.total):0;
  $("#main").innerHTML='<h2>'+ico("palette",18)+' AI Thumbnail</h2><div class="sub">'+esc(p.current||"…")+' — '+p.done+'/'+p.total+
   ' · har soch ko wahi OCR + analysis se napa jata hai jo competitors se</div><div class="pbar"><i style="width:'+pc+'%"></i></div>'}
 $("#main").innerHTML='<div class="err">bahut lamba laga — model badal kar dobara dabao. (Kaam server par chalta raha ho to page kholne par History me aa jaayega.)</div>'}
function aiNote(v){const n=v.name||"";
 if(n.indexOf("as-is")>=0){var sb=(v.spell||[]).filter(function(s){return s.st==="close";});
  return (sb.length?' <b>SPELLING KA SHAK:</b> "'+sb.map(function(s){return esc(s.w)+'" ke bajaye scene par "'+esc(s.got);}).join(' · ')+'" likha hai — akshar khud gin kar dekho. Score bara aur saaf text ko number deta hai, spelling ko nahi. ':'')+' <b>is par koi haath nahi lagaya</b> — doosre cards ke score se tulna karke yahi chuno.';}
 if(!v.airaw)return ' <b>scene me kuch likha hua hi nahi tha</b>, isliye haath lagane ki zaroorat nahi pari.';
 if(v.scrub)return ' <b>AI ka text muft scrub se hata diya gaya</b>'+(v.noise?', ab bhi '+v.noise+' jagah bachi hai':', text poori tarah gaya')+' — agar iska score as-is se kam hai to scrub ne scene ka hissa bhi chhua hai, as-is card behtar hai. ';
 if(v.airaw&&v.scrubv===2)return ' <b>AI ka text chheda hi nahi gaya</b> — wo line chehre ke upar chadh rahi thi, aur scrub chehra dhundhla kar deta hai (ye maine images dekh kar maana hai). As-is card ya khaali jagah par bithaye shabd hi theek hain.';
 return '';}
function renderAI(R){const B=(D&&D.deep&&D.deep.bench)||{},its=R.items||[],top=its[0]||{};
 const bc=(B&&top.ts)?[pchip(B,"text_size","bada text @320",top.ts.h320,"is me"),pchip(B,"text_contrast","text contrast",top.ts.cr_med,"is me"),
  pchip(B,"words","shabd",top.ts.n||0,"is me"),pchip(B,"brightness","brightness",top.an&&top.an.bright,"is me")].filter(x=>x).join(""):
  '<span class="sub">Topic scan khula ho to yehi batayega ki ye soch in '+((D&&D.items.length)||50)+' competitors ke benchmark me kahan khadi hai.</span>';
 const cards=its.map((v,i)=>'<div class="card"><h3>'+esc(v.name)+' — <span style="color:'+cc(v.score)+'">'+(v.score||"—")+'/100</span>'+
  (v.usd?' <span class="sub">$'+Number(v.usd).toFixed(4)+'</span>':"")+
  (v.dir?' <span class="chip">direction: <b>'+esc(v.dir)+'</b></span>':"")+
  (v.w?' <span class="chip">'+v.w+'×'+v.h+(v.res?' ('+esc(v.res)+')':'')+'</span>':"")+
  (v.dref?' <span class="chip">reference se farak <b>'+v.dref.px+'/100</b></span>':"")+
  (v.strength?' <span class="chip">strength <b>'+v.strength+'</b></span>':"")+
  (v.spell&&v.spell.some(function(s){return s.st==="close";})?' <span class="chip" style="background:rgba(var(--warnrgb),.14);color:var(--warn);border-color:rgba(var(--warnrgb),.4)">spelling shak</span>':"")+
  '</h3><div class="sub">'+esc(v.why)+aiNote(v)+'</div>'+
  '<div class="rvs"><div class="rvimg"><div class="lab">desktop browse 320px</div><img src="'+imgu(v.path)+'" style="width:320px;max-width:100%"></div>'+
  '<div class="rvimg"><div class="lab">mobile feed 210px</div><img src="'+imgu(v.path)+'" style="width:210px"></div>'+
  '<div class="rvimg"><div class="lab">asli size</div><img src="'+imgu(v.path)+'" style="width:560px;max-width:100%"></div></div>'+
  '<div style="margin-top:8px">'+chipsOf(v)+'</div>'+
  (v.dref?drefNote(v):"")+'<div id="u4v'+i+'"></div>'+'<div class="bar" style="margin:8px 0 0"><button class="sm" onclick="up4kV('+i+',&quot;free&quot;)">'+ico("up",14)+'4K master (muft, Pillow)</button><button class="sm" onclick="up4kV('+i+',&quot;ai&quot;)">'+ico("up",14)+'4K master (AI upscale, ~$0.010)</button></div>'+'<div class="bar" style="margin:10px 0 0"><button class="sm" onclick="useAI('+i+')">'+ico("image",14)+'iska poora analysis</button>'+
  '<button class="sm" onclick="saveAI('+i+')">'+ico("ab",14)+'A/B me save karo</button></div></div>').join("");
 const rp=/\.(jpe?g|png|webp|bmp)$/i.test(AQ.ref||"")?AQ.ref:"";
 const ref=rp?('<div class="two"><div><div class="sub">aapka reference</div><div class="bwrap"><img src="'+imgu(rp)+'" style="width:100%;border-radius:var(--r2)"></div></div>'+
  '<div><div class="sub">AI ne usi idea se banaya (sabse behtar) — neeche naapa gaya farak:</div>'+drefNote(its[0]||{})+'<div class="bwrap"><img src="'+imgu((its[0]||{}).path||"")+'" style="width:100%;border-radius:var(--r2)"></div></div></div>'):
  '<div class="two"><div><div class="sub">soch</div><div class="card">'+esc(R.idea||AQ.idea||"")+'</div></div>'+
  '<div><div class="sub">sabse behtar</div><div class="bwrap"><img src="'+imgu((its[0]||{}).path||"")+'" style="width:100%;border-radius:var(--r2)"></div></div></div>';
 return '<div class="sec">Natije <small> — model '+esc(R.model||"")+(R.size?' · size <b>'+esc(R.size)+'</b>':'')+(R.strength!=null?' · strength <b>'+R.strength+'</b> (reference se kitna door gaye)':'')+' · kul kharcha <b>$'+Number(R.cost||0).toFixed(4)+'</b> · sabse upar wala sabse mazboot napa gaya</small></div>'+
  ((R.errs||[]).length?'<div class="card"><div class="err">'+esc((R.errs||[]).join(" · "))+'</div></div>':"")+
  '<div class="card">'+bc+'</div>'+ref+'<div class="sec">'+its.length+' soch, sabse behtar pehle</div><div class="grid">'+cards+'</div>'+
  '<div class="bar" style="margin-top:12px"><button class="sm" onclick="aipg()">naya banakar dobara</button><button class="sm" onclick="goAI()">wahi dobara ('+((AIINFO.shots||4))+' soch)</button><button class="sm" onclick="cmp()">'+ico("back",14)+'competitors</button></div>'}

// ---------- meri thumbnail ----------
async function mine(){
 if(cur)await ensureData();  // benchmark (D.deep.bench) ke liye scan data chahiye — direct deep-link par D khali hota tha
 $("#main").innerHTML='<h2>'+ico("image",18)+' Meri Thumbnail</h2><div class="sub">Apni thumbnail ka <b>poora path</b> (C:\\Users\\...\\thumb.jpg), ya YouTube ka link/video id, ya TikTok/Instagram ka link (wahan se unka apna thumbnail + unka apna diya data aata hai — YouTube ke numbers se tulna nahi), ya neeche se file chuno. Tool use YouTube ke asli sizes par dikhaata hai, OCR se text padhta hai, aur (scan kiya ho to) batata hai ki aap in 50 videos me kahan khade ho.</div>'+
 '<div class="bar"><input type="text" id="ref" placeholder="C:\\Downloads\\thumb.jpg  ya  https://youtu.be/XXXX  ya  TikTok/Instagram ka link" style="min-width:420px" value="'+esc(MINE?MINE.path:"")+'">'+
 '<button class="go" onclick="chk()">Check karo</button><input type="file" id="f" accept="image/*" onchange="upl()"></div>'+
 (PEND?'<div class="card"><div class="sub">Behtar banao se bana version check karne ke liye taiyaar hai: <b>'+esc(PEND)+'</b></div><div class="bar"><button class="go" onclick=\'chkP()\'>iska analysis karo</button><button class="sm" onclick=\'PEND="";mine()\'>rehne do</button></div></div>':"")+
 '<div id="mr">'+(MINE?renderMine(MINE):"")+'</div>'}
async function upl(){const f=$("#f").files[0];if(!f)return;const fr=new FileReader();
 fr.onload=async()=>{const d=await fetch("/api/upload",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:f.name,b64:fr.result})});
  const r=await d.json();if(r.error)return toast(r.error);$("#ref").value=r.path;chk()};
 fr.readAsDataURL(f)}
function chkP(){if(!PEND)return;$("#ref").value=PEND;chk()}
function ownBlk(d){const vid=d.vid||"",O=d.own||{};
 if(!vid)return '<div class="sec">Asli CTR/retention — is file ke liye</div><div class="card"><div class="sub">Ye thumbnail kisi file path se aayi hai, iska koi YouTube video id nahi. CTR/retention ka koi data jud nahi sakta. Apni upload ki hui video ka <b>link</b> daal kar check karo to id mil jaayegi aur aap apna asli number save kar sakte ho.</div></div>'+
  '<div class="bar"><button class="sm" onclick="mine()">'+ico("back",14)+'link se check karo</button></div>';
 return '<div class="sec">Is video ka ASLI CTR/retention <small> — YouTube ye sirf channel ke malik ko deta hai, isliye ye sirf aap de sakte ho</small></div><div class="card">'+
  (O.ctr!=null||O.ret!=null?'<div class="sub">PEHLE SE SAVE HUA ASLI NUMBER: '+(O.ctr!=null?'CTR <b style="color:var(--grn)">'+O.ctr+'%</b> ':"")+(O.ret!=null?'retention <b style="color:var(--grn)">'+O.ret+'%</b> ':"")+'<span class="sub">daala gaya '+esc(O.at||"")+'</span></div>':
   '<div class="sub">abhi koi asli number nahi. YouTube Studio → Analytics → “Reach” me apni video ka <b>click-through rate</b> aur “Engagement” me <b>average view duration %</b> dikhta hai — wo yahan likh do. Uske baad ye tool har tulna me aapka asli number use karega, andaaze nahi.</div>')+
  '<div class="bar" style="margin-top:8px"><input type="text" id="ownc" placeholder="ASLI CTR % (jaise 4.7)" style="min-width:150px" value="'+(O.ctr!=null?O.ctr:"")+'">'+
  '<input type="text" id="ownr" placeholder="ASLI retention % (jaise 42)" style="min-width:150px" value="'+(O.ret!=null?O.ret:"")+'">'+
  '<button class="go" onclick="saveOwnM(\''+vid+'\')">asli number save karo</button><span class="sub">video id <code>'+esc(vid)+'</code></span></div></div>'}
async function saveOwnM(vid){const c=($("#ownc")||{}).value||"",r=($("#ownr")||{}).value||"";
 if(!c&&!r)return toast("CTR ya retention likho");
 try{const d=await jp("/api/own",{vid:vid,ctr:c,ret:r});if(d.error)return toast(d.error,"bad","Asli number jod nahi paya");
  if(MINE)MINE.own=d.own||{};toast("asli number save ho gaya — ab ye har jagah asli dikhega");
  if(MINE&&$("#mr"))$("#mr").innerHTML=renderMine(MINE)}catch(e){failToast(e,"badlav save karna")}}
// ---- apna asli CTR (Studio CSV) + us par wazon ki calibration ----
const WLAB={big_text:"asli text ki size",n_text:"shabdon ki tadaad",contrast:"text ka asli contrast (WCAG)",
 outline:"outline/shadow ka asar",face:"chehre ka size",frontal:"chehra saamne ka",bright:"brightness",
 dyn:"range/depth",clean:"frame ki safai",focus:"ek dominant subject",subject:"subject ka size",
 thirds:"rule-of-thirds",sharp:"clearness"};
async function ownpg(){const _t=RTN;let s;try{s=await j("/api/sys")}catch(e){s=SYS}SYS=s;
 if(_t!==RTN)return;
 $("#main").innerHTML='<h2>Apna CTR + wazon ki calibration</h2>'+
  '<div class="sub">Do kaam ek jagah: (1) <b>YouTube Studio ki CSV</b> se apne videos ka ASLI CTR/AVD yahan laao — YouTube wo data sirf channel ke malik ko deta hai, bina API key ke bahar nahi aata. (2) Wo asli numbers milne par <b>score ke wazan usi data par fit</b> hote hain. Abhi jo weights chal rahe hain wo engineering ke andaze hain, aapke channel se nape gaye nahi.</div>'+
  calCard(s)+
  '<div class="sec">YouTube Studio ki CSV <small> — Studio → Analytics → Content → Videos → Export CSV. Wo file ka raw text yahan paste karo; kuch upload nahi hota, kuch bahar nahi jaata.</small></div>'+
  '<div class="card"><textarea id="csvp" placeholder="Video title,Video id,Publication date,Views,Impressions,Impressions click-through rate (%),Average view duration,Average percentage viewed (%)"></textarea>'+
  '<div class="bar"><button class="sm" onclick="csvDry()">pehle dekho — kuch save nahi hoga</button>'+
  '<button class="go" onclick="csvGo()">asli numbers import karo</button>'+
  '<span class="sub">id column na ho to title se jodenge — tab naam ka POORA mel khana chahiye, warna line chhod di jaayegi (galat video par CTR baithna sabse bada dhoka hai)</span></div>'+
  '<div id="csvout"></div></div>'+
  ownTable(s)}
function calCard(s){const c=s.cal,k=s.heuristic,wD=s.w_def||{},wOn=s.w_on||wD;
 const keys=Object.keys(wD);
 const rows=keys.map(kk=>{const a=wD[kk],b=wOn[kk],raw=c&&c.raw?c.raw[kk]:null;
  return '<tr><td>'+esc(WLAB[kk]||kk)+'</td><td class="num">'+a+'</td>'+
   (k?'':'<td class="num">'+(b!=null?b:0)+'</td>')+
   (raw==null?'':'<td class="num '+(raw<0?'lo':'hi')+'">'+(raw>0?"+":"")+raw+'</td>')+'</tr>'}).join("");
 const st=k?'<b style="color:var(--amb)">abhi HEURISTIC wazan chal rahe hain</b> — ye engineering ke andaze hain, aapke CTR se nape gaye nahi. Inhe asli banane ke liye neeche CSV daalo aur calibrate karo.'+ (s.cal_rejected?'<div class="sub">'+ico("alert",14)+' '+esc(s.cal_rejected)+'</div>':'')
  :'<b style="color:var(--grn)">CALIBRATED wazan chal rahe hain</b> — fit: '+esc(c.fit||"")+' · videos <b>'+c.n+'</b> · R² <b>'+c.r2+'</b> · cross-validated R² <b>'+(c.cv_r2==null?"—":c.cv_r2)+'</b> · CTR median '+c.ctr_med+'% · '+esc(c.at?new Date(c.at*1000).toLocaleString():"");
 return '<div class="sec">Score ke wazan kis par bane <small> — isi ka naam har score card par likha hota hai</small></div><div class="card">'+st+
  (k?'<div class="sub" style="margin-top:6px">Ready videos (jinme asli CTR hai): <b>'+s.own_ready+'</b> / '+s.own_rows+'. Calibration ke liye kam se kam <b>'+s.need+'</b> chahiye. '+(s.ridge?'sklearn (Ridge + 5-fold) mojood hai.':'sklearn nahi hai — calibration nahi ho sakti.')+'</div>'
     :'<div class="sub" style="margin-top:6px">R² = in features se aapke CTR ka kitna hissa samajh aata hai. Cross-validated R² asli taqat hai (yaad karne ka dhoka nahi). 30 se kam videos par ye sirf ishara hai, faisala nahi. Jo feature ka coefficient minus me hai, uska matlab hai ki mere channel par wo cheez CTR ke ULTI chalti hai.</div>')+
  '<table style="margin-top:10px"><tr><th scope="col">feature</th><th scope="col" class="num">heuristic wazan</th>'+(k?'':'<th scope="col" class="num">mere data par fit</th>')+(c&&c.raw?'<th scope="col" class="num">asli coefficient</th>':'')+'</tr>'+rows+'</table>'+
  '<div class="bar"><button class="go" onclick="calGo()">wazan mere asli CTR par fit karo</button><span class="sub">har apni video ka thumbnail dobara naapa jaayega (naapa hua ~0.5s/video)</span></div><div id="calout"></div></div>'}
function ownTable(s){return '<div class="sec">Apne videos ke abhi tak ke asli numbers <small> — ye own.json me save hai: '+s.own_rows+' videos, inme se '+s.own_ready+' me ASLI CTR hai</small></div>'+
  '<div class="card"><div class="sub">Ek-ek karke bhi bhar sakte ho: apni video ka link kholo → “Meri Thumbnail” → neeche “ASLI CTR”. Poore channel ke liye CSV se behtar nahi.</div>'+
  (s.own_rows?'<div class="sub">import ke baad har row ka title/CTR/AVD yahi se dikhega, aur calibration button khud utha lega.</div>':'<div class="sub">abhi kuch nahi — pehle CSV daalo.</div>')+'</div>'}
async function csvDry(){const t=($("#csvp")||{}).value||"";if(!t)return toast("CSV paste karo");
 const o=$("#csvout");if(!o)return;o.innerHTML=skelLines(3,"CSV parse ho raha hai…");
 try{o.innerHTML=csvRep(await jp("/api/own_csv",{csv:t,dry:true}))}catch(e){o.innerHTML='<div class="err">✗ '+esc(e.message)+'</div>'}}
async function csvGo(){const t=($("#csvp")||{}).value||"";if(!t)return toast("CSV paste karo");
 const o=$("#csvout");if(!o)return;o.innerHTML=skelKpi(4)+skelLines(3,"asli numbers apne videos se jode ja rahe hain…");
 let d;try{d=await jp("/api/own_csv",{csv:t,dry:false})}catch(e){o.innerHTML='<div class="err">✗ '+esc(e.message)+'</div>';return}
 o.innerHTML=csvRep(d);if(d.ok){toast(d.n_matched+' videos ke asli numbers save ho gaye');
  setTimeout(ownpg,1200)}}
function csvRep(d){if(d.error)return '<div class="err">✗ '+esc(d.error)+'</div>'+
  (d.header?'<div class="sub">aapke CSV ke headers: '+d.header.map(h=>esc(h)).join(" · ")+'</div>':'');
 const f=d.cols_found||{},m=d.cols_missing||[];
 let h='<div class="sub">pehchane gaye columns: '+Object.keys(f).map(k=>'<span class="chip">'+k+' <b>'+esc(f[k])+'</b></span>').join('')+
  (m.length?'<br>jo column nahi mile (sirf wo data nahi aayega): '+m.map(esc).join(', '):'')+'</div>';
 h+='<div class="kpi">'+kpi("CSV ki lines",d.rows_in)+kpi("asli videos se jude",d.n_matched,"var(--grn)")+
    kpi("title se solve",d.by_title)+kpi("chhod di lines",d.n_bad,d.n_bad?"var(--amb)":"")+'</div>';
 if((d.matched||[]).length)h+='<table><tr><th scope="col">video</th><th scope="col" class="num">CTR %</th><th scope="col" class="num">AVD</th><th scope="col" class="num">retention %</th></tr>'+
  d.matched.slice(0,25).map(r=>'<tr><td>'+esc(r.title||r.vid)+' <span class="sub">'+esc(r.vid)+'</span></td><td class="num">'+(r.ctr==null?"—":r.ctr)+'</td><td class="num">'+(r.avd==null?"—":Math.round(r.avd/60)+"m")+'</td><td class="num">'+(r.ret==null?"—":r.ret)+'</td></tr>').join("")+'</table>';
 if((d.unmatched||[]).length)h+='<div class="sub" style="margin-top:8px">kyun chhoda:'+d.unmatched.slice(0,10).map(u=>'<br>· '+esc(u.title)+' — '+esc(u.why)).join('')+'</div>';
 if(d.dry)h+='<div class="sub" style="margin-top:8px">ye sirf jaanch thi — kuch save nahi hua. Theek lage to “asli numbers import karo” dabao.</div>';
 return h}
async function calGo(){const o=$("#calout");if(!o)return;o.innerHTML=skelKpi(5)+skelLines(3,"fit chalu hai — 5-fold cross-check me thora waqt lagta hai");
 let d;try{d=await jp("/api/calibrate",{})}catch(e){o.innerHTML='<div class="err">✗ '+esc(e.message)+'</div>';return}
 if(d.error){o.innerHTML='<div class="err">✗ '+esc(d.error)+'</div>';return}
 for(let i=0;i<400;i++){await new Promise(r=>setTimeout(r,900));let p;try{p=await j("/api/progress?id="+d.job)}catch(e){continue}
  if(p.state!=="run"){const r=p.result||{};
   const msg=(p.state==="error"||!r.ok)?'<div class="err">✗ '+esc(p.error||r.error||"fit nahi hua")+'</div>'+
     (r.unready||[]).slice(0,8).map(u=>'<div class="sub">· '+esc(u.vid)+' — '+esc(u.why)+'</div>').join(''):
     '<div class="sub" style="color:var(--grn)">✓ ab wazan aapke '+r.cal.n+' videos ke ASLI CTR par fit hain (R² '+r.cal.r2+', cross-validated '+r.cal.cv_r2+'). Naya scan inhi naye wazon se banega.</div>';
   await ownpg();const cc=$("#calout");if(cc)cc.innerHTML=msg;return}
  const pc=p.total?Math.round(p.done*100/p.total):0;
  o.innerHTML='<div class="sub">'+esc(p.current||"…")+' — '+p.done+'/'+p.total+'</div><div class="pbar"><i style="width:'+pc+'%"></i></div>'}}
async function chk(){const v=$("#ref").value;if(!v)return toast("path ya link daalo");const m=$("#mr");if(!m)return;
 m.innerHTML='<div class="empty">check ho raha hai — 1 second se kam lagta hai (naapi hui: nayi file 0.7s, dobara 0.2s — ek hi file dobara OCR nahi hoti, cache hai)...</div>';
 const d=await j("/api/check?ref="+encodeURIComponent(v)+"&title="+encodeURIComponent(TITLE||""));if(d.error){m.innerHTML='<div class="err">'+esc(d.error)+'</div>';return}
 MINE=d;PEND="";m.innerHTML=renderMine(d)}
 // Style fit: jab current scan me Style jeet naapi gayi ho, tab aapki thumbnail ka
 // style-andaza us scan ki sab se zyada chalne wali style se tulta hai. Ye bhi
 // andaza hai, guarantee nahi — isliye seedha "badlo" nahi kehta.
function styFitHint(d){if(!d.sty||!(D&&D.sty))return "";
 const g={};(D.items||[]).forEach(it=>{const b=(D.sty||{})[it.id];if(!b||b==="unknown")return;const a=g[b]=g[b]||{vs:[],n:0};a.n++;const v=vpd(it);if(v>0)a.vs.push(v)});
 const best=Object.keys(g).map(k=>({k:k,med:g[k].vs.length?medv(g[k].vs):0,n:g[k].n})).filter(r=>r.med>0).sort((x,y)=>y.med-x.med)[0];
 if(!best)return "";
 const me=d.sty;
 let a='<div class="sub" style="margin:6px 0;padding:8px 10px;background:var(--panel2);border-radius:var(--r1)"><b>Style fit</b> — is scan me sab se zyada chalne wali style ka andaza: <b>'+esc(STYL[best.k]||best.k)+'</b> ('+best.n+' videos, median views/day '+fmt(best.med)+'). Aapki thumbnail ka andaza: <b>'+esc(me==="unknown"?"pehchaan nahi hua":(STYL[me]||me))+'</b>. ';
 if(me==="unknown")a+='Classifier aapki thumbnail ka pattern pehchaan na saka — ye is baat ka saboot nahi ki wo kharab hai.';
 else if(me===best.k)a+='Dono ka pixel-pattern melta hai — style badalne ki zaroorat nahi, content par kaam karo.';
 else a+='Pattern alag hai. Style copy karna jaadu nahi — ye sirf pixel-pattern ka andaza hai — par topic wahi hai to dekhna faaydemande hai ki us style me aapka content kaam kar sakta hai ya nahi.';
 return a+' Ye poora tulna classifier ka andaza hai, guarantee nahi.</div>'}
function renderMine(d){
 const an=d.an||{},ts=d.ts||{},B=(D&&D.deep&&D.deep.bench)||null,sc=100/(an.w||1);
 const boxes='<div class="owrap"><img src="'+imgu(d.path)+'" style="width:100%;display:block;border-radius:var(--r2)">'+
  (d.words||[]).map(w=>'<div class="oword" title="'+esc(w.t)+'" style="left:'+(w.x*sc)+'%;top:'+(w.y*sc)+'%;width:'+(w.w*sc)+'%;height:'+(w.h*sc)+'%"></div>').join("")+
  (d.faces||[]).map(f=>'<div class="fbox" title="chehra: frame ka '+f.area+'%" style="left:'+(f.x*100)+'%;top:'+(f.y*100)+'%;width:'+(f.w*100)+'%;height:'+(f.h*100)+'%"></div>').join("")+'</div>';
 const big=(d.faces||[]).length?Math.max.apply(null,d.faces.map(f=>f.area||0)):0;
 const rd=(v)=>v==null?null:Math.round(v*1000)/1000;
 const sizes=[[1280,"asli / upload"],[320,"desktop browse (sabse common)"],[210,"mobile app feed"],[168,"sidebar / suggested"]].map(s=>
  '<div class="size"><div class="lab">'+s[1]+' — '+s[0]+'px wide</div><img src="'+imgu(d.path)+'" style="width:'+s[0]+'px;max-width:100%"></div>').join("");
 const pal=(an.colors||[]).map(c=>'<span class="chip"><span class="sw" style="background:'+c.hex+'"></span>'+esc(c.fam)+' '+c.pct+'%</span>').join("");
 const vs=(d.verdicts||[]).map(v=>'<div class="v"><b class="'+v.s+'">'+(v.s==="ok"?"✓":v.s==="warn"?"!":"✗")+'</b><div>'+esc(v.k)+'</div><div class="n">'+esc(v.v)+' — '+esc(v.n)+'</div></div>').join("");
 const cmp=D?cmpHint(ts,an,D.agg):"";
 const kp='<div class="kpi">'+kpi("score",d.score+"/100",cc(d.score))+
  kpi("text ke shabd",ts.n||0,ts.n?"":"var(--amb)")+
  kpi("sabse bada text @320",(ts.h320||0)+"px",ts.h320>=THv("h_ok",18)?"var(--grn)":ts.h320?"var(--amb)":"var(--red)")+
  kpi("320px par padha gaya",(d.read320||0)+"/"+(ts.n||0),(d.read320||0)>=(ts.n||0)?"var(--grn)":"var(--amb)")+
  kpi("text contrast",ts.cr_med==null?"—":f2(ts.cr_med)+":1",ts.cr_med==null?"":ts.cr_med>=THv("cr_ok",4.5)?"var(--grn)":ts.cr_med>=THv("cr_warn",3)?"var(--amb)":"var(--red)")+
  kpi("outline (charo taraf)",ts.ring_cr==null?"—":f2(ts.ring_cr)+":1",ts.ring_cr==null?"":ts.ring_cr>=THv("ring_ok",3)?"var(--grn)":"var(--amb)")+
  kpi("chehra frame ka",big?big+"%":"nahi mila",big>=THv("face_ok",8)?"var(--grn)":big>=THv("face_min",1)?"var(--amb)":"var(--red)")+
   kpi("text ka hisala",ts.cov==null?"—":Math.round((ts.cov||0)*100)+"%",ts.cov==null?"":ts.cov>=0.15?"var(--grn)":"var(--amb)")+
   kpi("ek subject? (dominance)",(d.comp||{}).dom==null?"—":Math.round((d.comp||{}).dom*100)+"%",(d.comp||{}).dom>=THv("dom_lo",0.32)?"var(--grn)":"var(--amb)")+
   kpi("subject ka size",(d.comp||{}).subj_pct==null?"—":(d.comp||{}).subj_pct+"%",(d.comp||{}).subj_pct>=THv("subj_lo",7)?"var(--grn)":"var(--amb)")+
   kpi("rule-of-thirds",(d.comp||{}).thirds==null?"—":f2((d.comp||{}).thirds),(d.comp||{}).thirds>=THv("thirds_ok",0.6)?"var(--grn)":"var(--amb)")+
   kpi("thumbnail↔topic match",(d.sem||{}).t_topic==null?"—":f2((d.sem||{}).t_topic),(d.sem||{}).t_topic>=0.15?"var(--grn)":"var(--amb)")+
  kpi("blur",an.blur?"HAAN":"nahi",an.blur?"var(--red)":"var(--grn)")+
  kpi("text ka position",ts.pos||"—")+
  kpi("title dohrata",(d.dup==null?"—":d.dup+"%"),d.dup==null?"":d.dup>25?"var(--red)":"var(--grn)")+'</div>'+
   '<div class="sub">'+calTag()+' · naap: '+esc((d.eng||{}).face||"?")+' + '+esc((d.eng||{}).ocr||"?")+' (server par jo engine sach me chal raha hai, wahi)</div>';
  const xp=d.xplat?('<div class="sub" style="margin:6px 0;padding:8px 10px;background:var(--panel2);border-radius:var(--r1)"><b>'+esc(d.xplat.plat)+' ka thumbnail (yt-dlp se liya)</b> — '+
    (d.xplat.views!=null?fmt(d.xplat.views)+' views':'views: platform ne nahi bataye')+(d.xplat.dur?' · '+d.xplat.dur+'s lambai':'')+(d.xplat.up?' · uploader: '+esc(d.xplat.up):'')+
    '. Ye numbers '+esc(d.xplat.plat)+' ka <b>apna diya hua</b> hai — YouTube ke views se inka tulna mat karo ("view" ki paribhasha aur algorithm dono alag hain). Thumbnail ke naap (text ka size, contrast, chehra, composition) wahi hain jo YouTube par chalte hain — isliye cross-platform tulna sirf un naapon par bharosa karega.</div>'):"";
 const bc=B?('<div class="sec">Is topic ke in '+D.items.length+' videos me aapki jagah <small> — percentile = ye naap in sab me aapse kitne aage hain</small></div><div class="card">'+
   [pchip(B,"text_size","bada text @320",rd(ts.h320)),pchip(B,"text_contrast","text contrast",rd(ts.cr_med)),pchip(B,"words","shabd",ts.n||0),
    pchip(B,"brightness","brightness",rd(an.bright)),pchip(B,"depth","tonal depth",rd(an.dyn)),pchip(B,"clutter","bheed (edges %)",rd(an.clutter)),
    pchip(B,"saturation","range",rd(an.sat)),pchip(B,"face_pct","chehra %",big?Math.round(big):null)].filter(x=>x).join("")+
   '<div class="sub" style="margin-top:6px">inme se <b>'+(B._face_pct_of_all||0)+'%</b> thumbnails par chehra dikhta hai · inka text median: '+(B.words?(nf(B.words.med)+" shabd, "+nf((B.text_size||{}).med)+"px @320, contrast "+nf((B.text_contrast||{}).med)+":1"):"—")+'</div></div>'):
  '<div class="sub">Percentile ke liye pehle <a style="color:var(--acc)" onclick="newScan()">Competitors scan</a> karo — benchmark wahin se banta hai.</div>';
 return kp+xp+styFitHint(d)+
  '<div class="two"><div><div class="lab sub">laal dabbe = OCR jo text padh paya · gulaabi = chehre</div>'+boxes+'</div>'+
  '<div><div class="sec">Rang</div>'+pal+'<div class="sec">Image ke naap</div><div>'+
   chip("brightness",an.bright)+chip("tonal depth",an.dyn)+chip("range (sat)",an.sat)+chip("bheed",an.clutter+"%")+
   chip("sharpness",an.sharp)+(an.blur?chip("BLUR","paisa wapas le jao","var(--red)"):"")+chip("subject",((an.subj||{}).w||0)+"×"+((an.subj||{}).h||0))+
   chip("thirds par",f2((an.comp||{}).thirds))+chip("chroma key",an.chrom_pct+"%")+chip("garam/thande",an.warm+"/"+an.cool)+'</div></div></div>'+
  '<div class="sec">YouTube par aisi dikhegi <small> — asli browse sizes, isi file ko itna chhota karke dikhaya gaya hai</small></div><div class="sizes">'+sizes+'</div>'+
  bc+
  '<div class="sec">Kya theek karna hai</div><div class="card">'+vs+'</div>'+cmp+ownBlk(d)+
'<div id="gemblk"></div>'+
  '<div class="bar"><button class="go" onclick="aiMine()">'+ico("palette",14)+'AI se nayi soch</button><button class="go" onclick="regenMine()">'+ico("refresh",14)+'Behtar banao</button>'+
  '<button class="go" id="gemgo" onclick="gemLook()">'+ico("eye",14)+'Gemini se dekhwa lo</button>'+
  '<button class="go" id="gdpgo" onclick="gdpMine()">'+ico("bars",14)+'Gemini se gehri analysis</button>'+
'<button class="go" onclick="sendTL()">'+ico("ext",14)+'Title Lab me le jao</button></div>'+
  '<div class="sub">"Behtar banao" aapki hi photo rakhta hai — text hatata/bara karta hai, rang aur sharpness sudharta hai, subject bara karta hai — aur phir har version ko dobara napta hai.</div>'}
function cmpHint(ts,an,a){
 if(!a)return "";
 const bad=[];
 if(ts.n===0&&a.with_text_pct>=60)bad.push("in competitors me "+a.with_text_pct+"% thumbnails par text hai — aapke paas bilkul nahi hai");
 if(ts.n>a.med_words+2)bad.push("in ka median "+a.med_words+" shabd hai — aapke "+ts.n+" hai");
 if(ts.h320&&a.med_maxh320&&ts.h320<a.med_maxh320)bad.push("in ka sabse bada text @320px median "+a.med_maxh320+"px hai — aapka "+ts.h320+"px (chhota)");
 if(ts.cr_med!=null&&a.med_cr&&ts.cr_med<a.med_cr)bad.push("in ka median contrast "+a.med_cr+":1 hai — aapka "+ts.cr_med+":1 (text patla/pikhra pad raha hai)");
 if(!bad.length)return '<div class="sec">Competitors se tulna</div><div class="card"><span class="hi">✓ Aapka thumbnail inke pattern se match karta hai (text, size, contrast).</span></div>';
 return '<div class="sec">Competitors se tulna <small> — "'+esc(D.topic)+'" ke '+D.agg.n+' thumbnails se</small></div><div class="card">'+
  bad.map(b=>'<div class="v"><b class="warn">!</b><div>'+esc(b)+'</div></div>').join("")+'</div>'}
function sendTL(){if(!MINE)return toast("pehle thumbnail check karo");go("tl")}

// ---------- title lab ----------
const SIZES=[{w:540,l:2,n:"desktop browse (2 lines)"},{w:300,l:1,n:"mobile app (1 line)"},{w:230,l:2,n:"sidebar (2 lines)"}];
function meas(){const c=document.createElement("canvas");return c.getContext("2d")}
function cut(text,ctx,font,maxw,lines){
 ctx.font=font;
 if(ctx.measureText(text).width<=maxw&&lines>=1)return{text:text,used:1,clip:false};
 const words=text.split(/(\s+)/);const out=[];let cur="";
 for(const w of words){const t=cur+w;
  if(ctx.measureText(t).width<=maxw){cur=t;continue}
  if(cur.trim()){out.push(cur);cur=w.trim()}else{cur=cur+w.trim()}
  if(out.length>=lines){let s=out[lines-1];while(s.length&&ctx.measureText(s+"…").width>maxw)s=s.slice(0,-1);
   out[lines-1]=s.replace(/\s+$/,"")+"…";return{text:out.join("").trim(),used:lines,clip:true}}}
 if(cur.trim()&&out.length<lines)out.push(cur);
 if(out.length>lines){out.length=lines;let s=out[lines-1];while(s.length&&ctx.measureText(s+"…").width>maxw)s=s.slice(0,-1);out[lines-1]=s.replace(/\s+$/,"")+"…";return{text:out.join("").trim(),used:lines,clip:true}}
 return{text:out.join("").trim(),used:out.length,clip:false}}
function tscore(t){
 const v=[];const n=t.length;
 v.push(n>=30&&n<=60?{s:"ok",k:"Length",v:n+" chars",nn:"30–60 ideal hai"}:(n<30?{s:"warn",k:"Length",v:n+" chars",nn:"bahut chhota — kuch nahi batata"}:{s:"warn",k:"Length",v:n+" chars",nn:"lambe ka tail mobile par chup jayega"}));
 if(/^\W*[0-9]/.test(t)||/\b\d+\b/.test(t.slice(0,25)))v.push({s:"ok",k:"Number shuru me",v:"haan",nn:"numbers CTR badhate hain"});
 else v.push({s:"warn",k:"Number",v:"nahi",nn:"7 things / #1 / 2026 jaisa number try karo"});
 if(/[A-Z]{4,}/.test(t))v.push({s:"warn",k:"POORA CAPS word",v:"haan",nn:"ek se zyada mat — spam lagta hai"});
 if(/\?/.test(t))v.push({s:"ok",k:"Sawal",v:"haan",nn:"sawal curiosity kholta hai"});
 if(D&&D.agg.phrases.length){const low=t.toLowerCase();const hit=D.agg.phrases.filter(p=>low.includes(p.p));
  if(hit.length){const early=hit.some(h=>low.indexOf(h.p)<=40);
   v.push(early?{s:"ok",k:"Competitors jaisa shabd",v:hit.map(h=>h.p).join(", "),nn:"ye log yehi likh rahe hain, aur shuru me bhi hai"}
    :{s:"warn",k:"Shabd 40 chars ke baad",v:hit.map(h=>h.p).join(", "),nn:"mobile par sirf pehle ~40 chars dikhte hain — wo shabd aage laao"});}
  else v.push({s:"warn",k:"Competitors jaisa shabd",v:"koi nahi",nn:"upar wale shabdon me se 1–2 daalo — topic pehchane ja sake"});}
 return v}
// ---------- Testing hub: Title Lab aur A/B ek jagah (reference ka testing-hub pattern) ----------
// Dono ka kaam ek hi cheez hai — click test — is liye ek screen, do tabs. Purane
// #/tl aur #/ab links apni jagah chalte hain; hub unhi functions ko #hubc me
// render karta hai, code dobara nahi likha.
let _hubT="title";
function hubv(){
 $("#main").innerHTML='<h2>'+ico("ab",18)+' Testing hub</h2>'+
  '<div class="sub">Title aur thumbnail ka poora trial yahan: Title Lab me title ko YouTube ke asli sizes par test karo, phir A/B variant save karo. Video upload ke baad YouTube khud 24–48 ghante dono ko test karta hai — ye tool record rakhta hai taake farak likh saken.</div>'+
  '<div class="bar"><div class="seg"><button class="'+(_hubT==="title"?"on":"")+'" onclick="tswitch(\'title\')">'+ico("pen",14)+'Title Lab</button>'+
  '<button class="'+(_hubT==="ab"?"on":"")+'" onclick="tswitch(\'ab\')">'+ico("ab",14)+'A/B variants</button></div></div>'+
  '<div id="hubc"></div>';
 (_hubT==="ab"?ab:tl)()}
function tswitch(t){_hubT=t;if(view==="hub"){hubv()}else go(t==="ab"?"ab":"tl")}
async function tl(){
 const _t=RTN;const d=await ensureData();if(_t!==RTN||(view==="hub"&&_hubT!=="title"))return;
 const M=$("#hubc")||$("#main");M.innerHTML='<h2>'+ico("pen",18)+' Title Lab</h2><div class="sub">Title ko YouTube ki tarah truncate karke dikhata hai. Font approximate hai (Roboto/Arial) — asli YouTube se thoda farq ho sakta hai, par cutoff ka idea sahi milta hai.</div>'+
 '<textarea id="ti" placeholder="Apna title yahan likho…">'+esc(TITLE)+'</textarea>'+
 '<div class="bar"><button class="go" onclick="go2()">Preview banao</button><button class="sm" onclick="saveAB()">'+ico("ab",14)+'A/B me save karo</button>'+
 (MINE?'<span class="sub">thumbnail: '+esc(MINE.path)+'</span>':'<span class="sub">thumbnail ke liye pehle "Meri Thumbnail" tab se check karo</span>')+'</div>'+
 '<div id="tr"></div>'}
function go2(){TITLE=$("#ti").value;const ctx=meas();
 const rows=SIZES.map(s=>{const r=cut(TITLE,ctx,"500 15.5px Roboto,Segoe UI,Arial,sans-serif",s.w,s.l);
  const th=MINE?'<img src="'+imgu(MINE.path)+'" style="width:'+Math.round(s.w*0.6)+'px;border-radius:var(--r2)">':'<div style="width:'+Math.round(s.w*0.6)+'px;height:'+Math.round(s.w*0.34)+'px;background:var(--card2);border-radius:var(--r2)"></div>';
  const comp=D?D.items.slice(0,2).map(it=>'<div class="yt"><img src="'+imgu(it.thumb)+'" style="width:'+Math.round(s.w*0.6)+'px;border-radius:var(--r2)"><div><div class="t">'+esc(cut(it.title,ctx,"500 15.5px Roboto,Segoe UI,Arial,sans-serif",s.w,s.l).text)+'</div><div class="m">'+esc(it.channel.slice(0,24))+' · '+fmt(it.views)+' views</div></div></div>').join(""):"";
  return '<div class="sec">'+esc(s.n)+' — '+s.w+'px, '+s.l+' line'+(s.l>1?"s":"")+'</div>'+
   '<div class="yt">'+th+'<div><div class="t">'+esc(r.text)+(r.clip?' <span class="lo">[KAT GYA]</span>':'')+'</div><div class="m">'+TITLE.length+' chars likhe · '+r.used+' line use hui</div></div></div>'+
   (comp?'<div class="sub" style="margin-top:6px"> isi size par competitors (asli titles, asli truncation):</div>'+comp:'')} ).join("");
 const sv=tscore(TITLE).map(v=>'<div class="v"><b class="'+v.s+'">'+(v.s==="ok"?"✓":v.s==="warn"?"!":"✗")+'</b><div>'+esc(v.k)+'</div><div class="n">'+esc(v.v)+' — '+esc(v.nn)+'</div></div>').join("");
 const fit=SIZES.map(s=>{const r=cut(TITLE,ctx,"500 15.5px Roboto,Segoe UI,Arial,sans-serif",s.w,s.l);
  return '<span class="chip">'+esc(s.n)+' me <b>'+(r.clip?"sirf "+r.text.length:"poora")+'</b> chars dikhega</span>'}).join("");
 $("#tr").innerHTML='<div class="sec">Kitna dikhega</div><div class="card">'+fit+'</div>'+
  '<div class="sec">Meri title aisi dikhegi</div>'+rows+'<div class="sec">Title ki jaanch</div><div class="card">'+sv+'</div>'}

// ---------- A/B ----------
function csv(){window.open("/api/variants.csv")}
async function ab(){const _t=RTN;if(!$("#hubc"))spin();const d=await j("/api/variants");if(_t!==RTN||(view==="hub"&&_hubT!=="ab"))return;
 const H=$("#hubc"),M=H||$("#main");M.innerHTML=(H?'':'<h2>'+ico("ab",18)+' A/B Variants</h2><div class="sub">Do title+thumbnail ke jode save karo. Video upload ke baad 24–48 ghante me dekhna kaunsa zyada click kha raha hai — YouTube khud "test and compare" karta hai (Studio me).</div>')+
 '<div class="bar"><button class="go" onclick="saveAB()">+ abhi wali save karo</button><button class="sm" onclick="csv()">'+ico("dl",14)+'CSV</button></div>'+
 (d.variants.length?'<table><thead><tr><th scope="col">banaya</th><th scope="col">topic</th><th scope="col">A title</th><th scope="col">A thumb</th><th scope="col">B title</th><th scope="col">B thumb</th><th scope="col">note</th><th scope="col" aria-label="kaam ke button"></th></tr></thead><tbody>'+
  d.variants.map((v,i)=>'<tr><td>'+esc(v.ts)+'</td><td>'+esc(v.topic||"")+'</td><td>'+esc(v.ta||"")+'</td><td>'+(v.ia?'<img loading="lazy" alt="" src="'+imgu(v.ia)+'" style="width:120px;border-radius:var(--r1)">':"")+'</td><td>'+esc(v.tb||"")+'</td><td>'+(v.ib?'<img loading="lazy" alt="" src="'+imgu(v.ib)+'" style="width:120px;border-radius:var(--r1)">':"")+'</td><td class="sub">'+esc(v.note||"")+'</td><td><button class="sm ic" title="ye variant hataao" aria-label="ye variant hataao" onclick="delAB('+i+')">'+ico("trash",15)+'</button></td></tr>').join("")+'</tbody></table>':
  esCard({i:"ab",t:"Abhi koi A/B variant save nahi hui",
     p:"Title Lab me title likho, <b>Meri Thumbnail</b> se thumbnail check karke uska record lo, phir <b>A/B me save karo</b>. Video upload ke baad YouTube khud 24–48 ghante dono ko compare karta hai — ye tool sirf record rakhta hai taake aap apna farak likh saken.",
     b:'<div class="bar"><button class="go" onclick="tswitch(\'title\')">Title Lab kholo</button><button class="sm" onclick="saveAB()">abhi wali save karo</button></div>'})+
    '<div class="sub">Variants <code>thumb_output/variants.json</code> me rehti hain — tool band karne par bhi nahi jaatin.</div>')}
async function delAB(i){const d=await j("/api/variants");const v=d.variants[i];try{await fetch("/api/variant_del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:v.id})});toast("variant hata di gayi","ok")}catch(e){failToast(e,"variant hatana")}if(view==="ab"||(view==="hub"&&_hubT==="ab"))ab()}
async function saveAB(){
 if(!TITLE)return toast("Title Lab me title likho pehle");
 const note=prompt("Note (kya test kar rahe ho):","")||"";
 await fetch("/api/variant",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({topic:TOPIC,ta:TITLE,ia:ABTH||(MINE?MINE.path:""),note:note})});
 toast("save ho gayi");if(view==="hub"){_hubT="ab";hubv()}else ab()}

// ---------- POORA CHANNEL (naam / @handle / channel id / link se) ----------
// Channel ka scan bhi ek normal scan hi hai (scans/<id>.json, kind:"channel") — isliye
// Deep Analysis, ideas, har video ka "poora analysis" aur CSV/JSON export channel par bhi
// bilkul waise hi chalte hain jaise topic scan par. Ye view sirf wo dikhata hai jo sirf
// channel ka hai: poori listing, shorts vs longs, upload ka routine, niche, aur kamai ka
// andaza. Har cheez ke saath wo baat bhi likhi hai jo data support KARTA hai aur kaun si
// nahi karta — khamosh andaza nahi jhuta jaata.
let CQ="",CHC=null,CHJ=null,CMP=null,RPMX=null;
const usd=v=>v==null?"—":"$"+(Math.abs(v)>=1e6?(v/1e6).toFixed(2)+"M":Math.abs(v)>=1e3?(v/1e3).toFixed(1)+"K":f2(v));
const capn=(v,c)=>v==null?"—":(fmt(v)+((c&&v>=(c||0))?"+":""));
function chPick(u){const e=$("#cq");if(e)e.value=u;goChan()}
async function goChan(){
  const q=(($("#cq")||{}).value||CQ||"").trim();
  if(!q)return toast("Type a channel name, @handle or link");
  CQ=q;CHC=null;
  const out=$("#chout");if(out)out.innerHTML=skelKpi(6)+skelTable(6)+'<div>'+skelLines(2,"finding the channel and counting its listing…")+'</div>';
  let r;try{r=await j("/api/chscan?q="+encodeURIComponent(q))}
  catch(e){if(out)out.innerHTML='<div class="err">Something went wrong: '+esc(String(e))+'</div>';return}
  if(r.err){if(out)out.innerHTML='<div class="err">'+esc(r.err)+'</div>';return}
  if(r.need){CHC=r;if(out)out.innerHTML="";return chanv()}
  CHJ={job:r.job,sid:r.id};return chanv()}
async function chPoll(){
  for(let k=0;k<900;k++){
    let p;try{p=await j("/api/progress?id="+CHJ.job)}catch(e){break}
    const el=$("#chp");
    if(el){const pc=Math.round(100*(p.done||0)/Math.max(1,p.total||1));
      el.innerHTML='<div class="sub"><b>'+esc(p.current||"…")+'</b> · '+(p.done||0)+'/'+(p.total||0)+'</div>'+
        '<div class="pbar"><i style="width:'+pc+'%"></i></div>'}
    if(p.state==="done"){const sid=CHJ.sid;CHJ=null;cur=sid;D=null;IDEAS=null;await boot();return}
    if(p.state==="error"){CHJ=null;const o=$("#chout");
      if(o)o.innerHTML='<div class="err">Channel scan failed: '+esc(p.error||"?")+'</div>'+
        (p.tb?'<div class="sub"><code>'+esc(p.tb)+'</code></div>':"");return}
    await new Promise(r=>setTimeout(r,1500));}}
function chMeTable(){
  const mine=SCANS.filter(s=>s.kind==="channel");
  if(!mine.length)return "";
  return '<div class="card"><h3>Channels already opened ('+mine.length+')</h3>'+
   '<table><thead><tr><th scope="col">Channel</th><th scope="col" class="num">Subscribers</th><th scope="col" class="num">Counted videos</th>'+
   '<th scope="col" class="num">Analyzed</th><th scope="col">When opened</th><th scope="col"></th></tr></thead><tbody>'+
    mine.map(s=>'<tr><td><b>'+esc((s.ch||{}).name||s.topic)+'</b> '+esc((s.ch||{}).handle||"")+'</td>'+
      '<td class="num">'+fmt(s.ch.subs||0)+'</td><td class="num">'+
      ((s.ch.tot_videos||0)>=400?(s.ch.tot_videos+"+"):(s.ch.tot_videos||0))+
      ' + '+((s.ch.tot_shorts||0))+' shorts</td><td class="num">'+s.kept+'</td>'+
      '<td class="sub">'+Math.round(s.age/3600)+' hours ago</td>'+
     '<td><button class="sm" data-s="'+s.id+'" onclick="openChan(this.dataset.s)">Open</button></td></tr>').join("")+
   '</tbody></table><div class="sub">Every channel scan is its own file — the <b>Competitors</b> view has the full thumbnail/OCR analysis of every video inside it, <b>Deep analysis</b> has the pattern across that channel’s <b>measured</b> videos (a new scan measures its whole counted listing, not a sample — if a row here shows fewer measured than counted, the rest is still openable with “Poora channel naap lo”), and the <b>Winning topics</b> view lists that channel’s winning topics.</div></div>'}
function openChan(id){cur=id;D=null;IDEAS=null;go("ch")}
function chSearchCard(){
  return '<div class="card"><h3>Find or open a channel</h3><div class="bar">'+
   '<input type="text" id="cq" placeholder="name, @handle, UC… id, or a youtube.com/@handle link" style="min-width:340px" value="'+esc(CQ)+'" onkeydown="if(event.key===\'Enter\')goChan()">'+
   '<button class="go" onclick="goChan()">'+ico("search",14)+'Open channel</button>'+
   '<button class="sm" onclick="chFindOnly()">'+ico("search",14)+'Search only</button></div>'+
    '<div class="sub">Up to <b>50 channels</b> by name — they come from YouTube’s own <b>Channel</b> filter; the name, @handle, subscriber count and verified badge are YouTube’s data, not written by this tool. Opening a channel counts its <b>/videos</b> and <b>/shorts</b> listings (up to <b>400</b>; past that a <b>+</b> appears, because counting stops there), and then <b>measures every counted video</b> — longs and shorts alike — with its <b>real</b> listing fields (tags, description, chapters, likes, comments, category) plus thumbnail measurements. A full channel takes time; the progress bar streams and each measured video lands in the table as it finishes — nothing is skipped or sampled.</div>'+
   '<div class="sub"><b>Five things that are not in YouTube’s public data</b> — so this tool will not invent them: (1) the channel’s <b>joined</b> date, (2) the channel’s <b>total views</b> (only the sum of counted videos is available), (3) whether it is <b>monetized</b>, (4) <b>RPM/CPM</b>, (5) watch time. Instead this tool shows what is actually there: the subscriber 1000+ condition is visible, watch-hours are counted as an <b>upper bound</b>, and earnings are given as a <b>range</b> — until you enter your own Studio RPM.</div></div>'}
async function chFindOnly(){
  const q=(($("#cq")||{}).value||CQ||"").trim();if(!q)return toast("kuch likho");CQ=q;
  const el=$("#chout");if(el)el.innerHTML=skelTable(8)+'<div>'+skelLines(2,"50 channels dhoondhe ja rahe hain…")+'</div>';
  let d;try{d=await j("/api/chsearch?q="+encodeURIComponent(q))}catch(e){return}
  CHC={q:q,cands:d.chans||[],note:"These are results from YouTube’s Channel filter — opening one counts its listing"};
  if(el)el.innerHTML="";chanv()}
function chCands(){
  if(!CHC)return "";
  const mine={};SCANS.forEach(s=>{if(s.kind==="channel"&&s.ch)mine[s.ch.id]=s.id});
  return '<div class="card"><h3>'+((CHC.cands||[]).length)+' channels mile "'+esc(CHC.q)+'" par</h3>'+
    (CHC.note?'<div class="sub">'+esc(CHC.note)+'</div>':"")+
    '<table><thead><tr><th scope="col">Channel</th><th scope="col" class="num">Subscriber</th><th scope="col">handle</th><th scope="col"></th></tr></thead><tbody>'+
    (CHC.cands||[]).map(c=>'<tr><td><b>'+esc(c.name)+'</b>'+(c.ver?" "+ico("check",13):"")+
      (c.desc?'<div class="sub">'+esc(c.desc.slice(0,110))+'</div>':"")+'</td>'+
      '<td class="num">'+fmt(c.subs)+'</td><td class="sub">'+esc(c.handle||"—")+'</td>'+
      '<td>'+(mine[c.id]?'<button class="sm" data-s="'+mine[c.id]+'" onclick="openChan(this.dataset.s)">khula hua hai — dekho</button>'
        :'<button class="sm go" data-u="'+esc(c.url)+'" onclick="chPick(this.dataset.u)">kholo</button>')+'</td></tr>').join("")+
    '</tbody></table><div class="sub">Subscriber = YouTube ka <code>channel_follower_count</code> (live). Total videos yahan NAHI dikhte — wo channel khulte waqt listing se gine jaate hain.</div></div>'}
// ---------- channel ka dashboard ----------
// ---------- Studio jaisa Content table: videos ki listing ----------
// YouTube Studio ke "Content" table ka pattern: upar type/date/search ke chips, columns ke
// sir par click karke sort, aur row par click se usi row ke neeche detail. Data wahin se aata
// hai jo /api/data deta hai — is table me kuch bhi naya nahi gina jaata. Channel aur topic,
// dono ki listing isi ek component se banti hai (do alag dikhne wale tables nahi).
let STF={q:"",kind:"all",win:"all",sort:"views",dir:-1,open:"",nap:"all",pg:0,ps:25,day:null,hr:null},
    CMPV="cards",CMV="ov",CMPM="iss";
// WALK = channel ki poori gini hui listing (/api/chwalk se), CHX = chal raha naap job.
// Dono scan se bandhi hain; scan badalne par phir se li jaati hain.
let WALK=null,CHX=null,CHXP={},TSJ=null,SPJ=null;
// Cards mode ka page. Table mode pehle se page by page chalta tha; 211 cards ek
// saath banne se DOM bhaari hota tha (napa: 849 KB ka HTML ek hi saath).
let CPG=0,CPS=24,CMPF="all",CMPFID="";
const STM=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const STC=[["views","Views"],["likes","Likes"],["cmts","Comments"],["date","Date"],["dur","Length"],
 ["ls","Listing"],["score","Thumbnail"],["sp","Ads"]];
function stDur(x){x=x||0;const h=Math.floor(x/3600),m=Math.floor(x%3600/60),c=x%60;
 return (h?h+":":"")+String(m).padStart(h?2:1,"0")+":"+String(c).padStart(2,"0")}
// SponsorBlock ka data — community marks, is liye "na mila" aur "zero" alat hain:
// jo video API me aayi hi nahi us par kuch nahi dikhega, sirf "—" (mark nahi).
function spSec(id){const s=(D&&D.spon||{})[id];return s?s.sec:null}
function spCell(id,dur){const s=(D&&D.spon||{})[id];
 if(!s)return '<span class="d" title="SponsorBlock par is video ka koi mark nahi — iska matlab ads ka na hona zaroori nahi">—</span>';
 return '<b>'+stDur(s.sec)+'</b>'+(dur?'<span class="d">'+Math.round(s.sec*100/dur)+'%</span>':"")}
function stDate(u){if(!u)return "—";const p=String(u).split("-");
 return p.length<3?String(u):(+p[2])+" "+(STM[+p[1]-1]||"?")+" "+p[0]}
function stAge(u){if(!u)return null;const t=Date.parse(u+"T00:00:00");return isNaN(t)?null:Math.floor((Date.now()-t)/864e5)}
function stKey(it,k){
 if(k==="vpd")return vpd(it);if(k==="date")return it.upload||null;if(k==="title")return (it.title||"").toLowerCase();
 if(k==="dur")return it.dur||0;if(k==="likes")return it.likes||0;if(k==="cmts")return it.cmts||0;
 if(k==="ls")return it.ls==null?null:it.ls;if(k==="score")return it.score==null?null:it.score;
 return it.views||0}
// Ek hi table do qisam ki rows rakhta hai: j par poora naap hua (it) aur jo sirf
// gini gayi (u). Sort me bas wahi jaata hai jo us row ke paas sach me hai.
function rwKey(r,k){
 if(r.u){const w=r.u;
  if(k==="date")return w.ts?new Date(w.ts*1000).toISOString().slice(0,10):null;
  if(k==="title")return (w.t||"").toLowerCase();
  if(k==="dur")return w.d||0;
  if(k==="views")return w.w==null?null:w.w;
  if(k==="sp")return spSec(w.id);
  return null}
 return stKey(r.it,k)}
function walkRows(){
 // /api/chwalk se aayi listing — sirf un rows ko deti hai jo ab tak naap se bahar hain
 // (jo id items me hai wo dobara is table me nahi judti, warna ek video do bar dikhegi).
 if(!WALK||WALK.id!==cur)return [];
 const have={};(D.items||[]).forEach(it=>{have[it.id]=1});
 return (WALK.rows||[]).filter(w=>!have[w.id])}
function stRows(){
 const q=STF.q.trim().toLowerCase(),w=STF.win==="all"?0:parseInt(STF.win,10),out=[];
 (D.items||[]).forEach((it,i)=>{
  if(STF.nap==="un")return;
  if(STF.kind==="long"&&it.sh)return;
  if(STF.kind==="short"&&!it.sh)return;
  if(w){const a=stAge(it.upload);if(a==null||a>w)return}
  if(q){const hay=((it.title||"")+" "+(it.tags||[]).join(" ")).toLowerCase();if(hay.indexOf(q)<0)return}
  if(STF.day!=null||STF.hr!=null){if(!stTimeOk(it))return}
  out.push({it:it,i:i})});
 if(STF.nap!=="meas")walkRows().forEach(u=>{
  if(STF.kind==="long"&&u.s)return;
  if(STF.kind==="short"&&!u.s)return;
  if(w){const a=u.ts?Math.floor((Date.now()-u.ts*1000)/864e5):null;if(a==null||a>w)return}
  if(q&&(u.t||"").toLowerCase().indexOf(q)<0)return;
  // Bina naap ke video ka chhapne ka waqt maloom hi nahi hota (listing me wo field
  // hi nahi aata), is liye waqt ka filter lagte hi ye rows khud-ba-khud bahar ho
  // jaati hain — ye chhupana nahi, na-apne ki had batana hai.
  if(STF.day!=null||STF.hr!=null)return;
  out.push({u:u})});
 const k=STF.sort,dr=STF.dir;
 out.sort((A,B)=>{const a=rwKey(A,k),b=rwKey(B,k);
  if(a==null&&b==null)return 0;if(a==null)return 1;if(b==null)return -1;   // jinke paas wo value nahi wo hamesha neeche
  return (a<b?-1:a>b?1:0)*dr});
 return out}
function stBlock(){return stBar()}
function stBar(){
 const its=D.items||[],nl=its.filter(i=>!i.sh).length,ns=its.filter(i=>i.sh).length;
 const un=walkRows(),unL=un.filter(u=>!u.s).length,unS=un.filter(u=>u.s).length;
 const rows=stRows(),tot=its.length+un.length;
 let h='<div class="st"><div class="st-bar">';
 if(ns||unS)h+='<div class="seg">'+[["all","All ("+tot+")"],["long","Longs ("+(nl+unL)+")"],["short","Shorts ("+(ns+unS)+")"]]
   .map(o=>'<button id="stk-'+o[0]+'" class="'+(STF.kind===o[0]?"on":"")+'" onclick="stKind(\''+o[0]+'\')">'+o[1]+'</button>').join("")+'</div>';
 else h+='<span class="pill" style="cursor:default">Videos <b>'+tot+'</b></span>';
 // Table me do qisam ki rows hain: j par poora naap hua, aur jo sirf listing se gin
 // kar aayi. Chhupaya kuch nahi jaata — user khud chunta hai kis ko dekhna hai.
 if(un.length)h+='<select class="pill" onchange="stSet(\'nap\',this.value)" title="fully measured, or only counted from the listing">'+[["all","Measurement: all ("+tot+")"],["meas","measured only ("+its.length+")"],["un","unmeasured only ("+un.length+")"]].map(o=>'<option value="'+o[0]+'"'+(STF.nap===o[0]?" selected":"")+'>'+o[1]+'</option>').join("")+'</select>';
 h+='<select class="pill" onchange="stSet(\'win\',this.value)" title="only videos uploaded within this window">'+
   [["all","Any time"],["7","Last 7 days"],["30","Last 30 days"],["90","Last 90 days"],["365","Last 12 months"]]
   .map(o=>'<option value="'+o[0]+'"'+(STF.win===o[0]?" selected":"")+'>'+o[1]+'</option>').join("")+'</select>';
 h+='<input class="stq" placeholder="search titles or tags…" value="'+esc(STF.q)+'" oninput="stSet(\'q\',this.value)">';
 h+='<span class="sp"></span><span class="cnt" id="stcnt">'+rows.length+" / "+tot+" shown</span></div>"
  +'<div id="stbox">'+stAct()+stSponBar()+stTimePanel(rows)+stTbl(stPage(rows))+stPg(rows)+stFoot()+'</div></div>';
 return h}
// Studio ki tarah page by page: 200 rows ek saath rakhne se browser atak jaata hai,
// aur insaan ko apni jagah khud dhoondhni padti hai. Slice sirf dikhane ka hai —
// filter, sorting aur ginti poori listing par hoti hai, is liye number sach rahte hain.
function stPage(rows){if(STF.ps>=rows.length)return rows;
const p=Math.max(0,Math.min(STF.pg,Math.floor((rows.length-1)/STF.ps)));STF.pg=p;
return rows.slice(p*STF.ps,p*STF.ps+STF.ps)}
function stPg(rows){const n=rows.length,ps=STF.ps;
if(n<=ps)return "";
const np=Math.ceil(n/ps),p=Math.max(0,Math.min(STF.pg,np-1));
const bt=(l,g,dis)=>'<button class="sm"'+(dis?' disabled':"")+' onclick="'+g+'">'+l+'</button>';
return '<div class="stpg">'+bt(ico("back",13)+" Previous","stPgGo(-1)",p<=0)+
 '<span class="pgi">page <b>'+(p+1)+'</b> / '+np+' &nbsp; '+(p*ps+1)+'-'+Math.min(n,(p+1)*ps)+' of '+n+'</span>'+
 '<select class="pill" onchange="stPs(this.value)" title="rows per page">'+[25,50,100].map(v=>
  '<option value="'+v+'"'+(ps===v?" selected":"")+'>'+v+' per page</option>').join("")+
 '<option value="9999">all rows on one page</option></select>'+
 bt("Next "+ico("down",13),"stPgGo(1)",p>=np-1)+'</div>'}
function stPgGo(d){const n=stRows().length,np=Math.max(1,Math.ceil(n/STF.ps));
STF.pg=Math.max(0,Math.min(np-1,STF.pg+d));stRender();
const e=document.querySelector(".st");if(e)e.scrollIntoView({block:"start",behavior:"smooth"})}
function stPs(v){STF.ps=Math.min(9999,parseInt(v,10)||25);STF.pg=0;stRender()}
async function walkGet(sid,force){
 // Channel ki poori gini hui listing. Server ye ek baar yt-dlp se leta hai aur 24
 // ghante file me rakhta hai; client me bhi sirf current scan tak pakadi rehti hai.
 if(!sid)return null;
 if(WALK&&WALK.id===sid&&!force)return WALK;
 let r;try{r=await j("/api/chwalk?id="+sid+(force?"&force=1":""))}catch(e){return null}
 if(!r||r.err){WALK={id:sid,rows:[],err:(r&&r.err)||""};return WALK}
 WALK={id:sid,rows:r.rows||[],cap:r.cap||400,got:r.got||"",terr:r.terr||"",n_long:r.n_long||0,n_short:r.n_short||0};
 return WALK}
async function chMore(n,ids){
 // Jo videos abhi sirf gini gayi hain un par wahi naap chalao (channel scan wala
 // engine), phir poora view taaza — counts, table aur dashboard ek hi sach par rahein.
 if(!cur)return toast("Open a channel first");
 let r;try{r=await j("/api/chmore?id="+cur+"&n="+n+(ids?("&ids="+encodeURIComponent(ids)):""))}catch(e){return failToast(e,"starting the measurement")}
 if(!r||r.err)return toast((r&&r.err)||"the measurement did not start");
 CHX={id:cur,job:r.job};CHXP={done:0,total:(r.n||0)*2,cur:"starting…",eta:r.eta||null};
 stRender();let last=-1;
 for(let k=0;k<3000;k++){
  await new Promise(z=>setTimeout(z,900));
  let p;try{p=await j("/api/progress?id="+r.job)}catch(e){break}
  if(!p||p.state==="gone")break;
  CHXP={done:p.done||0,total:p.total||0,cur:p.current||"…",eta:r.eta||null};
  const el=document.getElementById("chxp");if(el)el.outerHTML=progBlock();
  // Naya natija juda hai to table bhi taaza — lekin sirf tab jab koi row khula
  // nahi hai aur koi box type ho raha hai, warna user ki apni jagah hilegi.
  if((p.done||0)>last&&!STF.open){last=p.done;
   const ae=document.activeElement||{};
   if(!/^(INPUT|SELECT|TEXTAREA)$/.test(ae.tagName||"")){
    try{const nd=await j("/api/data?id="+cur);if(nd&&nd.items){D=nd;stRender()}}catch(e){}}}
  if(p.state==="done")break;
  if(p.state==="error"){CHX=null;CHXP={};toast("The measurement stopped: "+(p.error||"?"));await boot();return}}
 CHX=null;CHXP={};D=null;WALK=null;await boot();
 toast("poora channel naap liya — ab har video ka data table me hai")}
function chOne(id){chMore(1,id)}
function stAct(){
 // Sirf-gini-gayi videos par naap chalane ka button. Wahi engine chalta hai jo channel
 // scan chalata tha, bas chuninda videos par — isliye kharcha control me rehta hai.
 if(!D||D.kind!=="channel")return "";
 if(CHX&&CHX.id===cur)return progBlock();
 const un=walkRows().length;
 if(!un)return "";
 // Ek bara button sab se zaroori kaam ke liye: poore channel ka naap. Chhota option
 // is liye rakha hai ke pehle bees par kharcha samajh aa jaye.
 return '<div class="stact">'+ico("spark",14)+'<div style="flex:1"><b>'+un+'</b> videos sirf gini gayi hain '+
  '(in par abhi naap nahi hua, is liye Views/tags/thumbnail khali hai).'+
  '<div class="sub">Ek click me poora channel: har video par views, asli tags/description aur thumbnail/OCR. '+
  'Andazan '+measEta(un)+' — aur jo khep naap ho jaati hai wo foran table me aa jaati hai, '+
  'poore job ka intezaar nahi karna padta.</div></div>'+
  '<button class="go" onclick="chMore('+un+')">'+ico("deep",15)+" Poora channel naap lo ("+un+')</button>'+
  '<button class="sm" onclick="chMore(20)">pehle 20</button></div>'}
// Chalti naap ka block — stAct aur progress-loop dono isi ko banate hain, taake
// table taaza hone par bhi progress bar gayab na ho.
function progBlock(){const pc=Math.round(100*(CHXP.done||0)/Math.max(1,CHXP.total||1));
return '<div class="stact" id="chxp">'+ico("clock",14)+'<div style="flex:1">'+
 '<b>Poore channel ka naap chal raha hai — '+(CHXP.done||0)+'/'+(CHXP.total||0)+'</b>'+
 '<div class="sub">do charhan: pehle YouTube se metadata, phir thumbnail/OCR/chehra. '+
 esc(CHXP.cur||"shuru ho raha hai…")+
 (CHXP.eta?' · andazan '+(CHXP.eta[0]/60).toFixed(1)+'-'+(CHXP.eta[1]/60).toFixed(1)+' minute':"")+
 ' · jo video naap ho gayi wo foran table me hai</div>'+
 '<div class="pbar"><i style="width:'+pc+'%"></i></div></div>'+
 '<button class="sm" onclick="stRefresh()">'+ico("refresh",13)+" table taaza karo</button></div>"}
// Server ke meas_eta ka hi number — do jagah formula dobara nahi likha gaya.
function measEta(n){const e=((SYS||{}).eta)||[0.45,1.6];
const f=x=>x<60?Math.round(x)+" second":(x/60).toFixed(1)+" minute";
return f(e[0]*n)+" to "+f(e[1]*n)}
function stRefresh(){if(!cur)return;j("/api/data?id="+cur).then(d=>{if(d&&d.items){D=d;stRender();
toast("table taaza kar di")}}).catch(e=>failToast(e,"table taaza karna"))}
// SponsorBlock ki peshkash/chalti-manjheel ka block. Data community ka hai — is liye
// poora saaf likha hai ke kya mila aur kya nahi mil sakta.
function stSponBar(){
 if(!D||D.kind!=="channel")return "";
 if(SPJ&&SPJ.id===cur){const pc=Math.round(100*(SPJ.done||0)/Math.max(1,SPJ.total||1));
  return '<div class="stact" id="spbar">'+ico("clock",14)+'<div style="flex:1">'+
   '<b>SponsorBlock ke marks aa rahe hain — '+(SPJ.done||0)+'/'+(SPJ.total||0)+'</b>'+
   '<div class="sub">Ek video ka ek request, aur do requests ke beech thahao — ye logon ka banaya server hai, bojh daalna nahi. Jo marks aa chuke hain wo foran table me hain.</div>'+
   '<div class="pbar"><i style="width:'+pc+'%"></i></div></div></div>'}
 const n=Object.keys((D.spon||{})).length;
 const c=D.cst||{};const tot=(c.tot_videos||0)+(c.tot_shorts||0);
 const est=tot>40?" Andazan "+Math.max(1,Math.round(tot*0.8/60))+"+ minute.":"";
 return '<div class="stact" id="spbar">'+ico("bars",14)+'<div style="flex:1"><b>Ads ka bojh — SponsorBlock</b>'+
  '<div class="sub">'+(n?('Is scan ki <b>'+n+'</b> videos par community marks mile — "Ads" column aur row-detail me hain. Data logon ne bheja hai, is liye jitni videos par kisi ne mark nahi kiya un par "—" rahega: iska matlab ads ka na hona zaroori nahi.')
   :'Ek click me SponsorBlock se har video ke sponsor/self-promo marks maange jaate hain — free, community data. Jis video par mark nahi hoga us par "—" rahega, jhooth nahi. YouTube ads ki asli gin-ti public nahi karta, ye uska sabse qareebi saboot hai — naap nahi.')+est+
  '</div></div>'+
  '<button class="go" onclick="sponGo()">'+ico("deep",15)+(n?"Marks dobara taaza karo":"SponsorBlock se naap lo")+'</button></div>'}
async function sponGo(){
 if(!cur||SPJ)return;
 let r;try{r=await j("/api/spon?id="+cur)}catch(e){return failToast(e,"starting the SponsorBlock pass")}
 if(r.err)return toast(r.err);
 SPJ={id:cur,job:r.job,done:0,total:r.n||0};spPaint();
 for(let k=0;k<1800;k++){await new Promise(z=>setTimeout(z,1000));
  let p;try{p=await j("/api/progress?id="+r.job)}catch(e){break}
  if(!p||p.state==="gone")break;
  SPJ.done=p.done||0;SPJ.total=p.total||SPJ.total;spPaint();
  if(p.state==="done"||p.state==="error"){SPJ=null;
   if(p.state==="error")toast("SponsorBlock ruk gaya: "+(p.error||"?"));
   else{try{const nd=await j("/api/data?id="+cur);if(nd&&nd.items){D=nd;stRender()}}catch(e){}
    toast(p.current||"SponsorBlock ke marks aa gaye")}
   return}}
 SPJ=null}
function spPaint(){const el=document.getElementById("spbar");if(el)el.outerHTML=stSponBar();else stRender()}
// Screen reader ko batana ki kaunsa column sort hai aur kis disha me — colour aur
// teer sirf aankh ke liye hote hain.
function srtA(k){return STF.sort===k?' aria-sort="'+(STF.dir<0?"descending":"ascending")+'"':""}
// Upload ka waqt — kis din, kis ghari, aur hafte me kitni videos chhaapi jaati hain.
// Sirf un videos par banta hai jin ki APNI metadata me chhapne ka poora waqt mila ho
// (yt-dlp ka `timestamp`). Wo channel ki listing me KABHI nahi aata — na /videos tab
// par, na uploads playlist me (25 Oct ko dono test kar dekhe: har jagah NA aaya). Is
// liye jis video ka waqt nahi mila us par panel me saaf likha hai, aur ek button se
// baqi bharwa sakte ho: us me sirf metadata dobara padhi jaati hai, thumbnail/OCR/
// score dobara nahi chalta. Din ki gin-ti har tareekh se hoti hai — us me waqt ki
// zaroorat nahi, is liye wo poori channel par kaam karti hai.
const STDD=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
function stHH(n){return (n<10?"0":"")+n}
function stTimeOk(it){if(!it||!it.pubts)return false;const d=new Date(it.pubts*1000);
 if(STF.day!=null&&((d.getDay()+6)%7)!==STF.day)return false;
 if(STF.hr!=null&&d.getHours()!==STF.hr)return false;return true}
function stTimeGo(d,h){if(STF.day===d&&STF.hr===h){STF.day=null;STF.hr=null}
 else{STF.day=d;STF.hr=h}
 STF.pg=0;stRender()}
function stTimeClr(){STF.day=null;STF.hr=null;STF.pg=0;stRender()}
function stTimePanel(rows){
 const all=D.items||[];
 const its=all.filter(it=>!it.sh);
 if(!its.length)return "";
 // Ghari ka naqsha sirf long videos par: shorts chhapne ka waqt aksar us din ki
 // kisi aur video ke saath same hota hai aur us se "best time" ka jawaab bigad
 // jaata hai. Hafte aur gap ka hisaab saari uploads par hota hai (wo cadence hai).
 const wt=its.filter(it=>it.pubts),noTs=its.length-wt.length;
 const noAll=all.filter(it=>!it.pubts).length;
 const hm=new Array(168).fill(0);
 wt.forEach(it=>{const d=new Date(it.pubts*1000);hm[((d.getDay()+6)%7)*24+d.getHours()]++});
 let mx=1;hm.forEach(v=>{if(v>mx)mx=v});
 const dcnt=new Array(7).fill(0),hcnt=new Array(24).fill(0);
 hm.forEach((v,i)=>{dcnt[(i/24)|0]+=v;hcnt[i%24]+=v});
 const top=a=>{let b=[0,0];a.forEach((v,i)=>{if(v>b[0])b=[v,i]});return b};
 const bd=top(dcnt),bh=top(hcnt);
 const D8=864e5,WK=7*D8;
 const dts=all.map(it=>it.upload?Date.parse(it.upload+"T00:00:00"):NaN).filter(t=>!isNaN(t)).sort((a,b)=>a-b);
 const mon=t=>t-((new Date(t).getDay()+6)%7)*D8;
 const wk={};dts.forEach(t=>{const k=mon(t);wk[k]=(wk[k]||0)+1});
 const wks=Object.keys(wk).map(Number).sort((a,b)=>a-b);
 let gap=0,gat=0;
 for(let i=1;i<dts.length;i++){const g=dts[i]-dts[i-1];if(g>gap){gap=g;gat=dts[i-1]}}
 const last=dts.length?dts[dts.length-1]:0;
 const since=last?Math.floor((Date.now()-last)/D8):null;
 const span=wks.length?Math.round((wks[wks.length-1]-wks[0])/WK)+1:0;
 const perW=span>0?dts.length/span:0;
 let streak=0;for(let k=wks.length?wks[wks.length-1]:0;wk[k];k-=WK)streak++;
 const rec=wks.slice(-26);let mw=1;rec.forEach(k=>{if(wk[k]>mw)mw=wk[k]});
 const off=-new Date().getTimezoneOffset()/60;
 let h='<div class="tp"><div class="sec">Upload timing <small>— which day, which hour, and how many per week (from real timestamps)</small></div>'+
  '<div class="kpi">'+
   kpi("most uploads on",bd[0]?(STDD[bd[1]]+" ("+bd[0]+")"):"—",bd[0]?"var(--acc)":"")+
   kpi("most common hour",bh[0]?(stHH(bh[1])+":00-"+stHH((bh[1]+1)%24)+":00"):"—",bh[0]?"var(--acc)":"")+
   kpi("uploads per week",perW?perW.toFixed(2):"—")+
   kpi("last upload",(since==null?"—":since+" days ago"))+
   kpi("longest gap",(gap?Math.round(gap/D8)+" days":"—"),gap>30*D8?"var(--warn)":"")+
   kpi("consecutive weeks",streak?String(streak):"—")+'</div>';
 let hdr='<b></b>';for(let i=0;i<24;i++)hdr+='<u>'+(i%2?"":stHH(i))+'</u>';
 let cells='';
 for(let d=0;d<7;d++){
  cells+='<b title="'+STDD[d]+'">'+STDD[d]+'</b>';
  for(let k=0;k<24;k++){
   const v=hm[d*24+k],sel=(STF.day===d&&STF.hr===k),lb=STDD[d]+' '+stHH(k)+':00 — '+
    (v?(v+' video'+(v>1?"s":"")):"no video");
   cells+='<button type="button" class="hc'+(sel?" on":"")+'" data-d="'+d+'" data-h="'+k+'" '+
    'aria-label="'+lb+'" aria-pressed="'+(sel?"true":"false")+'" title="'+lb+'" '+
    'onclick="stTimeGo('+d+','+k+')" '+
    'style="background:rgba(var(--accrgb),'+(v?(0.12+0.8*v/mx).toFixed(2):"0.05")+')">'+
    (v?'<span>'+v+'</span>':"")+'</button>'}}
 h+='<div class="hm">'+hdr+cells+'</div>'+
  '<div class="sub">Hours are in your browser’s time (UTC'+(off>=0?"+":"-")+Math.abs(off)+'). '+
  'The map is built on '+its.length+' long videos — of these, '+wt.length+' gave a full publish time'+
  (noTs?(' — '+noTs+' have not yet'):'')+'. '+
  (all.length-its.length)+' shorts are excluded (their hour means something different), but the weekly and gap counts include them. '+
  'Click a cell = the videos from that day and hour; click again = filter off. '+
  'Colour depth = how many uploads ran on that day and hour (busiest cell has '+mx+').</div>';
 if(noAll&&!TSJ)h+='<div class="tpact"><button class="go" onclick="tsBack()">'+ico("clock",14)+
  'Get the publish time for the other '+noAll+' videos</button>'+
  '<span class="sub">Only their metadata is read again — thumbnail, OCR and measurement do not run again.</span></div>';
 if(TSJ)h+='<div id="tsb">'+tsProg()+'</div>';
 if(STF.day!=null||STF.hr!=null)
  h+='<div class="tpon">'+ico("filter",13)+'<b>'+(STF.day!=null?STDD[STF.day]:"any day")+
   (STF.hr!=null?(" "+stHH(STF.hr)+":00-"+stHH(STF.hr)+":59"):" at any hour")+'</b>'+
   '<span class="sub">'+((rows||[]).length)+' rows match this time filter</span>'+
   '<button class="sm" onclick="stTimeClr()">Remove the time filter</button></div>';
 if(rec.length){
  let bars='';rec.forEach(k=>{const d=new Date(k);
   bars+='<i title="week of '+d.getDate()+' '+STM[d.getMonth()]+' — '+wk[k]+' video'+(wk[k]>1?"s":"")+'" style="height:'+
    Math.max(4,Math.round(wk[k]/mw*100))+'%"></i>'});
  const f=new Date(rec[0]),l=new Date(rec[rec.length-1]);
  h+='<div class="sec" style="margin-top:12px">Uploads per week <small>— the last '+rec.length+
   ' weeks (counted from every date; this one does not need a publish time)</small></div>'+
   '<div class="wk" role="img" aria-label="uploads per week map: '+rec.length+' weeks, most uploads in one week: '+mw+'">'+bars+'</div>'+
   '<div class="sub">counted uploads span: '+f.getDate()+' '+STM[f.getMonth()]+' '+f.getFullYear()+' to '+
   l.getDate()+' '+STM[l.getMonth()]+' '+l.getFullYear()+' · '+dts.length+' videos across '+span+
   ' weeks · in this span, uploads per week '+(perW?perW.toFixed(2):"—")+
   ' · most uploads in one week: '+mw+
   ' (older uploads from the whole channel are not included — only '+all.length+' counted uploads are here; '+
   (all.length-dts.length)+' had no date at all)'+
   (gap?(' · longest gap '+Math.round(gap/D8)+' days, uploads resumed on '+
     new Date(gat+D8).getDate()+' '+STM[new Date(gat+D8).getMonth()]):'')+'</div>'}
 return h}
// Sirf chhapne ka waqt laane ka kaam: purani cache me ye field thi hi nahi, is liye
// poori naap dobara karne ki zaroorat nahi — server bhi sirf metadata padhta hai.
async function tsBack(){
 if(!cur||TSJ)return;
 let r;try{r=await j("/api/tback?id="+cur)}catch(e){return failToast(e,"starting the time backfill")}
 if(r.err)return failToast({message:r.err},"time backfill");
 TSJ={job:r.job,done:0,total:r.n||0,cur:"reading metadata…",el:0};
 tsPaint();
 for(let i=0;i<2400;i++){await new Promise(rs=>setTimeout(rs,1200));
  let p;try{p=await j("/api/progress?id="+r.job)}catch(e){break}
  TSJ.done=p.done||0;TSJ.total=p.total||TSJ.total;TSJ.cur=p.current||TSJ.cur;TSJ.el=p.elapsed||0;
  tsPaint();
  if(p.state==="done"||p.state==="error"){
   TSJ=null;
   if(p.state==="error")failToast({message:p.error||"the time backfill stopped"},"time backfill");
   else toast('publish time found for '+(p.found||0)+' videos ('+(p.elapsed||0)+' seconds)');
   CHX=null;D=null;WALK=null;CHXP={};await boot();return}}
 TSJ=null}
// Progress jahan bhi jagah mile wahin dikhao: panel ke andar #tsb, ya (jab panel
// pehle se na bana ho) button ki jagah. Dono surat me row ka kaam dikhta rahe.
function tsPaint(){const b=document.getElementById("tsb");
 if(b){b.innerHTML=tsProg();return}
 const p=document.querySelector(".tpact");if(p)p.innerHTML=tsProg()}
function tsProg(){
 const pct=TSJ&&TSJ.total?Math.min(100,Math.round(TSJ.done*100/TSJ.total)):0;
 return '<div class="stact"><b>Publish times arriving — '+(TSJ?TSJ.done:0)+'/'+(TSJ?TSJ.total:0)+'</b>'+
  '<div class="sub">'+esc(TSJ?TSJ.cur:"")+(TSJ&&TSJ.el?(' · '+TSJ.el+' seconds so far'):"")+'</div>'+
  '<div class="pbar"><i style="width:'+pct+'%"></i></div></div>'}
function stTbl(rows){
 const dn=STF.dir<0?"":" up";
 let h='<table class="stt"><thead><tr>'+
  '<th scope="col" class="no" aria-label="chunne ka box"><input type="checkbox"'+
  (rows.length&&rows.every(r=>SEL.has(r.u?r.u.id:r.it.id))?' checked':"")+
  ' onchange="stSelAll(this.checked)" aria-label="jo kuch is filter me dikh raha hai sab chuno"></th>'+
  '<th scope="col" class="l'+(STF.sort==="title"?" sorted"+dn:"")+'"'+srtA("title")+' onclick="stSort(\'title\')" title="title se sort karo">Video</th>'+
  STC.map(c=>'<th scope="col" class="'+(STF.sort===c[0]?"sorted"+dn:"")+'"'+srtA(c[0])+' onclick="stSort(\''+c[0]+'\')" title="is column se sort karo">'+c[1]+'</th>').join("")+
  '<th scope="col" class="l no" aria-label="kaam ke button"></th></tr></thead><tbody>';
 rows.forEach(r=>{
  if(r.u){const u=r.u;   // sirf gini gayi video: jo YouTube flat listing deta hai bas wahi dikhta hai
   h+='<tr class="srow un'+(SEL.has(u.id)?" sel":"")+'"><td class="no" onclick="event.stopPropagation()"><input type="checkbox"'+(SEL.has(u.id)?" checked":"")+' data-id="'+esc(u.id)+'" onchange="stSelChk(this)" aria-label="is video ko chuno"></td><td class="l"><div class="stv"><div class="sth">'+
    '<img loading="lazy" alt="" src="https://i.ytimg.com/vi/'+esc(u.id)+'/mqdefault.jpg" onerror="this.style.opacity=.12">'+
    (u.d?'<span class="dur">'+stDur(u.d)+'</span>':"")+(u.s?'<span class="sh">SHORT</span>':"")+'</div>'+
    '<div class="sti"><div class="t">'+esc(u.t||"(bina title)")+'</div>'+
    '<div class="m">sirf listing me gini gayi — is par naap nahi hua</div></div></div></td>'+
    '<td>'+(u.w==null?'<span class="d">—</span>':'<b>'+fmt(u.w)+'</b>')+'</td>'+
    '<td><span class="d">—</span></td><td><span class="d">—</span></td>'+
    '<td>'+(u.ts?stDate(new Date(u.ts*1000).toISOString().slice(0,10)):'<span class="d">—</span>')+'</td>'+
    '<td><span class="d" title="flat listing me lambai nahi milti — naap karne par asli lambai aa jaati hai">—</span>'+(u.s?'<span class="d">short</span>':"")+'</td>'+
    '<td><span class="d">—</span></td><td><span class="d">—</span></td>'+
    '<td>'+spCell(u.id,u.d)+'</td>'+
    '<td class="l"><a class="btn sm ytbtn" target="_blank" rel="noopener" href="https://www.youtube.com/watch?v='+esc(u.id)+'" title="is video ko YouTube par naye tab me kholo" aria-label="YouTube par kholo" onclick="event.stopPropagation()">'+ico("ext",13)+'</a><button class="sm" title="is video ka link copy karo" aria-label="link copy karo" onclick="event.stopPropagation();cpLink(\'https://www.youtube.com/watch?v='+esc(u.id)+'\')">'+ico("copy",13)+'</button><button class="sm nb" data-id="'+esc(u.id)+'" title="isi video par poora naap chalao (views, tags, thumbnail)" onclick="event.stopPropagation();chOne(this.dataset.id)">naap chalao</button></td></tr>';
   return}
  const it=r.it;
  h+='<tr class="srow'+(STF.open===it.id?" open":"")+(SEL.has(it.id)?" sel":"")+'" data-id="'+esc(it.id)+'" onclick="stOpen(this.dataset.id)">'+
   '<td class="no" onclick="event.stopPropagation()"><input type="checkbox"'+(SEL.has(it.id)?" checked":"")+' data-id="'+esc(it.id)+'" onchange="stSelChk(this)" aria-label="is video ko chuno"></td>'+
   '<td class="l"><div class="stv"><div class="sth"><img loading="lazy" src="'+imgu(it.thumb||"")+'" alt="">'+
    '<span class="dur">'+stDur(it.dur)+'</span>'+(it.sh?'<span class="sh">SHORT</span>':"")+'</div>'+
    '<div class="sti"><div class="t">'+esc(it.title||"(bina title)")+'</div><div class="m">'+
     esc((it.channel||it.chan||"").slice(0,34))+(it.cat?'<span class="sep">·</span>'+esc(it.cat):"")+
     ((it.dur||0)<120&&!it.sh?'<span class="sep">·</span>chhoti video':"")+'</div></div></div></td>'+
   '<td><b>'+fmt(it.views)+'</b><span class="d">'+fmt(vpd(it))+' /din</span></td>'+
   '<td>'+fmt(it.likes)+(it.likes&&it.views?'<span class="d">'+(it.likes*100/it.views).toFixed(2)+'%</span>':"")+'</td>'+
   '<td>'+fmt(it.cmts)+(it.cmts&&it.views?'<span class="d">'+(it.cmts*100/it.views).toFixed(2)+'%</span>':"")+'</td>'+
   '<td>'+stDate(it.upload)+'<span class="d">'+(stAge(it.upload)!=null?stAge(it.upload)+" din ki":"date nahi milti")+
    (it.pubts?' · '+stHH(new Date(it.pubts*1000).getHours())+":"+String(new Date(it.pubts*1000).getMinutes()).padStart(2,"0")+(it.pt?" (asli waqt, API se)":" (listing ka andazan waqt)"):"")+'</span></td>'+
   '<td>'+stDur(it.dur)+(it.sh?'<span class="d">short</span>':((it.dur||0)<120?'<span class="d">chhoti</span>':""))+'</td>'+
   '<td>'+(it.ls==null?'<span class="d">—</span>':'<b>'+it.ls+'</b><span class="mb"><i style="width:'+it.ls+'%;background:'+cc(it.ls)+'"></i></span>')+'</td>'+
   '<td>'+(it.score==null?'<span class="d">—</span>':'<b>'+it.score+'</b><span class="mb"><i style="width:'+it.score+'%;background:'+cc(it.score)+'"></i></span>')+issPill(it)+'</td>'+
   '<td>'+spCell(it.id,it.dur)+'</td>'+
   '<td class="l"><a class="btn sm ytbtn" target="_blank" rel="noopener" href="'+esc(it.url||"#")+'" title="is video ko YouTube par naye tab me kholo" aria-label="YouTube par kholo" onclick="event.stopPropagation()">'+ico("ext",13)+'</a><button class="sm" title="is video ka link copy karo" aria-label="link copy karo" onclick="event.stopPropagation();cpLink(\''+esc(it.url||"")+'\')">'+ico("copy",13)+'</button><button class="sm ic" data-i="'+r.i+'" title="is video ka poora analysis kholo" aria-label="poora analysis" onclick="event.stopPropagation();zoom(this.dataset.i)">'+ico("eye",15)+'</button></td></tr>';
  if(STF.open===it.id)h+=stDet(r)});
 return h+"</tbody></table>"}
function stFoot(){
 const c=D.cst||{},cap=c.walk_cap||400,n=(D.items||[]).length,un=walkRows().length;
 const vc=x=>x==null?"?":(x>=cap?x+"+":String(x));
 if(D.kind!=="channel")return '<div class="stft">Ye wo '+n+' videos hain jo is scan me li gayi thin — naap sirf inhi par hua hai.</div>';
 let s='Poori listing se <b>'+vc((c.tot_videos||0)+(c.tot_shorts||0))+'</b> videos gini gayi; inme se <b>'+n+
  '</b> par poora naap hua'+(un?', aur <b>'+un+'</b> sirf gini gayi hain — un par Views/Likes/tags/thumbnail ka naap khali hai (YouTube flat listing me wo nahi milta; "naap chalao" dabane par wo bhar jaate hain)':'')+'.';
 if((c.tot_videos||0)>=cap)s+=' Listing <b>'+cap+'</b> par ginna ruka tha (yt-dlp se ek request me itne se oopar nahi milte) — asli ginti isse zayada bhi ho sakti hai.';
 const sn=Object.keys((D.spon||{})).length;
 if(sn)s+=' "Ads" column = SponsorBlock ke community marks, '+sn+' videos par — jitni par marks nahi un par "—" hai (ads na hone ka dawa nahi).';
 return '<div class="stft">'+s+'</div>'}
function stDet(r){
 const it=r.it,sc=100/((it.an&&it.an.w)||1);
 const tb=(it.words||[]).map(w=>'<div class="oword" style="left:'+(w.x*sc)+'%;top:'+(w.y*sc)+'%;width:'+(w.w*sc)+'%;height:'+(w.h*sc)+'%"></div>').join("");
 const fb=(it.faces||[]).map(f=>'<div class="fbox" style="left:'+(f.x*sc)+'%;top:'+(f.y*sc)+'%;width:'+(f.w*sc)+'%;height:'+(f.h*sc)+'%"><span>chehra '+Math.round(f.area)+'%</span></div>').join("");
 const lr=it.likes&&it.views?(it.likes*100/it.views).toFixed(2)+"%":"—",cr=it.cmts&&it.views?(it.cmts*100/it.views).toFixed(2)+"%":"—";
 let h='<tr class="std"><td colspan="11"><div class="stdet"><div>'+
  '<div class="sub">teal box = jo text tool ne thumbnail par padha · pink box = chehra</div>'+
  '<div class="owrap" style="width:100%"><img src="'+imgu(it.thumb||"")+'">'+tb+fb+'</div>'+
  '<div class="bar" style="margin-top:10px">'+ytb(it.url)+ytc(it.url)+
  '<button class="go sm" data-i="'+r.i+'" onclick="zoom(this.dataset.i)">'+ico("eye",14)+'poora analysis (bara view)</button></div></div>'+
  '<div><div class="stdk">'+kpi("views",fmt(it.views))+kpi("views/day",fmt(vpd(it)))+kpi("like %",lr)+kpi("comment %",cr)+
   kpi("umr",(it.days!=null?it.days+" din":"—"))+kpi("lambai",stDur(it.dur))+kpi("asli tags",(it.tags||[]).length)+
   kpi("chapters",it.nch||0)+kpi("description",(it.dlen!=null?fmt(it.dlen)+" char":"—"))+
   kpi("listing score",(it.ls==null?"—":it.ls+"/100"))+kpi("thumbnail score",(it.score==null?"—":it.score+"/100"))+'</div>';
 if(it.vr)h+='<div class="lbl" style="margin-top:10px">Kya kharab hai — aur uska ilaaj</div>'+issList(it,r.i,true);
 if(it.sd)h+='<details class="kdet" style="margin-top:10px"><summary>'+ico("bars",14)+'score ka poora hisaab kholo</summary>'+
  '<div style="padding-top:8px">'+whyCard(it)+'</div></details>';
 if((it.tags||[]).length)h+='<div class="lbl">Asli tags — channel ne khud lagaye the (koi andaaza nahi)</div><div class="tagrow">'+
   it.tags.slice(0,30).map(t=>'<span class="chip">'+esc(t)+'</span>').join("")+'</div>';
 // SponsorBlock ka hissa — community marks. Jo video API me aayi hi nahi us par "koi
 // mark nahi" likha jaayega, "0 seconds ads" kabhi nahi — ye farq sach ka farq hai.
 const sdd=(D.spon||{})[it.id];
 if(sdd)h+='<div class="lbl" style="margin-top:10px">Ads ka bojh — SponsorBlock (logon ke marks, is tool ka naap nahi)</div>'+
  '<div class="sub">kul '+stDur(sdd.sec)+' sponsor/self-promo'+(it.dur?' — video ka '+Math.round(sdd.sec*100/it.dur)+'%':'')+
  ((sdd.segs||[]).length?(' · segments: '+sdd.segs.slice(0,10).map(s=>stTm(s[0])+'–'+stTm(s[1])+' '+esc(s[2])).join(" · ")):"")+'</div>';
 else if(D&&D.spon)h+='<div class="lbl" style="margin-top:10px">Ads ka bojh — SponsorBlock</div><div class="sub">is video par koi mark nahi — iska matlab ads ka na hona zaroori nahi, balki abhi kisi ne mark nahi kiya.</div>';
 // Poora record (poori description, keywords, chapters) row khulte hi us video se
 // liya jaata hai. 200 rows ka description table ke saath bhejne se page bhaari ho
 // jaata hai — jo kholi hai usi ka aata hai, aur wo bhi bina andaze ke.
 h+='<div class="lbl" style="margin-top:12px">Asli record — poori description, keywords, chapters</div>'+
    '<div class="smx" data-md="'+esc(it.id)+'"><div class="sub">ye record abhi us video se aa raha hai '+
    '(table ke saath bheja nahi jaata)…</div></div>';
 h+='<div class="lbl" style="margin-top:10px">Thumbnail ke naap (is tool ke — YouTube ka data nahi)</div><div class="tagrow">'+chipsOf(it)+'</div>'+
  '<div class="sub" style="margin-top:8px">Listing score = metadata ki saaf-suthri jaanch (title/tags/description), ye CTR nahi. Thumbnail score = banawas ki jaanch, chalne ka saboot nahi. Chalta kya hai ye Deep Analysis batata hai.</div>'+
  '</div></div></td></tr>';
 return h}
// Row khulte hi uska poora record maango — /api/meta wahi deta hai jo us video par
// YouTube ne khud diya hai (description, tags, chapters, category). Kuch bhi generate
// nahi hota; jo nahi mila wo "nahi mila" likha jaata hai.
function stMetaHook(){
document.querySelectorAll("[data-md]").forEach(el=>{
 if(el.dataset.done)return;const v=el.dataset.md;el.dataset.done="1";
 j("/api/meta?vid="+encodeURIComponent(v)).then(r=>{el.innerHTML=stMetaCard(r)}).
  catch(e=>{el.innerHTML='<div class="sub">record nahi aa saka: '+esc(String(e&&e.message||e))+
   ' — "naap chalao" se phir aa jaayega</div>'})})}
function stTm(s){s=s|0;const h=Math.floor(s/3600),m=Math.floor(s/60)%60;
return (h?h+":"+String(m).padStart(2,"0"):m)+":"+String(s%60).padStart(2,"0")}
function stMetaCard(r){
if(!r||!r.meta)return '<div class="sub">is video ka record file me nahi mila — "naap chalao" dabao, aa jaayega.</div>';
const m=r.meta,S=r.seo||{},hit=S.hit||[],miss=S.miss||[];
const dl=(m.desc||"").length,ch=m.chaps||[];
const chip=(t,c)=>'<span class="chip"'+(c?' style="color:'+c+'"':"")+'>'+esc(t)+'</span>';
let h='';
// Keywords: ye us video ki APNI listing ka hisaab hai — title ke kaun se shabd
// tags/description me dohraye gaye aur kaun se sirf title me hain. Gin-ti khud
// usi text se hui hai, koi suggestion tool ka andaaza nahi.
h+='<div class="lbl">Keywords — title ke shabd kahan dohraye gaye (asli gin-ti)</div>'+
 '<div class="tagrow" style="margin-bottom:4px">'+
  hit.map(w=>chip(w,"var(--ok)")).join("")+miss.map(w=>chip(w,"var(--bad)")).join("")+
  (hit.length||miss.length?"":'<span class="sub">is video ka title/tags itna short hai ke tulna nahi ho saki</span>')+'</div>'+
 '<div class="sub">hari = title ka wo shabd tags ya description me bhi hai (YouTube ko topic samajhne me aasan). '+
  'laal = sirf title me hai, kahin dohraya nahi gaya — inhe description ke pehle 200 characters me laana sabse sasta sudhaar hai.</div>'+
 '<div class="tagrow" style="margin-top:8px">'+
  '<span class="chip">asli tags <b>'+(m.tags||[]).length+'</b></span>'+
  '<span class="chip">description <b>'+fmt(dl)+'</b> ch</span>'+
  '<span class="chip">hashtags <b>'+(S.hh!=null?S.hh:"—")+'</b></span>'+
  '<span class="chip">description ke link <b>'+(S.lk!=null?S.lk:"—")+'</b></span>'+
  (m.cat?'<span class="chip">category <b>'+esc(m.cat)+'</b></span>':"")+
  (m.cc?'<span class="chip">subtitles <b>'+fmt(m.cc)+'</b> bhashayein</span>':"")+
  (m.age?'<span class="chip">age <b>'+esc(m.age)+'</b></span>':"")+
  (m.up?('<span class="chip">upload <b>'+esc(stDate(m.up.replace(/^(\d{4})(\d{2})(\d{2})$/,"$1-$2-$3")))+'</b></span>'):"")+'</div>';
h+='<div class="lbl" style="margin-top:10px">Poori description — jaisi usne likhi ('+fmt(dl)+' characters)</div>'+
  '<pre class="desc">'+esc(m.desc||"(kuch nahi likha)")+'</pre>'+
  (dl>700?'<button class="sm" data-on="0" onclick="stDescX(this)">'+ico("down",13)+' poori description kholo</button>':"");
h+='<div class="lbl" style="margin-top:10px">Chapters — '+
  (ch.length?'asli, unhi waqton ke saath jo usne lagaye ('+ch.length+')':'is video me chapters nahi bane (ye kami hai, andaza nahi)')+'</div>';
if(ch.length)h+='<table class="stt"><thead><tr><th scope="col">waqt</th><th scope="col">usne kya likha</th></tr></thead><tbody>'+
  ch.map(c=>'<tr><td><b>'+stTm(c.t)+'</b></td><td>'+esc(c.s||"(bina naam)")+'</td></tr>').join("")+'</tbody></table>';
return h}
function stDescX(b){const p=b.previousElementSibling;if(!p)return;
const on=b.dataset.on==="1";p.style.maxHeight=on?"":"none";b.dataset.on=on?"0":"1";
b.innerHTML=on?ico("down",13)+" poori description kholo":ico("up",13)+" sameto"}
function stKind(k){STF.kind=k;["all","long","short"].forEach(x=>{const b=document.getElementById("stk-"+x);if(b)b.className=(x===k?"on":"")});stRender()}
function stSet(k,v){STF[k]=v;stRender()}
function stSort(k){if(STF.sort===k)STF.dir=-STF.dir;else{STF.sort=k;STF.dir=(k==="date"||k==="title")?1:-1}stRender()}
function stOpen(id){STF.open=(STF.open===id?"":id);stRender()}
// ---- Bulk-select (reference ke video-library ka pattern) ----
// Selection video-id se hoti hai (measured ho ya sirf listing wali). Drawer fixed
// neeche rehta hai aur sirf unhi kaam ke buttons deta hai jo sach me ho sakte hain:
// chuninda rows ka CSV (asli naap ke saath), title copy, ya chunav saaf.
let SEL=new Set();
function stSelChk(el){if(el.checked)SEL.add(el.dataset.id);else SEL.delete(el.dataset.id);
 // ek row ka hi class badlo — poori table dobara render karne se scroll/focus udd jaata hai
 const tr=el.closest("tr");if(tr)tr.classList.toggle("sel",el.checked);stSelUpd()}
function stSelAll(on){stRows().forEach(r=>{const k=r.u?r.u.id:r.it.id;if(on)SEL.add(k);else SEL.delete(k)});stRender()}
function stSelClr(){SEL.clear();stRender()}
// Chuninda rows ka poora record: measured items poore numbers ke saath, sirf-listing
// wali rows sirf title/URL ke saath — khaali field jhooth bharna nahi, na-apni had.
function stSelData(){const out=[],by={};
 ((D&&D.items)||[]).forEach(it=>by[it.id]=it);
 if(WALK&&WALK.rows)WALK.rows.forEach(u=>{if(by[u.id]==null)by[u.id]={id:u.id,title:u.t,un:1}});
 SEL.forEach(id=>{const it=by[id];if(it)out.push(it)});return out}
function stSelCsv(){const rows=stSelData();if(!rows.length)return;
 const head=["id","title","channel","url","views","views_per_day","likes","comments","upload","duration_s","score","thumb_score","measured"],
  q=s=>'"'+String(s==null?"":s).replace(/"/g,'""')+'"',
  ln=r=>[r.id,r.title,r.channel||"",r.url||("https://www.youtube.com/watch?v="+r.id),r.views,vpd(r),r.likes,r.cmts,r.upload,r.dur,r.score,r.ls,r.un?"no":"yes"].map(q).join(",");
 const csv=head.join(",")+"\n"+rows.map(ln).join("\n"),
  b=new Blob([csv],{type:"text/csv"}),a=document.createElement("a");
 a.href=URL.createObjectURL(b);a.download="clicklab-selection.csv";a.click();
 setTimeout(()=>URL.revokeObjectURL(a.href),4000);
 toast(rows.length+" rows ka CSV ban gaya — jo naap nahi hua wo khaali chhoda, bharwa ke nahi")}
function stSelCopy(){const rows=stSelData();if(!rows.length)return;
 const t=rows.map(r=>r.title||"(bina title)").join("\n");
 const done=()=>toast(rows.length+" title clipboard par copy ho gaye");
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done).catch(()=>{taCopy(t);done()})}
 else{taCopy(t);done()}}
function taCopy(t){const ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.opacity="0";
 document.body.appendChild(ta);ta.select();try{document.execCommand("copy")}catch(e){}ta.remove()}
function stSelUpd(){const old=document.getElementById("selbar");if(old)old.remove();
 // header ka select-all box hamesha asli state dikhaye (chk ab full re-render nahi karta)
 const hc=document.querySelector("#stbox .stt thead input[type=checkbox]");
 if(hc){const cbs=[...document.querySelectorAll("#stbox .stt tbody input[type=checkbox]")];
  hc.checked=cbs.length>0&&cbs.every(c=>c.checked);}
 if(!SEL.size)return;
 let meas=0,un=0;SEL.forEach(id=>{const it=((D&&D.items)||[]).find(x=>x.id===id);if(it)meas++;else un++});
 const d=document.createElement("div");d.id="selbar";d.className="selbar";
 d.innerHTML='<b>'+SEL.size+' videos chuni</b><span class="mut">'+
  (meas?meas+" measured":"")+(meas&&un?" · ":"")+(un?un+" sirf-gini (numbers baad me bharne ke liye khaali rahenge)":"")+
  '</span><span class="sp" style="flex:1"></span>'+
  '<button class="go sm" onclick="stSelCsv()">'+ico("down",13)+"Selection ka CSV</button>"+
  '<button class="sm" onclick="bulkTr(false)">'+ico("file",13)+"Subtitles laao (bulk, 15 tak)</button>"+
  '<button class="sm" onclick="bulkTr(true)">'+ico("file",13)+"Screen text OCR (bulk, 4 tak)</button>"+
  '<button class="sm" onclick="stSelCopy()">'+ico("copy",13)+"Titles copy</button>"+
  '<button class="sm" onclick="stSelClr()">Chunav saaf</button>';
 document.body.appendChild(d)}
function stRender(){
 const b=document.getElementById("stbox");if(!b)return;
 const rows=stRows(),c=document.getElementById("stcnt");
 if(c)c.textContent=rows.length+" / "+((D.items||[]).length+walkRows().length)+" shown";
 b.innerHTML=stAct()+stSponBar()+stTimePanel(rows)+(rows.length?(stTbl(stPage(rows))+stPg(rows)+stFoot()):stEmpty());
 stMetaHook();stSelUpd()}
// Filter se kuch nahi bacha to sirf ek line nahi batati ki agla qadam kya hai.
// Ye khali haal hi ek button de deta hai — user ko khud guess na karna pade.
function stEmpty(){
 const f=STF.q||STF.win!=="all"||STF.kind!=="all"||STF.nap!=="all";
 let why=[];
 if(STF.q)why.push('"'+esc(STF.q)+'" par koi title ya tag nahi mila');
 if(STF.kind!=="all")why.push("sirf "+(STF.kind==="long"?"longs":"shorts")+" dikh rahe");
 if(STF.win!=="all")why.push("sirf "+STF.win+" din ke andar");
 if(STF.nap==="un")why.push("sirf bina-naap wali rows");
 if(STF.day!=null)why.push("sirf "+STDD[STF.day]+" ko chhapi gayi");
 if(STF.hr!=null)why.push("sirf "+stHH(STF.hr)+":00 ki ghari");
 return '<div class="es">'+ico("filter",26)+"<h3>In filteron me koi video nahi mili</h3><p>"+
  (why.length?why.join(" · ")+". ":"")+"Filter thoda chhota karo, ya ek click me sab wapas dikha do.</p>"+
  (f?'<button class="go" onclick="stReset()">'+ico("refresh",14)+"Saare filter hatao</button>":"")+
  '<div class="sub" style="margin-top:10px">Video filter se chhupi hai, mit-ti nahi — upar ginti wahi dikhati hai jo asli hai.</div></div>'}
function stReset(){STF.q="";STF.kind="all";STF.win="all";STF.nap="all";STF.day=null;STF.hr=null;STF.pg=0;
 const el=document.querySelector(".st");if(el)el.outerHTML=stBlock();else stRender()}
function cmpView(v){CMPV=v;CPG=0;cmp()}

// Channel ki creation date: About page se joined; na mili to listing ki sabse
// purani upload — dono ka matlab alag hai, isliye label hamesha saath.
function fD(iso){const p=String(iso||"").split("-");return p.length===3?(+p[2])+" "+STM[+p[1]-1]+" "+p[0]:"—"}
function jnChip(c){const j=c.joined;
 if(!j)return '<span class="chip">created <b>—</b> <button class="sm" onclick="joinGet()">'+ico("dl",13)+'fetch joined date</button></span>';
 const age=(Date.now()-new Date(j.d+"T12:00:00").getTime())/31557600000;
 return '<span class="chip">channel created <b>'+fD(j.d)+'</b> · <b>'+age.toFixed(1)+'</b> years old</span>'}
function jnNote(c,s){const j=c.joined;
 if(!j)return '<div class="sub"><b>channel creation date:</b> not in this scan (older scans did not fetch it) — press <b>fetch joined date</b> above; it reads the channel’s public About page once, then it is cached.</div>';
 const src=j.src==="about"?"read from YouTube’s own About page (the “Joined” date it shows publicly)":
  "the About page did not give a date — this is the <b>oldest upload</b> in this listing, so the channel is <i>at least</i> this old";
 return '<div class="sub"><b>channel created:</b> '+fD(j.d)+' — '+src+
  (s.last?' · <b>last upload in this listing:</b> '+fD(s.last)+(s.days_since!=null?' (<b>'+s.days_since+'</b> days ago)':""):"")+'</div>'}
async function joinGet(){if(!cur)return;
 let r;try{r=await j("/api/join?id="+encodeURIComponent(cur))}catch(e){return failToast(e,"joined date")}
 if(r.err)return toast(r.err)
 D.ch=D.ch||{};D.ch.joined=r.joined;CHX={};toast(r.joined.src==="about"?(r.upgraded?"About page se asli joined date mil gayi — pehle wali fallback (sabse purani upload) thi, upgrade kar diya":"joined date mil gayi — YouTube ke About page se"):"About page se date nahi mili — listing ki sabse purani upload par likh diya (source saath likha hai)");chanv()}
function chDash(d){
  const c=d.ch||{},s=d.cst||{},e=s.earn||{},ns=s.niche||{},m=s.monet||{},cap=s.walk_cap||400;
  const vc=v=>v==null?"—":(v>=cap?(v+"+"):String(v));
  let h='<div class="card"><h3>'+esc(c.name||"?")+' '+(c.handle?'<span class="chip">'+esc(c.handle)+'</span>':"")+
   (c.subs?'<span class="chip">subscribers <b>'+fmt(c.subs)+'</b></span>':"")+
   '<span class="chip">channel id <b>'+esc(c.id||"")+'</b></span>'+jnChip(c)+'</h3>'+
   '<div class="bar"><a class="btn sm ytbtn" target="_blank" rel="noopener" href="'+esc(c.url||"#")+'">'+ico("ext",14)+'Open on YouTube</a>'+
   '<button class="sm" onclick="go(\'cmp\')">'+ico("image",14)+'Full analysis of every video</button>'+
   '<button class="sm" onclick="go(\'deep\')">'+ico("bars",14)+'Deep analysis of this channel</button>'+
   '<button class="sm" onclick="go(\'ideas\')">'+ico("trophy",14)+'Winning topics → ideas</button>'+
   '<button class="sm" onclick="cur=\'\';CHC=null;go(\'ch\')">'+ico("search",14)+'Another channel</button></div>'+
   '<div class="sub">'+esc(d.cov||("measured on "+((s.n)||0)+" videos"))+
   ' · counted in the channel: <b>'+vc(s.tot_videos)+'</b> videos + <b>'+vc(s.tot_shorts)+'</b> shorts'+
   (s.tot_videos>=cap?' (the listing stopped at <b>'+cap+'</b> — that is why a <b>+</b> appears; a full count is not possible)':"")+
   (s.terr?' · '+esc(s.terr):"")+' · how it was found: '+esc(c.how||"")+'</div>'+jnNote(c,s)+'</div>';
  // ---- KPI ----
  h+='<div class="kpi">'+
    kpi("videos (counted)",vc(s.tot_videos))+(s.tot_shorts?kpi("shorts (counted)",vc(s.tot_shorts)):"")+
   kpi("analyzed",s.long_n+(s.short_n?" + "+s.short_n+" shorts":""))+
   kpi("subscribers",fmt(s.subs||0))+kpi("median views",fmt(s.views_med))+
   kpi("median views/day",fmt(s.vpd_med),"var(--acc)")+
   (s.per_week!=null?kpi("uploads / week",s.per_week):"")+
   (s.days_since!=null?kpi("last upload",s.days_since+" days ago",s.days_since>30?"var(--amb)":""):kpi("last upload","—"))+
   (s.last30!=null?kpi("uploads in 30 days",s.last30):"")+
    (s.hit_pct!=null?kpi("hit rate",s.hit_pct+"%",var2c(s.hit_pct,20,10)):"")+
    (s.flop_pct!=null?kpi("flop rate",s.flop_pct+"%",var2c(s.flop_pct,10,25)):"")+'</div>';
  // ---- monetization (public nahi) ----
  h+='<div class="card"><h3>'+ico("check",16)+' Monetized or not?</h3>'+
   '<div class="sub">'+esc(m.why||"")+'</div>'+
   '<div class="bar">'+(m.subs_ok?'<span class="chip">✓ subscribers 1000+ — <b>'+fmt(s.subs||0)+'</b></span>'
     :'<span class="chip">fewer than 1000 subscribers: <b>'+fmt(s.subs||0)+'</b> — the channel cannot clear this condition</span>')+
     '<span class="chip">watch-hours <b>upper</b> bound: <b>'+fmt(m.watch_hours_upper||0)+'</b> hours</span></div>'+
   '<div class="sub">'+esc(m.pyp||"")+' '+esc(m.pyp_hours_note||"")+'</div>'+
   '<div class="sub"><b>what this means:</b> monetization has no public field, so this tool will not claim "monetized: yes/no". What can be shown is above. The only certain answer is in YouTube Studio.</div></div>';
  // ---- kamai ----
  const el=e.long||{},esh=e.short||{};
  h+='<div class="card"><h3>'+ico("trend",16)+' Estimated earnings (a range, not one number)</h3>'+
   '<table><thead><tr><th scope="col">What</th><th scope="col" class="num">views (measured videos)</th><th scope="col" class="num">RPM range</th>'+
   '<th scope="col" class="num">earnings (low to high)</th></tr></thead><tbody>'+
    '<tr><td>longs ('+el.n+' videos)</td><td class="num">'+fmt(el.views)+'</td><td class="num">$'+el.rpm_lo+'–$'+el.rpm_hi+'</td>'+
    '<td class="num"><b>'+usd(el.lo)+' – '+usd(el.hi)+'</b></td></tr>'+
    (esh.n?'<tr><td>shorts ('+esh.n+' videos)</td><td class="num">'+fmt(esh.views)+'</td><td class="num">$'+esh.rpm_lo+'–$'+esh.rpm_hi+'</td><td class="num"><b>'+usd(esh.lo)+' – '+usd(esh.hi)+'</b></td></tr>':"")+
    '<tr><td>median for one long video</td><td class="num">'+fmt(s.views_med)+'</td><td class="num">—</td>'+
    '<td class="num">'+usd(e.per_video_lo)+' – '+usd(e.per_video_hi)+'</td></tr>'+
    '<tr><td>videos uploaded in the last 30 days</td><td class="num">'+fmt(s.last30_views||0)+'</td><td class="num">—</td>'+
    '<td class="num"><b>'+usd((s.last30_earn||{}).lo)+' – '+usd((s.last30_earn||{}).hi)+'</b></td></tr>'+
    '</tbody></table>'+
    '<div class="sub">Where the RPM range comes from: <b>'+esc(el.src||"")+'</b>. '+esc(e.cpm_note||"")+
   ' For rupees, multiply the dollars by your own exchange rate — this tool does not convert currency (a wrong rate gives a wrong number).</div>'+
   '<div class="bar"><input type="text" id="rpml" placeholder="your Studio RPM (longs), e.g. 0.4" style="width:180px">'+
   '<input type="text" id="rpmsh" placeholder="shorts RPM (optional)" style="width:150px">'+
   '<input type="text" id="rpmn" placeholder="note: e.g. India, low-CPM" style="width:180px">'+
   '<button class="sm go" onclick="setRpm(\''+esc(c.id)+'\')">this is my real RPM</button></div>'+
   '<div class="sub">Enter your own Studio RPM and the estimate above becomes a <b>real calculation</b> (±15%, because every video’s RPM differs) — and it is saved for this channel only.</div></div>';
  // ---- niche ----
  h+='<div class="card"><h3>'+ico("target",16)+' Niche</h3>'+
    '<div class="bar">'+(ns.real_cat?'<span class="chip">YouTube’s <b>real category field</b>: <b>'+esc(ns.real_cat)+'</b> — set on '+ns.real_n+'/'+(ns.items_n||s.long_n)+' videos'+(ns.cat_niches>1?' ('+ns.cat_niches+' categories)':'')+'</span>':'')+
     (ns.kw_niche?'<span class="chip">from keywords: <b>'+esc(ns.kw_niche)+'</b> ('+ns.kw_n+' hits)</span>':"")+
     (ns.alt&&ns.alt.length?'<span class="chip">other possibilities: '+esc(ns.alt.join(", "))+'</span>':"")+'</div>'+
   (ns.kw&&ns.kw.length?'<div class="sub">most frequent keywords (counted in titles+tags+channel tags): '+
     ns.kw.map(k=>'<span class="chip">'+esc(k[0])+' <b>'+k[1]+'</b></span>').join("")+'</div>':"")+
   '<div class="sub">Two different routes are shown because they are not the same thing: <b>category</b> is YouTube’s own field, set by the channel on each video (this is the more reliable one), <b>keywords</b> is this tool’s own count. If the two agree the niche is settled; if they differ the channel mixes topics. The RPM range depends on this: '+esc(ns.band_src||"")+'</div></div>';
  // ---- upload ka routine ----
  h+='<div class="card"><h3>'+ico("clock",16)+' Upload routine</h3><div class="kpi">'+
   kpi("first (measured) video",esc(s.first||"—"))+kpi("last upload",esc(s.last||"—"))+
   (s.gap_med!=null?kpi("median gap between videos",s.gap_med+" days"):"")+
   (s.per_week!=null?kpi("weekly pace",s.per_week):"")+
   (s.steady!=null?kpi("gaps under 21 days",s.steady+"%"):"")+
   (s.last90!=null?kpi("uploads in 90 days",s.last90):"")+'</div>'+
   (s.weekdays&&s.weekdays.length?'<table><thead><tr><th scope="col">Day</th><th scope="col" class="num">uploads that day</th><th scope="col" class="num">median views/day</th></tr></thead><tbody>'+
      s.weekdays.map(r=>'<tr><td>'+esc(r.d)+'</td><td class="num">'+r.n+'</td><td class="num">'+fmt(r.vpd)+'</td></tr>').join("")+
      '</tbody></table><div class="sub">Only days with <b>more than 4</b> videos are listed — on a small sample a per-day difference is noise, not signal. Day counts come from upload <b>dates</b>; the day-to-day difference is a correlation in this data, not a proven cause. The hour-level map (7×24) lives in the Content table below — it appears once upload <b>times</b> are fetched (the <b>time backfill</b> button there: 1 API unit, once per channel; new scans get times automatically when a YouTube key is set).</div>':
     '<div class="sub">The per-day difference cannot be counted in this sample (no day has more than 4 videos) — it stays silent for that reason, not because nothing was found.</div>')+
    (s.lens&&s.lens.length?'<div class="sub" style="margin-top:8px"><b>which video lengths work on this channel</b> (from its own videos):</div>'+
     '<table><thead><tr><th scope="col">Length</th><th scope="col" class="num">videos</th><th scope="col" class="num">median views</th><th scope="col" class="num">median views/day</th></tr></thead><tbody>'+
      s.lens.map(r=>'<tr><td>'+esc(r.k)+'</td><td class="num">'+r.n+'</td><td class="num">'+fmt(r.views)+'</td><td class="num">'+fmt(r.vpd)+'</td></tr>').join("")+
      '</tbody></table><div class="sub">This is correlation, not cause — long videos may have done better because their topic was different. The sample inside this channel is small, so do not put full trust in it.</div>':"")+
    '</div>';
  // ---- raftaar ----
  if(s.new10){
    h+='<div class="card"><h3>'+ico("spark",16)+' Speed of new vs old videos</h3><div class="kpi">'+
     kpi("views/day of the newest 10",fmt(s.new10.med))+kpi("the next 10 older videos",fmt(s.old10.med))+
     kpi("difference",(s.trend||0)+"x")+'</div>'+
      '<div class="sub">'+esc(s.trend_note||"")+'</div></div>'}
  // ---- saari videos: Studio jaisa Content table (sort + filter + row par detail) ----
  if((d.items||[]).length){
    h+='<div class="sec">'+ico("image",16)+' This channel’s videos — a measurement for every video '+
     '<small> — the Studio-style table: click any column header to sort, filter by type/date/search at the top, '+
     'click a row for the full detail under that row (real tags, description, thumbnail measurements). '+
     'At first, the videos with the most views are on top.</small></div>'+stBlock()}
  // ---- jo data nahi milta ----
  h+='<div class="card"><h3>'+ico("info",16)+' Data YouTube does not make public (so it is not shown anywhere)</h3>'+
   '<div class="sub">the channel’s <b>joined date</b> · the channel’s <b>total views</b> (videos past 400 are not counted, so total views would be incomplete too) · <b>monetization</b> yes/no · <b>RPM/CPM</b> · watch time · <b>traffic source</b> (search/suggested/browse) · <b>audience countries</b> · <b>revenue</b>. Everything shown above comes either from YouTube’s public fields or from counts made from those fields — and which one it is gets stated everywhere.</div></div>';
  return h}
function var2c(v,good,bad){return v>=good?"var(--grn)":v<=bad?"var(--red)":""}
async function setRpm(cid){
  const b=(v)=>{const x=parseFloat((($(v)||{}).value||"").trim());return isNaN(x)?null:Math.max(0,x)};
  const L=b("#rpml"),S=b("#rpmsh"),N=(($("#rpmn")||{}).value||"").trim();
  if(L==null&&S==null)return toast("RPM ka number likho (Studio se milta hai)");
  try{const r=await jp("/api/rpm",{cid:cid,long:L,short:S,note:N});
    toast("RPM save — "+(r.scans_updated||0)+" scan ka kamai ka hisaab naya hua");
    D=null;RPMX=null;chanv()}catch(e){failToast(e,"channel ka kaam")}}
async function chanv(){const _t=RTN;
  // Data cache me nahi to pehle skeleton: warna page khali khulta hai aur data aate
  // hi sab kuch koodta hai (layout shift).
  if(cur&&(!D||D.id!==cur))$("#main").innerHTML='<h2>'+ico("eye",22)+' Channel analytics</h2>'+
  '<div class="sub">Opening the channel’s data — anything measured before comes from the cache, so the listing is ready too.</div>'+
  chSearchCard()+skelKpi(6)+skelTable(6);
  const d=(cur&&D&&D.id===cur)?D:(cur?await ensureData():null);
   if(_t!==RTN)return;
  let h='<h2>'+ico("eye",22)+' Channel analytics</h2>'+
   '<div class="sub">The whole channel: search up to 50 channels, then open one — listing, shorts vs longs, each video’s real listing fields (tags/description/category), thumbnail measurements, upload routine, niche, and estimated earnings. Every number below is <b>a count</b>; where counting was not possible, it says so.</div>'+
   chSearchCard();
 if(CHJ)h+='<div class="card" id="chout"><h3>Opening the channel</h3><div id="chp"></div><div class="sub">Counting the listing (up to 400, ~5 seconds) → each video’s real listing fields + thumbnail (~0.5s per video, once; then cached) → OCR and measurement. This runs in the background; you can go elsewhere and come back.</div></div>';
  if(CHC)h+=chCands();
  h+=chMeTable();
  if(d&&d.kind==="channel")h+=chDash(d);
  else if(d)h+='<div class="card"><div class="sub">The scan selected above is a <b>topic</b> scan, not a channel. To open a channel, put a name/@handle in the form.</div></div>';
  $("#main").innerHTML=h;
  if(CHJ)chPoll()
  // Poori listing (jo sirf gini gayi hain) alag endpoint se aati hai: pehle dashboard
  // dekh do, listing aa jaaye to table apne aap taaza ho jaata hai.
  if(d&&d.kind==="channel")stWalk();stMetaHook()}
// ---------- do/zyada channel ki tulna ----------
async function cmpc(){
  const mine=SCANS.filter(s=>s.kind==="channel");
  let h='<h2>'+ico("trophy",22)+' Channel Tulna —mera channel vs competitors</h2>'+
    '<div class="sub">Ek se zayada channel kholo (Channels view se), phir yahan chuno. Upar seedha jawab milta hai: kaun aage hai, kis maap par, aur kahan sample itna chhota hai ke bharosa mat karo. Neeche poora hisaab — Overview me side-by-side bars, views/day ki range, upload rhythm aur subscribers ka farq, <b>"Timing &amp; pattern"</b> me upload ka din-ghari ka naqsha, length ka pattern, shorts-vs-long mix, title style aur common title words, "Kaun jeeta" me har maap ka scoreboard + matlab, aur views/day par Mann-Whitney U se <b>p-value</b> — taaki "behtar" ka matlab sirf bada number na ho.</div>';
  if(mine.length<2)return $("#main").innerHTML=h+'<div class="card"><div class="sub">Abhi <b>'+mine.length+'</b> channel khule hain. Tulna ke liye kam se kam do chahiye — <b>Channel Analytics</b> me ja kar doosra channel (competitor) kholo. Ek hi channel ke kai competitors khol sakte ho: har kholna ek alag scan banta hai, aur yahan sab select ho jaate hain.</div></div>';
  let sel=(CMP&&CMP.ids)||null;
  // Aakhri tulna yaad rehti hai — page band karke wapas aao to wahi channels
  // chune milte hain. Purane scans delete ho chuke ho to list apne aap saaf
  // ho jaati hai aur default do-channel wala chunalav lag jaata hai.
  if(!sel){try{const keep=mine.map(m=>m.id),sv=JSON.parse(localStorage.getItem("cl_cmpsel")||"[]");
   sel=sv.filter(x=>keep.indexOf(x)>=0);if(sel.length<2)sel=null}catch(e){sel=null}}
  if(!sel)sel=[mine[0].id,mine[1].id];
  h+='<div class="card"><h3>Kaun kaun tulna me <small class="sub" id="cmpn"></small></h3><div class="bar">'+
    mine.map(s=>{const c=s.ch||{},tv=c.tot_videos?((c.tot_videos>=400?c.tot_videos+"+":c.tot_videos)+" video"):null;
      return '<label class="pk"><input type="checkbox" value="'+s.id+'" onchange="cmpCount()" '+
      (sel.indexOf(s.id)>=0?"checked":"")+' data-n="'+esc(c.name||s.topic)+'"><b>'+esc(c.name||s.topic)+
      '</b><span>'+fmt(c.subs||0)+' subscriber'+(tv?' · '+tv:'')+'</span></label>'}).join("")+
    '<button class="go" onclick="runCmp()">'+ico("ab",14)+'Tulna dekho</button></div>'+
    '<div class="sub">Order matter karta hai: <b>sabse pehle chuna hua channel "mera" hai</b> — significance ki lines usi se against ginii jaati hain. '+
    'Ek waqt me <b>10 channels</b> tak — 1 apna aur 9 competitor. Overview me side-by-side bars aur ranges se ek nazar me farq dikhta hai; Maap tab me har line ek number hai (sections me baka hua, matlab ke saath) aur channels column me.</div></div>';
  if(CMP&&CMP.r)h+=cmpTable(CMP.r);
  $("#main").innerHTML=h;cmpCount()}
function cmpCount(){
 const n=document.querySelectorAll('#main input[type=checkbox]:checked').length,e=document.getElementById("cmpn");
 if(e)e.textContent=' — '+n+' chune / 10 tak'+(n>10?' (10 se oopar nahi ja sakte)':'');
 return n}
function cmpTable(r){
 if(!r||!(r.cols||[]).length)return '<div class="card"><div class="sub">Do channel kholo, phir tulna dikhegi.</div></div>';
 // footar ek hi jagah — jo tab khula ho, usi ki baat usi me jud jaati hai
 return cmSum(r)+cmVerdict(r)+'<div class="st">'+cmBar(r)+'<div id="cmbox" class="stscr">'+cmBody(r)+'</div>'+
  '<div class="stft" id="cmfoot">'+cmFootIn(r)+'</div></div>'}
function cmFootIn(r){
 const sg=CMV==="ov"?'Jo bhi bar ya range dikhti hai wo sirf unhi videos se bani hai jo waqai naapi gayi hain — jis channel ka sample chhota hai uski drawing bhi chhoti rahegi, aur jahan data na mil saka wahan "data nahi" likha aayega. Graph pattern dikhate hain, pakka faisala nahi karte. '
       :CMV==="tm"?'"Din ka pattern" scan me gini gayi har us video se ginti hai jisko date mil rahi hai — us par naap zaroori nahi; jo count hota hai wo legend me "gin X uploads" likha aata hai. Ghari ka naqsha sirf un LONG videos se jin ka exact waqt mila — jinhe nahi mila unhe chhoda gaya, isliye har card apna "n" khud likhta hai. Length ki ginti bhi sirf long videos ki. Title style aur common words sirf naapi gayi videos ke titles se ginte hain — common words ka matlab "dono ek hi space me hain" hai, chori ka davaa nahi. '
       :CMV==="sig"?esc((((r.sig||[])[0]||{}).note)||"")+" n kam ho to p ki line khamosh rehti hai — number ghadh kar bharosa mat karo. "
      :CMV==="rpm"?cmRpmFoot():'"Kul videos (gine)" YouTube ki listing se gini gayi hain (400 tak), "naapi gayi" wo hain jin par poora naap hua (views, tags, thumbnail). Baaki maap sirf naapi gayi videos par ginay gaye hain — chhote sample wali lines par itna bharosa mat karo.';
 return esc(r.note||"")+' '+sg}
function cmRpmFoot(){
 return 'YouTube kisi aur channel ka RPM, watch-time ya kul views public nahi karta — isliye kamai sirf ANDAAZA hai, aur wo bhi range me. '+
  'Apne channel ka asli RPM Studio se milta hai: wo "Channel Analytics" me daalo to yehi line asli ho jaati hai.'}
function cmBar(r){
 const cols=r.cols||[],sig=r.sig||[];let n=0;cols.forEach(c=>{n+=(c.long_n||0)+(c.short_n||0)});
 return '<div class="st-bar"><div class="seg">'+[["ov","Overview (charts)"],["tm","Timing & pattern ("+cols.length+")"],["maap","Maap ("+cols.length+" channels)"],["sig","Kaun jeeta ("+sig.length+")"],["rpm","Kamai ("+cols.length+")"]]
  .map(o=>'<button id="cmv-'+o[0]+'" class="'+(CMV===o[0]?"on":"")+'" onclick="cmvSet(\''+o[0]+'\')">'+o[1]+'</button>').join("")+'</div>'+
  '<span class="sp"></span><span class="cnt">'+cols.length+' channels · '+n+' videos naapi gayi</span></div>'}
function cmBody(r){return CMV==="ov"?cmOv(r):CMV==="tm"?cmTm(r):CMV==="sig"?cmSig(r):CMV==="rpm"?cmRpm(r):cmMaap(r)}
function cmvSet(v){CMV=v;["ov","tm","maap","sig","rpm"].forEach(x=>{const b=document.getElementById("cmv-"+x);if(b)b.className=(x===v?"on":"")});
 const b=document.getElementById("cmbox"),f=document.getElementById("cmfoot");
 if(CMP&&CMP.r){if(b)b.innerHTML=cmBody(CMP.r);if(f)f.innerHTML=cmFootIn(CMP.r)}}
function cmHead(c,i){
 return '<th scope="col" class="l no">'+(i===0?'<span class="tagme">mera</span>':"")+'<a class="chl" target="_blank" rel="noopener" href="'+esc(c.url||"#")+'">'+esc(c.name||"?")+'</a>'+
  '<div class="m">'+esc(String(c.handle||"—").replace(/^@/,""))+' · '+(c.long_n||0)+' long'+((c.short_n||0)?' + '+c.short_n+' short':"")+' naape gaye'+
  (c.joined?' · bana '+fD(c.joined.d)+(c.joined.src==="about"?" (About page se)":" (sabse purani listing se — is se purana milna lazmi nahi)"):"")+
  (c.last?' · aakhri upload '+fD(c.last):"")+'</div></th>'}
// Maap tab: table ulti hai — har LINE ek number, channels column me. Isse 30+ maap
// ek hi jagha padhe ja sakte hain; pehla column chipka rehta hai aur channels
// table ke andar hi sarakte hain (page bahar nahi jata). Sections khud baka hue
// hain, jo line section me na aayi wo "Baaki" me aa jaati hai — kahin chhupta nahi.
function cmAll(r){
 const cs=r.cols||[];   // "naapi gayi" ki line client se judti hai — count backend ke paas pehle se hai
 return [{k:"_meas",lab:"naapi gayi videos",vals:cs.map(c=>String(fmt((c.long_n||0)+(c.short_n||0)))),
   raw:cs.map(c=>(c.long_n||0)+(c.short_n||0)),best:null}].concat(r.rows||[])}
const CMSEC=[["Channel ka aakaar aur pichhla kaam",["subs","tot_videos","tot_shorts","_meas","views_sum","last30_views"]],
["Raftaar aur result",["views_med","vpd_med","hit_pct","flop_pct","trend"]],
["Audience ka reaction",["en_med"]],
["Chhapne ki aadatein, length aur waqt",["per_week","last30","days_since","short_share","mix","dur_med","peak_day","peak_hour"]],
["Title ka style",["t_chars","t_words","t_num","t_caps","t_q","t_emo","t_pipe"]],
["Thumbnail ka style",["score","words","h320","cr","face","nch","tags_n"]],
["Listing ki safai",["dlen","ls"]],
["Kamai ka andaza",["earn30"]]];
// Ye lines server ne bheje hue charts ke data (dow/tm/dur_med/ttl) se client par
// judti hain — dobara ginne ki zaroorat nahi. Jahan data nahi, wahan value null
// rehti hai aur table "data nahi" likhta hai — koi ghadh hua number nahi.
function cmExtra(r){const ch=r.charts||[],cs=r.cols||[],o={};
 const nn=x=>typeof x==="number"&&isFinite(x)?x:null;
 o.dur_med={k:"dur_med",lab:"Median length (longs, minutes)",vals:ch.map(x=>((x||{}).dur_med==null?null:(x||{}).dur_med+" min")),raw:ch.map(x=>nn((x||{}).dur_med)),best:null};
 o.mix={k:"mix",lab:"Shorts ka mix (poori listing se gini)",vals:cs.map(c=>{const t=c.tot_videos||0,s=c.tot_shorts||0;if(!t)return null;
   return Math.round(100*s/Math.max(1,t))+"% short ("+fmt(s)+" / "+fmt(t)+((t>=400)?"+":"")+")"}),raw:cs.map(c=>c.tot_videos?100*(c.tot_shorts||0)/c.tot_videos:null),best:null};
 o.peak_day={k:"peak_day",lab:"Sabse zyada upload jis din",vals:ch.map(x=>{const g=x||{},d=g.dow||[];if(!d.some(v=>v))return null;
   let b=0,bi=-1;d.forEach((v,k)=>{if(v>b){b=v;bi=k}});return STDD[bi]+" ("+b+" / "+(g.dow_n||0)+")"}),raw:[],best:null};
 o.peak_hour={k:"peak_hour",lab:"Peak upload window (ghari local time)",vals:ch.map(x=>{const g=x||{},tm=g.tm||[];if(!tm.some(v=>v))return null;
   let b=0,bi=-1;tm.forEach((v,k)=>{if(v>b){b=v;bi=k}});return STDD[Math.floor(bi/24)]+" "+String(bi%24).padStart(2,"0")+":00-"+String((bi%24)+3).padStart(2,"0")+":00 (gin "+(g.tm_n||0)+")"}),raw:[],best:null};
 const tt=ch.map(x=>(x||{}).ttl||null);
 const trow=(k,lab,f,suf)=>{o[k]={k:k,lab:lab,vals:tt.map(t=>t?f(t)+suf:null),raw:tt.map(t=>t?nn(f(t)):null),best:null}};
 trow("t_chars","Median title lambai (chars)",t=>t.chars,"");
 trow("t_words","Median title shabd",t=>t.words,"");
 trow("t_num","Numbers likhe titles ka percent",t=>t.num,"%");
 trow("t_caps","ALL-CAPS shabd wale titles ka percent",t=>t.caps,"%");
 trow("t_q","Sawal puche jaane wale titles ka percent",t=>t.q,"%");
 trow("t_emo","Emoji wale titles ka percent",t=>t.emoji,"%");
 trow("t_pipe","Separator (| – •) wale titles ka percent",t=>t.pipe,"%");
 return o}
function cmMaap(r){const cs=r.cols||[],byK={},used={},ex=cmExtra(r);
 cmAll(r).forEach(x=>{byK[x.k]=x});Object.keys(ex).forEach(k=>{byK[k]=ex[k]});
 const ncol=cs.length+1;
 let h='<div style="display:flex;gap:10px;align-items:center;margin:0 0 8px"><button class="go sm" style="white-space:nowrap" onclick="cmCsv()">'+ico("down",13)+'Maap ka CSV</button><span class="sub">Excel/Sheets me khulta hai — sections wahi, aur jis video par jo naapa nahi gaya uski cell khaali hai, ghadh hua number nahi.</span></div>'+
   '<table class="stt"><thead><tr><th scope="col" class="l no stk">Maap<div class="m">har line ek number — uska matlab neeche likha hai<span class="mmh"> Mobile par line par tap karke matlab kholein.</span></div></th>'+
   cs.map((c,i)=>'<th scope="col" class="no">'+(i===0?'<span class="tagme">mera</span> ':"")+'<i class="cdot" style="background:'+CMCOL[i%10]+'"></i> '+esc(String(c.name||"?").slice(0,18))+
   '<div class="m">'+fmt((c.long_n||0)+(c.short_n||0))+' videos naape'+
   (c.joined?' · bana '+fD(c.joined.d)+(c.joined.src==="about"?" (About page se)":" (sabse purani listing se — is se purana milna lazmi nahi)"):"")+
   (c.last?' · aakhri upload '+fD(c.last):"")+'</div></th>').join("")+'</tr></thead><tbody>';
 const rowH=row=>{const ns=(row.raw||[]).map(x=>typeof x==="number"&&isFinite(x)?Math.max(0,x):-1),mx=Math.max.apply(null,ns.concat([-1]));
  let x='<tr><td class="l stk" onclick="cmRowT(this)"><b>'+esc(row.lab||row.k)+'</b>'+(CMPMEAN[row.k]?'<div class="m mm">'+esc(CMPMEAN[row.k])+'</div>':"")+'</td>';
  cs.forEach((c,i)=>{const v=(row.vals||[])[i],raw=(row.raw||[])[i],w=row.best===i;
   const bw=(typeof raw==="number"&&isFinite(raw)&&mx>0)?Math.max(2,Math.round(Math.max(0,raw)/mx*100)):null;
   x+='<td'+(w?' class="win"':'')+'>'+(w?ico("trophy",13)+" ":"")+'<b>'+esc(v==null?"data nahi":String(v))+'</b>'+
    (bw!=null?'<span class="mb" title="is line me sabse bade number ke muqable"><i'+(w?'':' class="q"')+' style="width:'+bw+'%"></i></span>':"")+'</td>'});
  return x+'</tr>'};
 CMSEC.forEach(sec=>{const rows=sec[1].map(k=>byK[k]).filter(Boolean);if(!rows.length)return;
  rows.forEach(row=>{used[row.k]=1});
  h+='<tr class="sec"><td colspan="'+ncol+'">'+esc(sec[0])+'</td></tr>'+rows.map(rowH).join("")});
 const rest=cmAll(r).concat(Object.keys(ex).map(k=>ex[k])).filter(x=>!used[x.k]);
 if(rest.length)h+='<tr class="sec"><td colspan="'+ncol+'">Baaki</td></tr>'+rest.map(rowH).join("");
 return h+'</tbody></table>'}
// Mobile par matlab wali doosri line chhupi rehti hai — line par tap hi uska
// khulna hai; desktop par wo hamesha khuli dikhti hai, isliye tap wahan kuch
// nahi badalta. Table ka CSV bhi yahin se banta hai — screen par jo table hai,
// file wahi hai: sections, matlab ka column, asli numbers, aur jo naapa hi nahi
// gaya uski khaali cell (ghadh hua number kabhi nahi).
function cmRowT(el){const tr=el.closest("tr");if(tr)tr.classList.toggle("mx")}
function cmCsv(){if(!CMP||!CMP.r)return;const r=CMP.r,cs=r.cols||[],byK={},ex=cmExtra(r);
 cmAll(r).forEach(x=>{byK[x.k]=x});Object.keys(ex).forEach(k=>{byK[k]=ex[k]});
 const q=s=>'"'+String(s==null?"":s).replace(/"/g,'""')+'"';
 const val=(row,i)=>{const raw=(row.raw||[])[i];if(typeof raw==="number"&&isFinite(raw))return raw;
  const v=(row.vals||[])[i];return v==null?"":String(v)};
 const out=[["Section","Maap","Iska matlab"].concat(cs.map(c=>String(c.name||"?")+" ("+((c.long_n||0)+(c.short_n||0))+" videos naape)"))];
 const used={};
 CMSEC.forEach(sec=>{sec[1].forEach(k=>{const row=byK[k];if(!row)return;used[k]=1;
  out.push([sec[0],row.lab||row.k,CMPMEAN[k]||""].concat(cs.map((c,i)=>val(row,i))))})});
 cmAll(r).concat(Object.keys(ex).map(k=>ex[k])).forEach(row=>{if(used[row.k])return;
  out.push(["Baaki",row.lab||row.k,CMPMEAN[row.k]||""].concat(cs.map((c,i)=>val(row,i))))});
 const csv=""+out.map(rw=>rw.map(q).join(",")).join("\r\n"),
  b=new Blob([csv],{type:"text/csv;charset=utf-8"}),a=document.createElement("a");
 a.href=URL.createObjectURL(b);a.download="clicklab-maap.csv";a.click();
 setTimeout(()=>URL.revokeObjectURL(a.href),4000);
 toast((out.length-1)+" lines ka Maap CSV ban gaya — jo naapa nahi gaya khaali chhoda, bharwa ke nahi")}
const CMPMEAN={subs:"Channel ki audience ka size — waqt ke saath graph Overview me hai.",
 tot_videos:"Listing me kul videos (400+ ka matlab listing cap tak ginna possible tha).",
 tot_shorts:"Listing me gine gaye shorts.",short_share:"Shorts ka hissa — info line hai, jeet-haar nahi.",
 views_med:"Video ki median popularity (raw views).",vpd_med:"Umr-se-normalised speed — tulna ki asli rekh.",
 en_med:"Views ka kitna percent log likes+comments me tukte hain.",
 hit_pct:"Apne hi median se 2x+ aage jaane wali videos ka percent.",
 flop_pct:"Median se 30% se kam par reh jaane wali videos ka percent (kam = acha).",
 per_week:"Haftawe me kitni videos — info line hai, rhythm khud dekho.",
 days_since:"Aakhri upload kitne din pehle (kam = acha). Chuppi growth ko marti hai.",
 last30:"Pichhle 30 din me kitni uploads.",
 trend:"Nayi vs purani videos ka views/day — shuruati boost ki wajah se growth ka saboot NAHI.",
 views_sum:"Padhi gayi videos ke kul views.",last30_views:"Nayi 30 din ki videos ka kaam.",
 earn30:"Kamai ka ANDAAZA (RPM range se) — pakka number sirf apne Studio ka RPM hai.",
 _meas:"Jitni videos par poora naap hua — jitna zyada, utna bharosa.",
 tags_n:"Listing me asli tags ki median ginati.",dlen:"Description ki lambai (chars).",
 ls:"Listing ka safai-score (0–100): tags/description/category ka mix.",
 nch:"Chapters lagane wali videos ka percent.",words:"Thumbnail par likhe shabd (median).",
 h320:"320px par kitna text padha ja sakta hai (px) — browse par ye dikhta hai.",
 cr:"Text ka contrast ratio (4.5:1 WCAG ki had).",face:"Chehra dikhne wali videos ka percent.",
 score:"Thumbnail ka apna score (0–100) — isi tool ka naapa hua.",
  dur_med:"Long videos ki median lambai — audience ki ummeed isi par set hoti hai.",
  mix:"Poori listing se shorts ka percent — content ka banta hua mix (naapi gayi ginti se alag).",
  peak_day:"Jis din sabse zyada uploads gine gaye — scan me mili dates se, sirf naapi gayi par nibandh nahi.",
  peak_hour:"Jis din-ghari window me sabse zyada uploads hue — sirf un longs se jin ka exact waqt mila; ghari local time.",
  t_chars:"Title ki median lambai (characters) — mobile par katne se related.",
  t_words:"Title me median shabd.",
  t_num:"Kitne percent titles me number likha hai (rank, list, saal).",
  t_caps:"Kitne percent titles me poora-capital (ALL-CAPS) shabd hai.",
  t_q:"Kitne percent titles sawal puchte hain.",
  t_emo:"Emoji wale titles ka percent.",
  t_pipe:"Pipe ya separator (| – •) use karne wale titles ka percent."};
function cmSig(r){
 const cs=r.cols||[],rows=cmAll(r);let tally=cs.map(()=>0),nWin=0;
 let h='<h3>Scoreboard — kaun kis maap par aage</h3>'+
  '<div class="sub">Har us line par winner nishani hai jahan jeetna ginne layak tha; barabar ya ginne-layak-na-hone wali lines khamosh hain. Matlab column padhna mat bhoolo — bada number akela faisla nahi karta.</div>'+
  '<table class="stt"><thead><tr><th scope="col" class="l no stk">Maap</th>'+
  cs.map((c,i)=>'<th scope="col" class="no"><i class="cdot" style="background:'+CMCOL[i%10]+'"></i> '+esc(String(c.name||"?").slice(0,20))+'</th>').join("")+
  '<th scope="col" class="l no">Iska matlab</th></tr></thead><tbody>'+
 rows.map(row=>{const win=row.best!=null;if(win){nWin++;tally[row.best]++}
  return '<tr><td class="l stk"><b>'+esc(row.lab)+'</b></td>'+
   row.vals.map((v,i)=>'<td'+(win&&row.best===i?' class="win"':'')+'><b>'+esc(v==null?"—":String(v))+'</b>'+(win&&row.best===i?" "+ico("trophy",12):"")+'</td>').join("")+
   '<td class="l"><span class="sub">'+esc(CMPMEAN[row.k]||"—")+'</span></td></tr>'}).join("")+'</tbody></table>'+
  '<div class="sub" style="margin-top:6px">'+nWin+' lines par winner gina gaya — score: '+
  cs.map((c,i)=>'<b style="color:'+CMCOL[i%10]+'">'+esc(String(c.name||"?"))+'</b> '+tally[i]).join(" · ")+
  '</div><h3 style="margin-top:16px">Views/day par significance (Mann-Whitney U)</h3>';
 const sig=r.sig||[],mx=Math.max.apply(null,sig.map(x=>x.ratio||0).concat([1]));
 h+='<table class="stt"><thead><tr><th scope="col" class="l no stk">Mera vs</th><th scope="col" class="no">Mera median views/day</th><th scope="col" class="no">Uska</th>'+
  '<th scope="col" class="no">Sample (n)</th><th scope="col" class="no">Farq</th><th scope="col" class="no">p-value</th><th scope="col" class="l no">Iska matlab</th></tr></thead><tbody>'+
 sig.map(x=>{const ok=x.p!=null&&x.p<0.05,bw=x.ratio!=null?Math.max(4,Math.round(x.ratio/mx*100)):null;
  return '<tr><td class="l stk"><b>'+esc(x.b)+'</b></td><td>'+fmt(x.a_med)+'</td><td>'+fmt(x.b_med)+'</td>'+
   '<td>'+x.n_a+' vs '+x.n_b+'</td><td><b>'+(x.ratio==null?"—":x.ratio+"x")+'</b>'+(bw!=null?'<span class="mb"><i'+(ok?'':' class="q"')+' style="width:'+bw+'%"></i></span>':"")+'</td>'+
   '<td><b style="color:'+(x.p==null?"var(--mut)":ok?"var(--ok)":"var(--warn)")+'">'+(x.p==null?"—":pfmt(x.p))+'</b></td>'+
   '<td class="l"><span class="sub">'+(x.p==null?"n kaafi nahi (6+6 chahiye) — is line par bharosa mat karo"
    :ok?"p < 0.05 — dono ki poori distribution alag lagti hai, ittefaq nahi"
    :"p ≥ 0.05 — itna farq do random samples me bhi aa sakta hai; ye line kamzor hai")+'</span></td></tr>'}).join("")+'</tbody></table>';
 return h}
function cmRpm(r){
 const cols=r.cols||[],er=((r.rows||[]).find(x=>x.k==="earn30")||{}).raw||[];
 let h='<table class="stt"><thead><tr><th scope="col" class="l no stk">Channel</th><th scope="col" class="no">RPM (longs)</th><th scope="col" class="no">30 din ki kamai — oopar ki had</th>'+
  '<th scope="col" class="l no">RPM ka range kahan se aaya</th></tr></thead><tbody>'+
 cols.map((c,i)=>'<tr><td class="l stk"><b>'+esc(c.name||"?")+'</b><div class="m">'+esc(String(c.handle||"—").replace(/^@/,""))+'</div></td>'+
  '<td><b>'+(c.rpm?"$"+c.rpm[0]+" – $"+c.rpm[1]:"—")+'</b></td>'+
  '<td>'+(er[i]!=null?"<b>"+usd(er[i])+"</b>":"—")+'</td>'+
  '<td class="l"><span class="sub">'+esc(c.rpm?c.rpm[2]:"?")+'</span></td></tr>').join("")+'</tbody></table>';
 return h}
const CMCOL=["#00d2ff","#818cf8","#34d399","#f59e0b","#f472b6","#22d3ee","#a3e635","#fb923c","#e879f9","#94a3b8"];
function cmDc(a,b,hb){if(typeof a!=="number"||typeof b!=="number"||!isFinite(a)||!isFinite(b)||a===0)return "";
 const p=Math.round((b-a)/Math.abs(a)*100);if(!isFinite(p))return "";if(p===0)return '<span class="dchip n">barabar</span>';
 const up=p>0,cls=hb==null?"n":((up===hb)?"u":"d");
 return '<span class="dchip '+cls+'">'+(up?"▲ +":"▼ ")+p+"%</span>"}
function cmSum(r){const cs=r.cols||[],ch=r.charts||[],rows=r.rows||[];
 const rawOf=k=>{const x=rows.find(y=>y.k===k);return (x&&x.raw)||[]};
 const perW=rawOf("per_week"),dS=rawOf("days_since");
 let h='<div class="cmpsum">';
 cs.forEach((c,i)=>{const g=ch[i]||{},sty=g.sty||{},meas=(c.long_n||0)+(c.short_n||0),tot=(c.tot_videos||0)+(c.tot_shorts||0);
  const dc=(a,b,hb)=>i?cmDc(a,b,hb):"";
  h+='<div class="cmpc" style="border-top:2px solid '+CMCOL[i%10]+'">'+
   '<h4><i class="cdot" style="background:'+CMCOL[i%10]+'"></i><span class="cnm">'+esc(c.name||"?")+'</span>'+(i===0?' <span class="tagme">mera</span>':"")+'</h4>'+
   '<div class="kv"><span>Subscribers</span><b>'+fmt(c.subs||0)+dc(cs[0].subs,c.subs,true)+'</b></div>'+
   '<div class="kv"><span>Channel bana</span><b>'+(c.joined?fD(c.joined.d)+(c.joined.src==="about"?" (About page se)":" (sabse purani listing se)"):'— <span class="sub">is scan me abhi nahi — channel khol kar fetch dabao</span>')+'</b></div>'+
   '<div class="kv"><span>Videos (gini)</span><b>'+fmt(tot)+(tot>=400?"+":"")+dc((cs[0].tot_videos||0)+(cs[0].tot_shorts||0),tot,null)+'</b></div>'+
   '<div class="kv"><span>Naapi gayi</span><b>'+fmt(meas)+' / '+fmt(tot)+'</b></div>'+
   '<div class="kv"><span>Median views/day</span><b>'+(g.vpd_med!=null?g.vpd_med.toFixed(1):"—")+dc((ch[0]||{}).vpd_med,g.vpd_med,true)+'</b></div>'+
   '<div class="kv"><span>Engagement median</span><b>'+(g.en_med!=null?g.en_med+"%":"—")+dc((ch[0]||{}).en_med,g.en_med,true)+'</b></div>'+
   '<div class="kv"><span>Uploads / hafta</span><b>'+(perW[i]!=null?perW[i]:"—")+dc(perW[0],perW[i],null)+'</b></div>'+
   '<div class="kv"><span>Aakhri upload</span><b>'+(dS[i]!=null?dS[i]+" din pehle":"—")+dc(dS[0],dS[i],false)+'</b>'+(c.last?'<div class="sub">listing me aakhri date: '+fD(c.last)+'</div>':"")+'</div>'+
   '<div class="kv"><span>Thumb score / chapters</span><b>'+(sty.score!=null?sty.score:"—")+' / '+(sty.chp!=null?sty.chp+"%":"—")+'</b></div>'+
   (meas<6?'<div class="kv"><span class="sub">naap chhota — ye numbers sirf direction ke liye hain</span></div>':"")+
   '</div>'});
 return h+'</div>'}
function cmpGo(id){const s=SCANS.find(x=>x.id===id);if(!s)return;
 if(cur!==id){cur=id;D=null;WALK=null;SEL.clear();stSelUpd()}go("ch")}
// Verdict ki "naap barhao" seedha kaam kare: channel kholo aur usi waqt un
// videos par naap shuru kar do jo sirf gini gayi hain (wahi engine jo
// "Poora channel naap lo" chalata hai — button sirf wahi dikhta hai jab
// guni-gaath videos bachi hon).
function cmpMeas(id,n){const s=SCANS.find(x=>x.id===id);if(!s)return;
 if(cur!==id){cur=id;D=null;WALK=null;SEL.clear();stSelUpd()}go("ch");chMore(n)}
function cmVerdict(r){const cs=r.cols||[],ch=r.charts||[],rows=cmAll(r),f=[];
 const rawOf=k=>{const x=rows.find(y=>y.k===k);return (x&&x.raw)||[]};
 const add=(w,t,b)=>f.push({w:w,t:t,b:b||""});
 (r.sig||[]).forEach((x,i)=>{const nm=String(x.b||(cs[i+1]||{}).name||"?");
  if(x.p==null){const thin=(x.n_a<x.n_b)?cs[0]:(cs[i+1]||{});
   add("warn","vs "+nm+": sample chhota hai ("+x.n_a+" vs "+x.n_b+" videos) — is farq ka faisla nahi ho sakta. Pehle dono taraf kam se kam 6-6 videos naapo.",thin&&thin.id?( ((thin.tot_videos||0)+(thin.tot_shorts||0))>((thin.long_n||0)+(thin.short_n||0)) ?'<button class="ytbtn sm" onclick="cmpMeas(\''+thin.id+'\',20)">'+ico("deep",12)+'20 videos bulk naap lo</button>' :'<button class="ytbtn sm" onclick="cmpGo(\''+thin.id+'\')">Naap barhao</button>' ):"")}
  else if(x.p<0.05)add("ok","vs "+nm+": views/day ka farq asli hai (p="+pfmt(x.p)+") — "+((x.ratio||0)>1?"aap is se "+x.ratio+"× aage ho":(x.ratio?nm+" aap se "+(1/x.ratio).toFixed(1)+"× aage hai":"barabar"))+".","");
  else add("warn","vs "+nm+": p="+pfmt(x.p)+" — itna farq do random samples me bhi aa sakta hai; ye line faislay layak nahi.","")});
 const dS=rawOf("days_since");dS.forEach((v,i)=>{if(typeof v==="number"&&v>=90)
  add("warn",String((cs[i]||{}).name)+" pichhle "+v+" din se chup hai — channel ki growth me sabse mehnga nuksan chuppi ka hota hai.",'<button class="ytbtn sm" onclick="cmpGo(\''+cs[i].id+'\')\">Channel kholo</button>')});
 const en=rawOf("en_med"),enR=(rows.find(y=>y.k==="en_med")||{}).best;
 if(enR!=null&&en.filter(v=>typeof v==="number").length>=2)
  add("ok","Engagement me "+String(cs[enR].name)+" aage hai ("+en[enR]+"% vs baaki: "+en.map((v,i)=>i!==enR?v+"%":null).filter(v=>v).join(" / ")+") — views ke muqable log iske videos par zyada react karte hain.","");
 const stys=ch.map(x=>x.sty||{});
 const cmpst=(key,lab,thr,unit)=>{const vs=stys.map(s=>typeof s[key]==="number"?s[key]:null),vals=vs.filter(v=>v!=null);
  if(vals.length<2)return;const mx=Math.max.apply(null,vals),mn=Math.min.apply(null,vals);
  if(mx-mn>=thr)add("info",String(cs[vs.indexOf(mx)].name)+" "+lab+" me aage: "+mx+unit+" vs "+String(cs[vs.indexOf(mn)].name)+" "+mn+unit+".","")};
 cmpst("chp","chapters lagane",25,"%");cmpst("face","chehra dikhane",30,"%");cmpst("tags","asli tags",3," tags");cmpst("words","thumbnail par shabd",6," shabd");
 const pW=rawOf("per_week");
 if(pW.filter(v=>typeof v==="number").length>=2)add("info","Upload rhythm: "+cs.map((c,i)=>typeof pW[i]==="number"?String(c.name)+" "+pW[i]+"/hafta":null).filter(v=>v).join(" · "),"");
 if(rawOf("trend").some(v=>typeof v==="number"))add("info","Trend line (nayi vs purani videos) ke baare me yaad rakhna: views/day shuru ke dinon me apne aap uncha hota hai — ye growth ka saboot nahi, sirf abhi ki raftaar hai.","");
 // Pattern insights — "Timing & pattern" tab ki kahani ka nichod yahan bhi.
 const dpk=[];ch.forEach((x,i)=>{if(!x||!(x.dow_n>=6))return;const a=x.dow||[];let b=[0,-1];a.forEach((v,k)=>{if(v>b[0])b=[v,k]});if(b[1]>=0&&b[0]>0)dpk.push([i,b[1],b[0]])});
 if(dpk.length>=2&&dpk.some(x=>x[1]!==dpk[0][1]))add("info","Upload ka din alag-alag: "+dpk.map(x=>String((cs[x[0]]||{}).name)+" "+STDD[x[1]]+" ko ("+x[2]+")").join(" · ")+" — hafte ka pattern bhi packaging ka hissa hai.","<button class=\"ytbtn sm\" onclick=\"cmvSet('tm')\">Poora naqsha</button>");
 const hpk=ch.map((x,i)=>{if(!x||!(x.tm_n>=6))return null;const tm=x.tm||[];let b=[0,-1];for(let d=0;d<7;d++)for(let h0=0;h0<22;h0++){let t=0;for(let k=0;k<3;k++)t+=tm[d*24+h0+k];if(t>b[0])b=[t,h0]}return b[0]>0?[i,b[1]]:null}).filter(Boolean);
 if(hpk.length>=2&&hpk.some(x=>x[1]!==hpk[0][1]))add("info","Chhapne ka waqt bhi alag: "+hpk.map(x=>String((cs[x[0]]||{}).name)+" "+String(x[1]).padStart(2,"0")+":00 ke aas-paad").join(" · ")+".","<button class=\"ytbtn sm\" onclick=\"cmvSet('tm')\">Ghari ka naqsha</button>");
 const dm=ch.map(x=>x&&typeof x.dur_med==="number"?x.dur_med:null),dmv=dm.filter(v=>v!=null);
 if(dmv.length>=2&&Math.max.apply(null,dmv)/Math.max(0.5,Math.min.apply(null,dmv))>=1.5)
  add("info","Length ka style alag: "+cs.map((c,i)=>dm[i]!=null?String(c.name)+" median "+dm[i]+" min":null).filter(Boolean).join(" vs ")+" — audience ka watch-time expectation hi doosra hai.","<button class=\"ytbtn sm\" onclick=\"cmvSet('tm')\">Buckets dekho</button>");
 const mxp=cs.map(c=>{const l=c.tot_videos||0,s=c.tot_shorts||0,t=l+s;return t?Math.round(100*s/t):null}),mxv=mxp.filter(v=>v!=null);
 if(mxv.length>=2&&Math.max.apply(null,mxv)-Math.min.apply(null,mxv)>=25)
  add("info","Shorts mix me farq: "+cs.map((c,i)=>mxp[i]!=null?String(c.name)+" "+mxp[i]+"% shorts":null).filter(Boolean).join(" vs ")+" — ye do alag games hain, ek hi line se naapo mat.","");
 const tc=ch.map(x=>x&&x.ttl&&typeof x.ttl.chars==="number"?x.ttl.chars:null),tcv=tc.filter(v=>v!=null);
 if(tcv.length>=2&&Math.max.apply(null,tcv)-Math.min.apply(null,tcv)>=12)
  add("info","Title ki lambai ka farq: "+cs.map((c,i)=>tc[i]!=null?String(c.name)+" median "+tc[i]+" chars":null).filter(Boolean).join(" vs ")+".","<button class=\"ytbtn sm\" onclick=\"go('hub')\">Title Lab</button>");
 const cmn=r.common||[];
 if(cmn.length>=3)add("info","Titles me common words: "+cmn.slice(0,8).map(x=>x.w).join(", ")+" — matlab audience ka space same hai; farq sirf packaging ka hai.","<button class=\"ytbtn sm\" onclick=\"cmvSet('tm')\">Poore words</button>");
 cs.forEach((c,i)=>{const meas=(c.long_n||0)+(c.short_n||0);
  if(meas<6)add("warn",String(c.name)+" ka sirf "+meas+" video naapa gaya — iski har line kamzor dikhegi.",(c.tot_videos||0)+(c.tot_shorts||0)>meas?'<button class="ytbtn sm" onclick="cmpMeas(\''+c.id+'\',20)">'+ico("deep",12)+'20 videos bulk naap lo</button>':'<button class="ytbtn sm" onclick="cmpGo(\''+c.id+'\')\">Is channel ko naapo</button>')});
 if(!f.length)add("info","Dono channels me maayne ka farq nahi dikha — numbers kareeb hain. Zyada videos naapne par hi pattern saaf hoga.","");
 let h='<div class="card"><h3>Is tulna se kya nikalta hai</h3>';
 f.slice(0,12).forEach(x=>{h+='<div class="vfind"><span class="dot" style="background:var(--'+(x.w==="ok"?"ok":x.w==="warn"?"warn":"nic")+')"></span><span>'+esc(x.t)+'</span><span class="sp"></span>'+x.b+'</div>'});
 return h+'<div class="sub" style="margin-top:8px">Ye observation hai, experiment nahi — pakka faisala apne channel ke A/B se hi hoga.</div></div>'}
function cmLg(cs,idxs){return '<div class="lgd">'+idxs.map(i=>'<span><i style="background:'+CMCOL[i%10]+'"></i>'+esc(String((cs[i]||{}).name||"?").slice(0,22))+'</span>').join("")+'</div>'}
function cmOv(r){let h='<div class="ovg">';
 h+='<div class="card"><h3>Ek nazar me — side by side</h3><div class="sub">Har number ke do bars: bar ki lambi us line ke sabse bade number ke hisaab se, asli value bagal me likhi hai. Jahan jeet-haar ginne layak thi wahan trophy hai; length, mix ya title style jaisi lines par sirf farq dikhaya gaya hai — koi jeet nahi gini.</div>'+cmVs(r)+'</div>';
 h+='<div class="card"><h3>Views/day ka phailav — kam se zyada</h3><div class="sub">Har channel ki patti uski speed ki poori range hai: halka hissa sabse kam se sabse zyada tak, motra nishan median. Scale log hai (10, 100, 1K...). Pehle wala dots wala graph padhna mushkil tha — yahi baat ab ek nazar me.</div>'+cmSpread(r)+'</div>';
 h+='<div class="card"><h3>Upload rhythm — mahine var kitni videos</h3><div class="sub">Asli publish dates se, sirf naapi gayi videos ki ginati. Bars channel ke rang me. 4 se kam mahine mile to pattern nikalna bekaar hai — tab ginti ki line dikhti hai. Din aur ghari ka poora pattern "Timing & pattern" tab me hai.</div>'+cmUp(r)+cmLg(r.cols||[],(r.cols||[]).map((c,i)=>i))+'</div>';
 h+='<div class="card"><h3>Thumbnail style ka farq</h3><div class="sub">Har line ek cheez: thumbnail ke shabd, bada text, contrast, chehra %, tags, score. Bar us axis ki had tak bharta hai (shabd 15, text 40px, contrast 10, score 100), asli number bagal me. Radar wala purana graph shape se zyada confuse karta tha — ab seedha bar, jo naapa gaya wahi dikhta hai.</div>'+cmStyle(r)+'</div>';
 h+='<div class="card"><h3>Subscribers ka waqt ke saath</h3><div class="sub">Channel History ke snapshots se. 3 se kam snapshots par trend ki line ka koi bharosa nahi — tab sirf records ka farq dikhta hai; 3+ judne par graph apne aap ban jaayega.</div>'+cmSubs(r)+'</div>';
 return h+'</div>'}
function cmVs(r){const cs=r.cols||[],ch=r.charts||[],rows=r.rows||[];
 const g=k=>{const x=rows.find(y=>y.k===k)||{};return [x.raw||[],x.vals||[],x.best===undefined?null:x.best]};
 const nn=x=>typeof x==="number"&&isFinite(x)?Math.max(0,x):null;
 const items=[];
 [["Subscriber","subs"],["Median views/day","vpd_med"],["Median engagement %","en_med"],
  ["Hit rate % (apne median se 2x+)","hit_pct"],["Uploads / hafta","per_week"],
  ["Aakhri upload (din pehle — kam behtar)","days_since"],["Median thumbnail score","score"]
  ].forEach(p=>{const a=g(p[1]);items.push([p[0],a[0],a[1],a[2]])});
 items.push(["Median length (longs, min)",ch.map(x=>nn((x||{}).dur_med)),ch.map(x=>((x||{}).dur_med==null?null:(x||{}).dur_med+" min")),null]);
 items.push(["Shorts ka mix (listing se)",cs.map(c=>c.tot_videos?100*(c.tot_shorts||0)/c.tot_videos:null),
  cs.map(c=>{const t=c.tot_videos||0;if(!t)return null;return Math.round(100*(c.tot_shorts||0)/t)+"% short"}),null]);
 items.push(["Median title lambai (chars)",ch.map(x=>nn(((x||{}).ttl||{}).chars)),ch.map(x=>{const t=(x||{}).ttl;return t?t.chars+" chars":null}),null]);
 let h="";
 items.forEach(it=>{const lab=it[0],raw=it[1],vals=it[2],best=it[3];
  const mx=Math.max.apply(null,raw.map(x=>x==null?-1:x).concat([-1]));
  h+='<div class="vsr"><div class="vl">'+esc(lab)+'</div>';
  cs.forEach((c,i)=>{const n=raw[i];
   h+='<div class="vbar"><span class="vn" style="color:'+CMCOL[i%10]+'">'+esc(String(c.name||"?").slice(0,22))+'</span>'+
    '<span class="vt"><i style="width:'+(n!=null&&mx>0?Math.max(1,Math.round(n/mx*100)):0)+'%;background:'+CMCOL[i%10]+';opacity:.75"></i></span>'+
    '<span class="vv">'+(best===i?ico("trophy",12)+" ":"")+esc(vals[i]==null?"data nahi":String(vals[i]))+'</span></div>'});
  h+='</div>'});
 return h}
function cmSpread(r){const cs=r.cols||[],ch=r.charts||[],all=[];
 ch.forEach(x=>((x||{}).vd||[]).forEach(v=>{if(v>0)all.push(v)}));
 if(all.length<2)return '<div class="sub">Views/day ki range ke liye kam se kam 2 naapi gayi videos chahiye — abhi '+all.length+' hain. "Channel Analytics" me ja kar us channel ki aur videos naapwayein.</div>';
 const lo=Math.log10(Math.max(0.1,Math.min.apply(null,all))),sp=Math.max(0.0001,Math.log10(Math.max(1,Math.max.apply(null,all)))-lo),hi=lo+sp;
 const X=v=>Math.max(0,Math.min(100,(Math.log10(Math.max(0.1,v))-lo)/sp*100));
 let h='<div class="sub" style="margin-bottom:8px">Scale: '+fmt(Math.pow(10,Math.ceil(lo)))+' se '+fmt(Math.pow(10,Math.floor(hi)))+' views/day tak (log)</div>';
 cs.forEach((c,i)=>{const vd=((ch[i]||{}).vd||[]).filter(v=>v>0);if(!vd.length)return;
  vd.sort((a,b)=>a-b);const mn=vd[0],mxv=vd[vd.length-1];let md=(ch[i]||{}).vpd_med;
  if(!(typeof md==="number"&&md>0))md=vd[Math.floor(vd.length/2)];
  const a1=X(mn),b1=X(mxv),m1=X(md),cl=CMCOL[i%10];
  h+='<div class="vbar"><span class="vn" style="color:'+cl+'">'+esc(String(c.name||"?").slice(0,22))+'</span>'+
   '<span class="vt" style="height:12px;background:transparent"><i style="left:'+a1.toFixed(1)+'%;width:'+Math.max(0.8,b1-a1).toFixed(1)+'%;top:4px;height:4px;background:'+cl+';opacity:.35"></i>'+
   '<i style="left:'+m1.toFixed(1)+'%;width:3px;top:0;height:12px;background:'+cl+';border-radius:1px"></i></span>'+
   '<span class="vv">'+fmt(md)+'</span></div>'+
   '<div class="vcap">kam '+fmt(mn)+' · median '+fmt(md)+' · zyada '+fmt(mxv)+' — '+vd.length+' videos par naapa</div>'});
 return h}
function cmUp(r){const cs=r.cols||[],ch=r.charts||[],ms={};
 ch.forEach(x=>((x||{}).up||[]).forEach(u=>{ms[u.m]=1}));
 let months=Object.keys(ms).sort();
 if(!months.length)return '<div class="sub">Kisi naapi gayi video ki publish date nahi mili — rhythm nahi gin sakta.</div>';
 if(months.length<4){let t=[];ch.forEach((x,i)=>{const us=((x||{}).up||[]).filter(u=>u&&u.n>0);
   if(us.length)t.push(esc(String((cs[i]||{}).name||"?").slice(0,20))+": "+us.map(u=>u.m+" me "+u.n).join(", "))});
  return '<div class="sub">Sirf '+months.length+' mahine gine gaye ('+months[0]+' se '+months[months.length-1]+') — itne kam waqt me mahine ke rhythm ka koi pattern nahi nikalta. Ginti aisi hai: '+(t.join(" | ")||"—")+'. Hafte ke din aur ghari ka pattern "Timing & pattern" tab me dekho.</div>'}
 months=months.slice(-12);
 let cnt=[];ch.forEach(x=>((x||{}).up||[]).forEach(u=>cnt.push(u.n)));cnt.push(1);
 const mx=Math.max.apply(null,cnt),W=640,H=190,PL=34,PB=26,PT=10,plotH=H-PB-PT,plotW=W-PL-12,bw=plotW/months.length,sw=Math.max(3,(bw-6)/cs.length);
 let s='<svg viewBox="0 0 '+W+' '+H+'" class="chm" role="img" aria-label="Mahine var uploads">';
 [0,Math.round(mx/2),mx].forEach(v=>{const y=PT+plotH-(v/mx)*plotH;
  s+='<line x1="'+PL+'" y1="'+y.toFixed(1)+'" x2="'+(W-12)+'" y2="'+(y.toFixed(1))+'" class="grid"/><text x="'+(PL-4)+'" y="'+(y+3).toFixed(1)+'" class="axl" text-anchor="end">'+v+'</text>'});
 months.forEach((m,j)=>{const bx=PL+j*bw+3;
  cs.forEach((c,i)=>{const u=((ch[i]||{}).up||[]).find(x=>x.m===m);if(!u||!u.n)return;
   const hgt=Math.max(1,(u.n/mx)*plotH);
   s+='<rect x="'+(bx+i*sw).toFixed(1)+'" y="'+(PT+plotH-hgt).toFixed(1)+'" width="'+sw.toFixed(1)+'" height="'+hgt.toFixed(1)+'" rx="1" fill="'+CMCOL[i%10]+'" opacity=".85"><title>'+esc(String(c.name))+": "+u.n+' uploads ('+m+')</title></rect>'});
  if(j%2===0||months.length<=6)s+='<text x="'+(bx+bw/2-3).toFixed(1)+'" y="'+(H-8)+'" class="axl" text-anchor="middle">'+m.slice(2)+'</text>'});
 return s+'</svg>'}
const CMRA=[["Shabd (thumb)","words",15],["Bada text@320","h320",40],["Contrast","cr",10],["Chehra %","face",100],["Asli tags","tags",10],["Score","score",100]];
function cmStyle(r){const cs=r.cols||[],ch=r.charts||[];
 let h="";
 CMRA.forEach(ax=>{const cap=ax[2];
  h+='<div class="vsr"><div class="vl">'+esc(ax[0])+' <span class="vm">— had '+cap+'</span></div>';
  cs.forEach((c,i)=>{const st=(ch[i]||{}).sty||{},raw=typeof st[ax[1]]==="number"?st[ax[1]]:null;
   h+='<div class="vbar"><span class="vn" style="color:'+CMCOL[i%10]+'">'+esc(String(c.name||"?").slice(0,22))+'</span>'+
    '<span class="vt"><i style="width:'+(raw==null?0:Math.max(1,Math.min(100,Math.round(raw/cap*100))))+'%;background:'+CMCOL[i%10]+';opacity:.75"></i></span>'+
    '<span class="vv">'+(raw==null?"naap nahi hua":esc(String(raw)))+'</span></div>'});
  h+='</div>'});
 return h}
function cmSubs(r){const cs=r.cols||[],ch=r.charts||[],hs=ch.map(x=>(x||{}).hist||null);
 if(!hs.some(h=>h))return '<div class="sub">Kisi bhi channel ki history me 2+ snapshots nahi — graph ke liye "Channel History" me ja kar snapshot lo (ya channel dobara scan karo, snapshot apne aap jud jaata hai).</div>';
 if(hs.some(h=>h&&h.length<3)){let t="";cs.forEach((c,i)=>{const hh=hs[i];
   if(!hh){t+='<div class="vsr"><div class="vl" style="color:'+CMCOL[i%10]+'">'+esc(String(c.name||"?").slice(0,24))+'</div><div class="vcap">Iske paas 2+ snapshots nahi — "Channel History" me snapshot lo ya channel dobara scan karo, line apne aap jud jaayegi.</div></div>';return}
   const a0=hh[0],z0=hh[hh.length-1],d=(z0.subs||0)-(a0.subs||0),dy=Math.max(1,Math.round((Date.parse(z0.t||"")-Date.parse(a0.t||""))/86400000));
   t+='<div class="vsr"><div class="vl" style="color:'+CMCOL[i%10]+'">'+esc(String(c.name||"?").slice(0,24))+'</div>'+
    '<div class="vcap">'+esc(String(a0.t||"").slice(0,10))+": "+fmt(a0.subs||0)+" → "+esc(String(z0.t||"").slice(0,10))+": "+fmt(z0.subs||0)+" — farq "+(d>=0?"+":"")+fmt(d)+" ("+dy+" din me). 2 records se trend ki line bharose layak nahi — 3+ snapshots par graph apne aap ban jaayega.</div></div>"});
  return t}
 const ts=[],subs=[];
 hs.forEach(h=>{if(h)h.forEach(p=>{const t=Date.parse(p.t||"");if(t)ts.push(t);subs.push(p.subs||0)})});
 const lo=Math.min.apply(null,ts),hi=Math.max.apply(null,ts),ylo=Math.min.apply(null,subs),yhi=Math.max.apply(null,subs);
 const W=640,H=210,PL=56,PT=10,PB=24,plotW=W-PL-12,plotH=H-PT-PB,span=Math.max(1,hi-lo),yspan=Math.max(1,yhi-ylo);
 const sx=t=>PL+((Date.parse(t||""))-lo)/span*plotW,sy=v=>PT+plotH-((v-ylo)/yspan)*plotH;
 let s='<svg viewBox="0 0 '+W+' '+H+'" class="chm" role="img" aria-label="Subscribers time ke saath">';
 [ylo,Math.round((ylo+yhi)/2),yhi].forEach(v=>{const y=sy(v);
  s+='<line x1="'+PL+'" y1="'+y.toFixed(1)+'" x2="'+(W-12)+'" y2="'+(y.toFixed(1))+'" class="grid"/><text x="'+(PL-4)+'" y="'+(y+3).toFixed(1)+'" class="axl" text-anchor="end">'+fmt(v)+'</text>'});
 cs.forEach((c,i)=>{const h=hs[i];if(!h)return;
  s+='<polyline points="'+h.map(p=>sx(p.t).toFixed(1)+","+sy(p.subs||0).toFixed(1)).join(" ")+'" fill="none" stroke="'+CMCOL[i%10]+'" stroke-width="2"/>'+
   h.map(p=>'<circle cx="'+sx(p.t).toFixed(1)+'" cy="'+sy(p.subs||0).toFixed(1)+'" r="3" fill="'+CMCOL[i%10]+'"><title>'+esc(String(c.name))+": "+fmt(p.subs||0)+' ('+esc(String(p.t||"").slice(0,10))+')</title></circle>').join("")});
 s+='<text x="'+PL+'" y="'+(H-8)+'" class="axl">'+new Date(lo).toISOString().slice(0,10)+'</text>'+
    '<text x="'+(W-12)+'" y="'+(H-8)+'" class="axl" text-anchor="end">'+new Date(hi).toISOString().slice(0,10)+'</text></svg>';
 const miss=cs.map((c,i)=>hs[i]?null:String(c.name||"?")).filter(Boolean),have=cs.map((c,i)=>i).filter(i=>hs[i]);
 return s+(miss.length?'<div class="sub" style="margin-top:6px">In channels ki line nahi bani (3 snapshots chahiye): '+esc(miss.join(", "))+'</div>':"")+cmLg(cs,have)}
// "Timing & pattern" tab — comparison ka doosra aadha: sirf ye nahin ki kaun aage
// hai, balki ye ki wo DAALTA kaise hai: kis din, kis ghari, kitni lambi, kis mix
// me, aur title kaise likhta hai. Har card apna sample-size khud likhta hai.
function cmTm(r){let h='<div class="ovg">';
 h+='<div class="card"><h3>Upload ka din — hafte ka pattern</h3><div class="sub">Har upload ki tareekh se ginta hai (sirf naapi-gin ki zaroorat nahi — jahan date hai wahan din bhi hai). Bars channel ke rang me; neeche har channel ka apna peak din likha hai.</div>'+cmDow(r)+'</div>';
 h+='<div class="card"><h3>Chhapne ka waqt — din × ghari ka naqsha</h3><div class="sub">Sirf long videos, aur sirf jin ka exact waqt mila hai. Jitna gehra rang utni uploads. Sample chhota rahega to pattern bhi dhundhla rahega — is liye har card pehle apna "n" batata hai.</div>'+cmHeat(r)+'</div>';
 h+='<div class="card"><h3>Length ka pattern</h3><div class="sub">Long videos ki length ke buckets (Shorts alag game hai, us me ye gin nahi jaata). Median length niche likhi hai — ye audience ke watch-time expectation ka farq hai.</div>'+cmDur(r)+'</div>';
 h+='<div class="card"><h3>Shorts vs long ka mix</h3><div class="sub">Listing se gini gayi ginti (400 tak) — pure range me nahi to "+" dikhega. Naapi-gin ka mix bhi saath likha hai.</div>'+cmMix(r)+'</div>';
 h+='<div class="card"><h3>Title style — lambai, CAPS, numbers, emoji</h3><div class="sub">Naapi-gin videos ke titles se. Koi line "jeeti" nahi hoti — ye do deshs ka farq hai, jeet ka faisala A/B se hota hai.</div>'+cmTtl(r)+'</div>';
 h+='<div class="card"><h3>Common title words — dono ek hi space me?</h3><div class="sub">Wo shabd jo kam se kam do channels ke 2-2 ALAG titles me baithe hain. Ye "same audience ka space" dikhata hai — chori ka davaa nahi.</div>'+cmCommon(r)+'</div>';
 return h+'</div>'}
function cmDow(r){const cs=r.cols||[],ch=r.charts||[];
 if(!ch.some(x=>(x||{}).dow_n>0))return '<div class="sub">Kisi channel ki upload dates nahi mili — din ka pattern gin hi nahi sakta.</div>';
 const mx=Math.max.apply(null,ch.map(x=>Math.max.apply(null,(x||{}).dow||[0])).concat([1]));
 const W=640,H=185,PL=30,PT=10,PB=24,plotH=H-PB-PT,plotW=W-PL-12,bw=plotW/7,sw=Math.max(3,(bw-8)/cs.length);
 let s='<svg viewBox="0 0 '+W+' '+H+'" class="chm" role="img" aria-label="Hafte ke din uploads">';
 [0,Math.round(mx/2),mx].forEach(v=>{const y=PT+plotH-(v/mx)*plotH;
  s+='<line x1="'+PL+'" y1="'+y.toFixed(1)+'" x2="'+(W-12)+'" y2="'+y.toFixed(1)+'" class="grid"/><text x="'+(PL-4)+'" y="'+(y+3).toFixed(1)+'" class="axl" text-anchor="end">'+v+'</text>'});
 for(let d=0;d<7;d++){const bx=PL+d*bw+4;
  cs.forEach((c,i)=>{const v=((ch[i]||{}).dow||[])[d]||0;if(!v)return;
   const hgt=Math.max(1,(v/mx)*plotH);
   s+='<rect x="'+(bx+i*sw).toFixed(1)+'" y="'+(PT+plotH-hgt).toFixed(1)+'" width="'+sw.toFixed(1)+'" height="'+hgt.toFixed(1)+'" rx="1" fill="'+CMCOL[i%10]+'" opacity=".85"><title>'+esc(String(c.name))+": "+v+" uploads ("+STDD[d]+')</title></rect>'});
  s+='<text x="'+(bx+bw/2-4).toFixed(1)+'" y="'+(H-8)+'" class="axl" text-anchor="middle">'+STDD[d]+'</text>'}
 s+='</svg>';
 const pk=cs.map((c,i)=>{const a=(ch[i]||{}).dow||[];let b=[0,-1];a.forEach((v,k)=>{if(v>b[0])b=[v,k]});
  return b[1]<0?null:'<span><i style="background:'+CMCOL[i%10]+'"></i>'+esc(String(c.name||"?").slice(0,20))+' — sabse zyada '+STDD[b[1]]+' ko ('+b[0]+') · gin '+((ch[i]||{}).dow_n||0)+' uploads</span>'}).filter(Boolean);
 return s+'<div class="lgd">'+pk.join("")+'</div>'}
function cmHeat(r){const cs=r.cols||[],ch=r.charts||[];
 let h="";
 cs.forEach((c,i)=>{const g=ch[i]||{},tm=g.tm||[],tn=g.tm_n||0,ln=g.long_n||0;
  h+='<div class="hmcard"><h4><i class="cdot" style="background:'+CMCOL[i%10]+'"></i><span class="cnm">'+esc(String(c.name||"?"))+'</span></h4>';
  if(!tn){h+='<div class="sub">Is channel ki '+(ln||"saari")+' long videos me se kisi ka exact chhapne ka waqt nahi mila — ghari ka naqsha is liye nahi ban sakta. "Waqt jodo" dabao: sirf metadata dobara padhi jaati hai, thumbnail/score dobara nahi chalta.</div>'+
   '<button class="ytbtn sm" onclick="cmpTback(\''+c.id+'\')">Waqt jodo</button></div>';return}
  const W=300,LX=30,TY=13,cw=(W-LX-6)/24,rh=14,Hh=TY+7*rh+4;
  let mx=1;tm.forEach(v=>{if(v>mx)mx=v});
  let s='<svg viewBox="0 0 '+W+' '+Hh+'" class="chm" role="img" aria-label="Din aur ghari ke hisaab se uploads">';
  for(let hh=0;hh<24;hh+=3)s+='<text x="'+(LX+(hh+1.5)*cw).toFixed(1)+'" y="'+(TY-3)+'" class="axl" text-anchor="middle">'+String(hh).padStart(2,"0")+'</text>';
  for(let d=0;d<7;d++){s+='<text x="'+(LX-4)+'" y="'+(TY+d*rh+rh-3)+'" class="axl" text-anchor="end">'+STDD[d]+'</text>';
   for(let hh=0;hh<24;hh++){const v=tm[d*24+hh];
    s+='<rect x="'+(LX+hh*cw).toFixed(1)+'" y="'+(TY+d*rh)+'" width="'+(cw-1).toFixed(1)+'" height="'+(rh-1)+'" rx="1" fill="'+(v?CMCOL[i%10]:"rgba(255,255,255,.05)")+'" opacity="'+(v?(0.15+0.85*v/mx).toFixed(2):1)+'"><title>'+STDD[d]+" "+String(hh).padStart(2,"0")+":00 — "+v+' uploads</title></rect>'}}
  s+='</svg>';
  let bd=[0,-1];for(let d=0;d<7;d++){let t=0;for(let k=0;k<24;k++)t+=tm[d*24+k];if(t>bd[0])bd=[t,d]}
  let bh=[0,-1];for(let d=0;d<7;d++)for(let h0=0;h0<22;h0++){let t=0;for(let k=0;k<3;k++)t+=tm[d*24+h0+k];if(t>bh[0])bh=[t,h0]}
  h+=s+'<div class="sub" style="margin-top:6px">Sabse zyada uploads '+STDD[bd[1]]+' ko ('+bd[0]+') · peak ghari '+String(Math.max(0,bh[1])).padStart(2,"0")+":00–"+String(bh[1]+3).padStart(2,"0")+":00 (ghari system ke local time me) · waqt mila "+tn+"/"+ln+" longs ka"+
   (tn<6?" — naap chhota hai, pattern dhundhla rahega":"")+(tn<ln?' · <button class="ytbtn sm" onclick="cmpTback(\''+c.id+'\')">Baaki ka waqt jodo</button>':"")+"</div></div>"});
 return h}
async function cmpTback(id){if(!CMP)return;
 if(CMP.busy)return toast("ek waqt me ek hi waqt-jodna ka kaam chalne do");
 CMP.busy=1;let r;try{r=await j("/api/tback?id="+id)}catch(e){CMP.busy=0;return failToast(e,"waqt jodna")}
 if(r.err){CMP.busy=0;return toast(r.err)}
 toast("waqt jodne ka kaam shuru — "+(r.n||0)+" videos ki metadata padhi ja rahi hai…");
 for(let i=0;i<300;i++){await new Promise(rs=>setTimeout(rs,1500));
  let p;try{p=await j("/api/progress?id="+r.job)}catch(e){break}
  if(p.state==="done"||p.state==="error"){CMP.busy=0;
   if(p.state==="error")failToast({message:p.error||"waqt jodna ruk gaya"},"waqt jodna");
   else{toast("waqt mil gaya "+(p.found||0)+" videos ko — tulna dobara bhar rahi hai");if(CMV==="tm"&&CMP)runCmp()}
   return}}
 CMP.busy=0;toast("waqt-jodna abhi bhi chal raha hai — thodi der me ye page dobara kholo")}
function cmDur(r){const cs=r.cols||[],ch=r.charts||[],LB=["<2m","2-5m","5-10m","10-15m","15-20m","20m+"];
 if(!ch.some(x=>(x||{}).dur_med!=null))return '<div class="sub">Kisi channel ki long videos ki length nahi mili — length ka pattern gin hi nahi sakta.</div>';
 const mx=Math.max.apply(null,ch.map(x=>Math.max.apply(null,(x||{}).dur||[0])).concat([1]));
 const W=640,H=185,PL=30,PT=10,PB=24,plotH=H-PB-PT,plotW=W-PL-12,bw=plotW/6,sw=Math.max(3,(bw-8)/cs.length);
 let s='<svg viewBox="0 0 '+W+' '+H+'" class="chm" role="img" aria-label="Length ke buckets">';
 [0,Math.round(mx/2),mx].forEach(v=>{const y=PT+plotH-(v/mx)*plotH;
  s+='<line x1="'+PL+'" y1="'+y.toFixed(1)+'" x2="'+(W-12)+'" y2="'+y.toFixed(1)+'" class="grid"/><text x="'+(PL-4)+'" y="'+(y+3).toFixed(1)+'" class="axl" text-anchor="end">'+v+'</text>'});
 for(let b=0;b<6;b++){const bx=PL+b*bw+4;
  cs.forEach((c,i)=>{const v=((ch[i]||{}).dur||[])[b]||0;if(!v)return;
   const hgt=Math.max(1,(v/mx)*plotH);
   s+='<rect x="'+(bx+i*sw).toFixed(1)+'" y="'+(PT+plotH-hgt).toFixed(1)+'" width="'+sw.toFixed(1)+'" height="'+hgt.toFixed(1)+'" rx="1" fill="'+CMCOL[i%10]+'" opacity=".85"><title>'+esc(String(c.name))+": "+v+" videos ("+LB[b]+')</title></rect>'});
  s+='<text x="'+(bx+bw/2-4).toFixed(1)+'" y="'+(H-8)+'" class="axl" text-anchor="middle">'+LB[b]+'</text>'}
 s+='</svg>';
 const med=cs.map((c,i)=>{const g=ch[i]||{};return g.dur_med==null?null:'<span><i style="background:'+CMCOL[i%10]+'"></i>'+esc(String(c.name||"?").slice(0,20))+" — median "+g.dur_med+" min (gin "+((g.dur||[]).reduce((a,b)=>a+b,0)||0)+")</span>"}).filter(Boolean);
 return s+'<div class="lgd">'+med.join("")+'</div>'}
function cmMix(r){const cs=r.cols||[];let h="";
 cs.forEach((c,i)=>{const l=c.tot_videos||0,s=c.tot_shorts||0,t=l+s;
  h+='<div style="margin:9px 0"><div class="sub" style="margin-bottom:3px"><b style="color:'+CMCOL[i%10]+'">'+esc(String(c.name||"?").slice(0,24))+'</b>'+(t?' · listing se gini: '+fmt(l)+" long / "+fmt(s)+" short"+((c.tot_videos>=400||c.tot_shorts>=400)?"+":""):"")+"</div>";
  if(!t){h+='<div class="sub">is channel ki listing gin me nahi aayi — mix nahi dikha sakta.</div></div>';return}
  const lp=l/t*100;
  h+='<div style="height:14px;border-radius:3px;overflow:hidden;display:flex;border:1px solid var(--line)">'+
   '<div style="width:'+lp.toFixed(1)+'%;background:'+CMCOL[i%10]+';opacity:.85" title="long '+Math.round(lp)+'%"></div>'+
   '<div style="flex:1;background:'+CMCOL[i%10]+';opacity:.3" title="shorts"></div></div>'+
   '<div class="sub" style="margin-top:3px">longs '+Math.round(lp)+"% · shorts "+Math.round(100-lp)+"% — aur naape gaye: "+(c.long_n||0)+" long / "+(c.short_n||0)+" short</div></div>"});
 return h}
function cmTtl(r){const cs=r.cols||[],ch=r.charts||[],ts=ch.map(x=>(x||{}).ttl||null);
 if(!ts.some(Boolean))return '<div class="sub">Kisi channel ka ek bhi title gin me nahi aaya (naapi-gin videos nahi) — title style gin hi nahi sakta.</div>';
 const ROWS=[["Titles gine","n",""],["Median chars","chars",""],["Median shabd","words",""],
  ["% titles me number","num","%"],["% me koi ALL-CAPS shabd","caps","%"],
  ["% me sawal ( ? )","q","%"],["% me | ya • separator","pipe","%"],
  ["% me bracket ( ) [ ]","brack","%"],["% me emoji","emoji","%"]];
 let h='<div class="st stscr"><table class="stt"><thead><tr><th scope="col" class="l no stk">Title style</th>'+
  cs.map((c,i)=>'<th scope="col" class="no">'+(i===0?'<span class="tagme">mera</span> ':"")+esc(String(c.name||"?").slice(0,18))+"</th>").join("")+"</tr></thead><tbody>";
 ROWS.forEach(x=>{h+='<tr><td class="l no">'+x[0]+"</td>"+cs.map((c,i)=>{const t=ts[i];
  return '<td class="no">'+(t&&t[x[1]]!=null?t[x[1]]+x[2]:"—")+"</td>"}).join("")+"</tr>"});
 return h+'</tbody></table></div><div class="sub" style="margin-top:6px">Koi line "jeeti" nahi hoti — ye sirf do deshs ka farq dikhata hai. Apne aap se poochho: is niche me kaunsa deshs zyada chalta hai, aur mera deshs waisa hai ya in jaisa.</div>'}
function cmCommon(r){const cs=r.cols||[],cm=r.common||[];
 if(!cm.length)return '<div class="sub">Koi aisa common word nahi mila jo kam se kam do channels ke 2-2 ALAG titles me ho — ya to space alag hai, ya naap itna chhota hai ki shabd mile hi nahi. Zyada videos naapo.</div>';
 return '<div class="cwch">'+cm.map(x=>'<span><b>'+esc(x.w)+"</b> <span>"+x.c.map(v=>'<i>'+(v||"—")+"</i>").join(" / ")+"</span></span>").join("")+"</div>"+
  '<div class="sub" style="margin-top:6px">Numbers channel ke rang me, unhi ke order me: '+cs.map((c,i)=>'<span style="color:'+CMCOL[i%10]+'">'+esc(String(c.name||"?").slice(0,14))+"</span>").join(" / ")+' — matlab wo shabd us channel ke kitne ALAG titles me baitha hai.</div>'}
async function runCmp(){
  const ids=[...document.querySelectorAll('#main input[type=checkbox]:checked')].map(x=>x.value);
  if(ids.length<2)return toast("kam se kam do channel chuno");
  if(ids.length>10)return toast("ek waqt me 10 channels tak — kuch chhatak kar dobara");
  spin();let r;try{r=await j("/api/chcmp?id="+ids.join(","))}catch(e){return failToast(e,"channel ki tulna")}
  if(r.err)return toast(r.err);
  CMP={ids:ids,r:r};try{localStorage.setItem("cl_cmpsel",JSON.stringify(ids))}catch(e){}cmpc()}   // wahi page dobara, ab table ke saath — picker ka ek hi taur

function help(){$("#main").innerHTML='<h2>'+ico("info",18)+' Kaise kaam karta hai</h2><div class="card">'+
 '<p>Machine video bana rahi hai. Video ke baad insaan ke paas do hi cheezein bachti hain: <b>topic</b> aur <b>bechna</b> (title + thumbnail). Ye tool doosre wale ke liye hai — CTR.</p>'+
 '<p><b>1. Competitors</b> — topic daalo. Tool YouTube ke apne suggestions se search <b>chauda</b> karta hai (topic + 5 suggestion queries, merge karke, duplicate hataakar) taaki 50 videos ek hi channel ki copy-paste na ho. Har thumbnail OCR + pixel analysis se napa jata hai. Naap <b>views/day</b> par hai, raw views par nahi — warna 3 saal purani video aaj ki nayi video se hamesha jeet jaati.</p>'+
 '<p><b>2. Deep Analysis</b> — 14 patterns (chehra, chehre ka size, text ke shabd, text ka size/contrast, brightness, bheed, rang, taap-mizaaj, composition, title ki lambai, number, sawal, title dohrana) ke har hisse ka median views/day, poore set ke muqable <b>lift</b> ke saath (1.0 = barabar, 1.5× = aadha zyada chala). Plus: jo videos aapne aap 2.5× se upar bhaag rahi hain unki listing, aur ek <b>benchmark table</b> (p10…p90) — "Meri Thumbnail" usi me apni jagah batata hai.</p>'+
 '<p><b>3. Meri Thumbnail</b> — apni file ka path / YouTube link / file chuno. Tool OCR se text padhta hai (320px par alag se, taaki pata chale ki browse par kaun padh sakta hai), chehre dhoondta hai, outline/contrast naapta hai, aur 4 asli YouTube sizes par dikhaata hai. Rules: 1–4 shabd ideal, text 320px par 18px+, contrast 4.5:1 WCAG AA, chehra frame ka 10%+.</p>'+
 '<p><b>4. Behtar banao</b> — kisi bhi thumbnail ke saath. Tool <b>wahi photo rakhta hai</b>: purana text mitaata hai, title se 2–3 behtar shabd chunta hai jo pehle se nahi likhe, unhe khaali jagah par outline ke saath bara likhta hai, rang/sharpen sudharta hai, subject bara karta hai. Phir <b>har version ko dobara napta hai</b> aur score ka farq dikhata hai. Ye deterministic hai — koi AI nahi, isliye result control me rehta hai.</p>'+
  '<p><b>5. AI Thumbnail (Runware) + Thumbnail Generation</b> — nayi tasveer banane ka rasta. 6 models asli test karke chune gaye (cost Runware ke apni deni se, text ki jaanch ClickLab ki apni OCR/score se): default <b>z-image turbo — $0.0006/image, 2 second, text bhi saaf</b>. Ek click me 4 alag soch (~$0.0024-0.0048), har ek ko wahi benchmark se napa jaata hai jo competitors se — jeetne wala khud chuna jaata hai. Rule: scene AI se, <b>shabd Pillow se</b> (AI text likh sakta hai — 24 Oct ko sahi bhi aaya — magar kabhi misspell karta hai, isliye spelling ka zimmeda Pillow par). Thumbnail Generation tab poora hisaab dikhata hai (prices, sizes, reference ka sach, local SD ka rasta).</p>'+
 '<p><b>6. Title Lab</b> — title ko desktop/mobile/sidebar ke pixel width par wrap karke batata hai kitna chars dikhega, aur competitors ke titles se compare karta hai.</p>'+
 '<p><b>7. A/B</b> — variants save karo; YouTube Studio me "Test and compare" se asli winner pata chalta hai. Ye tool sirf tayyari karata hai — pakka faisala apne channel ke data se hi hoga.</p>'+
  '<p class="sub">Chalti kaise hai: yt-dlp + i.ytimg.com + Tesseract + Pillow (+ opencv ho to chehre). Tesseract na ho to OCR wale columns khali rahenge, baaki analysis chalta rahega. Sab kuch <code>thumb_output/</code> me cache hai — dobara scan karne par seconds lagte hain. API key sirf ek kaam par lagti hai: AI Thumbnail (Runware) — aur wo bhi optional hai, Behtar banao aur baaki poora tool bina key ke chalta hai. AI ka har kharcha screen par dikhta hai.</p>'+
 '<p class="sub">Imandari ki baat: ye observation hai, experiment nahi. Ye batata hai ki inhi videos me kaunsa tareeka zyada chala; CTR ka pakka jawab sirf aapke apne A/B se milta hai.</p></div>'}
(async()=>{try{await boot()}catch(e){$("#main").innerHTML='<div class="err">'+esc(e.message)+'</div>'}})();
</script></body></html>"""


if __name__ == "__main__":
    import webbrowser
    for d in (OUT, THUMB_DIR, CHK_DIR, TMP_DIR, SCN_DIR, REG_DIR, OCR_DIR, AI_DIR):
        d.mkdir(parents=True, exist_ok=True)

    def _alive(p):
        # kya ye port pehle se HAMARA ClickLab chala raha hai? /api/ping poochhta
        # hai — doosri misal utha kar doosra port dhoondhne se behtar hai ke
        # maujooda hi khol diya jaye (bat bar-bar dabane par zombie servers na banein).
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % p, timeout=1.2) as r:
                return json.loads(r.read().decode("utf-8", "replace")).get("app") == "clicklab"
        except Exception:
            return False
    if _alive(PORT):
        u0 = "http://127.0.0.1:%d" % PORT
        print("ClickLab pehle se chal raha hai — bas browser khol diya:", u0)
        try:
            webbrowser.open(u0)
        except Exception:
            print("browser apne aap nahi khula — ye address khol lein:", u0)
        raise SystemExit(0)
    srv, port = pick_port()
    url = "http://127.0.0.1:%d" % (port or srv.server_address[1])
    print("ClickLab v3 ->", url)
    # Pehle server: page aur /api foran jawab dein. Tools ki khoj aur bhaari engines
    # background me tayyar hote hain — is se tool kholne ka intezaar seconds se
    # milliseconds aa jata hai, aur jo abhi tayyar nahi uska sach UI me likha rehta hai.
    t0 = time.perf_counter()
    start_warm(2.0)   # browser na khole bhi 2 second baad engines khud tayyar ho jayenge
    # scans ki listing (har scan ka JSON padh kar) pehle hi garam kar do, taake
    # browser khulte hi pehla /api/scans foran jawab de — warna pehli baar me
    # 20+ scans parse hone tak page "Loading…" par atka rehta hai.
    threading.Thread(target=list_scans, daemon=True).start()
    print("pehla jawab ", round(time.perf_counter() - t0, 2), "second me — engines background me tayyar honge")
    # Browser server BIND hone ke BAAD khulta hai (bat file se pehle kholne par
    # browser "refused/loading" dikha kar atak jata tha — ye wahi race thi jo
    # "Loading…" ka sabab banti thi). Adhā second ka waqfa server ke ready hone ka hai.
    def _open():
        try:
            webbrowser.open(url)
        except Exception:
            print("browser apne aap nahi khula — ye address khol lein:", url)
    threading.Timer(0.4, _open).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
