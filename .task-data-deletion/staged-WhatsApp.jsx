import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Gift,
  Globe,
  MessageCircle,
  MessageSquareQuote,
  Phone,
  Send,
  Sparkles,
  Star,
  Users,
  Layers,
  Clock,
  MapPin,
  Bot,
  Filter,
  Users2,
  Calendar,
} from 'lucide-react';
import toast from 'react-hot-toast';

import Header from '../../components/Layout/Header.jsx';
import Badge from '../../components/UI/badge.jsx';
import Button from '../../components/UI/button.jsx';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/UI/card.jsx';
import Loader from '../../components/UI/loader.jsx';
import Select from '../../components/UI/select.jsx';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/UI/table.jsx';
import { communicationsApi } from '../../services/communications.js';
import { customersApi } from '../../services/customers.js';
import { segmentsApi } from '../../services/segments.js';
import { templatesApi } from '../../services/templates.js';
import {
  formatApiError,
  whatsappGraphVersion,
  whatsappPhoneNumberId,
  whatsappProvider,
  whatsappSendPath,
} from '../../services/api';
import { formatCurrency, formatNumber, formatRelativeTime } from '../../utils/format.js';

// Marketing Hub Sub-Components
import BulkSenderTab from './whatsapp/BulkSenderTab.jsx';
import ScheduledQueueTab from './whatsapp/ScheduledQueueTab.jsx';
import GMapsExtractorTab from './whatsapp/GMapsExtractorTab.jsx';
import AutoResponderTab from './whatsapp/AutoResponderTab.jsx';
import NumberFilterTab from './whatsapp/NumberFilterTab.jsx';
import GroupToolsTab from './whatsapp/GroupToolsTab.jsx';
import InteractiveButtonsBuilder from './whatsapp/InteractiveButtonsBuilder.jsx';
import MediaAttachmentManager from './whatsapp/MediaAttachmentManager.jsx';
import SpintaxHelper from './whatsapp/SpintaxHelper.jsx';

function normalizeCustomers(payload) {
  const customers =
    payload?.data ||
    payload?.items ||
    payload?.customers ||
    payload?.data?.data ||
    payload?.data?.items ||
    [];

  return Array.isArray(customers) ? customers : [];
}

function cleanPhoneNumber(value) {
  return (value || '').replace(/[^\d]/g, '');
}

function buildWhatsAppLink(phone, message) {
  const cleanedPhone = cleanPhoneNumber(phone);

  if (!cleanedPhone) return null;

  return `https://wa.me/${cleanedPhone}?text=${encodeURIComponent(message)}`;
}

function buildTemplateMessage(type, customer) {
  const name = customer?.name || 'there';
  const offerValue = formatCurrency(customer?.lifecycle?.avgOrderValue || 500);

  if (type === 'rating') {
    return `Hi ${name}, thanks for shopping with us. We'd love your feedback. Please reply with a quick rating from 1 to 5 and share any suggestions.`;
  }

  if (type === 'followup') {
    return `Hi ${name}, we noticed it has been a while since your last purchase. If you need help choosing the right product, just reply here and we'll assist you.`;
  }

  return `Hi ${name}, we have a special offer for you today. Based on your recent shopping profile, you may enjoy an exclusive deal around ${offerValue}. Reply to this message to claim it.`;
}

function buildTemplateParameters(type, customer) {
  const customerName = customer?.name || 'Customer';
  const offerValue = formatCurrency(customer?.lifecycle?.avgOrderValue || 500);

  if (type === 'offer') {
    return [customerName, offerValue];
  }

  if (type === 'rating') {
    return [customerName];
  }

  if (type === 'followup') {
    return [customerName];
  }

  return [customerName];
}

function personalizeMessage(templateMessage, customer) {
  const name = customer?.name || 'Customer';
  const discount = formatCurrency(customer?.lifecycle?.avgOrderValue || 500);

  return String(templateMessage || '')
    .replace(/\{\{\s*name\s*\}\}/gi, name)
    .replace(/\{\{\s*customer_name\s*\}\}/gi, name)
    .replace(/\{\{\s*discount\s*\}\}/gi, discount);
}

