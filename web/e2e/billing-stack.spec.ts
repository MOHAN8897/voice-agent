import { expect, test } from "@playwright/test";

async function fixture(page: import('@playwright/test').Page) {
  const evidence = Object.fromEntries(['sarvamModelAccess','sttVerified','ttsCatalogVerified','toolsVerified','capacityVerified','mediaFormatsVerified','credentialRefConfigured'].map(key => [key,true]));
  const makeProfile = (tier: string, webRate: number) => ({ tier, label: tier === 'low' ? 'Economical' : 'Standard', profileRevision: 1,
    readiness: { ready: true, enabled: true, blockers: [] }, retailRate: { complete: true, inrPaisePerMin: 1000, usdMicrosPerMin: 100000, fxRateInr: 100, version: 1 },
    webRetailRate: { complete: true, inrPaisePerMin: webRate * 100, usdMicrosPerMin: webRate * 10000, fxRateInr: 100, version: 1 },
    composedProfile: { schemaVersion: 1, enabled: true, label: tier === 'low' ? 'Economical' : 'Standard', retailRateInr: 10, webRetailRateInr: webRate, supportedLanguages: ['te-IN'],
      stt: { provider: 'sarvam', model: 'saaras:v3-realtime' }, llm: { provider: 'sarvam', modelId: 'sarvam-105b-conversations', apiMode: 'chat_completions_v1' }, evidence,
      engines: [{ id: 'speech', label: 'Speech', models: [{ id: 'model', label: 'Model', provider: 'gnani', model: 'timbre-v3.0', apiMode: 'websocket',
        voices: [{ id: 'voice', label: 'Voice', providerVoiceId: 'Shivani', languages: ['te-IN'] }] }] }] } });
  const profiles = [makeProfile('low',3),makeProfile('medium',6)];
  const writes: {tier: string; body: Record<string,unknown>}[] = [];
  const taxWrites: unknown[] = [];
  const tax = { enabled: true, configured: true, legalName: 'Fixture Business', gstin: '36AABCU9603R1ZO', addressLine1: 'Fixture address', city: 'Hyderabad', stateCode: '36',
    stateOptions: [{code:'36',name:'Telangana'},{code:'27',name:'Maharashtra'}], defaultRateBps: 1800, ratePercent: 18, priceIncludesTax: false, exportZeroRated: true,
    invoicePrefix: 'INV', creditNotePrefix: 'CN', invoiceTerms: 'Configured checkout tax terms.', currentFy: '2026-27', updatedAt: '2026-10-27T10:00:00Z', webhookConfigured: true, pdfAvailable: true };
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path === '/api/auth/dev-me') return route.fulfill({json:{authenticated:true,role:'developer',kind:'dev',csrf_token:'fixture-csrf'}});
    if (path.endsWith('/tax-settings')) {
      if (request.method()==='PUT') { taxWrites.push(request.postDataJSON()); Object.assign(tax,request.postDataJSON()); }
      return route.fulfill({json:tax});
    }
    if (path.endsWith('/tax-preview')) {
      const body=request.postDataJSON(), amount=body.amount;
      const rate = body.settings.enabled && !(body.buyerCountry!=='IN' && body.settings.exportZeroRated) ? body.settings.defaultRateBps/10000 : 0;
      const subtotal = body.settings.priceIncludesTax ? amount/(1+rate) : amount;
      return route.fulfill({json:{currency:body.currency,subtotal,tax:subtotal*rate,total:subtotal*(1+rate),creditInr:subtotal*(body.currency==='USD'?100:1),taxKind:body.buyerCountry!=='IN'?'export':'cgst_sgst'}});
    }
    if (path.endsWith('/voice-profiles')) return route.fulfill({json:{environment:'test',profiles}});
    if (/\/voice-profiles\/(low|medium)$/.test(path) && request.method()==='PUT') {
      const tier=path.split('/').at(-1)!, row=profiles.find(item=>item.tier===tier)!;
      const body=request.postDataJSON(); writes.push({tier,body});
      row.composedProfile=body.composedProfile; row.profileRevision+=1;
      return route.fulfill({json:row});
    }
    if (path.endsWith('/catalog')) return route.fulfill({json:{providers:[
      {id:'sarvam',enabled:true,configured:true,models:{stt:[{id:'saaras:v3-realtime'}],llm:[{id:'sarvam-105b-conversations'}]}},
      {id:'gnani',enabled:true,configured:true,models:{tts:[{id:'timbre-v3.0',api_mode:'websocket',voices:profiles[0].composedProfile.engines[0].models[0].voices}]}},
    ]}});
    if (path.endsWith('/billing-rates')) return route.fulfill({json:{rates:{webInrPerMin:5,numberMonthlyInr:300,fxRateInr:100}}});
    return route.fulfill({json:{ok:true,items:[]}});
  });
  await page.goto('/dev/stack');
  return { profiles,writes,taxWrites };
}

test('admin web prices stay separate for each selected stack', async ({page}) => {
  const state=await fixture(page);
  const input=page.getByLabel('Web agent price (₹/min)',{exact:true});
  await expect(input).toHaveValue('3');
  await input.fill('4');
  await expect.poll(()=>state.writes.length).toBe(1);
  expect(state.writes[0].tier).toBe('low');
  expect((state.writes[0].body.composedProfile as {webRetailRateInr:number}).webRetailRateInr).toBe(4);
  await page.getByRole('group',{name:'Select voice stack tier'}).getByRole('button').filter({hasText:'Standard'}).click();
  await expect(input).toHaveValue('6');
  expect(state.profiles[1].composedProfile.webRetailRateInr).toBe(6);
});

test('GST draft preview uses edited rules and saving carries concurrency and checkout terms', async ({page}) => {
  const state=await fixture(page);
  const gst=page.locator('#gst-billing');
  await gst.getByLabel('GST rate (%)',{exact:true}).fill('20');
  await expect(gst.getByLabel('GST rate (%)',{exact:true})).toHaveValue('20');
  await gst.getByRole('button',{name:'Preview checkout',exact:true}).click();
  await expect(gst.getByTestId('admin-gst-preview')).toContainText('INR 1200.00');
  expect(state.taxWrites).toHaveLength(0);
  await gst.getByLabel('Invoice and checkout terms',{exact:true}).fill('Updated GST terms for checkout and invoice.');
  await gst.getByRole('button',{name:'Save GST settings',exact:true}).click();
  await expect.poll(()=>state.taxWrites.length).toBe(1);
  expect(state.taxWrites[0]).toMatchObject({defaultRateBps:2000,expectedUpdatedAt:'2026-10-27T10:00:00Z',invoiceTerms:'Updated GST terms for checkout and invoice.'});
});
