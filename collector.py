# -*- coding: utf-8 -*-
"""
جمع‌کننده تدریجی کانال‌های نورونرس (Telethon — با اکانت خودت).
هسته‌ی استخراج دقیقاً همان منطق اثبات‌شده‌ی اسکریپت‌های خود امیررضا است
(main_admin برای کوییز، extract_hashtags برای محتوای هشتگ‌دار) که
هزاران سوال را با توضیح کامل استخراج کرده‌اند؛ فقط سیم‌کشی بایگانی
(وضعیت، هفته‌ها، خروجی JSON، اجرای GitHub Actions) و ظاهر ورد
(وزیرمتن، راست‌چین، قالب توافق‌شده) دور آن ساخته شده است.

چرا نسخه‌ی قبلی collector توضیح‌ها را خالی می‌گذاشت (۰ از ۱۰۰۰)؟
  - وقتی تلگرام لیست ادمین‌ها را برنمی‌گرداند، اسکریپت قدیمی
    admin_keys را None می‌کرد تا اولین کامنت‌گذار ادمین فرض شود؛
    collector قبلی این پرچم را نداشت و با لیست خالی، هیچ‌کس را
    ادمین نمی‌شناخت (no_admin_found).
  - دنباله‌ی کامنت‌ها باید نسبت به ریشه‌ی واقعی ترد (پیام آینه‌ای
    پست در گروه Discussion) سنجیده شود؛ collector قبلی فرض می‌کرد
    کامنت‌ها مستقیم به آیدی پست کانال ریپلی شده‌اند. این‌جا
    find_root_id ریشه را از روی خودِ ریپلای‌ها پیدا می‌کند.
قانون‌های استخراج (از اسکریپت‌های خودت، بدون تغییر):
  - جواب صحیح از خود نظرسنجی (poll.results)؛ اگر هنوز دیده نمی‌شود
    و config: allow_vote=true، یک رای به گزینه اول داده می‌شود تا
    تلگرام جواب را نشان دهد؛ نتیجه رای مهم نیست. فقط اگر در کامنت
    صریحاً «گزینه ب» و... آمده بود، به‌عنوان حدس علامت‌دار ثبت
    می‌شود (answer_source=comment_guess).
  - توضیح فقط از اولین ادمینِ کامنت‌گذار، فقط پیام‌های متوالی همان
    ادمین، سقف ۷ پیام برای کوییز و ۹ پیام برای محتوای تصویری؛ فقط
    ریپلای به خودِ پست (ریشه‌ی ترد) یا ریپلای به پیام قبلی خودش؛
    پیام با پروفایل گروه/کانال (c) و پیام بدون فرستنده (anon) هم
    ادمین است؛ حساب‌های سرویس تلگرام (ALWAYS_ADMIN_USER_IDS) همیشه
    ادمین‌اند. اگر هیچ ادمینی پیدا نشد، همان قانون روی اولین
    کامنت‌گذار اعمال می‌شود و در ورد مشخص می‌شود که از ادمین نیست.
  - صورت سوال: اگر کوییز ریپلای به پیامی باشد، آن پیام (متن/عکس)
    جزو صورت سوال است. پیام بالای سوال فقط برای شماره‌های داخل
    config (preceding_stem_numbers).
  - عکس صورت سوال دانلود می‌شود؛ عکس کامنت نه. توضیح فقط‌عکس:
    «فقط عکس بود» نوشته می‌شود. PDF ضمیمه (تا ۳۰ مگ) دانلود می‌شود.
  - شماره چاپ‌شده لاتین ابتدای سوال، شماره سوال در ورد است.
اجرا:  python collector.py --collect --build --limit 1000
       python collector.py --recheck-missing [N] --build
       python collector.py --backfill-previous [--build]   # یک‌بارمصرف: پیام بالای ۸ شماره‌ی preceding_stem_numbers
در GitHub Actions با Secretها اجرا می‌شود؛ هیچ رمزی در کد نیست.
"""
import argparse
import asyncio
import copy
import json
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

TEHRAN = ZoneInfo("Asia/Tehran")
STATE_PATH = "data/state.json"
IMAGES_DIR = "out/images"
FILES_DIR = "data/files"

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import FloodWaitError, RPCError
    from telethon.tl.types import (
        MessageMediaPoll, MessageMediaPhoto, MessageMediaDocument,
        MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
        MessageEntityStrike, MessageEntityTextUrl,
        ChannelParticipantsAdmins, PeerUser, PeerChannel, PeerChat,
    )
    from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
    from telethon.tl.functions.messages import SendVoteRequest
except ImportError:
    print("Telethon نصب نیست: pip install -r requirements.txt")
    sys.exit(1)

# --- ثابت‌های استخراج (از اسکریپت‌های خودت) ---
PREVIOUS_MESSAGE_QUESTIONS = {1055, 869, 809, 1367, 665, 658, 46, 719}
MAX_ADMIN_MESSAGES_QUIZ = 7
MAX_ADMIN_MESSAGES_VISUAL = 9
SCAN_LIMIT_QUIZ = 30
SCAN_LIMIT_VISUAL = 40
ONLY_SAME_ADMIN = True
START_AT_FIRST_ADMIN_COMMENT = True
FALLBACK_FIRST_COMMENTER = True
INCLUDE_COMMENT_MEDIA = False
USE_REPLY_RULE = True
ALWAYS_ADMIN_USER_IDS = {136817688, 1087968824}
DOWNLOAD_PDFS = True
MAX_PDF_MB = 30
SAVE_EVERY = 50
OPTION_LABELS = ["الف", "ب", "ج", "د", "ه", "و", "ز", "ح"]
PERSIAN_LETTER_MAP = {"الف": 1, "ب": 2, "ج": 3, "د": 4, "ه": 5, "و": 6, "ز": 7, "ح": 8}
ENGLISH_LETTER_MAP = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8}


def log_error(msg):
    print(f"خطا: {msg}")


def log_info(msg):
    print(msg)


# ---------- config / state ----------

def load_config():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "items": [], "last_seen": {}, "updated_at": None}


def save_state(state):
    state["updated_at"] = datetime.now(TEHRAN).isoformat()
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _sync_state(state, items_by_key):
    # پیشرفت تا اینجا را در state بنویس تا اگر اجرا نیمه‌کاره ماند،
    # اجرای بعد از همان‌جا ادامه دهد، نه از صفر.
    state["items"] = sorted(
        items_by_key.values(),
        key=lambda x: (x.get("date", ""), x.get("channel_msg_id", 0)),
    )
    save_state(state)


def week_key_for(dt_tehran):
    """جمعه ۰۰:۰۰ تهران شروع هفته است. dt را به شروع همان هفته ببر."""
    d = dt_tehran.date()
    days_since_friday = (d.weekday() - 4) % 7  # Monday=0 ... Friday=4
    start = d - timedelta(days=days_since_friday)
    return start.isoformat()


# ---------- متن ----------

def normalize_digits(text):
    if not text:
        return ""
    persian = "۰۱۲۳۴۵۶۷۸۹"
    arabic = "٠١٢٣٤٥٦٧٨٩"
    western = "0123456789"
    return text.translate(str.maketrans(persian + arabic, western + western))


