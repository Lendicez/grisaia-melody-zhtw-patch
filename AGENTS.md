# Development rules

- Source, synthetic tests and zh-TW translations only. Never commit game files, extracted scripts, Japanese source text, screenshots, saves or binaries derived from game data.
- Translation output files contain only `id` and `zh`. Source text lives only in the local lab (`C:\GameDev\grisaia-melody-lab`).
- Do not modify the user's Steam install except through the installer (backup in `_zhTW_backup`, reversible).
- Proper nouns follow `translation/glossary.zh-TW.json`; changes need a source/basis note.
- Every translation batch must pass `translation/validate.py`.
- Installer changes must pass `tools/make_installer.py` self-test (status → install → byte-compare with Python build → uninstall restores originals).
