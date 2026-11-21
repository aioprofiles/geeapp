# ගී (geebot) — Telegram music bot

Search, synced lyrics, video, downloads **with lyrics embedded**, plus games, dedications, wrapped, and community lyric timing.
Built on Bot API 10.x features: rich messages, HTML widgets, guest mode, Stars payments, quiz polls.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env && export $(grep -v '^#' .env | xargs)   # fill BOT_TOKEN, BOT_USERNAME, OWNER_IDS, ...
python -m geebot.main                                           # bot (long polling + scheduler)
uvicorn webapp.server:app --port 8080                           # Mini App backend, serve over HTTPS
python -m unittest discover -s tests -t .                       # 56 tests
```
BotFather setup: enable **Guest Mode**; create a Mini App with short name = `APP_SHORT` pointing to `WEBAPP_URL/app`;
turn **privacy mode off** (or make the bot admin) so plain-text game guesses are seen in groups (`/g title` works regardless).
Stars payments need no provider token (`currency=XTR`).

## Deploy on Render (free)
Facts from Render's docs (check them again, they change): free web services spin down after 15 min without inbound traffic,
have an **ephemeral filesystem**, may restart at any time, get 750 instance-hours/month per workspace, and have no persistent disk.
Free Postgres expires after 30 days and has no backups. So this repo runs as **one** free web service (`geebot/serve.py` = Mini App API +
bot long-polling + scheduler) and keeps its SQLite database in Telegram (`geebot/backup.py`).
1. Push this folder to a (private) GitHub repo. Message your bot once with /start (so it may DM you).
2. Render -> New -> Blueprint -> pick the repo (uses `render.yaml`, Docker, plan: free). Fill the env vars:
   `BOT_TOKEN, BOT_USERNAME, OWNER_IDS, BACKUP_CHAT_ID (= your user id), JAMENDO_CLIENT_ID`, optional `ANTHROPIC_API_KEY`.
3. After the first deploy copy the service URL into `WEBAPP_URL` (https://<name>.onrender.com) and redeploy.
4. BotFather: Mini App short name = `APP_SHORT`, URL = `WEBAPP_URL/app`; enable Guest Mode; privacy mode off.
5. Keep it awake: a free uptime monitor (UptimeRobot / cron-job.org) hitting `WEBAPP_URL/healthz` every 5 min.
   Without it the bot sleeps and scheduled dedications / game timers do not fire.
6. Check: `/stats` as owner works; a pinned `geebot-backup.sqlite.gz` appears in your chat with the bot within ~5 min.
Limits: last <=5 min of data can be lost on a hard crash; backup must stay < 20 MB compressed (restore uses getFile);
a redeploy briefly runs two pollers (harmless `Conflict` log lines); cold start up to ~1 min; 512 MB RAM.
Verify the Sinhala font path with `fc-list :lang=si` inside the container (needed only for reels).

## Content policy (read before launching)
* Catalogue = **Creative-Commons music (Jamendo)** + tracks uploaded by approved artists. No YouTube/Spotify ripping.
* Video = official YouTube **embed**, play only.
* Download only when `downloadable=1` (Jamendo's per-track permission, or the uploader's declaration).
* Reels (remix video) only for licences without ND (`features.lyric_reel_ok`).
* Lyrics: owner/artist/community-contributed. `USE_LRCLIB=1` is off by default — enabling it makes you responsible for lyric licensing.
* `/report`, `/takedown <id>` give you a takedown path. Add your own Terms/contact before going public.

## Feature map
| Area | Where | Status |
|---|---|---|
| Search by title / half-remembered lyric / feeling | `search.py` | tested (feeling uses Claude if `ANTHROPIC_API_KEY`, else keyword map) |
| Song card (rich message + buttons) | `cards.py`, `tg.send_rich` | tested; **rich-message param shape unverified** → auto-fallback to HTML message |
| Karaoke widget (private chat) | `widgets.py`, `wq.py` | tested logic + JS syntax; 1066 B compressed (limit 4096); **never run inside a real client** |
| Beat Tap widget | `widgets.py` | same as above |
| Mini App player (audio, YouTube, synced lyrics, Singlish, party, sync tool) | `webapp/` | JS syntax-checked; server **not run** (FastAPI not installed in my sandbox) |
| Download + lyrics in ID3 + `.lrc` | `user.send_download`, `media.py` | tested with real ffmpeg |
| Daily Heardle + streak + share card | `games.py`, `user.py` | tested |
| Dedications (scheduled, anonymous option) | `features.py`, `sched.py` | tested |
| Diary / time capsule, Wrapped, taste match, rhymes | `features.py` | tested |
| Playlists, favourites, history | `user.py` | tested |
| Group: party, queue, duel, chain, missing word, scramble, odd-one-out, before/after, word hunt, bingo, karaoke roulette, sing-off, hum-it, team battle, tournament, leaderboard | `group.py` | tested with a fake Telegram client |
| Admin: settings, cooldown, who-can-play, welcome, owner stats/ban/takedown/artist role, uploads, approve lyric timings + badges | `admin.py`, `group.py` | tested |
| Channels: daily "song of the day" | `admin.cmd_channel`, `sched.py` | tested |
| Guest mode (`@bot` in any chat; translate/explain/identify song) | `guest.py` | tested; **Update field names unverified** |
| Stars premium | `main.on_payment` | logic tested; **never run against real Stars** |
| Lyric reel video | `media.make_reel` | filter builder tested; render needs a Sinhala font (`FONT_FILE`) |

## Known gaps / things to verify against the live docs
1. `sendRichMessage` parameters, `guest_message`/`guest_query_id` field names, button `style` values — I could only confirm `answerGuestQuery(guest_query_id, result: InlineQueryResult)`, `sendWidget`, `answerWidgetQuery`, `editMessageWidgetData`.
2. **Widget limits that shaped the design:** no network/audio/video inside widgets; state strings ≤1024 B (lyrics are streamed in chunks); widgets only work in the private chat in production (groups/inline/forwards = test server, `TEST_ENV=1`); widgets can't go in channels.
3. Karaoke widget sync is **approximate** (its own clock + ±0.5 s nudge); exact sync is in the Mini App.
4. Beat Tap scores come from the client — fine for fun, not for prizes.
5. Tamil UI strings fall back to English (needs a native speaker). Sinhala romanisation is approximate.
6. Group quiz polls award +2 per correct answer (via `poll_answer`); guess-by-text games need privacy mode off.
7. Stars → cash-out, artist tip payouts, and an "image" Wrapped card are not built.
8. Single process, SQLite, long polling: fine for thousands of users, not millions.