def find_answer_index(text):
    """حالت پشتیبان: تشخیص جواب از روی متن کامنت‌ها"""
    if not text:
        return None
    normalized = normalize_digits(text)
    patterns = [
        r"گزینه\s*(?:ی)?\s*([1-8])",
        r"گزینه\s*(?:ی|‌ی)?\s*(الف|ب|ج|د|ه|و|ز|ح)",
        r"پاسخ\s*(?:صحیح)?\s*[:\-،]?\s*(الف|ب|ج|د|ه|و|ز|ح)\b",
        r"پاسخ\s*(?:صحیح)?\s*[:\-،]?\s*([1-8])\b",
        r"جواب\s*(?:صحیح)?\s*[:\-،]?\s*(الف|ب|ج|د|ه|و|ز|ح)\b",
        r"جواب\s*(?:صحیح)?\s*[:\-،]?\s*([1-8])\b",
        r"answer\s*[:\-]?\s*(?:is|option)?\s*([A-Ha-h])\b",
        r"answer\s*[:\-]?\s*(?:is|option)?\s*([1-8])\b",
        r"correct\s*(?:answer)?\s*[:\-]?\s*(?:option)?\s*([1-8])\b",
        r"correct\s*(?:answer)?\s*[:\-]?\s*(?:option)?\s*([A-Ha-h])\b",
        r"[✔✅☑✓]\uFE0F?\s*([1-8])",
    ]
    for pat in patterns:
        m = re.search(pat, normalized, flags=re.IGNORECASE)
        if m:
            token = m.group(1)
            if token in PERSIAN_LETTER_MAP:
                return PERSIAN_LETTER_MAP[token]
            if token.lower() in ENGLISH_LETTER_MAP:
                return ENGLISH_LETTER_MAP[token.lower()]
            if token.isdigit():
                return int(token)
    return None


_INVISIBLE = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
             "\u2066\u2067\u2068\u2069\ufeff\ufe0f"), None)


def parse_channel_number(question_text):
    """
    شماره‌ی سوال را از ابتدای متن خودِ کوییز می‌خواند. نمونه‌هایی که پشتیبانی می‌شوند:
    '1773. #روان ...'   '⭐️ 567. #داخلی ...'   '⭐️ #582. #داخلی ...'   '142‌. #ویژه ...' (نیم‌فاصله قبل از نقطه)
    خط اول بررسی می‌شود؛ فقط اگر خط اول فقط هشتگ بود (مثل '#CCU') خط دوم هم دیده می‌شود.
    به این ترتیب فهرست‌های شماره‌دار داخل متن سوال اشتباه گرفته نمی‌شوند.
    """
    t = normalize_digits(question_text or "").translate(_INVISIBLE)
    lines = [ln for ln in t.split("\n") if ln.strip()]
    pattern = r"(?:#\S+\s+)*(?:سوال|تست|شماره)?\s*[#(\[]?(\d{1,5})\s*[\.\-–—:)\]]"
    for ln in lines[:2]:
        ln = re.sub(r"^[^\w#]+", "", ln)     # حذف ایموجی و نشانه‌های ابتدای خط
        m = re.match(pattern, ln)
        if m:
            return int(m.group(1))
        if not re.fullmatch(r"\s*(?:#\S+\s*)+", ln):
            break
    return None


def _clean_for_number(text):
    """
    متن را برای تشخیص شماره/پیشوند تمیز می‌کند و نگاشت ایندکس برمی‌گرداند:
    (cleaned, index_map) که index_map[i] ایندکس کاراکتر iامِ متن تمیز در متن
    اصلی است و index_map[len(cleaned)] == len(text). تمیز کردن فقط حذف است
    (کاراکتر نامرئی در کل متن + ایموجی/نشانه‌های ابتدای هر خط) و ترتیب
    کاراکترها عوض نمی‌شود؛ پس با نگاشت می‌شود انتهای پیشوندِ پیدا‌شده در متن
    تمیز را به متن اصلی برگرداند. normalize_digits طول را عوض نمی‌کند.
    """
    t = normalize_digits(text or "")
    kept_idx = [i for i, ch in enumerate(t) if ord(ch) not in _INVISIBLE]
    s1 = "".join(t[i] for i in kept_idx)
    lines = s1.split("\n")
    out_chars, out_idx = [], []
    pos = 0
    for li, ln in enumerate(lines):
        m = re.match(r"^[^\w#]+", ln)
        skip = m.end() if m else 0
        for j in range(skip, len(ln)):
            out_chars.append(ln[j])
            out_idx.append(kept_idx[pos + j])
        if li < len(lines) - 1:
            out_chars.append("\n")
            out_idx.append(kept_idx[pos + len(ln)])
        pos += len(ln) + 1
    out_idx.append(len(t))
    return "".join(out_chars), out_idx


def parse_printed_number(text):
    """(شماره چاپ‌شده، متن سوال بدون پیشوند شماره) — برای ورد، شماره در
    تیتر «سوال N» می‌آید و اول متن سوال تکرار نمی‌شود. پیشوند با همان
    پاک‌سازی parse_channel_number (نامرئی + ایموجی ابتدای خط) پیدا می‌شود
    تا شماره‌ی سخت (مثل '⭐️ 567.') هم حذف شود، نه فقط پیدا؛ prefix_len
    مثل قبل از اختلاف طول رشته‌ی اصلی و رشته‌ی بدون پیشوند حساب می‌شود."""
    if not text:
        return None, text
    num = parse_channel_number(text)
    if num is None:
        return None, text
    cleaned, index_map = _clean_for_number(text)
    m = re.match(
        r"(?:#\S+\s+)*(?:سوال|تست|شماره)?\s*[#(\[]?\d{1,5}\s*[\.\-–—:)\]]",
        cleaned,
    )
    if m:
        stripped = text[index_map[m.end()]:].lstrip()
        return num, stripped
    return num, text


def message_to_segments(text, entities):
    """
    offset در تلگرام بر اساس UTF-16 است، پس همان‌طور محاسبه می‌شود.
    بولد، ایتالیک، زیرخط، خط‌خورده و لینک‌های مخفی (TextUrl) حفظ می‌شوند.
    """
    if not text:
        return []
    raw = text.encode("utf-16-le")
    n = len(raw) // 2
    flags = [0] * n
    urls = [None] * n
    for ent in entities or []:
        start = max(0, ent.offset)
        end = min(n, ent.offset + ent.length)
        if isinstance(ent, MessageEntityTextUrl):
            for k in range(start, end):
                urls[k] = ent.url
            continue
        if isinstance(ent, MessageEntityBold):
            bit = 1
        elif isinstance(ent, MessageEntityItalic):
            bit = 2
        elif isinstance(ent, MessageEntityUnderline):
            bit = 4
        elif isinstance(ent, MessageEntityStrike):
            bit = 8
        else:
            continue
        for k in range(start, end):
            flags[k] |= bit

    segments = []
    i = 0
    while i < n:
        j = i
        while j < n and flags[j] == flags[i] and urls[j] == urls[i]:
            j += 1
        chunk = raw[i * 2:j * 2].decode("utf-16-le", errors="ignore")
        if chunk:
            f = flags[i]
            segments.append(
                {"t": chunk, "b": bool(f & 1), "i": bool(f & 2), "u": bool(f & 4),
                 "s": bool(f & 8), "url": urls[i]}
            )
        i = j
    return segments


def segments_from(obj):
    if obj is None:
        return [{"t": "", "b": False}]
    if isinstance(obj, str):
        return [{"t": obj, "b": False}]
    return message_to_segments(getattr(obj, "text", "") or "", getattr(obj, "entities", None))


def seg_text(segments):
    return "".join(s.get("t", "") for s in (segments or []))


def extract_text(obj):
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "text"):
        return obj.text
    return str(obj)


# ---------- ادمین‌ها و کامنت‌ها (از اسکریپت‌های خودت) ----------

