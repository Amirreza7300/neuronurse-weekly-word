# -*- coding: utf-8 -*-
"""
تست آفلاین parse_channel_number و parse_printed_number — بدون تلگرام و بدون شبکه.

collector.py موقع import به telethon نیاز دارد؛ این‌جا ماژول‌های telethon با
استاب‌های حداقلی جایگزین می‌شوند تا فقط منطق محض (تشخیص شماره و حذف پیشوند)
تست شود. نه به تلگرام وصل می‌شود، نه فایلی می‌خواند.

اجرا:
    python tests/test_parse_number.py
    python -m pytest tests/test_parse_number.py
"""
import os
import sys
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)


def _stub_telethon():
    """ماژول‌های telethon را با کلاس‌های خالی جایگزین کن تا import شدن
    collector.py (که موقع import به آن‌ها ارجاع می‌دهد) ممکن شود."""
    if "telethon" in sys.modules:
        return
    telethon = types.ModuleType("telethon")
    sessions = types.ModuleType("telethon.sessions")
    errors = types.ModuleType("telethon.errors")
    tl = types.ModuleType("telethon.tl")
    tl_types = types.ModuleType("telethon.tl.types")
    tl_funcs = types.ModuleType("telethon.tl.functions")
    channels = types.ModuleType("telethon.tl.functions.channels")
    messages = types.ModuleType("telethon.tl.functions.messages")

    class _Dummy:
        def __init__(self, *a, **k):
            pass

    telethon.TelegramClient = _Dummy
    sessions.StringSession = _Dummy
    errors.FloodWaitError = type("FloodWaitError", (Exception,), {})
    errors.RPCError = type("RPCError", (Exception,), {})
    errors.UserAlreadyParticipantError = type(
        "UserAlreadyParticipantError", (Exception,), {})
    for name in ("MessageMediaPoll", "MessageMediaPhoto", "MessageMediaDocument",
                 "MessageEntityBold", "MessageEntityItalic", "MessageEntityUnderline",
                 "MessageEntityStrike", "MessageEntityTextUrl",
                 "ChannelParticipantsAdmins", "PeerUser", "PeerChannel", "PeerChat"):
        setattr(tl_types, name, _Dummy)
    channels.GetFullChannelRequest = _Dummy
    channels.GetParticipantsRequest = _Dummy
    messages.SendVoteRequest = _Dummy
    messages.ImportChatInviteRequest = _Dummy
    messages.CheckChatInviteRequest = _Dummy

    sys.modules["telethon"] = telethon
    sys.modules["telethon.sessions"] = sessions
    sys.modules["telethon.errors"] = errors
    sys.modules["telethon.tl"] = tl
    sys.modules["telethon.tl.types"] = tl_types
    sys.modules["telethon.tl.functions"] = tl_funcs
    sys.modules["telethon.tl.functions.channels"] = channels
    sys.modules["telethon.tl.functions.messages"] = messages


_stub_telethon()

from collector import parse_channel_number, parse_printed_number  # noqa: E402


# (متن ورودی، شماره‌ی موردانتظار، متن بدون پیشوندِ موردانتظار)
CASES = [
    # ۱) ساده
    ("1773. #روان\nمتن سوال تستی؟",
     1773, "#روان\nمتن سوال تستی؟"),
    # ۲) ایموجی ابتدای خط + شماره
    ("⭐️ 567. #داخلی\nمتن سوال تستی؟",
     567, "#داخلی\nمتن سوال تستی؟"),
    # ۳) ایموجی + هشتگ + شماره
    ("⭐️ #582. #داخلی\nمتن سوال تستی؟",
     582, "#داخلی\nمتن سوال تستی؟"),
    # ۴) نیم‌فاصله (U+200C) قبل از نقطه
    ("142‌. #ویژه\nمتن سوال تستی؟",
     142, "#ویژه\nمتن سوال تستی؟"),
    # ۵) هشتگ در خط اول + شماره در خط دوم
    ("#CCU\n1773. متن سوال تستی؟",
     1773, "متن سوال تستی؟"),
    # ۶) رگرسیون: بدون شماره — متن دست نخورده برمی‌گردد
    ("متن سوال بدون شماره؟",
     None, "متن سوال بدون شماره؟"),
    # ۷) رگرسیون: خط اول فقط هشتگ، خط دوم هم شماره ندارد
    ("#CCU\nمتن سوال؟",
     None, "#CCU\nمتن سوال؟"),
    # ۸) رگرسیون: فهرست شماره‌دار داخل متن سوال اشتباه گرفته نمی‌شود
    ("متن سوال؟\n1. گزینه اول\n2. گزینه دوم",
     None, "متن سوال؟\n1. گزینه اول\n2. گزینه دوم"),
]


def test_parse_channel_number():
    for text, expected_num, _ in CASES:
        got = parse_channel_number(text)
        assert got == expected_num, f"{text!r}: got {got}, expected {expected_num}"


def test_parse_printed_number():
    for text, expected_num, expected_stripped in CASES:
        num, stripped = parse_printed_number(text)
        assert num == expected_num, f"{text!r}: num {num}, expected {expected_num}"
        assert stripped == expected_stripped, (
            f"{text!r}: stripped {stripped!r}, expected {expected_stripped!r}")
        # شماره نباید هم در تیتر بیاید هم اول متن سوال (باگِ دو بار آمدن)
        if num is not None:
            assert not stripped.startswith(str(num)), (
                f"{text!r}: number appears twice, stripped={stripped!r}")


def test_prefix_len_convention():
    """قرارداد prefix_len در process_poll: اختلاف طول رشته‌ی اصلی و رشته‌ی
    بدون پیشوند، همان تعداد کاراکتری است که از ابتدای متن حذف شده است."""
    for text, expected_num, expected_stripped in CASES:
        if expected_num is None:
            continue
        _, stripped = parse_printed_number(text)
        prefix_len = len(text) - len(stripped)
        assert prefix_len > 0, f"{text!r}: prefix_len must be positive"
        assert text[prefix_len:].lstrip() == stripped, (
            f"{text!r}: prefix_len {prefix_len} does not cut the prefix")


if __name__ == "__main__":
    tests = [test_parse_channel_number, test_parse_printed_number,
             test_prefix_len_convention]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__} ({len(CASES)} cases)")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    if failed:
        print(f"{failed} test(s) failed")
        sys.exit(1)
    print(f"OK: {len(tests)} test groups, {len(CASES)} cases each")
