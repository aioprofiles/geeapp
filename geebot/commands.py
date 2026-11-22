"""Command menus (setMyCommands): default scope for private chats + a shorter list for groups."""
PRIVATE = [("start", "Main menu"), ("menu", "Main menu"), ("search", "Find a song"), ("feel", "Search by feeling"),
           ("lyric", "Find by a lyric line"), ("heardle", "Daily clip game"), ("fav", "Your favorites"),
           ("playlists", "Your playlists"), ("history", "Recently played"), ("dedicate", "Dedicate a song"),
           ("diary", "Song diary"), ("wrapped", "Your year in music"), ("match", "Taste match with a friend"),
           ("rhyme", "Rhyme finder"), ("beat", "Beat Tap widget game"), ("donate", "Support with Stars"),
           ("premium", "Premium"), ("lang", "Language"), ("privacy", "Privacy & FAQ"), ("about", "About"), ("help", "Help")]
GROUP = [("party", "Start a listening party"), ("request", "Request a song"), ("queue", "Show the queue"),
         ("duel", "Blind-test duel"), ("chain", "Lyrics chain"), ("missing", "Missing word quiz"),
         ("scramble", "Unscramble lyrics"), ("wordhunt", "Word hunt"), ("bingo", "Music bingo"),
         ("roulette", "Karaoke roulette"), ("hum", "Hum it"), ("team", "Team battle"), ("top", "Leaderboard"),
         ("settings", "Group settings (admins)"), ("help", "Help")]
SI = {"start": "ප්‍රධාන මෙනුව", "menu": "ප්‍රධාන මෙනුව", "search": "සින්දුවක් සොයන්න", "heardle": "දිනපතා ක්‍රීඩාව",
      "donate": "Stars වලින් සහාය වන්න", "help": "උදව්", "privacy": "පෞද්ගලිකත්වය සහ FAQ", "about": "ගැන"}


async def install(tg):
    await tg.set_commands(PRIVATE)
    await tg.set_commands([(c, SI.get(c, d)) for c, d in PRIVATE], language_code="si")
    await tg.try_call("setMyCommands", commands=[{"command": c, "description": d} for c, d in GROUP],
                      scope={"type": "all_group_chats"})