def sender_key(msg):
    """
    هویت فرستنده: ('u', id) برای حساب کاربری، ('c', id) برای کانال/گروه
    (یعنی پیامی که با «نام و عکس پروفایل گروه» ارسال شده).
    علت باگ قبلی: تلگرام شناسه‌ی گروه/کانال را با پیشوند 100- برمی‌گرداند و با
    شناسه‌ی ساده مقایسه نمی‌شد؛ این تابع هر دو را یکسان می‌کند.
    """
    fid = getattr(msg, "from_id", None)
    if isinstance(fid, PeerUser):
        return ("u", fid.user_id)
    if isinstance(fid, PeerChannel):
        return ("c", fid.channel_id)
    if isinstance(fid, PeerChat):
        return ("c", fid.chat_id)
    sid = getattr(msg, "sender_id", None)
    if sid is None:
        return ("anon", 0)   # فرستنده مشخص نیست (معمولاً ادمین ناشناس / پروفایل گروه)
    if sid > 0:
        return ("u", sid)
    s = str(-sid)
    if s.startswith("100") and len(s) > 10:
        return ("c", int(s[3:]))
    return ("c", -sid)


def entity_label(ent):
    title = getattr(ent, "title", None)
    if title:
        return f"{title} (گروه/کانال)"
    name = " ".join(p for p in (getattr(ent, "first_name", None), getattr(ent, "last_name", None)) if p)
    uname = getattr(ent, "username", None)
    if uname:
        name = f"{name} @{uname}".strip()
    return name.strip() or "؟"


async def _admin_ids_of(client, target):
    """
    شناسه‌ی همه‌ی ادمین‌ها را مستقیم از لیست شرکت‌کنندگان می‌خواند. با این روش
    ادمین‌های «Deleted Account» (حساب حذف‌شده) هم شناسایی می‌شوند، چون فقط به شناسه
    نیاز داریم نه به اطلاعات حساب. ربات‌ها (مثل ربات‌های نگهبان) جدا نگه داشته می‌شوند.
    """
    admins, bots, labels = set(), set(), {}
    offset = 0
    for _ in range(100):
        res = await client(GetParticipantsRequest(
            channel=target, filter=ChannelParticipantsAdmins(), offset=offset, limit=100, hash=0))
        participants = getattr(res, "participants", None) or []
        if not participants:
            break
        users = {u.id: u for u in (getattr(res, "users", None) or [])}
        for p in participants:
            uid = getattr(p, "user_id", None)
            if uid is None:
                continue
            u = users.get(uid)
            if u is not None and getattr(u, "bot", False):
                bots.add(uid)
                labels[uid] = f"{entity_label(u)} (ربات - کنار گذاشته شد)"
                continue
            admins.add(uid)
            if u is None or getattr(u, "deleted", False):
                labels[uid] = f"حساب حذف‌شده ({uid})"
            else:
                labels[uid] = entity_label(u)
        offset += len(participants)
    return admins, bots, labels


async def collect_admin_keys(client, entity, extra_admins):
    """
    هویت ادمین‌ها را جمع می‌کند: ادمین‌های کانال و گروه Discussion (حتی حساب‌های
    حذف‌شده)، خودِ کانال و خودِ گروه (ارسال با نام/پروفایل گروه)، و هر یوزرنیم/آیدی
    که دستی داده شده باشد. ربات‌های ادمین (مثل نگهبان) ادمین حساب نمی‌شوند.
    خروجی: (مجموعه هویت‌ها, آیا ادمین واقعی پیدا شد, لیست نام‌ها)
    """
    keys = {("c", entity.id)}
    keys.update(("u", uid) for uid in ALWAYS_ADMIN_USER_IDS)
    names = {}
    found_real_admin = False
    targets = [entity]

    try:
        full = await client(GetFullChannelRequest(entity))
        linked_id = getattr(full.full_chat, "linked_chat_id", None)
        if linked_id:
            keys.add(("c", linked_id))
            linked = next((c for c in full.chats if c.id == linked_id), None)
            if linked is not None:
                targets.append(linked)
    except Exception as e:
        log_error(f"خطا در پیدا کردن گروه Discussion: {e}")

    for target in targets:
        try:
            admins, bots, labels = await _admin_ids_of(client, target)
            for uid in admins:
                keys.add(("u", uid))
                found_real_admin = True
            for uid, lb in labels.items():
                names[("u", uid)] = lb
        except Exception as e:
            log_error(f"خطا در گرفتن لیست ادمین‌ها: {e}")

    for ident in extra_admins:
        try:
            ref = int(ident) if str(ident).lstrip("-").isdigit() else ident
            ent = await client.get_entity(ref)
            kind = "c" if getattr(ent, "title", None) else "u"
            keys.add((kind, ent.id))
            names[(kind, ent.id)] = entity_label(ent)
            found_real_admin = True
        except Exception as e:
            print(f"هشدار: ادمین دستی '{ident}' پیدا نشد.")
            log_error(f"خطا در پیدا کردن ادمین دستی {ident}: {e}")

    return keys, found_real_admin, list(names.values())


def reply_target_id(msg):
    rt = getattr(msg, "reply_to", None)
    return getattr(rt, "reply_to_msg_id", None) if rt else None


def find_root_id(comments):
    """شناسه‌ی پیام اصلی (خودِ پست در گروه Discussion) را از روی ریپلای‌ها پیدا می‌کند"""
    counts = {}
    for c in comments:
        rt = getattr(c, "reply_to", None)
        if not rt:
            continue
        rid = getattr(rt, "reply_to_top_id", None) or getattr(rt, "reply_to_msg_id", None)
        if rid:
            counts[rid] = counts.get(rid, 0) + 1
    return max(counts, key=counts.get) if counts else None


def select_admin_run(comments, admin_keys, max_run):
    """
    از لیست کامنت‌ها (قدیمی به جدید) اولین دنباله‌ی متوالی پیام‌های ادمین را
    (حداکثر max_run) برمی‌گرداند:
      - از اولین پیام ادمینی شروع می‌شود که روی خودِ پست/تست ریپلی شده باشد
      - ادامه می‌دهد تا وقتی پیام ادمین (همان ادمین) پشت سر هم باشد و هر پیام
        یا روی خودِ پست ریپلی شده باشد یا روی پیام قبلیِ همان ادمین
      - به محض اینکه پیام یک نفر دیگر بیاید، دنباله قطع می‌شود
      - ادمین‌هایی که روی کامنت بقیه ریپلی کرده‌اند نادیده گرفته می‌شوند
    اگر admin_keys برابر None باشد، فرستنده‌ی اولین کامنت به‌عنوان ادمین فرض می‌شود.
    """
    if not comments:
        return []

    by_id = {c.id: c for c in comments}
    root_id = find_root_id(comments)

    def is_admin(msg):
        k = sender_key(msg)
        if admin_keys is None:
            return k is not None and k == sender_key(comments[0])
        # فقط ادمین‌ها می‌توانند با نام کانال/گروه پیام بفرستند، پس هر فرستنده از نوع
        # کانال/گروه/ناشناس (حتی اگر شناسه‌اش در لیست نباشد) ادمین حساب می‌شود
        return k in admin_keys or (k is not None and k[0] in ("c", "anon"))

    def replies_to_root(msg):
        if not USE_REPLY_RULE:
            return True
        tgt = reply_target_id(msg)
        return tgt is None or tgt == root_id

    def replies_ok(msg, ident):
        if replies_to_root(msg):
            return True
        parent = by_id.get(reply_target_id(msg))
        if parent is None:
            return False
        if ONLY_SAME_ADMIN:
            return sender_key(parent) == ident
        return is_admin(parent)

    start = None
    for idx, c in enumerate(comments):
        if is_admin(c) and replies_to_root(c):
            start = idx
            break
        if not START_AT_FIRST_ADMIN_COMMENT:
            break
    if start is None:
        return []

    ident = sender_key(comments[start])
    run = []
    for c in comments[start:]:
        if len(run) >= max_run:
            break
        if not is_admin(c):
            break
        if ONLY_SAME_ADMIN and sender_key(c) != ident:
            break
        if not replies_ok(c, ident):
            break
        run.append(c)
    return run


