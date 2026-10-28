// Browser-only fixture: every API request is intercepted before any financial write.
const evidence = Object.fromEntries(['sarvamModelAccess','sttVerified','ttsCatalogVerified','toolsVerified','capacityVerified','mediaFormatsVerified','credentialRefConfigured'].map(key => [key,true]));
const profiles = ['low','medium'].map((tier,index) => ({tier,label:index?'Standard':'Economical',profileRevision:1,
  readiness:{ready:true,enabled:true,blockers:[]},
  retailRate:{complete:true,inrPaisePerMin:1000,usdMicrosPerMin:100000,fxRateInr:100,version:1},
  webRetailRate:{complete:true,inrPaisePerMin:index?600:300,usdMicrosPerMin:index?60000:30000,fxRateInr:100,version:1},
  composedProfile:{schemaVersion:1,enabled:true,label:index?'Standard':'Economical',retailRateInr:10,webRetailRateInr:index?6:3,supportedLanguages:['te-IN'],evidence,
    stt:{provider:'sarvam',model:'saaras:v3-realtime'},llm:{provider:'sarvam',modelId:'sarvam-105b-conversations',apiMode:'chat_completions_v1'},
    engines:[{id:'speech',label:'Speech',models:[{id:'model',label:'Model',provider:'gnani',model:'timbre-v3.0',apiMode:'websocket',voices:[{id:'voice',label:'Voice',providerVoiceId:'Shivani',languages:['te-IN']}]}]}]}}));
const tax = {enabled:true,configured:true,legalName:'Fixture Business',gstin:'36AABCU9603R1ZO',addressLine1:'Fixture address',city:'Hyderabad',stateCode:'36',
  stateOptions:[{code:'36',name:'Telangana'},{code:'27',name:'Maharashtra'}],defaultRateBps:1800,ratePercent:18,priceIncludesTax:false,exportZeroRated:true,
  invoicePrefix:'INV',creditNotePrefix:'CN',invoiceTerms:'Configured checkout tax terms.',currentFy:'2026-27',updatedAt:'2026-10-27T10:00:00Z',webhookConfigured:true,pdfAvailable:true};
const realFetch=window.fetch.bind(window);
window.fetch=async (input,init) => {
  const request=input instanceof Request?input:null;
  const path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
  if (!path.startsWith('/api/')) return realFetch(input,init);
  const method=init?.method||request?.method||'GET';
  const raw=init?.body||(request?await request.clone().text():'');
  const data=raw?JSON.parse(raw):{};
  let body={ok:true,items:[]};
  if(path==='/api/auth/dev-me') body={authenticated:true,role:'developer',kind:'dev',csrf_token:'fixture-csrf'};
  else if(path.endsWith('/voice-profiles')) body={environment:'test',profiles};
  else if(/\/voice-profiles\/(low|medium)$/.test(path)&&method==='PUT') {
    const row=profiles.find(item=>item.tier===path.split('/').at(-1)); row.composedProfile=data.composedProfile; row.profileRevision+=1; body=row;
  } else if(path.endsWith('/catalog')) body={providers:[
    {id:'sarvam',enabled:true,configured:true,models:{stt:[{id:'saaras:v3-realtime'}],llm:[{id:'sarvam-105b-conversations'}]}},
    {id:'gnani',enabled:true,configured:true,models:{tts:[{id:'timbre-v3.0',api_mode:'websocket',voices:profiles[0].composedProfile.engines[0].models[0].voices}]}}]};
  else if(path.endsWith('/billing-rates')) body={rates:{webInrPerMin:5,numberMonthlyInr:300,fxRateInr:100}};
  else if(path.endsWith('/tax-settings')) {if(method==='PUT') Object.assign(tax,data); body=tax;}
  else if(path.endsWith('/tax-preview')) {
    const rate=data.settings.enabled&&!(data.buyerCountry!=='IN'&&data.settings.exportZeroRated)?data.settings.defaultRateBps/10000:0;
    const subtotal=data.settings.priceIncludesTax?data.amount/(1+rate):data.amount;
    body={currency:data.currency,subtotal,tax:subtotal*rate,total:subtotal*(1+rate),creditInr:subtotal*(data.currency==='USD'?100:1),taxKind:'cgst_sgst'};
  }
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
};
