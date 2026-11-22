# Knoxville Deal Hunter — Daily Edition

## What it does

- Keeps the previous styled dashboard, coupon terms, and multi-checkout reward optimizer.
- On every opening, fetches the newest `data/latest.json` from your hosted site with cache bypass.
- Shows a daily compilation of new, changed, and no-longer-in-feed public deal posts **since the browser's previous visit**, plus source failures and last successful collection time.
- Runs a **scheduled** GitHub Actions collector at approximately 8–9 AM Eastern, if deployed and enabled. You can also manually run the workflow on GitHub's Actions page.
- Discovers store-related RSS headlines across CVS, Walgreens, Kroger, Publix, Walmart, Target, Dollar General, Food City, Costco, Sam's Club, and ALDI, but only if these feeds have matching posts.
- Never treats RSS headline discounts as verified coupon stacks. Numerical deal ranking requires a separately, manually checked complete-basket offer with `verified_at` equal to today. Old November 16 numbers are hidden unless you choose **Show historical demonstration deals**.

## Deploy and keep the site updated

The included GitHub Actions workflow runs on initial pushes, on demand, and daily at 13:17 UTC (8:17 AM EST / 9:17 AM EDT). It tests and executes the collector, commits new data to `main`, **and explicitly publishes a GitHub Pages artifact**. This explicit publish is important: a commit made with the default `GITHUB_TOKEN` does not trigger a Pages build on its own.

1. Upload repository contents including `.github/workflows/refresh-deals.yml`.
2. Go to **Settings → Pages → Build and deployment**. Select **GitHub Actions** as the source if it is not already enabled. The workflow uses `actions/configure-pages` with `enablement: true` to try first-time provisioning, but GitHub may require an administrator to enable Pages manually.
3. Review **Actions → Refresh and Publish Knoxville Deals**. Check the first run and, if needed, select **Run workflow** to retry after enabling Pages. If GitHub reports an authorization error for workflow commits, check **Settings → Actions → General → Workflow permissions** for read/write permission; the workflow requests `contents: write`.
4. The expected site address is `https://jacksonschne123-max.github.io/knoxville-deal-hunter/` once GitHub reports a successful Pages deployment. Opening it loads the latest published snapshot and displays a digest of changes since the previous visit.

**Important:** This deploy does not alter the old `chatgpt.site` URL. A plain local HTML file cannot run background collection. Scheduled Actions can be delayed and source feeds may fail; the app labels incomplete/stale collections.

## Where the data comes from

The Python collector reads two publicly listed RSS feeds: The Krazy Coupon Lady RSS and Slickdeals Frontpage RSS. These are **third-party deal discovery leads**, not official per-account retailer product catalogs. It attempts one request per feed per day, with 15-second timeouts, no authentication or access-control evasion, and keeps only post titles, short excerpts, source links, and metadata. Sources may rate-limit, disallow, or change their feeds at any time; respect their usage policies. No official feed exists for the whole coupon catalog of every retailer.

When a source fails, the dashboard reports the failure. Stale leads may remain marked **NOT RECHECKED** for up to 12 days; an RSS feed no longer containing a post does not establish that the deal expired. Account-specific coupon and local Knoxville shelf prices are not verified by this collector.

For high-confidence *numeric* rankings, manually verify the basket, exact products, coupon compatibility, reward spend calculation, limits, location, and expiration, then add an object to `data/reviewed_deals.json` with: `id`, `store`, `item`, `regular`, `checkout`, `earn` (fields `eb`, `wc`, `rr`, `rebate` as applicable), `expires` in YYYY-MM-DD, `verified_at` in YYYY-MM-DD, `source`, and `terms`. Sample:

```json
[
  {
    "id":"cvs-verified-sample","store":"CVS","item":"Example 2 qualifying products",
    "regular":12.00,"checkout":9.00,"earn":{"eb":4},
    "expires":"2026-11-29","verified_at":"2026-11-22",
    "source":"https://www.cvs.com/","terms":"DEMONSTRATION ONLY; NOT a real validated current offer",
    "q":1
  }
]
```

This sample is deliberately **not** included in the live file. It illustrates the required schema. Revenue from store rewards is not cash profit; tax, account eligibility, posting delay and reward restrictions still apply.

## Technical verification

`python -m unittest discover -s tests -v` tests RSS parsing, store extraction, stable comparison, source failures and same-day numeric deal validation. No Python dependencies beyond the standard library are needed for the collector.

For local browser preview, run `python -m http.server 8000` in this directory and open `http://localhost:8000`. To run the collector locally, execute `python scripts/update_deals.py`. Merely opening `index.html` from the filesystem cannot refresh remote RSS content.

## Running costs and limits

GitHub Pages + Actions can be free within account plan limits; check your account. Scheduled GitHub Actions jobs can be delayed, and public-repository schedules may be disabled after 60 days of inactivity; monitor the source-health timestamps in the dashboard. Feed availability and merchant terms are outside this project's control.