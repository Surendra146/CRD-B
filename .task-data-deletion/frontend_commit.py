from pathlib import Path
import subprocess
root = Path(r'D:\web apps\React\CBD project')
def git(*args):
    return subprocess.check_output(['git', *args], cwd=root).decode().strip()
assert not git('diff', '--cached', '--name-only'), 'Existing staged changes require review'
paths = [
    'package-lock.json', 'src/Pages/CLC/Settings.jsx',
    'src/Pages/CLC/whatsapp/AutoResponderTab.jsx', 'src/Pages/CLC/whatsapp/BulkSenderTab.jsx',
    'src/Pages/CLC/whatsapp/GMapsExtractorTab.jsx', 'src/Pages/CLC/whatsapp/GroupToolsTab.jsx',
    'src/Pages/CLC/whatsapp/MediaAttachmentManager.jsx', 'src/Pages/CLC/whatsapp/NumberFilterTab.jsx',
]
git('add', '--', *paths)
for name in ['src/Pages/CLC/WhatsApp.jsx', 'src/config/apiConfig.js']:
    path = root / name
    current = path.read_text(encoding='utf-8')
    head = git('show', 'HEAD:' + name) + '\n'
    if name.endswith('WhatsApp.jsx'):
        def update(s): return s.replace('Bulk & Unlimited Sender', 'WhatsApp Broadcast')
    else:
        before = "export const formatApiError = (error) =>\n  error?.response?.data?.message ||\n  error?.response?.data?.error ||\n  error?.message ||\n  'Something went wrong';"
        after = """export const formatApiError = (error) => {
  const detail = error?.response?.data?.detail;
  return (typeof detail === 'string' ? detail : detail?.provider_message || detail?.message) ||
    error?.response?.data?.message || error?.response?.data?.error ||
    error?.message || 'Something went wrong';
};"""
        def update(s):
            assert before in s, 'Error formatter insertion point missing'
            return s.replace(before, after)
    path.write_text(update(current), encoding='utf-8')
    temporary = Path(__file__).parent / ('staged-' + path.name)
    temporary.write_text(update(head), encoding='utf-8')
    sha = git('hash-object', '-w', '--', str(temporary))
    git('update-index', '--cacheinfo', f'100644,{sha},{name}')
print(git('diff', '--cached', '--stat'))
git('diff', '--cached', '--check')
