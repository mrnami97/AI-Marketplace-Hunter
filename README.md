AI Marketplace Hunter v0.2.2

CHANGED/NEW FILES:
- app.py
- handlers.py
- database.py
- watcher.py
- marketplace_utils.py (NEW)
- crawler/carousell.py
- requirements.txt

INSTALL:
1. Stop the bot with Ctrl+C.
2. Copy these files into the project, keeping crawler/carousell.py inside crawler.
3. Run:
   py -m pip install -r requirements.txt
4. Run:
   py app.py

COMMANDS:
- /search RTX 3070 under RM1200 best
- /search RTX 3070 under RM1200 newest
- /search RTX 3070 under RM1200 cheapest
- /current 2 best
- /current 2 newest
- /current 2 cheapest
- /check 2
- /status

FEATURES:
- Blocks box-only, broken, repair, parts-only and similar listings.
- Rejects weakly relevant titles.
- Ignores listings older than 30 days.
- Sorts by best score, newest or cheapest.
- Local AI-style scoring: relevance + freshness + relative price.
- Compact Telegram table.
- Clickable "Click Here" links.

NOTE:
This release uses local scoring and does not require an OpenAI API key.
