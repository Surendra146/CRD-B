from pathlib import Path
root = Path(r'D:\web apps\React\CBD project')
path = root / 'src/Pages/CLC/whatsapp/BulkSenderTab.jsx'
s = path.read_text(encoding='utf-8')
s = s.replace('Safe Sending Rate', 'Dispatch interval').replace('Anti-Ban Protection & Throttling', 'Dispatch interval')
s = s.replace('Adds a safety delay between dispatches to comply with WhatsApp rate limits and prevent account restrictions.', 'Waits between requests. Meta messaging rules and account limits still apply.')
s = s.replace('                      <option value={8}>8 seconds (Extra Safe)</option>\n', '').replace('                      <option value={12}>12 seconds (Conservative)</option>\n', '')
path.write_text(s, encoding='utf-8')
path = root / 'src/Pages/CLC/whatsapp/AutoResponderTab.jsx'
s = path.read_text(encoding='utf-8').replace('WhatsApp 24/7 Auto Responder Bot', 'Auto-Reply Rule Tester').replace('Set up automatic keyword-based replies, product catalogs, FAQ bots, and default fallback responses for all incoming customer messages.', 'Save and test keyword-based response rules. Automatic replies to incoming WhatsApp messages are not connected.')
path.write_text(s, encoding='utf-8')
path = root / 'src/Pages/CLC/whatsapp/MediaAttachmentManager.jsx'
s = path.read_text(encoding='utf-8').replace('Multiple Media & File Attachments', 'Public Media URL').replace('Attach multiple product images, PDF brochures, catalogs, or documents at once', 'Send one public HTTPS image, video or document URL per message. Local uploads are not supported')
s = s.replace("onClick={() => fileInputRef.current?.click()}", 'disabled title="Use Add Media URL; local upload is not supported"')
s = s.replace("    if (!urlInput.trim()) {", "    if (mediaFiles.length) {\n      toast.error('Send one media URL per message');\n      return;\n    }\n    if (!urlInput.trim().startsWith('https://')) {")
path.write_text(s, encoding='utf-8')
