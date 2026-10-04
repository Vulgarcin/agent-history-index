# AHI Global Index Free

The public website is free. No Pro tier or paywall is enabled.

## Local preview

Run `python -m http.server 8000 --directory web` from the repository root.
Open http://localhost:8000. The local server must remain running.

## Publication

Enable GitHub Pages in repository Settings > Pages, with Source set to GitHub Actions.
`Publish AHI Website` publishes only the HTML, CSS, JavaScript and four public JSON files.
It runs on website changes, manually, and after successful daily capture or backfill.
The workflow follows the current main branch so collector bot commits are included.
The historical evidence, signing material and collector code are not packaged into the website.
