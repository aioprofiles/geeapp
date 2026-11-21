"""UI strings. Sinhala + English complete; Tamil falls back to English until a native speaker adds strings."""
S = {
    "welcome": {"si": "🎵 <b>ගී</b> වෙත සාදරයෙන් පිළිගනිමු!\nසින්දුවක නමක්, පේළියක්, නැත්නම් හැඟීමක් ලියන්න.",
                "en": "🎵 <b>Welcome!</b>\nType a song name, a lyric line, or a feeling."},
    "help": {"si": ("<b>විධාන</b>\n/search නම · /feel හැඟීම · /lyric පේළිය\n/fav · /playlists · /history\n"
                    "/heardle · /dedicate · /diary · /wrapped · /match @user · /rhyme වචනය\n/reel · /premium · /lang\n"
                    "<b>Group:</b> /party /queue /duel /chain /missing /scramble /wordhunt /bingo /roulette /top /settings"),
             "en": ("<b>Commands</b>\n/search name · /feel feeling · /lyric line\n/fav · /playlists · /history\n"
                    "/heardle · /dedicate · /diary · /wrapped · /match @user · /rhyme word\n/reel · /premium · /lang\n"
                    "<b>Groups:</b> /party /queue /duel /chain /missing /scramble /wordhunt /bingo /roulette /top /settings")},
    "nothing": {"si": "කිසිවක් හමු වුණේ නැහැ. වෙන විදියකට ලියන්න.", "en": "Nothing found. Try different words."},
    "pick": {"si": "තෝරන්න:", "en": "Pick one:"},
    "no_lyrics": {"si": "මේ සින්දුවට lyrics තවම නැහැ. /sync එකෙන් ඔයාටත් එකතු කරන්න පුළුවන්.",
                  "en": "No lyrics for this track yet. You can contribute timings via the sync tool."},
    "dl_limit": {"si": "අද දවසේ free downloads ({n}) ඉවරයි. /premium බලන්න.", "en": "Free downloads for today ({n}) used up. See /premium."},
    "dl_off": {"si": "මේ සින්දුව download කරන්න අවසර නැහැ (licence).", "en": "Downloads are not permitted for this track (licence)."},
    "fav_on": {"si": "❤ Favorites වලට එකතු කළා", "en": "❤ Added to favourites"},
    "fav_off": {"si": "Favorites වලින් ඉවත් කළා", "en": "Removed from favourites"},
    "banned": {"si": "ඔයාට මේ bot පාවිච්චි කරන්න බැහැ.", "en": "You can't use this bot."},
    "admins_only": {"si": "මේක admins ට විතරයි.", "en": "Admins only."},
    "cooldown": {"si": "පොඩ්ඩක් ඉන්න ({s}s).", "en": "Slow down ({s}s)."},
    "heardle_intro": {"si": "🎧 අද Heardle! clip එක අහලා සින්දුවේ නම ලියන්න ({n}/{m}).", "en": "🎧 Today's Heardle! Listen and type the title ({n}/{m})."},
    "heardle_done": {"si": "අද Heardle කරලා ඉවරයි. හෙට ආයෙ එන්න!", "en": "You've finished today's Heardle. Come back tomorrow!"},
    "heardle_win": {"si": "🎉 හරි! <b>{t}</b>\nStreak: {s} 🔥", "en": "🎉 Correct! <b>{t}</b>\nStreak: {s} 🔥"},
    "heardle_lose": {"si": "😔 උත්තරය: <b>{t}</b>", "en": "😔 The answer: <b>{t}</b>"},
    "premium_on": {"si": "⭐ Premium {d} දක්වා.", "en": "⭐ Premium until {d}."},
    "dedicate_ask": {"si": "කාට කැප කරන්නද? <code>@username ඔයාගේ පණිවිඩය</code> විදියට එවන්න.", "en": "Who is it for? Send <code>@username your message</code>."},
    "dedicate_when": {"si": "කවදාද යවන්නේ?", "en": "When should it be sent?"},
    "dedicate_saved": {"si": "✅ සුරැකුවා. {w}", "en": "✅ Saved. {w}"},
    "ded_head": {"si": "🎁 ඔයාට සින්දුවක් කැප කරලා!", "en": "🎁 A song was dedicated to you!"},
    "diary_ask": {"si": "මේ සින්දුව ගැන ඔයාගේ සටහන එවන්න:", "en": "Send your note for this song:"},
    "diary_saved": {"si": "📔 සටහන සුරැකුවා. අවුරුද්දකින් මතක් කරනවා.", "en": "📔 Saved. I'll remind you in a year."},
    "sync_hint": {"si": "Mini App එකේ 'Sync' tab එකෙන් lyrics timing කරන්න.", "en": "Use the Sync tab in the Mini App to time the lyrics."},
    "done": {"si": "හරි ✅", "en": "Done ✅"},
}


def t(lang: str, key: str, **kw) -> str:
    d = S.get(key, {})
    s = d.get(lang) or d.get("en") or key
    return s.format(**kw) if kw else s
