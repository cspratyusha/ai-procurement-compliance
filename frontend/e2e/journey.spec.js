import { test, expect } from '@playwright/test';

/**
 * The full user journey, against a live backend.
 *
 * These cover what unit tests cannot: that the frontend and backend agree on
 * the response shape, that CORS permits the call at all, and that the honesty
 * guarantees survive the round trip, an out-of-scope query must not produce a
 * recommendation in the browser, whatever the API returned.
 */

test.describe('Search', () => {
  test('an in-scope query returns recommendations with certification flags', async ({ page }) => {
    await page.goto('/app/query');

    await page.fill('#spec', 'PVC insulated copper cable for indoor panel wiring');
    await page.click('button[type=submit]');

    const cards = page.locator('article.rec');
    await expect(cards.first()).toBeVisible({ timeout: 120_000 });
    expect(await cards.count()).toBeGreaterThan(0);

    await expect(page.locator('h2', { hasText: 'Recommended standards' })).toBeVisible();

    // IS 694 is under a real Quality Control Order; the flag must survive.
    await expect(page.locator('.badge-accent').first()).toBeVisible();
  });

  test('an everyday product word finds its standard and its BIS listing', async ({ page }) => {
    // "Laptop" shares no words with "information technology equipment".
    await page.goto('/app/query');
    await page.fill('#spec', 'laptop for office use');
    await page.click('button[type=submit]');

    await expect(page.locator('[data-demo-target="query-expansion"]'))
      .toContainText('information technology equipment', { timeout: 120_000 });
    await expect(page.locator('article.rec').first()).toContainText('IS 13252');
    const bis = page.locator('[data-demo-target="query-bis-products"]');
    await expect(bis).toContainText('Laptop');
    await expect(bis).toContainText('CRS');
  });

  test('gold jewellery names compulsory hallmarking and its order', async ({ page }) => {
    // Hallmarking of Gold Jewellery and Gold Artefacts Order, 2020, as amended.
    await page.goto('/app/query');
    await page.fill('#spec', 'gold jewellery purity and marking');
    await page.click('button[type=submit]');

    const bis = page.locator('[data-demo-target="query-bis-products"]');
    await expect(bis).toContainText('BIS hallmark with HUID', { timeout: 120_000 });
    await expect(bis).toContainText('IS 1417');
    await expect(bis).toContainText('Hallmarking of Gold Jewellery');
    await expect(page.locator('article.rec').first()).toContainText('IS 1417');
  });

  test('an out-of-scope query refuses to recommend', async ({ page }) => {
    // The query has to be outside coverage whatever corpus is served.
    //
    // This used to search "banana fruit crates", which was out of scope for
    // the 45-standard corpus and is emphatically NOT for the full one --
    // IS 15532:2004 is "Plastics Crates for Fruits and Vegetables", and the
    // engine is right to return it. The test was asserting a fact about one
    // corpus, not about the confidence gate.
    //
    // BIS publishes standards for products, materials and test methods, so
    // this names something no standards body would ever cover.
    await page.goto('/app/query');

    await page.fill('#spec', 'sonnet about the melancholy of retired racehorses');
    await page.click('button[type=submit]');

    await expect(page.locator('.notice-crit')).toBeVisible({ timeout: 120_000 });
    await expect(page.locator('h2', { hasText: 'Nearest text matches' })).toBeVisible();

    // The load-bearing assertion: nothing is presented as a recommendation.
    expect(await page.locator('article.rec').count()).toBe(0);
    // The phrase appears in both the banner and the reference-list heading;
    // both are correct, so assert presence rather than uniqueness.
    expect(await page.locator('text=not recommendations').count()).toBeGreaterThan(0);
  });

  test('the submit button is disabled until something is typed', async ({ page }) => {
    await page.goto('/app/query');
    await expect(page.locator('button[type=submit]')).toBeDisabled();
    await page.fill('#spec', 'cement');
    await expect(page.locator('button[type=submit]')).toBeEnabled();
  });
});

