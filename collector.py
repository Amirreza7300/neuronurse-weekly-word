# -*- coding: utf-8 -*-
"""
جمع‌کننده تدریجی کانال‌های نورونرس (Telethon — با اکانت خودت).
چرا Telethon و نه ربات Bot API؟ ربات تاریخچه کانال، کامنت‌های گروه
Discussion و جواب صحیح کوییز را نمی‌تواند بخواند؛ اکانت کاربری می‌تواند.
قانون‌های استخراج — همان قانون‌های اثبات‌شده قبلی (telegram-admin-extract):
  - جواب صحیح از خود نظرسنجی (poll.results) گرفته می‌شود، نه از کامنت.
    اگر نتیجه هنوز دیده نمی‌شود، با اجازه امیررضا (2026-11-17،
    config: allow_vote=true) یک رای به گزینه اول داده می‌شود تا
    تلگرام جواب صحیح را نشان دهد؛ نتیجه رای برای او مهم نیست.
    اگر allow_vote خاموش باشد، جواب «نامشخص» می‌ماند و در اجراهای
    بعد دوباره چک می‌شود. فقط اگر در کامنت ادمین صریحاً «گزینه ب»
    و... آمده بود، به‌عنوان حدس علامت‌دار ثبت می‌شود
    (answer_source=comment_guess).
  - توضیح فقط از اولین ادمینِ کامنت‌گذار، فقط پیام‌های متوالی همان
    ادمین، سقف ۷ پیام، فقط ریپلای مستقیم به خود پست یا ریپلای به پیام
    قبلی خودش؛ ریپلای به دیگران یا پیام غیرادمین وسط، دنباله را قطع
    می‌کند. پیام با پروفایل گروه/کانال (sender_chat) هم ادمین است؛
    پیام بدون فرستنده در گروه Discussion هم ادمین ناشناس است.
  - اگر هیچ ادمینی توضیح نداده بود، همان قانون روی اولین کامنت‌گذار
    اعمال می‌شود و در ورد مشخص می‌شود که از ادمین نیست.
  - صورت سوال: اگر کوییز ریپلای به پیامی باشد، آن پیام (متن/عکس)
    جزو صورت سوال است. پیام بالای سوال فقط برای شماره‌های داخل
    config (preceding_stem_numbers).
  - عکس صورت سوال دانلود می‌شود؛ عکس کامنت نه. توضیح فقط‌عکس:
    «فقط عکس بود» نوشته می‌شود.
  - شماره چاپ‌شده لاتین ابتدای سوال، شماره سوال در ورد است.
اجرا (محلی):  python collector.py --collect --build
در GitHub Actions با Secretها اجرا می‌شود؛ هیچ رمزی در کد نیست.
"""
import argparse
import asyncio
import copy
import json
import os
import re
import sys
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import yaml

TEHRAN = ZoneInfo("Asia/Tehran")
STATE_PATH = "data/state.json"
IMAGES_DIR = "data/images"

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import FloodWaitError
    from telethon.tl.types import (
        MessageMediaPoll, MessageMediaPhoto, MessageMediaDocument,
        MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
        MessageEntityStrike, ChannelParticipantsAdmins,
    )
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.functions.messages import SendVoteRequest
except ImportError:
    print("Telethon نصب نیست: pip install -r requirements.txt")
    sys.exit(1)


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


def week_key_for(dt_tehran):
    """جمعه ۰۰:۰۰ تهران شروع هفته است. dt را به شروع همان هفته ببر."""
    d = dt_tehran.date()
    days_since_friday = (d.weekday() - 4) % 7  # Monday=0 ... Friday=4
    start = d - timedelta(days=days_since_friday)
    return start.isoformat()


def parse_printed_number(text):
    if not text:
        return None, text
    m = re.match(r"^\s*(\d{1,5})\s*[.\-–:]\s*", text)
    if not m:
        return None, text
    return int(m.group(1)), text[m.end():]


# ---------- سگمنت‌های بولد/ایتالیک (UTF-16 مثل تلگرام) ----------

