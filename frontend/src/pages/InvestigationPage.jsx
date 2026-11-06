import DocumentViewer from '../components/DocumentViewer'
import DocumentSelector from '../components/DocumentSelector'
import AuditTrailModal from '../components/AuditTrailModal'
import { useEffect, useState } from 'react'
import api from '../services/api'
import {
  Search, Plus, SlidersHorizontal, FolderSearch, History,
  FileText, Clock3, CircleCheck, CircleAlert,
  X, ArrowLeft, CalendarDays, Upload, Trash2,
  FilePlus2, MoreHorizontal
} from 'lucide-react'

const filters = ['All', 'In Progress', 'Completed', 'On Hold']

function mapDocument(document) {
  return {
    id: document.id,
    backendId: document.id,
    name: document.filename,
    size: document.size,
    type: document.doc_type || 'Document',
    sha256: document.sha256,
    processingStatus: document.processing_status,
    extractedFields: document.extracted_fields || [],
    processingResult: document.processing_result,
  }
}

function mapInvestigation(record) {
  return {
    id: String(record.id),
    backendId: record.id,
    name: record.title,
    type: 'Document Analysis',
    description: record.description || '',
    priority: 'Medium',
    status: record.status === 'analyzed' ? 'Completed' : 'In Progress',
    date: record.created_at
      ? new Date(record.created_at).toLocaleDateString()
      : '',
    documents: (record.documents || []).map(mapDocument),
    findings: record.findings || [],
  }
}