test.describe('Multilingual', () => {
  test('a Gujarati query is detected, translated and shown', async ({ page }) => {
    await page.goto('/app/query');
    await page.fill('#spec', 'ઘર માટે તાંબાનો વાયર');
    await page.click('button[type=submit]');
    await expect(page.locator('.notice', { hasText: 'Translated from Gujarati' })).toBeVisible({ timeout: 180_000 });
  });

  test('a language that is not supported says so', async ({ page }) => {
    await page.goto('/app/query');
    await page.fill('#spec', 'ගෙදර සඳහා වයර්');     // Sinhala
    await page.click('button[type=submit]');
    await expect(page.locator('text=/not supported yet/')).toBeVisible({ timeout: 120_000 });
  });

  test('a Hindi query is translated and shows what was searched', async ({ page }) => {
    await page.goto('/app/query');

    await expect(page.locator('#q-lang')).toBeVisible();
    await page.locator('.example-chip', { hasText: 'हिन्दी' }).click();

    await expect(page.locator('article.rec').first()).toBeVisible({ timeout: 180_000 });

    // The translation must be shown, not applied silently.
    const panel = page.locator('.notice', { hasText: 'Translated from Hindi' });
    await expect(panel).toBeVisible();
    await expect(panel).toContainText('You typed');
    await expect(panel).toContainText('Searched for');
  });
});

test.describe('Catalogue and detail', () => {
  test('the catalogue lists the corpus grouped by sector', async ({ page }) => {
    await page.goto('/app/catalogue');
    await expect(page.locator('.card-link').first()).toBeVisible({ timeout: 60_000 });
    expect(await page.locator('.card-link').count()).toBeGreaterThan(10);
  });

  test('searching the catalogue narrows it', async ({ page }) => {
    await page.goto('/app/catalogue');
    await expect(page.locator('.card-link').first()).toBeVisible({ timeout: 60_000 });

    const before = await page.locator('.card-link').count();
    await page.fill('#cat-search', 'cement');
    await page.waitForTimeout(500);
    const after = await page.locator('.card-link').count();

    // On a large corpus both counts hit the list's display cap, so "fewer
    // rows" stops being a meaningful signal. What must hold on any corpus is
    // that filtering does not widen the list and that the rows left actually
    // match -- which is the behaviour this test exists to protect.
    expect(after).toBeLessThanOrEqual(before);
    expect(after).toBeGreaterThan(0);

    // Not asserting the word appears in each row's visible text: the filter
    // also searches the scope clause and keywords, and a row can match on
    // text the card truncates. Asserting otherwise fails on rows the filter
    // was right to keep -- as it did on IS 10079, matched via "concrete" in
    // its scope.
    //
    // What is checkable here is that a nonsense term empties the list while
    // a real one does not, which is the filter actually doing something.
    await page.fill('#cat-search', 'qzxwvu-no-such-standard');
    await page.waitForTimeout(500);
    expect(await page.locator('.card-link').count()).toBe(0);
  });

  test('a standard detail page shows its allied cluster', async ({ page }) => {
    await page.goto(`/app/standard/${encodeURIComponent('IS 456:2000')}`);

    await expect(page.locator('h1.mono')).toContainText('IS 456:2000', { timeout: 60_000 });
    await expect(page.locator('text=Allied standards')).toBeVisible();
    await expect(page.locator('.ref-row').first()).toBeVisible({ timeout: 30_000 });
  });

  test('a standard detail page shows its real certification status', async ({ page }) => {
    // IS 694 is under the Electrical Wires, Cables ... (Quality Control) Order.
    await page.goto(`/app/standard/${encodeURIComponent('IS 694:2010')}`);
    const card = page.locator('[data-demo-target="detail-certification"]');
    await expect(card).toContainText('ISI mark required', { timeout: 60_000 });
    await expect(card).toContainText('Electrical Wires');
    await expect(card.locator('a[href*="bis.gov.in"]')).toBeVisible();
    await expect(page.locator('text=Not yet built')).toHaveCount(0);

    // Gold: compulsory hallmarking, with the order and where it applies.
    await page.goto(`/app/standard/${encodeURIComponent('IS 1417:2016')}`);
    await expect(card).toContainText('Hallmark required', { timeout: 60_000 });
    await expect(card).toContainText('392 districts');
  });

  test('a standard held on its number and title only says so', async ({ page }) => {
    // IS 2112:2025, silver hallmarking: in BIS's record, not in the archive.
    await page.goto(`/app/standard/${encodeURIComponent('IS 2112:2025')}`);
    await expect(page.locator('h1.mono')).toContainText('IS 2112:2025', { timeout: 60_000 });
    await expect(page.locator('text=/official title only/i')).toBeVisible();
  });

  test('a standard outside the corpus says so honestly', async ({ page }) => {
    await page.goto(`/app/standard/${encodeURIComponent('IS 9999:1900')}`);
    await expect(page.locator('text=Not in the current corpus')).toBeVisible({ timeout: 60_000 });
  });
});

