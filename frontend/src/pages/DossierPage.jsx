import { useEffect, useMemo, useState } from 'react'
import {
  FileText,
  Plus,
  Search,
  Filter,
  Eye,
  Pencil,
  Trash2,
  X,
  ArrowLeft,
  CalendarDays,
  FolderOpen,
  FileCheck2,
  Clock3,
  Printer,
  ClipboardList,
  ShieldCheck,
} from 'lucide-react'
import StatusPill from '../components/StatusPill'
import api from '../services/api'
import { formatDate as formatLocalDate } from '../utils/dateTime'

const initialForm = {
  title: '',
  investigation: '',
  priority: 'Medium',
  summary: '',
  status: 'Draft',
}

const statusOptions = ['Draft', 'In Review', 'Completed']
const priorityOptions = ['Low', 'Medium', 'High', 'Critical']

function formatDate(date) {
  return formatLocalDate(date)
}

export default function DossierPage() {
  const [dossiers, setDossiers] = useState([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All Statuses')
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [selectedDossier, setSelectedDossier] = useState(null)
  const [form, setForm] = useState(initialForm)
  const [investigations, setInvestigations] = useState([])
  const [selectedInvestigationId, setSelectedInvestigationId] = useState('')
  const [reports, setReports] = useState([])
  const [apiError, setApiError] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false)

  useEffect(() => {
    api.getInvestigations()
      .then((records) => {
        setInvestigations(records)
        if (records.length) setSelectedInvestigationId(String(records[0].id))
      })
      .catch((error) => setApiError(error.message))
  }, [])

  useEffect(() => {
    if (!selectedInvestigationId) {
      setReports([])
      return
    }

    api.getReports(selectedInvestigationId)
      .then(setReports)
      .catch((error) => setApiError(error.message))
  }, [selectedInvestigationId])

  const generateInvestigationReport = async () => {
    if (!selectedInvestigationId || isGenerating) return
    setApiError('')
    setIsGenerating(true)
    try {
      await api.generateReport(selectedInvestigationId)
      setReports(await api.getReports(selectedInvestigationId))
    } catch (error) {
      setApiError(error.message)
    } finally {
      setIsGenerating(false)
    }
  }

  const generateInvestigationPdf = async () => {
    if (!selectedInvestigationId || isGeneratingPdf) return
    setApiError('')
    setIsGeneratingPdf(true)
    try {
      await api.generatePdfReport(selectedInvestigationId)
      setReports(await api.getReports(selectedInvestigationId))
    } catch (error) {
      setApiError(error.message)
    } finally {
      setIsGeneratingPdf(false)
    }
  }

  const stats = useMemo(() => ({
    total: dossiers.length,
    draft: dossiers.filter(item => item.status === 'Draft').length,
    review: dossiers.filter(item => item.status === 'In Review').length,
    completed: dossiers.filter(item => item.status === 'Completed').length,
  }), [dossiers])

  const filteredDossiers = useMemo(() => {
    return dossiers.filter(item => {
      const matchesSearch =
        item.title.toLowerCase().includes(search.toLowerCase()) ||
        item.id.toLowerCase().includes(search.toLowerCase()) ||
        item.investigation.toLowerCase().includes(search.toLowerCase())

      const matchesStatus =
        statusFilter === 'All Statuses' || item.status === statusFilter

      return matchesSearch && matchesStatus
    })
  }, [dossiers, search, statusFilter])

  const openCreateModal = () => {
    setEditingId(null)
    setForm(initialForm)
    setShowModal(true)
  }

  const openEditModal = (dossier) => {
    setEditingId(dossier.id)
    setForm({
      title: dossier.title,
      investigation: dossier.investigation,
      priority: dossier.priority,
      summary: dossier.summary,
      status: dossier.status,
    })
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditingId(null)
    setForm(initialForm)
  }

  const handleSubmit = (event) => {
    event.preventDefault()

    if (!form.title.trim() || !form.investigation.trim()) return

    if (editingId) {
      const updated = dossiers.map(item =>
        item.id === editingId
          ? { ...item, ...form, updatedAt: new Date().toISOString() }
          : item
      )
      setDossiers(updated)

      if (selectedDossier?.id === editingId) {
        setSelectedDossier({ ...selectedDossier, ...form })
      }
    } else {
      const newDossier = {
        ...form,
        id: `DOS-${Date.now().toString().slice(-7)}`,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
      setDossiers(prev => [newDossier, ...prev])
    }

    closeModal()
  }

  const deleteDossier = (id) => {
    const confirmed = window.confirm(
      'Are you sure you want to delete this dossier?'
    )
    if (!confirmed) return

    setDossiers(prev => prev.filter(item => item.id !== id))
    if (selectedDossier?.id === id) setSelectedDossier(null)
  }

  const updateStatus = (id, status) => {
    setDossiers(prev =>
      prev.map(item =>
        item.id === id
          ? { ...item, status, updatedAt: new Date().toISOString() }
          : item
      )
    )

    if (selectedDossier?.id === id) {
      setSelectedDossier(prev => ({ ...prev, status }))
    }
  }

  const getStatusClass = (status) => {
    if (status === 'Completed') return 'completed'
    if (status === 'In Review') return 'review'
    return 'draft'
  }

  const getPriorityClass = (priority) => priority.toLowerCase()

  if (selectedDossier) {
    const currentDossier =
      dossiers.find(item => item.id === selectedDossier.id) || selectedDossier

    return (
      <div className="dossiers-page">
        <button
          className="dossier-back-btn"
          onClick={() => setSelectedDossier(null)}
        >
          <ArrowLeft size={17} />
          Back to Dossiers
        </button>

        <div className="dossier-detail-header">
          <div>
            <span className="dossier-eyebrow">DOSSIER DETAILS</span>
            <h1>{currentDossier.title}</h1>
            <p>{currentDossier.id} · Created {formatDate(currentDossier.createdAt)}</p>
          </div>

          <div className="dossier-detail-actions">
            <button
              className="dossier-secondary-btn"
              onClick={() => window.print()}
            >
              <Printer size={16} />
              Print Report
            </button>
            <button
              className="dossier-primary-btn"
              onClick={() => openEditModal(currentDossier)}
            >
              <Pencil size={16} />
              Edit Dossier
            </button>
          </div>
        </div>

        <div className="dossier-detail-grid">
          <section className="dossier-detail-main">
            <div className="dossier-panel">
              <div className="dossier-panel-heading">
                <FileText size={19} />
                <h2>Dossier Summary</h2>
              </div>
              <p className="dossier-summary-text">
                {currentDossier.summary || 'No summary has been added to this dossier yet.'}
              </p>
            </div>

            <div className="dossier-panel dossier-report-panel">
              <div className="dossier-panel-heading">
                <ClipboardList size={19} />
                <h2>Report Preview</h2>
              </div>
              <div className="dossier-report-content">
                <h3>{currentDossier.title}</h3>
                <p className="dossier-report-meta">
                  Reference: {currentDossier.id}
                </p>
                <div className="dossier-report-divider" />
                <h4>Investigation Reference</h4>
                <p>{currentDossier.investigation}</p>
                <h4>Executive Summary</h4>
                <p>
                  {currentDossier.summary || 'Summary not provided.'}
                </p>
                <h4>Conclusion</h4>
                <p className="dossier-report-placeholder">
                  Conclusion and supporting evidence can be added when the
                  investigation findings are available.
                </p>
              </div>
            </div>
          </section>

          <aside className="dossier-detail-sidebar">
            <div className="dossier-panel">
              <div className="dossier-panel-heading">
                <ShieldCheck size={19} />
                <h2>Dossier Information</h2>
              </div>

              <div className="dossier-info-item">
                <span>Status</span>
                <select
                  value={currentDossier.status}
                  onChange={event => updateStatus(currentDossier.id, event.target.value)}
                  className={`dossier-status-select ${getStatusClass(currentDossier.status)}`}
                >
                  {statusOptions.map(status => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </div>

              <div className="dossier-info-item">
                <span>Priority</span>
                <strong className={`dossier-priority ${getPriorityClass(currentDossier.priority)}`}>
                  {currentDossier.priority}
                </strong>
              </div>

              <div className="dossier-info-item">
                <span>Investigation</span>
                <strong>{currentDossier.investigation}</strong>
              </div>

              <div className="dossier-info-item">
                <span>Created</span>
                <strong>{formatDate(currentDossier.createdAt)}</strong>
              </div>

              <div className="dossier-info-item">
                <span>Last Updated</span>
                <strong>{formatDate(currentDossier.updatedAt)}</strong>
              </div>
            </div>
          </aside>
        </div>

        {showModal && renderModal()}
      </div>
    )
  }

  function renderModal() {
    return (
      <div className="dossier-modal-overlay" onClick={closeModal}>
        <div className="dossier-modal" onClick={event => event.stopPropagation()}>
          <div className="dossier-modal-header">
            <div>
              <h2>{editingId ? 'Edit Dossier' : 'Create New Dossier'}</h2>
              <p>Enter the details for this investigation dossier.</p>
            </div>
            <button className="dossier-modal-close" onClick={closeModal}>
              <X size={19} />
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="dossier-form-group">
              <label>Dossier Title <span>*</span></label>
              <input
                value={form.title}
                onChange={event => setForm({ ...form, title: event.target.value })}
                placeholder="e.g. Financial Fraud Investigation"
                required
              />
            </div>

            <div className="dossier-form-group">
              <label>Investigation Name / ID <span>*</span></label>
              <input
                value={form.investigation}
                onChange={event => setForm({ ...form, investigation: event.target.value })}
                placeholder="Enter investigation name or ID"
                required
              />
            </div>

            <div className="dossier-form-row">
              <div className="dossier-form-group">
                <label>Priority</label>
                <select
                  value={form.priority}
                  onChange={event => setForm({ ...form, priority: event.target.value })}
                >
                  {priorityOptions.map(priority => (
                    <option key={priority} value={priority}>{priority}</option>
                  ))}
                </select>
              </div>

              <div className="dossier-form-group">
                <label>Status</label>
                <select
                  value={form.status}
                  onChange={event => setForm({ ...form, status: event.target.value })}
                >
                  {statusOptions.map(status => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="dossier-form-group">
              <label>Executive Summary</label>
              <textarea
                rows="4"
                value={form.summary}
                onChange={event => setForm({ ...form, summary: event.target.value })}
                placeholder="Write a brief summary of this dossier..."
              />
            </div>

            <div className="dossier-modal-footer">
              <button type="button" className="dossier-secondary-btn" onClick={closeModal}>
                Cancel
              </button>
              <button type="submit" className="dossier-primary-btn">
                {editingId ? 'Save Changes' : 'Create Dossier'}
              </button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="dossiers-page">
      <div className="dossiers-header">
        <div>
          <span className="dossier-eyebrow">INVESTIGATION WORKSPACE</span>
          <h1>Dossiers & Reports</h1>
          <p>Generate structured data or a navigable PDF dossier for a standard investigation.</p>
        </div>

        <button className="dossier-primary-btn" onClick={openCreateModal}>
          <Plus size={18} />
          Create Dossier
        </button>
      </div>

      <section className="dossier-panel">
        <div className="dossier-panel-heading">
          <ClipboardList size={19} />
          <h2>Investigation Dossiers</h2>
        </div>
        <div className="dossiers-toolbar">
          <div className="dossiers-filter">
            <select
              aria-label="Select investigation for dossier"
              value={selectedInvestigationId}
              onChange={(event) => setSelectedInvestigationId(event.target.value)}
            >
              <option value="">Select an investigation</option>
              {investigations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title} (#{item.id})
                </option>
              ))}
            </select>
          </div>
          <div className="dossier-detail-actions">
            <button
              className="dossier-secondary-btn"
              onClick={generateInvestigationReport}
              disabled={!selectedInvestigationId || isGenerating || isGeneratingPdf}
            >
              <FileText size={17} />
              {isGenerating ? 'Generating…' : 'Generate structured JSON'}
            </button>
            <button
              className="dossier-primary-btn"
              onClick={generateInvestigationPdf}
              disabled={!selectedInvestigationId || isGenerating || isGeneratingPdf}
            >
              <FileCheck2 size={17} />
              {isGeneratingPdf ? 'Generating…' : 'Generate formatted PDF'}
            </button>
          </div>
        </div>
        {apiError && <p role="alert">{apiError}</p>}
        {reports.length ? (
          <div className="associated-document-list">
            {reports.map((report) => (
              <div className="associated-document" key={report.id}>
                <FileText size={20} />
                <div className="associated-document-info">
                  <strong>Investigation #{report.investigation_id} {report.format?.toUpperCase() || 'JSON'} report</strong>
                  <span>{formatDate(report.created_at)}</span>
                </div>
                <a
                  className="dossier-secondary-btn"
                  href={api.getReportDownloadUrl(report.id)}
                  download
                >
                  <FileCheck2 size={16} />
                  Download {report.format?.toUpperCase() || 'JSON'} dossier
                </a>
              </div>
            ))}
          </div>
        ) : (
          <p>
            {selectedInvestigationId
              ? 'No generated reports for this investigation yet.'
              : 'Create or select an investigation to generate its dossier.'}
          </p>
        )}
      </section>

      <div className="dossiers-stats">
        <div className="dossier-stat-card">
          <div className="dossier-stat-icon teal"><FolderOpen size={21} /></div>
          <div><span>Total Dossiers</span><strong>{stats.total}</strong></div>
        </div>
        <div className="dossier-stat-card">
          <div className="dossier-stat-icon amber"><Clock3 size={21} /></div>
          <div><span>Draft</span><strong>{stats.draft}</strong></div>
        </div>
        <div className="dossier-stat-card">
          <div className="dossier-stat-icon purple"><FileText size={21} /></div>
          <div><span>In Review</span><strong>{stats.review}</strong></div>
        </div>
        <div className="dossier-stat-card">
          <div className="dossier-stat-icon green"><FileCheck2 size={21} /></div>
          <div><span>Completed</span><strong>{stats.completed}</strong></div>
        </div>
      </div>

      <div className="dossiers-toolbar">
        <div className="dossiers-search">
          <Search size={18} />
          <input
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Search dossiers by title, ID or investigation..."
          />
        </div>

        <div className="dossiers-filter">
          <Filter size={17} />
          <select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}>
            <option>All Statuses</option>
            {statusOptions.map(status => (
              <option key={status}>{status}</option>
            ))}
          </select>
        </div>
      </div>

      <section className="dossiers-table-panel">
        <div className="dossiers-table-heading">
          <div>
            <h2>All Dossiers</h2>
            <p>Review and manage your investigation reports.</p>
          </div>
          <span>{filteredDossiers.length} records</span>
        </div>

        {filteredDossiers.length > 0 ? (
          <div className="dossiers-table-wrap">
            <table className="dossiers-table">
              <thead>
                <tr>
                  <th>DOSSIER</th>
                  <th>INVESTIGATION</th>
                  <th>PRIORITY</th>
                  <th>STATUS</th>
                  <th>DATE CREATED</th>
                  <th>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {filteredDossiers.map(dossier => (
                  <tr key={dossier.id}>
                    <td>
                      <strong>{dossier.title}</strong>
                      <small>{dossier.id}</small>
                    </td>
                    <td>{dossier.investigation}</td>
                    <td>
                      <span className={`dossier-priority ${getPriorityClass(dossier.priority)}`}>
                        {dossier.priority}
                      </span>
                    </td>
                    <td>
                      <StatusPill status={dossier.status} variant="dossier" />
                    </td>
                    <td><span className="dossier-date"><CalendarDays size={14} />{formatDate(dossier.createdAt)}</span></td>
                    <td>
                      <div className="dossier-row-actions">
                        <button title="View dossier" onClick={() => setSelectedDossier(dossier)}>
                          <Eye size={17} />
                        </button>
                        <button title="Edit dossier" onClick={() => openEditModal(dossier)}>
                          <Pencil size={16} />
                        </button>
                        <button title="Delete dossier" onClick={() => deleteDossier(dossier.id)}>
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="dossiers-empty">
            <div className="dossiers-empty-icon"><FileText size={28} /></div>
            <h3>{search || statusFilter !== 'All Statuses' ? 'No matching dossiers' : 'No dossiers yet'}</h3>
            <p>
              {search || statusFilter !== 'All Statuses'
                ? 'Try changing your search or filter.'
                : 'Create a dossier to organize investigation summaries and reports.'}
            </p>
            {!search && statusFilter === 'All Statuses' && (
              <button className="dossier-primary-btn" onClick={openCreateModal}>
                <Plus size={17} />
                Create First Dossier
              </button>
            )}
          </div>
        )}
      </section>

      <div className="dossiers-footer">
        <span>DECIPHER DOCUMENT INTELLIGENCE</span>
        <span>Version 1.0.0 · Development Preview</span>
      </div>

      {showModal && renderModal()}
    </div>
  )
}