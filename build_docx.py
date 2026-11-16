# -*- coding: utf-8 -*-
"""
ساخت فایل‌های ورد از data/state.json — بدون تلگرام.
خروجی‌ها:
  out/Neuronurse-Quiz-Kamel.docx        فایل کلی همه تست‌ها
  out/Neuronurse-Visual-Kamel.docx      فایل کلی همه محتوای تصویری
  out/weekly/Quiz-<شروع>-ta-<پایان>.docx     هر هفته جدا
  out/weekly/Visual-<شروع>-ta-<پایان>.docx   هر هفته جدا
  out/report.json                       شمارش‌ها و موارد جاافتاده
همه فایل‌ها راست‌چین، فونت وزیرمتن، به‌ترتیب تاریخ (قدیمی به جدید).
اجرا:  python build_docx.py [--sample] [--state data/state.json] [--out out]
"""
import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    import jdatetime
except ImportError:
    jdatetime = None

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

TEHRAN = ZoneInfo("Asia/Tehran")
FONT = "Vazirmatn"
FONT_SIZE = 13
TITLE_SIZE = 16
OPTION_LABELS = ["الف", "ب", "ج", "د", "ه", "و", "ز", "ح"]
DIVIDER = "-" * 30


def fa_digits(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def jalali_str(iso_date):
    """ISO date -> '۲۷ آبان ۱۴۰۵'؛ اگر jdatetime نبود، همان میلادی با ارقام فارسی."""
    try:
        d = datetime.fromisoformat(iso_date).date() if "T" not in iso_date else datetime.fromisoformat(iso_date).date()
    except Exception:
        return iso_date
    if jdatetime is not None:
        jd = jdatetime.date.fromgregorian(day=d.day, month=d.month, year=d.year)
        months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                  "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
        return f"{fa_digits(jd.day)} {months[jd.month - 1]} {fa_digits(jd.year)}"
    return fa_digits(d.isoformat())


def week_label(week_key):
    """week_key = 'YYYY-MM-DD' شروع هفته (جمعه). برمی‌گرداند '۱۴۰۵/۰۸/۲۲ تا ۱۴۰۵/۰۸/۲۹'."""
    try:
        from datetime import date, timedelta
        start = date.fromisoformat(week_key)
        end = start + timedelta(days=7)
        if jdatetime is not None:
            s = jdatetime.date.fromgregorian(day=start.day, month=start.month, year=start.year)
            e = jdatetime.date.fromgregorian(day=end.day, month=end.month, year=end.year)
            return f"{fa_digits(f'{s.year:04d}/{s.month:02d}/{s.day:02d}')} تا {fa_digits(f'{e.year:04d}/{e.month:02d}/{e.day:02d}')}"
        return f"{start.isoformat()} تا {end.isoformat()}"
    except Exception:
        return week_key


# ---------- قالب‌بندی ورد (راست‌چین + وزیرمتن در همه slotها) ----------

def set_rtl(p):
    pPr = p._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def fmt(run, size=FONT_SIZE, bold=False, italic=False, underline=False, strike=False):
    rPr = run._element.get_or_add_rPr()
    for child in list(rPr):
        rPr.remove(child)
    rf = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(attr), FONT)
    rPr.append(rf)
    if bold:
        rPr.append(OxmlElement("w:b")); rPr.append(OxmlElement("w:bCs"))
    if italic:
        rPr.append(OxmlElement("w:i")); rPr.append(OxmlElement("w:iCs"))
    if strike:
        rPr.append(OxmlElement("w:strike"))
    if underline:
        u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rPr.append(u)
    sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(int(size * 2))); rPr.append(sz)
    szcs = OxmlElement("w:szCs"); szcs.set(qn("w:val"), str(int(size * 2))); rPr.append(szcs)
    rPr.append(OxmlElement("w:rtl"))


def para(doc, size=FONT_SIZE):
    p = doc.add_paragraph()
    set_rtl(p)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    return p


def add_text(doc, text, size=FONT_SIZE, bold=False):
    p = para(doc, size)
    r = p.add_run(text or "")
    fmt(r, size, bold=bold)
    return p


