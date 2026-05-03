import { useEffect } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { X } from 'lucide-react'
import { QR_URL_KEY, QR_CTA_KEY, DEFAULT_QR_URL, DEFAULT_QR_CTA } from '../qrConfig'

interface QrModalProps {
  open: boolean;
  onClose: () => void;
}

export default function QrModal({ open, onClose }: QrModalProps) {
  const url = localStorage.getItem(QR_URL_KEY) || DEFAULT_QR_URL
  const cta = localStorage.getItem(QR_CTA_KEY) || DEFAULT_QR_CTA

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative bg-white rounded-3xl shadow-2xl flex flex-col items-center gap-6 p-16 mx-4 min-w-[520px]"
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 rounded-full text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        <p className="text-3xl font-bold text-gray-900 text-center leading-tight">{cta}</p>

        <div className="rounded-2xl overflow-hidden p-3 bg-white ring-1 ring-gray-100 shadow-inner">
          <QRCodeSVG value={url} size={380} bgColor="#ffffff" fgColor="#111827" level="M" />
        </div>

        <p className="text-sm text-gray-400 font-mono break-all text-center">{url}</p>
      </div>
    </div>
  );
}
