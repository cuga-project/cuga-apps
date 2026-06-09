---
title: CUGA Apps
emoji: 🚀
colorFrom: indigo
colorTo: purple
sdk: static
pinned: false
---

# CUGA Apps — umbrella UI

A lightweight launcher for the CUGA ship-ready apps. The apps, the MCP servers,
and the usage/stats dashboard all run as a **single all-in-one service on IBM
Code Engine**; this Space ships no backend of its own — it only links into that
service's path routes (`<ce-host>/a/<app>/`).

Rebuild / repoint with `build/hf/build.sh` in the source repo (it bakes the CE
base URL into the static bundle).