def add_segments(doc, segments, size=FONT_SIZE, force_bold=False):
    p = para(doc, size)
    for seg in segments or [{"t": "", "b": False}]:
        r = p.add_run(seg.get("t", ""))
        fmt(r, size, bold=bool(seg.get("b")) or force_bold,
            italic=bool(seg.get("i")), underline=bool(seg.get("u")),
            strike=bool(seg.get("s")))
    return p


def add_image(doc, path, width=4.0):
    if not path or not os.path.exists(path):
        return
    p = para(doc)
    r = p.add_run()
    try:
        r.add_picture(path, width=Inches(width))
    except Exception:
        add_text(doc, f"[تصویر بارگذاری نشد: {os.path.basename(path)}]")


def seg_text(segments):
    return "".join(s.get("t", "") for s in (segments or []))


# ---------- ساخت ورد ----------

def apply_doc_defaults(doc):
    """فونت وزیرمتن + راست‌چین در سطح استایل Normal، علاوه بر bidi
    تک‌تک پاراگراف‌ها — تا در Word موبایل هم سند کاملاً راست‌چین
    باز شود، نه فقط پاراگراف‌هایی که دستی ساخته شده‌اند."""
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(FONT_SIZE)
    rpr = st.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts"); rpr.append(rf)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(attr), FONT)
    pPr = st.element.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "right")
    pPr.append(jc)


def build_quiz_doc(items, title, subtitle):
    doc = Document()
    apply_doc_defaults(doc)

    add_text(doc, title, size=TITLE_SIZE, bold=True)
    add_text(doc, subtitle, bold=True)
    add_text(doc, f"تعداد سوال: {fa_digits(len(items))}")
    add_text(doc, "")

    for i, it in enumerate(items):
        num = it.get("printed_number")
        head = f"سوال {fa_digits(num)}" if num else f"سوال {fa_digits(i + 1)}"
        add_text(doc, head, size=TITLE_SIZE, bold=True)
        # قالب خواسته‌شده، به همین ترتیب: تاریخ و زمان، سوال بولد،
        # گزینه‌ها، گزینه درست، توضیح (پاسخ تشریحی).
        add_text(doc, f"تاریخ: {jalali_str(it.get('date', ''))} | ساعت: {fa_digits(it.get('time_tehran', ''))}")
        stem = it.get("stem") or {}
        if stem.get("text") or stem.get("photo_path"):
            label = "صورت سوال (پیام ریپلای‌شده):" if stem.get("source") == "replied_message" else "صورت سوال (پیام بالای سوال):"
            add_text(doc, label, bold=True)
            if stem.get("segments"):
                add_segments(doc, stem["segments"])
            elif stem.get("text"):
                add_text(doc, stem["text"])
            if stem.get("photo_path"):
                add_image(doc, stem["photo_path"])
        add_segments(doc, it.get("question_segments") or [{"t": it.get("question", ""), "b": False}],
                     force_bold=True)
        if it.get("image_path"):
            add_image(doc, it["image_path"])

        for oi, opt in enumerate(it.get("options", [])):
            label = OPTION_LABELS[oi] if oi < len(OPTION_LABELS) else str(oi + 1)
            # گزینه صحیح در لیست گزینه‌ها بولد نمی‌شود (خواسته امیررضا)؛
            # فقط خط «پاسخ صحیح:» پایین سوال بولد است. بولدهای خود
            # تلگرام داخل متن گزینه سر جایشان می‌مانند.
            p = para(doc)
            r = p.add_run(f"{label}) ")
            fmt(r, FONT_SIZE, bold=False)
            segs = None
            if it.get("options_segments") and oi < len(it["options_segments"]):
                segs = it["options_segments"][oi]
            if not segs:
                segs = [{"t": opt, "b": False}]
            for seg in segs:
                r = p.add_run(seg.get("t", ""))
                fmt(r, FONT_SIZE, bold=bool(seg.get("b")),
                    italic=bool(seg.get("i")))
        add_text(doc, "")
        idx = it.get("answer_index")
        if idx and 1 <= idx <= len(it.get("options", [])):
            add_text(doc, f"گزینه درست: {OPTION_LABELS[idx - 1]}) {it['options'][idx - 1]}", bold=True)
        else:
            add_text(doc, "گزینه درست: نامشخص (در نظرسنجی هنوز مشخص نیست — در اجرای بعد دوباره چک می‌شود)", bold=True)
        if it.get("answer_source") == "comment_guess":
            add_text(doc, "(جواب از روی متن کامنت حدس زده شده، نه از خود نظرسنجی)")
        add_text(doc, "توضیح:", bold=True)
        expl = it.get("explanation_items") or []
        if expl:
            for c in expl:
                if c.get("type") == "text":
                    add_segments(doc, c.get("segments") or [{"t": c.get("text", ""), "b": False}])
                elif c.get("type") == "image":
                    add_text(doc, "[توضیح فقط عکس بود]")
            if not it.get("explanation_from_admin", True):
                add_text(doc, "(توضیح بالا از ادمین نیست — از اولین کامنت‌گذار گرفته شده)")
        else:
            add_text(doc, "توضیحی از ادمین پیدا نشد.")
        if i != len(items) - 1:
            add_text(doc, "")
            add_text(doc, DIVIDER)
            add_text(doc, "")
    return doc


