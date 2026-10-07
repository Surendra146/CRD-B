from pathlib import Path

root = Path(r'D:\web apps\React\CBD project')
path = root / 'src/Pages/CLC/whatsapp/BulkSenderTab.jsx'
s = path.read_text(encoding='utf-8')
s = s.replace("  const [message, setMessage] = useState('');", "  const [message, setMessage] = useState('');\n  const [metaTemplateName, setMetaTemplateName] = useState('');\n  const [metaTemplateLanguage, setMetaTemplateLanguage] = useState('en_US');")
s = s.replace("      toast.success(res?.message || 'Bulk campaign launched successfully!');", "      if (res?.success === false || res?.data?.stats?.failed > 0) {\n        toast.error(res?.message || 'Some messages failed. Check recipient errors in the queue.');\n      } else {\n        toast.success(res?.message || 'Meta accepted the broadcast; delivery is pending confirmation.');\n      }")
s = s.replace("      toast.error(err?.response?.data?.detail || err?.message || 'Failed to dispatch bulk campaign');", "      const detail = err?.response?.data?.detail;\n      toast.error(typeof detail === 'string' ? detail : detail?.provider_message || detail?.message || err?.message || 'Failed to dispatch bulk campaign');")
s = s.replace('    if (!message.trim()) {', '    if (!message.trim() && !metaTemplateName.trim()) {')
s = s.replace('      message: message.trim(),', "      message: message.trim(),\n      template: metaTemplateName.trim() ? { name: metaTemplateName.trim(), language: { code: metaTemplateLanguage.trim() } } : undefined,")
s = s.replace('Send thousands of personalized messages with interactive buttons, multi-media files, anti-ban pacing, and scheduled broadcasts.', 'Send up to 20 recipients per immediate broadcast. Meta acceptance and delivery are tracked separately in the queue.')
s = s.replace('              <div>\n                <label className="mb-2 block text-xs font-semibold text-gray-700">Message Body *</label>', '''              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
                <p>Custom text requires the recipient to have messaged your business within the last 24 hours. Otherwise use an approved Meta template. A saved CRM message is not a Meta-approved template.</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label>Approved Meta template name (optional)
                    <Input value={metaTemplateName} onChange={(e) => setMetaTemplateName(e.target.value)} placeholder="hello_world" />
                  </label>
                  <label>Exact template language code
                    <Input value={metaTemplateLanguage} onChange={(e) => setMetaTemplateLanguage(e.target.value)} placeholder="en_US" />
                  </label>
                </div>
                <p className="mt-2 text-xs">Use a template with no dynamic parameters here. Leave the name empty to send the custom text below. Meta controls the template content.</p>
              </div>
              <div>
                <label className="mb-2 block text-xs font-semibold text-gray-700">Message Body</label>''')
# Insert the guidance reliably even when source whitespace differs.
if 'Approved Meta template name' not in s:
    raise RuntimeError('Composer insertion point was not found')
s = s.replace("onClick={() => setDeliveryMode('scheduled')}", "disabled title=\"Automatic scheduling is not available yet\"")
s = s.replace('Starts processing the broadcast queue now', 'Sends immediately through Meta')
path.write_text(s, encoding='utf-8')

path = root / 'src/Pages/CLC/whatsapp/ScheduledQueueTab.jsx'
s = path.read_text(encoding='utf-8')
s = s.replace("    queryFn: () => communicationsApi.getBulkJobs({ limit: 50 }),", "    queryFn: () => communicationsApi.getBulkJobs({ limit: 50 }),\n    refetchInterval: 10000,")
s = s.replace("      case 'completed':", "      case 'failed':\n        return <Badge variant=\"destructive\">Failed</Badge>;\n      case 'completed':")
s = s.replace('<th className="p-2">Status</th>', '<th className="p-2">Status / Error</th>')
s = s.replace('<span className="text-emerald-700 font-semibold capitalize">{r.status}</span>', '''<span className={r.status === 'failed' || r.status === 'unknown' ? 'text-red-700 font-semibold capitalize' : 'text-gray-700 font-semibold capitalize'}>{r.status}</span>
                            {r.message_id && <p className="break-all text-[10px] text-gray-500">{r.message_id}</p>}
                            {r.error && <p className="mt-1 text-red-700">{typeof r.error === 'string' ? r.error : JSON.stringify(r.error)}</p>}''')
path.write_text(s, encoding='utf-8')