function InvestigationPage({ onNavigate }) {
  const [investigations, setInvestigations] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState('All')
  const [modalOpen, setModalOpen] = useState(false)
  const [previewDocument, setPreviewDocument] = useState(null)
  const [auditOpen, setAuditOpen] = useState(false)
  const [auditEvents, setAuditEvents] = useState([])
  const [selectedInvestigation, setSelectedInvestigation] = useState(null)
  const [apiError, setApiError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  const [formData, setFormData] = useState({
    name: '',
    type: 'Document Analysis',
    description: '',
    priority: 'Medium'
  })

  useEffect(() => {
    let active = true

    async function loadInvestigations() {
      setIsLoading(true)
      try {
        const records = await api.getInvestigations()
        const details = await Promise.all(
          records.map((record) => api.getInvestigation(record.id))
        )
        if (active) {
          setInvestigations(details.map(mapInvestigation))
        }
      } catch (error) {
        if (active) setApiError(error.message)
      } finally {
        if (active) setIsLoading(false)
      }
    }

    loadInvestigations()
    return () => {
      active = false
    }
  }, [])

  const refreshInvestigation = async (id) => {
    const record = await api.getInvestigation(id)
    const updated = mapInvestigation(record)
    setInvestigations((previous) => [
      updated,
      ...previous.filter((item) => item.backendId !== record.id),
    ])
    setSelectedInvestigation((current) =>
      current?.backendId === record.id ? updated : current
    )
    return updated
  }

  const recordAuditEvent = (event) => {
    setAuditEvents((previous) => [
      {
        id: `AUD-${Date.now()}-${Math.random()}`,
        actor: 'Local session',
        timestamp: new Date().toISOString(),
        ...event,
      },
      ...previous,
    ])
  }

  const updateField = (event) => {
    const { name, value } = event.target
    setFormData((previous) => ({ ...previous, [name]: value }))
  }

  const handleCreateInvestigation = async (event) => {
    event.preventDefault()
    setApiError('')

    try {
      const created = await api.createInvestigation({
        title: formData.name.trim(),
        description: formData.description.trim(),
      })
      const newInvestigation = mapInvestigation(created)
      newInvestigation.type = formData.type
      newInvestigation.priority = formData.priority
      setInvestigations((previous) => [newInvestigation, ...previous])
      setSelectedInvestigation(newInvestigation)
      recordAuditEvent({
        type: 'created',
        action: 'Investigation created',
        description: `${newInvestigation.name} (#${newInvestigation.id}) was created.`,
        investigationId: newInvestigation.id,
      })
      setFormData({
        name: '',
        type: 'Document Analysis',
        description: '',
        priority: 'Medium'
      })
      setActiveFilter('All')
      setSearchQuery('')
      setModalOpen(false)
    } catch (error) {
      setApiError(error.message)
    }
  }

  const handleAnalyzeInvestigation = async () => {
    if (!selectedInvestigation || isAnalyzing) return
    setApiError('')
    setIsAnalyzing(true)
    try {
      await api.analyzeInvestigation(selectedInvestigation.backendId)
      await refreshInvestigation(selectedInvestigation.backendId)
      recordAuditEvent({
        type: 'analysis',
        action: 'Contextual analysis completed',
        description: `Analysis completed for ${selectedInvestigation.name}.`,
        investigationId: selectedInvestigation.id,
      })
    } catch (error) {
      setApiError(error.message)
    } finally {
      setIsAnalyzing(false)
    }
  }

  const handleDocumentSelection = async (event) => {
    const files = Array.from(event.target.files || [])

    if (!selectedInvestigation || files.length === 0) return
    setApiError('')
    setIsLoading(true)
    try {
      for (const file of files) {
        await api.uploadDocument(selectedInvestigation.backendId, file)
      }
      const updated = await refreshInvestigation(selectedInvestigation.backendId)
      recordAuditEvent({
        type: 'document',
        action: 'Documents processed',
        description: `${files.length} document(s) uploaded to ${updated.name}.`,
        investigationId: updated.id,
      })
    } catch (error) {
      setApiError(error.message)
    } finally {
      setIsLoading(false)
      event.target.value = ''
    }
  }

  const filteredInvestigations = investigations.filter((item) => {
    const query = searchQuery.toLowerCase()

    const matchesSearch =
      item.name.toLowerCase().includes(query) ||
      item.id.toLowerCase().includes(query) ||
      item.type.toLowerCase().includes(query)

    const matchesFilter =
      activeFilter === 'All' || item.status === activeFilter

    return matchesSearch && matchesFilter
  })

  const counts = {
    total: investigations.length,
    progress: investigations.filter(
      (item) => item.status === 'In Progress'
    ).length,
    completed: investigations.filter(
      (item) => item.status === 'Completed'
    ).length,
    onHold: investigations.filter(
      (item) => item.status === 'On Hold'
    ).length
  }

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  // ======================================
  // INVESTIGATION DETAILS VIEW
  // ======================================

  if (selectedInvestigation) {
    const item = investigations.find(
      (investigation) => investigation.id === selectedInvestigation.id
    ) || selectedInvestigation

    return (
      <div className="investigation-page">

        <button
          className="details-back-btn"
          onClick={() => setSelectedInvestigation(null)}
        >
          <ArrowLeft size={17} />
          Back to Investigations
        </button>

        <div className="details-header">
          <div>
            <span className="page-eyebrow">INVESTIGATION DETAILS</span>
            <h1>{item.name}</h1>
            <p>{item.id} · {item.type}</p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              type="button"
              className="investigation-primary-btn"
              onClick={handleAnalyzeInvestigation}
              disabled={isAnalyzing || item.documents.length === 0}
            >
              {isAnalyzing ? 'Analyzing…' : 'Analyze Investigation'}
            </button>
            <button
              type="button"
              className="document-view-btn"
              onClick={() => setAuditOpen(true)}
            >
              <History size={16} /> Audit Trail
            </button>
            <span className="details-status">
              <span className="status-dot" />
              {item.status}
            </span>
          </div>
        </div>

        <div className="investigation-overview">
          <div className="investigation-overview-card">
            <div className="overview-icon teal">
              <FolderSearch size={21} />
            </div>
            <div>
              <span>Investigation Type</span>
              <h2 className="details-small-value">{item.type}</h2>
            </div>
          </div>

          <div className="investigation-overview-card">
            <div className="overview-icon purple">
              <FileText size={21} />
            </div>
            <div>
              <span>Documents</span>
              <h2>{item.documents.length}</h2>
            </div>
          </div>

          <div className="investigation-overview-card">
            <div className="overview-icon orange">
              <CircleAlert size={21} />
            </div>
            <div>
              <span>Priority</span>
              <h2 className="details-small-value">{item.priority}</h2>
            </div>
          </div>

          <div className="investigation-overview-card">
            <div className="overview-icon green">
              <CalendarDays size={21} />
            </div>
            <div>
              <span>Created On</span>
              <h2 className="details-small-value">{item.date}</h2>
            </div>
          </div>
        </div>

        <div className="details-content-grid">

          <section className="investigation-list-panel details-overview-panel">
            <div className="investigation-list-heading">
              <div>
                <h3>Investigation Overview</h3>
                <p>Basic information and description</p>
              </div>
            </div>

            <div className="details-description">
              <span>Description</span>
              <p>
                {item.description || 'No description provided for this investigation.'}
              </p>

              <div className="details-information-row">
                <div>
                  <span>Investigation ID</span>
                  <strong>{item.id}</strong>
                </div>
                <div>
                  <span>Priority</span>
                  <strong>{item.priority}</strong>
                </div>
                <div>
                  <span>Status</span>
                  <strong>{item.status}</strong>
                </div>
              </div>

              <div className="details-status-control">
                <label htmlFor="investigation-status">Update Status</label>
                <select
                  id="investigation-status"
                  value={item.status}
                  disabled
                >
                  <option>In Progress</option>
                  <option>Completed</option>
                  <option>On Hold</option>
                </select>
              </div>
            </div>
          </section>

          <section className="investigation-list-panel details-documents-panel">
            <div className="investigation-list-heading">
              <div>
                <h3>Associated Documents</h3>
                <p>Documents linked to this investigation</p>
              </div>
              <span className="investigation-count">
                {item.documents.length} Files
              </span>
            </div>

            <div className="associated-documents-content">
              {item.documents.length === 0 ? (
                <div className="associated-documents-empty">
                  <FileText size={30} />
                  <strong>No documents associated</strong>
                  <p>Attach documents to this investigation.</p>
                </div>
              ) : (
                <div className="associated-document-list">
                  {item.documents.map((doc) => (
                    <div className="associated-document" key={doc.id}>
                      <FileText size={21} />
                      <div className="associated-document-info">
                        <strong>{doc.name}</strong>
                        <span>
                          {doc.size ? formatSize(doc.size) : doc.processingStatus}
                        </span>
                      </div>
                      <button
  type="button"
  className="document-view-btn"
  onClick={() => setPreviewDocument(doc.file)}
  disabled={!doc.file}
>
  View
</button>
                    </div>
                  ))}
                </div>
              )}

              <DocumentSelector
                onFilesSelected={(files) => {
                  handleDocumentSelection({
                    target: { files, value: '' }
                  })
                }}
              />
              {isLoading && <p>Processing documents…</p>}
            </div>
          </section>

        </div>

        <section className="investigation-list-panel">
          <div className="investigation-list-heading">
            <div>
              <h3>Investigation Findings</h3>
              <p>Evidence-linked indicators; human review is required.</p>
            </div>
            <span className="investigation-count">
              {item.findings?.length || 0} Findings
            </span>
          </div>
          {item.findings?.length ? item.findings.map((finding) => (
            <article key={finding.id} className="associated-document">
              <div>
                <strong>{finding.title}</strong>
                <p>{finding.explanation}</p>
                <span>
                  {finding.severity} · {finding.classification}
                </span>
                {(finding.evidence || []).map((evidence, index) => (
                  <small key={`${evidence.document_id}-${evidence.page}-${index}`}>
                    Document {evidence.document_id}, page {evidence.page}
                    {evidence.bbox
                      ? ` · region ${evidence.bbox.x0}, ${evidence.bbox.y0}`
                      : ''}
                    {evidence.value ? ` · ${evidence.label}: ${evidence.value}` : ''}
                  </small>
                ))}
              </div>
            </article>
          )) : (
            <div className="associated-documents-empty">
              <p>
                {item.documents.length
                  ? 'Run analysis to compare the processed documents.'
                  : 'Upload documents to begin the investigation.'}
              </p>
            </div>
          )}
        </section>

        {apiError && <section className="upload-errors" role="alert">{apiError}</section>}

        {previewDocument && (
          <DocumentViewer
            file={previewDocument}
            onClose={() => setPreviewDocument(null)}
          />
        )}
        <AuditTrailModal
          isOpen={auditOpen}
          onClose={() => setAuditOpen(false)}
          title={`${item.name} — Audit Trail`}
          events={auditEvents.filter((event) => event.investigationId === item.id)}
        />
      </div>
    )
  }

  // ======================================
  // INVESTIGATIONS LIST VIEW
  // ======================================

  return (
    <div className="investigation-page">

      <div className="investigation-header">
        <div>
          <span className="page-eyebrow">WORKSPACE</span>
          <h1>Investigations</h1>
          <p>Manage, monitor and organize your document investigations.</p>
        </div>

        {apiError && <section className="upload-errors" role="alert">{apiError}</section>}
        {isLoading && investigations.length === 0 && <p>Loading investigations…</p>}

        <button
          className="investigation-primary-btn"
          onClick={() => setModalOpen(true)}
        >
          <Plus size={18} />
          New Investigation
        </button>
      </div>

      <div className="investigation-overview">

        <div className="investigation-overview-card">
          <div className="overview-icon teal"><FolderSearch size={21} /></div>
          <div><span>Total Investigations</span><h2>{counts.total}</h2></div>
        </div>

        <div className="investigation-overview-card">
          <div className="overview-icon purple"><Clock3 size={21} /></div>
          <div><span>In Progress</span><h2>{counts.progress}</h2></div>
        </div>

        <div className="investigation-overview-card">
          <div className="overview-icon green"><CircleCheck size={21} /></div>
          <div><span>Completed</span><h2>{counts.completed}</h2></div>
        </div>

        <div className="investigation-overview-card">
          <div className="overview-icon orange"><CircleAlert size={21} /></div>
          <div><span>On Hold</span><h2>{counts.onHold}</h2></div>
        </div>

      </div>

      <div className="investigation-toolbar">

        <div className="investigation-search">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search investigations..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />

          {searchQuery && (
            <button
              className="search-clear-btn"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
            >
              <X size={16} />
            </button>
          )}
        </div>

        <div className="investigation-filter-label">
          <SlidersHorizontal size={17} />
          <span>Filter:</span>
        </div>

        <div className="investigation-filters">
          {filters.map((filter) => (
            <button
              key={filter}
              className={`investigation-filter-btn ${
                activeFilter === filter ? 'active' : ''
              }`}
              onClick={() => setActiveFilter(filter)}
            >
              {filter}
            </button>
          ))}
        </div>

      </div>

      <div className="investigation-list-panel">

        <div className="investigation-list-heading">
          <div>
            <h3>All Investigations</h3>
            <p>Your investigation workspace</p>
          </div>

          <span className="investigation-count">
            {filteredInvestigations.length} Records
          </span>
        </div>

        {filteredInvestigations.length === 0 ? (
          <div className="investigation-empty-state">
            <div className="investigation-empty-icon">
              <FolderSearch size={34} />
            </div>

            <h3>
              {searchQuery || investigations.length > 0
                ? 'No matching investigations'
                : 'No investigations yet'}
            </h3>

            <p>
              {searchQuery || investigations.length > 0
                ? 'Try changing your search or selected filter.'
                : 'Your investigations will appear here once you create your first investigation.'}
            </p>

            {investigations.length === 0 && (
              <button
                className="investigation-primary-btn empty-action-btn"
                onClick={() => setModalOpen(true)}
              >
                <Plus size={18} />
                Start an Investigation
              </button>
            )}
          </div>
        ) : (
          <div className="investigation-records">
            {filteredInvestigations.map((item) => (
              <button
                key={item.id}
                className="investigation-record clickable-investigation-record"
                onClick={() => setSelectedInvestigation(item)}
              >
                <div className="record-file-icon">
                  <FolderSearch size={21} />
                </div>

                <div className="record-main-info">
                  <strong>{item.name}</strong>
                  <span>{item.id} · {item.type}</span>
                </div>

                <div className="record-meta">
                  <span className={`priority-label priority-${item.priority.toLowerCase()}`}>
                    {item.priority} Priority
                  </span>
                  <span className="record-status">
                    <span className="status-dot" />
                    {item.status}
                  </span>
                  <small>{item.date}</small>
                </div>

                <MoreHorizontal size={19} className="record-more-icon" />
              </button>
            ))}
          </div>
        )}

      </div>

      {/* CREATE MODAL */}

      {modalOpen && (
        <div
          className="investigation-modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setModalOpen(false)
            }
          }}
        >
          <div className="investigation-modal">

            <div className="investigation-modal-header">
              <div>
                <span className="page-eyebrow">WORKSPACE</span>
                <h2>Create Investigation</h2>
                <p>Enter the basic details for your new investigation.</p>
              </div>

              <button
                className="modal-close-btn"
                onClick={() => setModalOpen(false)}
                aria-label="Close modal"
              >
                <X size={21} />
              </button>
            </div>

            <form onSubmit={handleCreateInvestigation}>

              <div className="investigation-form-group">
                <label htmlFor="investigation-name">Investigation Name *</label>
                <input
                  id="investigation-name"
                  name="name"
                  type="text"
                  placeholder="Enter investigation name"
                  value={formData.name}
                  onChange={updateField}
                  maxLength={100}
                  required
                />
              </div>

              <div className="investigation-form-row">
                <div className="investigation-form-group">
                  <label htmlFor="investigation-type">Investigation Type</label>
                  <select
                    id="investigation-type"
                    name="type"
                    value={formData.type}
                    onChange={updateField}
                  >
                    <option>Document Analysis</option>
                    <option>Financial Investigation</option>
                    <option>Fraud Detection</option>
                    <option>Compliance Review</option>
                    <option>General Investigation</option>
                  </select>
                </div>

                <div className="investigation-form-group">
                  <label htmlFor="investigation-priority">Priority</label>
                  <select
                    id="investigation-priority"
                    name="priority"
                    value={formData.priority}
                    onChange={updateField}
                  >
                    <option>Low</option>
                    <option>Medium</option>
                    <option>High</option>
                    <option>Critical</option>
                  </select>
                </div>
              </div>

              <div className="investigation-form-group">
                <label htmlFor="investigation-description">Description</label>
                <textarea
                  id="investigation-description"
                  name="description"
                  placeholder="Describe the purpose of this investigation..."
                  rows={4}
                  value={formData.description}
                  onChange={updateField}
                  maxLength={1000}
                />
              </div>

              <div className="investigation-modal-actions">
                <button
                  type="button"
                  className="modal-cancel-btn"
                  onClick={() => setModalOpen(false)}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="investigation-primary-btn"
                >
                  <Plus size={17} />
                  Create Investigation
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

    </div>
  )
}

export default InvestigationPage
