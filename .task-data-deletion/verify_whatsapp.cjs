(async () => {
  const frontend = 'https://crd-f.onrender.com';
  const html = await (await fetch(frontend + '/whatsapp')).text();
  const script = html.match(/<script[^>]*src="([^"]+)"/);
  const js = await (await fetch(new URL(script[1], frontend))).text();
  const config = js.match(/apiConfig-[A-Za-z0-9_-]+\.js/);
  const configJs = config ? await (await fetch(frontend + '/assets/' + config[0])).text() : js;
  const urls = [...new Set(configJs.match(/https:\/\/[A-Za-z0-9.-]+\.onrender\.com/g) || [])].filter(u => u !== frontend);
  console.log('Backend URLs:', urls);
  const whatsapp = js.match(/WhatsApp-[A-Za-z0-9_-]+\.js/);
  if (whatsapp) {
    const code = await (await fetch(frontend + '/assets/' + whatsapp[0])).text();
    console.log('New approved-template composer live:', code.includes('Approved Meta template name'));
  }
  for (const base of urls) {
    const r = await fetch(base + '/openapi.json', {signal: AbortSignal.timeout(55000)});
    const schema = await r.json();
    console.log(base, 'Webhook methods:', Object.keys(schema.paths?.['/api/webhooks/whatsapp'] || {}));
  }
})().catch(e => {console.error(e.message);process.exit(1)});
