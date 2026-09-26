import { test, expect } from '@playwright/test';

/**
 * The full user journey, against a live backend.
 *
 * These cover what unit tests cannot: that the frontend and backend agree on
 * the response shape, that CORS permits the call at all, and that the honesty
 * guarantees survive the round trip — an out-of-scope query must not produce a
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
  test('fixture screens are labelled, live screens are not', async ({ page }) => {
    // What genuinely still has no backing data source.
    for (const route of ['/app/simulator', '/app/settings']) {
      await page.goto(route);
      await expect(
        page.locator('text=Illustrative screen'),
        `${route} must be labelled as fixture data`,
      ).toBeVisible();
    }

    // Every screen since wired to the engine. Each was fixture data once and
    // must never regain the label.
    for (const route of [
      '/app', '/app/query', '/app/catalogue', '/app/tender',
      '/app/compliance', '/app/alerts', '/app/audit', '/app/boq',
      '/app/admin', '/app/projects', '/app/builder', '/app/map',
      '/app/certification',
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
      return text.trim() === '—' ? 0 : Number(text.replace(/[^0-9]/g, ''));
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
    // must now be a fact about the corpus: a real IS number, and — where the
    // finding is critical — the replacement that resolves it.
    await page.goto('/app/alerts');

    const cards = page.locator('article.alert-card');
    await expect(cards.first()).toBeVisible({ timeout: 120_000 });

    const count = await cards.count();
    for (let i = 0; i < count; i += 1) {
      const heading = await cards.nth(i).locator('h2').innerText();
      expect(heading, 'every finding names an IS number').toMatch(/IS\s?\d+/);
    }

    // A critical finding claims the fix is known, so it must name it.
    const critical = cards.filter({ hasText: 'Fix before issue' });
    const criticalCount = await critical.count();
    for (let i = 0; i < criticalCount; i += 1) {
      await expect(
        critical.nth(i).locator('text=/Cite IS/'),
        'a critical finding must name the replacement edition',
      ).toBeVisible();
    }
  });

  test('the hygiene screen states what it did not check', async ({ page }) => {
    // A short list must not read as an all-clear: most standards have never
    // been checked for amendments, and the screen has to say so.
    await page.goto('/app/alerts');
    await expect(page.locator('article.alert-card').first()).toBeVisible({ timeout: 120_000 });

    await expect(page.locator('text=Never checked for amendments')).toBeVisible();
    await expect(page.locator('text=/not a statement that it has none/i')).toBeVisible();
  });

  test('corpus health shows counts against their totals', async ({ page }) => {
    // The ratio is the honest unit: a researched count alone says nothing.
    await page.goto('/app/compliance');
    await expect(page.locator('text=Metadata coverage')).toBeVisible({ timeout: 120_000 });

    const page_ = page.locator('main .container.page');
    // The value and its total are separate spans, so assert on the combined
    // text of the row rather than on a single text node.
    const ratioRow = page_.locator('.stack', { hasText: 'Certification confirmed' }).first();
    await expect(ratioRow).toContainText(/\d+\s*\/\s*\d+/);

    // An unverified certification status is not a pass and must be shown.
    await expect(page.locator('text=Certification not verified')).toBeVisible();

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
    await expect(page.locator('text=Researched standards')).toBeVisible({ timeout: 120_000 });

    // The default selection is a mandatory rule, so the detail panel must
    // name both the order and the gazette notification.
    // Exact: the phrase also appears in the clause caption below, and both
    // are correct, so a loose match is a strict-mode violation rather than a
    // real failure.
    await expect(page.getByText('Statutory order', { exact: true })).toBeVisible();
    await expect(page.getByText('Quality Control', { exact: false }).first()).toBeVisible();

    // And the generated clause must carry it too, not just the panel.
    await expect(page.locator('blockquote.clause')).toContainText('BIS licence number');
  });

  test('certification states what it did not research', async ({ page }) => {
    // Absence of a rule is absence of research, never a clearance.
    await page.goto('/app/certification');
    await expect(page.locator('text=Researched standards')).toBeVisible({ timeout: 120_000 });

    await expect(page.locator('text=/standards researched/')).toBeVisible();
    await expect(page.locator("text=/not a statement that no certification is required/i"))
      .toBeVisible();
  });

  test('no route renders a console error or overflows horizontally', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

    const routes = [
      '/', '/app', '/app/query', '/app/catalogue', '/app/tender',
      '/app/builder', '/app/audit', '/app/settings',
      '/app/compliance', '/app/alerts', '/app/boq', '/app/admin',
      '/app/projects', '/app/map', '/app/certification',
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