def message_to_segments(text, entities):
    if not text:
        return []
    raw = text.encode("utf-16-le")
    n = len(raw) // 2
    flags = [0] * n
    for ent in entities or []:
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
        for k in range(max(0, ent.offset), min(n, ent.offset + ent.length)):
            flags[k] |= bit
    out, i = [], 0
    while i < n:
        j = i
        while j < n and flags[j] == flags[i]:
            j += 1
        chunk = raw[i * 2:j * 2].decode("utf-16-le", errors="ignore")
        if chunk:
            f = flags[i]
            out.append({"t": chunk, "b": bool(f & 1), "i": bool(f & 2),
                        "u": bool(f & 4), "s": bool(f & 8)})
        i = j
    return out


def segments_from(obj):
    if obj is None:
        return [{"t": "", "b": False}]
    if isinstance(obj, str):
        return [{"t": obj, "b": False}]
    return message_to_segments(getattr(obj, "text", "") or "", getattr(obj, "entities", None))


def seg_text(segments):
    return "".join(s.get("t", "") for s in (segments or []))


# ---------- ادمین ----------

def _all_sender_ids(msg):
    ids = set()
    sid = getattr(msg, "sender_id", None)
    if isinstance(sid, int):
        ids.add(sid)
    sender = getattr(msg, "sender", None)
    if sender is not None and isinstance(getattr(sender, "id", None), int):
        ids.add(sender.id)
    chat = getattr(msg, "sender_chat", None)
    if chat is not None and isinstance(getattr(chat, "id", None), int):
        ids.add(chat.id)
    from_id = getattr(msg, "from_id", None)
    if from_id is not None:
        for attr in ("user_id", "channel_id", "chat_id"):
            v = getattr(from_id, attr, None)
            if isinstance(v, int):
                ids.add(v)
    return ids


def admin_identity(msg):
    chat = getattr(msg, "sender_chat", None)
    if chat is not None and isinstance(getattr(chat, "id", None), int):
        return ("chat", chat.id)
    sid = getattr(msg, "sender_id", None)
    if isinstance(sid, int):
        return ("user", sid)
    sender = getattr(msg, "sender", None)
    if sender is not None and isinstance(getattr(sender, "id", None), int):
        return ("user", sender.id)
    return ("unknown", None)  # پیام بدون فرستنده در گروه = ادمین ناشناس


def is_admin_message(msg, admin_user_ids, admin_chat_ids):
    if admin_user_ids is None:
        return True
    ids = _all_sender_ids(msg)
    # پیام بدون هیچ شناسه‌ای (ادمین ناشناس گروه) هم ادمین حساب می‌شود
    if not ids:
        return True
    return bool(ids & set(admin_user_ids)) or bool(ids & set(admin_chat_ids))


async def collect_admin_ids(client, entity):
    admin_user_ids, admin_chat_ids = set(), {entity.id}
    targets = [entity]
    try:
        full = await client(GetFullChannelRequest(entity))
        linked_id = getattr(full.full_chat, "linked_chat_id", None)
        if linked_id:
            admin_chat_ids.add(linked_id)
            linked = next((c for c in full.chats if c.id == linked_id), None)
            if linked is not None:
                targets.append(linked)
    except Exception as e:
        print(f"هشدار: گروه Discussion پیدا نشد: {e}")
    for target in targets:
        try:
            async for user in client.iter_participants(target, filter=ChannelParticipantsAdmins):
                admin_user_ids.add(user.id)
        except Exception as e:
            print(f"هشدار: لیست ادمین‌ها خوانده نشد: {e}")
    return admin_user_ids, admin_chat_ids


