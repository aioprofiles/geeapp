"""Test doubles: a stub `httpx` (not installed in CI sandbox) and a recording Telegram client."""
import sys
import types

if "httpx" not in sys.modules:
    m = types.ModuleType("httpx")

    class AsyncClient:
        def __init__(self, *a, **k): pass
        async def aclose(self): pass

    class HTTPError(Exception): pass
    m.AsyncClient, m.HTTPError = AsyncClient, HTTPError
    sys.modules["httpx"] = m


class FakeTg:
    def __init__(self):
        self.log, self.mid = [], 100
        self.http = None

    def _r(self, name, args, kw):
        self.log.append((name, args, kw))
        self.mid += 1
        chat = (args[0] if args and isinstance(args[0], int) else kw.get("chat_id", 0))
        return {"message_id": self.mid, "chat": {"id": chat}, "poll": {"id": f"poll{self.mid}"}}

    def __getattr__(self, name):
        async def f(*a, **k):
            return self._r(name, a, k)
        return f

    async def call(self, method, **kw):
        self.log.append((method, (), kw))
        self.mid += 1
        if method == "getChatMember":
            return {"status": "administrator" if kw.get("user_id") == 999 else "member"}
        if method == "getChat":
            return {"id": -1001}
        if method == "stopPoll":
            return {"options": [{"voter_count": 3}, {"voter_count": 1}]}
        return {"message_id": self.mid, "chat": {"id": kw.get("chat_id", 0)}, "poll": {"id": f"poll{self.mid}"}}

    try_call = call

    async def poll_quiz(self, chat_id, question, options, correct, **kw):
        return await self.call("sendPoll", chat_id=chat_id, question=question, options=options,
                               type="quiz", correct_option_ids=[correct], **kw)

    def calls(self, name):
        return [(a, k) for n, a, k in self.log if n == name]

    def texts(self):
        out = []
        for n, a, k in self.log:
            if n in ("send", "send_rich", "edit"):
                out.append(str(a[1] if n != "edit" else a[2]))
        return out
