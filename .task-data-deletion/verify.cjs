(async () => {
  const base = 'https://crd-f.onrender.com';
  const response = await fetch(base + '/data-deletion');
  const html = await response.text();
  const script = html.match(/<script[^>]*src="([^"]+)"/);
  console.log('Public route HTTP:', response.status);
  if (!script) throw Error('Application script missing');
  const js = await (await fetch(new URL(script[1], base))).text();
  if (!js.includes('/data-deletion')) throw Error('Deletion route missing from live application');
  const component = js.match(/DataDeletion-[A-Za-z0-9_-]+\.js/);
  if (!component) throw Error('Deletion component missing');
  const code = await (await fetch(base + '/assets/' + component[0])).text();
  if (!code.includes('/data-deletion/index.html')) throw Error('Public document reference missing');
  const document = await fetch(base + '/data-deletion/index.html');
  const text = await document.text();
  if (document.status !== 200 || !text.includes('Data Deletion Instructions') || !text.includes('hanuramtech@gmail.com')) throw Error('Public deletion content missing');
  console.log('Verified live public route, component, deletion instructions and contact email without authentication.');
})().catch(error => { console.error(error.message); process.exit(1); });