async def fetch_comments(client, entity, post_id, scan_limit):
    msgs = []
    try:
        async for reply in client.iter_messages(
            entity, reply_to=post_id, reverse=True, limit=scan_limit
        ):
            if getattr(reply, "action", None):
                continue
            msgs.append(reply)
    except FloodWaitError:
        raise
    except Exception as e:
        log_error(f"خطا در خواندن کامنت‌های پست {post_id}: {e}")
    return msgs


async def fetch_unit_comments(client, entity, unit, scan_limit):
    """
    برای آلبوم، کامنت‌ها روی یکی از پیام‌های آلبوم قرار دارد؛
    پیامی که تعداد کامنتش بیشتر از صفر است انتخاب می‌شود.
    """
    with_info = [m for m in unit if getattr(m, "replies", None) is not None]
    if with_info:
        candidates = [m for m in with_info if (m.replies.replies or 0) > 0]
    else:
        candidates = list(unit)
    for m in candidates:
        msgs = await fetch_comments(client, entity, m.id, scan_limit)
        if msgs:
            return msgs
    return []


# ---------- جواب صحیح و توضیح داخل کوییز (از خود تلگرام) ----------

def correct_index_from_results(poll_obj, results):
    if not results or not getattr(results, "results", None):
        return None
    for i, ans in enumerate(poll_obj.answers):
        for res in results.results:
            if res.option == ans.option and getattr(res, "correct", False):
                return i + 1
    return None


def poll_solution_segments(results):
    """توضیح داخل خودِ کوییز (علامت لامپ) که بعد از پاسخ‌دادن آشکار می‌شود"""
    if results is None:
        return []
    sol = getattr(results, "solution", None)
    if not sol:
        return []
    return message_to_segments(sol, getattr(results, "solution_entities", None))


async def get_quiz_info(client, entity, message, poll_obj, allow_vote):
    """
    خروجی: (شماره‌ی گزینه‌ی صحیح یا None, توضیح داخل کوییز).
    اگر کوییز هنوز پاسخ داده نشده باشد و allow_vote فعال باشد (با اجازه
    امیررضا، 2026-11-17)، یک گزینه انتخاب می‌شود تا تلگرام جواب
    و توضیح را آشکار کند؛ نتیجه رای برای او مهم نیست.
    """
    res = getattr(message.poll, "results", None)
    idx = correct_index_from_results(poll_obj, res)
    if idx:
        return idx, poll_solution_segments(res)

    if not getattr(poll_obj, "quiz", False) or not poll_obj.answers or getattr(poll_obj, "closed", False):
        return None, poll_solution_segments(res)

    if not allow_vote:
        return None, poll_solution_segments(res)

    vote_result = None
    try:
        vote_result = await client(
            SendVoteRequest(peer=entity, msg_id=message.id, options=[poll_obj.answers[0].option])
        )
    except FloodWaitError:
        raise
    except Exception as e:
        log_error(f"خطا در رای‌دادن به پیام {message.id} (شاید قبلاً رای داده شده): {e}")

    for upd in getattr(vote_result, "updates", None) or []:
        if hasattr(upd, "results") and hasattr(upd, "poll_id"):
            idx = correct_index_from_results(poll_obj, upd.results)
            if idx:
                return idx, poll_solution_segments(upd.results)

    try:
        fresh = await client.get_messages(entity, ids=message.id)
        if fresh and fresh.poll:
            r = fresh.poll.results
            return correct_index_from_results(poll_obj, r), poll_solution_segments(r)
    except FloodWaitError:
        raise
    except Exception as e:
        log_error(f"خطا در خواندن مجدد نتیجه نظرسنجی {message.id}: {e}")
    return None, []


# ---------- پیام‌های زمینه‌ای: ریپلای و پیام بالای سوال ----------

def _has_photo(msg):
    media = getattr(msg, "media", None)
    if isinstance(media, MessageMediaPhoto):
        return True
    if isinstance(media, MessageMediaDocument):
        mime = getattr(getattr(msg, "file", None), "mime_type", None)
        return mime in ("image/jpeg", "image/png")
    return bool(getattr(msg, "photo", None))


def _msg_text(msg):
    return getattr(msg, "raw_text", None) or getattr(msg, "text", "") or ""


async def fetch_replied_unit(client, entity, message):
    """پیامی (یا آلبومی) که کوییز روی آن ریپلی شده است؛ بخشی از صورت سوال"""
    rt = getattr(message, "reply_to", None)
    rid = getattr(rt, "reply_to_msg_id", None) if rt else None
    if not rid:
        return []
    if getattr(rt, "reply_to_peer_id", None) is not None:
        return []   # ریپلای روی پیامی از چت دیگر
    target = await client.get_messages(entity, ids=rid)
    if not target or getattr(target, "action", None):
        return []
    if target.poll:
        log_info(f"کوییز {message.id} روی یک نظرسنجی دیگر ریپلی شده؛ نادیده گرفته شد.")
        return []
    if target.grouped_id:
        neighbors = await client.get_messages(entity, ids=list(range(max(1, rid - 9), rid + 10)))
        unit = [m for m in neighbors if m and getattr(m, "grouped_id", None) == target.grouped_id]
        unit.sort(key=lambda m: m.id)
        return unit or [target]
    return [target]


async def fetch_previous_unit(client, entity, message_id):
    """پیام (یا آلبومِ) دقیقاً بالای کوییز در کانال"""
    older = []
    async for m in client.iter_messages(entity, max_id=message_id, limit=12):
        if getattr(m, "action", None):
            continue
        older.append(m)
    if not older:
        return []
    first = older[0]
    if first.poll:
        return []
    if first.grouped_id:
        unit = [m for m in older if m.grouped_id == first.grouped_id]
    else:
        unit = [first]
    unit.sort(key=lambda m: m.id)
    return unit


async def download_image(client, msg, stem, ext):
    path = os.path.join(IMAGES_DIR, f"{stem}{ext}")
    if os.path.exists(path):
        return [{"type": "image", "path": path}]
    try:
        os.makedirs(IMAGES_DIR, exist_ok=True)
        saved = await client.download_media(msg, file=path)
        if saved:
            return [{"type": "image", "path": saved}]
    except FloodWaitError:
        raise
    except Exception as e:
        log_error(f"خطا در دانلود تصویر {stem}: {e}")
    return [{"type": "note", "text": "[تصویری در این پیام بود که دانلود نشد]"}]


async def media_items(client, msg, stem, link=None):
    media = msg.media
    if media is None:
        return []

    if isinstance(media, MessageMediaPhoto):
        return await download_image(client, msg, stem, ".jpg")

    if isinstance(media, MessageMediaDocument):
        if getattr(msg, "sticker", None):
            return []
        f = msg.file
        mime = (f.mime_type or "") if f else ""
        name = (f.name or "") if f else ""
        size = (f.size or 0) if f else 0

        if mime in ("image/jpeg", "image/png"):
            return await download_image(client, msg, stem, ".png" if mime == "image/png" else ".jpg")

        if mime == "application/pdf" and DOWNLOAD_PDFS and size <= MAX_PDF_MB * 1024 * 1024:
            os.makedirs(FILES_DIR, exist_ok=True)
            path = os.path.join(FILES_DIR, f"{stem}.pdf")
            try:
                if not os.path.exists(path):
                    await client.download_media(msg, file=path)
                return [{"type": "note",
                         "text": f"[فایل PDF ضمیمه: {name or 'PDF'}]"}]
            except FloodWaitError:
                raise
            except Exception as e:
                log_error(f"خطا در دانلود PDF {stem}: {e}")

        if getattr(msg, "video", None) or getattr(msg, "video_note", None) or getattr(msg, "gif", None):
            kind = "ویدیو"
        elif getattr(msg, "voice", None) or getattr(msg, "audio", None):
            kind = "صوت"
        else:
            kind = "فایل"
        text = f"[{kind} ضمیمه: {name}]" if name else f"[{kind} ضمیمه]"
        if link:
            text += f" — لینک پیام: {link}"
        return [{"type": "note", "text": text}]

    return []