def select_admin_run(comments, admin_user_ids, admin_chat_ids, post_id, max_n=7):
    """قانون متوالی ادمین؛ برمی‌گرداند (run, stopped_reason, first_is_admin)."""
    if not comments:
        return [], "no_comments", False
    start = None
    for idx, c in enumerate(comments):
        rt = getattr(c, "reply_to", None)
        parent = getattr(rt, "reply_to_msg_id", None) if rt is not None else None
        if is_admin_message(c, admin_user_ids, admin_chat_ids) and parent == post_id:
            start = idx
            break
    if start is None:
        return [], "no_admin_found", False
    first_key = admin_identity(comments[start])
    run, run_ids = [], set()
    for c in comments[start:]:
        if len(run) >= max_n:
            return run, "cap_reached_7", True
        if not is_admin_message(c, admin_user_ids, admin_chat_ids):
            return run, "interrupted_by_non_admin", True
        if admin_identity(c) != first_key:
            return run, "interrupted_by_other_admin", True
        rt = getattr(c, "reply_to", None)
        parent = getattr(rt, "reply_to_msg_id", None) if rt is not None else None
        if parent == post_id or parent in run_ids:
            run.append(c); run_ids.add(c.id)
        else:
            return run, "interrupted_by_admin_reply_to_other", True
    return run, "end_of_comments", True


def select_first_commenter_run(comments, post_id, max_n=7):
    """فالبک: همان قانون متوالی روی اولین کامنت‌گذار (وقتی ادمین نیست)."""
    if not comments:
        return []
    first = comments[0]
    rt = getattr(first, "reply_to", None)
    if getattr(rt, "reply_to_msg_id", None) != post_id:
        return []
    key = admin_identity(first)
    run, run_ids = [], set()
    for c in comments:
        if len(run) >= max_n:
            break
        if admin_identity(c) != key:
            break
        rt = getattr(c, "reply_to", None)
        parent = getattr(rt, "reply_to_msg_id", None) if rt is not None else None
        if parent == post_id or parent in run_ids:
            run.append(c); run_ids.add(c.id)
        else:
            break
    return run


PERSIAN_LETTER_MAP = {"الف": 1, "ب": 2, "ج": 3, "د": 4, "ه": 5, "و": 6, "ز": 7, "ح": 8}


def guess_answer_from_text(text):
    """فقط حدس علامت‌دار از متن کامنت؛ جواب اصلی نیست."""
    if not text:
        return None
    norm = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2))
    for pat in [r"گزینه\s*(?:ی)?\s*([1-8])", r"پاسخ\s*(?:صحیح)?\s*[:\-،]?\s*(الف|ب|ج|د|ه|و|ز|ح)\b",
                r"جواب\s*(?:صحیح)?\s*[:\-،]?\s*([1-8])\b"]:
        m = re.search(pat, norm)
        if m:
            tok = m.group(1)
            if tok in PERSIAN_LETTER_MAP:
                return PERSIAN_LETTER_MAP[tok]
            if tok.isdigit():
                return int(tok)
    return None


def correct_index_from_results(poll_obj, results):
    if not results or not getattr(results, "results", None):
        return None
    for i, ans in enumerate(poll_obj.answers):
        for res in results.results:
            if res.option == ans.option and getattr(res, "correct", False):
                return i + 1
    return None


async def get_correct_answer(client, entity, message, poll_obj, allow_vote):
    """جواب صحیح از خود نظرسنجی. اگر نتیجه هنوز دیده نمی‌شود و
    allow_vote فعال است (با اجازه امیررضا، 2026-11-17)، یک رای به
    گزینه اول می‌دهد تا تلگرام جواب صحیح را نشان دهد؛ نتیجه رای
    برای او مهم نیست. برمی‌گرداند (index, source) با source یکی از
    'poll' یا 'poll_vote' یا None."""
    idx = correct_index_from_results(poll_obj, getattr(message.poll, "results", None))
    if idx:
        return idx, "poll"
    if not getattr(poll_obj, "quiz", False):
        return None, None
    if getattr(poll_obj, "closed", False) or not poll_obj.answers:
        return None, None
    if not allow_vote:
        return None, None
    try:
        result = await client(SendVoteRequest(
            peer=entity, msg_id=message.id, options=[poll_obj.answers[0].option]))
        for upd in getattr(result, "updates", None) or []:
            if hasattr(upd, "results") and hasattr(upd, "poll_id"):
                idx = correct_index_from_results(poll_obj, upd.results)
                if idx:
                    return idx, "poll_vote"
    except FloodWaitError:
        raise
    except Exception as e:
        print(f"خطا در رای‌دادن به پیام {getattr(message, 'id', '?')}: {e}")
        return None, None
    try:
        fresh = await client.get_messages(entity, ids=message.id)
        if fresh and fresh.poll:
            idx = correct_index_from_results(poll_obj, fresh.poll.results)
            if idx:
                return idx, "poll_vote"
    except FloodWaitError:
        raise
    except Exception as e:
        print(f"خطا در خواندن مجدد نتیجه نظرسنجی {getattr(message, 'id', '?')}: {e}")
    return None, None


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


