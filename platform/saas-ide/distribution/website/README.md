# Publishing AEP-X on www.softwareequality.com

Everything here is generated: edit `../releases.json` or `../generate_downloads.py`, then run
`python3 distribution/generate_downloads.py` (CI fails if the committed pages are stale).

| File | Live URL | Why |
| --- | --- | --- |
| `static/app-ads.txt` | `https://www.softwareequality.com/app-ads.txt` | **Required by AdMob.** Without it at the domain root, ads in the Android/iOS apps are limited. |
| `static/aepx/index.html` | `https://www.softwareequality.com/aepx/` | Product, plans and downloads page |
| `static/aepx/privacy.html` | `https://www.softwareequality.com/aepx/privacy.html` | Privacy policy, required by Google Play for apps with ads or payments. Use this URL in Play Console. |
| `static/aepx/*.png, *.svg, favicon.ico` | `/aepx/...` | Logo, favicon, social preview image |

## Option 1: Hostinger / cPanel (static upload)
1. Open **File Manager** (Hostinger hPanel → Websites → Manage → File Manager, or cPanel → File Manager).
2. Go to `public_html` and upload `aepx-website-static.zip`, then **Extract** it there.
   You should now have `public_html/app-ads.txt` and `public_html/aepx/`.
3. Check in a browser: `https://www.softwareequality.com/app-ads.txt` shows one line starting `google.com, pub-2980680946304710`,
   and `https://www.softwareequality.com/aepx/` shows the AEP-X page.

## Option 2: WordPress
WordPress cannot serve a file at the domain root by itself, so do step 1 of Option 1 for `app-ads.txt` and the `/aepx/` folder
(the logo and privacy page live there too). Then:
1. **Pages → Add New**, title "AEP-X Agentic IDE", slug **`aepx-ide`** (not `aepx`: that name is the uploaded folder).
2. Add a **Custom HTML** block and paste the whole of `wordpress/aepx-downloads-block.html`. Publish.
3. Optional: a "AEP-X privacy" page with `wordpress/aepx-privacy-block.html`. The static `/aepx/privacy.html` already works,
   so Play Console can keep using that URL.
4. Add the page to your menu (Appearance → Menus, or Site Editor → Navigation).

If a security plugin strips `<style>` from Custom HTML, allow it for administrators, or use Option 1's page at `/aepx/`.

## After publishing
- AdMob → Apps → AEP-X → **app-ads.txt** tab: click *Check for updates*. Verification can take up to 24 hours.
- In Play Console, set the developer website to `https://www.softwareequality.com`. AdMob reads app-ads.txt from the
  developer website listed on the store page, so both must use the same domain.
- When a signed build or store listing goes live, fill its entry in `releases.json`. Download buttons appear only for
  signed, checksummed files on `downloads.softwareequality.com`; store buttons appear once their links are set.