def text_items(msg):
    segments = message_to_segments(msg.raw_text or "", msg.entities)
    if segments and any(s["t"].strip() for s in segments):
        return [{"type": "text", "segments": segments}]
    return []


async def unit_content(client, unit, stem, base_link):
    """محتوای کامل یک پیام/آلبوم: اول رسانه‌ها (عکس، PDF، ...) بعد متن با قالب‌بندی"""
    items = []
    for m in unit:
        items.extend(await media_items(client, m, f"{stem}{m.id}", f"{base_link}/{m.id}"))
    for m in unit:
        items.extend(text_items(m))
    return items


def explanation_items_from_run(run):
    """متن کامنت‌های ادمین؛ کامنتی که فقط عکس بود «فقط عکس بود» می‌شود.
    عکس کامنت هرگز دانلود نمی‌شود (INCLUDE_COMMENT_MEDIA=False)."""
    items = []
    for c in run:
        parts = text_items(c)
        if parts:
            items.extend(parts)
        elif _has_photo(c):
            items.append({"type": "image", "text": "فقط عکس بود"})
    return items


# ---------- پردازش یک سوال / یک پست تصویری ----------

UNRECOGNIZED = {}   # فرستنده‌هایی که کامنت اولشان ادمین/معتبر حساب نشد (برای عیب‌یابی)


def sender_name(msg):
    s = getattr(msg, "sender", None)
    return entity_label(s) if s is not None else "؟"


def describe_comment(c, count):
    """توصیف کوتاه اولین کامنت برای عیب‌یابی در گزارش"""
    fid = getattr(c, "from_id", None)
    who = None
    if fid is not None:
        who = getattr(fid, "user_id", None) or getattr(fid, "channel_id", None) or getattr(fid, "chat_id", None)
    rt = getattr(c, "reply_to", None)
    return (f"{count} کامنت؛ اولی: from_id={type(fid).__name__ if fid is not None else None}:{who} "
            f"reply_to={getattr(rt, 'reply_to_msg_id', None)} top={getattr(rt, 'reply_to_top_id', None)}")


def _stem_from_context(context):
    """اولین گروه زمینه‌ای را به شکل stem تخت (سازگار با state قدیمی) برمی‌گرداند."""
    if not context:
        return None
    g = context[0]
    text = ""
    segments = []
    photo_path = None
    for it in g["items"]:
        if it["type"] == "text":
            text += seg_text(it.get("segments"))
            segments.extend(it.get("segments") or [])
        elif it["type"] == "image" and photo_path is None:
            photo_path = it.get("path")
    source = "replied_message" if g["kind"] == "reply" else "previous"
    return {"source": source, "message_id": g["first_id"], "text": text,
            "segments": segments, "photo_path": photo_path}


def _first_image_path(context):
    for g in context or []:
        for it in g["items"]:
            if it["type"] == "image":
                return it.get("path")
    return None


async def process_poll(client, entity, message, admin_keys, base_link, previous_numbers,
                       allow_vote, max_admin_messages):
    poll_obj = message.poll.poll

    answer_index, solution = await get_quiz_info(client, entity, message, poll_obj, allow_vote)
    answer_source = None
    if answer_index is not None:
        # get_quiz_info جواب را از خود نظرسنجی (با رای یا بدون رای) گرفته است
        answer_source = "poll"

    question_text = extract_text(poll_obj.question)
    options = [extract_text(a.text) for a in poll_obj.answers]
    number, stripped = parse_printed_number(question_text)
    # سگمنت‌های سوال با جابه‌جایی entities بعد از حذف پیشوند شماره
    prefix_len = len(question_text) - len(stripped)
    entities = []
    for ent in getattr(poll_obj.question, "entities", None) or []:
        try:
            start, end = ent.offset, ent.offset + ent.length
        except AttributeError:
            continue
        if end <= prefix_len:
            continue
        ent2 = copy.copy(ent)
        ent2.offset = max(0, start - prefix_len)
        ent2.length = end - max(start, prefix_len)
        if ent2.length > 0:
            entities.append(ent2)
    q_segs = message_to_segments(stripped, entities)
    options_segs = [segments_from(a.text) for a in poll_obj.answers]

    # --- صورت سوال: ریپلای + (برای شماره‌های مشخص) پیام بالای سوال ---
    context = []
    seen_ids = set()
    reply_unit = await fetch_replied_unit(client, entity, message)
    if reply_unit:
        items = await unit_content(client, reply_unit, "ctx", base_link)
        context.append({"first_id": reply_unit[0].id, "kind": "reply", "items": items})
        seen_ids.update(m.id for m in reply_unit)
    if number in previous_numbers:
        prev_unit = await fetch_previous_unit(client, entity, message.id)
        if prev_unit and not (seen_ids & {m.id for m in prev_unit}):
            items = await unit_content(client, prev_unit, "ctx", base_link)
            context.append({"first_id": prev_unit[0].id, "kind": "previous", "items": items})

    # --- کامنت‌های ادمین (و در صورت نبودن ادمین، اولین کامنت‌دهنده) ---
    comments = await fetch_comments(client, entity, message.id, SCAN_LIMIT_QUIZ)
    run = select_admin_run(comments, admin_keys, max_admin_messages)
    comment_source = "admin" if run else "none"
    admin_diag = "admin" if run else ("no_comments" if not comments else "no_admin_found")
    debug = ""
    if comments and not run:
        k = sender_key(comments[0])
        rec = UNRECOGNIZED.setdefault(k, [sender_name(comments[0]), 0])
        rec[1] += 1
        if FALLBACK_FIRST_COMMENTER:
            run = select_admin_run(comments, None, max_admin_messages)
            if run:
                comment_source = "first_person"
                admin_diag = "first_person"
        debug = describe_comment(comments[0], len(comments))

    comments_items = explanation_items_from_run(run)

    # توضیح کامل: اول توضیح داخل خود کوییز (لامپ)، بعد کامنت‌های ادمین
    expl = []
    if solution:
        expl.append({"type": "text", "segments": solution})
    expl.extend(comments_items)

    if answer_index is None:
        parts = ["".join(s["t"] for s in solution)]
        parts += ["".join(s["t"] for s in it["segments"]) for it in comments_items if it["type"] == "text"]
        g = find_answer_index("\n".join(parts))
        if g:
            answer_index, answer_source = g, "comment_guess"

    dt = (message.date or datetime.now(TEHRAN)).astimezone(TEHRAN)
    stem = _stem_from_context(context)
    return {
        "source": "quiz", "kind": "quiz", "channel_msg_id": message.id,
        "date": dt.date().isoformat(), "time_tehran": dt.strftime("%H:%M"),
        "week_key": week_key_for(dt),
        "printed_number": number, "question": stripped,
        "question_segments": q_segs, "options": options,
        "options_segments": options_segs,
        "answer_index": answer_index, "answer_source": answer_source,
        "stem": stem, "contexts": context,
        "explanation_items": expl,
        "explanation_from_admin": comment_source != "first_person",
        "admin_diag": admin_diag, "comment_source": comment_source,
        "comments_scanned": len(comments), "debug": debug,
        "status": "pending",
        "image_path": _first_image_path(context),
    }


