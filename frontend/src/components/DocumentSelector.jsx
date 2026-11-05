
import { useRef } from 'react'
import { Upload } from 'lucide-react'

export default function DocumentSelector({
  onFilesSelected,
  accept = '.pdf,.doc,.docx,.txt,.csv,.xls,.xlsx,.png,.jpg,.jpeg',
  multiple = true,
  label = 'Attach Documents',
  note = 'Supported: PDF, DOC, DOCX, TXT, CSV, XLS, XLSX, PNG and JPG.',
}) {
  const inputRef = useRef(null)

  const handleChange = (event) => {
    const files = Array.from(event.target.files || [])

    if (files.length > 0) {
      onFilesSelected?.(files)
    }

    // Allow selecting the same file again later
    event.target.value = ''
  }

  return (
    <div className="document-selector">
      <label className="details-upload-btn">
        <Upload size={17} />
        {label}

        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleChange}
          hidden
        />
      </label>

      {note && (
        <p className="details-upload-note">
          {note}
        </p>
      )}
    </div>
  )
}
