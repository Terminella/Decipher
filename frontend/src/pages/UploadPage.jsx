
import { useRef, useState } from 'react'
import {
  Upload,
  FileText,
  FileSpreadsheet,
  FileImage,
  File,
  X,
  Trash2,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
  ShieldCheck,
  ArrowRight,
} from 'lucide-react'

const ACCEPTED_TYPES = [
  '.pdf',
  '.doc',
  '.docx',
  '.txt',
  '.csv',
  '.xls',
  '.xlsx',
  '.png',
  '.jpg',
  '.jpeg',
]

const MAX_FILE_SIZE = 20 * 1024 * 1024

function getFileIcon(fileName) {
  const extension = fileName.split('.').pop().toLowerCase()

  if (['jpg', 'jpeg', 'png'].includes(extension)) {
    return FileImage
  }

  if (['xls', 'xlsx', 'csv'].includes(extension)) {
    return FileSpreadsheet
  }

  if (['pdf', 'doc', 'docx', 'txt'].includes(extension)) {
    return FileText
  }

  return File
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export default function UploadPage() {
  const inputRef = useRef(null)

  const [files, setFiles] = useState([])
  const [errors, setErrors] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  const processFiles = (selectedFiles) => {
    const newErrors = []
    const validFiles = []

    Array.from(selectedFiles).forEach((file) => {
      const extension = `.${file.name.split('.').pop().toLowerCase()}`

      if (!ACCEPTED_TYPES.includes(extension)) {
        newErrors.push(`${file.name}: Unsupported file type`)
        return
      }

      if (file.size > MAX_FILE_SIZE) {
        newErrors.push(`${file.name}: File exceeds 20 MB`)
        return
      }

      if (file.size === 0) {
        newErrors.push(`${file.name}: Empty files are not allowed`)
        return
      }

      validFiles.push(file)
    })

    setErrors(newErrors)

    if (validFiles.length > 0) {
      setFiles((previous) => {
        const combined = [...previous]

        validFiles.forEach((file) => {
          const alreadyExists = combined.some(
            (existing) =>
              existing.name === file.name &&
              existing.size === file.size &&
              existing.lastModified === file.lastModified
          )

          if (!alreadyExists) {
            combined.push(file)
          }
        })

        return combined
      })

      setConfirmed(false)
    }
  }

  const removeFile = (index) => {
    setFiles((previous) =>
      previous.filter((_, fileIndex) => fileIndex !== index)
    )

    setConfirmed(false)
  }

  const clearFiles = () => {
    setFiles([])
    setErrors([])
    setConfirmed(false)

    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragging(false)
    processFiles(event.dataTransfer.files)
  }

  const totalSize = files.reduce(
    (total, file) => total + file.size,
    0
  )

  return (
    <div className="upload-page">

      {/* Page Heading */}

      <div className="upload-heading">
        <div>
          <div className="eyebrow">
            <span className="live-dot" />
            DOCUMENT MANAGEMENT
          </div>

          <h1>Upload Documents</h1>

          <p>
            Add your documents to begin the investigation workflow.
          </p>
        </div>

        <div className="secure-label">
          <ShieldCheck size={19} />
          Secure document workspace
        </div>
      </div>

      {/* Upload Area */}

      <section className="upload-panel">
        <div className="upload-panel-heading">
          <div>
            <h3>Select your documents</h3>
            <p>
              Upload individual files or multiple documents together.
            </p>
          </div>

          <div className="upload-step">STEP 01 / 03</div>
        </div>

        <div
          className={`drop-zone ${isDragging ? 'drag-active' : ''}`}
          onDragOver={(event) => {
            event.preventDefault()
            setIsDragging(true)
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) {
              setIsDragging(false)
            }
          }}
          onDrop={handleDrop}
        >
          <div className="upload-icon">
            <Upload size={34} />
          </div>

          <h2>
            Drag and drop your documents here
          </h2>

          <p>
            or browse files from your computer
          </p>

          <button
            className="button-primary browse-button"
            onClick={() => inputRef.current?.click()}
          >
            <FolderOpen size={19} />
            Browse Files
          </button>

          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED_TYPES.join(',')}
            hidden
            onChange={(event) => {
              processFiles(event.target.files)
              event.target.value = ''
            }}
          />

          <div className="upload-limit">
            Maximum 20 MB per file
          </div>
        </div>

        <div className="supported-formats">
          <span>SUPPORTED FORMATS</span>

          <div className="format-list">
            {['PDF', 'DOCX', 'XLSX', 'CSV', 'TXT', 'JPG', 'PNG'].map(
              (format) => (
                <span key={format}>{format}</span>
              )
            )}
          </div>
        </div>
      </section>

      {/* Validation Errors */}

      {errors.length > 0 && (
        <section className="upload-errors">
          <div className="error-heading">
            <AlertCircle size={19} />
            Some files could not be selected
          </div>

          {errors.map((error, index) => (
            <p key={index}>{error}</p>
          ))}
        </section>
      )}

      {/* Selected Files */}

      <section className="selected-files-panel">
        <div className="selected-header">
          <div>
            <h3>Selected Documents</h3>
            <p>
              {files.length} {files.length === 1 ? 'file' : 'files'} selected
            </p>
          </div>

          {files.length > 0 && (
            <button
              className="clear-button"
              onClick={clearFiles}
            >
              <Trash2 size={16} />
              Clear all
            </button>
          )}
        </div>

        {files.length === 0 ? (
          <div className="no-files">
            <FileText size={30} />
            <strong>No documents selected</strong>
            <span>
              Your selected documents will appear here.
            </span>
          </div>
        ) : (
          <div className="selected-file-list">
            {files.map((file, index) => {
              const Icon = getFileIcon(file.name)

              return (
                <div className="selected-file" key={`${file.name}-${file.lastModified}-${index}`}>
                  <div className="selected-file-icon">
                    <Icon size={23} />
                  </div>

                  <div className="selected-file-info">
                    <strong>{file.name}</strong>
                    <span>
                      {formatFileSize(file.size)} · Ready for review
                    </span>
                  </div>

                  <div className="file-ready">
                    <CheckCircle2 size={17} />
                    <span>Ready</span>
                  </div>

                  <button
                    className="remove-file"
                    onClick={() => removeFile(index)}
                    aria-label={`Remove ${file.name}`}
                  >
                    <X size={18} />
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {files.length > 0 && (
          <div className="upload-summary">
            <div>
              <span>Total files</span>
              <strong>{files.length}</strong>
            </div>

            <div>
              <span>Total size</span>
              <strong>{formatFileSize(totalSize)}</strong>
            </div>

            <div>
              <span>Selection status</span>
              <strong className="ready-text">
                {confirmed ? 'Confirmed locally' : 'Ready'}
              </strong>
            </div>
          </div>
        )}

        {files.length > 0 && (
          <div className="upload-actions">
            <button
              className="button-secondary"
              onClick={clearFiles}
            >
              Cancel
            </button>

            <button
              className="button-primary"
              onClick={() => setConfirmed(true)}
            >
              {confirmed ? (
                <>
                  <CheckCircle2 size={18} />
                  Selection Confirmed
                </>
              ) : (
                <>
                  Confirm Selection
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </div>
        )}

        {confirmed && (
          <div className="confirmation-message">
            <CheckCircle2 size={19} />
            Your file selection is confirmed locally. No files have
            been uploaded to a server or analyzed.
          </div>
        )}
      </section>

      {/* Information */}

      <div className="upload-information">
        <ShieldCheck size={21} />

        <div>
          <strong>Document handling information</strong>
          <p>
            This frontend prototype keeps selected file references
            in browser memory only. No permanent storage or server
            upload is currently configured.
          </p>
        </div>
      </div>

    </div>
  )
}