export default function WhatsApp() {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = searchParams.get('tab') || 'bulk';

  const [activeTab, setActiveTab] = useState(currentTab);
  const [preloadedNumbers, setPreloadedNumbers] = useState([]);

  // Direct Send State (Preserved)
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [selectedSegment, setSelectedSegment] = useState('');
  const [templateType, setTemplateType] = useState('');
  const [message, setMessage] = useState('');
  const [lastDelivery, setLastDelivery] = useState(null);
  const [singleButtons, setSingleButtons] = useState([]);
  const [singleMediaFiles, setSingleMediaFiles] = useState([]);

  // Sync tab with URL
  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    if (tabFromUrl) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Synchronize the selected tab with browser URL navigation.
      setActiveTab(tabFromUrl);
    }
  }, [searchParams]);

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  const handleSendToBulkMarketing = (numbersList) => {
    setPreloadedNumbers(numbersList);
    setActiveTab('bulk');
    setSearchParams({ tab: 'bulk' });
    toast.success(`Loaded ${numbersList.length} numbers into Bulk Sender!`);
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['whatsapp-customers'],
    queryFn: () =>
      customersApi.getAll({
        limit: 200,
        sortBy: 'createdAt',
        sortOrder: 'desc',
      }),
  });

  const templatesQuery = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.getAll(),
  });

  const segmentsQuery = useQuery({
    queryKey: ['segments'],
    queryFn: () => segmentsApi.getAll(),
  });

  const customers = useMemo(() => normalizeCustomers(data), [data]);
  const templates = useMemo(() => {
    const list =
      templatesQuery.data?.data ||
      templatesQuery.data?.items ||
      templatesQuery.data ||
      [];
    return Array.isArray(list) ? list : [];
  }, [templatesQuery.data]);

  const savedSegments = useMemo(() => {
    const list =
      segmentsQuery.data?.data ||
      segmentsQuery.data?.items ||
      segmentsQuery.data ||
      [];
    return Array.isArray(list) ? list : [];
  }, [segmentsQuery.data]);

  const reachableCustomers = useMemo(
    () => customers.filter((customer) => cleanPhoneNumber(customer.phone)),
    [customers]
  );

  const segmentOptions = useMemo(() => {
    const uniqueSegments = [
      ...new Set(
        savedSegments
          .flatMap((segment) =>
            Array.isArray(segment?.filters?.segments) ? segment.filters.segments : []
          )
          .filter(Boolean)
      ),
    ];

    return [
      { value: '', label: 'All Segments' },
      ...uniqueSegments.map((segment) => ({
        value: segment,
        label: String(segment).replace(/_/g, ' '),
      })),
    ];
  }, [savedSegments]);

  const templateOptions = useMemo(
    () =>
      templates.map((template) => ({
        value: template._id,
        label: template.name || template.whatsappTemplateName || 'Template',
      })),
    [templates]
  );

  const selectedTemplate = useMemo(
    () => templates.find((template) => template._id === templateType) || null,
    [templates, templateType]
  );

  useEffect(() => {
    if (!templateType && templates.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Select the initial template after asynchronous templates load.
      setTemplateType(templates[0]._id);
    }
  }, [templateType, templates]);

  const filteredCustomers = useMemo(() => {
    if (!selectedSegment) return reachableCustomers;
    return reachableCustomers.filter(
      (customer) => customer.lifecycle?.segment === selectedSegment
    );
  }, [reachableCustomers, selectedSegment]);

  const selectedCustomer = useMemo(
    () =>
      reachableCustomers.find((customer) => customer._id === selectedCustomerId) ||
      null,
    [reachableCustomers, selectedCustomerId]
  );

  const customerOptions = filteredCustomers.map((customer) => ({
    value: customer._id,
    label: `${customer.name} - ${customer.phone}`,
  }));

  const sendWhatsAppMutation = useMutation({
    mutationFn: ({ customer, outgoingMessage }) =>
      communicationsApi.sendWhatsApp({
        customerId: customer._id,
        name: customer.name,
        phone: cleanPhoneNumber(customer.phone),
        provider: whatsappProvider,
        graphVersion: whatsappGraphVersion,
        phoneNumberId: whatsappPhoneNumberId || undefined,
        templateType: selectedTemplate?.category || 'custom',
        templateParameters: buildTemplateParameters(selectedTemplate?.category, customer),
        preferredLanguage: customer.preferences?.language || 'en',
        channel: 'whatsapp',
        message: outgoingMessage,
        buttons: singleButtons,
        media_files: singleMediaFiles,
      }),

    onSuccess: (response, variables) => {
      const providerMessage =
        response?.message ||
        response?.data?.message ||
        'WhatsApp message sent successfully';

      setLastDelivery({
        customerName: variables.customer.name,
        phone: cleanPhoneNumber(variables.customer.phone),
        mode: 'api',
        message: variables.outgoingMessage,
        deliveryMode:
          response?.deliveryMode ||
          response?.data?.deliveryMode ||
          response?.data?.data?.deliveryMode ||
          'text',
      });

      toast.success(providerMessage);
    },

    onError: (error, variables) => {
      toast.error(formatApiError(error));

      if (variables?.allowFallback) {
        const fallbackLink = buildWhatsAppLink(
          variables.customer.phone,
          variables.outgoingMessage
        );

        if (fallbackLink) {
          window.open(fallbackLink, '_blank', 'noopener,noreferrer');
        }
      }
    },
  });

  const applyTemplate = () => {
    const nextMessage =
      selectedTemplate?.content?.body ||
      buildTemplateMessage(selectedTemplate?.category, selectedCustomer);
    setMessage(nextMessage);
    if (selectedTemplate?.content?.buttons?.length) {
      setSingleButtons(selectedTemplate.content.buttons);
    }
    toast.success('Message template applied');
  };

  const resolveOutgoingMessage = (customer) => {
    const rawMessage =
      message.trim() ||
      selectedTemplate?.content?.body ||
      buildTemplateMessage(selectedTemplate?.category, customer);

    return personalizeMessage(rawMessage, customer);
  };

  const handleOpenWhatsApp = (customer = selectedCustomer) => {
    if (!customer) {
      toast.error('Please choose a customer first');
      return;
    }

    const customerPhone = customer.phone;

    if (!cleanPhoneNumber(customerPhone)) {
      toast.error('This customer does not have a valid phone number');
      return;
    }

    const outgoingMessage = resolveOutgoingMessage(customer);
    const link = buildWhatsAppLink(customerPhone, outgoingMessage);

    if (!link) {
      toast.error('Unable to create WhatsApp link');
      return;
    }

    window.open(link, '_blank', 'noopener,noreferrer');

    setLastDelivery({
      customerName: customer.name,
      phone: cleanPhoneNumber(customerPhone),
      mode: 'manual',
      message: outgoingMessage,
    });
  };

  const handleSendViaApi = (customer = selectedCustomer) => {
    if (!customer) {
      toast.error('Please choose a customer first');
      return;
    }

    const customerPhone = customer.phone;

    if (!cleanPhoneNumber(customerPhone)) {
      toast.error('This customer does not have a valid phone number');
      return;
    }

    const outgoingMessage = resolveOutgoingMessage(customer);

    sendWhatsAppMutation.mutate({
      customer,
      outgoingMessage,
      allowFallback: true,
    });
  };

  if (isLoading || templatesQuery.isLoading || segmentsQuery.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader size="lg" />
      </div>
    );
  }

  const tabsConfig = [
    { id: 'bulk', label: 'WhatsApp Broadcast', icon: Layers, badge: 'Popular' },
    { id: 'scheduled', label: 'Scheduled Queue', icon: Clock },
    { id: 'gmaps', label: 'Google Maps Extractor', icon: MapPin, badge: 'Hot' },
    { id: 'auto_responder', label: 'Auto Responder Bot', icon: Bot },
    { id: 'number_filter', label: 'Number Filter', icon: Filter },
    { id: 'group_tools', label: 'Group Tools', icon: Users2 },
    { id: 'single', label: 'Direct 1-on-1 Send', icon: MessageCircle },
  ];

  return (
    <div className="min-h-screen bg-gray-50/50 pb-16">
      <Header
        title="WhatsApp Marketing Suite"
        subtitle="Complete bulk messaging, Google Maps lead extractor, auto responder, number filter, and group tools"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => refetch()}>
              Refresh Data
            </Button>
          </div>
        }
      />

      <div className="p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Navigation Tabs Bar */}
        <div className="flex items-center gap-2 overflow-x-auto rounded-2xl border border-gray-200 bg-white p-2 shadow-xs">
          {tabsConfig.map((t) => {
            const Icon = t.icon;
            const isSelected = activeTab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => handleTabChange(t.id)}
                className={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition-all ${
                  isSelected
                    ? 'bg-primary-600 text-white shadow-sm'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                <Icon className={`h-4 w-4 ${isSelected ? 'text-white' : 'text-gray-500'}`} />
                <span>{t.label}</span>
                {t.badge && (
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                      isSelected ? 'bg-white/20 text-white' : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {t.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* TAB 1: BULK & UNLIMITED SENDER */}
        {activeTab === 'bulk' && (
          <BulkSenderTab
            customers={customers}
            savedSegments={savedSegments}
            templates={templates}
            preloadedNumbers={preloadedNumbers}
            onSwitchToScheduledQueue={() => handleTabChange('scheduled')}
          />
        )}

        {/* TAB 2: SCHEDULED QUEUE & BULK JOBS */}
        {activeTab === 'scheduled' && <ScheduledQueueTab />}

        {/* TAB 3: GOOGLE MAPS LEAD EXTRACTOR */}
        {activeTab === 'gmaps' && (
          <GMapsExtractorTab onSendToBulkMarketing={handleSendToBulkMarketing} />
        )}

        {/* TAB 4: AUTO RESPONDER BOT */}
        {activeTab === 'auto_responder' && <AutoResponderTab />}

        {/* TAB 5: WHATSAPP NUMBER FILTER */}
        {activeTab === 'number_filter' && (
          <NumberFilterTab onSendToBulkMarketing={handleSendToBulkMarketing} />
        )}

        {/* TAB 6: GROUP TOOLS (AUTO JOINER & GRAB MEMBERS) */}
        {activeTab === 'group_tools' && (
          <GroupToolsTab onSendToBulkMarketing={handleSendToBulkMarketing} />
        )}

        {/* TAB 7: DIRECT 1-ON-1 SEND (PRESERVED ORIGINAL FUNCTIONALITY) */}
        {activeTab === 'single' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              <Card>
                <CardContent className="flex items-center justify-between p-6">
                  <div>
                    <p className="text-sm text-gray-500">Reachable Customers</p>
                    <p className="mt-2 text-2xl font-semibold text-gray-900">
                      {formatNumber(reachableCustomers.length)}
                    </p>
                  </div>
                  <Users className="h-6 w-6 text-green-600" />
                </CardContent>
              </Card>

              <Card>
                <CardContent className="flex items-center justify-between p-6">
                  <div>
                    <p className="text-sm text-gray-500">Selected Template</p>
                    <p className="mt-2 text-2xl font-semibold capitalize text-gray-900">
                      {selectedTemplate?.name || 'No template selected'}
                    </p>
                  </div>
                  <Sparkles className="h-6 w-6 text-primary-600" />
                </CardContent>
              </Card>

              <Card>
                <CardContent className="flex items-center justify-between p-6">
                  <div>
                    <p className="text-sm text-gray-500">Delivery Mode</p>
                    <p className="mt-2 text-2xl font-semibold text-gray-900">
                      {whatsappProvider === 'meta_cloud' ? 'Meta Cloud' : 'Manual Link'}
                    </p>
                  </div>
                  <MessageCircle className="h-6 w-6 text-gray-700" />
                </CardContent>
              </Card>
            </div>

            <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
              <Card className="xl:col-span-2">
                <CardHeader>
                  <CardTitle>Direct Message Composer</CardTitle>
                </CardHeader>

                <CardContent className="space-y-4">
                  {isError ? (
                    <p className="text-sm text-red-500">
                      Customers could not be loaded. Please refresh and try again.
                    </p>
                  ) : null}

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <Select
                      label="Segment"
                      options={segmentOptions}
                      value={selectedSegment}
                      onChange={(e) => {
                        setSelectedSegment(e.target.value);
                        setSelectedCustomerId('');
                      }}
                    />

                    <Select
                      label="Template"
                      options={templateOptions}
                      value={templateType}
                      onChange={(e) => {
                        const nextTemplateType = e.target.value;
                        setTemplateType(nextTemplateType);

                        const nextTemplate =
                          templates.find((template) => template._id === nextTemplateType) || null;
                        setMessage(
                          nextTemplate?.content?.body ||
                            buildTemplateMessage(nextTemplate?.category, selectedCustomer)
                        );
                        if (nextTemplate?.content?.buttons?.length) {
                          setSingleButtons(nextTemplate.content.buttons);
                        }
                      }}
                    />

                    <Select
                      label="Customer"
                      options={customerOptions}
                      value={selectedCustomerId}
                      onChange={(e) => {
                        const nextCustomerId = e.target.value;
                        setSelectedCustomerId(nextCustomerId);

                        const nextCustomer =
                          filteredCustomers.find(
                            (customer) => customer._id === nextCustomerId
                          ) || null;

                        setMessage(
                          selectedTemplate?.content?.body ||
                            buildTemplateMessage(selectedTemplate?.category, nextCustomer)
                        );
                      }}
                      placeholder="Choose customer"
                    />
                  </div>

                  {selectedCustomer ? (
                    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <p className="font-medium text-gray-900">{selectedCustomer.name}</p>

                        <Badge variant="info">
                          {(selectedCustomer.lifecycle?.segment || 'unassigned').replace(/_/g, ' ')}
                        </Badge>

                        <span className="text-sm text-gray-500">{selectedCustomer.phone}</span>
                      </div>

                      <p className="mt-2 text-sm text-gray-600">
                        Last purchase:{' '}
                        {selectedCustomer.lifecycle?.lastPurchaseDate
                          ? formatRelativeTime(selectedCustomer.lifecycle.lastPurchaseDate)
                          : 'No purchase yet'}
                      </p>
                    </div>
                  ) : null}

                  <div>
                    <label
                      htmlFor="whatsapp-message"
                      className="mb-2 block text-sm font-medium text-gray-700"
                    >
                      Message Body
                    </label>

                    <textarea
                      id="whatsapp-message"
                      rows={6}
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      placeholder="Write your WhatsApp message here..."
                      className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>

                  {/* Personalization helper */}
                  <SpintaxHelper
                    message={message}
                    onInsertToken={(tok) => setMessage((prev) => `${prev} ${tok}`)}
                  />

                  {/* Interactive Buttons (Feature 4: Add Button) */}
                  <InteractiveButtonsBuilder buttons={singleButtons} onChange={setSingleButtons} />

                  {/* Media files (Feature 8) */}
                  <MediaAttachmentManager mediaFiles={singleMediaFiles} onChange={setSingleMediaFiles} />

                  <div className="flex flex-wrap items-center gap-3 pt-2">
                    <Button variant="outline" onClick={applyTemplate}>
                      Apply Template
                    </Button>

                    <Button
                      onClick={() => handleSendViaApi()}
                      isLoading={sendWhatsAppMutation.isPending}
                    >
                      <Send className="mr-2 h-4 w-4" />
                      Send via API
                    </Button>

                    <Button onClick={() => handleOpenWhatsApp()}>
                      <MessageCircle className="mr-2 h-4 w-4" />
                      Open WhatsApp
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Send Setup & Diagnostics</CardTitle>
                </CardHeader>

                <CardContent className="space-y-4">
                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                    <div className="flex items-start gap-3">
                      <div className="rounded-lg bg-white p-2">
                        <Globe className="h-5 w-5 text-gray-700" />
                      </div>

                      <div>
                        <p className="font-medium text-gray-900">API endpoint</p>
                        <p className="mt-1 break-all text-sm text-gray-500">{whatsappSendPath}</p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                    <p className="text-sm font-medium text-gray-900">Meta Cloud target</p>
                    <p className="mt-2 text-sm text-gray-500">Provider: {whatsappProvider}</p>
                    <p className="mt-1 text-sm text-gray-500">Graph version: {whatsappGraphVersion}</p>
                    <p className="mt-1 break-all text-sm text-gray-500">
                      Phone number ID: {whatsappPhoneNumberId || 'Not configured'}
                    </p>
                  </div>

                  {lastDelivery ? (
                    <div className="rounded-xl border border-green-200 bg-green-50 p-4">
                      <p className="text-sm font-medium text-green-800">Last delivery</p>
                      <p className="mt-2 text-sm text-green-700">
                        {lastDelivery.customerName} ({lastDelivery.phone})
                      </p>
                      <p className="mt-1 text-sm text-green-700">
                        Sent via {lastDelivery.mode === 'api' ? 'backend API' : 'manual WhatsApp link'}
                      </p>
                      {lastDelivery.deliveryMode ? (
                        <p className="mt-1 text-sm text-green-700">
                          Meta delivery mode: {lastDelivery.deliveryMode}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>WhatsApp Ready Customers</CardTitle>
              </CardHeader>

              <CardContent className="p-0">
                {filteredCustomers.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Customer</TableHead>
                        <TableHead>Phone</TableHead>
                        <TableHead>Segment</TableHead>
                        <TableHead>Total Spent</TableHead>
                        <TableHead>Last Activity</TableHead>
                        <TableHead className="text-right">Action</TableHead>
                      </TableRow>
                    </TableHeader>

                    <TableBody>
                      {filteredCustomers.slice(0, 12).map((customer) => (
                        <TableRow key={customer._id}>
                          <TableCell>
                            <div>
                              <p className="font-medium text-gray-900">{customer.name}</p>
                              <p className="text-sm text-gray-500">{customer.email || 'No email'}</p>
                            </div>
                          </TableCell>

                          <TableCell>
                            <div className="flex items-center gap-2 text-sm text-gray-700">
                              <Phone className="h-4 w-4 text-gray-400" />
                              {customer.phone}
                            </div>
                          </TableCell>

                          <TableCell>
                            <Badge variant="default">
                              {(customer.lifecycle?.segment || 'unassigned').replace(/_/g, ' ')}
                            </Badge>
                          </TableCell>

                          <TableCell>{formatCurrency(customer.lifecycle?.totalSpent || 0)}</TableCell>

                          <TableCell>
                            {customer.lifecycle?.lastPurchaseDate
                              ? formatRelativeTime(customer.lifecycle.lastPurchaseDate)
                              : 'No recent purchase'}
                          </TableCell>

                          <TableCell className="text-right">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedCustomerId(customer._id);
                                setMessage(
                                  selectedTemplate?.content?.body ||
                                    buildTemplateMessage(selectedTemplate?.category, customer)
                                );
                                handleSendViaApi(customer);
                              }}
                            >
                              Send
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="px-6 py-10 text-center text-sm text-gray-500">
                    No customers with WhatsApp-ready phone numbers were found for this filter.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
