$ErrorActionPreference = 'Stop'
$frontend = 'D:\web apps\React\CBD project'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$page = @'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Request deletion of HanuRam Tech account, customer, personal and stored WhatsApp-related data.">
  <title>Data Deletion | HanuRam Tech</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; color: #1e293b; background: #f8fafc; }
    body { margin: 0; line-height: 1.75; }
    header, main, footer { max-width: 800px; margin: auto; padding: 24px; }
    header { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px; border-bottom: 1px solid #e2e8f0; }
    main { padding-top: 48px; padding-bottom: 48px; }
    h1 { font-size: clamp(2rem, 6vw, 3rem); line-height: 1.2; margin: 0 0 12px; color: #0f172a; }
    h2 { font-size: 1.25rem; line-height: 1.4; margin-top: 32px; color: #0f172a; }
    a { color: #075985; text-underline-offset: 3px; overflow-wrap: anywhere; }
    a:focus-visible { outline: 3px solid #0284c7; outline-offset: 4px; }
    .date, footer { color: #475569; font-size: .9rem; }
    .contact { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 24px; margin: 28px 0; }
    footer { border-top: 1px solid #e2e8f0; }
  </style>
</head>
<body>
  <header><strong>HanuRam Tech</strong><a href="/privacy-policy">Privacy Policy</a></header>
  <main>
    <h1>Data Deletion Instructions</h1>
    <p class="date">Last updated: 6 October 2026</p>
    <p>You can request deletion of your account information, customer information, WhatsApp-related data stored by our application, and other personal data held by HanuRam Tech. You do not need to sign in to read these instructions or email a request.</p>
    <section class="contact" aria-labelledby="request">
      <h2 id="request">Submit a deletion request</h2>
      <p>Email <a href="mailto:hanuramtech@gmail.com?subject=Data%20deletion%20request">hanuramtech@gmail.com</a> with the subject <strong>Data deletion request</strong>.</p>
      <p>Please include:</p>
      <ul>
        <li>Your name and the email address associated with your account or customer record.</li>
        <li>Your phone or WhatsApp number, including country code, if the request concerns WhatsApp or phone-based records.</li>
        <li>The name of the business or organization you interacted with or whose CRM account holds your information.</li>
        <li>What you want deleted: your account, customer records, stored WhatsApp communications, or all personal data relating to you.</li>
      </ul>
      <p>Send your request from the associated email address where possible. Do not send passwords, access tokens, payment details, or unnecessary identity documents.</p>
    </section>
    <h2>Information covered</h2>
    <p>Requests may cover account profile and contact information; customer records, preferences, tags and sales information; and WhatsApp phone numbers, stored message content or attachments, campaign history, and delivery or read metadata held by this application, where those features are used.</p>
    <h2>How we handle your request</h2>
    <ol>
      <li>We review your request and locate the relevant account, customer records, or communications.</li>
      <li>We may ask for limited verification to confirm that you are entitled to request deletion and prevent unauthorized changes.</li>
      <li>If a business controls the records, we coordinate with that business. You may also contact it directly using the contact details it provided.</li>
      <li>We delete or anonymize the relevant data where appropriate and confirm completion by email, or explain any information we must retain.</li>
    </ol>
    <p>Our target is to acknowledge requests within approximately 7 days and complete them within approximately 30 days after receiving sufficient information and verification. These are estimates; complex requests or coordination with a business may take longer. We will explain any delay and provide an updated estimate.</p>
    <h2>Retention and limits</h2>
    <p>Some information may need to be retained for applicable legal obligations, security, fraud prevention, or disputes. We will explain any applicable exception. Residual copies in backups may remain until their normal retention cycle expires.</p>
    <p>This request covers data stored by HanuRam Tech and its application. It does not delete your WhatsApp account or automatically remove copies independently held by Meta/WhatsApp, other businesses, or message recipients. Those services or organizations must be contacted separately for their copies.</p>
    <p>For more information about how data is handled, see our <a href="/privacy-policy">Privacy Policy</a>.</p>
  </main>
  <footer>HanuRam Tech &middot; <a href="mailto:hanuramtech@gmail.com">hanuramtech@gmail.com</a></footer>
</body>
</html>
'@
$directory = Join-Path $frontend 'public/data-deletion'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
[IO.File]::WriteAllText((Join-Path $directory 'index.html'), $page, $utf8)
$component = @'
import { useEffect } from 'react';

export default function DataDeletion() {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = 'Data Deletion | HanuRam Tech';
    return () => { document.title = previousTitle; };
  }, []);

  return (
    <iframe
      title="HanuRam Tech Data Deletion Instructions"
      src="/data-deletion/index.html"
      className="fixed inset-0 h-full w-full border-0 bg-slate-50"
    />
  );
}
'@
[IO.File]::WriteAllText((Join-Path $frontend 'src/Pages/DataDeletion.jsx'), $component, $utf8)
$path = Join-Path $frontend 'src/routes/AppRoutes.jsx'
$content = [IO.File]::ReadAllText($path)
$content = $content.Replace("const PrivacyPolicy = lazy(() => import('../Pages/PrivacyPolicy'));", "const PrivacyPolicy = lazy(() => import('../Pages/PrivacyPolicy'));`r`nconst DataDeletion = lazy(() => import('../Pages/DataDeletion'));")
$content = $content.Replace('      <Route path="/privacy-policy"', '      <Route path="/data-deletion" element={<PageLoader><DataDeletion /></PageLoader>} />' + "`r`n" + '      <Route path="/privacy-policy"')
[IO.File]::WriteAllText($path, $content, $utf8)
$path = Join-Path $frontend 'render.yaml'
$content = [IO.File]::ReadAllText($path)
$content = $content.Replace('    routes:', "    routes:`r`n      - type: rewrite`r`n        source: /data-deletion`r`n        destination: /data-deletion/index.html`r`n      - type: rewrite`r`n        source: /data-deletion/`r`n        destination: /data-deletion/index.html")
[IO.File]::WriteAllText($path, $content, $utf8)
$path = Join-Path $frontend 'nginx.conf'
$content = [IO.File]::ReadAllText($path)
$content = $content.Replace('  location / {', "  location = /data-deletion {`r`n    try_files /data-deletion/index.html =404;`r`n  }`r`n`r`n  location = /data-deletion/ {`r`n    try_files /data-deletion/index.html =404;`r`n  }`r`n`r`n  location / {")
[IO.File]::WriteAllText($path, $content, $utf8)
$path = Join-Path $frontend 'public/privacy-policy/index.html'
$content = [IO.File]::ReadAllText($path)
$content = $content.Replace('<h2 id="rights">Your choices and deletion requests</h2>', '<h2 id="rights">Your choices and deletion requests</h2>' + "`r`n    " + '<p>For request instructions and estimated handling times, visit our <a href="/data-deletion">Data Deletion page</a>.</p>')
[IO.File]::WriteAllText($path, $content, $utf8)
