# Public site

The site is built from the records, not written by hand:

- one page per finding (`community/findings/F*.json`) and per contribution (`community/contributions/C*.json`), so it holds thousands of them;
- a findings list with search and a stage filter, and the stage counts on the overview;
- the prose pages named in `site/config.json`. `<!-- findings-list -->` and `<!-- contributions-list -->` in a page mark where a list goes.

The stage of a finding comes from its record. GitHub adds what only the tracker knows: comment counts, last activity, and issues filed as findings that have no record yet (shown by number only). Without network access the site builds from the records alone; `--offline` forces that, `--issues FILE` reads a snapshot, and `--require-issues` fails the build when GitHub cannot be read, which the deploy uses so a failed read keeps the last published site.

```sh
uv run --no-project --with markdown==3.7 scripts/build_site.py
python3 scripts/check_site.py _site
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

`_site/` is ignored. It also holds `findings.json` and `status.json`, a machine-readable index for other projects. Inventory files, licensed data and private evidence are never build inputs, and `check_site.py` refuses data file types in the output.

[The Documentation workflow](../.github/workflows/pages.yml) deploys to GitHub Pages after a push to `main`, once a day, and when an issue is opened, closed or relabelled. Pull requests build and check the site without deploying it.

The design follows [Départ de Sentier's website](https://www.d-d-s.ch/): the green logo from [Depart-de-Sentier/dds-logo](https://github.com/Depart-de-Sentier/dds-logo) by Sylvain Prevost (CC BY 4.0), Nunito from [Google Fonts](https://github.com/google/fonts/tree/main/ofl/nunito) under `site/assets/OFL.txt`, dark green `#3C5343`, beige `#F0EEE1` and sage `#84AE99`. The renderer and stylesheet are meant to be shared with the sibling dataset sites; dataset-specific text lives in `site/config.json` and the Markdown sources.
