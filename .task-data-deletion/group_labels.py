from pathlib import Path
path = Path(r'D:\web apps\React\CBD project\src\Pages\CLC\whatsapp\GroupToolsTab.jsx')
s = path.read_text(encoding='utf-8')
s = s.replace('2. Auto Group Joiner', '2. Invite Link Organizer').replace('Group Join Queue (', 'Validated Invite Links (').replace('Ready to Join', 'Valid link format').replace('Paste WhatsApp group invite links on the left to organize and join them without getting flagged for fast spamming.', 'Paste invite links to validate their format. Opening a link lets you review and join manually in WhatsApp.')
path.write_text(s, encoding='utf-8')