def build_visual_doc(items, title, subtitle, hashtag_order):
    doc = Document()
    apply_doc_defaults(doc)

    add_text(doc, title, size=TITLE_SIZE, bold=True)
    add_text(doc, subtitle, bold=True)
    add_text(doc, f"تعداد مورد: {fa_digits(len(items))}")
    add_text(doc, "")

    # گروه‌بندی با اسم هشتگ، به ترتیب config؛ هر گروه پشت سر هم.
    groups = OrderedDict()
    for h in hashtag_order or []:
        groups[h] = []
    groups["بدون هشتگ"] = []
    for it in items:
        placed = False
        for h in (it.get("hashtags") or []):
            if h in groups:
                groups[h].append(it); placed = True; break
        if not placed:
            groups["بدون هشتگ"].append(it)
    n = 0
    for h, g in groups.items():
        if not g:
            continue
        add_text(doc, h, size=TITLE_SIZE, bold=True)
        add_text(doc, "")
        for it in g:
            n += 1
            add_text(doc, f"{fa_digits(n)}. {jalali_str(it.get('date', ''))} — ساعت {fa_digits(it.get('time_tehran', ''))}", bold=True)
            if it.get("caption_segments"):
                add_segments(doc, it["caption_segments"])
            elif it.get("caption"):
                add_text(doc, it["caption"])
            if it.get("image_path"):
                add_image(doc, it["image_path"])
            expl = it.get("explanation_items") or []
            if expl:
                add_text(doc, "توضیح:", bold=True)
                for c in expl:
                    if c.get("type") == "text":
                        add_segments(doc, c.get("segments") or [{"t": c.get("text", ""), "b": False}])
                    elif c.get("type") == "image":
                        add_text(doc, "[توضیح فقط عکس بود]")
            else:
                add_text(doc, "توضیحی از ادمین پیدا نشد.")
            add_text(doc, "")
            add_text(doc, DIVIDER)
            add_text(doc, "")
    return doc


def sort_items(items):
    return sorted(items, key=lambda x: (x.get("date", ""), x.get("channel_msg_id", 0)))


