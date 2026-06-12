# GitHub social preview

`trentpower-fr-github-social.png` (1280 × 640) is the card GitHub shows
when the repository is shared. It is rendered in the print register of
README.pdf — warm paper, iron ink, restrained oxblood — from the site's
own licensed fonts; no external assets.

Regenerate (fonts are untracked — restore them first):

    python3 tools/build/fetch_licensed_fonts.py
    python3 tools/visual/build_github_social_preview.py

Apply manually in GitHub:
**Settings → General → Social preview → Edit → Upload an image**

Uploading changes nothing on the site or in the repository — GitHub
serves the card from its own CDN.