async def fetch_comments(client, entity, post_id, limit=200):
    msgs = []
    try:
        async for reply in client.iter_messages(entity, reply_to=post_id, reverse=True, limit=limit):
            if getattr(reply, "action", None):
                continue
            msgs.append(reply)
    except FloodWaitError:
        raise
    except Exception as e:
        print(f"خطا در خواندن کامنت‌های پست {post_id}: {e}")
    return msgs


async def download_stem_image(client, msg, key):
    if not _has_photo(msg):
        return None
    media = msg.media
    ext = ".png" if isinstance(media, MessageMediaDocument) and getattr(getattr(msg, "file", None), "mime_type", None) == "image/png" else ".jpg"
    os.makedirs(IMAGES_DIR, exist_ok=True)
    path = os.path.join(IMAGES_DIR, f"{key}{ext}")
    if os.path.exists(path):
        return path
    try:
        return await client.download_media(msg, file=path)
    except FloodWaitError:
        raise
    except Exception as e:
        print(f"خطا در دانلود عکس {key}: {e}")
        return None


def explanation_items_from_run(run):
    items = []
    for c in run:
        segs = message_to_segments(c.raw_text or "", c.entities)
        if segs and any(s["t"].strip() for s in segs):
            items.append({"type": "text", "segments": segs})
        elif _has_photo(c):
            items.append({"type": "image", "text": "فقط عکس بود"})
    if items and all(i["type"] == "image" for i in items):
        items = [{"type": "text", "segments": [{"t": "فقط عکس بود", "b": False}]}]
    return items


async def process_poll(client, entity, message, admin_user_ids, admin_chat_ids, cfg, source_id, source=None):
    poll_obj = message.poll.poll
    answer_index, answer_source = await get_correct_answer(
        client, entity, message, poll_obj, cfg.get("allow_vote", False))
    q_text = getattr(poll_obj.question, "text", "") or ""
    printed, stripped = parse_printed_number(q_text)
    # سگمنت‌ها را با جابه‌جایی entities بعد از حذف پیشوند شماره بساز،
    # تا شماره چاپ‌شده هم در تیتر سوال باشد و هم اول متن سوال تکرار نشود.
    prefix_len = len(q_text) - len(stripped)
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
    options = [(getattr(a.text, "text", "") or "") for a in poll_obj.answers]
    options_segs = [segments_from(a.text) for a in poll_obj.answers]

    stem = None
    rt = getattr(message, "reply_to", None)
    replied_id = getattr(rt, "reply_to_msg_id", None) if rt is not None else None
    if replied_id:
        try:
            replied = await client.get_messages(entity, ids=replied_id)
            if replied and not getattr(replied, "poll", None):
                stem = {"source": "replied_message", "message_id": replied.id,
                        "text": _msg_text(replied),
                        "segments": message_to_segments(_msg_text(replied), getattr(replied, "entities", None)),
                        "photo_path": await download_stem_image(client, replied, f"stem{message.id}")}
        except FloodWaitError:
            raise
        except Exception as e:
            print(f"خطا در پیام ریپلای‌شده {message.id}: {e}")
    if stem is None and printed in (cfg.get("preceding_stem_numbers") or []):
        try:
            prev = None
            async for m in client.iter_messages(entity, offset_id=message.id, limit=1):
                prev = m; break
            if prev is not None and not getattr(prev, "poll", None) and (_msg_text(prev) or _has_photo(prev)):
                stem = {"source": "preceding_message", "message_id": prev.id,
                        "text": _msg_text(prev),
                        "segments": message_to_segments(_msg_text(prev), getattr(prev, "entities", None)),
                        "photo_path": await download_stem_image(client, prev, f"stem{message.id}")}
        except FloodWaitError:
            raise
        except Exception as e:
            print(f"خطا در پیام بالای {message.id}: {e}")

    comments = await fetch_comments(client, entity, message.id)
    run, reason, from_admin = select_admin_run(
        comments, admin_user_ids, admin_chat_ids, message.id,
        max_n=cfg.get("max_admin_messages", 7))
    if not run:
        run = select_first_commenter_run(comments, message.id, max_n=cfg.get("max_admin_messages", 7))
        from_admin = False if run else True
    expl = explanation_items_from_run(run)
    if answer_index is None and expl:
        joined = "\n".join(seg_text(c.get("segments")) for c in expl if c.get("type") == "text")
        g = guess_answer_from_text(joined)
        if g:
            answer_index, answer_source = g, "comment_guess"

    dt = (message.date or datetime.now(TEHRAN)).astimezone(TEHRAN)
    return {
        "source": source_id, "kind": "quiz", "channel_msg_id": message.id,
        "date": dt.date().isoformat(), "time_tehran": dt.strftime("%H:%M"),
        "week_key": week_key_for(dt),
        "printed_number": printed, "question": stripped,
        "question_segments": q_segs, "options": options,
        "options_segments": options_segs,
        "answer_index": answer_index, "answer_source": answer_source,
        "stem": stem,
        "explanation_items": expl, "explanation_from_admin": from_admin,
        "admin_diag": reason, "status": "pending",
        "image_path": stem.get("photo_path") if stem else None,
    }