test.describe('Tender builder', () => {
  test('typing a spec yields live recommendations and a clause', async ({ page }) => {
    await page.goto('/app/tender');

    // The demo must never imply a live GeM connection.
    await expect(page.locator('text=not connected to GeM')).toBeVisible();

    await page.fill(
      '#t-desc',
      'PVC insulated single core copper conductor cable 1.5 sq mm 1100 V for concealed conduit wiring',
    );

    await expect(page.locator('.rec-mini').first()).toBeVisible({ timeout: 120_000 });

    await page.fill('#t-qty', '500');
    await page.locator('.rec-mini button').first().click();

    const clause = page.locator('blockquote.clause');
    await expect(clause).toBeVisible();
    await expect(clause).toContainText('CONFORMANCE');
    await expect(clause).toContainText('500 metres');
  });
});

test.describe('Honesty guarantees', () => {
  test('no screen carries fixture data', async ({ page }) => {
    // Every screen is wired to the engine. Each was fixture data once (the
    // simulator and settings were the last) and must never regain the label.
    for (const route of [
      '/app', '/app/query', '/app/catalogue', '/app/tender',
      '/app/compliance', '/app/alerts', '/app/audit', '/app/boq',
      '/app/admin', '/app/projects', '/app/builder', '/app/map',
      '/app/certification', '/app/simulator', '/app/settings',
    ]) {
      await page.goto(route);
      expect(
        await page.locator('text=Illustrative screen').count(),
        `${route} is live and must not carry the fixture label`,
      ).toBe(0);
    }
  });

  test('the dashboard counts a search it just served', async ({ page }) => {
    // The dashboard's whole claim is that its figures are counted rather than
    // invented, so the test is the round trip: read the count, run a search,
    // read it again. A fixture screen cannot pass this.
    await page.goto('/app');

    const tile = page.locator('.card', { hasText: 'Searches served' });
    await expect(tile).toBeVisible({ timeout: 120_000 });

    const readCount = async () => {
      const text = await tile.locator('.tabular').innerText();
      return text.trim() === '–' ? 0 : Number(text.replace(/[^0-9]/g, ''));
    };
    const before = await readCount();

    await page.goto('/app/query');
    await page.fill('#spec', 'galvanised steel wire for fencing');
    await page.click('button[type=submit]');
    await expect(page.locator('h2').filter({ hasText: /Recommended standards|Nearest text matches/ }))
      .toBeVisible({ timeout: 120_000 });

    await page.goto('/app');
    await expect(tile).toBeVisible({ timeout: 120_000 });
    await expect.poll(readCount, { timeout: 30_000 }).toBeGreaterThan(before);
  });

  test('the dashboard never shows a figure it cannot compute', async ({ page }) => {
    // Rates that are not yet calculable render as an em dash. Showing 0%
    // instead would state something false: that decisions were recorded and
    // none were accepts.
    await page.goto('/app');
    await expect(page.locator('.card', { hasText: 'Searches served' })).toBeVisible({ timeout: 120_000 });

    // Scoped to the dashboard's own content: the shell's nav and the other
    // routes legitimately use some of these words, and matching those would
    // make this assert something it does not mean.
    const dashboard = page.locator('main .container.page');

    // The retired fixture figures must not come back under any state.
    for (const gone of ['Gaps identified', 'Outdated citations flagged', 'Orphan queries']) {
      expect(
        await dashboard.getByText(gone, { exact: false }).count(),
        `"${gone}" cannot be computed and must not be displayed`,
      ).toBe(0);
    }

    // The fixture dashboard's headline figure was a flat invented number.
    expect(
      await dashboard.getByText('1,248').count(),
      'the fixture query count must not survive anywhere on this screen',
    ).toBe(0);
  });

  test('every standards-hygiene finding names a real standard', async ({ page }) => {
    // The fixture screen invented notifications with relative times. Each row
    // must now be a fact about the corpus: a real IS number, and, where the
    // finding is critical, the replacement that resolves it.
    await page.goto('/app/alerts');

    const cards = page.locator('article.alert-card');
    await expect(cards.first()).toBeVisible({ timeout: 120_000 });

    const count = await cards.count();
    for (let i = 0; i < count; i += 1) {
      const heading = await cards.nth(i).locator('h2').innerText();
      expect(heading, 'every finding names an IS number').toMatch(/IS\s?\d+/);
    }

    // A critical ("Replaced") finding claims the replacement is known, so it
    // must name it. Matched on the badge, not its wording, which has changed.
    const critical = cards.filter({ has: page.locator('.badge-crit') });
    const criticalCount = await critical.count();
    for (let i = 0; i < criticalCount; i += 1) {
      await expect(
        critical.nth(i).locator('text=/Cite IS/'),
        'a critical finding must name the replacement edition',
      ).toBeVisible();
    }
  });

  test('the hygiene screen states what it did not check', async ({ page }) => {
    // No finding must not read as an all-clear: amendments come from each
    // standard's archived copy, and later ones would not be in it.
    await page.goto('/app/alerts');
    await expect(page.locator('article.alert-card').first()).toBeVisible({ timeout: 120_000 });

    await expect(page.locator('text=No text to read')).toBeVisible();
    await expect(page.locator('text=/not a statement that it has none/i')).toBeVisible();
  });

  test('BIS’s amendment count is shown with dates from the standard’s own copy', async ({ page }) => {
    // BIS lists 7 amendments to IS 1537:1976. Its archived copy carries slips
    // 1, 2, 4 and 5; 3 is known only from 4; 6 and 7 are known only from BIS.
    await page.goto(`/app/standard/${encodeURIComponent('IS 1537:1976')}`);
    await expect(page.locator('text=7 issued')).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('text=July 1977')).toBeVisible();
    await expect(page.locator('text=/Known from a later amendment/')).toBeVisible();
    await expect(page.locator('text=/Listed by BIS; date not in the sources read/').first()).toBeVisible();
    await expect(page.locator('blockquote.clause', { hasText: 'incorporating all 7 amendments' })).toBeVisible();
    // The record card agrees with the amendments card.
    await expect(page.locator('text=/latest dated: No. 5, May 1994/')).toBeVisible();
  });

  test('corpus health shows counts against their totals', async ({ page }) => {
    // The ratio is the honest unit: a researched count alone says nothing.
    await page.goto('/app/compliance');
    await expect(page.locator('text=Metadata coverage')).toBeVisible({ timeout: 120_000 });

    const page_ = page.locator('main .container.page');
    // The value and its total are separate spans, so assert on the combined
    // text of the row rather than on a single text node.
    const ratioRow = page_.locator('.stack', { hasText: 'Under compulsory certification' }).first();
    await expect(ratioRow).toContainText(/\d+\s*\/\s*\d+/);

    // Deferred and related listings need a look before issuing, so they are shown.
    await expect(page.locator('text=Deferred or related listing')).toBeVisible();

    // The retired invented figures must not come back.
    //
    // Named departments and their rates, not the words "compliance rate":
    // the footer legitimately says tender compliance rates are NOT shown, and
    // an absence assertion that trips over the page explaining the absence is
    // testing the wrong thing.
    for (const gone of ['Electrical Wing', 'Civil Works', 'IT Procurement', '95.8']) {
      expect(
        await page_.getByText(gone, { exact: false }).count(),
        `"${gone}" was invented and must not be displayed`,
      ).toBe(0);
    }
  });

  test('the audit screen refuses to call an uncited document clean', async ({ page }) => {
    // The load-bearing case: a tender citing no standards produces no
    // findings, and that is the worst case rather than a pass.
    await page.goto('/app/audit');

    await page.setInputFiles(
      'input[type=file]',
      {
        name: 'no-citations.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('A tender describing goods but naming no standards at all.'),
      },
    );

    await expect(page.locator('text=/not a pass/i')).toBeVisible({ timeout: 120_000 });
  });

  test('the audit screen names the replacement for a superseded citation', async ({ page }) => {
    await page.goto('/app/audit');

    await page.setInputFiles(
      'input[type=file]',
      {
        name: 'tender.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from(
          'Clause 4.3: Cement shall conform to IS 269:1989, 33 grade, for all civil works.',
        ),
      },
    );

    const finding = page.locator('article.card', { hasText: 'IS 269:1989' });
    await expect(finding).toBeVisible({ timeout: 120_000 });
    await expect(finding.locator('text=/Replace the citation with IS/')).toBeVisible();
  });

  test('the audit names what a cited standard depends on but the tender leaves out', async ({ page }) => {
    // IS 694 specifies its conductor by IS 8130; a tender citing only IS 694
    // leaves the conductor undefined.
    await page.goto('/app/audit');
    await page.setInputFiles('input[type=file]', {
      name: 'cables.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Clause 5: PVC insulated cables shall conform to IS 694:2010.'),
    });
    const section = page.locator('[data-demo-target="audit-dependencies"]');
    await expect(section).toBeVisible({ timeout: 120_000 });
    await expect(section).toContainText('IS 694:2010');
    await expect(section).toContainText('IS 8130');
    await expect(section).toContainText('IS 10810');
  });

  test('an Excel BOQ, as CPPP publishes them, is read line by line', async ({ page }) => {
    await page.goto('/app/boq');
    // Relative to the directory Playwright runs from (frontend/).
    await page.setInputFiles('input[type=file]', 'e2e/fixtures/sample-boq.xlsx');
    await expect(page.locator('text=/8 line items/')).toBeVisible({ timeout: 240_000 });
    const body = await page.locator('main').innerText();
    expect(body).toContain('820 Bags');
    expect(body).not.toContain('Name of Work');                   // tender details are not items
  });

  test('a BOQ matches each line item on its own terms', async ({ page }) => {
    // Flattening a BOQ into one query lets the first item's vocabulary
    // dominate. Item 2 must come back with cement, not more cable.
    await page.goto('/app/boq');

    await page.setInputFiles(
      'input[type=file]',
      {
        name: 'boq.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from(
          ['SPECIFICATION',
           'Item 1: PVC insulated copper cable, single core, 1100 V. Quantity 4500 m.',
           'Item 2: Ordinary Portland Cement, 43 grade, in bags. Quantity 820 bags.',
          ].join(String.fromCharCode(10)),
        ),
      },
    );

    await expect(page.locator('text=/2 line items/')).toBeVisible({ timeout: 180_000 });

    // Open item 2 and check it matched cement rather than cable.
    await page.locator('text=Ordinary Portland Cement').first().click();
    const body = await page.locator('main').innerText();
    expect(body).toMatch(/IS\s?(269|8112|12269|1489)/);
  });

  test('a document with no line items is not rendered as an empty BOQ', async ({ page }) => {
    await page.goto('/app/boq');

    await page.setInputFiles(
      'input[type=file]',
      {
        name: 'prose.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('A tender describing one product in continuous prose with no numbering.'),
      },
    );

    await expect(page.locator('text=/No line items found/')).toBeVisible({ timeout: 120_000 });
  });

  test('every mandatory certification claim cites its statutory order', async ({ page }) => {
    // The asymmetry that makes this screen the highest-stakes one: asserting
    // a legal obligation with nothing to trace it to is unusable in a tender
    // and indefensible in a dispute.
    await page.goto('/app/certification');
    await expect(page.locator('text=On BIS’s lists')).toBeVisible({ timeout: 120_000 });

    // Read from BIS's own lists: hundreds of products, not a handful.
    await expect(page.locator('text=/standards under compulsory certification/')).toBeVisible();

    // The default selection is an obligation in force, so the panel names the
    // order (linked) and the clause cites it.
    await expect(page.getByText('Statutory order', { exact: true })).toBeVisible();
    await expect(page.locator('.card a[href*="bis.gov.in"]').first()).toBeVisible();
    await expect(page.locator('blockquote.clause')).toContainText('as required by');
  });

  test('a deferred order is not shown as mandatory', async ({ page }) => {
    // S.O. 5038(E): the Electrical Equipment QCO is deferred except Sr. 1.1(a).
    await page.goto('/app/certification');
    await expect(page.locator('text=On BIS’s lists')).toBeVisible({ timeout: 120_000 });
    await page.click('.seg button:has-text("Deferred")');
    await page.locator('.alert-mini').first().click();
    await expect(page.locator('text=Deferred, not yet mandatory')).toBeVisible();
    await expect(page.locator('blockquote.clause')).toHaveCount(0);
  });

  test('hallmarking is compulsory for gold and voluntary for silver', async ({ page }) => {
    await page.goto('/app/certification');
    await expect(page.locator('text=On BIS’s lists')).toBeVisible({ timeout: 120_000 });
    await page.click('.seg button:has-text("Hallmarking")');

    await page.locator('.alert-mini', { hasText: 'IS 1417' }).click();
    await expect(page.locator('text=Hallmark mandatory')).toBeVisible();
    await expect(page.locator('text=/392 districts/')).toBeVisible();
    await expect(page.locator('blockquote.clause')).toContainText('HUID');

    // Silver: a scheme exists, no order makes it compulsory, so the clause is optional.
    await page.locator('.alert-mini', { hasText: 'IS 2112' }).click();
    await expect(page.locator('text=Hallmarking voluntary')).toBeVisible();
    await expect(page.locator('text=Optional tender clause')).toBeVisible();
  });

  test('any standard can be checked, including one not on the lists', async ({ page }) => {
    await page.goto('/app/certification');
    await expect(page.locator('text=On BIS’s lists')).toBeVisible({ timeout: 120_000 });
    // Coarse aggregates: in the catalogue, not under any certification order.
    await page.fill('#cert-search', 'IS 383:2016');
    await page.click('button:has-text("Check IS 383:2016")');
    await expect(page.locator('text=No compulsory certification')).toBeVisible();
    await expect(page.locator('text=/Not on BIS.s lists/')).toBeVisible();
  });

  test('no route renders a console error or overflows horizontally', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

    const routes = [
      '/', '/app', '/app/query', '/app/catalogue', '/app/tender',
      '/app/builder', '/app/audit', '/app/settings',
      '/app/compliance', '/app/alerts', '/app/boq', '/app/admin',
      '/app/projects', '/app/map', '/app/certification', '/app/simulator',
    ];

    for (const route of routes) {
      await page.goto(route, { waitUntil: 'networkidle' });
      const [scrollWidth, clientWidth] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scrollWidth, `${route} scrolls horizontally`).toBeLessThanOrEqual(clientWidth + 1);
    }

    expect(errors).toEqual([]);
  });
});