async def process_visual(client, entity, unit, admin_keys, base_link, hashtags,
                         max_admin_messages):
    """یک پست/آلبوم تصویری: رسانه‌ها + متن + کامنت ادمین (حداکثر ۹ پیام)."""
    combined = "\n".join((m.raw_text or "") for m in unit)
    tags = find_tags(combined, hashtags)
    if not tags:
        return None

    first_id = unit[0].id
    post_items = []
    for m in unit:
        post_items.extend(await media_items(client, m, f"p{m.id}", f"{base_link}/{m.id}"))
    for m in unit:
        post_items.extend(text_items(m))

    caption = ""
    caption_segments = []
    images, notes = [], []
    for it in post_items:
        if it["type"] == "text":
            caption += seg_text(it.get("segments"))
            caption_segments.extend(it.get("segments") or [])
        elif it["type"] == "image":
            images.append(it.get("path"))
        elif it["type"] == "note":
            notes.append(it.get("text", ""))

    comments = await fetch_unit_comments(client, entity, unit, SCAN_LIMIT_VISUAL)
    run = select_admin_run(comments, admin_keys, max_admin_messages)
    comment_source = "admin" if run else "none"
    admin_diag = "admin" if run else ("no_comments" if not comments else "no_admin_found")
    debug = ""
    if comments and not run:
        k = sender_key(comments[0])
        rec = UNRECOGNIZED.setdefault(k, [sender_name(comments[0]), 0])
        rec[1] += 1
        if FALLBACK_FIRST_COMMENTER:
            run = select_admin_run(comments, None, max_admin_messages)
            if run:
                comment_source = "first_person"
                admin_diag = "first_person"
        debug = describe_comment(comments[0], len(comments))

    expl = explanation_items_from_run(run)

    dt = (unit[0].date or datetime.now(TEHRAN)).astimezone(TEHRAN)
    return {
        "source": "visual", "kind": "visual", "channel_msg_id": first_id,
        "date": dt.date().isoformat(), "time_tehran": dt.strftime("%H:%M"),
        "week_key": week_key_for(dt),
        "message_ids": [m.id for m in unit],
        "hashtags": tags, "caption": caption,
        "caption_segments": caption_segments,
        "image_path": images[0] if images else None,
        "images": images, "notes": notes,
        "explanation_items": expl,
        "explanation_from_admin": comment_source != "first_person",
        "admin_diag": admin_diag, "comment_source": comment_source,
        "comments_scanned": len(comments), "debug": debug,
        "status": "pending",
    }


def minimal_item(message):
    """اگر پردازش کامل شکست خورد، حداقل سوال و گزینه‌ها ثبت می‌شوند"""
    try:
        poll_obj = message.poll.poll
        question_text = extract_text(poll_obj.question)
        options = [extract_text(a.text) for a in poll_obj.answers]
    except Exception:
        question_text, options = "(خطا در خواندن سوال)", []
    number, stripped = parse_printed_number(question_text)
    return {
        "source": "quiz", "kind": "quiz", "channel_msg_id": message.id,
        "date": (message.date or datetime.now(TEHRAN)).astimezone(TEHRAN).date().isoformat(),
        "time_tehran": (message.date or datetime.now(TEHRAN)).astimezone(TEHRAN).strftime("%H:%M"),
        "week_key": week_key_for((message.date or datetime.now(TEHRAN)).astimezone(TEHRAN)),
        "printed_number": number, "question": stripped,
        "question_segments": [], "options": options, "options_segments": [],
        "answer_index": None, "answer_source": None,
        "stem": None, "contexts": [],
        "explanation_items": [], "explanation_from_admin": True,
        "admin_diag": "error", "comment_source": "none",
        "comments_scanned": 0, "debug": "خطا در پردازش",
        "status": "pending", "image_path": None,
    }


async def retry_flood(factory):
    while True:
        try:
            return await factory()
        except FloodWaitError as e:
            print(f"\nمحدودیت تلگرام: {e.seconds} ثانیه صبر می‌کنیم ...")
            log_error(f"FloodWaitError: {e.seconds} ثانیه")
            await asyncio.sleep(e.seconds + 1)


# ---------- هشتگ (از اسکریپت تصویری خودت) ----------

def normalize_for_tag(s):
    """یکسان‌سازی ی/ک عربی و فارسی، و نیم‌فاصله با خط‌زیر"""
    return (
        s.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", "_")
        .replace("\u200f", "")
    )


def find_tags(text, hashtag_list):
    if not text:
        return []
    t = normalize_for_tag(text)
    found = []
    for tag in hashtag_list or []:
        pattern = re.escape(normalize_for_tag(tag)) + r"(?!\w)"
        if re.search(pattern, t):
            found.append(tag)
    return found


# ---------- جمع‌کردن و دوباره‌چک‌کردن (سیم‌کشی بایگانی) ----------

def _channel_ref(channel):
    """لینک/یوزرنیم کانال را به مرجعی که Telethon می‌فهمد تبدیل می‌کند"""
    if channel is None:
        return None
    c = str(channel).strip()
    if c.startswith("https://t.me/"):
        c = c[len("https://t.me/"):].strip("/")
    if c.startswith("t.me/"):
        c = c[len("t.me/"):].strip("/")
    if c.startswith("@"):
        c = c[1:]
    if c.lstrip("-").isdigit():
        return int(c)
    return c or None


def _has_explanation(item):
    return bool(item.get("explanation_items"))


def _item_age_hours(item):
    try:
        d = datetime.fromisoformat(item.get("date", "")).date()
        now = datetime.now(TEHRAN).date()
        return (now - d).days * 24
    except Exception:
        return 0


def finalize_items(state, recheck_hours, recheck_missing_days):
    """
    نهایی‌کردن آیتم‌ها:
      - توضیح دارد و قدیمی‌تر از recheck_hours است → final
      - توضیح ندارد و قدیمی‌تر از recheck_missing_days روز است → final
      - توضیح ندارد و هنوز در بازه است → pending می‌ماند تا دوباره چک شود
    """
    for it in state.get("items", []):
        age_h = _item_age_hours(it)
        if _has_explanation(it):
            if age_h > recheck_hours:
                it["status"] = "final"
        else:
            if age_h > recheck_missing_days * 24:
                it["status"] = "final"
            else:
                it["status"] = "pending"
    return state


def _seen_ids(state, source_id):
    return {(it.get("source"), it.get("channel_msg_id"))
            for it in state.get("items", []) if it.get("source") == source_id}


