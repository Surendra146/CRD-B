from pathlib import Path
root = Path(r'D:\web apps\React\CBD project')
service = '''import { apiWrapper } from '../config';

const base = '/api/whatsapp-connection';
export const whatsappConnectionApi = {
  status: () => apiWrapper({ url: `${base}/`, method: 'GET' }),
  start: () => apiWrapper({ url: `${base}/start`, method: 'POST' }),
  exchange: (data) => apiWrapper({ url: `${base}/exchange`, method: 'POST', data }),
  select: (data) => apiWrapper({ url: `${base}/select`, method: 'POST', data }),
  disconnect: () => apiWrapper({ url: `${base}/`, method: 'DELETE' }),
};
'''
(root / 'src/services/whatsappConnection.js').write_text(service, encoding='utf-8')
component = '''import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import Button from '../UI/button.jsx';
import { Card, CardContent, CardHeader, CardTitle } from '../UI/card.jsx';
import { whatsappConnectionApi } from '../../services/whatsappConnection.js';
import { useAuthStore } from '../../store/authstore.js';

const dataOf = (response) => response?.data?.data || response?.data || response;
const errorOf = (error) => {
  const detail = error?.response?.data?.detail;
  return (typeof detail === 'string' ? detail : detail?.message) || error.message || 'Unable to connect WhatsApp';
};

let sdkPromise;
function loadSdk(config) {
  if (!sdkPromise) {
    sdkPromise = new Promise((resolve, reject) => {
      if (window.FB) { resolve(); return; }
      const script = document.createElement('script');
      script.src = 'https://connect.facebook.net/en_US/sdk.js';
      script.async = true;
      script.crossOrigin = 'anonymous';
      script.onload = () => window.FB ? resolve() : reject(new Error('Meta sign-in SDK did not load'));
      script.onerror = () => reject(new Error('Unable to load Meta sign-in. Check your browser or connection'));
      document.head.appendChild(script);
    }).catch((error) => { sdkPromise = undefined; throw error; });
  }
  return sdkPromise.then(() => window.FB.init({ appId: config.app_id, version: config.graph_version, cookie: false, xfbml: false }));
}

export default function WhatsAppConnectionCard() {
  const user = useAuthStore((state) => state.user);
  const organization = user?.organization_id || user?.organizationId;
  const queryClient = useQueryClient();
  const key = ['whatsapp-connection', organization];
  const status = useQuery({ queryKey: key, queryFn: whatsappConnectionApi.status, enabled: Boolean(organization) });
  const connection = dataOf(status.data) || {};
  const [signup, setSignup] = useState(null);
  const [assets, setAssets] = useState([]);
  const [selected, setSelected] = useState('');
  const [registerNew, setRegisterNew] = useState(false);
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);

  async function prepare() {
    setBusy(true);
    setSignup(null);
    setAssets([]);
    try {
      const config = dataOf(await whatsappConnectionApi.start());
      await loadSdk(config);
      setSignup(config);
    } catch (error) { toast.error(errorOf(error)); }
    finally { setBusy(false); }
  }

  function continueWithMeta() {
    if (!signup || busy) return;
    setBusy(true);
    // Keep FB.login inside the click handler so browsers allow the popup.
    window.FB.login((response) => {
      const code = response?.authResponse?.code;
      if (!code) { setBusy(false); toast.error('Meta sign-in was cancelled or did not grant access'); return; }
      whatsappConnectionApi.exchange({ state: signup.state, code })
        .then((result) => {
          const list = dataOf(result)?.assets || [];
          setAssets(list);
          setSelected(list.length === 1 ? `${list[0].waba_id}:${list[0].phone_number_id}` : '');
        })
        .catch((error) => { setSignup(null); toast.error(errorOf(error)); })
        .finally(() => setBusy(false));
    }, { config_id: signup.config_id, response_type: 'code', override_default_response_type: true, extras: {} });
  }

  async function finish() {
    const asset = assets.find((item) => `${item.waba_id}:${item.phone_number_id}` === selected);
    if (!asset) { toast.error('Select a WhatsApp phone number'); return; }
    if (registerNew && !/^\\d{6}$/.test(pin)) { toast.error('Enter the six-digit registration PIN'); return; }
    setBusy(true);
    try {
      await whatsappConnectionApi.select({ state: signup.state, waba_id: asset.waba_id, phone_number_id: asset.phone_number_id, ...(registerNew ? { registration_pin: pin } : {}) });
      setSignup(null); setAssets([]); setPin(''); setRegisterNew(false);
      await queryClient.invalidateQueries({ queryKey: key });
      toast.success('Your organization’s WhatsApp Business account is connected');
    } catch (error) { toast.error(errorOf(error)); }
    finally { setBusy(false); }
  }

  async function disconnect() {
    if (!window.confirm('Disconnect this organization from WhatsApp? Its CRM sends will stop. Your Meta account and messages will remain.')) return;
    setBusy(true);
    try {
      await whatsappConnectionApi.disconnect();
      setSignup(null); setAssets([]); setPin('');
      await queryClient.invalidateQueries({ queryKey: key });
      toast.success('WhatsApp disconnected from this CRM');
    } catch (error) { toast.error(errorOf(error)); }
    finally { setBusy(false); }
  }

  return (
    <Card className="xl:col-span-3">
      <CardHeader><CardTitle>WhatsApp Business connection</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-gray-600">Connect your organization’s own WhatsApp account through Meta. Messages use this connection and stay separate from other organizations.</p>
        {status.isPending && <p className="text-sm">Checking connection…</p>}
        {status.isError && <p role="alert" className="text-sm text-red-700">{errorOf(status.error)}</p>}
        {connection.connected && <p className="text-sm text-emerald-700">Connected: {connection.verified_name || 'WhatsApp Business'} · {connection.display_phone_number || connection.phone_number_id}</p>}
        {connection.expired && <p role="alert" className="text-sm text-amber-700">Your Meta authorization has expired. Reconnect to send messages.</p>}
        {!status.isPending && !status.isError && !connection.signup_configured && <p className="text-sm text-amber-700">The service administrator must finish the shared Meta signup setup before accounts can connect.</p>}
        {connection.can_manage ? (
          <div className="flex flex-wrap gap-3">
            {!signup && <Button type="button" disabled={busy || !connection.signup_configured} onClick={prepare}>{busy ? 'Preparing…' : connection.connected ? 'Reconnect WhatsApp' : 'Connect WhatsApp'}</Button>}
            {signup && !assets.length && <Button type="button" disabled={busy} onClick={continueWithMeta}>{busy ? 'Connecting…' : 'Continue with Meta'}</Button>}
            {signup && <Button type="button" variant="outline" disabled={busy} onClick={() => { setSignup(null); setAssets([]); setPin(''); }}>Cancel</Button>}
            {connection.connected && <Button type="button" variant="outline" disabled={busy} onClick={disconnect}>Disconnect</Button>}
          </div>
        ) : !status.isPending && <p className="text-sm text-gray-500">The organization owner manages this connection.</p>}
        {assets.length > 0 && (
          <div className="space-y-3 rounded-xl border border-gray-200 p-4">
            <label className="block text-sm font-medium">Choose a phone number authorized by Meta
              <select className="mt-2 block w-full rounded border p-2" value={selected} onChange={(event) => setSelected(event.target.value)}>
                <option value="">Select a number</option>
                {assets.map((asset) => <option key={`${asset.waba_id}:${asset.phone_number_id}`} value={`${asset.waba_id}:${asset.phone_number_id}`}>{asset.verified_name || 'WhatsApp Business'} · {asset.display_phone_number || asset.phone_number_id}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={registerNew} onChange={(event) => setRegisterNew(event.target.checked)} />Register a new phone number with Cloud API</label>
            {registerNew && <label className="block text-sm">Six-digit registration PIN<input className="ml-3 rounded border p-2" type="password" inputMode="numeric" maxLength={6} autoComplete="off" value={pin} onChange={(event) => setPin(event.target.value)} /><span className="mt-1 block text-xs text-gray-500">Keep this PIN for your business. Leave registration unchecked for an already registered sender.</span></label>}
            <Button type="button" disabled={busy || !selected} onClick={finish}>{busy ? 'Saving connection…' : 'Connect selected number'}</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
'''
directory = root / 'src/components/whatsapp'
directory.mkdir(parents=True, exist_ok=True)
(directory / 'WhatsAppConnectionCard.jsx').write_text(component, encoding='utf-8')
path = root / 'src/Pages/CLC/Settings.jsx'
s = path.read_text(encoding='utf-8')
s = s.replace("import { authApi } from '../../services/auth.js';", "import { authApi } from '../../services/auth.js';\nimport WhatsAppConnectionCard from '../../components/whatsapp/WhatsAppConnectionCard.jsx';")
s = s.replace('<div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:p-8 xl:grid-cols-3">', '<div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:p-8 xl:grid-cols-3">\n        <WhatsAppConnectionCard />')
path.write_text(s, encoding='utf-8')