def load_state(path):
    if not os.path.exists(path):
        return {"items": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sample_items():
    """داده نمونه برای تست — شبیه پست‌های واقعی کانال، دو هفته جدا."""
    return [
        {"source": "quiz", "kind": "quiz", "channel_msg_id": 101, "date": "2026-11-13",
         "time_tehran": "09:10", "week_key": "2026-11-13",
         "printed_number": 1773, "question": "کدام دارو در نارسایی قلبی منع مصرف دارد؟",
         "question_segments": [{"t": "کدام دارو در نارسایی قلبی منع مصرف دارد؟", "b": False}],
         "options": ["متوپرولول", "وراپامیل", "کارودیلول", "بیزوپرولول"],
         "options_segments": [[{"t": o, "b": False}] for o in ["متوپرولول", "وراپامیل", "کارودیلول", "بیزوپرولول"]],
         "answer_index": 2, "answer_source": "poll",
         "explanation_items": [{"type": "text", "segments": [{"t": "پاسخ صحیح وراپامیل است؛ بلوک‌کننده کلسیم غیر دی‌هیدروپیریدینی در نارسایی سیستولیک قلب اثر اینوتروپ منفی دارد.", "b": False}]}],
         "explanation_from_admin": True, "stem": None, "status": "final"},
        {"source": "quiz", "kind": "quiz", "channel_msg_id": 102, "date": "2026-11-14",
         "time_tehran": "14:25", "week_key": "2026-11-13",
         "printed_number": 1774, "question": "شایع‌ترین علت شوک کاردیوژنیک چیست؟",
         "question_segments": [{"t": "شایع‌ترین علت شوک کاردیوژنیک چیست؟", "b": False}],
         "options": ["انفارکتوس میوکارد", "میوکاردیت", "تامپوناد", "آمبولی ریه"],
         "options_segments": [[{"t": o, "b": False}] for o in ["انفارکتوس میوکارد", "میوکاردیت", "تامپوناد", "آمبولی ریه"]],
         "answer_index": 1, "answer_source": "poll",
         "explanation_items": [{"type": "text", "segments": [{"t": "پاسخ صحیح انفارکتوس میوکارد است.", "b": False}]}],
         "explanation_from_admin": True, "stem": None, "status": "final"},
        {"source": "quiz", "kind": "quiz", "channel_msg_id": 201, "date": "2026-11-21",
         "time_tehran": "09:30", "week_key": "2026-11-20",
         "printed_number": 1775, "question": "در ECG موج P نشان‌دهنده چیست؟",
         "question_segments": [{"t": "در ECG موج P نشان‌دهنده چیست؟", "b": False}],
         "options": ["دپولاریزاسیون دهلیز", "دپولاریزاسیون بطن", "رپولاریزاسیون بطن", "رپولاریزاسیون دهلیز"],
         "options_segments": [[{"t": o, "b": False}] for o in ["دپولاریزاسیون دهلیز", "دپولاریزاسیون بطن", "رپولاریزاسیون بطن", "رپولاریزاسیون دهلیز"]],
         "answer_index": 1, "answer_source": "poll",
         "explanation_items": [],
         "explanation_from_admin": True, "stem": None, "status": "pending"},
        {"source": "visual", "kind": "visual", "channel_msg_id": 301, "date": "2026-11-13",
         "time_tehran": "20:30", "week_key": "2026-11-13",
         "hashtags": ["#حافظه_تصویری"], "caption": "حافظه تصویری: مراحل احیای قلبی ریوی",
         "caption_segments": [{"t": "حافظه تصویری: مراحل احیای قلبی ریوی", "b": True}],
         "explanation_items": [{"type": "text", "segments": [{"t": "توضیح عکس در کامنت ادمین: فشار قفسه سینه ۱۰۰ تا ۱۲۰ در دقیقه.", "b": False}]}],
         "explanation_from_admin": True, "status": "final"},
        {"source": "visual", "kind": "visual", "channel_msg_id": 302, "date": "2026-11-14",
         "time_tehran": "20:35", "week_key": "2026-11-13",
         "hashtags": ["#پمفلت_تصویری"], "caption": "پمفلت تصویری: مراقبت از کاتتر وریدی",
         "caption_segments": [{"t": "پمفلت تصویری: مراقبت از کاتتر وریدی", "b": True}],
         "explanation_items": [{"type": "text", "segments": [{"t": "توضیح پمفلت در کامنت‌ها آمده است.", "b": False}]}],
         "explanation_from_admin": True, "status": "final"},
        {"source": "visual", "kind": "visual", "channel_msg_id": 303, "date": "2026-11-21",
         "time_tehran": "20:30", "week_key": "2026-11-20",
         "hashtags": ["#حافظه_تصویری"], "caption": "حافظه تصویری: نوار قلب انفارکتوس",
         "caption_segments": [{"t": "حافظه تصویری: نوار قلب انفارکتوس", "b": True}],
         "explanation_items": [],
         "explanation_from_admin": True, "status": "pending"},
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--state", default="data/state.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--hashtags", default="#حافظه_تصویری,#پمفلت_تصویری,#پمفلت")
    args = ap.parse_args()

    items = sample_items() if args.sample else load_state(args.state).get("items", [])
    hashtag_order = [h.strip() for h in args.hashtags.split(",") if h.strip()]
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(args.out, "weekly"), exist_ok=True)

    quizzes = sort_items([i for i in items if i.get("kind") == "quiz"])
    visuals = sort_items([i for i in items if i.get("kind") == "visual"])

    report = {"total_quiz": len(quizzes), "total_visual": len(visuals),
              "quiz_no_answer": [i.get("channel_msg_id") for i in quizzes if not i.get("answer_index")],
              "quiz_no_explanation": [i.get("channel_msg_id") for i in quizzes if not i.get("explanation_items")],
              "visual_no_explanation": [i.get("channel_msg_id") for i in visuals if not i.get("explanation_items")],
              "quiz_no_number": [i.get("channel_msg_id") for i in quizzes if not i.get("printed_number")],
              "weeks": {}}

    if quizzes:
        doc = build_quiz_doc(quizzes, "بانک تست نورونرس — فایل کلی", "همه تست‌ها به‌ترتیب تاریخ انتشار")
        doc.save(os.path.join(args.out, "Neuronurse-Quiz-Kamel.docx"))
    if visuals:
        doc = build_visual_doc(visuals, "حافظه تصویری و پمفلت — فایل کلی", "همه موارد به‌ترتیب تاریخ، گروه‌بندی‌شده با هشتگ", hashtag_order)
        doc.save(os.path.join(args.out, "Neuronurse-Visual-Kamel.docx"))

    weeks = sorted({i.get("week_key") for i in items if i.get("week_key")})
    for wk in weeks:
        q = [i for i in quizzes if i.get("week_key") == wk]
        v = [i for i in visuals if i.get("week_key") == wk]
        label = week_label(wk)
        report["weeks"][wk] = {"label": label, "quiz": len(q), "visual": len(v)}
        if q:
            doc = build_quiz_doc(q, "تست‌های هفته نورونرس", f"هفته {label} — جمعه ساعت ۱۲ شب تا جمعه بعد ساعت ۱۲ شب")
            doc.save(os.path.join(args.out, "weekly", f"Quiz-{wk}.docx"))
        if v:
            doc = build_visual_doc(v, "حافظه تصویری و پمفلت هفته", f"هفته {label}", hashtag_order)
            doc.save(os.path.join(args.out, "weekly", f"Visual-{wk}.docx"))

    # خروجی JSON تمیز برای اپ و برای دادن به هوش مصنوعی:
    # دقیقاً همان شکل بانک تست خودت (questions.json) — فیلدهای ساده،
    # بدون سگمنت و بدون ساعت/تاریخ ارسال (اپ به آن‌ها نیاز ندارد).
    # داده کامل (سگمنت‌ها، stem و...) در data/state.json می‌ماند.
    def expl_text(it):
        parts = []
        for c in it.get("explanation_items") or []:
            if c.get("type") == "text":
                t = seg_text(c.get("segments")) or c.get("text", "")
                if t.strip():
                    parts.append(t)
            elif c.get("type") == "image":
                parts.append("فقط عکس بود")
        return "\n".join(parts)

    def clean_quiz(it):
        stem = (it.get("stem") or {}).get("text", "") or ""
        q = (stem.strip() + "\n" if stem.strip() else "") + (it.get("question", "") or "")
        return {
            "num": it.get("printed_number"),
            "question": q,
            "options": it.get("options", []),
            "answer": it.get("answer_index"),
            "explanation": expl_text(it),
            "source": "Neuro_Nurse",
            "week": it.get("week_key"),
            "image": it.get("image_path"),
        }

    def clean_visual(it):
        return {
            "caption": it.get("caption", ""),
            "hashtags": it.get("hashtags", []),
            "explanation": expl_text(it),
            "image": it.get("image_path"),
            "week": it.get("week_key"),
        }

    clean_q = [clean_quiz(i) for i in quizzes]
    clean_v = [clean_visual(i) for i in visuals]

    def write_json(path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    write_json(os.path.join(args.out, "questions-quiz.json"), clean_q)
    write_json(os.path.join(args.out, "Neuronurse-Quiz-Kamel.json"), clean_q)
    write_json(os.path.join(args.out, "questions-visual.json"), clean_v)
    write_json(os.path.join(args.out, "Neuronurse-Visual-Kamel.json"), clean_v)
    for wk in weeks:
        q = [clean_quiz(i) for i in quizzes if i.get("week_key") == wk]
        v = [clean_visual(i) for i in visuals if i.get("week_key") == wk]
        if q:
            write_json(os.path.join(args.out, "weekly", f"Quiz-{wk}.json"), q)
        if v:
            write_json(os.path.join(args.out, "weekly", f"Visual-{wk}.json"), v)

    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