async def process_visual(client, entity, message, admin_user_ids, admin_chat_ids, cfg, source_id, source=None):
    text = _msg_text(message)
    # هشتگ‌ها از منبع (source) خوانده می‌شوند، نه از ریشه config —
    # قبلاً cfg.get("hashtags") همیشه خالی بود و ترتیب config رعایت نمی‌شد.
    hashtags = [h for h in ((source or {}).get("hashtags") or []) if h in text]
    # هشتگ‌های دیگر داخل متن هم نگه دار
    for h in re.findall(r"#\S+", text):
        if h not in hashtags:
            hashtags.append(h)
    comments = await fetch_comments(client, entity, message.id)
    run, reason, from_admin = select_admin_run(
        comments, admin_user_ids, admin_chat_ids, message.id,
        max_n=cfg.get("max_admin_messages", 7))
    if not run:
        run = select_first_commenter_run(comments, message.id, max_n=cfg.get("max_admin_messages", 7))
        from_admin = False if run else True
    expl = explanation_items_from_run(run)
    dt = (message.date or datetime.now(TEHRAN)).astimezone(TEHRAN)
    img = await download_stem_image(client, message, f"visual{message.id}")
    return {
        "source": source_id, "kind": "visual", "channel_msg_id": message.id,
        "date": dt.date().isoformat(), "time_tehran": dt.strftime("%H:%M"),
        "week_key": week_key_for(dt),
        "hashtags": hashtags, "caption": text,
        "caption_segments": message_to_segments(text, getattr(message, "entities", None)),
        "explanation_items": expl, "explanation_from_admin": from_admin,
        "admin_diag": reason, "status": "pending", "image_path": img,
    }


