from pathlib import Path
path = Path(r'D:\web apps\React\CBD project\src\Pages\CLC\whatsapp\BulkSenderTab.jsx')
s = path.read_text(encoding='utf-8')
s = s.replace('disabled title="Automatic scheduling is not available yet"', 'title="Automatic scheduling is not available yet"')
s = s.replace("onChange={() => setDeliveryMode('scheduled')}", 'disabled')
s = s.replace('Queue this campaign to be sent automatically at a future date and time.', 'Automatic scheduling is not available yet. Use Send Immediately.')
s = s.replace('Sends immediately through Meta with {batchDelaySeconds}s delay per contact.', 'Submits to Meta now. Delivery confirmation arrives separately.')
path.write_text(s, encoding='utf-8')
