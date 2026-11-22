# -*- coding: utf-8 -*-
"""
تست آفلاین select_reply_chain — بدون تلگرام و بدون شبکه.

توضیح پست‌های کانال تصویری از ریپلای‌های داخل خود کانال روی همان پست
می‌آید (گروه Discussion نیست). select_reply_chain منطق محض انتخاب
زنجیره است؛ این‌جا با پیام‌های جعلی تست می‌شود. موقع import کردن
collector.py ماژول‌های telethon با استاب‌های حداقلی جایگزین می‌شوند.

اجرا:
    python tests/test_visual_replies.py
    python -m pytest tests/test_visual_replies.py
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

from collector import select_reply_chain  # noqa: E402


class FakeMsg:
    """پیام جعلی: فقط id و reply_to که select_reply_chain لازم دارد."""

    def __init__(self, mid, reply_to=None):
        self.id = mid
        self.reply_to = (
            types.SimpleNamespace(reply_to_msg_id=reply_to)
            if reply_to is not None else None
        )


def ids(run):
    return [m.id for m in run]


def test_direct_replies_to_post():
    msgs = [FakeMsg(101, 100), FakeMsg(102, 100), FakeMsg(103, 100)]
    assert ids(select_reply_chain(msgs, [100], 9)) == [101, 102, 103]


def test_chain_reply_to_reply():
    msgs = [FakeMsg(101, 100), FakeMsg(102, 101), FakeMsg(103, 102)]
    assert ids(select_reply_chain(msgs, [100], 9)) == [101, 102, 103]


def test_replies_to_album_unit():
    # آلبوم دو آیدی دارد؛ ریپلای روی هر کدام از آن‌ها جزو زنجیره است.
    msgs = [FakeMsg(102, 101), FakeMsg(103, 100), FakeMsg(104, 103)]
    assert ids(select_reply_chain(msgs, [100, 101], 9)) == [102, 103, 104]


def test_reply_to_other_post_excluded():
    msgs = [FakeMsg(101, 555), FakeMsg(102, 100)]
    assert ids(select_reply_chain(msgs, [100], 9)) == [102]
    # ریپلای روی یک پیام ردشده هم وارد زنجیره نمی‌شود، چون پدرش قبول نشده.
    msgs = [FakeMsg(101, 555), FakeMsg(102, 101), FakeMsg(103, 100)]
    assert ids(select_reply_chain(msgs, [100], 9)) == [103]


def test_cap_nine_respected():
    msgs = [FakeMsg(100 + i, 100) for i in range(1, 16)]
    run = select_reply_chain(msgs, [100], 9)
    assert len(run) == 9, f"cap: got {len(run)}, expected 9"
    assert ids(run) == list(range(101, 110))


def test_interleaved_non_replies_do_not_break_chain():
    msgs = [FakeMsg(101, 100), FakeMsg(102), FakeMsg(103, 101), FakeMsg(104)]
    assert ids(select_reply_chain(msgs, [100], 9)) == [101, 103]


def test_own_album_message_not_a_reply():
    # پیام دوم آلبوم (آیدی ۱۰۱) در جریان پیام‌های بعد از پست هم دیده
    # می‌شود؛ حتی اگر reply_to داشته باشد، توضیح حساب نمی‌شود.
    msgs = [FakeMsg(101, 100), FakeMsg(102, 100), FakeMsg(103, 102)]
    assert ids(select_reply_chain(msgs, [100, 101], 9)) == [102, 103]


def test_empty_and_no_replies():
    assert select_reply_chain([], [100], 9) == []
    msgs = [FakeMsg(101), FakeMsg(102, 999)]
    assert select_reply_chain(msgs, [100], 9) == []


if __name__ == "__main__":
    tests = [test_direct_replies_to_post, test_chain_reply_to_reply,
             test_replies_to_album_unit, test_reply_to_other_post_excluded,
             test_cap_nine_respected,
             test_interleaved_non_replies_do_not_break_chain,
             test_own_album_message_not_a_reply, test_empty_and_no_replies]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    if failed:
        print(f"{failed} test(s) failed")
        sys.exit(1)
    print(f"OK: {len(tests)} test groups")