async def collect_source(client, cfg, source, state, items_by_key):
    channel = source["channel"]
    if "CHANGEME" in channel:
        print(f"رد شد: کانال {source['id']} هنوز در config.yaml تنظیم نشده ({channel})")
        return 0
    entity = await client.get_entity(channel)
    admin_user_ids, admin_chat_ids = await collect_admin_ids(client, entity)
    print(f"منبع {source['id']}: کانال {entity.id}، ادمین‌ها: {len(admin_user_ids)} نفر")
    last_seen = state.get("last_seen", {}).get(source["id"], 0)
    new_count = 0
    # پست‌های جدید + پست‌های pending قدیمی برای چک دوباره
    now = datetime.now(TEHRAN)
    pending_ids = set()
    for it in state["items"]:
        if it.get("source") != source["id"] or it.get("status") != "pending":
            continue
        # ساده: همه pendingها را تا ۷ روز دوباره چک کن
        pending_ids.add(it["channel_msg_id"])

    async for message in client.iter_messages(entity, min_id=last_seen, reverse=True):
        if getattr(message, "action", None):
            continue
        await asyncio.sleep(cfg.get("pause_between_posts", 0.4))
        is_poll = getattr(message, "poll", None) is not None
        if source["kind"] == "quiz" and not is_poll:
            continue
        if source["kind"] == "visual" and is_poll:
            continue
        if source["kind"] == "visual" and source.get("require_hashtag"):
            text = _msg_text(message)
            if not any(h in text for h in (source.get("hashtags") or [])):
                continue
        try:
            if is_poll:
                item = await process_poll(client, entity, message, admin_user_ids, admin_chat_ids, cfg, source["id"], source)
            else:
                item = await process_visual(client, entity, message, admin_user_ids, admin_chat_ids, cfg, source["id"], source)
        except FloodWaitError as e:
            print(f"FloodWait {e.seconds} ثانیه — صبر می‌کنم")
            await asyncio.sleep(e.seconds + 5)
            continue
        key = (source["id"], message.id)
        items_by_key[key] = item
        new_count += 1
        state.setdefault("last_seen", {})[source["id"]] = max(state["last_seen"].get(source["id"], 0), message.id)

    # چک دوباره pendingها
    for mid in sorted(pending_ids):
        if (source["id"], mid) in items_by_key:
            continue
        try:
            message = await client.get_messages(entity, ids=mid)
            if not message:
                continue
            await asyncio.sleep(cfg.get("pause_between_posts", 0.4))
            if getattr(message, "poll", None):
                item = await process_poll(client, entity, message, admin_user_ids, admin_chat_ids, cfg, source["id"], source)
            else:
                item = await process_visual(client, entity, message, admin_user_ids, admin_chat_ids, cfg, source["id"], source)
            # اگر توضیح کامل شد یا ۷ پیام رسید، نهایی کن؛ وگرنه pending بماند
            dt = datetime.fromisoformat(item["date"]).replace(tzinfo=TEHRAN)
            if (now - dt).total_seconds() > cfg.get("recheck_hours", 48) * 3600:
                item["status"] = "final"
            items_by_key[(source["id"], mid)] = item
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            print(f"خطا در چک دوباره {mid}: {e}")
    return new_count


async def main_async():
    cfg = load_config()
    state = load_state()
    items_by_key = {(i["source"], i["channel_msg_id"]): i for i in state.get("items", [])}
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session_str = os.environ.get("TG_SESSION_STRING", "")
    if session_str:
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
    else:
        client = TelegramClient("neuronurse_weekly_session", api_id, api_hash)
    await client.start()
    print("وصل شدم به تلگرام.")
    total = 0
    for source in cfg.get("sources", []):
        total += await collect_source(client, cfg, source, state, items_by_key)
    await client.disconnect()
    # نهایی‌کردن پست‌های قدیمی‌تر از recheck_hours
    now = datetime.now(TEHRAN)
    for it in items_by_key.values():
        try:
            dt = datetime.fromisoformat(it["date"]).replace(tzinfo=TEHRAN)
            if (now - dt).total_seconds() > cfg.get("recheck_hours", 48) * 3600:
                it["status"] = "final"
        except Exception:
            pass
    state["items"] = sorted(items_by_key.values(), key=lambda x: (x.get("date", ""), x.get("channel_msg_id", 0)))
    save_state(state)
    print(f"تمام شد: {total} پست تازه پردازش شد، مجموع {len(state['items'])} مورد در state.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    if args.collect:
        asyncio.run(main_async())
    if args.build:
        import subprocess
        subprocess.run([sys.executable, "build_docx.py"], check=True)
    if not args.collect and not args.build:
        ap.print_help()


if __name__ == "__main__":
    main()