async def collect_source(client, entity, source, admin_keys, state, limit):
    """
    یک منبع را از جایی که state مانده ادامه می‌دهد (iter_messages از min_id).
    هر ۵۰ پست state ذخیره می‌شود تا اگر اجرا قطع شد، پیشرفت از دست نرود.
    """
    src_id = source["id"]
    kind = source["kind"]
    seen = _seen_ids(state, src_id)
    last_seen = state.get("last_seen", {}).get(src_id, 0)
    cfg = load_config()
    pause = float(cfg.get("pause_between_posts", 0.4))
    allow_vote = bool(cfg.get("allow_vote", True))
    prev_numbers = set(cfg.get("preceding_stem_numbers") or PREVIOUS_MESSAGE_QUESTIONS)
    max_q = int(cfg.get("max_admin_messages", MAX_ADMIN_MESSAGES_QUIZ))
    max_v = int(cfg.get("max_admin_messages_visual", MAX_ADMIN_MESSAGES_VISUAL))
    base_link = f"https://t.me/{getattr(entity, 'username', '') or ''}".rstrip("/")

    count = 0
    processed = 0
    if kind == "quiz":
        async for message in client.iter_messages(entity, min_id=last_seen, reverse=True, limit=limit):
            if getattr(message, "action", None):
                continue
            if not getattr(message, "poll", None):
                continue
            count += 1
            if (src_id, message.id) in seen:
                continue
            try:
                item = await retry_flood(
                    lambda: process_poll(client, entity, message, admin_keys, base_link,
                                         prev_numbers, allow_vote, max_q))
            except Exception as e:
                log_error(f"خطا در پردازش کوییز {message.id}: {e}")
                item = minimal_item(message)
            state["items"].append(item)
            seen.add((src_id, message.id))
            processed += 1
            last_seen = max(last_seen, message.id)
            state.setdefault("last_seen", {})[src_id] = last_seen
            if processed % SAVE_EVERY == 0:
                save_state(state)
                print(f"  ... {processed} پست جدید، state ذخیره شد")
            if pause:
                await asyncio.sleep(pause)
            if processed >= limit:
                break
    else:
        hashtags = source.get("hashtags") or []
        require_tag = bool(source.get("require_hashtag", True))
        # آلبوم‌ها: پیام‌های grouped_id کنار هم می‌آیند؛ iter_messages ترتیب
        # جدید→قدیم می‌دهد، پس برای گروه‌بندی اول دسته را کامل جمع می‌کنیم.
        pending_album = []
        pending_gid = None

        async def flush_album(album):
            nonlocal processed, last_seen
            if not album:
                return
            album = sorted(album, key=lambda m: m.id)
            first_id = album[0].id
            if (src_id, first_id) in seen:
                return
            combined = "\n".join((m.raw_text or "") for m in album)
            tags = find_tags(combined, hashtags)
            if require_tag and not tags:
                return
            try:
                item = await retry_flood(
                    lambda: process_visual(client, entity, album, admin_keys, base_link,
                                           hashtags, max_v))
            except Exception as e:
                log_error(f"خطا در پردازش پست تصویری {first_id}: {e}")
                return
            if item is None:
                return
            state["items"].append(item)
            seen.add((src_id, first_id))
            processed += 1
            last_seen = max(last_seen, max(m.id for m in album))
            state.setdefault("last_seen", {})[src_id] = last_seen
            if processed % SAVE_EVERY == 0:
                save_state(state)
                print(f"  ... {processed} پست جدید، state ذخیره شد")

        async for message in client.iter_messages(entity, min_id=last_seen, reverse=True, limit=limit):
            if getattr(message, "action", None):
                continue
            if getattr(message, "poll", None):
                continue
            gid = getattr(message, "grouped_id", None)
            if gid is not None:
                if pending_gid is None:
                    pending_gid, pending_album = gid, [message]
                elif gid == pending_gid:
                    pending_album.append(message)
                else:
                    await flush_album(pending_album)
                    pending_gid, pending_album = gid, [message]
            else:
                await flush_album(pending_album)
                pending_gid, pending_album = None, []
                await flush_album([message])
            count += 1
            if pause:
                await asyncio.sleep(pause)
            if processed >= limit:
                break
        await flush_album(pending_album)

    save_state(state)
    print(f"منبع {src_id}: {count} پست خوانده شد، {processed} آیتم جدید")
    return processed


async def recheck_missing(client, sources_by_id, state, cap, only_pending=False):
    """
    آیتم‌هایی که توضیح ندارند را دوباره از تلگرام می‌خواند (قدیمی‌ترین‌ها اول).
    آیتمی که بعد از این تلاش هم توضیح ندارد، pending می‌ماند و نهایی نمی‌شود.
    علاوه بر آن، آیتم‌های pending که توضیحشان از اولین کامنت‌گذار آمده
    (comment_source == "first_person") هم دوباره چک می‌شوند تا اگر ادمین
    دیرتر توضیح داده باشد، توضیح ادمین جای آن را بگیرد؛ جایگزینی فقط وقتی
    انجام می‌شود که منبع جدید admin باشد (قانون better اسکریپت‌های خودت).
    آیتم final هیچ‌وقت برنمی‌گردد.
    only_pending=True یعنی فقط آیتم‌های pending (تازه و بی‌توضیح) — برای اجرای عادی.
    """
    cfg = load_config()
    allow_vote = bool(cfg.get("allow_vote", True))
    prev_numbers = set(cfg.get("preceding_stem_numbers") or PREVIOUS_MESSAGE_QUESTIONS)
    max_q = int(cfg.get("max_admin_messages", MAX_ADMIN_MESSAGES_QUIZ))
    max_v = int(cfg.get("max_admin_messages_visual", MAX_ADMIN_MESSAGES_VISUAL))

    no_expl = [it for it in state.get("items", []) if not _has_explanation(it)]
    # ارتقای first_person → admin: فقط pending؛ توضیح دارد ولی از ادمین نیست.
    upgrade = [it for it in state.get("items", [])
               if it.get("status") == "pending"
               and it.get("comment_source") == "first_person"
               and _has_explanation(it)]
    missing = list(no_expl)
    if only_pending:
        missing = [it for it in missing if it.get("status") == "pending"]
    upgrade_ids = {id(it) for it in upgrade}
    missing = missing + upgrade
    missing.sort(key=lambda it: (it.get("last_recheck_at") or "",
                                 it.get("date", ""), it.get("channel_msg_id", 0)))
    missing = missing[:cap]
    n_upgrade = sum(1 for it in missing if id(it) in upgrade_ids)
    print(f"دوباره‌چک {len(missing)} آیتم ({len(missing) - n_upgrade} بدون توضیح"
          + (f" + {n_upgrade} ارتقای first_person→admin" if n_upgrade else "")
          + f"، سقف {cap})")

    admin_cache = {}
    refilled = 0
    upgraded = 0
    for it in missing:
        src = sources_by_id.get(it.get("source"))
        if not src:
            continue
        entity = src.get("_entity")
        if entity is None:
            continue
        if it.get("source") not in admin_cache:
            admin_cache[it["source"]] = await collect_admin_keys(
                client, entity, [])
        admin_keys = admin_cache[it["source"]]
        base_link = f"https://t.me/{getattr(entity, 'username', '') or ''}".rstrip("/")
        try:
            if it.get("kind") == "quiz":
                msg = await client.get_messages(entity, ids=it["channel_msg_id"])
                if not msg or not getattr(msg, "poll", None):
                    continue
                new = await retry_flood(
                    lambda: process_poll(client, entity, msg, admin_keys, base_link,
                                         prev_numbers, allow_vote, max_q))
            else:
                ids = it.get("message_ids") or [it["channel_msg_id"]]
                msgs = await client.get_messages(entity, ids=ids)
                unit = [m for m in (msgs if isinstance(msgs, list) else [msgs]) if m]
                if not unit:
                    continue
                new = await retry_flood(
                    lambda: process_visual(client, entity, unit, admin_keys, base_link,
                                           src.get("hashtags") or [], max_v))
                if new is None:
                    continue
        except Exception as e:
            log_error(f"خطا در دوباره‌چک {it.get('channel_msg_id')}: {e}")
            continue
        was_upgrade = id(it) in upgrade_ids
        old_source = it.get("comment_source")
        it["last_recheck_at"] = datetime.now(TEHRAN).isoformat()
        if _has_explanation(new):
            # قانون better: آیتم بدون توضیح هر توضیحی را می‌پذیرد؛ آیتم
            # first_person فقط وقتی توضیح ادمین بیاید جایگزین می‌شود.
            better = (not was_upgrade) or (
                new.get("comment_source") == "admin" and old_source != "admin")
            if better:
                for k in ("answer_index", "answer_source", "explanation_items",
                          "explanation_from_admin", "admin_diag", "comment_source",
                          "comments_scanned", "debug", "image_path"):
                    if k in new:
                        it[k] = new[k]
                if new.get("contexts"):
                    it["contexts"] = new["contexts"]
                    it["stem"] = new.get("stem")
                if was_upgrade:
                    upgraded += 1
                    print(f"  ✓ توضیح ادمین جای توضیح اولین کامنت‌گذار نشست: "
                          f"{it.get('channel_msg_id')}")
                else:
                    refilled += 1
                    print(f"  ✓ توضیح پیدا شد: {it.get('channel_msg_id')}")
            else:
                print(f"  - توضیح جدید بهتر نبود (منبع: {new.get('comment_source')}): "
                      f"{it.get('channel_msg_id')}")
        save_state(state)
    print(f"دوباره‌چک تمام شد؛ {refilled} آیتم توضیح گرفتند"
          + (f" و {upgraded} آیتم به توضیح ادمین ارتقا یافتند" if upgraded else ""))
    return refilled


