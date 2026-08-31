# ai-checkkit — AI-era Python lint bundle

Catch the silent footguns AI leaves behind: no-op stubs that ship as `None`, `assert`s that vanish under `-O`, builtin shadowing, mutable defaults.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)](https://github.com/Rituparno-Majumdar/ai-checkkit)

Bundles 4 focused linters that previously shipped as `stubcheck`, `assertcheck`, `shadowcheck`, `mutablecheck` — now one `pip install`.

## Why ai-checkkit?

| Footgun | What it catches | Why AI creates it |
| :--- | :--- | :--- |
| **stubcheck** | `def handler(): pass` / `...` bodies that return `None` | AI scaffolds callbacks/handlers with placeholders |
| **assertcheck** | `assert <cond>` for runtime validation | LLMs copy test-style asserts into production |
| **shadowcheck** | `def foo(list, id):` shadowing builtins | Autocomplete reuses builtin names as params |
| **mutablecheck** | `def foo(x=[])` aliasing | Classic Python gotcha amplified by generation |

All 4 are zero-dependency, pure-`ast`, <0.1s on 10k lines.

## Install

Requires Python 3.9+.

```bash
pip install ai-checkkit

# or editable for dev
pip install -e .[dev]
```

Backward compat aliases still work: `stubcheck`, `assertcheck`, `shadowcheck`, `mutablecheck` point to the same bundle.

## Quick start

```bash
# Run all 4 checks (default)
ai-checkkit
ai-checkkit all ./src --check --json

# Individual linters (same flags as standalone)
ai-checkkit stubcheck ./src --min-severity medium --include-test
ai-checkkit assertcheck ./src --min-severity high
ai-checkkit shadowcheck ./src --allow id,type
ai-checkkit mutablecheck ./src --allow __init__

# Legacy aliases
stubcheck ./src --check
assertcheck --json ./src
```

**Python API**

```python
from ai_checkkit.stubcheck import detect as stub_detect
from ai_checkkit.assertcheck import detect as assert_detect
from ai_checkkit.shadowcheck import detect as shadow_detect
from ai_checkkit.mutablecheck import detect as mutable_detect

findings = stub_detect(open("app.py").read(), "app.py")
```

## Comparison vs separate installs

| Before | After |
| :--- | :--- |
| `pip install stubcheck assertcheck shadowcheck mutablecheck` (4 repos, 4 CIs) | `pip install ai-checkkit` (1 repo, 1 CI) |
| 4 READMEs, 4 badges | 1 unified README + `ai-checkkit all` |

## Development

```bash
pip install -e .[dev]
pytest -q --cov=ai_checkkit
```

## License

MIT — see [LICENSE](LICENSE).

## Links

- Homepage: https://github.com/Rituparno-Majumdar/ai-checkkit
- Issues: https://github.com/Rituparno-Majumdar/ai-checkkit/issues
- Changelog: https://github.com/Rituparno-Majumdar/ai-checkkit/blob/main/CHANGELOG.md
# test
