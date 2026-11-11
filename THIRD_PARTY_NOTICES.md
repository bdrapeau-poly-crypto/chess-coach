# Third-party notices

The original Chess Coach application code is licensed under GPL-3.0-or-later.
Third-party software and development materials retain their own licenses.

## Neon agent skills

The materials under `.agents/skills/`, other than the license file added here,
were installed from [neondatabase/agent-skills](https://github.com/neondatabase/agent-skills).
Their source paths and content hashes are recorded in `skills-lock.json`.
These materials remain under the Apache License, Version 2.0, reproduced in
[.agents/skills/LICENSE](.agents/skills/LICENSE). No project copyright claim is
made over those third-party materials.

## python-chess

The backend imports [python-chess](https://github.com/niklasf/python-chess),
licensed under GNU GPL version 3 or later. Its authors retain their copyright.
It is installed as a dependency and its source is not vendored in this repository.

## Stockfish

The backend communicates with [Stockfish](https://github.com/official-stockfish/Stockfish)
through UCI. Stockfish is separately licensed under GNU GPL version 3.
The Docker build installs the Debian package; this repository contains no
Stockfish executable or source. Anyone distributing a built image or executable
must also satisfy the applicable third-party license and source obligations.

## Other dependencies and data

Python and JavaScript dependencies retain their respective licenses and notices.
Their license files accompany the installed packages. The project license does
not replace those terms or license third-party Chess.com data, provider services,
fonts, or trademarks. The demo PGNs in the application are illustrative fixtures.
