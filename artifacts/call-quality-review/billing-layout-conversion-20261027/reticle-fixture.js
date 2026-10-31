
            const user = {id:'layout-fixture', userId:'layout-fixture', fullName:'Layout Tester',
              email:'layout@example.invalid', tenantId:'layout-tenant', hasCompletedOnboarding:true};
            const encode = value => btoa(JSON.stringify(value)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
            sessionStorage.setItem('voxly_auth_token', `${encode({alg:'none'})}.${encode({sub:user.id,exp:Math.floor(Date.now()/1000)+3600})}.synthetic`);
            localStorage.setItem('voxly_auth_session', JSON.stringify(user));
            localStorage.setItem('voxly_tour_completed_layout@example.invalid','true');
            const agent = {id:'layout-agent', agent_id:'layout-agent', name:'Layout Agent', status:'active',
              languages:['te-IN'], defaultTier:'low', voiceRevision:1, active_compiled_brain_version:'published',
              voiceSettings:{stackSelectionVersion:1,profileRevision:1,engineId:'eng-fixture',modelId:'mod-fixture',voiceId:'voc-fixture'}};
            const profiles = [{tier:'low', label:'Economical', ready:true, enabled:true, profileRevision:1,
              retailRate:{complete:true,usdMicrosPerMin:10000,inrPaisePerMin:100,fxRateInr:100,version:1},
              webRetailRate:{complete:true,usdMicrosPerMin:30000,inrPaisePerMin:300,fxRateInr:100,version:1},
              engines:[{id:'eng-fixture',label:'Voice engine',models:[{id:'mod-fixture',label:'Speech model',
                voices:[{id:'voc-fixture',label:'Voice one',languages:['te-IN'],gender:'female',category:'Conversational'}, {id:'voc-second',label:'Voice two',languages:['te-IN'],gender:'male',category:'Normal'}]}]}]}];
            const leads = [{leadId:'fixture-lead',agentId:agent.id,name:'Example Enquiry',phone:'+12025550101',email:'lead@example.invalid',stage:'qualified',notes:'Please arrange a demo',createdAt:'2026-10-20T10:00:00Z',updatedAt:'2026-10-27T10:00:00Z'}];
            const realFetch = window.fetch.bind(window);
            window.fetch = async (input, init) => {
              const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
              if (!path.startsWith('/api/')) return realFetch(input,init);
              let body = {ok:true,items:[]};
              if(path==='/api/billing/razorpay/config') body={enabled:true,keyId:'fixture',currency:'INR'};
              else if(path==='/api/billing/catalog') body={topupMinInr:100,topupMaxInr:10000,rates:{fxRateInr:100}};
              else if(path==='/api/billing/quote') {const v=JSON.parse(init.body).amount;body={amount:v,currency:'INR',subtotal:v,total:v*1.18,totalMinor:Math.round(v*118),tax:v*.18,creditInr:v,ratePercent:18,taxKind:'cgst_sgst',cgst:v*.09,sgst:v*.09,checkoutTerms:'Configured GST checkout terms.'};}
              else if(path==='/api/billing/razorpay/create-order') body={orderId:'order-fixture',keyId:'fixture',amountMinor:59000,currency:'INR',creditedInr:500};
              else if(path==='/api/billing/razorpay/verify') body={ok:true,creditedInr:500,invoiceNumber:'INV-FIXTURE'};
              else if(path.startsWith('/api/leads/')) {Object.assign(leads[0],JSON.parse(init.body));body={lead:leads[0]};}
              else 
              if (path === '/api/auth/me') body={user,tenant:{tenantId:user.tenantId},role:'owner'};
              else if (path === '/api/auth/session') body={authenticated:true,saas_auth_enabled:true};
              else if (path === '/api/agents') body={agents:[agent]};
              else if (path === '/api/agents/layout-agent') body={agent};
              else if (path === '/api/leads') {
                const url = new URL(typeof input === 'string' ? input : input.url,location.href);
                const matches = !url.searchParams.get('search') || url.searchParams.get('search').toLowerCase().includes('example');
                body={leads:matches?leads:[],total:matches?1:0,stageCounts:matches?{[leads[0].stage]:1}:{}};
              }
              else if (path === '/api/voice-stacks/catalog') body={profiles};
              else if (path.includes('/voice-options')) body={voices:[],languages:[{code:'te-IN',label:'Telugu'}]};
              else if (path.endsWith('/billing/wallet')) body={balanceUsd:100};
              else if (path.endsWith('/business-brain')) body={draft:{revision:'fixture',sections:[{section_id:'script',type:'facts',title:'Calling script',raw_text:'Hello, how can I help?',enabled:true,order:20}]},published:{version_id:'published'}};
              else if (path.endsWith('/telephony-profile')) body={profile:{}};
              return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
            };
            
document.addEventListener('DOMContentLoaded', () => { const s=document.createElement('style'); s.textContent='[data-reticle-overlay]{display:none!important}'; document.head.append(s); });

window.Razorpay=class {constructor(options){this.options=options;this.handlers={};} on(name,handler){this.handlers[name]=handler;} open(){this.options.handler({razorpay_order_id:'order-fixture',razorpay_payment_id:'payment-fixture',razorpay_signature:'fixture-signature-only'});}};
