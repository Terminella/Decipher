
import { useEffect, useState } from 'react'
import { X, FileText, Download } from 'lucide-react'

export default function DocumentViewer({ file, onClose }) {
  const [previewUrl, setPreviewUrl] = useState('')

  useEffect(() => {
    if (!file) return

    const url = URL.createObjectURL(file)
    setPreviewUrl(url)

    return () => URL.revokeObjectURL(url)
  }, [file])

  if (!file) return null

  const isPdf =
    file.type === 'application/pdf' ||
    file.name.toLowerCase().endsWith('.pdf')

  const isImage = file.type.startsWith('image/') ||
    /\.(png|jpe?g|tiff?|bmp|webp)$/i.test(file.name)

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        background: 'rgba(0,0,0,0.8)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div style={{
        width: '100%',
        maxWidth: '1100px',
        height: '90vh',
        background: '#19283e',
        border: '1px solid #33445e',
        borderRadius: '12px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{
          minHeight: '60px',
          padding: '12px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid #33445e',
          color: '#fff',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            minWidth: 0,
          }}>
            <FileText size={20} />
            <strong style={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>{file.name}</strong>
          </div>

          <div style={{ display: 'flex', gap: '16px' }}>
            <a
              href={previewUrl}
              download={file.name}
              style={{ color: '#37d5c8' }}
              aria-label="Download file"
            >
              <Download size={20} />
            </a>

            <button
              onClick={onClose}
              style={{
                background: 'transparent',
                border: 0,
                color: '#fff',
                cursor: 'pointer',
              }}
              aria-label="Close preview"
            >
              <X size={22} />
            </button>
          </div>
        </div>

        <div style={{
          flex: 1,
          minHeight: 0,
          overflow: 'auto',
          background: '#101827',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
        }}>
          {previewUrl && isPdf && (
            <iframe
              src={previewUrl}
              title={file.name}
              style={{
                width: '100%',
                height: '100%',
                border: 0,
                background: '#fff',
              }}
            />
          )}

          {previewUrl && isImage && (
            <img
              src={previewUrl}
              alt={file.name}
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                objectFit: 'contain',
              }}
            />
          )}

          {!isPdf && !isImage && (
            <div style={{ color: '#fff', textAlign: 'center' }}>
              <FileText size={42} />
              <h3>Preview unavailable</h3>
              <p>This format cannot be previewed directly.</p>
              <a href={previewUrl} download={file.name}>
                Download File
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