async def backfill_previous_context(client, sources_by_id, state, prev_numbers):
    """
    یک‌بارمصرف (معادل patch_previous_context اسکریپت خودت): برای سوال‌های
    کوییز که شماره‌شان در preceding_stem_numbers است ولی گروه زمینه‌ای
    previous ندارند، پیام بالای سوال را اضافه می‌کند. صرف‌نظر از status
    (حتی final)؛ status، پنجره‌ی نهایی‌شدن و بقیه‌ی فیلدها عوض نمی‌شود.
    اگر چیزی برای اضافه کردن نباشد، هیچ کاری نمی‌کند.
    """
    targets = [it for it in state.get("items", [])
               if it.get("kind") == "quiz"
               and it.get("printed_number") in prev_numbers
               and not any(g.get("kind") == "previous"
                           for g in it.get("contexts") or [])]
    print(f"backfill پیام بالا: {len(targets)} سوال بدون زمینه‌ی previous")
    if not targets:
        return 0
    patched = 0
    for it in targets:
        src = sources_by_id.get(it.get("source"))
        if not src:
            continue
        entity = src.get("_entity")
        if entity is None:
            continue
        base_link = f"https://t.me/{getattr(entity, 'username', '') or ''}".rstrip("/")
        try:
            unit = await retry_flood(
                lambda: fetch_previous_unit(client, entity, it["channel_msg_id"]))
            if not unit:
                print(f"  - پیام بالای سوال {it.get('printed_number')} پیدا نشد")
                continue
            seen_first = {g.get("first_id") for g in it.get("contexts") or []}
            if unit[0].id in seen_first:
                print(f"  - پیام بالای سوال {it.get('printed_number')} "
                      f"همان زمینه‌ی قبلی است؛ رد شد")
                continue
            items = await retry_flood(
                lambda: unit_content(client, unit, "ctx", base_link))
            it.setdefault("contexts", []).append(
                {"first_id": unit[0].id, "kind": "previous", "items": items})
            it["stem"] = _stem_from_context(it["contexts"])
            it["image_path"] = _first_image_path(it["contexts"])
            patched += 1
            print(f"  ✓ پیام بالای سوال {it.get('printed_number')} اضافه شد")
            save_state(state)
        except Exception as e:
            log_error(f"خطا در backfill پیام بالای سوال {it.get('printed_number')}: {e}")
            continue
    print(f"backfill پیام بالا تمام شد؛ {patched} سوال زمینه گرفتند")
    return patched


def make_client():
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session_string = os.environ.get("TG_SESSION_STRING") or ""
    if session_string:
        from telethon.sessions import StringSession
        return TelegramClient(StringSession(session_string), api_id, api_hash)
    # بدون StringSession: لاگین تعاملی با شماره تلفن (مسیر اسکریپت‌های خودت).
    # در GitHub Actions همیشه StringSession از Secretها می‌آید.
    return TelegramClient("neuronurse_session", api_id, api_hash)


async def main_async(args):
    cfg = load_config()
    state = load_state()
    client = make_client()
    await client.start()

    sources = cfg.get("sources", [])
    sources_by_id = {}
    for src in sources:
        raw = src.get("channel")
        if not raw or "CHANGEME" in str(raw).upper():
            print(f"منبع {src.get('id')} هنوز کانال ندارد؛ رد شد.")
            continue
        ref = _channel_ref(raw)
        if not ref or "CHANGEME" in str(ref).upper():
            print(f"منبع {src.get('id')} هنوز کانال ندارد؛ رد شد.")
            continue
        try:
            entity = await client.get_entity(ref)
        except Exception as e:
            print(f"منبع {src.get('id')}: خطا در پیدا کردن کانال {ref}: {e} — رد شد.")
            log_error(f"خطا در get_entity برای منبع {src.get('id')} ({ref}): {e}")
            continue
        src["_entity"] = entity
        sources_by_id[src["id"]] = src

    if args.backfill_previous:
        prev_numbers = set(cfg.get("preceding_stem_numbers") or PREVIOUS_MESSAGE_QUESTIONS)
        await backfill_previous_context(client, sources_by_id, state, prev_numbers)
        save_state(state)
    elif args.recheck_missing is not None:
        cap = args.recheck_missing if args.recheck_missing > 0 else int(
            cfg.get("recheck_missing_batch", 200))
        await recheck_missing(client, sources_by_id, state, cap)
    else:
        for src in sources:
            if src["id"] not in sources_by_id:
                continue
            entity = src["_entity"]
            admin_keys, found_real, names = await collect_admin_keys(client, entity, [])
            print(f"منبع {src['id']}: ادمین‌ها: {len(names)} نفر"
                  + ("" if found_real else " (ادمین واقعی پیدا نشد — اولین کامنت‌گذار استفاده می‌شود)"))
            if names:
                for n in names:
                    print(f"  - {n}")
            await collect_source(client, entity, src, admin_keys, state, args.limit)
        # دوباره‌چک آیتم‌های pending (توضیح دیررس ادمین) — مثل رفتار قبلی collector؛
        # فقط تازه‌ها، نه هزار تای قدیمی (آن‌ها با --recheck-missing جداگانه پر می‌شوند).
        await recheck_missing(client, sources_by_id, state,
                              int(cfg.get("recheck_missing_batch", 200)),
                              only_pending=True)
        # نهایی‌کردن: فقط در اجرای عادی؛ در recheck آیتم بدون توضیح نهایی نمی‌شود
        finalize_items(state,
                       int(cfg.get("recheck_hours", 48)),
                       int(cfg.get("recheck_missing_days", 7)))
        save_state(state)

    if UNRECOGNIZED:
        print("فرستنده‌هایی که کامنت اولشان ادمین/معتبر حساب نشد:")
        for k, (name, cnt) in sorted(UNRECOGNIZED.items(), key=lambda x: -x[1][1]):
            print(f"  {k}: {name} ({cnt} بار)")

    await client.disconnect()

    if args.build:
        hashtags = []
        for src in sources:
            hashtags.extend(src.get("hashtags") or [])
        cmd = [sys.executable, "build_docx.py", "--state", STATE_PATH, "--out", "out"]
        if hashtags:
            cmd += ["--hashtags", ",".join(dict.fromkeys(hashtags))]
        print("ساخت ورد و JSON:", " ".join(cmd))
        import subprocess
        subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--recheck-missing", nargs="?", const=0, type=int, default=None,
                    help="آیتم‌های بدون توضیح را دوباره چک کن؛ عدد اختیاری = سقف (پیش‌فرض از config)")
    ap.add_argument("--backfill-previous", action="store_true",
                    help="یک‌بارمصرف: پیام بالای سوال‌های preceding_stem_numbers را که زمینه‌ی previous ندارند اضافه کن (بدون تغییر status/پنجره‌ها)")
    args = ap.parse_args()
    if args.recheck_missing is None and not args.collect and not args.build and not args.backfill_previous:
        ap.print_help()
        return
    if args.build and not args.collect and args.recheck_missing is None and not args.backfill_previous:
        import subprocess
        subprocess.run([sys.executable, "build_docx.py", "--state", STATE_PATH,
                        "--out", "out"], check=True)
        return
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
